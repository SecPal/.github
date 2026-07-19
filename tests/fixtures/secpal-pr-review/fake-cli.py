#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Run the PR-state CLI with explicit fixture executables for integration tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


if len(sys.argv) < 4:
    raise SystemExit("usage: fake-cli.py HELPER FIXTURE_BIN COMMAND [ARG ...]")

helper = Path(sys.argv[1]).resolve()
fixture_bin = Path(sys.argv[2]).resolve()
spec = importlib.util.spec_from_file_location("secpal_pr_review_fixture", helper)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot load helper: {helper}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
real_command_runner = module.CommandRunner


class FixtureCommandRunner(real_command_runner):
    def __init__(self) -> None:
        super().__init__(
            {
                "git": str(fixture_bin / "git"),
                "gh": str(fixture_bin / "gh"),
            }
        )


module.CommandRunner = FixtureCommandRunner
raise SystemExit(module.main(sys.argv[3:]))
