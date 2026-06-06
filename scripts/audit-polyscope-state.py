#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit local Polyscope state for drift and stale data.")
    parser.add_argument(
        "--polyscope-home",
        default=str(Path.home() / ".polyscope"),
        help="Path to the Polyscope home directory. Defaults to ~/.polyscope.",
    )
    parser.add_argument(
        "--backup-retention",
        type=int,
        default=8,
        help="How many newest polyscope.db backups to keep before older ones are reported as excess.",
    )
    parser.add_argument("--json", action="store_true", help="Print findings as JSON.")
    return parser.parse_args()


def ensure_dependencies(polyscope_home: Path, backup_retention: int) -> Path:
    if backup_retention < 0:
        raise SystemExit("--backup-retention must be >= 0")

    if shutil.which("git") is None:
        raise SystemExit("git is required to audit Polyscope worktrees")

    db_path = polyscope_home / "polyscope.db"
    if not db_path.exists():
        raise SystemExit(f"Polyscope DB not found at {db_path}")
    return db_path


def is_git_worktree(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def resolve_git_dir(worktree_path: Path) -> Path:
    # Linked worktrees store .git as a file pointing at <main>/.git/worktrees/<name>,
    # which is where per-worktree info/exclude lives; resolve it via git so the
    # audit reads the correct location instead of <worktree>/.git/info/exclude.
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "rev-parse", "--absolute-git-dir"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return worktree_path / ".git"
    return Path(result.stdout.strip())


def has_exclude_entry(exclude_path: Path, entry: str) -> bool:
    if not exclude_path.exists():
        return False
    return any(line.strip() == entry for line in exclude_path.read_text().splitlines())


def load_state(db_path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    repositories = {
        repo_id: {"name": name, "path": path}
        for repo_id, name, path in cur.execute("SELECT id, name, path FROM repositories ORDER BY name")
    }
    worktrees = [
        {
            "repo_id": repo_id,
            "branch": branch,
            "path": path,
            "status": status,
        }
        for repo_id, branch, path, status in cur.execute(
            "SELECT repo_id, branch, path, status FROM worktrees ORDER BY repo_id, path"
        )
    ]
    conn.close()
    return repositories, worktrees


def audit_state(polyscope_home: Path, backup_retention: int) -> dict[str, list[Any]]:
    db_path = ensure_dependencies(polyscope_home, backup_retention)
    repositories, worktrees = load_state(db_path)

    clone_root = polyscope_home / "clones"
    repo_ids = set(repositories)
    # Audit is read-only: if clones/ has not been provisioned yet, treat it as empty
    # rather than creating it (would mutate user state on a fresh Polyscope home).
    clone_roots = sorted(path for path in clone_root.iterdir() if path.is_dir()) if clone_root.is_dir() else []
    registered_worktree_paths = {Path(entry["path"]).resolve(): entry for entry in worktrees}

    findings: dict[str, list[Any]] = {
        "orphan_clone_roots": [],
        "repos_missing_clone_roots": [],
        "invalid_clone_worktrees": [],
        "unregistered_git_worktrees": [],
        "missing_registered_worktrees": [],
        "worktrees_missing_repositories": [],
        "missing_clone_local_configs": [],
        "worktree_config_mismatches": [],
        "missing_worktree_excludes": [],
        "excess_db_backups": [],
    }

    for repo_id, repo in sorted(repositories.items(), key=lambda item: item[1]["name"]):
        expected_clone_root = clone_root / repo_id
        if not expected_clone_root.is_dir():
            findings["repos_missing_clone_roots"].append(
                {
                    "repo_id": repo_id,
                    "repo_name": repo["name"],
                    "repo_path": repo["path"],
                    "clone_root": str(expected_clone_root),
                }
            )

    for root in clone_roots:
        if root.name not in repo_ids:
            findings["orphan_clone_roots"].append(str(root))

        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            child_resolved = child.resolve()
            if is_git_worktree(child):
                if child_resolved not in registered_worktree_paths:
                    findings["unregistered_git_worktrees"].append(str(child))
            else:
                findings["invalid_clone_worktrees"].append(str(child))

    for worktree in worktrees:
        worktree_path = Path(worktree["path"])
        if not worktree_path.exists():
            findings["missing_registered_worktrees"].append(worktree)
            continue

        repo = repositories.get(worktree["repo_id"])
        if repo is None:
            findings["worktrees_missing_repositories"].append(worktree)
            continue

        repo_root = Path(repo["path"])
        repo_config = repo_root / "polyscope.local.json"
        worktree_config = worktree_path / "polyscope.local.json"
        if repo_config.exists():
            if not worktree_config.exists():
                findings["missing_clone_local_configs"].append(str(worktree_path))
            elif repo_config.read_text() != worktree_config.read_text():
                findings["worktree_config_mismatches"].append(str(worktree_path))

            exclude_path = resolve_git_dir(worktree_path) / "info" / "exclude"
            if not has_exclude_entry(exclude_path, "polyscope.local.json"):
                findings["missing_worktree_excludes"].append(str(worktree_path))

    backups = sorted(polyscope_home.glob("polyscope.db.backup-*"))
    if backup_retention == 0:
        findings["excess_db_backups"] = [str(path) for path in backups]
    elif backup_retention < len(backups):
        findings["excess_db_backups"] = [str(path) for path in backups[:-backup_retention]]

    return findings


def print_human(findings: dict[str, list[Any]]) -> None:
    labels = {
        "orphan_clone_roots": "Orphan clone roots",
        "repos_missing_clone_roots": "Repositories missing clone roots",
        "invalid_clone_worktrees": "Invalid clone worktrees",
        "unregistered_git_worktrees": "Unregistered git worktrees",
        "missing_registered_worktrees": "Missing registered worktrees",
        "worktrees_missing_repositories": "Worktrees missing repositories",
        "missing_clone_local_configs": "Missing clone-local configs",
        "worktree_config_mismatches": "Clone-local config mismatches",
        "missing_worktree_excludes": "Missing worktree exclude entries",
        "excess_db_backups": "Excess DB backups",
    }
    any_findings = False
    for key, label in labels.items():
        values = findings[key]
        if not values:
            continue
        any_findings = True
        print(f"{label}:")
        for value in values:
            if isinstance(value, dict):
                print(f"  - {json.dumps(value, sort_keys=True)}")
            else:
                print(f"  - {value}")
    if not any_findings:
        print("Polyscope state audit passed with no findings.")


def main() -> int:
    args = parse_args()
    try:
        findings = audit_state(Path(args.polyscope_home), args.backup_retention)
    except SystemExit as exc:
        message = str(exc)
        if message:
            print(message, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(findings, indent=2, sort_keys=True))
    else:
        print_human(findings)

    return 1 if any(findings.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
