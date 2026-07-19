#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


HEAD = "a" * 40
arguments = sys.argv[1:]
log_path = os.environ.get("FAKE_GIT_LOG")
if log_path:
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments, separators=(",", ":")) + "\n")

if not arguments:
    raise SystemExit(2)

prohibited = {"push", "commit", "checkout", "switch", "reset", "clean", "stash", "fetch"}
if arguments[0] in prohibited:
    print(f"fake git rejected write operation: {arguments[0]}", file=sys.stderr)
    raise SystemExit(1)

responses = {
    ("rev-parse", "--show-toplevel"): "/fixture/repository\n",
    ("remote", "get-url", "origin"): "git@github.com:SecPal/.github.git\n",
    ("status", "--porcelain=v2", "--untracked-files=all"): "",
    ("branch", "--show-current"): "feat/test\n",
    ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"): "origin/feat/test\n",
    ("rev-parse", "HEAD"): f"{HEAD}\n",
    ("rev-parse", "@{upstream}"): f"{HEAD}\n",
    ("cat-file", "-e", f"{HEAD}^{{commit}}"): "",
}

key = tuple(arguments)
if key == ("verify-commit", "--raw", HEAD):
    print('Good "git" signature for aroviqen with ED25519 key SHA256:fixture', file=sys.stderr)
    raise SystemExit(0)
if key not in responses:
    print(f"fake git has no response for {arguments!r}", file=sys.stderr)
    raise SystemExit(2)
sys.stdout.write(responses[key])
