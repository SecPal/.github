# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main validation of the exact parked public-site Node 26 tree."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


INVARIANTS = [
    "current_tree_exact",
    "historical_bytes_unavailable",
    "registered_validation",
    "source_history",
]
COMMANDS = (
    ("npm", "ci", "--no-audit", "--no-fund"),
    ("npm", "run", "format:check"),
    ("npm", "run", "check"),
    ("npm", "run", "lint"),
    ("npm", "run", "test"),
    ("npm", "run", "build"),
)


def main(arguments: list[str]) -> int:
    root = Path.cwd()
    required = (
        root / ".nvmrc",
        root / ".npmrc",
        root / "package.json",
        root / "package-lock.json",
        root / "CHANGELOG.md",
        root / "tests/workflow-action-pins.test.mjs",
    )
    if arguments or any(not path.is_file() for path in required):
        print(json.dumps(["registered_validation"]))
        return 1
    try:
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        if (
            (root / ".nvmrc").read_text(encoding="utf-8").strip() != "26"
            or package.get("engines", {}).get("node") != "^26.10.0"
            or "engine-strict=true" not in (root / ".npmrc").read_text(encoding="utf-8")
        ):
            raise ValueError("Node toolchain contract changed")
        with tempfile.TemporaryDirectory(prefix="secpal-app-352-validation-") as directory:
            candidate = Path(directory) / "candidate"
            shutil.copytree(root, candidate, ignore=shutil.ignore_patterns(".git"))
            for git_command in (("git", "init", "--quiet"), ("git", "add", "-A")):
                if subprocess.run(
                    git_command, cwd=candidate, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=15, check=False,
                ).returncode:
                    raise ValueError("isolated source index is unavailable")
            for command in COMMANDS:
                result = subprocess.run(
                    command,
                    cwd=candidate,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=90,
                    check=False,
                )
                if result.returncode:
                    raise ValueError("registered Node validation failed")
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps(["registered_validation"]))
        return 1
    print(json.dumps(INVARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
