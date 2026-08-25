#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Managed Polyscope contract evidence for graph-first replanning."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "polyscope-codex-AGENTS.md"
QUALITY = ROOT / ".github" / "workflows" / "quality.yml"
PREFLIGHT = ROOT / "scripts" / "preflight.sh"
COMMANDS = (
    "python3 -m unittest tests/secpal-work-graph-replan-unit.py",
    "python3 -m unittest tests/polyscope-work-graph-replanning.py",
)


class PolyscopeReplanningContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instructions = TEMPLATE.read_text(encoding="utf-8")
        matches = tuple(
            re.finditer(
                r"^## Canonical Work-Graph Replanning\n(?P<body>.*?)(?=^## |\Z)",
                cls.instructions,
                flags=re.MULTILINE | re.DOTALL,
            )
        )
        if len(matches) != 1:
            raise AssertionError(f"expected one replanning section, found {len(matches)}")
        cls.section = matches[0].group("body")

    def test_graph_mutation_precedes_scope_expansion(self):
        self.assertRegex(self.section, r"before\s+implementation scope expands")
        self.assertIn("scripts/secpal-work-graph-replan.py", self.section)
        self.assertIn("plan", self.section)
        self.assertIn("apply", self.section)
        self.assertRegex(self.section, r"exact\s+authenticated actor")
        self.assertRegex(self.section, r"(?i)stale|drift")

    def test_all_authoritative_classifications_are_named(self):
        for classification in (
            "IN_CONTRACT_DEFECT",
            "MISSING_PREREQUISITE",
            "NEW_RESPONSIBILITY",
            "PROMOTE_TO_SUB_EPIC",
            "NON_BLOCKING_FOLLOWUP",
            "INVALID_FINDING",
        ):
            self.assertIn(f"`{classification}`", self.section)

    def test_blocking_facts_and_high_risk_boundary_remain_explicit(self):
        self.assertIn("technically_blocking", self.section)
        self.assertIn("mechanically_blocking", self.section)
        for risk in ("P1", "P2", "security", "authentication", "integrity", "fail-open"):
            self.assertIn(risk, self.section)
        self.assertIn("cannot use `NON_BLOCKING_FOLLOWUP`", self.section)

    def test_current_contract_and_downstream_lifecycle_boundaries_are_preserved(self):
        self.assertRegex(self.section, r"IN_CONTRACT_DEFECT[^.]*current (?:leaf|delivery contract)")
        self.assertIn("#692", self.section)
        self.assertRegex(self.section, r"(?i)lifecycle[^.]*#692")
        self.assertRegex(self.section, r"(?i)owning epic|owning sub-epic")

    def test_required_validation_runs_both_replanning_suites_fail_closed(self):
        workflow = QUALITY.read_text(encoding="utf-8")
        preflight = PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn("work-graph-resolver:", workflow)
        self.assertIn("set -euo pipefail", preflight)
        for command in COMMANDS:
            self.assertEqual(workflow.count(f"run: {command}"), 1)
            self.assertEqual(preflight.count(command), 1)


if __name__ == "__main__":
    unittest.main()
