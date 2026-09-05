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
CONTRACT = ROOT / "docs" / "work-graph-contract.md"
EVIDENCE_CONTRACT = ROOT / "docs" / "evidence-architecture-contract.md"
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
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.evidence_contract = EVIDENCE_CONTRACT.read_text(encoding="utf-8")

    def test_graph_mutation_precedes_scope_expansion(self):
        self.assertRegex(self.section, r"before\s+implementation scope expands")
        self.assertIn("scripts/secpal-work-graph-replan.py", self.section)
        self.assertIn("plan", self.section)
        self.assertIn("apply", self.section)
        self.assertRegex(self.section, r"exact\s+authenticated actor")
        self.assertRegex(self.section, r"(?i)stale|drift")

    def test_classification_semantics_have_one_authoritative_home(self):
        for classification in (
            "IN_CONTRACT_DEFECT",
            "MISSING_PREREQUISITE",
            "NEW_RESPONSIBILITY",
            "PROMOTE_TO_SUB_EPIC",
            "NON_BLOCKING_FOLLOWUP",
            "INVALID_FINDING",
        ):
            self.assertIn(f"`{classification}`", self.contract)
            self.assertNotIn(classification, self.section)
        self.assertIn("docs/work-graph-contract.md", self.section)
        self.assertRegex(self.contract, r"single\s+(?:authoritative|organization-wide) definition")
        self.assertNotIn("technically_blocking", self.section)
        self.assertNotIn("mechanically_blocking", self.section)
        self.assertIn("`technically_blocking`", self.contract)
        self.assertIn("`mechanically_blocking`", self.contract)
        for risk in ("P1", "P2", "security", "authentication", "integrity", "fail-open"):
            self.assertIn(risk, self.contract)

    def test_managed_instructions_only_carry_the_operational_protocol(self):
        self.assertRegex(self.section, r"before\s+implementation scope expands")
        self.assertNotRegex(self.section, r"(?i)P1|P2|security|authentication|integrity|fail-open")

    def test_prerequisite_insertion_requires_canonical_necessity_judgment(self):
        matches = re.findall(
            r"^#### Prerequisite Necessity\n(?P<body>.*?)(?=^#{2,4} |\Z)",
            self.contract,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(matches), 1)
        rule = " ".join(matches[0].split())

        for excluded_shortcut in (
            "ordinary in-contract defect",
            "invocation boundary",
            "restored or reacquired",
            "existing issue already owns",
        ):
            self.assertIn(excluded_shortcut, rule)
        self.assertIn("independent trust or authority boundary", rule)
        self.assertRegex(
            rule,
            re.compile(r"second corrective prerequisite.*independently necessary", re.DOTALL),
        )
        self.assertIn("historical classification", rule)
        self.assertIn("current technical truth", rule)
        self.assertIn("accepted authority extension", rule)
        self.assertIn("remove the obsolete native dependency first", rule)
        self.assertRegex(
            " ".join(self.contract.split()),
            r"MISSING_PREREQUISITE.*Prerequisite Necessity.*section 7\.1",
        )
        self.assertIn(
            "Prerequisite Necessity",
            " ".join(self.evidence_contract.split()),
        )

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
