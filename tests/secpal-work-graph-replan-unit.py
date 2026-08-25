#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Behavior evidence for bounded graph-first replanning operations."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import github, github_replanning, model, replanning  # noqa: E402

REPO = "SecPal/.github"


def key(number: int) -> str:
    return model.node_key(REPO, number)


def node(number: int, **overrides) -> model.Node:
    fields = {
        "repository": REPO,
        "number": number,
        "node_id": f"ISSUE_{number}",
        "repository_id": "REPO_ID",
        "has_acceptance_criteria": True,
        "blocking_observable": True,
    }
    fields.update(overrides)
    if "blocking" in overrides and "blocking_count" not in overrides:
        fields["blocking_count"] = len(overrides["blocking"])
    return model.Node(**fields)


def graph(*nodes: model.Node) -> model.Snapshot:
    return model.build_snapshot(nodes)


def finding(name: str, **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "classification": name,
        "technically_blocking": False,
        "mechanically_blocking": False,
        "timing": "BEFORE_FREEZE",
        "risk": [],
    }
    value.update(overrides)
    return value


class FakeRecoverySigner:
    def sign(self, digest):
        return {"kind": "test-signature", "value": "signed:" + digest}

    def verify(self, authentication, digest):
        if authentication != {"kind": "test-signature", "value": "signed:" + digest}:
            raise replanning.StalePlanError("recovery authentication is invalid")


class ClassificationTests(TestCase):
    def test_each_classification_selects_exactly_one_bounded_action(self):
        expected = {
            "IN_CONTRACT_DEFECT": "KEEP_IN_CURRENT_CONTRACT",
            "MISSING_PREREQUISITE": "INSERT_PREREQUISITE",
            "NEW_RESPONSIBILITY": "CREATE_OWNED_SIBLING",
            "PROMOTE_TO_SUB_EPIC": "PROMOTE_TO_SUB_EPIC",
            "NON_BLOCKING_FOLLOWUP": "CREATE_OWNED_FOLLOWUP",
            "INVALID_FINDING": "REJECT_WITH_EVIDENCE",
        }
        for classification, action in expected.items():
            facts = finding(classification)
            if classification in {
                "IN_CONTRACT_DEFECT",
                "MISSING_PREREQUISITE",
                "PROMOTE_TO_SUB_EPIC",
            }:
                facts["technically_blocking"] = True
            if classification == "NON_BLOCKING_FOLLOWUP":
                facts["timing"] = "AFTER_FREEZE"
            with self.subTest(classification=classification):
                self.assertEqual(replanning.classify(facts).action, action)

    def test_blocking_facts_remain_independent(self):
        result = replanning.classify(
            finding(
                "NON_BLOCKING_FOLLOWUP",
                timing="AFTER_FREEZE",
                technically_blocking=False,
                mechanically_blocking=True,
                risk=["P3"],
            )
        )
        self.assertFalse(result.technically_blocking)
        self.assertTrue(result.mechanically_blocking)

    def test_pre_freeze_in_contract_defect_stays_in_current_contract_without_a_technical_blocker(self):
        for risk, mechanical in (("P3", True), ("INFORMATIONAL", False)):
            with self.subTest(risk=risk, mechanically_blocking=mechanical):
                result = replanning.validate_request(
                    {
                        "current_issue": key(2),
                        "finding": finding(
                            "IN_CONTRACT_DEFECT",
                            technically_blocking=False,
                            mechanically_blocking=mechanical,
                            risk=[risk],
                        ),
                        "operation": {"kind": "KEEP_IN_CURRENT_CONTRACT"},
                    }
                )
                self.assertEqual(result.action, "KEEP_IN_CURRENT_CONTRACT")
                self.assertFalse(result.technically_blocking)
                self.assertEqual(result.mechanically_blocking, mechanical)

    def test_rollout_prerequisite_does_not_become_a_technical_blocker(self):
        result = replanning.classify(
            finding(
                "MISSING_PREREQUISITE",
                technically_blocking=False,
                mechanically_blocking=True,
                risk=["P3"],
            )
        )
        self.assertEqual(result.action, "INSERT_PREREQUISITE")
        self.assertFalse(result.technically_blocking)
        self.assertTrue(result.mechanically_blocking)

    def test_promotion_requirement_does_not_become_a_technical_blocker(self):
        result = replanning.classify(
            finding(
                "PROMOTE_TO_SUB_EPIC",
                technically_blocking=False,
                mechanically_blocking=True,
                risk=["INFORMATIONAL"],
            )
        )
        self.assertEqual(result.action, "PROMOTE_TO_SUB_EPIC")
        self.assertFalse(result.technically_blocking)
        self.assertTrue(result.mechanically_blocking)

    def test_high_risk_findings_cannot_use_non_blocking_follow_up(self):
        for risk in ("P1", "P2", "SECURITY", "AUTHENTICATION", "INTEGRITY", "FAIL_OPEN"):
            with self.subTest(risk=risk), self.assertRaises(replanning.PlanError):
                replanning.classify(
                    finding(
                        "NON_BLOCKING_FOLLOWUP",
                        timing="AFTER_FREEZE",
                        risk=[risk],
                    )
                )

    def test_in_contract_defect_cannot_escape_to_a_follow_up_before_freeze(self):
        with self.assertRaisesRegex(replanning.PlanError, "current contract"):
            replanning.validate_request(
                {
                    "current_issue": key(2),
                    "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
                    "operation": {"kind": "CREATE_OWNED_FOLLOWUP"},
                }
            )

    def test_post_freeze_high_risk_defect_stays_in_current_contract(self):
        result = replanning.validate_request(
            {
                "current_issue": key(2),
                "finding": finding(
                    "IN_CONTRACT_DEFECT",
                    timing="AFTER_FREEZE",
                    technically_blocking=True,
                    mechanically_blocking=True,
                    risk=["P1", "INTEGRITY"],
                ),
                "operation": {"kind": "KEEP_IN_CURRENT_CONTRACT"},
            }
        )
        self.assertEqual(result.action, "KEEP_IN_CURRENT_CONTRACT")
        self.assertTrue(result.technically_blocking)


class PlanningTests(TestCase):
    def setUp(self):
        self.snapshot = graph(
            node(1, children=(key(2), key(9))),
            node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
            node(3, blocking=(key(2),)),
            node(8, blocked_by=(key(2),)),
            node(9, parent=key(1)),
        )

    def test_new_responsibility_is_owned_and_keeps_siblings_parallel(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Deliver separate work",
                    "body": "## Acceptance Criteria\n\n- Delivered independently.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        self.assertEqual(plan.owner, key(1))
        self.assertEqual(
            [step.kind for step in plan.steps],
            ["CREATE_ISSUE", "REPRIORITIZE_SUB_ISSUE"],
        )
        self.assertFalse(any(step.kind == "ADD_BLOCKED_BY" for step in plan.steps))
        self.assertEqual(plan.steps[1].arguments["after"], key(2))

    def test_post_freeze_follow_up_is_owned_without_a_technical_dependency(self):
        request = {
            "current_issue": key(2),
            "finding": finding(
                "NON_BLOCKING_FOLLOWUP",
                timing="AFTER_FREEZE",
                mechanically_blocking=True,
                risk=["INFORMATIONAL"],
            ),
            "operation": {
                "kind": "CREATE_OWNED_FOLLOWUP",
                "issue": {
                    "alias": "follow-up",
                    "repository": REPO,
                    "title": "Track later improvement",
                    "body": "## Acceptance Criteria\n\n- Improvement is delivered.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        self.assertEqual(plan.owner, key(1))
        self.assertNotIn("ADD_BLOCKED_BY", [step.kind for step in plan.steps])

    def test_existing_cross_repository_prerequisite_keeps_its_owner(self):
        prerequisite = model.Node(
            repository="SecPal/api",
            number=44,
            node_id="API_44",
            repository_id="API_REPO",
            has_acceptance_criteria=True,
            blocking_observable=True,
        )
        snapshot = model.build_snapshot((*self.snapshot.nodes.values(), prerequisite))
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "existing_issue": "SecPal/api#44",
                "move_current_blockers": [],
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        self.assertEqual([step.kind for step in plan.steps], ["ADD_BLOCKED_BY"])
        self.assertEqual(plan.steps[0].arguments["blocked"], key(2))
        self.assertEqual(plan.steps[0].arguments["blocker"], "SecPal/api#44")

    def test_new_prerequisite_for_root_leaf_creates_native_epic_first(self):
        snapshot = graph(node(2))
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "epic": {
                    "alias": "aggregate",
                    "repository": REPO,
                    "title": "Coordinate aggregate delivery",
                    "body": "## Acceptance Criteria\n\n- Both contracts are complete.\n",
                },
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Provide prerequisite",
                    "body": "## Acceptance Criteria\n\n- Output exists.\n",
                },
                "move_current_blockers": [],
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        self.assertEqual(plan.owner, "@aggregate")
        self.assertEqual(
            [step.kind for step in plan.steps],
            [
                "CREATE_ISSUE",
                "ADD_SUB_ISSUE",
                "CREATE_ISSUE",
                "REPRIORITIZE_SUB_ISSUE",
                "ADD_BLOCKED_BY",
            ],
        )
        self.assertIsNone(plan.steps[0].arguments["parent"])
        self.assertEqual(plan.steps[1].arguments["child"], key(2))

    def test_inserted_prerequisite_rewires_only_named_edges(self):
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Provide prerequisite",
                    "body": "## Acceptance Criteria\n\n- Required output exists.\n",
                },
                "move_current_blockers": [key(3)],
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        edges = [(step.kind, dict(step.arguments)) for step in plan.steps if "BLOCKED_BY" in step.kind]
        self.assertEqual(
            edges,
            [
                ("ADD_BLOCKED_BY", {"blocked": "@prerequisite", "blocker": key(3)}),
                ("ADD_BLOCKED_BY", {"blocked": key(2), "blocker": "@prerequisite"}),
                ("REMOVE_BLOCKED_BY", {"blocked": key(2), "blocker": key(3)}),
            ],
        )

    def test_planned_dependency_cycle_fails_before_mutation(self):
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "existing_issue": key(8),
                "move_current_blockers": [],
            },
        }
        with self.assertRaisesRegex(replanning.PlanError, "canonical structural"):
            replanning.build_plan(self.snapshot, request, actor="alice")

    def test_intermediate_native_dependency_limit_fails_before_mutation(self):
        dependents = tuple(key(number) for number in range(100, 149))
        snapshot = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1), blocked_by=(key(3),)),
            node(
                3,
                blocking=(key(2), *dependents),
                blocking_count=model.MAX_DEPENDENCIES_PER_TYPE,
            ),
            *(node(number, blocked_by=(key(3),)) for number in range(100, 149)),
        )
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Provide prerequisite",
                    "body": "## Acceptance Criteria\n\n- Required output exists.\n",
                },
                "move_current_blockers": [key(3)],
            },
        }
        with self.assertRaisesRegex(replanning.PlanError, "canonical structural"):
            replanning.build_plan(snapshot, request, actor="alice")

    def test_promotion_requires_exhaustive_edge_placement(self):
        incomplete = {
            "current_issue": key(2),
            "finding": finding("PROMOTE_TO_SUB_EPIC", technically_blocking=True),
            "operation": {
                "kind": "PROMOTE_TO_SUB_EPIC",
                "children": [],
                "blocked_by_placement": {},
                "blocking_placement": {},
            },
        }
        with self.assertRaisesRegex(replanning.PlanError, "every existing"):
            replanning.build_plan(self.snapshot, incomplete, actor="alice")

    def test_promotion_repoints_only_semantically_selected_edges(self):
        request = {
            "current_issue": key(2),
            "finding": finding("PROMOTE_TO_SUB_EPIC", technically_blocking=True),
            "operation": {
                "kind": "PROMOTE_TO_SUB_EPIC",
                "children": [
                    {
                        "alias": "contract-a",
                        "repository": REPO,
                        "title": "Contract A",
                        "body": "## Acceptance Criteria\n\n- A is delivered.\n",
                    },
                    {
                        "alias": "contract-b",
                        "repository": REPO,
                        "title": "Contract B",
                        "body": "## Acceptance Criteria\n\n- B is delivered.\n",
                    },
                ],
                "blocked_by_placement": {key(3): ["contract-a"]},
                "blocking_placement": {key(8): ["contract-b"]},
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        edges = [(step.kind, dict(step.arguments)) for step in plan.steps if "BLOCKED_BY" in step.kind]
        self.assertEqual(
            edges,
            [
                ("ADD_BLOCKED_BY", {"blocked": "@contract-a", "blocker": key(3)}),
                ("REMOVE_BLOCKED_BY", {"blocked": key(2), "blocker": key(3)}),
                ("ADD_BLOCKED_BY", {"blocked": key(8), "blocker": "@contract-b"}),
                ("REMOVE_BLOCKED_BY", {"blocked": key(8), "blocker": key(2)}),
            ],
        )
        self.assertNotIn("ADD_CHILD_DEPENDENCY", [step.kind for step in plan.steps])

    def test_snapshot_drift_fails_before_any_mutation(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        changed = graph(
            node(1, children=(key(9), key(2))),
            *[item for item in self.snapshot.nodes.values() if item.number != 1],
        )
        writer = replanning.RecordingWriter()
        with self.assertRaisesRegex(replanning.StalePlanError, "drift"):
            replanning.apply_plan(plan, changed, actor="alice", writer=writer)
        self.assertEqual(writer.calls, [])

    def test_post_mutation_verification_rejects_unrelated_relationship_changes(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        after = graph(
            node(1, children=(key(2), key(10), key(9))),
            node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
            node(3, blocking=(key(2),)),
            node(8, blocked_by=(key(2),)),
            # This unrelated node was re-parented during the operation.
            node(9, parent=None),
            node(10, parent=key(1)),
        )
        with self.assertRaisesRegex(replanning.PlanError, "unrelated"):
            replanning.verify_unchanged_relationships(
                plan,
                self.snapshot,
                after,
                {
                    "new-work": replanning.CreatedIssueIdentity(
                        key=key(10), node_id="ISSUE_10", repository_id="REPO_ID"
                    )
                },
            )

    def test_created_issue_is_verified_as_an_exact_postcondition(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        identity = replanning.CreatedIssueIdentity(
            key=key(10), node_id="ISSUE_10", repository_id="REPO_ID"
        )
        expected_body = replanning.created_issue_body(plan, 0)
        base_created = node(
            10,
            parent=key(1),
            title="Separate work",
            body_digest=replanning.content_digest(expected_body),
        )
        cases = {
            "content": node(
                10,
                parent=key(1),
                title="Separate work",
                body_digest=replanning.content_digest("changed"),
            ),
            "dependency": model.Node(
                **{
                    **base_created.__dict__,
                    "blocked_by": (key(3),),
                }
            ),
            "unobservable": model.Node(
                **{
                    **base_created.__dict__,
                    "dependencies_observable": False,
                }
            ),
        }
        for label, created in cases.items():
            after = graph(
                node(1, children=(key(2), key(10), key(9))),
                node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
                node(3, blocking=(key(2),)),
                node(8, blocked_by=(key(2),)),
                node(9, parent=key(1)),
                created,
            )
            with self.subTest(label=label), self.assertRaises(replanning.PlanError):
                replanning.verify_applied(plan, after, {"new-work": identity})


class MutationBoundaryTests(TestCase):
    class FakeAdapter:
        def __init__(self):
            self.calls = []
            self.next_issue = 10

        def query(self, document, variables):
            self.calls.append((document, variables))
            if "WorkGraphViewer" in document:
                return github.GraphQLResponse({"viewer": {"login": "alice"}}, ())
            if "ReplanCreateIssue" in document:
                number = self.next_issue
                self.next_issue += 1
                return github.GraphQLResponse(
                    {
                        "createIssue": {
                            "issue": {
                                "id": f"ISSUE_{number}",
                                "number": number,
                                "url": f"https://github.com/SecPal/.github/issues/{number}",
                                "repository": {"id": "REPO_ID", "nameWithOwner": REPO},
                                "parent": (
                                    {"id": variables["input"]["parentIssueId"]}
                                    if "parentIssueId" in variables["input"]
                                    else None
                                ),
                            }
                        }
                    },
                    (),
                )
            if "ReplanPrioritizeSubIssue" in document:
                return github.GraphQLResponse(
                    {
                        "reprioritizeSubIssue": {
                            "issue": {"id": variables["input"]["issueId"]}
                        }
                    },
                    (),
                )
            if "ReplanAddSubIssue" in document:
                value = variables["input"]
                return github.GraphQLResponse(
                    {
                        "addSubIssue": {
                            "issue": {"id": value["issueId"]},
                            "subIssue": {"id": value["subIssueId"]},
                        }
                    },
                    (),
                )
            if "ReplanAddBlockedBy" in document or "ReplanRemoveBlockedBy" in document:
                value = variables["input"]
                field = "addBlockedBy" if "ReplanAddBlockedBy" in document else "removeBlockedBy"
                return github.GraphQLResponse(
                    {
                        field: {
                            "issue": {"id": value["issueId"]},
                            "blockingIssue": {"id": value["blockingIssueId"]},
                        }
                    },
                    (),
                )
            raise AssertionError("unexpected mutation")

    def apply_with_recovery(self, plan, snapshot, adapter):
        with tempfile.TemporaryDirectory() as directory:
            return replanning.apply_plan(
                plan,
                snapshot,
                actor="alice",
                writer=github_replanning.GitHubMutationWriter(adapter),
                recovery=replanning.RecoveryJournal(
                    Path(directory) / "operation.json", plan, FakeRecoverySigner()
                ),
            )

    def test_writer_uses_only_the_compiled_native_mutations(self):
        snapshot = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1)),
        )
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = self.FakeAdapter()
        aliases = self.apply_with_recovery(plan, snapshot, adapter)
        self.assertEqual(aliases["new-work"].key, key(10))
        mutations = [call for call in adapter.calls if call[0].lstrip().startswith("mutation")]
        self.assertEqual(len(mutations), 2)
        self.assertIn("mutation ReplanCreateIssue", mutations[0][0])
        self.assertIn("mutation ReplanPrioritizeSubIssue", mutations[1][0])
        create_input = mutations[0][1]["input"]
        self.assertEqual(create_input["parentIssueId"], "ISSUE_1")
        self.assertNotIn("replaceParent", create_input)
        self.assertEqual(create_input["body"], request["operation"]["issue"]["body"])

    def test_root_prerequisite_path_creates_owner_and_native_edges(self):
        snapshot = graph(node(2))
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "epic": {
                    "alias": "aggregate",
                    "repository": REPO,
                    "title": "Aggregate",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Prerequisite",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "move_current_blockers": [],
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = self.FakeAdapter()
        aliases = self.apply_with_recovery(plan, snapshot, adapter)
        self.assertEqual(
            {alias: identity.key for alias, identity in aliases.items()},
            {"aggregate": key(10), "prerequisite": key(11)},
        )
        self.assertEqual(
            [
                next(name for name in (
                    "ReplanCreateIssue",
                    "ReplanAddSubIssue",
                    "ReplanPrioritizeSubIssue",
                    "ReplanAddBlockedBy",
                ) if name in document)
                for document, _ in adapter.calls
                if document.lstrip().startswith("mutation")
            ],
            [
                "ReplanCreateIssue",
                "ReplanAddSubIssue",
                "ReplanCreateIssue",
                "ReplanPrioritizeSubIssue",
                "ReplanAddBlockedBy",
            ],
        )
        first_mutation = next(call for call in adapter.calls if "ReplanCreateIssue" in call[0])
        self.assertNotIn("parentIssueId", first_mutation[1]["input"])

    def test_actor_is_reauthenticated_immediately_before_each_write(self):
        class ChangedActorAdapter(self.FakeAdapter):
            def query(self, document, variables):
                if "WorkGraphViewer" in document:
                    self.calls.append((document, variables))
                    return github.GraphQLResponse({"viewer": {"login": "mallory"}}, ())
                return super().query(document, variables)

        snapshot = graph(node(1, children=(key(2),)), node(2, parent=key(1)))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = ChangedActorAdapter()
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            with self.assertRaisesRegex(github_replanning.MutationError, "actor changed"):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(adapter),
                    recovery=journal,
                )
            self.assertEqual(journal.load()["outcome"], "NO_WRITES")
        self.assertFalse(any(call[0].lstrip().startswith("mutation") for call in adapter.calls))

    def test_partial_root_creation_is_recovered_without_duplicate_creation(self):
        class FailsSecondActorCheck(self.FakeAdapter):
            def __init__(self):
                super().__init__()
                self.viewer_reads = 0

            def query(self, document, variables):
                if "WorkGraphViewer" in document:
                    self.viewer_reads += 1
                    if self.viewer_reads == 2:
                        self.calls.append((document, variables))
                        return github.GraphQLResponse({"viewer": {"login": "mallory"}}, ())
                return super().query(document, variables)

        snapshot = graph(node(2))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "epic": {
                    "alias": "aggregate",
                    "repository": REPO,
                    "title": "Aggregate",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            adapter = FailsSecondActorCheck()
            with self.assertRaises(github_replanning.MutationError):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(adapter),
                    recovery=journal,
                )
            evidence = journal.load()
            self.assertEqual(evidence["outcome"], "KNOWN_WRITES")
            self.assertEqual(evidence["next_step"], 1)
            self.assertEqual(evidence["created"]["aggregate"]["key"], key(10))

            with self.assertRaisesRegex(replanning.StalePlanError, "recovery"):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(self.FakeAdapter()),
                    recovery=journal,
                )

            recovered = replanning.recovery_identities(evidence)
            created_epic = node(
                10,
                title="Aggregate",
                body_digest=replanning.content_digest(replanning.created_issue_body(plan, 0)),
            )
            recovery_snapshot = graph(node(2), created_epic)
            replanning.verify_applied(plan, recovery_snapshot, recovered, step_limit=1)
            replanning.verify_unchanged_relationships(
                plan, snapshot, recovery_snapshot, recovered, step_limit=1
            )

            resumed_adapter = self.FakeAdapter()
            resumed_adapter.next_issue = 11
            completed = replanning.apply_plan(
                plan,
                snapshot,
                actor="alice",
                writer=github_replanning.GitHubMutationWriter(resumed_adapter),
                recovery=journal,
                resume=True,
            )
            self.assertEqual(completed["aggregate"].key, key(10))
            create_mutations = [
                call for call in resumed_adapter.calls if "ReplanCreateIssue" in call[0]
            ]
            self.assertEqual(len(create_mutations), 1)
            self.assertEqual(journal.load()["outcome"], "COMPLETE")

            tampered = journal.load()
            tampered.pop("journal_digest")
            tampered.pop("authentication")
            tampered["created"]["aggregate"]["node_id"] = "ISSUE_999"
            tampered["journal_digest"] = replanning.recovery_document_digest(tampered)
            tampered["authentication"] = {
                "kind": "test-signature",
                "value": "signed:stale",
            }
            journal.path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(replanning.StalePlanError, "authentication"):
                journal.load()

    def test_unknown_mutation_outcome_is_retained_and_never_resumed(self):
        class UnknownCreateAdapter(self.FakeAdapter):
            def query(self, document, variables):
                if "ReplanCreateIssue" in document:
                    self.calls.append((document, variables))
                    return github.GraphQLResponse(None, ({"message": "unknown"},))
                return super().query(document, variables)

        snapshot = graph(node(1, children=(key(2),)), node(2, parent=key(1)))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            with self.assertRaises(github_replanning.MutationError):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(UnknownCreateAdapter()),
                    recovery=journal,
                )
            self.assertEqual(journal.load()["outcome"], "UNKNOWN_MUTATION_OUTCOME")
            with self.assertRaisesRegex(replanning.StalePlanError, "unknown mutation outcome"):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(self.FakeAdapter()),
                    recovery=journal,
                    resume=True,
                )


if __name__ == "__main__":
    main()
