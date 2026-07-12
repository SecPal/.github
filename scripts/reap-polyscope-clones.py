#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

"""Conservatively remove stale Polyscope clone roots and worktrees."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import stat
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


def active_worktree_paths(conn: sqlite3.Connection, clone_root: Path) -> set[Path]:
    """Return active registered worktrees physically contained by clone_root."""
    worktree_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(worktrees)")}
    worktree_query = "SELECT path FROM worktrees"
    if "status" in worktree_columns:
        worktree_query += " WHERE status = 'active'"
    paths = set()
    for row in conn.execute(worktree_query):
        path = Path(row[0]).resolve()
        if is_within(path, clone_root):
            paths.add(path)
    return paths


def protected_clone_root_names(conn: sqlite3.Connection, clone_root: Path) -> set[str]:
    names = {str(row[0]) for row in conn.execute("SELECT id FROM repositories")}
    paths = [Path(row[0]).resolve() for row in conn.execute("SELECT path FROM repositories")]
    paths.extend(active_worktree_paths(conn, clone_root))
    for path in paths:
        try:
            relative = path.relative_to(clone_root)
        except ValueError:
            continue
        if relative.parts:
            names.add(relative.parts[0])
    return names


def load_protected_paths(db_path: Path, clone_root: Path) -> tuple[set[str], set[Path]]:
    if not db_path.is_file():
        raise ValueError(f"Polyscope DB not found at {db_path}")
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            return protected_clone_root_names(conn, clone_root), active_worktree_paths(conn, clone_root)
    except sqlite3.Error as exc:
        raise ValueError(f"unable to read Polyscope DB: {exc}") from exc



def is_registered_candidate(
    conn: sqlite3.Connection, clone_root: Path, candidate: Path, is_worktree: bool
) -> bool:
    if is_worktree:
        return protects_active_worktree(candidate, active_worktree_paths(conn, clone_root))
    return candidate.name in protected_clone_root_names(conn, clone_root)


def quarantine_if_still_orphan(
    db_path: Path, clone_root: Path, candidate: Path, cutoff: float, is_worktree: bool
) -> Path | None:
    """Atomically detach a candidate while preventing database registrations."""
    parent_name = candidate.parent.name if is_worktree else "root"
    quarantine = clone_root / f".reaper-trash-{os.getpid()}-{parent_name}-{candidate.name}"
    parent_fd = -1
    clone_fd = -1
    try:
        clone_fd = os.open(clone_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if is_worktree:
            if candidate.parent.parent != clone_root:
                return None
            parent_fd = os.open(candidate.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        else:
            parent_fd = os.dup(clone_fd)
        pinned_candidate = Path(f"/proc/self/fd/{parent_fd}") / candidate.name
        candidate_stat = os.stat(candidate.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(candidate_stat.st_mode) or pinned_candidate.is_symlink():
            return None
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if is_registered_candidate(conn, clone_root, candidate, is_worktree):
                return None
            newest_mtime = newest_tree_mtime(pinned_candidate)
            if (
                newest_mtime is None
                or newest_mtime > cutoff
                or has_lock(pinned_candidate)
                or has_active_process(pinned_candidate.resolve())
            ):
                return None
            os.rename(candidate.name, quarantine.name, src_dir_fd=parent_fd, dst_dir_fd=clone_fd)
        return quarantine
    except (AttributeError, OSError, sqlite3.Error):
        return None
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
        if clone_fd >= 0:
            os.close(clone_fd)


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


def newest_tree_mtime(root: Path) -> float | None:
    try:
        return max(path.lstat().st_mtime for path in [root, *root.rglob("*")])
    except OSError:
        return None


def protects_active_worktree(candidate: Path, active_worktrees: set[Path]) -> bool:
    """Whether candidate is, or contains, an active registered worktree."""
    candidate_path = candidate.resolve()
    return any(is_within(worktree, candidate_path) for worktree in active_worktrees)


def candidates(
    clone_root: Path, protected_roots: set[str], protected_worktrees: set[Path]
) -> list[tuple[Path, bool]]:
    """Return root and safe-to-inspect child worktree candidates in path order."""
    result: list[tuple[Path, bool]] = []
    for root in clone_root.iterdir():
        result.append((root, False))
        try:
            root_path = root.resolve()
            # Only registered clone roots can contain individually managed
            # worktrees. A registered worktree at the root has arbitrary
            # source subdirectories, never worktree candidates.
            if (
                root.name not in protected_roots
                or root.is_symlink()
                or not root.is_dir()
                or not is_within(root_path, clone_root)
                or root_path in protected_worktrees
            ):
                continue
            result.extend((child, True) for child in root.iterdir())
        except OSError:
            continue
    return sorted(result, key=lambda item: str(item[0]))


def reap(args: argparse.Namespace) -> dict[str, Any]:
    home = resolved_absolute(Path(args.polyscope_home), "Polyscope home")
    clone_root = resolved_absolute(Path(args.clone_root) if args.clone_root else home / "clones", "clone root")
    db_path = home / "polyscope.db"
    protected_roots, protected_worktrees = load_protected_paths(db_path, clone_root)
    report: dict[str, Any] = {
        "removed": [],
        "would_remove": [],
        "reclaimed_bytes": 0,
        "skipped": {"active": [], "grace_period": [], "lock": [], "process": [], "unsafe": []},
    }
    if not clone_root.is_dir():
        return report

    cutoff = time.time() - args.grace_period
    for candidate, is_worktree in candidates(clone_root, protected_roots, protected_worktrees):
        parent = candidate.parent.resolve()
        expected_parent = parent if is_worktree else clone_root
        # Only real clone roots and immediate worktree children are eligible.
        if (
            (is_worktree and candidate.name.startswith("."))
            or candidate.is_symlink()
            or not candidate.is_dir()
            or not is_within(candidate.resolve(), expected_parent)
        ):
            report["skipped"]["unsafe"].append(str(candidate))
            continue
        protected = (
            protects_active_worktree(candidate, protected_worktrees)
            if is_worktree
            else candidate.name in protected_roots
        )
        if protected:
            report["skipped"]["active"].append(str(candidate))
            continue
        try:
            newest_mtime = newest_tree_mtime(candidate)
            if newest_mtime is None:
                report["skipped"]["unsafe"].append(str(candidate))
                continue
            if newest_mtime > cutoff:
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
        quarantined = quarantine_if_still_orphan(db_path, clone_root, candidate, cutoff, is_worktree)
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
        print(f"{action} {report['reclaimed_bytes']} bytes from {len(report['would_remove']) or len(report['removed'])} Polyscope directories.")
        for reason, paths in report["skipped"].items():
            for path in paths:
                print(f"Skipped ({reason}): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
