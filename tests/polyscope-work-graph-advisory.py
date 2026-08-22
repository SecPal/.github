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
        cls.advisory = cls._advisory_section(cls.instructions)
        cls.units = cls._semantic_units(cls.advisory)

    @staticmethod
    def _advisory_section(instructions: str) -> str:
        matches = tuple(
            re.finditer(
                r"^## Canonical Work-Graph Advisory\n(?P<body>.*?)(?=^## |\Z)",
                instructions,
                flags=re.MULTILINE | re.DOTALL,
            )
        )
        if len(matches) != 1:
            raise AssertionError(
                f"expected exactly one Canonical Work-Graph Advisory section, found {len(matches)}"
            )
        return matches[0].group("body")

    @staticmethod
    def _semantic_units(section: str) -> tuple[str, ...]:
        """Return normalized Markdown bullet units, independent of wrapping."""
        units: list[list[str]] = []
        current: list[str] | None = None
        for line in section.splitlines():
            if line.startswith("- "):
                current = [line[2:].strip()]
                units.append(current)
            elif current is not None and line.startswith("  "):
                current.append(line.strip())
            elif line.strip():
                current = None
        return tuple(" ".join(unit) for unit in units)

    def unit_with(self, *terms: str) -> str:
        matches = [unit for unit in self.units if all(term in unit for term in terms)]
        self.assertEqual(
            len(matches),
            1,
            f"expected one semantic instruction unit containing {terms}, got {matches}",
        )
        return matches[0]

    def test_managed_surface_declares_a_single_canonical_advisory_seam(self) -> None:
        self.assertTrue(self.advisory, "the managed advisory section is missing")
        resolver_unit = self.unit_with(
            "docs/work-graph-contract.md",
            "scripts/secpal-work-graph.py",
            "read-only",
        )
        self.assertRegex(resolver_unit, r"(?i)machine-readable|JSON")

    def test_duplicate_advisory_sections_are_rejected(self) -> None:
        duplicate = self.instructions + "\n## Canonical Work-Graph Advisory\n\n- conflicting guidance\n"
        with self.assertRaisesRegex(AssertionError, "exactly one"):
            self._advisory_section(duplicate)

    def test_next_uses_the_resolver_default_authenticated_identity(self) -> None:
        next_unit = self.unit_with("next <owner/repo#scope-number>", "canonical NEXT")
        self.assertNotIn(
            "--executor",
            next_unit,
            "managed NEXT must not substitute a Polyscope actor for the GitHub executor",
        )
        self.assertRegex(next_unit, r"(?i)resolver.*authenticated GitHub (viewer )?identity")

    def test_scope_and_state_come_from_canonical_native_graph_output(self) -> None:
        requested_reference = "<owner/repo#requested-number>"
        scope_reference = "<owner/repo#scope-number>"
        scope_unit = self.unit_with(
            f"show {requested_reference}",
            f"show {scope_reference}",
            f"ready {scope_reference}",
            f"next {scope_reference}",
            f"validate-issue {requested_reference}",
        )
        for term in ("native", "ancestors", "scope root", "incomplete graph input", "do not guess"):
            self.assertIn(term, scope_unit)
        self.assertRegex(scope_unit, r"(?i)bare issue numbers require an explicit `--repo`")
        self.assertIn("must not be used", scope_unit)

        mirror_unit = self.unit_with("body-only relationship mirror", "not authoritative")
        for term in ("hierarchy", "dependencies", "sibling order", "scope selection"):
            self.assertIn(term, mirror_unit)

    def test_requested_issue_remains_an_explicit_advisory_override(self) -> None:
        state_unit = self.unit_with(
            "requested issue",
            "READY",
            "canonical NEXT",
            "blocked",
            "malformed",
        )
        for state in ("blocked", "non-leaf", "structurally incomplete", "malformed"):
            self.assertIn(state, state_unit)

        override_unit = self.unit_with(
            "requested issue different from NEXT",
            "explicit user selection",
            "advisory override",
            "continue with the requested issue",
            "never call it READY",
        )
        self.assertIn("advisory, not a hard block", override_unit)

    def test_parallelism_and_read_only_operation_are_preserved(self) -> None:
        parallel_unit = self.unit_with("READY siblings remain parallel", "NEXT selects one candidate")
        self.assertRegex(parallel_unit, r"do not [^.]*mutate the graph")
        self.assertRegex(parallel_unit, r"(?:do not|or) (?:create|infer) dependencies")
        self.assertRegex(parallel_unit, r"do not [^.]*silently substitute")

    def test_every_ready_next_unit_delegates_to_the_canonical_contract(self) -> None:
        semantic_units = [unit for unit in self.units if re.search(r"\b(?:READY|NEXT)\b", unit)]
        self.assertTrue(semantic_units)
        for unit in semantic_units:
            self.assertIn("docs/work-graph-contract.md", unit)


if __name__ == "__main__":
    unittest.main()
