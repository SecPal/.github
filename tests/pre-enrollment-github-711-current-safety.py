# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main safety assertions for the immutable GitHub #711 tree."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


INVARIANTS = [
    "current_tree_exact",
    "historical_bytes_unavailable",
    "registered_validation",
    "source_history",
]
SCRIPT = Path("scripts/secpal-trivy-repository-scan.py")
ACTION = Path(".github/actions/trivy-repository-scan/action.yml")
POLICY = Path("policies/trivy-repository-scan-v1.json")
SCHEMA = Path("docs/schemas/secpal-trivy-repository-scan-v1.schema.json")
SCANNER_TESTS = Path("tests/secpal-trivy-repository-scan-unit.py")


def main(arguments: list[str]) -> int:
    required = (SCRIPT, ACTION, POLICY, SCHEMA, SCANNER_TESTS)
    if arguments or any(not path.is_file() for path in required):
        print(json.dumps(["registered_validation"]))
        return 1
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                SCANNER_TESTS.as_posix(),
            ],
            check=False,
            cwd=Path.cwd(),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        print(json.dumps(["registered_validation"]))
        return 1
    if completed.returncode != 0:
        print(json.dumps(["registered_validation"]))
        return 1
    print(json.dumps(INVARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
