#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Read-only SecPal work-graph resolution.

Semantics: docs/work-graph-contract.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secpal_work_graph.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
