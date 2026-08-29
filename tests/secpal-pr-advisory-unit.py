#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Behavior evidence for the #674 advisory delivery-PR gate."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import model, pr_advisory, resolver  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "secpal_pr_advisory_cli", ROOT / "scripts" / "secpal-pr-advisory.py"
)
advisory_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(advisory_cli)

REPO = "SecPal/.github"


def key(number: int) -> str:
    return model.node_key(REPO, number)


def resolution(*nodes: model.Node, root: int = 674) -> resolver.Resolution:
    return resolver.resolve(model.build_snapshot(nodes), key(root))


def leaf(number: int, **overrides) -> model.Node:
    values = {"repository": REPO, "number": number, "has_acceptance_criteria": True}
    values.update(overrides)
    return model.Node(**values)


class DeliveryGraphAdvisoryTests(TestCase):
    def test_clean_leaf_reports_owning_issue_and_graph_state_without_findings(self):
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
        )

        self.assertEqual(report["owning_issue"], key(674))
        self.assertEqual(report["graph_state"]["role"], "leaf")
        self.assertTrue(report["graph_state"]["ready"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["status"], "advisory_clean")
        self.assertTrue(report["advisory"])

    def test_non_leaf_blocked_primary_and_multiple_closures_are_separate_findings(self):
        blocker = leaf(673, state=model.CLOSED, state_reason="not_planned")
        graph = resolution(
            leaf(674, children=(key(700),), blocked_by=(key(673),)),
            leaf(700, parent=key(674)),
            blocker,
        )

        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674), key(700)),
            graph=graph,
        )

        findings = {item["code"]: item for item in report["findings"]}
        self.assertEqual(
            set(findings),
            {"PR_CLOSES_NON_LEAF", "PRIMARY_ISSUE_BLOCKED", "MULTIPLE_DELIVERY_CONTRACTS"},
        )
        self.assertEqual(findings["PR_CLOSES_NON_LEAF"]["rule"], "work-graph section 5.2")
        self.assertEqual(findings["PRIMARY_ISSUE_BLOCKED"]["graph_state"]["blocked"], True)
        self.assertFalse(findings["PRIMARY_ISSUE_BLOCKED"]["technically_blocking"])
        self.assertFalse(findings["PRIMARY_ISSUE_BLOCKED"]["mechanically_blocking"])
        self.assertTrue(all(item["advisory"] for item in report["findings"]))

    def test_unready_leaf_reports_canonical_resolver_reasons_even_when_not_blocked(self):
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674, has_acceptance_criteria=False)),
        )

        finding = report["findings"][0]
        self.assertEqual(finding["code"], "PRIMARY_ISSUE_NOT_READY")
        self.assertFalse(finding["graph_state"]["blocked"])
        self.assertIn("missing_acceptance_criteria", finding["graph_state"]["reasons"])
        self.assertIn("missing_acceptance_criteria", finding["evidence"])

    def test_competing_primary_claim_excludes_current_pull_request(self):
        graph = resolution(
            leaf(
                674,
                claims=(
                    model.Claim("current", key(800)),
                    model.Claim("competitor", key(801)),
                ),
            )
        )

        report = pr_advisory.assess(
            pull_request=f"https://github.com/{REPO}/pull/800",
            pull_request_key=key(800),
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=graph,
        )

        finding = report["findings"][0]
        self.assertEqual(finding["code"], "COMPETING_PRIMARY_DELIVERY_CLAIM")
        self.assertIn(key(801), finding["evidence"])
        self.assertNotIn(key(800), finding["evidence"])

    def test_parent_reference_must_match_native_parent_and_root_must_omit_it(self):
        nested = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            pull_request_body="Fixes #674\n\nPart of: #999\n",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(667, children=(key(674),)), leaf(674, parent=key(667))),
        )
        standalone = pr_advisory.assess(
            pull_request=f"{REPO}#801",
            pull_request_body="Fixes #674\n\nPart of: not-an-issue\n",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
        )

        self.assertEqual(nested["findings"][0]["code"], "PARENT_REFERENCE_MISMATCH")
        self.assertIn(key(667), nested["findings"][0]["evidence"])
        self.assertEqual(standalone["findings"][0]["code"], "UNEXPECTED_PARENT_REFERENCE")


class EngineeringObservationTests(TestCase):
    def test_each_judgment_observation_maps_to_one_concise_canonical_rule(self):
        observations = tuple(
            pr_advisory.Observation(kind, evidence=f"evidence for {kind}")
            for kind in (
                "SECOND_RESPONSIBILITY",
                "DUPLICATE_INVARIANT_WITHOUT_BOUNDARY_JUSTIFICATION",
                "UNNAMED_EVIDENCE",
                "STRUCTURAL_EVIDENCE_AS_BEHAVIOR",
                "CUSTOM_MECHANISM_WITHOUT_STANDARDS_CHECK",
                "FINITE_DENYLIST_WHERE_ALLOWLIST_IS_PRACTICAL",
                "IN_SCOPE_PRE_FREEZE_OFFLOAD",
            )
        )
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
            observations=observations,
        )

        self.assertEqual(len(report["findings"]), len(observations))
        self.assertTrue(all(item["owning_issue"] == key(674) for item in report["findings"]))
        self.assertTrue(all(item["action"] and len(item["action"]) < 240 for item in report["findings"]))
        self.assertEqual(
            {item["rule"] for item in report["findings"]},
            {
                "work-graph section 7.2",
                "work-graph section 11",
                "work-graph sections 9 and 10",
                "work-graph section 9.3",
                "work-graph section 12.1",
                "work-graph section 12.2",
                "work-graph section 8.1",
            },
        )
        offload = next(
            item for item in report["findings"] if item["code"] == "IN_SCOPE_PRE_FREEZE_DEFECT_OFFLOADED"
        )
        self.assertIn("#692", offload["lifecycle_rule"])

    def test_counts_are_review_smells_but_never_standalone_findings(self):
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
            smells=pr_advisory.ReviewSmells(tests=90, changed_lines=4000, mutations=120),
        )
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["review_smells"], {"tests": 90, "changed_lines": 4000, "mutations": 120})


class LifecycleDispositionConsumptionTests(TestCase):
    def test_invalid_late_feedback_claim_uses_canonical_classifier_diagnostic(self):
        feedback = pr_advisory.FeedbackClaim(
            finding_id="late-1",
            classification={
                "classification": "NON_BLOCKING_FOLLOWUP",
                "technically_blocking": False,
                "mechanically_blocking": True,
                "timing": "BEFORE_FREEZE",
                "risk": [],
            },
            reported_technically_blocking=False,
            reported_mechanically_blocking=True,
        )
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
            feedback=(feedback,),
        )
        finding = report["findings"][0]
        self.assertEqual(finding["code"], "INVALID_LIFECYCLE_DISPOSITION")
        self.assertEqual(finding["lifecycle_rule"], "work-graph section 8.1 via #692 orchestration")
        self.assertIn("only valid after the evidence freeze", finding["evidence"])

    def test_high_risk_deferral_and_blocker_misreport_are_not_reimplemented(self):
        high_risk = pr_advisory.FeedbackClaim(
            finding_id="security-1",
            classification={
                "classification": "NON_BLOCKING_FOLLOWUP",
                "technically_blocking": False,
                "mechanically_blocking": True,
                "timing": "AFTER_FREEZE",
                "risk": ["SECURITY"],
            },
            reported_technically_blocking=False,
            reported_mechanically_blocking=True,
        )
        valid = pr_advisory.FeedbackClaim(
            finding_id="p3-1",
            classification={
                "classification": "NON_BLOCKING_FOLLOWUP",
                "technically_blocking": False,
                "mechanically_blocking": True,
                "timing": "AFTER_FREEZE",
                "risk": ["P3"],
            },
            reported_technically_blocking=True,
            reported_mechanically_blocking=True,
        )
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
            feedback=(high_risk, valid),
        )
        findings = {item["code"]: item for item in report["findings"]}
        self.assertIn("INVALID_LIFECYCLE_DISPOSITION", findings)
        self.assertIn("BLOCKING_STATUS_MISREPORTED", findings)
        self.assertFalse(findings["BLOCKING_STATUS_MISREPORTED"]["technically_blocking"])
        self.assertTrue(findings["BLOCKING_STATUS_MISREPORTED"]["mechanically_blocking"])

    def test_counter_reset_recursive_churn_and_unowned_followup_name_lifecycle_rule(self):
        claims = (
            pr_advisory.LifecycleClaim(
                "COUNTER_RESET", "replacement PR resets review counters", False, True
            ),
            pr_advisory.LifecycleClaim(
                "RECURSIVE_REVIEW_RESTART", "late feedback starts Cycle 3", False, True
            ),
            pr_advisory.LifecycleClaim(
                "UNOWNED_FOLLOW_UP", "follow-up omits existing epic #667", False, True
            ),
        )
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
            lifecycle_claims=claims,
        )
        self.assertEqual(len(report["findings"]), 3)
        self.assertTrue(all("lifecycle_rule" in item for item in report["findings"]))
        self.assertTrue(all("#692" in item["lifecycle_rule"] for item in report["findings"]))
        self.assertTrue(all(item["mechanically_blocking"] for item in report["findings"]))


class AdvisoryCommandTests(TestCase):
    def test_enforced_gate_rejects_each_authoritative_delivery_rule(self):
        cases = {
            "blocked primary": (
                resolution(
                    leaf(674, blocked_by=(key(673),)),
                    leaf(673, state=model.CLOSED, state_reason="not_planned"),
                ),
                (key(674),),
                "PRIMARY_ISSUE_BLOCKED",
                "work-graph sections 3.2 and 4.1",
            ),
            "non-leaf closure": (
                resolution(
                    leaf(674, children=(key(700),)),
                    leaf(700, parent=key(674)),
                ),
                (key(674),),
                "PR_CLOSES_NON_LEAF",
                "work-graph section 5.2",
            ),
            "structurally incomplete primary": (
                resolution(leaf(674, has_acceptance_criteria=False)),
                (key(674),),
                "PRIMARY_ISSUE_NOT_READY",
                "work-graph sections 3.5 and 4.1",
            ),
            "malformed primary": (
                resolution(leaf(674, parent=key(667))),
                (key(674),),
                "PRIMARY_ISSUE_NOT_READY",
                "work-graph sections 3.5 and 4.1",
            ),
            "multiple primary closures": (
                resolution(leaf(674)),
                (key(674), key(700)),
                "MULTIPLE_DELIVERY_CONTRACTS",
                "work-graph section 5.2",
            ),
        }

        for label, (graph, closing, expected_code, expected_rule) in cases.items():
            with self.subTest(label=label):
                pull = {
                    "url": f"https://github.com/{REPO}/pull/800",
                    "body": "Fixes #674\n",
                    "additions": 1,
                    "deletions": 0,
                    "closingIssuesReferences": {
                        "nodes": [
                            {
                                "number": int(issue.rpartition("#")[2]),
                                "repository": {"nameWithOwner": REPO},
                            }
                            for issue in closing
                        ]
                    },
                }

                def load_snapshot(_adapter, issue):
                    if issue == key(700):
                        return model.build_snapshot([leaf(700)]), issue
                    return graph.snapshot, issue

                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    patch.object(advisory_cli.github, "GitHubReadAdapter", return_value=object()),
                    patch.object(advisory_cli, "_pull_request", return_value=pull),
                    patch.object(advisory_cli.github, "load_snapshot", side_effect=load_snapshot),
                ):
                    status = advisory_cli.main(
                        ["--repo", REPO, "--pr", "800", "--enforce"],
                        stdout=stdout,
                        stderr=stderr,
                    )

                self.assertEqual(status, 1)
                report = __import__("json").loads(stdout.getvalue())
                finding = next(
                    item for item in report["findings"] if item["code"] == expected_code
                )
                self.assertEqual(finding["rule"], expected_rule)
                self.assertTrue(finding["evidence"])
                if label == "blocked primary":
                    self.assertIn(key(673), finding["evidence"])
                self.assertIn(expected_code, stderr.getvalue())
                self.assertIn(expected_rule, stderr.getvalue())

    def test_enforced_gate_accepts_a_standalone_single_leaf(self):
        pull = {
            "url": f"https://github.com/{REPO}/pull/800",
            "body": "Fixes #674\n",
            "additions": 1,
            "deletions": 0,
            "closingIssuesReferences": {
                "nodes": [{"number": 674, "repository": {"nameWithOwner": REPO}}]
            },
        }
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(advisory_cli.github, "GitHubReadAdapter", return_value=object()),
            patch.object(advisory_cli, "_pull_request", return_value=pull),
            patch.object(
                advisory_cli.github,
                "load_snapshot",
                return_value=(model.build_snapshot([leaf(674)]), key(674)),
            ),
        ):
            status = advisory_cli.main(
                ["--repo", REPO, "--pr", "800", "--enforce"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(status, 0)
        self.assertIn('"gate_status": "pass"', stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_enforced_gate_requires_graph_first_replanning_for_independent_scope(self):
        report = pr_advisory.assess(
            pull_request=f"{REPO}#800",
            primary_issue=key(674),
            closing_issues=(key(674),),
            graph=resolution(leaf(674)),
            observations=(
                pr_advisory.Observation(
                    "SECOND_RESPONSIBILITY",
                    "independent operator contract was added to the delivery diff",
                ),
            ),
        )

        hard = pr_advisory.hard_gate_findings(report)
        self.assertEqual([item["code"] for item in hard], ["SECOND_RESPONSIBILITY_WITHOUT_REPLANNING"])
        self.assertEqual(hard[0]["rule"], "work-graph section 7.2")

    def test_reported_finding_is_a_successful_warning_not_a_gate_failure(self):
        pull = {
            "url": f"https://github.com/{REPO}/pull/800",
            "additions": 900,
            "deletions": 100,
            "closingIssuesReferences": {
                "nodes": [
                    {"number": 674, "repository": {"nameWithOwner": REPO}},
                    {"number": 700, "repository": {"nameWithOwner": REPO}},
                ]
            },
        }
        snapshots = {
            key(674): model.build_snapshot([leaf(674)]),
            key(700): model.build_snapshot([leaf(700)]),
        }

        def load_snapshot(_adapter, issue):
            return snapshots[issue], issue

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(advisory_cli.github, "GitHubReadAdapter", return_value=object()),
            patch.object(advisory_cli, "_pull_request", return_value=pull),
            patch.object(advisory_cli.github, "load_snapshot", side_effect=load_snapshot),
        ):
            status = advisory_cli.main(
                ["--repo", REPO, "--pr", "800"], stdout=stdout, stderr=stderr
            )

        self.assertEqual(status, 0)
        self.assertIn('"status": "advisory_findings"', stdout.getvalue())
        self.assertIn("::warning title=SecPal PR advisory::", stderr.getvalue())
        self.assertIn("MULTIPLE_DELIVERY_CONTRACTS", stderr.getvalue())

    def test_non_delivery_pr_is_clean_without_graph_inference(self):
        pull = {
            "url": f"https://github.com/{REPO}/pull/800",
            "additions": 3,
            "deletions": 2,
            "closingIssuesReferences": {"nodes": []},
        }
        stdout = io.StringIO()
        with (
            patch.object(advisory_cli.github, "GitHubReadAdapter", return_value=object()),
            patch.object(advisory_cli, "_pull_request", return_value=pull),
            patch.object(advisory_cli.github, "load_snapshot") as load_snapshot,
        ):
            status = advisory_cli.main(
                ["--repo", REPO, "--pr", "800"], stdout=stdout, stderr=io.StringIO()
            )

        self.assertEqual(status, 0)
        self.assertIn('"status": "not_a_delivery_pr"', stdout.getvalue())
        load_snapshot.assert_not_called()

    def test_workflow_pins_node_22_before_installing_parser_dependencies(self):
        workflow = (ROOT / ".github/workflows/pr-governance-advisory.yml").read_text(
            encoding="utf-8"
        )

        setup = workflow.index("uses: actions/setup-node@")
        version = workflow.index('node-version: "22.x"')
        install = workflow.index("run: npm ci")
        self.assertLess(setup, version)
        self.assertLess(version, install)


if __name__ == "__main__":
    main()
