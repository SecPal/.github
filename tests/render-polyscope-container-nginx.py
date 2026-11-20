#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import tempfile
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "render-polyscope-container-nginx.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_nginx", SCRIPT)
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
    with tempfile.TemporaryDirectory(prefix="polyscope-nginx.") as temporary:
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
        (api_worktree / "storage").mkdir()
        unready = module.render(db_path, pathlib.Path("/workspaces"), clone_root, repository_root)
        assert "api-calm-otter.preview.secpal.dev" not in unready
        assert "frontend-calm-otter.preview.secpal.dev" in unready
        (api_worktree / "public" / module.API_PREVIEW_ADMISSION_FILENAME).touch()
        assert module.api_preview_is_admitted(api_worktree)
        (api_worktree / "public" / module.API_PREVIEW_ADMISSION_FILENAME).unlink()
        assert not module.api_preview_is_admitted(api_worktree)
        (api_worktree / "public" / module.API_PREVIEW_ADMISSION_FILENAME).touch()

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
        for prefix, physical in (
            ("api", "calm-otter-a1b2c3d4"),
            ("frontend", "calm-otter-e5f6a7b8"),
            ("secpal-app", "calm-otter-12345678"),
        ):
            assert f"server_name {prefix}-{physical}.preview.secpal.dev;" in rendered
            assert f"return 308 https://{prefix}-calm-otter.preview.secpal.dev$request_uri;" in rendered
        assert "root /workspaces/1;" in rendered
        assert "root /workspaces/2;" in rendered
        assert r"location ~* \.php(?:/|$) { return 404; }" in rendered
        assert "if (!-f $document_root/.polyscope-secpal-container-ready) { return 503; }" in rendered
        assert "location = /index.php {" in rendered
        assert "fastcgi_param SCRIPT_FILENAME /app/public/index.php;" in rendered
        assert "fastcgi_pass unix:/run/preview-sockets/1/api.sock;" in rendered
        assert "access_log off;" in rendered

        # Rebuilding a document root atomically requires new container mounts.
        frontend_root = clone_root / worktrees["frontend"][0] / worktrees["frontend"][2] / "dist"
        frontend_root.rename(frontend_root.with_name("dist-old"))
        frontend_root.mkdir()
        replaced = module.render(db_path, pathlib.Path("/workspaces"), clone_root, repository_root)
        assert replaced != rendered
        assert "frontend-calm-otter.preview.secpal.dev" in replaced

        # A physical-name redirect must never shadow another active
        # workspace's canonical hostname.
        conflicting = clone_root / "api-repo_1/other-otter-11223344"
        (conflicting / "public").mkdir(parents=True)
        (conflicting / "public" / module.API_PREVIEW_ADMISSION_FILENAME).touch()
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

        output = root / "config" / "nginx.conf"
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
        (legacy_path / "public" / module.API_PREVIEW_ADMISSION_FILENAME).touch()
        (legacy_path / "storage").mkdir()
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'active')",
                ("legacy-api", "api-repo_1", str(legacy_path)),
            )
        legacy_rendered = module.render(
            db_path, pathlib.Path("/workspaces"), clone_root, repository_root
        )
        assert "api-legacy-otter.preview.secpal.dev" in legacy_rendered
        assert "return 308 https://api-legacy-otter.preview.secpal.dev" not in legacy_rendered

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

        # Rollout retains the physical name when the short slug collides.
        spec = importlib.util.spec_from_file_location(
            "collision_rollout", REPO_ROOT / "scripts/polyscope-rollout.py"
        )
        rollout = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rollout)
        collision = clone_root / "api-repo_1/calm-otter-deadbeef"
        (collision / "public").mkdir(parents=True)
        (collision.parent / "calm-otter").symlink_to(api_worktree.name)
        (collision / "public" / module.API_PREVIEW_ADMISSION_FILENAME).touch()
        (collision / "storage").mkdir()
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'active')",
                ("collision-api", "api-repo_1", str(collision)),
            )
        assert rollout.resolve_current_workspace_name(collision, db_path=db_path) == collision.name
        rollout.ensure_workspace_alias(collision, db_path=db_path)
        registry_before_collision = alias_registry.read_bytes()
        def render_collision():
            return module.render(
                db_path, pathlib.Path("/workspaces"), clone_root, repository_root
            )
        expect_runtime_error(render_collision, "canonical Polyscope workspace alias")
        marker = collision / rollout.PROVISION_MARKER_FILENAME
        for invalid in ({"workspace": "calm-otter"}, {"workspace": "../escape"}, []):
            marker.write_text(json.dumps(invalid))
            expect_runtime_error(render_collision, "canonical Polyscope workspace alias")
        marker.write_text("{")
        expect_runtime_error(render_collision, "canonical Polyscope workspace alias")
        marker.unlink()
        foreign_marker = root / "foreign-provision-marker.json"
        foreign_marker.write_text(json.dumps({"workspace": collision.name}))
        marker.symlink_to(foreign_marker)
        expect_runtime_error(render_collision, "canonical Polyscope workspace alias")
        marker.unlink()
        rollout.write_provision_marker(marker, {
            "repo": "api", "workspace": collision.name, "setup_hash": "a" * 64,
        })
        # Replacement at the actual open boundary must not turn a checked
        # regular marker into evidence read through a symlink.
        original_path_open = pathlib.Path.open
        original_os_open = module.os.open
        swapped = []
        def replace_marker():
            if not marker.is_symlink():
                marker.unlink()
                marker.symlink_to(foreign_marker)
                swapped.append(True)
        def racing_path_open(path, *args, **kwargs):
            if path == marker:
                replace_marker()
            return original_path_open(path, *args, **kwargs)
        def racing_os_open(path, *args, **kwargs):
            if pathlib.Path(path) == marker:
                replace_marker()
            return original_os_open(path, *args, **kwargs)
        with mock.patch.object(pathlib.Path, "open", racing_path_open), mock.patch.object(
            module.os, "open", racing_os_open
        ):
            assert not module.has_provisioned_physical_name(collision)
        assert swapped == [True]
        marker.unlink()
        module.os.mkfifo(marker)
        assert not module.has_provisioned_physical_name(collision)
        marker.unlink()
        rollout.write_provision_marker(marker, {
            "repo": "api", "workspace": collision.name, "setup_hash": "a" * 64,
        })
        collision_rendered = render_collision()
        assert f"api-{collision.name}.preview.secpal.dev" in collision_rendered
        assert "api-calm-otter.preview.secpal.dev" in collision_rendered
        assert f"return 308 https://api-{collision.name}.preview.secpal.dev" not in collision_rendered
        assert alias_registry.read_bytes() == registry_before_collision
        (collision / "public" / module.API_PREVIEW_ADMISSION_FILENAME).unlink()
        assert f"api-{collision.name}.preview.secpal.dev" not in render_collision()
        with sqlite3.connect(db_path) as connection:
            connection.execute("delete from worktrees where id = 'collision-api'")

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
