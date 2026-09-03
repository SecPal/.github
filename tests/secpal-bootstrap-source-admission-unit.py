# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for the exact #810 bootstrap implementation source."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BootstrapSourceAdmissionContractTests(unittest.TestCase):
    def test_accepted_main_exposes_exact_source_admission_boundary(self) -> None:
        module = importlib.import_module(
            "scripts.secpal_pr_review.bootstrap_source_admission"
        )

        self.assertTrue(
            callable(module.execute_first_ready_executor_bootstrap),
            "accepted main lacks the closed #810 bootstrap source boundary",
        )


if __name__ == "__main__":
    unittest.main()
