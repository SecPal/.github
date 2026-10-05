# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""One Actions construction for composition fixtures in one interpreter."""

from scripts.secpal_pr_review import bootstrap_source_admission

_actions = None


def load_actions():
    global _actions
    if _actions is None:
        _actions = bootstrap_source_admission._load_actions_helper()
    return _actions._require_owned_actions_bridge()
