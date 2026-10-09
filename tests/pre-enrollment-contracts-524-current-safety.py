# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main assertions for the immutable contracts #524 correction."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


INVARIANTS = [
    "current_tree_exact", "historical_bytes_unavailable",
    "registered_validation", "source_history",
]
GUARD = Path("scripts/check-node-toolchain.mjs")


def _run(command: list[str], *, cwd: Path, timeout: int = 10):
    return subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          timeout=timeout, check=False)


def _probe_guard(root: Path) -> bool:
    """Assert selector failures and reject nonregular files before opening them."""
    with tempfile.TemporaryDirectory(prefix="secpal-contracts-guard-") as directory:
        fixture = Path(directory)
        workflows = fixture / ".github/workflows"
        workflows.mkdir(parents=True)
        (fixture / "scripts").mkdir()
        shutil.copyfile(root / GUARD, fixture / GUARD)
        (fixture / "node_modules").symlink_to(root / "node_modules", target_is_directory=True)
        (fixture / ".nvmrc").write_text("26\n")
        package = {"engines": {"node": "^26.0.0"}}
        (fixture / "package.json").write_text(json.dumps(package))
        (fixture / "package-lock.json").write_text(json.dumps({"packages": {"": package}}))
        workflow = "jobs:\n  lint:\n    steps:\n      - uses: actions/setup-node@" + "1" * 40 + "\n        with:\n          node-version: '26'\n"
        for name in ("local-openapi-lint.yml", "local-prettier.yml"):
            (workflows / name).write_text(workflow)
        command = ["node", str(fixture / GUARD)]
        if _run(command, cwd=fixture).returncode != 0:
            return False
        for relative, bad in ((".nvmrc", "22\n"),
                              ("package.json", '{"engines":{"node":"^22.0.0"}}'),
                              ("package-lock.json", '{"packages":{"":{"engines":{"node":"^22.0.0"}}}}'),
                              (".github/workflows/local-prettier.yml", workflow.replace("'26'", "'22'")),
                              (".github/workflows/local-openapi-lint.yml", "jobs: {}\n")):
            path = fixture / relative
            original = path.read_bytes()
            path.write_text(bad)
            try:
                if _run(command, cwd=fixture).returncode == 0:
                    return False
            finally:
                path.write_bytes(original)
        target = fixture / "unopened-fifo"
        os.mkfifo(target)
        for name in ("probe.yml", "probe.yaml"):
            path = workflows / name
            for kind in ("symlink", "fifo", "directory"):
                if kind == "symlink":
                    path.symlink_to(target)
                elif kind == "fifo":
                    os.mkfifo(path)
                else:
                    path.mkdir()
                try:
                    result = _run(command, cwd=fixture, timeout=5)
                    if result.returncode != 1 or f"{name} must be a regular file".encode() not in result.stderr:
                        return False
                finally:
                    path.rmdir() if kind == "directory" else path.unlink()
        return True


def main(arguments: list[str]) -> int:
    root = Path.cwd()
    success = False
    try:
        if arguments or (root / ".nvmrc").read_text().strip() != "26":
            raise ValueError("wrong runtime selection")
        if json.loads((root / "package.json").read_text()).get("engines", {}).get("node") != "^26.0.0":
            raise ValueError("wrong engine selection")
        if _run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=root, timeout=60).returncode != 0:
            raise ValueError("locked dependencies failed")
        success = (_run(["node", str(GUARD)], cwd=root).returncode == 0
                   and _probe_guard(root))
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        success = False
    finally:
        shutil.rmtree(root / "node_modules", ignore_errors=True)
    print(json.dumps(INVARIANTS if success else ["registered_validation"]))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
