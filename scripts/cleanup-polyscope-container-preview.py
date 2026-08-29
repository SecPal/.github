#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Drop orphaned API preview storage through the canonical rollout contract."""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sqlite3
import sys


def load_rollout(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("secpal_polyscope_rollout", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load canonical Polyscope rollout: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_existing(path: pathlib.Path) -> pathlib.Path | None:
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def cleanup(
    db_path: pathlib.Path,
    clone_root: pathlib.Path,
    repository_root: pathlib.Path,
) -> list[str]:
    api_source = (repository_root / "api").resolve(strict=True)
    rollout = load_rollout(
        (repository_root / ".github/scripts/polyscope-rollout.py").resolve(strict=True)
    )
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        repository_rows = connection.execute(
            "select id, path from repositories where name = 'SecPal/api'"
        ).fetchall()
        canonical_ids = [
            str(repository_id)
            for repository_id, source_path in repository_rows
            if pathlib.Path(str(source_path)).is_absolute()
            and resolve_existing(pathlib.Path(str(source_path))) == api_source
        ]
        if len(canonical_ids) != 1:
            raise RuntimeError(
                "expected exactly one canonical SecPal/api repository, "
                f"found {len(canonical_ids)}"
            )
        api_repository_id = canonical_ids[0]
        registered_worktrees = [
            pathlib.Path(str(row[0]))
            for row in connection.execute(
                "select path from worktrees where repo_id = ? and status = 'active' order by path",
                (api_repository_id,),
            )
        ]

    return rollout.cleanup_removed_api_preview_databases(
        {"api": {"id": api_repository_id}},
        {
            "api": {
                "path": api_source,
                rollout.NATIVE_SETUP_COMMANDS_KEY: [],
            }
        },
        clone_root,
        db_path=db_path,
        validated_instruction_roots=set(),
        registered_api_worktrees=registered_worktrees,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True, type=pathlib.Path)
    parser.add_argument("--clone-root", required=True, type=pathlib.Path)
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    args = parser.parse_args()
    for path in (args.db_path, args.clone_root, args.repository_root):
        if not path.is_absolute():
            parser.error(f"path must be absolute: {path}")
    for cleaned_target in cleanup(args.db_path, args.clone_root, args.repository_root):
        print(f"Removed orphaned Polyscope preview storage {cleaned_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
