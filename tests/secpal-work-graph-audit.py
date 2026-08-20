#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Focused pure evidence for the report-only work-graph migration audit."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from secpal_work_graph import audit  # noqa: E402
from secpal_work_graph.model import CLOSED, COMPLETED, Node, build_snapshot  # noqa: E402

REPO = "SecPal/.github"
def key(number): return f"{REPO}#{number}"
def leaf(number, **kwargs): return Node(REPO, number, has_acceptance_criteria=True, **kwargs)


class AuditClassificationTests(TestCase):
    def findings(self, nodes, candidate=None):
        snapshot = build_snapshot(nodes)
        candidate = candidate or audit.Candidate(nodes[0].key, "native")
        return audit.classify(snapshot, nodes[0].key, candidate)

    def test_clean_native_graph_is_clean(self):
        self.assertEqual(self.findings([leaf(1)]), [])

    def test_mirrors_are_migration_debt_not_graph_authority(self):
        findings = self.findings([leaf(1, mirror_relationships=("blocked by",))])
        self.assertEqual({item["kind"] for item in findings}, {"body_relationship_mirror", "prose_only_blocker"})
        self.assertTrue(all(item["classification"] == "migration_debt" for item in findings))

    def test_closed_parent_open_child_and_incomplete_leaf_are_blockers(self):
        parent = Node(REPO, 1, state=CLOSED, state_reason=COMPLETED, children=(key(2),))
        child = Node(REPO, 2, parent=key(1), has_acceptance_criteria=False)
        findings = self.findings([parent, child])
        self.assertEqual({item["kind"] for item in findings}, {"closed_parent_open_child", "structurally_incomplete_delivery_leaf"})
        self.assertTrue(all(item["classification"] == "execution_blocker" for item in findings))

    def test_direct_epic_pr_and_multi_contract_candidate_are_advisory(self):
        epic = Node(REPO, 1, title="[EPIC] rollout", children=(key(2),), closing_pull_requests=(f"{REPO}#9",))
        child = leaf(2, parent=key(1), blocking_count=2)
        findings = self.findings([epic, child])
        direct = next(item for item in findings if item["kind"] == "direct_epic_delivery_pull_request")
        multi = next(item for item in findings if item["kind"] == "multi_contract_leaf_candidate")
        self.assertEqual(direct["classification"], "migration_debt")
        self.assertTrue(multi["requires_judgment"])

    def test_document_is_deterministic_and_explicitly_clean(self):
        first = {"repository": "SecPal/z", "status": "clean", "findings": []}
        second = {"repository": "SecPal/a", "status": "clean", "findings": []}
        self.assertEqual(audit.document([first, second]), audit.document([second, first]))


if __name__ == "__main__":
    main()
