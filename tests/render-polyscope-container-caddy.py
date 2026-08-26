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
SCRIPT = REPO_ROOT / "scripts" / "render-polyscope-container-caddy.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_caddy", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_runtime_error(callback, message: str) -> None:
    try:
        callback()
    except RuntimeError as error:
        assert message in str(error), error
    else:
        raise AssertionError(f"expected RuntimeError containing {message!r}")


def main() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="polyscope-caddy.") as temporary:
        root = pathlib.Path(temporary)
        repository_root = root / "repos/SecPal"
        clone_root = root / "clones"
        for repository_name in ("api", "frontend", "GuardGuide", "guardguide.de"):
            (repository_root / repository_name).mkdir(parents=True)

        worktrees = {
            "api": ("api-repo_1", "calm-otter", "calm-otter-a1b2c3d4", "public"),
            "frontend": ("Frontend_2", "calm-otter", "calm-otter-e5f6a7b8", "dist"),
            "GuardGuide": ("guardguide-3", "patient-fox", "patient-fox-11223344", "public"),
            "guardguide.de": (
                "guardguide_de_4",
                "patient-fox",
                "patient-fox-55667788",
                "dist",
            ),
        }
        for repository_name, (
            repository_id,
            workspace,
            physical_workspace,
            document_root,
        ) in worktrees.items():
            repository_clone_root = clone_root / repository_id
            (repository_clone_root / physical_workspace / document_root).mkdir(parents=True)
            (repository_clone_root / ".polyscope-secpal-workspace-aliases.json").write_text(
                json.dumps({"version": 1, "aliases": {workspace: physical_workspace}})
            )

        db_path = root / "polyscope #1.db"
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "create table repositories (id text primary key, name text not null, path text not null)"
            )
            connection.execute(
                "create table worktrees (id text primary key, repo_id text not null, path text not null, status text not null)"
            )
            for repository_name, (
                repository_id,
                _workspace,
                physical_workspace,
                _document_root,
            ) in worktrees.items():
                connection.execute(
                    "insert into repositories (id, name, path) values (?, ?, ?)",
                    (
                        repository_id,
                        f"SecPal/{repository_name}",
                        str(repository_root / repository_name),
                    ),
                )
                connection.execute(
                    "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'active')",
                    (
                        f"worktree-{repository_id}",
                        repository_id,
                        str(clone_root / repository_id / physical_workspace),
                    ),
                )
            inactive = clone_root / "api-repo_1/inactive-wolf/public"
            inactive.mkdir(parents=True)
            connection.execute(
                "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'inactive')",
                ("inactive", "api-repo_1", str(inactive.parent)),
            )

        rendered = module.render(
            db_path,
            pathlib.Path("/workspaces"),
            clone_root,
            repository_root,
        )
        assert "api-calm-otter.preview.secpal.dev" in rendered
        assert "frontend-calm-otter.preview.secpal.dev" in rendered
        assert "guardguide-patient-fox.preview.secpal.dev" in rendered
        assert "guardguide-de-patient-fox.preview.secpal.dev" in rendered
        assert "inactive-wolf" not in rendered
        assert "{re." not in rendered
        assert "api-calm-otter-a1b2c3d4.preview.secpal.dev" not in rendered
        assert "frontend-calm-otter-e5f6a7b8.preview.secpal.dev" not in rendered
        assert "root * /workspaces/api-repo_1/calm-otter-a1b2c3d4/public" in rendered
        assert "root * /workspaces/Frontend_2/calm-otter-e5f6a7b8/dist" in rendered
        assert "@non_front_controller_php_1 {" in rendered
        assert "not path /index.php" in rendered
        assert 'respond @non_front_controller_php_1 "Not found" 404' in rendered
        assert "rewrite * /index.php" in rendered
        assert "            php\n" in rendered

        output = root / "config" / "Caddyfile"
        module.write_atomic(output, rendered)
        assert output.read_text() == rendered
        assert (output.stat().st_mode & 0o777) == 0o600

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into repositories (id, name, path) values (?, ?, ?)",
                ("duplicate", "SecPal/api", str(repository_root / "api")),
            )
        expect_runtime_error(
            lambda: module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            ),
            "exactly one canonical Polyscope repository",
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute("delete from repositories where id = 'duplicate'")

        alias_registry = clone_root / "api-repo_1/.polyscope-secpal-workspace-aliases.json"
        alias_registry.write_text(json.dumps({"version": 1, "aliases": {}}))
        expect_runtime_error(
            lambda: module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            ),
            "exactly one canonical Polyscope workspace alias",
        )
        alias_registry.write_text(
            json.dumps(
                {
                    "version": 1,
                    "aliases": {
                        "calm-otter": "calm-otter-a1b2c3d4",
                        "other-otter": "calm-otter-a1b2c3d4",
                    },
                }
            )
        )
        expect_runtime_error(
            lambda: module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            ),
            "exactly one canonical Polyscope workspace alias",
        )
        alias_registry.write_text(
            json.dumps(
                {"version": 1, "aliases": {"calm-otter": "calm-otter-a1b2c3d4"}}
            )
        )

        escaping_link = clone_root / "api-repo_1/calm-otter-a1b2c3d4/public/leak"
        escaping_link.symlink_to(pathlib.Path("../.env"))
        expect_runtime_error(
            lambda: module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            ),
            "symbolic link",
        )


if __name__ == "__main__":
    main()
