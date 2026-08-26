#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import pathlib
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


def main() -> None:
    module = load_module()
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

        caddyfile = root / "Caddyfile"
        caddyfile.write_text(":18080 {}\n")
        command = module.build_command(
            renderer_path=REPO_ROOT / "scripts/render-polyscope-container-caddy.py",
            db_path=db_path,
            clone_root=clone_root,
            repository_root=repository_root,
            caddyfile=caddyfile,
            image="localhost/preview:latest",
            network="preview-network",
            preview_port=18080,
        )
        assert f"{clone_root}:/workspaces:ro" in command
        assert f"{clone_root}:{clone_root}:ro" in command
        storage_mount = f"{physical_worktree / 'storage'}:/workspaces/api-repo/{physical_worktree.name}/storage:rw"
        assert storage_mount in command
        assert f"{physical_worktree}:/workspaces/api-repo/{physical_worktree.name}:rw" not in command
        assert not any(".env" in argument for argument in command)
        assert command[command.index("localhost/preview:latest") - 1] == "--"
        assert module.SAFE_NAME.fullmatch("--privileged") is None

        (physical_worktree / "storage").rmdir()
        try:
            module.build_command(
                renderer_path=REPO_ROOT / "scripts/render-polyscope-container-caddy.py",
                db_path=db_path,
                clone_root=clone_root,
                repository_root=repository_root,
                caddyfile=caddyfile,
                image="localhost/preview:latest",
                network="preview-network",
                preview_port=18080,
            )
        except RuntimeError as error:
            assert "writable API runtime directory is unavailable" in str(error)
        else:
            raise AssertionError("missing API storage directory must fail closed")


if __name__ == "__main__":
    main()
