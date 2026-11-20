#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Start the rootless Nginx preview and its admitted PHP-FPM backends."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import time


PODMAN = "/usr/bin/podman"
CONTAINER_ROOT = pathlib.Path("/workspaces")
SOCKET_ROOT = "/run/preview-sockets"
FPM_CONFIG_PATH = "/run/preview/fpm.conf"
FPM_COMMAND = ["--nodaemonize", "--fpm-config", FPM_CONFIG_PATH]
FPM_CONFIG = """[global]
error_log = /proc/self/fd/2
[www]
listen = /run/preview-php/api.sock
listen.mode = 0600
pm = ondemand
pm.max_children = 4
clear_env = yes
env[DB_HOST] = polyscope-postgresql-proxy
env[DB_PORT] = 5432
env[APP_ENV] = local
env[APP_DEBUG] = "false"
security.limit_extensions = .php
php_admin_flag[display_errors] = off
"""
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]*$")


def load_renderer(renderer_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("polyscope_preview_renderer", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load preview renderer: {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def owned_runtime_container_names(
    rows: list[dict], *, expected_images: set[str], network: str,
    worktrees: dict[pathlib.Path, tuple[str, str]], role_commands: dict[str, list[str]],
    proc_root: pathlib.Path = pathlib.Path("/proc"),
) -> set[str]:
    """Admit existing native workers for preservation, never by name alone."""
    owned: set[str] = set()
    uid = os.getuid()
    for row in rows:
        role = next((role for role, command in role_commands.items()
                     if command == row.get("Config", {}).get("Cmd")), None)
        if (role is None or row.get("Image", "").removeprefix("sha256:") not in expected_images
                or not row.get("State", {}).get("Running")
                or set(row.get("NetworkSettings", {}).get("Networks", {})) != {network}
                or row.get("Config", {}).get("Entrypoint") not in (None, [])
                or row.get("Config", {}).get("WorkingDir") != "/app"):
            continue
        mounted = [pathlib.Path(mount["Source"]) for mount in row.get("Mounts", [])
                   if mount.get("Destination") == "/app" and isinstance(mount.get("Source"), str)]
        if len(mounted) != 1 or mounted[0] not in worktrees:
            continue
        workspace, runtime_id = worktrees[mounted[0]]
        unit = f"polyscope-api-worktree-{workspace}-{runtime_id}-{role}.service"
        monitor_pid = row.get("State", {}).get("ConmonPid")
        init_pid = row.get("State", {}).get("Pid")
        identifier = row.get("Id", "")
        if (type(monitor_pid) is not int or monitor_pid <= 1
                or type(init_pid) is not int or init_pid <= 1
                or re.fullmatch(r"[0-9a-f]{64}", identifier) is None):
            continue
        try:
            monitor = proc_root / str(monitor_pid)
            expected_group = (
                f"0::/user.slice/user-{uid}.slice/user@{uid}.service/app.slice/{unit}"
            )
            init = proc_root / str(init_pid)
            expected_init_group = (
                f"0::/user.slice/user-{uid}.slice/user@{uid}.service/"
                f"user.slice/libpod-{identifier}.scope/container"
            )
            if (init.stat().st_uid != uid
                    or (init / "cgroup").read_text().strip() != expected_init_group
                    or monitor.stat().st_uid != uid
                    or str((monitor / "exe").readlink()) != "/usr/bin/conmon"
                    or (monitor / "cgroup").read_text().strip() != expected_group):
                continue
        except OSError:
            continue
        name = row.get("Name", "").removeprefix("/")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            owned.add(name)
    return owned


def service_pod_id(runtime_directory: pathlib.Path) -> str | None:
    try:
        value = (runtime_directory / "pod-id").read_text().strip()
    except FileNotFoundError:
        return None
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RuntimeError("preview-pod-identity-invalid")
    return value


def observe_runtime_members(args) -> set[str]:
    renderer = load_renderer(args.renderer)
    rollout = load_renderer(pathlib.Path(__file__).resolve().with_name("polyscope-rollout.py"))
    identifiers = renderer.repository_ids(args.db_path, args.repository_root)
    repository_id = identifiers.get("SecPal/api")
    worktrees = {}
    if repository_id is not None:
        for workspace, physical in renderer.active_workspaces(
            args.db_path, repository_id, args.clone_root, "public"
        ):
            path = (args.clone_root / repository_id / physical).resolve(strict=True)
            worktrees[path] = (workspace, rollout.build_api_runtime_id(path))
    identifiers = subprocess.check_output(
        ["podman", "ps", "--filter", f"network={args.network}", "--format", "{{.ID}}"],
        text=True, timeout=10,
    ).splitlines()
    if not identifiers:
        return set()
    if len(identifiers) > 100 or any(re.fullmatch(r"[0-9a-f]{12,64}", value) is None for value in identifiers):
        raise RuntimeError("runtime-container-observation-invalid")
    template = (
        '{"Id":"{{.Id}}","Name":"{{.Name}}","Image":"{{.Image}}","Pod":"{{.Pod}}",'
        '"State":{"Pid":{{.State.Pid}},"ConmonPid":{{.State.ConmonPid}},"Running":{{.State.Running}}},'
        '"Config":{"Cmd":{{json .Config.Cmd}},"WorkingDir":{{json .Config.WorkingDir}},"Entrypoint":{{json .Config.Entrypoint}}},'
        '"NetworkSettings":{"Networks":{{json .NetworkSettings.Networks}}},"Mounts":{{json .Mounts}}}'
    )
    raw = subprocess.check_output(
        ["podman", "inspect", "--format", template, *identifiers], text=True, timeout=10,
    )
    if len(raw) > 1024 * 1024:
        raise RuntimeError("runtime-container-observation-limit")
    rows = [json.loads(line) for line in raw.splitlines()]
    target_image = subprocess.check_output(
        ["podman", "image", "inspect", args.image, "--format", "{{.Id}}"],
        text=True, timeout=10,
    ).strip().removeprefix("sha256:")
    expected_images = {target_image}
    for row in rows:
        if (row.get("Name", "").removeprefix("/") == "polyscope-preview"
                and args.network in row.get("NetworkSettings", {}).get("Networks", {})):
            expected_images.add(row.get("Image", "").removeprefix("sha256:"))
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in expected_images):
        raise RuntimeError("runtime-container-image-observation-invalid")
    owned = owned_runtime_container_names(
        rows, expected_images=expected_images, network=args.network, worktrees=worktrees,
        role_commands={role: shlex.split(command) for role, command in rollout.API_RUNTIME_ROLE_COMMANDS.items()},
    )
    pod = service_pod_id(args.runtime_directory)
    if pod is not None:
        for row in rows:
            name = row.get("Name", "").removeprefix("/")
            if (row.get("Pod") == pod
                    and re.fullmatch(r"polyscope-preview-fpm-[1-9][0-9]*", name)
                    and row.get("Config", {}).get("Cmd") == FPM_COMMAND
                    and set(row.get("NetworkSettings", {}).get("Networks", {})) == {args.network}):
                owned.add(name)
    return owned


def preview_commands(routes, runtime_directory, *, pod, image, nginx_image, network, preview_port):
    """Build the commands for one observed route snapshot and one owned Podman pod."""
    common = [
        PODMAN, "run", "--pod", pod, "--pull=never",
        "--userns=keep-id:uid=1000,gid=1000", "--user=1000:1000",
        "--read-only", "--cap-drop=all", "--security-opt=no-new-privileges",
    ]
    socket_root = runtime_directory / "sockets"
    gateway = common + [
        "--rm", "--name", "polyscope-preview", "--network=bridge", "--sdnotify=healthy",
        "--publish", f"127.0.0.1:{preview_port}:18080",
        "--health-cmd",
        "wget -S -T 3 -O /dev/null http://127.0.0.1:18080/ 2>&1 | grep -Eq 'HTTP/[0-9.]+ 404 '",
        "--health-interval=2s", "--health-timeout=5s", "--health-start-period=5s",
        "--volume", f"{runtime_directory / 'nginx.conf'}:/run/preview/nginx.conf:ro,z",
        "--volume", f"{socket_root}:{SOCKET_ROOT}:ro,z",
    ]
    backends = []
    for index, route in enumerate(routes, start=1):
        worktree = route.worktree
        gateway.extend([
            "--volume", f"{worktree / route.document_root}:{CONTAINER_ROOT / str(index)}:ro,z",
        ])
        if not route.php:
            continue
        storage = worktree / "storage"
        if storage.is_symlink() or not storage.is_dir() or storage.resolve() != storage:
            raise RuntimeError("writable API runtime directory is unavailable")
        backends.append(common + [
            "--detach", "--name", f"polyscope-preview-fpm-{index}",
            "--network", network, "--no-healthcheck", "--sdnotify=ignore",
            "--stop-signal=SIGQUIT", "--restart=on-failure",
            "--workdir", "/app",
            "--volume", f"{worktree}:/app:ro,z",
            "--volume", f"{storage}:/app/storage:rw,z",
            "--volume", f"{socket_root / str(index)}:/run/preview-php:rw,z",
            "--volume", f"{runtime_directory / 'fpm.conf'}:{FPM_CONFIG_PATH}:ro,z",
            "--entrypoint", "/usr/local/sbin/php-fpm", "--", image, *FPM_COMMAND,
        ])
    gateway.extend([
        "--entrypoint", "/usr/sbin/nginx", "--", nginx_image,
        "-c", "/run/preview/nginx.conf", "-g", "daemon off;",
    ])
    return backends, gateway


def remove_pod(runtime_directory: pathlib.Path) -> None:
    pod = service_pod_id(runtime_directory)
    if pod is not None:
        subprocess.run([PODMAN, "pod", "rm", "--ignore", "--force", "--time", "10", pod], check=True)
        (runtime_directory / "pod-id").unlink(missing_ok=True)
    try:
        shutil.rmtree(runtime_directory / "sockets")
    except FileNotFoundError:
        pass


def start_preview(args) -> None:
    if not args.runtime_directory.is_dir() or args.runtime_directory.is_symlink():
        raise RuntimeError("preview-runtime-directory-unavailable")
    if service_pod_id(args.runtime_directory) is not None:
        raise RuntimeError("preview-pod-already-owned")
    renderer = load_renderer(args.renderer)
    routes = renderer.preview_routes(args.db_path, args.clone_root, args.repository_root)
    sockets = args.runtime_directory / "sockets"
    listeners = []
    try:
        sockets.mkdir(mode=0o700)
        for index, route in enumerate(routes, start=1):
            if route.php:
                directory = sockets / str(index)
                directory.mkdir(mode=0o700)
                listeners.append(directory / "api.sock")
        renderer.write_atomic(args.runtime_directory / "nginx.conf", renderer.render_routes(routes, CONTAINER_ROOT))
        renderer.write_atomic(args.runtime_directory / "fpm.conf", FPM_CONFIG)

        # Group lifetime only, with independent mounts, network and process namespaces.
        subprocess.run([
            PODMAN, "pod", "create", "--infra=false", "--share=",
            "--pod-id-file", str(args.runtime_directory / "pod-id"),
        ], check=True, stdout=subprocess.DEVNULL)
        pod = service_pod_id(args.runtime_directory)
        if pod is None:
            raise RuntimeError("preview-pod-identity-unavailable")
        backends, gateway = preview_commands(
            routes, args.runtime_directory, pod=pod, image=args.image, nginx_image=args.nginx_image,
            network=args.network, preview_port=args.preview_port,
        )
        for command in backends:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while not all(path.is_socket() and not path.is_symlink() for path in listeners):
            if time.monotonic() >= deadline:
                raise RuntimeError("preview-fastcgi-socket-not-ready")
            time.sleep(0.1)
        os.execv(gateway[0], gateway)
    except BaseException:
        remove_pod(args.runtime_directory)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("start", "observe", "cleanup"):
        command = modes.add_parser(mode)
        command.add_argument("--runtime-directory", required=True, type=pathlib.Path)
        if mode != "cleanup":
            for name in ("renderer", "db-path", "clone-root", "repository-root"):
                command.add_argument("--" + name, required=True, type=pathlib.Path)
            command.add_argument("--image", required=True)
            command.add_argument("--network", required=True)
        if mode == "start":
            command.add_argument("--nginx-image", required=True)
            command.add_argument("--preview-port", required=True, type=int)
    args = parser.parse_args()
    for value in vars(args).values():
        if isinstance(value, pathlib.Path) and re.fullmatch(r"/[A-Za-z0-9._/+-]+", str(value)) is None:
            parser.error("paths must be safe absolute paths")
    if args.mode == "cleanup":
        remove_pod(args.runtime_directory)
    else:
        if SAFE_NAME.fullmatch(args.image) is None or SAFE_NAME.fullmatch(args.network) is None:
            parser.error("image or network contains unsupported characters")
        if args.mode == "observe":
            print("\n".join(sorted(observe_runtime_members(args))))
        else:
            if SAFE_NAME.fullmatch(args.nginx_image) is None or not 1 <= args.preview_port <= 65535:
                parser.error("Nginx image or preview port is invalid")
            start_preview(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
