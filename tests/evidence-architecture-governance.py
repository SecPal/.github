#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Structural invariants for canonical evidence-architecture governance."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK_GRAPH_PATH = "docs/work-graph-contract.md"
EVIDENCE_PATH = "docs/evidence-architecture-contract.md"


def validate_binding(work_graph: str, evidence: str, agents: str) -> None:
    """Require one canonical companion and an unbroken runtime delegation."""

    if EVIDENCE_PATH not in work_graph:
        raise AssertionError(
            "the work-graph contract must normatively incorporate the evidence contract"
        )
    if "normatively incorporates" not in work_graph:
        raise AssertionError(
            "the work-graph contract must identify the companion as normative"
        )
    for path in (WORK_GRAPH_PATH, EVIDENCE_PATH):
        if path not in agents:
            raise AssertionError(f"the root runtime baseline must reference {path}")
    for reference in (
        "#64",
        "#67",
        "#72",
        "#117",
        "#120",
        "#121",
        "#122",
        "#145",
        "#146",
        "#147",
        "#148",
        "#149",
        "33021568439",
    ):
        if reference not in evidence:
            raise AssertionError(
                f"the historical source record must retain {reference}"
            )


class EvidenceArchitectureGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_graph = (ROOT / WORK_GRAPH_PATH).read_text(encoding="utf-8")
        self.evidence = (ROOT / EVIDENCE_PATH).read_text(encoding="utf-8")
        self.agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    def test_canonical_runtime_binding_is_complete(self) -> None:
        validate_binding(self.work_graph, self.evidence, self.agents)

    def test_missing_work_graph_delegation_is_rejected(self) -> None:
        mutated = self.work_graph.replace(EVIDENCE_PATH, "")
        with self.assertRaisesRegex(AssertionError, "normatively incorporate"):
            validate_binding(mutated, self.evidence, self.agents)

    def test_missing_runtime_baseline_reference_is_rejected(self) -> None:
        mutated = self.agents.replace(EVIDENCE_PATH, "")
        with self.assertRaisesRegex(AssertionError, "root runtime baseline"):
            validate_binding(self.work_graph, self.evidence, mutated)


if __name__ == "__main__":
    unittest.main()
