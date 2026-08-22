#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Contract evidence for Polyscope's advisory canonical graph selection."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "polyscope-codex-AGENTS.md"


class PolyscopeWorkGraphAdvisoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.instructions = TEMPLATE.read_text(encoding="utf-8")
        match = re.search(
            r"^## Canonical Work-Graph Advisory\n(?P<body>.*?)(?=^## |\Z)",
            cls.instructions,
            flags=re.MULTILINE | re.DOTALL,
        )
        cls.advisory = match.group("body") if match else ""

    def test_managed_surface_declares_a_single_canonical_advisory_seam(self) -> None:
        self.assertTrue(self.advisory, "the managed advisory section is missing")
        self.assertIn("docs/work-graph-contract.md", self.advisory)
        self.assertIn("scripts/secpal-work-graph.py", self.advisory)
        self.assertRegex(self.advisory, r"(?i)read-only")
        self.assertRegex(self.advisory, r"(?i)machine-readable|JSON")
        for command in ("show", "ready", "next", "validate-issue"):
            self.assertRegex(self.advisory, rf"(?m)^.*\b{re.escape(command)}\b.*$")

    def test_scope_and_state_are_taken_from_canonical_native_graph_output(self) -> None:
        self.assertRegex(self.advisory, r"(?i)requested issue.*\bshow\b|\bshow\b.*requested issue")
        self.assertRegex(self.advisory, r"(?i)ancestor")
        self.assertRegex(self.advisory, r"(?i)scope\s+root")
        for state in ("blocked", "non-leaf", "structurally incomplete", "malformed"):
            self.assertRegex(self.advisory, rf"(?i)\b{state}\b")
        self.assertRegex(self.advisory, r"(?i)incomplete.*input|input.*incomplete")
        self.assertRegex(self.advisory, r"(?i)body-only.*not authoritative|not authoritative.*body-only")

    def test_requested_issue_remains_an_explicit_advisory_override(self) -> None:
        self.assertRegex(self.advisory, r"(?i)requested.*READY|READY.*requested")
        self.assertRegex(self.advisory, r"(?i)requested.*NEXT|NEXT.*requested")
        self.assertRegex(self.advisory, r"(?i)explicit user.*override")
        self.assertRegex(self.advisory, r"(?i)continue.*requested|requested.*continue")
        self.assertRegex(self.advisory, r"(?i)advisory.*not.*hard|not.*hard.*advisory")

    def test_parallelism_and_read_only_operation_are_preserved(self) -> None:
        self.assertRegex(self.advisory, r"(?i)parallel")
        self.assertRegex(self.advisory, r"(?i)do not.*dependenc|dependenc.*do not")
        self.assertRegex(self.advisory, r"(?i)do not.*mutat|mutat.*do not")


if __name__ == "__main__":
    unittest.main()
