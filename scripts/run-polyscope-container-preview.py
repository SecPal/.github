#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Start the preview container with narrowly writable API runtime storage."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shlex
import subprocess


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


def observe_runtime_members(args) -> set[str]:
    renderer = load_renderer(args.renderer)
    rollout = load_renderer(pathlib.Path(__file__).resolve().with_name("polyscope-rollout.py"))
    identifiers = renderer.repository_ids(args.db_path, args.repository_root)
    repository_id = identifiers.get("SecPal/api")
    if repository_id is None:
        return set()
    worktrees = {}
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
        '{"Id":"{{.Id}}","Name":"{{.Name}}","Image":"{{.Image}}",'
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
    return owned_runtime_container_names(
        rows, expected_images=expected_images, network=args.network, worktrees=worktrees,
        role_commands={role: shlex.split(command) for role, command in rollout.API_RUNTIME_ROLE_COMMANDS.items()},
    )


def build_command(
    *,
    renderer_path: pathlib.Path,
    db_path: pathlib.Path,
    clone_root: pathlib.Path,
    repository_root: pathlib.Path,
    caddyfile: pathlib.Path,
    image: str,
    network: str,
    preview_port: int,
) -> list[str]:
    renderer = load_renderer(renderer_path)
    identifiers = renderer.repository_ids(db_path, repository_root)
    api_repository_id = identifiers.get("SecPal/api")
    command = [
        "/usr/bin/podman",
        "run",
        "--replace",
        "--rm",
        "--name",
        "polyscope-preview",
        "--network",
        network,
        "-e",
        "DB_HOST=polyscope-postgresql-proxy",
        "-e",
        "DB_PORT=5432",
        "-p",
        f"127.0.0.1:{preview_port}:18080",
        "-v",
        f"{caddyfile}:/etc/frankenphp/Caddyfile:ro",
        "-v",
        f"{clone_root}:/workspaces:ro",
        "-v",
        f"{clone_root}:{clone_root}:ro",
    ]
    if api_repository_id is not None:
        for _logical_workspace, physical_workspace in renderer.active_workspaces(
            db_path, api_repository_id, clone_root, "public",
            require_runtime_admission=True,
        ):
            repository_clone_root = renderer._resolved(clone_root / api_repository_id)
            physical_worktree = renderer._resolved(
                clone_root / api_repository_id / physical_workspace
            )
            storage_path = physical_worktree / "storage"
            if storage_path.is_symlink() or not storage_path.is_dir():
                raise RuntimeError(
                    f"writable API runtime directory is unavailable: {storage_path}"
                )
            storage = renderer._resolved(storage_path)
            if not storage.is_dir() or storage.parent != physical_worktree:
                raise RuntimeError(
                    f"writable API runtime directory is unavailable: {storage_path}"
                )
            if physical_worktree.parent != repository_clone_root:
                raise RuntimeError(f"active API worktree escapes its clone root: {physical_worktree}")
            target = pathlib.PurePosixPath(
                "/workspaces", api_repository_id, physical_workspace, "storage"
            )
            command.extend(["-v", f"{storage}:{target}:rw"])
    command.extend(
        [
            "--entrypoint",
            "/usr/local/bin/frankenphp",
            "--",
            image,
            "run",
            "--config",
            "/etc/frankenphp/Caddyfile",
            "--adapter",
            "caddyfile",
        ]
    )
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observe-runtime-members", action="store_true")
    parser.add_argument("--renderer", required=True, type=pathlib.Path)
    parser.add_argument("--db-path", required=True, type=pathlib.Path)
    parser.add_argument("--clone-root", required=True, type=pathlib.Path)
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--caddyfile", required=True, type=pathlib.Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--preview-port", required=True, type=int)
    args = parser.parse_args()
    for path in (
        args.renderer,
        args.db_path,
        args.clone_root,
        args.repository_root,
        args.caddyfile,
    ):
        if not path.is_absolute():
            parser.error(f"path must be absolute: {path}")
    if SAFE_NAME.fullmatch(args.image) is None or SAFE_NAME.fullmatch(args.network) is None:
        parser.error("image or network contains unsupported characters")
    if not 1 <= args.preview_port <= 65535:
        parser.error("preview port must be between 1 and 65535")
    if args.observe_runtime_members:
        print("\n".join(sorted(observe_runtime_members(args))))
        return 0
    command = build_command(
        renderer_path=args.renderer,
        db_path=args.db_path,
        clone_root=args.clone_root,
        repository_root=args.repository_root,
        caddyfile=args.caddyfile,
        image=args.image,
        network=args.network,
        preview_port=args.preview_port,
    )
    os.execv(command[0], command)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
