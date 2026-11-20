#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import copy
import json
import pathlib
import os
import shutil
import sqlite3
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run-polyscope-container-preview.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_preview", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_owned_runtime_members(module):
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        monitor = root / "proc/42"
        monitor.mkdir(parents=True)
        (monitor / "exe").symlink_to("/usr/bin/conmon")
        unit = "polyscope-api-worktree-calm-otter-123456789abc-queue.service"
        (monitor / "cgroup").write_text(f"0::/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/app.slice/{unit}\n")
        init = root / "proc/43"
        init.mkdir()
        (init / "cgroup").write_text(
            f"0::/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/user.slice/libpod-{'b' * 64}.scope/container\n"
        )
        image = "a" * 64
        worktree = root / "clones/api/calm-otter"
        row = {
            "Id": "b" * 64, "Name": "/native-worker", "Image": image,
            "State": {"Pid": 43, "ConmonPid": 42, "Running": True},
            "Config": {"Cmd": ["php", "artisan", "queue:work"], "WorkingDir": "/app"},
            "NetworkSettings": {"Networks": {"preview-network": {}}},
            "Mounts": [{"Source": str(worktree), "Destination": "/app"}],
        }
        arguments = dict(expected_images={image}, network="preview-network",
            worktrees={worktree: ("calm-otter", "123456789abc")},
            role_commands={"queue": ["php", "artisan", "queue:work"]},
            proc_root=root / "proc")
        assert module.owned_runtime_container_names([row], **arguments) == {"native-worker"}
        for field, value in (
            ("Id", "invalid"),
            ("Image", "c" * 64),
            ("Config", {"Cmd": ["php", "arbitrary.php"], "WorkingDir": "/app"}),
            ("Config", {"Cmd": row["Config"]["Cmd"], "WorkingDir": "/app", "Entrypoint": ["/bin/sh"]}),
            ("NetworkSettings", {"Networks": {"preview-network": {}, "foreign-network": {}}}),
            ("Mounts", [{"Source": str(root / "unregistered"), "Destination": "/app"}]),
            ("NetworkSettings", {"Networks": {"foreign-network": {}}}),
            ("State", {"ConmonPid": 9999, "Running": True}),
        ):
            rejected = copy.deepcopy(row)
            rejected[field] = value
            assert module.owned_runtime_container_names([rejected], **arguments) == set(), field
        (monitor / "cgroup").write_text("0::/unrelated.service\n")
        assert module.owned_runtime_container_names([row], **arguments) == set()



def main() -> None:
    module = load_module()
    test_owned_runtime_members(module)
    image_recipe = (REPO_ROOT / "containers/polyscope-php/Containerfile").read_text()
    assert "FROM docker.io/library/php:8.4." in image_recipe
    assert "frankenphp" not in image_recipe.lower()
    with tempfile.TemporaryDirectory(prefix="polyscope-preview-runner.") as temporary:
        root = pathlib.Path(temporary)
        repository_root = root / "repos/SecPal"
        clone_root = root / "clones"
        (repository_root / "api").mkdir(parents=True)
        physical_worktree = clone_root / "api-repo/calm-otter-a1b2c3d4"
        (physical_worktree / "public").mkdir(parents=True)
        (physical_worktree / "storage").mkdir()
        (clone_root / "api-repo/.polyscope-secpal-workspace-aliases.json").write_text(
            json.dumps({"version": 1, "aliases": {"calm-otter": physical_worktree.name}})
        )
        db_path = root / "polyscope.db"
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "create table repositories (id text primary key, name text not null, path text not null)"
            )
            connection.execute(
                "create table worktrees (id text primary key, repo_id text not null, path text not null, status text not null)"
            )
            connection.execute(
                "insert into repositories values (?, ?, ?)",
                ("api-repo", "SecPal/api", str(repository_root / "api")),
            )
            connection.execute(
                "insert into worktrees values (?, ?, ?, 'active')",
                ("worktree", "api-repo", str(physical_worktree)),
            )

        renderer = module.load_renderer(REPO_ROOT / "scripts/render-polyscope-container-nginx.py")
        arguments = dict(
            pod="owned-pod", image="localhost/php:8.4", nginx_image="localhost/nginx:test",
            network="preview-network", preview_port=18080,
        )

        def commands():
            routes = renderer.preview_routes(db_path, clone_root, repository_root)
            return module.preview_commands(routes, root, **arguments)

        backends, _ = commands()
        assert backends == [], "active registrations alone must not start PHP"
        admission = physical_worktree / "public" / renderer.API_PREVIEW_ADMISSION_FILENAME
        # An old root marker does not trigger execution under the new runtime.
        (physical_worktree / admission.name).touch()
        assert commands()[0] == []
        admission.touch()

        other_worktree = clone_root / "api-repo/quiet-owl"
        for directory in ("public", "storage"):
            (other_worktree / directory).mkdir(parents=True)
        (other_worktree / "public" / admission.name).touch()
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into worktrees values (?, ?, ?, 'active')",
                ("other", "api-repo", str(other_worktree)),
            )

        backends, gateway = commands()
        assert len(backends) == 2
        for index, (backend, worktree) in enumerate(zip(backends, (physical_worktree, other_worktree)), 1):
            assert "/usr/local/sbin/php-fpm" in backend
            assert f"{worktree}:/app:ro,z" in backend
            assert f"{worktree / 'storage'}:/app/storage:rw,z" in backend
            assert f"{root / 'sockets' / str(index)}:/run/preview-php:rw,z" in backend
            assert backend[backend.index("--network") + 1] == "preview-network"
            assert "--restart=on-failure" in backend
            assert "--sdnotify=ignore" in backend
            assert "--publish" not in backend
            assert f"{worktree / 'public'}:/workspaces/{index}:ro,z" in gateway
            assert not any(str(worktree) in argument for argument in backends[2-index])
        assert "/usr/sbin/nginx" in gateway
        assert "--sdnotify=healthy" in gateway
        assert "127.0.0.1:18080:18080" in gateway and "preview-network" not in gateway
        assert all(":ro,z" in mount for mount in gateway if str(root) in mount)
        for command in [*backends, gateway]:
            assert "--userns=keep-id:uid=1000,gid=1000" in command
            assert "--cap-drop=all" in command and "--read-only" in command
            assert not any(argument.startswith(f"{clone_root}:") for argument in command)
            assert "--security-opt=label=disable" not in command
            assert command[command.index("--") + 1] in {arguments["image"], arguments["nginx_image"]}
        assert module.SAFE_NAME.fullmatch("--privileged") is None

        (physical_worktree / "storage").rmdir()
        try:
            commands()
        except RuntimeError as error:
            assert "writable API runtime directory is unavailable" in str(error)
        else:
            raise AssertionError("missing API storage directory must fail closed")

        admission.unlink()
        assert len(commands()[0]) == 1

        # A newly registered API repository may have no active clone directory yet.
        with sqlite3.connect(db_path) as connection:
            connection.execute("delete from worktrees")
        shutil.rmtree(clone_root / "api-repo")
        assert commands()[0] == []


if __name__ == "__main__":
    main()
