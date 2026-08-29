#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REFRESH = REPO_ROOT / "scripts" / "refresh-polyscope-container-preview.sh"


def write_executable(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def run_refresh(
    root: pathlib.Path, rendered_content: str, *, fail_restart: bool = False
) -> subprocess.CompletedProcess[str]:
    fake_bin = root / "bin"
    command_log = root / "commands.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "RENDERED_CONTENT": rendered_content,
            "POLYSCOPE_PREVIEW_REFRESH_ATTEMPTS": "1",
            "POLYSCOPE_PREVIEW_REFRESH_DELAY_SECONDS": "1",
            "FAIL_RESTART": "1" if fail_restart else "0",
        }
    )
    return subprocess.run(
        [
            "bash",
            str(REFRESH),
            str(root / "renderer.py"),
            str(root / "cleanup.py"),
            str(root / "polyscope.db"),
            str(root / "clones"),
            str(root / "repos"),
            str(root / "Caddyfile"),
            "polyscope-preview.service",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="polyscope-preview-refresh.") as temporary:
        root = pathlib.Path(temporary)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        (root / "clones").mkdir()
        (root / "repos").mkdir()
        (root / "polyscope.db").touch()
        write_executable(root / "cleanup.py", "#!/usr/bin/env python3\n")
        write_executable(
            root / "renderer.py",
            "#!/usr/bin/env python3\n"
            "import argparse, os, pathlib\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--output', required=True)\n"
            "args, _ = parser.parse_known_args()\n"
            "pathlib.Path(args.output).write_text(os.environ['RENDERED_CONTENT'])\n",
        )
        write_executable(
            fake_bin / "systemctl",
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >>"$COMMAND_LOG"\n'
            'if [ "${FAIL_RESTART:-0}" = 1 ]; then exit 1; fi\n'
            "exit 0\n",
        )

        caddyfile = root / "Caddyfile"
        caddyfile.write_text("same\n", encoding="utf-8")
        unchanged = run_refresh(root, "same\n")
        assert unchanged.returncode == 0, (unchanged.stdout, unchanged.stderr)
        assert not (root / "commands.log").exists()
        assert caddyfile.read_text(encoding="utf-8") == "same\n"

        changed = run_refresh(root, "changed\n")
        assert changed.returncode == 0, (changed.stdout, changed.stderr)
        assert caddyfile.read_text(encoding="utf-8") == "changed\n"
        assert (caddyfile.stat().st_mode & 0o777) == 0o600
        assert (root / "commands.log").read_text(encoding="utf-8") == (
            "--user restart polyscope-preview.service\n"
        )

        (root / "commands.log").unlink()
        failed = run_refresh(root, "must-not-stick\n", fail_restart=True)
        assert failed.returncode != 0
        assert caddyfile.read_text(encoding="utf-8") == "changed\n"
        assert not list(root.glob(".Caddyfile.*"))


if __name__ == "__main__":
    main()
