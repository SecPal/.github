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
        for repository_name in ("api", "frontend", "secpal.app", "GuardGuide", "guardguide.de"):
            (repository_root / repository_name).mkdir(parents=True)

        # Retained retired registrations prove historical worktrees cannot create routes.
        worktrees = {
            "secpal.app": ("website-5", "calm-otter", "calm-otter-12345678", "dist"),
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

        api_worktree = clone_root / "api-repo_1/calm-otter-a1b2c3d4"
        unready = module.render(db_path, pathlib.Path("/workspaces"), clone_root, repository_root)
        assert "api-calm-otter.preview.secpal.dev" not in unready
        assert "frontend-calm-otter.preview.secpal.dev" in unready
        module.admit_api_preview(api_worktree)
        assert module.api_preview_is_admitted(api_worktree)
        module.withdraw_api_preview(api_worktree)
        assert not module.api_preview_is_admitted(api_worktree)
        module.admit_api_preview(api_worktree)

        rendered = module.render(
            db_path,
            pathlib.Path("/workspaces"),
            clone_root,
            repository_root,
        )
        assert "api-calm-otter.preview.secpal.dev" in rendered
        assert "frontend-calm-otter.preview.secpal.dev" in rendered
        assert "guardguide-patient-fox.preview.secpal.dev" not in rendered
        assert "guardguide-de-patient-fox.preview.secpal.dev" not in rendered
        assert "secpal-app-calm-otter.preview.secpal.dev" in rendered
        assert "inactive-wolf" not in rendered
        assert "{re." not in rendered
        # Native Polyscope links use physical clone names. Redirect those
        # exact active aliases to the canonical host, preserving path/query.
        for index, prefix, physical in (
            (1, "api", "calm-otter-a1b2c3d4"),
            (2, "frontend", "calm-otter-e5f6a7b8"),
            (3, "secpal-app", "calm-otter-12345678"),
        ):
            redirect = (
                f"    @preview_redirect_{index} host {prefix}-{physical}.preview.secpal.dev\n"
                f"    handle @preview_redirect_{index} {{\n"
                f"        redir https://{prefix}-calm-otter.preview.secpal.dev{{uri}} 308\n"
                "    }"
            )
            assert redirect in rendered, redirect
            assert rendered.index(redirect) < rendered.index(f"    @preview_{index} host")
            assert f"    @preview_{index} host {prefix}-{physical}.preview.secpal.dev" not in rendered
        assert "root * /workspaces/api-repo_1/calm-otter-a1b2c3d4/public" in rendered
        assert "root * /workspaces/Frontend_2/calm-otter-e5f6a7b8/dist" in rendered
        assert "@non_front_controller_php_1 {" in rendered
        assert "not path /index.php" in rendered
        assert 'respond @non_front_controller_php_1 "Not found" 404' in rendered
        assert "try_files .polyscope-secpal-container-ready" in rendered
        assert 'respond @api_not_ready_1 "Preview not ready" 503' in rendered
        assert rendered.index("respond @api_not_ready_1") < rendered.index("file_server @static_file_1")
        assert "rewrite * /index.php" in rendered
        assert "            php\n" in rendered

        # A physical-name redirect must never shadow another active
        # workspace's canonical hostname.
        conflicting = clone_root / "api-repo_1/other-otter-11223344"
        (conflicting / "public").mkdir(parents=True)
        module.admit_api_preview(conflicting)
        registry_path = clone_root / "api-repo_1/.polyscope-secpal-workspace-aliases.json"
        registry_before = registry_path.read_text()
        registry_path.write_text(json.dumps({
            "version": 1,
            "aliases": {
                "calm-otter": "calm-otter-a1b2c3d4",
                "calm-otter-a1b2c3d4": conflicting.name,
            },
        }))
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'active')",
                ("conflicting-api", "api-repo_1", str(conflicting)),
            )
        expect_runtime_error(
            lambda: module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            ),
            "physical preview hostname conflicts with a canonical workspace",
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute("delete from worktrees where id = 'conflicting-api'")
        registry_path.write_text(registry_before)

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

        legacy_path = clone_root / "api-repo_1/legacy-otter"
        (legacy_path / "public").mkdir(parents=True)
        module.admit_api_preview(legacy_path)
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'active')",
                ("legacy-api", "api-repo_1", str(legacy_path)),
            )
        legacy_rendered = module.render(
            db_path, pathlib.Path("/workspaces"), clone_root, repository_root
        )
        assert "api-legacy-otter.preview.secpal.dev" in legacy_rendered
        assert "root * /workspaces/api-repo_1/legacy-otter/public" in legacy_rendered
        assert "redir https://api-legacy-otter.preview.secpal.dev" not in legacy_rendered

        alias_registry.unlink()
        expect_runtime_error(
            lambda: module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            ),
            "canonical Polyscope workspace alias",
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
