#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Refresh hard work-graph results after mutable native graph changes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secpal_work_graph import gate_refresh  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="secpal-work-graph-gate-refresh")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--gh", default="gh")
    parser.add_argument("--apply", action="store_true", required=True)
    arguments = parser.parse_args(argv)
    try:
        gateway = gate_refresh.CommandGateway(
            gh=arguments.gh, repository_root=Path(__file__).resolve().parents[1]
        )
        report = gate_refresh.refresh_repository(gateway, arguments.repo)
    except (OSError, ValueError, gate_refresh.RefreshError) as exc:
        print(f"work-graph gate refresh failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failed"] or report["unavailable"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
