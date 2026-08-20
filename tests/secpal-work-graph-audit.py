#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Focused pure evidence for the report-only work-graph migration audit."""
from __future__ import annotations

import sys
import importlib.util
import io
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from secpal_work_graph import audit  # noqa: E402
from secpal_work_graph import acceptance_criteria  # noqa: E402
from secpal_work_graph.model import CLOSED, COMPLETED, Node, build_snapshot  # noqa: E402

SPEC = importlib.util.spec_from_file_location("work_graph_audit_cli", ROOT / "scripts" / "secpal-work-graph-audit.py")
audit_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(audit_cli)

REPO = "SecPal/.github"
def key(number): return f"{REPO}#{number}"
def leaf(number, **kwargs): return Node(REPO, number, has_acceptance_criteria=True, **kwargs)


class AuditClassificationTests(TestCase):
    def findings(self, nodes, candidate=None, repository=REPO, closing_pull_requests_by_issue=None):
        snapshot = build_snapshot(nodes)
        candidate = candidate or audit.Candidate(nodes[0].key, "native")
        return audit.classify(snapshot, nodes[0].key, candidate, repository=repository, closing_pull_requests_by_issue=closing_pull_requests_by_issue)

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

    def test_direct_epic_pr_and_multiple_delivery_prs_are_advisory(self):
        epic = Node(REPO, 1, title="[EPIC] rollout", children=(key(2),))
        child = leaf(2, parent=key(1))
        findings = self.findings([epic, child], closing_pull_requests_by_issue={key(1): (f"{REPO}#9",), key(2): (f"{REPO}#10", f"{REPO}#11")})
        direct = next(item for item in findings if item["kind"] == "direct_epic_delivery_pull_request")
        multi = next(item for item in findings if item["kind"] == "multi_contract_leaf_candidate")
        self.assertEqual(direct["classification"], "migration_debt")
        self.assertTrue(multi["requires_judgment"])

    def test_legacy_epic_label_remains_epic_evidence_for_closing_prs(self):
        node = leaf(1)
        findings = self.findings([node], audit.Candidate(node.key, "legacy_candidate", epic_candidate=True), closing_pull_requests_by_issue={key(1): (f"{REPO}#9",)})
        self.assertIn("direct_epic_delivery_pull_request", {item["kind"] for item in findings})

    def test_leaf_title_does_not_make_an_epic(self):
        node = leaf(1, title="Fix epic synchronization failure")
        findings = self.findings([node], closing_pull_requests_by_issue={key(1): (f"{REPO}#9",)})
        self.assertNotIn("direct_epic_delivery_pull_request", {item["kind"] for item in findings})

    def test_cross_repository_nodes_are_reported_only_by_their_repository(self):
        other = "SecPal/api"
        parent = Node(REPO, 1, children=(f"{other}#2",))
        child = Node(other, 2, parent=key(1), has_acceptance_criteria=False)
        findings = self.findings([parent, child])
        self.assertTrue(all(item["repository"] == REPO for item in findings))

    def test_document_is_deterministic_and_explicitly_clean(self):
        first = {"repository": "SecPal/z", "status": "clean", "findings": []}
        second = {"repository": "SecPal/a", "status": "clean", "findings": []}
        self.assertEqual(audit.document([first, second]), audit.document([second, first]))
        self.assertEqual(len(audit.DEFAULT_REPOSITORIES), 9)

    def test_cli_returns_zero_for_a_clean_repository(self):
        class EmptyAdapter:
            def __init__(self, **_kwargs):
                pass

            def query(self, _document, _variables):
                return audit_cli.github.GraphQLResponse(
                    {"repository": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}, ()
                )

        output = io.StringIO()
        with patch.object(audit_cli.github, "GitHubReadAdapter", EmptyAdapter), patch("sys.stdout", output):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 0)
        document = __import__("json").loads(output.getvalue())
        self.assertEqual(document["repositories"], [{"repository": REPO, "status": "clean", "findings": []}])

    def test_cli_marks_operational_failure_and_returns_three(self):
        class FailingAdapter:
            def __init__(self, **_kwargs):
                pass

            def query(self, _document, _variables):
                raise audit_cli.github.GitHubError("unavailable")

        output = io.StringIO()
        with patch.object(audit_cli.github, "GitHubReadAdapter", FailingAdapter), patch("sys.stdout", output):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 3)
        self.assertEqual(__import__("json").loads(output.getvalue())["repositories"][0]["status"], "unavailable")

    def test_cli_marks_graphql_access_error_unavailable(self):
        class ForbiddenAdapter:
            def __init__(self, **_kwargs):
                pass

            def query(self, _document, _variables):
                return audit_cli.github.GraphQLResponse(None, ({"type": "FORBIDDEN"},))

        output = io.StringIO()
        with patch.object(audit_cli.github, "GitHubReadAdapter", ForbiddenAdapter), patch("sys.stdout", output):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 3)
        self.assertEqual(__import__("json").loads(output.getvalue())["repositories"][0]["status"], "unavailable")

    def test_cli_rejects_partially_readable_discovery_pagination(self):
        class PartialAdapter:
            def __init__(self, **_kwargs):
                self.calls = 0

            def query(self, _document, _variables):
                self.calls += 1
                if self.calls == 1:
                    return audit_cli.github.GraphQLResponse(
                        {"repository": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}}, ()
                    )
                return audit_cli.github.GraphQLResponse(None, ({"type": "NOT_FOUND"},))

        output = io.StringIO()
        with patch.object(audit_cli.github, "GitHubReadAdapter", PartialAdapter), patch("sys.stdout", output):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 3)
        self.assertEqual(__import__("json").loads(output.getvalue())["repositories"][0]["status"], "unavailable")

    def test_markdown_task_lists_are_structural_migration_evidence(self):
        checklist, code_example = acceptance_criteria.parse(["- [ ] first item\n- [x] second item", "```md\n- [ ] example\n```"])
        self.assertTrue(checklist.has_status_checklist)
        self.assertFalse(code_example.has_status_checklist)


if __name__ == "__main__":
    main()
