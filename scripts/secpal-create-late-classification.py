#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Launch maintained evidence production through the Actions owner."""

import importlib.util
from pathlib import Path
import sys


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "secpal_pr_review_actions", Path(__file__).resolve().with_name("secpal-pr-review-actions.py")
    )
    if spec.name in sys.modules:
        raise RuntimeError("Cannot replace a preloaded Actions owner")
    owner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = owner
    spec.loader.exec_module(owner)
    return owner._owned_verifier_module("late_classification_cli").main()


if __name__ == "__main__":
    raise SystemExit(main())
