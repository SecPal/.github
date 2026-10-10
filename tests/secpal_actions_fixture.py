# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""One constructed Actions owner for same-process fixture composition."""

import importlib.util
from pathlib import Path
import sys

_actions = None


def load_actions():
    global _actions
    if _actions is None:
        path = Path(__file__).resolve().parents[1] / "scripts/secpal-pr-review-actions.py"
        spec = importlib.util.spec_from_file_location("secpal_pr_review_actions", path)
        if spec.name in sys.modules:
            raise RuntimeError("Shared fixture cannot replace an existing Actions owner")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _actions = module
    return _actions._require_owned_actions_bridge()
