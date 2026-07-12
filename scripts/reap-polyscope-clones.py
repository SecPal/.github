#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

"""Conservatively remove stale Polyscope clone roots."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any


def parse_duration(value: str) -> int:
    units = {"s": 1, "m": 60, "h": 60 * 60, "d": 24 * 60 * 60}
    if len(value) < 2 or value[-1] not in units or not value[:-1].isdigit():
        raise argparse.ArgumentTypeError("grace period must be a whole number followed by s, m, h, or d")
    seconds = int(value[:-1]) * units[value[-1]]
    if seconds <= 0:
        raise argparse.ArgumentTypeError("grace period must be greater than zero")
    return seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove orphaned Polyscope clone roots after a grace period.")
    parser.add_argument("--polyscope-home", default=str(Path.home() / ".polyscope"))
    parser.add_argument("--clone-root", help="Absolute clone root. Defaults to POLYSCOPE_HOME/clones.")
    parser.add_argument("--grace-period", type=parse_duration, default=7 * 24 * 60 * 60)
    parser.add_argument("--dry-run", action="store_true", help="Report eligible clone roots without removing them.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser.parse_args()


def resolved_absolute(path: Path, description: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{description} must be absolute: {path}")
    return path.resolve()


def protected_clone_root_names(conn: sqlite3.Connection, clone_root: Path) -> set[str]:
    names = {str(row[0]) for row in conn.execute("SELECT id FROM repositories")}
    worktree_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(worktrees)")}
    worktree_query = "SELECT path FROM worktrees"
    if "status" in worktree_columns:
        worktree_query += " WHERE status = 'active'"
    paths = [Path(row[0]).resolve() for row in conn.execute("SELECT path FROM repositories")]
    paths.extend(Path(row[0]).resolve() for row in conn.execute(worktree_query))
    for path in paths:
        try:
            relative = path.relative_to(clone_root)
        except ValueError:
            continue
        if relative.parts:
            names.add(relative.parts[0])
    return names


def load_protected_clone_root_names(db_path: Path, clone_root: Path) -> set[str]:
    if not db_path.is_file():
        raise ValueError(f"Polyscope DB not found at {db_path}")
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            return protected_clone_root_names(conn, clone_root)
    except sqlite3.Error as exc:
        raise ValueError(f"unable to read Polyscope DB: {exc}") from exc



def quarantine_if_still_orphan(
    db_path: Path, clone_root: Path, candidate: Path, cutoff: float
) -> Path | None:
    """Atomically detach a candidate while preventing database registrations."""
    quarantine = clone_root / f".reaper-trash-{os.getpid()}-{candidate.name}"
    try:
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if candidate.name in protected_clone_root_names(conn, clone_root):
                return None
            if candidate.stat().st_mtime > cutoff or has_lock(candidate) or has_active_process(candidate):
                return None
            candidate.rename(quarantine)
        return quarantine
    except (OSError, sqlite3.Error):
        return None


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def has_lock(root: Path) -> bool:
    try:
        # Dependency manifests such as yarn.lock are durable source files, not
        # evidence of an in-progress operation. Git's lock files live inside
        # a worktree's .git directory and protect exactly the metadata that a
        # clone-root deletion must not race.
        metadata_paths = [root / ".git"]
        metadata_paths.extend(
            child / ".git" for child in root.iterdir() if child.is_dir() and not child.is_symlink()
        )
        for metadata in metadata_paths:
            if metadata.is_file():
                contents = metadata.read_text(errors="replace").strip()
                if contents.startswith("gitdir: "):
                    git_dir = Path(contents.removeprefix("gitdir: "))
                    metadata = (metadata.parent / git_dir).resolve() if not git_dir.is_absolute() else git_dir
            if metadata.is_dir() and any(path.is_file() for path in metadata.rglob("*.lock")):
                return True
        return False
    except OSError:
        # An unreadable tree must never be a deletion candidate.
        return True


def has_active_process(root: Path) -> bool:
    proc = Path("/proc")
    if not proc.is_dir():
        # Without portable process inspection, skip rather than risk deleting a live tree.
        return True
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        for location in (entry / "cwd", entry / "exe"):
            try:
                if is_within(Path(os.readlink(location)), root):
                    return True
            except OSError:
                # The process may exit or hide this link while it is scanned.
                continue
        fd_dir = entry / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd).removesuffix(" (deleted)")
                if target.startswith("/") and is_within(Path(target), root):
                    return True
            except OSError:
                # File descriptors can close between directory listing and lookup.
                continue
    return False


def allocated_bytes(root: Path) -> int:
    total = 0
    try:
        for path in [root, *root.rglob("*")]:
            total += path.lstat().st_blocks * 512
    except OSError:
        return 0
    return total


def reap(args: argparse.Namespace) -> dict[str, Any]:
    home = resolved_absolute(Path(args.polyscope_home), "Polyscope home")
    clone_root = resolved_absolute(Path(args.clone_root) if args.clone_root else home / "clones", "clone root")
    db_path = home / "polyscope.db"
    allowlist = load_protected_clone_root_names(db_path, clone_root)
    report: dict[str, Any] = {
        "removed": [],
        "would_remove": [],
        "reclaimed_bytes": 0,
        "skipped": {"active": [], "grace_period": [], "lock": [], "process": [], "unsafe": []},
    }
    if not clone_root.is_dir():
        return report

    cutoff = time.time() - args.grace_period
    for candidate in sorted(clone_root.iterdir()):
        # Only immediate, real directories under the configured clone root are eligible.
        if candidate.is_symlink() or not candidate.is_dir() or not is_within(candidate.resolve(), clone_root):
            report["skipped"]["unsafe"].append(str(candidate))
            continue
        if candidate.name in allowlist:
            report["skipped"]["active"].append(str(candidate))
            continue
        try:
            if candidate.stat().st_mtime > cutoff:
                report["skipped"]["grace_period"].append(str(candidate))
                continue
        except OSError:
            report["skipped"]["unsafe"].append(str(candidate))
            continue
        if has_lock(candidate):
            report["skipped"]["lock"].append(str(candidate))
            continue
        if has_active_process(candidate):
            report["skipped"]["process"].append(str(candidate))
            continue
        size = allocated_bytes(candidate)
        if args.dry_run:
            report["would_remove"].append(str(candidate))
            report["reclaimed_bytes"] += size
            continue
        quarantined = quarantine_if_still_orphan(db_path, clone_root, candidate, cutoff)
        if quarantined is None:
            report["skipped"]["unsafe"].append(str(candidate))
            continue
        try:
            shutil.rmtree(quarantined)
        except OSError:
            report["skipped"]["unsafe"].append(str(candidate))
            continue
        report["removed"].append(str(candidate))
        report["reclaimed_bytes"] += size
    return report


def main() -> int:
    args = parse_args()
    try:
        report = reap(args)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        action = "Would reclaim" if args.dry_run else "Reclaimed"
        print(f"{action} {report['reclaimed_bytes']} bytes from {len(report['would_remove']) or len(report['removed'])} clone roots.")
        for reason, paths in report["skipped"].items():
            for path in paths:
                print(f"Skipped ({reason}): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
