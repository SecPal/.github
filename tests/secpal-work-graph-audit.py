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
from secpal_work_graph import resolver  # noqa: E402
from secpal_work_graph.model import CLOSED, COMPLETED, Node, build_snapshot  # noqa: E402

SPEC = importlib.util.spec_from_file_location("work_graph_audit_cli", ROOT / "scripts" / "secpal-work-graph-audit.py")
audit_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(audit_cli)

REPO = "SecPal/.github"
def key(number): return f"{REPO}#{number}"
def leaf(number, **kwargs): return Node(REPO, number, has_acceptance_criteria=True, **kwargs)


class AuditClassificationTests(TestCase):
    @staticmethod
    def discovery_adapter(rows):
        class DiscoveryAdapter:
            def __init__(self, **_kwargs):
                pass

            def query(self, _document, _variables):
                return audit_cli.github.GraphQLResponse(
                    {
                        "repository": {
                            "issues": {
                                "nodes": rows,
                                "pageInfo": {"hasNextPage": False},
                            }
                        }
                    },
                    (),
                )

        return DiscoveryAdapter

    @staticmethod
    def discovery_row(
        number,
        *,
        body="",
        parent=None,
        children=0,
        blocked_by=0,
        blocking=0,
        closing=(),
    ):
        return {
            "number": number,
            "title": f"Issue {number}",
            "body": body,
            "repository": {"nameWithOwner": REPO},
            "parent": parent,
            "subIssues": {"totalCount": children},
            "blockedBy": {"totalCount": blocked_by},
            "blocking": {"totalCount": blocking},
            "labels": {"nodes": []},
            "closedByPullRequestsReferences": {
                "totalCount": len(closing),
                "nodes": [
                    {"number": number, "repository": {"nameWithOwner": REPO}}
                    for number in closing
                ],
            },
        }

    def findings(self, nodes, repository=REPO):
        snapshot = build_snapshot(nodes)
        return audit.classify_native(snapshot, nodes[0].key, repository=repository)

    def test_clean_native_graph_is_clean(self):
        self.assertEqual(self.findings([leaf(1)]), [])

    def test_mirrors_are_migration_debt_not_graph_authority(self):
        findings = audit.classify_advisory(
            audit.AdvisoryIssueFacts(
                key(1), REPO, "legacy_candidate", relationship_mirrors=("blocked by",)
            )
        )
        self.assertEqual({item["kind"] for item in findings}, {"body_relationship_mirror", "prose_only_blocker"})
        self.assertTrue(all(item["classification"] == "migration_debt" for item in findings))

    def test_closed_parent_open_child_and_incomplete_leaf_are_blockers(self):
        parent = Node(REPO, 1, state=CLOSED, state_reason=COMPLETED, children=(key(2),))
        child = Node(REPO, 2, parent=key(1), has_acceptance_criteria=False)
        findings = self.findings([parent, child])
        self.assertEqual({item["kind"] for item in findings}, {"closed_parent_open_child", "structurally_incomplete_delivery_leaf"})
        self.assertTrue(all(item["classification"] == "execution_blocker" for item in findings))

    def test_direct_epic_pr_and_multiple_delivery_prs_are_advisory(self):
        findings = audit.classify_advisory(
            audit.AdvisoryIssueFacts(
                key(1),
                REPO,
                "native",
                native_children_count=1,
                closing_pull_requests=(f"{REPO}#9",),
            )
        ) + audit.classify_advisory(
            audit.AdvisoryIssueFacts(
                key(2),
                REPO,
                "native",
                closing_pull_requests=(f"{REPO}#10", f"{REPO}#11"),
            )
        )
        direct = next(item for item in findings if item["kind"] == "direct_epic_delivery_pull_request")
        multi = next(item for item in findings if item["kind"] == "multi_contract_leaf_candidate")
        self.assertEqual(direct["classification"], "migration_debt")
        self.assertTrue(multi["requires_judgment"])

    def test_native_epic_is_not_a_multi_contract_leaf_candidate(self):
        epic_findings = audit.classify_advisory(
            audit.AdvisoryIssueFacts(
                key(1),
                REPO,
                "native",
                native_children_count=1,
                closing_pull_requests=(f"{REPO}#10", f"{REPO}#11"),
            )
        )
        self.assertEqual(
            [item["kind"] for item in epic_findings],
            [
                "direct_epic_delivery_pull_request",
                "direct_epic_delivery_pull_request",
            ],
        )

        leaf_findings = audit.classify_advisory(
            audit.AdvisoryIssueFacts(
                key(2),
                REPO,
                "native",
                closing_pull_requests=(f"{REPO}#12", f"{REPO}#13"),
            )
        )
        candidate = next(
            item
            for item in leaf_findings
            if item["kind"] == "multi_contract_leaf_candidate"
        )
        self.assertEqual(candidate["classification"], "migration_debt")
        self.assertTrue(candidate["requires_judgment"])

    def test_legacy_epic_label_remains_epic_evidence_for_closing_prs(self):
        findings = audit.classify_advisory(
            audit.AdvisoryIssueFacts(
                key(1),
                REPO,
                "legacy_candidate",
                legacy_epic_candidate=True,
                closing_pull_requests=(f"{REPO}#9",),
            )
        )
        self.assertIn("direct_epic_delivery_pull_request", {item["kind"] for item in findings})

    def test_leaf_title_does_not_make_an_epic(self):
        row = self.discovery_row(1, closing=(9,))
        row["title"] = "Fix epic synchronization failure"
        facts = audit_cli._advisory_facts(
            row,
            acceptance_criteria.StructuralBody(False, ()),
            REPO,
        )
        findings = audit.classify_advisory(facts)
        self.assertNotIn("direct_epic_delivery_pull_request", {item["kind"] for item in findings})

    def test_cross_repository_nodes_are_reported_only_by_their_repository(self):
        other = "SecPal/api"
        parent = Node(REPO, 1, children=(f"{other}#2",))
        child = Node(other, 2, parent=key(1), has_acceptance_criteria=False)
        findings = self.findings([parent, child])
        self.assertTrue(all(item["repository"] == REPO for item in findings))

    def test_cross_repository_dependency_cycle_is_attributed_to_local_member(self):
        frontend = "SecPal/frontend"
        api = "SecPal/api"
        root = f"{frontend}#1"
        frontend_leaf = f"{frontend}#10"
        api_dependency = f"{api}#2"
        snapshot = build_snapshot(
            [
                Node(frontend, 1, children=(frontend_leaf,)),
                Node(
                    frontend,
                    10,
                    parent=root,
                    blocked_by=(api_dependency,),
                    has_acceptance_criteria=True,
                ),
                Node(
                    api,
                    2,
                    blocked_by=(frontend_leaf,),
                    has_acceptance_criteria=True,
                ),
            ]
        )

        resolution = resolver.resolve(snapshot, root)
        canonical = next(
            finding
            for finding in resolution.findings
            if finding.code == resolver.FINDING_DEPENDENCY_CYCLE
        )
        self.assertEqual(canonical.node, api_dependency)

        findings = audit.classify_native(snapshot, root, repository=frontend)
        cycle = next(item for item in findings if item["kind"] == "dependency_cycle")
        self.assertEqual(cycle["classification"], "execution_blocker")
        self.assertEqual(cycle["issue"], frontend_leaf)
        self.assertFalse(
            any(
                item["kind"] == "dependency_cycle"
                for item in audit.classify_native(
                    snapshot, root, repository="SecPal/contracts"
                )
            )
        )

    def test_cross_repository_unresolved_child_is_attributed_to_local_parent(self):
        frontend = "SecPal/frontend"
        root = f"{frontend}#1"
        missing_child = "SecPal/api#2"
        snapshot = build_snapshot([Node(frontend, 1, children=(missing_child,))])

        findings = audit.classify_native(snapshot, root, repository=frontend)
        unresolved = next(
            item for item in findings if item["kind"] == "unresolved_sub_issue"
        )
        self.assertEqual(unresolved["issue"], root)
        self.assertEqual(unresolved["classification"], "execution_blocker")

    def test_cross_repository_inconsistent_child_is_attributed_to_local_parent(self):
        frontend = "SecPal/frontend"
        root = f"{frontend}#1"
        inconsistent_child = "SecPal/api#2"
        snapshot = build_snapshot(
            [
                Node(frontend, 1, children=(inconsistent_child,)),
                Node("SecPal/api", 2, has_acceptance_criteria=True),
            ]
        )

        findings = audit.classify_native(snapshot, root, repository=frontend)
        inconsistent = next(
            item for item in findings
            if item["kind"] == "containment_inconsistent"
        )
        self.assertEqual(inconsistent["issue"], root)
        self.assertEqual(inconsistent["classification"], "execution_blocker")

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

    def test_checklist_only_issue_is_advisory_without_snapshot_resolution(self):
        rows = [self.discovery_row(1, body="- [ ] one\n- [x] two")]
        output = io.StringIO()
        with (
            patch.object(audit_cli.github, "GitHubReadAdapter", self.discovery_adapter(rows)),
            patch.object(audit_cli.github, "load_snapshot") as load_snapshot,
            patch("sys.stdout", output),
        ):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 0)
        findings = __import__("json").loads(output.getvalue())["repositories"][0]["findings"]
        self.assertEqual({item["kind"] for item in findings}, {"duplicated_markdown_status"})
        self.assertEqual(findings[0]["classification"], "migration_debt")
        load_snapshot.assert_not_called()

    def test_many_checklist_only_issues_do_not_fan_out_snapshot_resolution(self):
        rows = [self.discovery_row(number, body="- [ ] migrate") for number in range(1, 126)]
        output = io.StringIO()
        with (
            patch.object(audit_cli.github, "GitHubReadAdapter", self.discovery_adapter(rows)),
            patch.object(audit_cli.github, "load_snapshot") as load_snapshot,
            patch("sys.stdout", output),
        ):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 0)
        findings = __import__("json").loads(output.getvalue())["repositories"][0]["findings"]
        self.assertEqual(len(findings), 125)
        self.assertEqual({item["kind"] for item in findings}, {"duplicated_markdown_status"})
        load_snapshot.assert_not_called()

    def test_standalone_dependency_root_reports_unresolved_dependency(self):
        rows = [self.discovery_row(1, blocked_by=1)]
        adapter = self.discovery_adapter(rows)()
        snapshot = build_snapshot([leaf(1, blocked_by=(key(404),))])
        with patch.object(
            audit_cli.github,
            "load_snapshot",
            return_value=(snapshot, key(1)),
        ) as load_snapshot:
            result = audit_cli._audit_repository(adapter, REPO)

        self.assertEqual(result["status"], "findings")
        unresolved = next(
            item
            for item in result["findings"]
            if item["kind"] == "unresolved_dependency"
        )
        self.assertEqual(unresolved["classification"], "execution_blocker")
        load_snapshot.assert_called_once_with(adapter, key(1))

    def test_standalone_dependency_root_reports_dependency_cycle(self):
        rows = [self.discovery_row(1, blocked_by=1)]
        adapter = self.discovery_adapter(rows)()
        peer = "SecPal/api#2"
        snapshot = build_snapshot(
            [
                leaf(1, blocked_by=(peer,)),
                Node(
                    "SecPal/api",
                    2,
                    blocked_by=(key(1),),
                    has_acceptance_criteria=True,
                ),
            ]
        )
        with patch.object(
            audit_cli.github,
            "load_snapshot",
            return_value=(snapshot, key(1)),
        ) as load_snapshot:
            result = audit_cli._audit_repository(adapter, REPO)

        cycle = next(
            item
            for item in result["findings"]
            if item["kind"] == "dependency_cycle"
        )
        self.assertEqual(cycle["classification"], "execution_blocker")
        load_snapshot.assert_called_once_with(adapter, key(1))

    def test_contained_dependency_leaf_does_not_add_native_root(self):
        parent = {"number": 1, "repository": {"nameWithOwner": REPO}}
        rows = [
            self.discovery_row(1, children=1),
            self.discovery_row(2, parent=parent, blocked_by=1),
        ]
        adapter = self.discovery_adapter(rows)()
        snapshot = build_snapshot(
            [
                Node(REPO, 1, children=(key(2),)),
                leaf(2, parent=key(1), blocked_by=(key(404),)),
            ]
        )
        with patch.object(
            audit_cli.github,
            "load_snapshot",
            return_value=(snapshot, key(1)),
        ) as load_snapshot:
            result = audit_cli._audit_repository(adapter, REPO)

        self.assertIn(
            "unresolved_dependency",
            {item["kind"] for item in result["findings"]},
        )
        load_snapshot.assert_called_once_with(adapter, key(1))

    def test_one_native_root_serves_advisory_descendants_without_reresolution(self):
        parent = {"number": 1, "repository": {"nameWithOwner": REPO}}
        rows = [
            self.discovery_row(1, children=3),
            self.discovery_row(2, parent=parent, body="- [ ] migrate"),
            self.discovery_row(3, parent=parent, body="Blocked by: #9"),
            self.discovery_row(4, parent=parent, closing=(10, 11)),
        ]
        snapshot = build_snapshot(
            [
                Node(REPO, 1, children=(key(2), key(3), key(4))),
                Node(REPO, 2, parent=key(1), has_acceptance_criteria=False),
                leaf(3, parent=key(1)),
                leaf(4, parent=key(1)),
            ]
        )
        output = io.StringIO()
        with (
            patch.object(audit_cli.github, "GitHubReadAdapter", self.discovery_adapter(rows)),
            patch.object(
                audit_cli.github,
                "load_snapshot",
                return_value=(snapshot, key(1)),
            ) as load_snapshot,
            patch("sys.stdout", output),
        ):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 0)
        kinds = {
            item["kind"]
            for item in __import__("json").loads(output.getvalue())["repositories"][0]["findings"]
        }
        self.assertIn("structurally_incomplete_delivery_leaf", kinds)
        self.assertIn("duplicated_markdown_status", kinds)
        self.assertIn("body_relationship_mirror", kinds)
        self.assertIn("multi_contract_leaf_candidate", kinds)
        load_snapshot.assert_called_once()

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

    def test_cli_deduplicates_findings_from_overlapping_candidates(self):
        rows = [
            {
                "number": 1,
                "title": "Root",
                "body": "",
                "repository": {"nameWithOwner": REPO},
                "parent": None,
                "subIssues": {"totalCount": 1},
                "labels": {"nodes": []},
                "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
            },
            {
                "number": 2,
                "title": "Child",
                "body": "Blocked by: #9",
                "repository": {"nameWithOwner": REPO},
                "parent": {"number": 1, "repository": {"nameWithOwner": REPO}},
                "subIssues": {"totalCount": 0},
                "labels": {"nodes": []},
                "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
            },
        ]

        class DiscoveryAdapter:
            def __init__(self, **_kwargs):
                pass

            def query(self, _document, _variables):
                return audit_cli.github.GraphQLResponse(
                    {"repository": {"issues": {"nodes": rows, "pageInfo": {"hasNextPage": False}}}}, ()
                )

        snapshot = build_snapshot(
            [
                Node(REPO, 1, children=(key(2),)),
                leaf(2, parent=key(1), mirror_relationships=("blocked by",)),
            ]
        )
        facts = [
            acceptance_criteria.StructuralBody(False, ()),
            acceptance_criteria.StructuralBody(False, ("blocked by",)),
        ]
        output = io.StringIO()
        with (
            patch.object(audit_cli.github, "GitHubReadAdapter", DiscoveryAdapter),
            patch.object(audit_cli.github, "load_snapshot", side_effect=lambda _adapter, root: (snapshot, root)),
            patch.object(audit_cli, "parse", return_value=facts),
            patch("sys.stdout", output),
        ):
            self.assertEqual(audit_cli.main(["--repo", REPO]), 0)
        document = __import__("json").loads(output.getvalue())
        kinds = [item["kind"] for item in document["repositories"][0]["findings"]]
        self.assertEqual(kinds.count("body_relationship_mirror"), 1)
        self.assertEqual(kinds.count("prose_only_blocker"), 1)
        self.assertEqual(document["summary"]["migration_debt"], 2)

    def test_cli_uses_canonical_repository_identity_from_discovery(self):
        requested_repository = "secpal/.github"
        rows = [
            {
                "number": 1,
                "title": "Root",
                "body": "",
                "repository": {"nameWithOwner": REPO},
                "parent": None,
                "subIssues": {"totalCount": 1},
                "labels": {"nodes": []},
                "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
            }
        ]

        class DiscoveryAdapter:
            def __init__(self, **_kwargs):
                pass

            def query(self, _document, _variables):
                return audit_cli.github.GraphQLResponse(
                    {"repository": {"issues": {"nodes": rows, "pageInfo": {"hasNextPage": False}}}}, ()
                )

        snapshot = build_snapshot(
            [
                Node(REPO, 1, children=(key(2),)),
                Node(REPO, 2, parent=key(1), has_acceptance_criteria=False),
            ]
        )
        output = io.StringIO()
        with (
            patch.object(audit_cli.github, "GitHubReadAdapter", DiscoveryAdapter),
            patch.object(audit_cli.github, "load_snapshot", return_value=(snapshot, key(1))),
            patch("sys.stdout", output),
        ):
            self.assertEqual(audit_cli.main(["--repo", requested_repository]), 0)
        result = __import__("json").loads(output.getvalue())["repositories"][0]
        self.assertEqual(result["repository"], REPO)
        self.assertIn("structurally_incomplete_delivery_leaf", {item["kind"] for item in result["findings"]})

    def test_markdown_task_lists_are_structural_migration_evidence(self):
        checklist, code_example = acceptance_criteria.parse(["- [ ] first item\n- [x] second item", "```md\n- [ ] example\n```"])
        self.assertTrue(checklist.has_status_checklist)
        self.assertFalse(code_example.has_status_checklist)

    def test_checkbox_like_list_prose_is_not_a_task_list(self):
        link, inline_code, prose = acceptance_criteria.parse(
            [
                "- See [x](https://example.com)",
                "- The literal marker is `[x]`",
                "- A later marker [ ] is explanatory prose",
            ]
        )
        self.assertFalse(link.has_status_checklist)
        self.assertFalse(inline_code.has_status_checklist)
        self.assertFalse(prose.has_status_checklist)


if __name__ == "__main__":
    main()
