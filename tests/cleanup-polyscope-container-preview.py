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
SCRIPT = REPO_ROOT / "scripts" / "cleanup-polyscope-container-preview.py"


def load_module():
    spec = importlib.util.spec_from_file_location("cleanup_preview", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="polyscope-preview-cleanup.") as temporary:
        root = pathlib.Path(temporary)
        repository_root = root / "repos/SecPal"
        clone_root = root / "clones"
        (repository_root / "api").mkdir(parents=True)
        (repository_root / "api/.env").write_text("DB_CONNECTION=pgsql\n")
        rollout = repository_root / ".github/scripts/polyscope-rollout.py"
        rollout.parent.mkdir(parents=True)
        record = root / "record.json"
        rollout.write_text(
            "NATIVE_SETUP_COMMANDS_KEY = 'native_setup'\n"
            "def cleanup_removed_api_preview_databases(repo_state, repo_specs, clone_root, **kwargs):\n"
            " import json\n"
            f" open({str(record)!r}, 'w').write(json.dumps({{'repo_state': repo_state, 'paths': [str(p) for p in kwargs['registered_api_worktrees']]}}))\n"
            " return ['polyscope__preview__stale']\n"
        )
        worktree = clone_root / "api-repo/calm-otter-a1b2c3d4"
        (worktree / "public").mkdir(parents=True)
        (clone_root / "api-repo/.polyscope-secpal-workspace-aliases.json").write_text(
            json.dumps({"version": 1, "aliases": {"calm-otter": worktree.name}})
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
                "insert into repositories values ('api-repo', 'SecPal/api', ?)",
                (str(repository_root / "api"),),
            )
            connection.execute(
                "insert into worktrees values ('active', 'api-repo', ?, 'active')",
                (str(worktree),),
            )

        cleaned = module.cleanup(db_path, clone_root, repository_root)
        assert cleaned == ["polyscope__preview__stale"]
        recorded = json.loads(record.read_text())
        assert recorded["repo_state"] == {"api": {"id": "api-repo"}}
        assert recorded["paths"] == [str(worktree)]


if __name__ == "__main__":
    main()
