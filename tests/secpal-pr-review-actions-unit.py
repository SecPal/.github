#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase, main, mock
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIONS_HELPER = REPO_ROOT / "scripts/secpal-pr-review-actions.py"
P21_TESTS = REPO_ROOT / "tests/secpal-pr-review-unit.py"
FIXTURES = REPO_ROOT / "tests/fixtures/secpal-pr-review-actions"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


actions = load_module("secpal_pr_review_actions", ACTIONS_HELPER)
p21 = load_module("secpal_pr_review_p21_tests", P21_TESTS)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evidence_snapshot() -> dict[str, Any]:
    value = p21.snapshot()
    value["review_threads"] = [p21.thread()]
    return p21.finalize_snapshot(value)


def repository_config() -> dict[str, Any]:
    value = p21.config()
    value["reviewer_identities"] = []
    return value


def base_session() -> dict[str, Any]:
    return {
        "state": "WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION",
        "state_captures": 3,
        "remediation_cycles": 1,
        "holistic_audits": 1,
        "signed_commits": 1,
        "fast_forward_pushes": 1,
        "evidence_replies": 0,
        "reaction_writes": 0,
        "thread_resolutions": 0,
        "worktree_clean": True,
        "head_matches": True,
        "snapshot_digest_matches": True,
        "unexplained_commit": False,
        "signatures_valid": True,
        "evidence_complete": True,
        "ci_state": "SUCCESS",
        "unresolved_material_finding": False,
        "github_state_safe": True,
        "scope_requires_other_repository": False,
        "late_feedback_detected": False,
        "push_failed": False,
        "mutation_failed": False,
        "actionable_findings": True,
        "merge_ready_evidence": True,
    }


def complete_resolution_evidence() -> dict[str, bool]:
    return {
        "local_verified": True,
        "final_evidence_verified": True,
        "no_late_feedback": True,
        "all_threads_classified": True,
        "manual_gates_verified": True,
        "registered_validation_verified": True,
    }


def finding(
    finding_id: str = "finding-001",
    classification: str = "VALID_ACTIONABLE",
    *,
    thread_id: str | None = "THREAD_1",
    disposition: str = "CORRECTED_AND_VERIFIED",
) -> dict[str, Any]:
    return {
        "logical_finding_id": finding_id,
        "source_node_ids": ["RC_1"],
        "source_subitem_id": None,
        "source_database_ids": [21],
        "parent_thread_id": thread_id,
        "classification": classification,
        "canonical_finding_id": None,
        "disposition": disposition,
        "evidence_digest": digest(finding_id),
        "test_evidence": ["tests pass"],
        "commit_sha": p21.HEAD,
    }


def operation(
    kind: str = "REACTION",
    *,
    operation_id: str = "reaction-001",
    classification: str = "VALID_ACTIONABLE",
    reaction: str | None = "THUMBS_UP",
    reply_body: str | None = None,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "logical_finding_id": "finding-001",
        "kind": kind,
        "target_node_id": "RC_1" if kind != "THREAD_RESOLUTION" else "THREAD_1",
        "target_database_id": 21 if kind != "THREAD_RESOLUTION" else None,
        "parent_thread_id": "THREAD_1",
        "expected_current_state": {
            "target_type": "PULL_REQUEST_REVIEW_COMMENT"
            if kind != "THREAD_RESOLUTION"
            else "PULL_REQUEST_REVIEW_THREAD",
            "body_digest": digest("Finding") if kind != "THREAD_RESOLUTION" else None,
            "is_resolved": False,
            "is_outdated": False,
            "material_misunderstanding": kind == "EVIDENCE_REPLY",
            "invalidity_non_obvious": kind == "EVIDENCE_REPLY",
        },
        "expected_actor_identity": {
            "login": "aroviqen",
            "node_id": "USER_1",
            "database_id": 7,
        },
        "expected_source_actor_identity": {
            "login": "reviewer",
            "node_id": "ACTOR_reviewer",
            "database_id": 7,
        },
        "classification": classification,
        "evidence_digest": digest("finding-001"),
        "reaction": reaction,
        "reply_body": reply_body,
        "applied_mutation_identity": None,
        "resolution_preconditions": {
            "pushed": True,
            "focused_validation_succeeded": True,
            "complete_validation_succeeded": True,
            "required_ci_succeeded": True,
            "valid_signatures": True,
            "heads_match": True,
            "worktree_clean": True,
            "no_late_feedback": True,
            "all_thread_findings_disposed": True,
        }
        if kind == "THREAD_RESOLUTION"
        else None,
    }


def plan(*operations: dict[str, Any], current_state: str = "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES") -> dict[str, Any]:
    snapshot = evidence_snapshot()
    session = base_session()
    session["state"] = current_state
    if current_state == "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES":
        session.update(
            {
                "state_captures": 1,
                "remediation_cycles": 0,
                "holistic_audits": 0,
                "signed_commits": 0,
                "fast_forward_pushes": 0,
            }
        )
    registered = actions.select_repository(actions.load_registry(), "SecPal/.github")
    manual_gate_evidence = [
        {
            "gate": gate,
            "status": "SATISFIED",
            "evidence": ["verified by the unit-test fixture"],
        }
        for gate in registered["manual_gates"]
    ]
    return {
        "schema_version": "1.0",
        "repository": "SecPal/.github",
        "pull_request_number": 1,
        "snapshot_digest": snapshot["snapshot_digest"],
        "initial_snapshot_digest": snapshot["snapshot_digest"],
        "expected_head_sha": p21.HEAD,
        "created_for_state": current_state,
        "cycle_number": session["remediation_cycles"],
        "session": session,
        "findings": [finding()],
        "manual_gate_evidence": (
            manual_gate_evidence
            if current_state == "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE"
            else []
        ),
        "operations": list(operations),
    }


def registry_entry(repository: str) -> dict[str, Any]:
    return {
        "repository": repository,
        "default_branch": "main",
        "allowed_base_repositories": [repository],
        "reviewer_identities": [],
        "focused_validation": [
            {"argv": ["npm", "run", "test"], "working_directory": ".", "purpose": "Run tests"}
        ],
        "required_local_validation": [
            {"argv": ["npm", "run", "lint"], "working_directory": ".", "purpose": "Run lint"}
        ],
        "signature_policy": repository_config()["signature_policy"],
        "check_policy": repository_config()["check_policy"],
        "manual_gates": ["Confirm any environment-dependent validation with the user."],
        "unsupported_operations": list(actions.PROHIBITED_OPERATION_KINDS),
        "maximum_api_calls": 200,
        "maximum_items": 10000,
        "maximum_threads": 500,
        "maximum_comments": 200,
        "maximum_reactions": 50,
    }


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = False
        self.state = {
            "head_sha": p21.HEAD,
            "pr_state": "OPEN",
            "actor": {"login": "reviewer", "node_id": "ACTOR_reviewer", "database_id": 7},
            "viewer": {"login": "aroviqen", "node_id": "USER_1", "database_id": 7},
            "target": {
                "node_id": "RC_1",
                "database_id": 21,
                "parent_thread_id": "THREAD_1",
                "target_type": "PULL_REQUEST_REVIEW_COMMENT",
                "url": "https://github.com/SecPal/.github/pull/1#discussion_r1",
                "body_digest": digest("Finding"),
                "is_resolved": False,
                "is_outdated": False,
                "reply_to_database_id": None,
                "reactions": [],
                "replies": [],
                "thread_comments": [
                    {
                        "node_id": "RC_1",
                        "body_digest": digest("Finding"),
                        "actor": {
                            "login": "reviewer",
                            "node_id": "ACTOR_reviewer",
                            "database_id": 7,
                        },
                        "reply_to_id": None,
                        "reactions": [],
                    }
                ],
            },
        }

    def read_current_state(self, _plan: dict[str, Any], _operation: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("READ", "current-state"))
        return copy.deepcopy(self.state)

    def verify_current_required_checks(
        self,
        _plan: dict[str, Any],
        _snapshot: dict[str, Any],
        _configuration: dict[str, Any],
    ) -> None:
        self.calls.append(("READ", "required-checks"))

    def apply_reaction(self, _plan: dict[str, Any], operation_value: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("WRITE", "REACTION"))
        if self.fail:
            raise actions.MutationFailure("reaction failed")
        return {"mutation_id": "REACTION_NEW", "content": operation_value["reaction"]}

    def apply_reply(self, _plan: dict[str, Any], _operation: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("WRITE", "EVIDENCE_REPLY"))
        if self.fail:
            raise actions.MutationFailure("reply failed")
        return {"mutation_id": "REPLY_NEW"}

    def apply_resolution(self, _plan: dict[str, Any], _operation: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("WRITE", "THREAD_RESOLUTION"))
        if self.fail:
            raise actions.MutationFailure("resolution failed")
        return {"mutation_id": "THREAD_1", "is_resolved": True}


class ContractTests(TestCase):
    def test_classification_fixture_covers_exact_taxonomy_and_cases_1_to_16(self) -> None:
        fixture = json.loads((FIXTURES / "classification-cases.json").read_text(encoding="utf-8"))
        self.assertEqual([case["number"] for case in fixture["cases"]], list(range(1, 17)))
        observed = {classification for case in fixture["cases"] for classification in case["classifications"]}
        self.assertEqual(observed, set(actions.CLASSIFICATIONS))

    def test_state_fixture_covers_cases_17_to_38_and_terminal_rules(self) -> None:
        fixture = json.loads((FIXTURES / "state-machine-cases.json").read_text(encoding="utf-8"))
        self.assertEqual([case["number"] for case in fixture["cases"]], list(range(17, 39)))
        for case in fixture["cases"]:
            session = base_session()
            session.update(case["overrides"])
            with self.subTest(case=case["number"]):
                self.assertEqual(actions.determine_terminal_outcome(session), case["expected"])

    def test_no_actionable_session_finishes_without_required_ci_success(self) -> None:
        session = base_session()
        session.update(
            {
                "state_captures": 1,
                "remediation_cycles": 0,
                "holistic_audits": 0,
                "signed_commits": 0,
                "fast_forward_pushes": 0,
                "ci_state": "PENDING",
                "actionable_findings": False,
                "merge_ready_evidence": False,
            }
        )
        self.assertEqual(actions.determine_terminal_outcome(session), "NO_ACTIONABLE_FINDINGS")

    def test_exact_finite_counters_are_enforced(self) -> None:
        limits = {
            "remediation_cycles": 2,
            "state_captures": 3,
            "holistic_audits": 1,
            "signed_commits": 2,
            "fast_forward_pushes": 2,
            "evidence_replies": 10,
        }
        self.assertEqual(actions.SESSION_LIMITS, limits)
        for key, maximum in limits.items():
            session = base_session()
            session[key] = maximum + 1
            with self.subTest(counter=key), self.assertRaises(actions.PlanError):
                actions.validate_session_state(session)

    def test_session_state_is_closed_and_bound_to_the_plan_phase(self) -> None:
        schema = json.loads(actions.PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            tuple(schema["$defs"]["session"]["properties"]["state"]["enum"]),
            actions.SESSION_STATES,
        )
        session = base_session()
        session["state"] = "UNRECOGNIZED_PHASE"
        with self.assertRaisesRegex(actions.PlanError, "finite workflow state"):
            actions.validate_session_state(session)

        rolled_back = base_session()
        rolled_back["state"] = "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES"
        with self.assertRaisesRegex(actions.PlanError, "counter state"):
            actions.validate_session_state(rolled_back)

        for kind, required_state in (
            ("REACTION", "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES"),
            ("EVIDENCE_REPLY", "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES"),
            ("THREAD_RESOLUTION", "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE"),
        ):
            operation_value = operation(
                kind,
                operation_id=f"{kind.lower()}-001",
                classification=(
                    "INVALID_FALSE_OR_MISLEADING"
                    if kind == "EVIDENCE_REPLY"
                    else "VALID_ACTIONABLE"
                ),
                reaction=None if kind != "REACTION" else "THUMBS_UP",
                reply_body="Independent evidence" if kind == "EVIDENCE_REPLY" else None,
            )
            value = plan(operation_value, current_state=required_state)
            if kind == "EVIDENCE_REPLY":
                value["findings"][0].update(
                    {
                        "classification": "INVALID_FALSE_OR_MISLEADING",
                        "disposition": "DISPROVEN_WITH_EVIDENCE",
                    }
                )
            wrong_state = (
                "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES"
                if required_state == "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE"
                else "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE"
            )
            changed = copy.deepcopy(value)
            changed["session"]["state"] = wrong_state
            if wrong_state == "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES":
                changed["session"].update(
                    state_captures=1,
                    remediation_cycles=0,
                    holistic_audits=0,
                    signed_commits=0,
                    fast_forward_pushes=0,
                )
            else:
                changed["session"].update(
                    state_captures=3,
                    remediation_cycles=1,
                    holistic_audits=1,
                    signed_commits=1,
                    fast_forward_pushes=1,
                )
            with self.subTest(kind=kind, mismatch="session"), self.assertRaisesRegex(
                actions.PlanError, "creation state"
            ):
                actions.validate_plan(changed, evidence_snapshot(), repository_config())
            changed = copy.deepcopy(value)
            changed["created_for_state"] = wrong_state
            changed["session"]["state"] = changed["created_for_state"]
            if wrong_state == "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES":
                changed["session"].update(
                    state_captures=1,
                    remediation_cycles=0,
                    holistic_audits=0,
                    signed_commits=0,
                    fast_forward_pushes=0,
                )
            else:
                changed["session"].update(
                    state_captures=3,
                    remediation_cycles=1,
                    holistic_audits=1,
                    signed_commits=1,
                    fast_forward_pushes=1,
                )
            with self.subTest(kind=kind, mismatch="operation"), self.assertRaisesRegex(
                actions.PlanError, "operation phase"
            ):
                actions.validate_plan(changed, evidence_snapshot(), repository_config())

        classification = plan()
        classification["session"]["state"] = "CLASSIFY_ALL_SNAPSHOT_ITEMS"
        self.assertEqual(
            actions.validate_plan(classification, evidence_snapshot(), repository_config())[
                "session"
            ]["state"],
            "CLASSIFY_ALL_SNAPSHOT_ITEMS",
        )

    def test_plan_is_deterministic_and_bound_to_p21_snapshot(self) -> None:
        value = plan(operation())
        normalized = actions.validate_plan(value, evidence_snapshot(), repository_config())
        self.assertEqual(actions.canonical_json_bytes(normalized), actions.canonical_json_bytes(normalized))
        changed = copy.deepcopy(value)
        changed["snapshot_digest"] = "0" * 64
        with self.assertRaisesRegex(actions.PlanError, "snapshot digest"):
            actions.validate_plan(changed, evidence_snapshot(), repository_config())
        changed = copy.deepcopy(value)
        changed["expected_head_sha"] = "f" * 40
        with self.assertRaisesRegex(actions.PlanError, "head"):
            actions.validate_plan(changed, evidence_snapshot(), repository_config())
        changed = copy.deepcopy(value)
        changed["findings"][0]["source_node_ids"] = ["MISSING_SOURCE"]
        with self.assertRaisesRegex(actions.PlanError, "source node"):
            actions.validate_plan(changed, evidence_snapshot(), repository_config())

    def test_operation_evidence_is_bound_to_its_logical_finding(self) -> None:
        value = plan(operation())
        value["operations"][0]["evidence_digest"] = digest("unrelated evidence")

        with self.assertRaisesRegex(actions.PlanError, "operation evidence"):
            actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_plan_requires_the_registered_repository_configuration(self) -> None:
        unregistered_identities = p21.config()
        with self.assertRaisesRegex(actions.PlanError, "registry"):
            actions.validate_plan(
                plan(operation()), evidence_snapshot(), unregistered_identities
            )

        weakened = copy.deepcopy(repository_config())
        weakened["signature_policy"]["require_github_verified"] = False
        with self.assertRaisesRegex(actions.PlanError, "registry"):
            actions.validate_plan(plan(operation()), evidence_snapshot(), weakened)

        repository = "OutsideOrg/not-registered"
        snapshot = evidence_snapshot()
        snapshot["repository"].update(
            {
                "owner": "OutsideOrg",
                "name": "not-registered",
                "name_with_owner": repository,
                "url": f"https://github.com/{repository}",
            }
        )
        for key in ("base_repository", "head_repository"):
            snapshot["pull_request"][key].update(
                {
                    "name_with_owner": repository,
                    "url": f"https://github.com/{repository}",
                }
            )
        snapshot["pull_request"]["url"] = f"https://github.com/{repository}/pull/1"
        snapshot = p21.finalize_snapshot(snapshot)
        configuration = copy.deepcopy(repository_config())
        configuration["repository"] = repository
        configuration["allowed_base_repositories"] = [repository]
        value = plan(operation())
        value["repository"] = repository
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        with self.assertRaisesRegex(actions.PlanError, "registry"):
            actions.validate_plan(value, snapshot, configuration)

    def test_plan_rejects_structurally_valid_but_blocked_p21_evidence(self) -> None:
        snapshot = evidence_snapshot()
        snapshot["commits"][0]["github_signature"].update(
            {"state": "invalid", "verified": False, "reason": "bad_signature"}
        )
        snapshot = p21.finalize_snapshot(snapshot)
        value = plan(operation())
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        with self.assertRaisesRegex(actions.PlanError, "evidence verification"):
            actions.validate_plan(value, snapshot, repository_config())

    def test_plan_accepts_a_deleted_source_actor_without_weakening_writer_identity(self) -> None:
        snapshot = evidence_snapshot()
        snapshot["review_threads"][0]["comments"][0]["author"] = p21.actor(None)
        snapshot = p21.finalize_snapshot(snapshot)
        value = plan(operation())
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        value["operations"][0]["expected_source_actor_identity"] = {
            "login": None,
            "node_id": None,
            "database_id": None,
        }
        normalized = actions.validate_plan(value, snapshot, repository_config())
        self.assertEqual(
            normalized["operations"][0]["expected_source_actor_identity"]["login"],
            None,
        )
        self.assertEqual(normalized["operations"][0]["expected_actor_identity"]["login"], "aroviqen")

    def test_operations_bind_to_their_finding_and_immutable_snapshot_state(self) -> None:
        second_comment = p21.review_comment("RC_2", body="Independent finding")
        second_comment["database_id"] = 22
        snapshot = evidence_snapshot()
        snapshot["review_threads"].append(
            p21.thread("THREAD_2", comments=[second_comment])
        )
        snapshot = p21.finalize_snapshot(snapshot)

        cross_target = plan(operation())
        cross_target["snapshot_digest"] = snapshot["snapshot_digest"]
        cross_target["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        cross_target["operations"][0].update(
            {
                "target_node_id": "RC_2",
                "target_database_id": 22,
                "parent_thread_id": "THREAD_2",
            }
        )
        cross_target["operations"][0]["expected_current_state"]["body_digest"] = digest(
            "Independent finding"
        )
        with self.assertRaisesRegex(actions.PlanError, "logical finding"):
            actions.validate_plan(cross_target, snapshot, repository_config())

        edited_state = plan(operation())
        edited_state["operations"][0]["expected_current_state"]["body_digest"] = digest(
            "Edited after immutable snapshot"
        )
        with self.assertRaisesRegex(actions.PlanError, "snapshot state"):
            actions.validate_plan(edited_state, evidence_snapshot(), repository_config())

        changed_thread_state = plan(operation())
        changed_thread_state["operations"][0]["expected_current_state"]["is_resolved"] = True
        with self.assertRaisesRegex(actions.PlanError, "snapshot state"):
            actions.validate_plan(changed_thread_state, evidence_snapshot(), repository_config())

    def test_each_source_item_has_exactly_one_independent_classification(self) -> None:
        value = plan(operation())
        value["findings"].append(
            finding("finding-002", "INFORMATIONAL", disposition="NON_ACTIONABLE")
        )
        with self.assertRaisesRegex(actions.PlanError, "source sub-item"):
            actions.validate_plan(value, evidence_snapshot(), repository_config())

        folded = plan(operation())
        folded["findings"][0]["source_node_ids"].append("REACTION_1")
        with self.assertRaisesRegex(actions.PlanError, "source item"):
            actions.validate_plan(folded, evidence_snapshot(), repository_config())

    def test_apply_phase_requires_classification_coverage_for_every_snapshot_source(self) -> None:
        snapshot = evidence_snapshot()
        second_comment = p21.review_comment("RC_2", body="Second finding")
        second_comment["database_id"] = 22
        snapshot["review_threads"][0]["comments"].append(second_comment)
        snapshot = p21.finalize_snapshot(snapshot)
        value = plan(operation())
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]

        with self.assertRaisesRegex(actions.PlanError, "classification coverage"):
            actions.validate_plan(value, snapshot, repository_config())

    def test_resolution_coverage_allows_exact_recorded_policy_writes(self) -> None:
        initial = evidence_snapshot()
        writer = p21.actor("aroviqen")
        writer_identity = {
            key: writer[key] for key in ("login", "node_id", "database_id")
        }

        reaction_snapshot = copy.deepcopy(initial)
        own_reaction = p21.reaction("REACTION_OWN", "THUMBS_UP")
        own_reaction["user"] = writer
        reaction_snapshot["review_threads"][0]["comments"][0]["reactions"] = [
            own_reaction
        ]
        reaction_snapshot = p21.finalize_snapshot(reaction_snapshot)
        recorded_reaction = operation()
        recorded_reaction["applied_mutation_identity"] = "REACTION_OWN"
        recorded_reaction["expected_actor_identity"] = writer_identity
        reaction_plan = plan(
            recorded_reaction,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        reaction_plan["snapshot_digest"] = reaction_snapshot["snapshot_digest"]
        reaction_plan["initial_snapshot_digest"] = initial["snapshot_digest"]
        reaction_plan["session"]["reaction_writes"] = 1

        self.assertEqual(
            actions.validate_plan(
                reaction_plan, reaction_snapshot, repository_config()
            ),
            reaction_plan,
        )
        self.assertTrue(
            actions._all_initial_threads_classified(reaction_plan, initial)
        )

        reply_snapshot = copy.deepcopy(initial)
        own_reply = p21.review_comment(
            "REPLY_OWN", login="aroviqen", body="Independent evidence"
        )
        own_reply["database_id"] = 22
        own_reply["reply_to_id"] = "RC_1"
        reply_snapshot["review_threads"][0]["comments"].append(own_reply)
        reply_snapshot = p21.finalize_snapshot(reply_snapshot)
        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["applied_mutation_identity"] = "REPLY_OWN"
        recorded_reply["expected_actor_identity"] = writer_identity
        reply_plan = plan(
            recorded_reply,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        reply_plan["snapshot_digest"] = reply_snapshot["snapshot_digest"]
        reply_plan["initial_snapshot_digest"] = initial["snapshot_digest"]
        reply_plan["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        reply_plan["session"]["evidence_replies"] = 1

        self.assertEqual(
            actions.validate_plan(reply_plan, reply_snapshot, repository_config()),
            reply_plan,
        )
        self.assertTrue(actions._all_initial_threads_classified(reply_plan, initial))

    def test_resolution_coverage_rejects_forged_recorded_policy_writes(self) -> None:
        initial = evidence_snapshot()
        final = copy.deepcopy(initial)
        late_reply = p21.review_comment(
            "REPLY_LATE", login="reviewer", body="Late feedback"
        )
        late_reply["database_id"] = 22
        late_reply["reply_to_id"] = "RC_1"
        final["review_threads"][0]["comments"].append(late_reply)
        final = p21.finalize_snapshot(final)
        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["applied_mutation_identity"] = "REPLY_LATE"
        value = plan(
            recorded_reply,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["snapshot_digest"] = final["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        value["session"]["evidence_replies"] = 1

        with self.assertRaisesRegex(actions.PlanError, "recorded policy write"):
            actions.validate_plan(value, final, repository_config())

    def test_compound_source_supports_unique_stable_subitem_classifications(self) -> None:
        first = finding()
        first["source_subitem_id"] = "runtime-behavior"
        second = finding(
            "finding-002",
            "INFORMATIONAL",
            disposition="NON_ACTIONABLE",
        )
        second["source_subitem_id"] = "documentation-context"
        value = plan()
        value["findings"] = [first, second]

        normalized = actions.validate_plan(value, evidence_snapshot(), repository_config())
        self.assertEqual(
            [item["source_subitem_id"] for item in normalized["findings"]],
            ["runtime-behavior", "documentation-context"],
        )

        empty = copy.deepcopy(value)
        empty["findings"][0]["source_subitem_id"] = ""
        with self.assertRaisesRegex(actions.PlanError, "Schema string"):
            actions.validate_plan(empty, evidence_snapshot(), repository_config())

        duplicate = copy.deepcopy(value)
        duplicate["findings"][1]["source_subitem_id"] = "runtime-behavior"
        with self.assertRaisesRegex(actions.PlanError, "sub-item"):
            actions.validate_plan(duplicate, evidence_snapshot(), repository_config())

        mixed = copy.deepcopy(value)
        mixed["findings"][1]["source_subitem_id"] = None
        with self.assertRaisesRegex(actions.PlanError, "sub-item"):
            actions.validate_plan(mixed, evidence_snapshot(), repository_config())

    def test_duplicate_findings_require_a_canonical_root(self) -> None:
        value = plan(operation())
        value["findings"] = [finding(classification="DUPLICATE", disposition="DUPLICATE_OF_CANONICAL")]
        with self.assertRaisesRegex(actions.PlanError, "canonical"):
            actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_duplicate_and_superseded_canonical_references_must_be_acyclic(self) -> None:
        for classification, disposition in (
            ("DUPLICATE", "DUPLICATE_OF_CANONICAL"),
            ("SUPERSEDED", "SUPERSEDED_BY_CANONICAL"),
        ):
            first = finding("finding-001", classification, disposition=disposition)
            second = finding("finding-002", classification, disposition=disposition)
            second["source_node_ids"] = ["RC_2"]
            second["source_database_ids"] = [22]
            first["canonical_finding_id"] = "finding-002"
            second["canonical_finding_id"] = "finding-001"
            value = plan()
            value["findings"] = [first, second]
            with self.subTest(classification=classification), self.assertRaisesRegex(
                actions.PlanError, "canonical.*cycle"
            ):
                actions._validate_finding_semantics(value["findings"])

    def test_actionable_fixed_dispositions_require_commit_and_test_proof(self) -> None:
        for classification, disposition in (
            ("VALID_ACTIONABLE", "CORRECTED_AND_VERIFIED"),
            ("VALID_ACTIONABLE", "PROVEN_EXISTING_FIX"),
            ("OUTDATED_BUT_STILL_VALID", "CORRECTED_AND_VERIFIED"),
            ("OUTDATED_BUT_STILL_VALID", "PROVEN_EXISTING_FIX"),
        ):
            value = plan()
            value["findings"] = [
                finding(classification=classification, disposition=disposition)
            ]
            value["findings"][0]["commit_sha"] = None
            value["findings"][0]["test_evidence"] = []
            with self.subTest(
                classification=classification, disposition=disposition
            ), self.assertRaisesRegex(actions.PlanError, "commit and test evidence"):
                actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_disallowed_operation_kinds_and_capabilities_are_rejected(self) -> None:
        self.assertEqual(set(actions.ALLOWED_OPERATION_KINDS), {"REACTION", "EVIDENCE_REPLY", "THREAD_RESOLUTION"})

        non_reactable = plan(operation(classification="INFORMATIONAL", reaction=None))
        non_reactable["findings"][0].update(
            {"classification": "INFORMATIONAL", "disposition": "NON_ACTIONABLE"}
        )
        with self.assertRaisesRegex(actions.PlanError, "reaction"):
            actions.validate_plan(non_reactable, evidence_snapshot(), repository_config())
        prohibited = {
            "REVIEW_REQUEST", "READY_TRANSITION", "LABEL", "ISSUE", "REVIEW_SUBMISSION",
            "MERGE", "AUTO_MERGE", "COMMENT_DELETE", "REVIEW_DISMISSAL", "BRANCH_WRITE",
        }
        self.assertEqual(set(actions.PROHIBITED_OPERATION_KINDS), prohibited)
        value = plan(operation())
        value["operations"][0]["kind"] = "MERGE"
        with self.assertRaises(actions.PlanError):
            actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_reaction_reply_and_resolution_semantics_are_fail_closed(self) -> None:
        cases = [
            ("INFORMATIONAL", "REACTION", "THUMBS_UP", None),
            ("INVALID_FALSE_OR_MISLEADING", "REACTION", "THUMBS_UP", None),
            ("VALID_ACTIONABLE", "REACTION", "THUMBS_DOWN", None),
            ("AMBIGUOUS_NEEDS_USER_DECISION", "EVIDENCE_REPLY", None, "Evidence"),
        ]
        for classification, kind, reaction_value, body in cases:
            value = plan(operation(kind, classification=classification, reaction=reaction_value, reply_body=body))
            value["findings"][0]["classification"] = classification
            with self.subTest(classification=classification, kind=kind), self.assertRaises(actions.PlanError):
                actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_review_summary_findings_use_the_allowlisted_reactable_type(self) -> None:
        snapshot = evidence_snapshot()
        review = p21.review_record()
        snapshot["reviews"] = [review]
        snapshot = p21.finalize_snapshot(snapshot)
        value = plan(operation())
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        value["findings"][0]["source_node_ids"] = [review["id"]]
        value["findings"][0]["source_database_ids"] = [review["database_id"]]
        value["findings"][0]["parent_thread_id"] = None
        value["findings"].append(
            finding("finding-002", "INFORMATIONAL", disposition="NON_ACTIONABLE")
        )
        value["operations"][0]["target_node_id"] = review["id"]
        value["operations"][0]["target_database_id"] = review["database_id"]
        value["operations"][0]["parent_thread_id"] = None
        value["operations"][0]["expected_current_state"]["target_type"] = "PULL_REQUEST_REVIEW"
        value["operations"][0]["expected_current_state"]["body_digest"] = digest(review["body"])
        value["operations"][0]["expected_current_state"]["is_resolved"] = None
        normalized = actions.validate_plan(value, snapshot, repository_config())
        self.assertEqual(
            normalized["operations"][0]["expected_current_state"]["target_type"],
            "PULL_REQUEST_REVIEW",
        )

    def test_issue_comment_reactions_accept_the_canonical_issue_url(self) -> None:
        snapshot = evidence_snapshot()
        conversation = {
            "id": "CONVERSATION_1",
            "database_id": 12,
            "author": p21.actor("reviewer"),
            "body": "Top-level review feedback",
            "url": "https://github.com/SecPal/.github/issues/1#issuecomment-12",
            "created_at": "2026-07-19T00:00:00Z",
            "updated_at": "2026-07-19T00:00:00Z",
            "reactions": [],
        }
        snapshot["conversation_comments"] = [conversation]
        snapshot = p21.finalize_snapshot(snapshot)
        reaction = operation()
        reaction.update(
            {
                "target_node_id": conversation["id"],
                "target_database_id": conversation["database_id"],
                "parent_thread_id": None,
            }
        )
        reaction["expected_current_state"].update(
            {
                "target_type": "ISSUE_COMMENT",
                "body_digest": digest(conversation["body"]),
                "is_resolved": None,
                "is_outdated": False,
            }
        )
        value = plan(reaction)
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        value["findings"][0].update(
            {
                "source_node_ids": [conversation["id"]],
                "source_database_ids": [conversation["database_id"]],
                "parent_thread_id": None,
            }
        )
        value["findings"].append(
            finding("finding-002", "INFORMATIONAL", disposition="NON_ACTIONABLE")
        )
        normalized = actions.validate_plan(value, snapshot, repository_config())
        self.assertEqual(
            normalized["operations"][0]["expected_current_state"]["target_type"],
            "ISSUE_COMMENT",
        )

    def test_fixed_or_status_replies_are_refused(self) -> None:
        for body in (
            "fixed",
            "Addressed.",
            f"Fixed in {p21.HEAD}",
            f"Fixed in {p21.HEAD}: focused checks pass.",
            "status: complete",
        ):
            op = operation(
                "EVIDENCE_REPLY",
                operation_id="reply-001",
                classification="INVALID_FALSE_OR_MISLEADING",
                reaction=None,
                reply_body=body,
            )
            value = plan(op)
            value["findings"][0]["classification"] = "INVALID_FALSE_OR_MISLEADING"
            value["findings"][0]["disposition"] = "DISPROVEN_WITH_EVIDENCE"
            with self.subTest(body=body), self.assertRaisesRegex(actions.PlanError, "status reply"):
                actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_at_most_one_reaction_per_initial_finding_and_ten_replies_total(self) -> None:
        value = plan(operation(), operation(operation_id="reaction-002"))
        with self.assertRaisesRegex(actions.PlanError, "reaction"):
            actions.validate_plan(value, evidence_snapshot(), repository_config())
        replies = []
        findings = []
        for index in range(11):
            finding_id = f"finding-{index:03d}"
            op = operation(
                "EVIDENCE_REPLY",
                operation_id=f"reply-{index:03d}",
                classification="INVALID_FALSE_OR_MISLEADING",
                reaction=None,
                reply_body=f"Independent evidence {index}",
            )
            op["logical_finding_id"] = finding_id
            replies.append(op)
            item = finding(
                finding_id,
                "INVALID_FALSE_OR_MISLEADING",
                disposition="DISPROVEN_WITH_EVIDENCE",
            )
            item["source_node_ids"] = [f"RC_{index}"]
            item["source_database_ids"] = [index + 1]
            op["evidence_digest"] = item["evidence_digest"]
            findings.append(item)
        value = plan(*replies)
        value["findings"] = findings
        with self.assertRaisesRegex(actions.PlanError, "evidence repl"):
            actions._validate_operation_semantics(
                value, actions._validate_finding_semantics(value["findings"])
            )

    def test_consumed_counters_reserve_capacity_for_pending_operations(self) -> None:
        reaction = plan(operation())
        reaction["session"]["reaction_writes"] = 1

        reply_operation = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        reply = plan(reply_operation)
        reply["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        reply["session"]["evidence_replies"] = 10

        resolution = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        resolution["session"]["thread_resolutions"] = 1

        for name, value in (
            ("reaction", reaction),
            ("reply", reply),
            ("resolution", resolution),
        ):
            with self.subTest(kind=name), self.assertRaisesRegex(actions.PlanError, "counter"):
                actions.validate_plan(value, evidence_snapshot(), repository_config())

    def test_resolution_push_precondition_matches_remediation_history(self) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            classification="INFORMATIONAL",
            reaction=None,
        )
        resolution["resolution_preconditions"]["pushed"] = False
        value = plan(
            resolution,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["cycle_number"] = 0
        value["session"].update(
            remediation_cycles=0,
            signed_commits=0,
            fast_forward_pushes=0,
        )
        value["findings"][0].update(
            classification="INFORMATIONAL",
            disposition="NON_ACTIONABLE",
            commit_sha=None,
            test_evidence=[],
        )

        self.assertEqual(
            actions.validate_plan(value, evidence_snapshot(), repository_config()),
            value,
        )

        false_push_claim = copy.deepcopy(value)
        false_push_claim["operations"][0]["resolution_preconditions"]["pushed"] = True
        with self.assertRaisesRegex(actions.PlanError, "pushed precondition"):
            actions.validate_plan(
                false_push_claim, evidence_snapshot(), repository_config()
            )

    def test_recorded_mutation_identity_belongs_to_only_one_operation(self) -> None:
        recorded_reaction = operation()
        recorded_reaction["applied_mutation_identity"] = "MUTATION_SHARED"
        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-002",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["logical_finding_id"] = "finding-002"
        recorded_reply["applied_mutation_identity"] = "MUTATION_SHARED"
        second_finding = finding(
            "finding-002",
            "INVALID_FALSE_OR_MISLEADING",
            disposition="DISPROVEN_WITH_EVIDENCE",
        )
        second_finding["source_node_ids"] = ["RC_2"]
        second_finding["source_database_ids"] = [22]
        recorded_reply["evidence_digest"] = second_finding["evidence_digest"]
        value = plan(recorded_reaction, recorded_reply)
        value["findings"].append(second_finding)
        value["session"]["reaction_writes"] = 1
        value["session"]["evidence_replies"] = 1

        with self.assertRaisesRegex(actions.PlanError, "mutation identity"):
            actions._validate_operation_semantics(
                value, actions._validate_finding_semantics(value["findings"])
            )


class MutationTests(TestCase):
    def apply(self, value: dict[str, Any], operation_id: str, github: FakeGitHub, *, apply: bool = True) -> dict[str, Any]:
        snapshot = evidence_snapshot()
        return actions.execute_operation(
            value,
            operation_id,
            snapshot,
            repository_config(),
            github,
            apply=apply,
            resolution_evidence=None,
            current_feedback={
                "feedback": actions._snapshot_review_feedback(snapshot, value)
            }
            if apply
            else None,
        )

    def test_mutation_fixture_covers_cases_39_to_60(self) -> None:
        fixture = json.loads((FIXTURES / "mutation-cases.json").read_text(encoding="utf-8"))
        self.assertEqual([case["number"] for case in fixture["cases"]], list(range(39, 61)))

    def test_apply_flag_is_required_and_default_mode_has_zero_writes(self) -> None:
        github = FakeGitHub()
        result = self.apply(plan(operation()), "reaction-001", github, apply=False)
        self.assertEqual(result["status"], "VALIDATED_NO_MUTATION")
        self.assertEqual(github.calls, [("READ", "current-state")])

    def test_valid_thumbs_up_and_down_reactions_apply_once(self) -> None:
        for reaction_value in ("THUMBS_UP", "THUMBS_DOWN"):
            github = FakeGitHub()
            classification = "VALID_ACTIONABLE" if reaction_value == "THUMBS_UP" else "INVALID_FALSE_OR_MISLEADING"
            op = operation(classification=classification, reaction=reaction_value)
            value = plan(op)
            value["findings"][0]["classification"] = classification
            if classification != "VALID_ACTIONABLE":
                value["findings"][0]["disposition"] = "DISPROVEN_WITH_EVIDENCE"
            result = self.apply(value, "reaction-001", github)
            self.assertEqual(result["status"], "APPLIED")
            self.assertEqual(github.calls.count(("WRITE", "REACTION")), 1)

    def test_existing_actor_reaction_is_idempotent(self) -> None:
        github = FakeGitHub()
        existing = {
            "mutation_id": "REACTION_EXISTING",
            "content": "THUMBS_UP",
            "actor": copy.deepcopy(github.state["viewer"]),
        }
        github.state["target"]["reactions"] = [existing]
        github.state["target"]["thread_comments"][0]["reactions"] = [
            copy.deepcopy(existing)
        ]
        result = self.apply(plan(operation()), "reaction-001", github)
        self.assertEqual(result["status"], "ALREADY_APPLIED")
        self.assertNotIn(("WRITE", "REACTION"), github.calls)

    def test_intended_inline_reaction_does_not_hide_an_additional_late_reaction(self) -> None:
        github = FakeGitHub()
        intended = {
            "mutation_id": "REACTION_EXISTING",
            "content": "THUMBS_UP",
            "actor": copy.deepcopy(github.state["viewer"]),
        }
        late = {
            "mutation_id": "REACTION_LATE",
            "content": "THUMBS_DOWN",
            "actor": {
                "login": "late-reviewer",
                "node_id": "ACTOR_late",
                "database_id": 19,
            },
        }
        github.state["target"]["reactions"] = [intended, late]
        github.state["target"]["thread_comments"][0]["reactions"] = copy.deepcopy(
            github.state["target"]["reactions"]
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "feedback changed"):
            self.apply(plan(operation()), "reaction-001", github)
        self.assertNotIn(("WRITE", "REACTION"), github.calls)

    def test_top_level_reaction_requires_the_complete_snapshot_reaction_set(self) -> None:
        snapshot = evidence_snapshot()
        review = p21.review_record()
        snapshot["reviews"] = [review]
        snapshot = p21.finalize_snapshot(snapshot)
        op = operation()
        op.update(
            {
                "target_node_id": review["id"],
                "target_database_id": review["database_id"],
                "parent_thread_id": None,
            }
        )
        op["expected_current_state"].update(
            {
                "target_type": "PULL_REQUEST_REVIEW",
                "body_digest": digest(review["body"]),
                "is_resolved": None,
            }
        )
        value = plan(op)
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        value["findings"][0].update(
            {
                "source_node_ids": [review["id"]],
                "source_database_ids": [review["database_id"]],
                "parent_thread_id": None,
            }
        )
        value["findings"].append(
            finding("finding-002", "INFORMATIONAL", disposition="NON_ACTIONABLE")
        )
        github = FakeGitHub()
        github.state["target"].update(
            {
                "node_id": review["id"],
                "database_id": review["database_id"],
                "parent_thread_id": None,
                "target_type": "PULL_REQUEST_REVIEW",
                "url": review["url"],
                "body_digest": digest(review["body"]),
                "is_resolved": None,
                "reactions": [
                    {
                        "mutation_id": "REACTION_LATE",
                        "content": "THUMBS_DOWN",
                        "actor": {
                            "login": "late-reviewer",
                            "node_id": "ACTOR_late",
                            "database_id": 19,
                        },
                    }
                ],
            }
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "target reactions changed"):
            actions.execute_operation(
                value,
                "reaction-001",
                snapshot,
                repository_config(),
                github,
                apply=True,
                resolution_evidence=None,
            )
        self.assertNotIn(("WRITE", "REACTION"), github.calls)

        github.state["target"]["reactions"] = [
            {
                "mutation_id": "REACTION_EXISTING",
                "content": "THUMBS_UP",
                "actor": copy.deepcopy(github.state["viewer"]),
            }
        ]
        result = actions.execute_operation(
            value,
            "reaction-001",
            snapshot,
            repository_config(),
            github,
            apply=True,
            resolution_evidence=None,
        )
        self.assertEqual(result["status"], "ALREADY_APPLIED")
        self.assertNotIn(("WRITE", "REACTION"), github.calls)

    def test_non_obvious_invalid_evidence_reply_applies_once_and_duplicate_is_refused(self) -> None:
        op = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="The cited path is not executed; the focused regression proves the branch is unreachable.",
        )
        value = plan(op)
        value["findings"][0]["classification"] = "INVALID_FALSE_OR_MISLEADING"
        value["findings"][0]["disposition"] = "DISPROVEN_WITH_EVIDENCE"
        github = FakeGitHub()
        self.assertEqual(self.apply(value, "reply-001", github)["status"], "APPLIED")
        github = FakeGitHub()
        github.state["target"]["replies"] = [
            {
                "mutation_id": "REPLY_EXISTING",
                "body": op["reply_body"],
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_database_id": 21,
            }
        ]
        github.state["target"]["thread_comments"].append(
            {
                "node_id": "REPLY_EXISTING",
                "body_digest": digest(op["reply_body"]),
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_id": "RC_1",
                "reactions": [],
            }
        )
        self.assertEqual(self.apply(value, "reply-001", github)["status"], "ALREADY_APPLIED")
        self.assertNotIn(("WRITE", "EVIDENCE_REPLY"), github.calls)

    def test_duplicate_reply_must_match_the_exact_parent_comment(self) -> None:
        op = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        value = plan(op)
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        github = FakeGitHub()
        github.state["target"]["replies"] = [
            {
                "mutation_id": "REPLY_ON_OTHER_PARENT",
                "body": op["reply_body"],
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_database_id": 999,
            }
        ]
        self.assertEqual(self.apply(value, "reply-001", github)["status"], "APPLIED")
        self.assertEqual(github.calls.count(("WRITE", "EVIDENCE_REPLY")), 1)

    def test_retained_reply_verification_requires_the_exact_parent_comment(self) -> None:
        op = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        op["applied_mutation_identity"] = "REPLY_EXISTING"
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        value["session"]["evidence_replies"] = 1
        github = FakeGitHub()
        github.state["target"]["replies"] = [
            {
                "mutation_id": "REPLY_EXISTING",
                "body": op["reply_body"],
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_database_id": 999,
            }
        ]
        with self.assertRaisesRegex(actions.MutationBlocked, "feedback changed"):
            actions._verify_retained_mutations(
                value,
                evidence_snapshot(),
                github,
            )

        github.state["target"]["replies"][0]["reply_to_database_id"] = 21
        github.state["target"]["thread_comments"].append(
            {
                "node_id": "REPLY_EXISTING",
                "body_digest": digest(op["reply_body"]),
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_id": "RC_1",
                "reactions": [],
            }
        )
        self.assertEqual(
            actions._verify_retained_mutations(
                value,
                evidence_snapshot(),
                github,
            ),
            {"REPLY_EXISTING"},
        )

    def test_retained_mutations_include_sibling_writes_in_the_same_thread(self) -> None:
        recorded_reaction = operation()
        recorded_reaction["applied_mutation_identity"] = "REACTION_RECORDED"
        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-002",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["logical_finding_id"] = "finding-002"
        recorded_reply["evidence_digest"] = digest("finding-002")
        recorded_reply["applied_mutation_identity"] = "REPLY_RECORDED"
        value = plan(
            recorded_reaction,
            recorded_reply,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["findings"].append(
            finding(
                "finding-002",
                "INVALID_FALSE_OR_MISLEADING",
                disposition="DISPROVEN_WITH_EVIDENCE",
            )
        )
        value["session"]["reaction_writes"] = 1
        value["session"]["evidence_replies"] = 1
        github = FakeGitHub()
        recorded_reaction_state = {
            "mutation_id": "REACTION_RECORDED",
            "content": "THUMBS_UP",
            "actor": copy.deepcopy(github.state["viewer"]),
        }
        github.state["target"]["reactions"] = [recorded_reaction_state]
        github.state["target"]["replies"] = [
            {
                "mutation_id": "REPLY_RECORDED",
                "body": "Independent evidence",
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_database_id": 21,
            }
        ]
        github.state["target"]["thread_comments"] = [
            {
                **github.state["target"]["thread_comments"][0],
                "reactions": [copy.deepcopy(recorded_reaction_state)],
            },
            {
                "node_id": "REPLY_RECORDED",
                "body_digest": digest("Independent evidence"),
                "actor": copy.deepcopy(github.state["viewer"]),
                "reply_to_id": "RC_1",
                "reactions": [],
            },
        ]
        self.assertEqual(
            actions._verify_retained_mutations(
                value,
                evidence_snapshot(),
                github,
            ),
            {"REACTION_RECORDED", "REPLY_RECORDED"},
        )

    def test_retained_thread_resolution_is_verified_against_live_state(self) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            reaction=None,
        )
        resolution["applied_mutation_identity"] = "THREAD_1"
        value = plan(
            resolution,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["session"]["thread_resolutions"] = 1
        github = FakeGitHub()
        github.state["target"].update(
            {
                "node_id": "THREAD_1",
                "database_id": None,
                "target_type": "PULL_REQUEST_REVIEW_THREAD",
                "body_digest": None,
                "is_resolved": True,
            }
        )
        self.assertEqual(
            actions._verify_retained_mutations(value, evidence_snapshot(), github),
            {"THREAD_1"},
        )

        github.state["target"]["is_resolved"] = False
        with self.assertRaisesRegex(actions.MutationBlocked, "retained mutation identity"):
            actions._verify_retained_mutations(value, evidence_snapshot(), github)

    def test_evidence_reply_rejects_a_snapshot_reply_as_its_parent(self) -> None:
        snapshot = evidence_snapshot()
        snapshot["review_threads"][0]["comments"][0]["reply_to_id"] = "RC_PARENT"
        snapshot = p21.finalize_snapshot(snapshot)
        op = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        value = plan(op)
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        with self.assertRaisesRegex(actions.PlanError, "top-level review comment"):
            actions.validate_plan(value, snapshot, repository_config())

    def test_live_evidence_reply_rejects_a_reply_target(self) -> None:
        op = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        value = plan(op)
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        github = FakeGitHub()
        github.state["target"]["reply_to_database_id"] = 20
        with self.assertRaisesRegex(actions.MutationBlocked, "top-level review comment"):
            self.apply(value, "reply-001", github)
        self.assertNotIn(("WRITE", "EVIDENCE_REPLY"), github.calls)

    def test_changed_head_actor_or_target_identity_is_refused(self) -> None:
        mutations = (
            ("head_sha", "f" * 40),
            ("actor.login", "intruder"),
            ("viewer.login", "intruder"),
            ("target.node_id", "CHANGED"),
            ("target.url", "https://github.com/SecPal/.github/pull/2#discussion_r1"),
        )
        for path, replacement in mutations:
            github = FakeGitHub()
            parent, key = (github.state, path) if "." not in path else (github.state[path.split(".")[0]], path.split(".")[1])
            parent[key] = replacement
            with self.subTest(path=path), self.assertRaises(actions.MutationBlocked):
                self.apply(plan(operation()), "reaction-001", github)
            self.assertFalse(any(call[0] == "WRITE" for call in github.calls))

    def test_closed_pr_and_changed_thread_state_are_refused_before_a_write(self) -> None:
        github = FakeGitHub()
        github.state["pr_state"] = "CLOSED"
        with self.assertRaises(actions.MutationBlocked):
            self.apply(plan(operation()), "reaction-001", github)
        self.assertFalse(any(call[0] == "WRITE" for call in github.calls))

        reply_operation = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        reply = plan(reply_operation)
        reply["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        github = FakeGitHub()
        github.state["target"]["is_resolved"] = True
        with self.assertRaises(actions.MutationBlocked):
            self.apply(reply, "reply-001", github)
        self.assertFalse(any(call[0] == "WRITE" for call in github.calls))

    def test_recorded_mutation_identity_requires_matching_live_state(self) -> None:
        value = plan(operation())
        value["operations"][0]["applied_mutation_identity"] = "REACTION_NEW"
        value["session"]["reaction_writes"] = 1
        github = FakeGitHub()
        with self.assertRaises(actions.MutationBlocked):
            self.apply(value, "reaction-001", github)
        self.assertEqual(github.calls, [("READ", "current-state")])

        github = FakeGitHub()
        github.state["target"]["reactions"] = [
            {
                "mutation_id": "REACTION_NEW",
                "content": "THUMBS_UP",
                "actor": copy.deepcopy(github.state["viewer"]),
            }
        ]
        github.state["target"]["thread_comments"][0]["reactions"] = copy.deepcopy(
            github.state["target"]["reactions"]
        )
        result = self.apply(value, "reaction-001", github)
        self.assertEqual(result["status"], "ALREADY_APPLIED_RECORDED")
        self.assertEqual(result["mutation_identity"], "REACTION_NEW")
        self.assertEqual(github.calls, [("READ", "current-state")])

    def test_mutation_failure_is_terminal_without_retry(self) -> None:
        github = FakeGitHub()
        github.fail = True
        with self.assertRaises(actions.MutationFailure):
            self.apply(plan(operation()), "reaction-001", github)
        self.assertEqual(github.calls.count(("WRITE", "REACTION")), 1)

    def test_exact_command_allowlist_rejects_generic_or_extended_api_shapes(self) -> None:
        query = actions._graphql_arguments(
            actions.CURRENT_MUTATION_TARGET_QUERY,
            {
                "owner": "SecPal",
                "name": ".github",
                "number": 1,
                "targetNodeId": "RC_1",
                "threadNodeId": "THREAD_1",
            },
        )
        actions._validate_action_command(query)
        feedback_query = actions._graphql_arguments(
            actions.CURRENT_REVIEW_FEEDBACK_QUERY,
            {"owner": "SecPal", "name": ".github", "number": 1},
        )
        actions._validate_action_command(feedback_query)
        feedback_page = actions._graphql_arguments(
            actions.CURRENT_REVIEW_FEEDBACK_QUERY,
            {
                "owner": "SecPal",
                "name": ".github",
                "number": 1,
                "threadsCursor": "THREAD_CURSOR_1",
            },
        )
        actions._validate_action_command(feedback_page)
        checks_query = actions._graphql_arguments(
            actions.CURRENT_REQUIRED_CHECKS_QUERY,
            {
                "owner": "SecPal",
                "name": ".github",
                "number": 1,
                "oid": p21.HEAD,
                "after": "CHECK_CURSOR_1",
            },
        )
        actions._validate_action_command(checks_query)
        rules = [
            "gh", "api", "--hostname", "github.com",
            "repos/SecPal/.github/rules/branches/main?per_page=100&page=1",
            "--method", "GET",
        ]
        protection = [
            "gh", "api", "--hostname", "github.com",
            "repos/SecPal/.github/branches/main/protection/required_status_checks",
            "--method", "GET",
        ]
        actions._validate_action_command(rules)
        actions._validate_action_command(protection)
        add_reaction = actions._graphql_arguments(
            actions.ADD_REACTION_MUTATION,
            {"subjectId": "REVIEW_1", "content": "THUMBS_UP"},
        )
        actions._validate_action_command(add_reaction)
        reaction = [
            "gh", "api", "--hostname", "github.com",
            "repos/SecPal/.github/pulls/comments/21/reactions",
            "--method", "POST", "--header", "Accept: application/vnd.github+json",
            "-f", "content=+1",
        ]
        actions._validate_action_command(reaction)
        reply = [
            "gh", "api", "--hostname", "github.com",
            "repos/SecPal/.github/pulls/1/comments",
            "--method", "POST", "-f", "body=@must-not-read-from-disk",
            "-F", "in_reply_to=21",
        ]
        actions._validate_action_command(reply)
        for unsafe in (
            ["gh", "api", "--hostname", "github.com", "repos/SecPal/.github/issues"],
            [*reaction, "--input", "payload.json"],
            [*query, "-f", "extra=value"],
            [*feedback_page, "-f", "extra=value"],
            [*checks_query, "-f", "extra=value"],
            [*rules, "--paginate"],
            [*reply[:7], "-F", *reply[8:]],
        ):
            with self.subTest(arguments=unsafe), self.assertRaises(actions.MutationBlocked):
                actions._validate_action_command(unsafe)

    def test_live_required_checks_revalidate_rules_target_and_outcomes(self) -> None:
        snapshot = evidence_snapshot()

        def runner(
            *,
            conclusion: str = "SUCCESS",
            rules_strict: bool = True,
            malformed_rules: bool = False,
            base_ref: str = "main",
            fail_checks_after_rules: bool = False,
            change_check_projection: bool = False,
            change_rules_projection: bool = False,
        ) -> SimpleNamespace:
            rules_read = False
            rules_reads = 0
            head_reads = 0

            def run(arguments: list[str]) -> Any:
                nonlocal head_reads, rules_read, rules_reads
                endpoint = arguments[4]
                if "/rules/branches/" in endpoint:
                    rules_read = True
                    rules_reads += 1
                    current_rules_strict = (
                        False
                        if change_rules_projection and rules_reads >= 2
                        else rules_strict
                    )
                    return [
                        {
                            "type": "required_status_checks",
                            "parameters": {
                                "required_status_checks": [
                                    {"context": "tests", "integration_id": "invalid"},
                                    {"context": "other", "integration_id": 1},
                                ],
                                "strict_required_status_checks_policy": current_rules_strict,
                            }
                        }
                    ] if malformed_rules else [
                        {
                            "type": "required_status_checks",
                            "parameters": {
                                "required_status_checks": [
                                    {"context": "tests", "integration_id": 1}
                                ],
                                "strict_required_status_checks_policy": current_rules_strict,
                            },
                        }
                    ]
                if endpoint.endswith("/protection/required_status_checks"):
                    return {
                        "strict": True,
                        "contexts": ["tests"],
                        "checks": [{"context": "tests", "app_id": 1}],
                    }
                variables = {
                    assignment.split("=", 1)[0]: assignment.split("=", 1)[1]
                    for assignment in arguments[8::2]
                }
                oid = variables["oid"]
                nodes = []
                if oid == p21.HEAD:
                    head_reads += 1
                    nodes = [
                        {
                            "__typename": "CheckRun",
                            "id": "CHECK_1",
                            "name": "tests",
                            "status": "COMPLETED",
                            "conclusion": (
                                "FAILURE"
                                if (fail_checks_after_rules and rules_read)
                                or (change_check_projection and head_reads >= 2)
                                else conclusion
                            ),
                            "startedAt": "2026-07-19T00:00:00Z",
                            "detailsUrl": "https://github.com/SecPal/.github/actions/runs/1",
                            "checkSuite": {
                                "app": {
                                    "id": "APP_1",
                                    "databaseId": 1,
                                    "name": "Actions",
                                    "slug": "github-actions",
                                }
                            },
                        }
                    ]
                return {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "id": "PR_1",
                                "headRefOid": p21.HEAD,
                                "state": "OPEN",
                                "potentialMergeCommit": {"oid": p21.MERGE},
                                "baseRefName": base_ref,
                                "baseRefOid": p21.BASE,
                                "baseRepository": {
                                    "id": "REPO_1",
                                    "nameWithOwner": "SecPal/.github",
                                },
                            },
                            "object": {
                                "statusCheckRollup": {
                                    "contexts": {
                                        "nodes": nodes,
                                        "pageInfo": {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    }
                                }
                            },
                        }
                    }
                }

            return SimpleNamespace(run=run)

        actions.LiveGitHub(runner()).verify_current_required_checks(
            plan(), snapshot, repository_config()
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "no longer successful"):
            actions.LiveGitHub(runner(conclusion="FAILURE")).verify_current_required_checks(
                plan(), snapshot, repository_config()
            )
        with self.assertRaisesRegex(actions.MutationBlocked, "no longer successful"):
            actions.LiveGitHub(
                runner(fail_checks_after_rules=True)
            ).verify_current_required_checks(plan(), snapshot, repository_config())
        with self.assertRaisesRegex(actions.MutationBlocked, "checks changed"):
            actions.LiveGitHub(
                runner(change_check_projection=True)
            ).verify_current_required_checks(plan(), snapshot, repository_config())
        with self.assertRaisesRegex(actions.MutationBlocked, "rules changed"):
            actions.LiveGitHub(
                runner(change_rules_projection=True)
            ).verify_current_required_checks(plan(), snapshot, repository_config())
        with self.assertRaisesRegex(actions.MutationBlocked, "rules changed"):
            actions.LiveGitHub(runner(rules_strict=False)).verify_current_required_checks(
                plan(), snapshot, repository_config()
            )
        with self.assertRaisesRegex(actions.MutationBlocked, "target changed"):
            actions.LiveGitHub(runner(base_ref="release")).verify_current_required_checks(
                plan(), snapshot, repository_config()
            )
        merge_snapshot = copy.deepcopy(snapshot)
        merge_snapshot["pull_request"]["check_commit_oid"] = p21.MERGE
        merge_snapshot["pull_request"]["check_commit_source"] = "test_merge"
        merge_snapshot = p21.finalize_snapshot(merge_snapshot)
        with self.assertRaisesRegex(actions.MutationBlocked, "target changed"):
            actions.LiveGitHub(runner()).verify_current_required_checks(
                plan(), merge_snapshot, repository_config()
            )
        with self.assertRaisesRegex(actions.MutationBlocked, "rules are incomplete"):
            actions.LiveGitHub(runner(malformed_rules=True)).verify_current_required_checks(
                plan(), snapshot, repository_config()
            )
        failed_runner = SimpleNamespace(
            run=mock.Mock(
                side_effect=actions.ActionCommandFailure(
                    ["gh", "api"], 1, "", "read failed"
                )
            )
        )
        with self.assertRaises(actions.MutationFailure):
            actions.LiveGitHub(failed_runner).verify_current_required_checks(
                plan(), snapshot, repository_config()
            )

    def test_current_target_query_uses_concrete_actor_identity_fragments(self) -> None:
        query = actions.CURRENT_MUTATION_TARGET_QUERY
        self.assertNotIn("author { id databaseId login }", query)
        self.assertIn("replyTo { databaseId }", query)
        self.assertRegex(
            query,
            r"(?s)comments\(first:100\).*reactions\(first:100\).*pageInfo \{ hasNextPage \}",
        )
        for actor_type in ("User", "Bot", "Organization", "Mannequin"):
            self.assertIn(f"... on {actor_type} {{ id databaseId }}", query)

    def test_pr_wide_query_stays_below_githubs_possible_node_limit(self) -> None:
        query = actions.CURRENT_REVIEW_FEEDBACK_QUERY
        self.assertRegex(
            query,
            r"(?s)reviewThreads\(first:100, after:\$threadsCursor\).*comments\(first:100\).*reactions\(first:25\)",
        )
        self.assertNotRegex(
            query,
            r"(?s)reviewThreads\(first:100\).*comments\(first:100\).*reactions\(first:100\)",
        )

    def test_live_thread_comment_reactions_are_normalized_and_bounded(self) -> None:
        actor = {"id": "ACTOR_reviewer", "databaseId": 7, "login": "reviewer"}
        payload = {
            "data": {
                "viewer": {"id": "USER_1", "databaseId": 7, "login": "aroviqen"},
                "repository": {
                    "pullRequest": {"id": "PR_1", "headRefOid": p21.HEAD, "state": "OPEN"}
                },
                "node": {
                    "__typename": "PullRequestReviewComment",
                    "id": "RC_1",
                    "databaseId": 21,
                    "body": "Finding",
                    "url": "https://github.com/SecPal/.github/pull/1#discussion_r1",
                    "replyTo": None,
                    "author": actor,
                    "reactions": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                },
                "thread": {
                    "id": "THREAD_1",
                    "isResolved": False,
                    "isOutdated": False,
                    "comments": {
                        "nodes": [
                            {
                                "id": "RC_1",
                                "databaseId": 21,
                                "body": "Finding",
                                "url": "https://github.com/SecPal/.github/pull/1#discussion_r1",
                                "replyTo": None,
                                "author": actor,
                                "reactions": {
                                    "nodes": [
                                        {
                                            "id": "REACTION_1",
                                            "databaseId": 41,
                                            "content": "THUMBS_UP",
                                            "user": actor,
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False},
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False},
                    },
                },
            }
        }
        runner = SimpleNamespace(run=lambda _arguments: copy.deepcopy(payload))
        github = actions.LiveGitHub(runner)
        current = github.read_current_state(plan(operation()), operation())
        self.assertEqual(
            current["target"]["thread_comments"][0]["reactions"][0]["mutation_id"],
            "REACTION_1",
        )

        payload["data"]["thread"]["comments"]["nodes"][0]["reactions"]["pageInfo"][
            "hasNextPage"
        ] = True
        with self.assertRaisesRegex(actions.MutationBlocked, "thread reactions exceed"):
            github.read_current_state(plan(operation()), operation())

    def test_live_resolution_target_does_not_require_a_reaction_connection(self) -> None:
        actor = {"id": "ACTOR_reviewer", "databaseId": 7, "login": "reviewer"}
        thread = {
            "id": "THREAD_1",
            "isResolved": False,
            "isOutdated": False,
            "comments": {
                "nodes": [
                    {
                        "id": "RC_1",
                        "databaseId": 21,
                        "body": "Finding",
                        "url": "https://github.com/SecPal/.github/pull/1#discussion_r1",
                        "replyTo": None,
                        "author": actor,
                        "reactions": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False},
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            },
        }
        payload = {
            "data": {
                "viewer": {"id": "USER_1", "databaseId": 7, "login": "aroviqen"},
                "repository": {
                    "pullRequest": {
                        "id": "PR_1",
                        "headRefOid": p21.HEAD,
                        "state": "OPEN",
                    }
                },
                "node": {
                    "__typename": "PullRequestReviewThread",
                    "id": "THREAD_1",
                    "isResolved": False,
                    "isOutdated": False,
                },
                "thread": thread,
            }
        }
        github = actions.LiveGitHub(
            SimpleNamespace(run=lambda _arguments: copy.deepcopy(payload))
        )
        resolution = operation(
            "THREAD_RESOLUTION", operation_id="resolve-001", reaction=None
        )
        current = github.read_current_state(
            plan(
                resolution,
                current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
            ),
            resolution,
        )
        self.assertEqual(current["target"]["reactions"], [])
        self.assertEqual(current["target"]["thread_comments"][0]["node_id"], "RC_1")

    def test_live_pr_wide_feedback_is_normalized_and_bounded(self) -> None:
        actor = {"id": "ACTOR_reviewer", "databaseId": 7, "login": "reviewer"}
        empty = {"nodes": [], "pageInfo": {"hasNextPage": False}}
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "id": "PR_1",
                        "headRefOid": p21.HEAD,
                        "state": "OPEN",
                        "reactions": copy.deepcopy(empty),
                        "reviews": copy.deepcopy(empty),
                        "comments": copy.deepcopy(empty),
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "THREAD_1",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "RC_1",
                                                "databaseId": 21,
                                                "body": "Finding",
                                                "author": actor,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "id": "REACTION_1",
                                                            "databaseId": 41,
                                                            "content": "THUMBS_UP",
                                                            "user": actor,
                                                        }
                                                    ],
                                                    "pageInfo": {"hasNextPage": False},
                                                },
                                            }
                                        ],
                                        "pageInfo": {"hasNextPage": False},
                                    },
                                }
                            ],
                            "pageInfo": {"hasNextPage": False},
                        },
                    }
                }
            }
        }
        runner = SimpleNamespace(run=lambda _arguments: copy.deepcopy(payload))
        github = actions.LiveGitHub(runner)
        current = github.read_current_feedback(plan())
        self.assertEqual(
            current["feedback"]["threads"][0]["comments"][0]["reactions"][0][
                "mutation_id"
            ],
            "REACTION_1",
        )

        payload["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"][
            "hasNextPage"
        ] = True
        payload["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"][
            "endCursor"
        ] = "THREAD_CURSOR_1"
        second_page = copy.deepcopy(payload)
        second_thread = second_page["data"]["repository"]["pullRequest"][
            "reviewThreads"
        ]
        second_thread["nodes"][0]["id"] = "THREAD_2"
        second_thread["nodes"][0]["comments"]["nodes"][0]["id"] = "RC_2"
        second_thread["pageInfo"] = {
            "hasNextPage": False,
            "endCursor": "THREAD_CURSOR_2",
        }
        calls: list[list[str]] = []

        def next_page(arguments: list[str]) -> dict[str, Any]:
            calls.append(arguments)
            if any(item == "threadsCursor=THREAD_CURSOR_1" for item in arguments):
                return copy.deepcopy(second_page)
            return copy.deepcopy(payload)

        github = actions.LiveGitHub(
            SimpleNamespace(run=next_page)
        )
        current = github.read_current_feedback(plan())
        self.assertEqual(
            [item["node_id"] for item in current["feedback"]["threads"]],
            ["THREAD_1", "THREAD_2"],
        )
        self.assertNotIn("threadsCursor=THREAD_CURSOR_1", calls[0])
        self.assertIn("threadsCursor=THREAD_CURSOR_1", calls[1])

        changed_second_page = copy.deepcopy(second_page)
        changed_second_page["data"]["repository"]["pullRequest"]["reactions"] = {
            "nodes": [
                {
                    "id": "REACTION_LATE",
                    "databaseId": 42,
                    "content": "THUMBS_DOWN",
                    "user": actor,
                }
            ],
            "pageInfo": {"hasNextPage": False},
        }
        pages = iter((payload, changed_second_page))
        github = actions.LiveGitHub(
            SimpleNamespace(run=lambda _arguments: copy.deepcopy(next(pages)))
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "changed during bounded pagination"):
            github.read_current_feedback(plan())

        changed_inactive_page = copy.deepcopy(second_page)
        changed_inactive_page["data"]["repository"]["pullRequest"]["comments"] = {
            "nodes": [
                {
                    "id": "COMMENT_LATE",
                    "databaseId": 31,
                    "body": "Late conversation feedback",
                    "updatedAt": "2026-07-20T00:00:00Z",
                    "author": actor,
                    "reactions": copy.deepcopy(empty),
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
        pages = iter((payload, changed_inactive_page))
        github = actions.LiveGitHub(
            SimpleNamespace(run=lambda _arguments: copy.deepcopy(next(pages)))
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "changed during bounded pagination"):
            github.read_current_feedback(plan())

        changed_final_page = copy.deepcopy(second_page)
        changed_final_page["data"]["repository"]["pullRequest"]["reviewThreads"][
            "nodes"
        ][0]["comments"]["nodes"][0]["body"] = "Edited after page completion"
        capture = 0

        def changed_completed_page(arguments: list[str]) -> dict[str, Any]:
            nonlocal capture
            if any(item == "threadsCursor=THREAD_CURSOR_1" for item in arguments):
                return copy.deepcopy(
                    changed_final_page if capture == 2 else second_page
                )
            capture += 1
            return copy.deepcopy(payload)

        github = actions.LiveGitHub(SimpleNamespace(run=changed_completed_page))
        with self.assertRaisesRegex(actions.MutationBlocked, "between bounded reads"):
            github.read_current_feedback(plan())

    def test_nullable_graphql_mutation_leaves_fail_closed(self) -> None:
        reaction_operation = operation()
        reaction_plan = plan(reaction_operation)
        for field in ("reaction", "subject"):
            response = {
                "data": {
                    "addReaction": {
                        "reaction": {
                            "id": "REACTION_NEW",
                            "content": "THUMBS_UP",
                            "user": {
                                "id": "USER_1",
                                "databaseId": 7,
                                "login": "aroviqen",
                            },
                        },
                        "subject": {"id": "RC_1"},
                    }
                }
            }
            response["data"]["addReaction"][field] = None
            github = actions.LiveGitHub(
                SimpleNamespace(run=lambda _arguments, value=response: copy.deepcopy(value))
            )
            with self.subTest(field=field), self.assertRaises(actions.MutationFailure):
                github.apply_reaction(reaction_plan, reaction_operation)

        resolution_operation = operation(
            "THREAD_RESOLUTION", operation_id="resolve-001", reaction=None
        )
        github = actions.LiveGitHub(
            SimpleNamespace(
                run=lambda _arguments: {
                    "data": {"resolveReviewThread": {"thread": None}}
                }
            )
        )
        with self.assertRaises(actions.MutationFailure):
            github.apply_resolution(plan(resolution_operation), resolution_operation)

    def test_live_feedback_projection_obeys_every_registered_item_cap(self) -> None:
        feedback = {
            "pull_request_reactions": [],
            "reviews": [
                {"node_id": "REVIEW_1", "reactions": []},
                {"node_id": "REVIEW_2", "reactions": []},
            ],
            "conversation_comments": [],
            "threads": [],
        }
        limits = {
            "maximum_items": 1,
            "maximum_threads": 1,
            "maximum_comments": 1,
            "maximum_reactions": 1,
        }
        with self.assertRaisesRegex(actions.MutationBlocked, "items"):
            actions._validate_feedback_limits(feedback, limits)

        feedback["reviews"] = [
            {
                "node_id": "REVIEW_1",
                "reactions": [{} for _index in range(26)],
            }
        ]
        limits.update(maximum_items=1000, maximum_reactions=50)
        with self.assertRaisesRegex(actions.MutationBlocked, "reactions"):
            actions._validate_feedback_limits(feedback, limits)

    def test_pending_policy_write_reserves_feedback_capacity(self) -> None:
        limits = {
            "maximum_items": 10000,
            "maximum_threads": 500,
            "maximum_comments": 200,
            "maximum_reactions": 50,
        }
        comments = [
            {
                "node_id": f"RC_{index}",
                "body_digest": digest(f"comment {index}"),
                "actor": {},
                "reply_to_id": None,
                "reactions": [],
            }
            for index in range(100)
        ]
        feedback = {
            "pull_request_reactions": [],
            "reviews": [],
            "conversation_comments": [],
            "threads": [{"node_id": "THREAD_1", "comments": comments[:99]}],
        }
        actions._validate_feedback_limits(
            feedback, limits, pending_operation_kind="EVIDENCE_REPLY"
        )
        feedback["threads"][0]["comments"] = comments
        with self.assertRaisesRegex(actions.MutationBlocked, "comments"):
            actions._validate_feedback_limits(
                feedback, limits, pending_operation_kind="EVIDENCE_REPLY"
            )

        feedback["threads"][0]["comments"] = [
            {
                **comments[0],
                "reactions": [{} for _index in range(24)],
            }
        ]
        actions._validate_feedback_limits(
            feedback, limits, pending_operation_kind="REACTION"
        )
        feedback["threads"][0]["comments"][0]["reactions"].append({})
        with self.assertRaisesRegex(actions.MutationBlocked, "reactions"):
            actions._validate_feedback_limits(
                feedback, limits, pending_operation_kind="REACTION"
            )

    def test_policy_write_blocks_before_mutation_at_effective_capacity(self) -> None:
        snapshot = evidence_snapshot()
        reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        value = plan(reply)
        value["findings"][0].update(
            classification="INVALID_FALSE_OR_MISLEADING",
            disposition="DISPROVEN_WITH_EVIDENCE",
        )
        feedback = actions._snapshot_review_feedback(snapshot, value)
        feedback["threads"][0]["comments"].extend(
            {
                "node_id": f"RC_EXTRA_{index}",
                "body_digest": digest(f"comment {index}"),
                "actor": {},
                "reply_to_id": None,
                "reactions": [],
            }
            for index in range(99)
        )
        github = FakeGitHub()

        with self.assertRaisesRegex(actions.MutationBlocked, "comments"):
            actions.execute_operation(
                value,
                "reply-001",
                snapshot,
                repository_config(),
                github,
                apply=True,
                resolution_evidence=None,
                current_feedback={"feedback": feedback},
            )

        self.assertNotIn(("WRITE", "EVIDENCE_REPLY"), github.calls)

    def test_missing_trusted_gh_is_reported_as_a_guarded_blocker(self) -> None:
        with mock.patch.object(
            actions.evidence,
            "resolve_trusted_executable",
            side_effect=actions.evidence.CommandPolicyError("gh unavailable"),
        ):
            with self.assertRaisesRegex(actions.MutationBlocked, "GitHub CLI"):
                actions.ActionCommandRunner()

    def test_resolution_requires_complete_specific_remediation_evidence(self) -> None:
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        github = FakeGitHub()
        github.state["target"].update(
            {
                "node_id": "THREAD_1",
                "database_id": None,
                "target_type": "PULL_REQUEST_REVIEW_THREAD",
                "body_digest": None,
                "is_resolved": False,
            }
        )
        complete = complete_resolution_evidence()
        result = actions.execute_operation(
            value, "resolve-001", evidence_snapshot(), repository_config(), github, apply=True,
            resolution_evidence=complete,
        )
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(
            github.calls,
            [
                ("READ", "current-state"),
                ("READ", "required-checks"),
                ("WRITE", "THREAD_RESOLUTION"),
            ],
        )
        for key in complete:
            github = FakeGitHub()
            github.state["target"].update({"node_id": "THREAD_1", "database_id": None, "target_type": "PULL_REQUEST_REVIEW_THREAD", "body_digest": None, "is_resolved": False})
            incomplete = copy.deepcopy(complete)
            incomplete[key] = False
            with self.subTest(precondition=key), self.assertRaises(actions.MutationBlocked):
                actions.execute_operation(value, "resolve-001", evidence_snapshot(), repository_config(), github, apply=True, resolution_evidence=incomplete)

    def test_unrecorded_already_resolved_thread_is_blocked(self) -> None:
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        github = FakeGitHub()
        github.state["target"].update({"node_id": "THREAD_1", "database_id": None, "target_type": "PULL_REQUEST_REVIEW_THREAD", "body_digest": None, "is_resolved": True})
        with self.assertRaisesRegex(actions.MutationBlocked, "resolution state changed"):
            actions.execute_operation(
                value,
                "resolve-001",
                evidence_snapshot(),
                repository_config(),
                github,
                apply=True,
                resolution_evidence=complete_resolution_evidence(),
            )
        self.assertNotIn(("WRITE", "THREAD_RESOLUTION"), github.calls)

        value["operations"][0]["applied_mutation_identity"] = "THREAD_1"
        value["session"]["thread_resolutions"] = 1
        result = actions.execute_operation(
            value,
            "resolve-001",
            evidence_snapshot(),
            repository_config(),
            github,
            apply=True,
            resolution_evidence=complete_resolution_evidence(),
        )
        self.assertEqual(result["status"], "ALREADY_APPLIED_RECORDED")

    def test_resolution_rechecks_the_complete_live_thread_comment_set(self) -> None:
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        github = FakeGitHub()
        github.state["target"].update(
            {
                "node_id": "THREAD_1",
                "database_id": None,
                "target_type": "PULL_REQUEST_REVIEW_THREAD",
                "body_digest": None,
                "is_resolved": False,
            }
        )
        github.state["target"]["thread_comments"].append(
            {
                "node_id": "RC_LATE",
                "body_digest": digest("Late material feedback"),
                "actor": {
                    "login": "reviewer",
                    "node_id": "ACTOR_reviewer",
                    "database_id": 7,
                },
                "reply_to_id": None,
                "reactions": [],
            }
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "thread feedback changed"):
            actions.execute_operation(
                value,
                "resolve-001",
                evidence_snapshot(),
                repository_config(),
                github,
                apply=True,
                resolution_evidence=complete_resolution_evidence(),
            )
        self.assertNotIn(("WRITE", "THREAD_RESOLUTION"), github.calls)

    def test_every_thread_sensitive_mutation_rechecks_complete_thread_feedback(self) -> None:
        cases = (
            ("REACTION", "reaction-001", "VALID_ACTIONABLE"),
            ("EVIDENCE_REPLY", "reply-001", "INVALID_FALSE_OR_MISLEADING"),
            ("THREAD_RESOLUTION", "resolve-001", "VALID_ACTIONABLE"),
        )
        for kind, operation_id, classification in cases:
            op = operation(
                kind,
                operation_id=operation_id,
                classification=classification,
                reaction="THUMBS_UP" if kind == "REACTION" else None,
                reply_body="Independent evidence" if kind == "EVIDENCE_REPLY" else None,
            )
            state = (
                "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE"
                if kind == "THREAD_RESOLUTION"
                else "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES"
            )
            value = plan(op, current_state=state)
            if kind == "EVIDENCE_REPLY":
                value["findings"][0].update(
                    {
                        "classification": classification,
                        "disposition": "DISPROVEN_WITH_EVIDENCE",
                    }
                )
            github = FakeGitHub()
            if kind == "THREAD_RESOLUTION":
                github.state["target"].update(
                    {
                        "node_id": "THREAD_1",
                        "database_id": None,
                        "target_type": "PULL_REQUEST_REVIEW_THREAD",
                        "body_digest": None,
                    }
                )
            github.state["target"]["thread_comments"].append(
                {
                    "node_id": "RC_LATE",
                    "body_digest": digest("Late material feedback"),
                    "actor": {
                        "login": "reviewer",
                        "node_id": "ACTOR_reviewer",
                        "database_id": 7,
                    },
                    "reply_to_id": None,
                    "reactions": [],
                }
            )
            with self.subTest(kind=kind), self.assertRaisesRegex(
                actions.MutationBlocked, "thread feedback changed"
            ):
                actions.execute_operation(
                    value,
                    operation_id,
                    evidence_snapshot(),
                    repository_config(),
                    github,
                    apply=True,
                    resolution_evidence=(
                        complete_resolution_evidence()
                        if kind == "THREAD_RESOLUTION"
                        else None
                    ),
                )
            self.assertFalse(any(call[0] == "WRITE" for call in github.calls))

    def test_late_thread_comment_reaction_blocks_a_mutation(self) -> None:
        github = FakeGitHub()
        github.state["target"]["thread_comments"][0]["reactions"] = [
            {
                "mutation_id": "REACTION_LATE",
                "content": "THUMBS_UP",
                "actor": {
                    "login": "late-reactor",
                    "node_id": "ACTOR_late",
                    "database_id": 19,
                },
            }
        ]
        with self.assertRaisesRegex(actions.MutationBlocked, "thread feedback changed"):
            self.apply(plan(operation()), "reaction-001", github)
        self.assertFalse(any(call[0] == "WRITE" for call in github.calls))

    def test_terminal_session_blockers_stop_before_live_reads_or_writes(self) -> None:
        blocker_values = {
            "worktree_clean": False,
            "head_matches": False,
            "unexplained_commit": True,
            "signatures_valid": False,
            "snapshot_digest_matches": False,
            "evidence_complete": False,
            "late_feedback_detected": True,
            "scope_requires_other_repository": True,
            "mutation_failed": True,
            "push_failed": True,
            "github_state_safe": False,
            "ci_state": "FAILED",
        }
        for key, blocked_value in blocker_values.items():
            value = plan(operation())
            value["session"][key] = blocked_value
            github = FakeGitHub()
            with self.subTest(blocker=key), self.assertRaises(actions.MutationBlocked):
                self.apply(value, "reaction-001", github)
            self.assertEqual(github.calls, [])

    def test_command_preflight_blocks_before_resolution_reads_and_validations(self) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            reaction=None,
        )
        arguments = SimpleNamespace(
            command="resolve",
            plan="plan.json",
            snapshot="final.json",
            config="config.json",
            initial_snapshot="initial.json",
            operation_id="resolve-001",
            repo="SecPal/.github",
            pr=1,
            snapshot_digest=evidence_snapshot()["snapshot_digest"],
            expected_head=p21.HEAD,
            apply=True,
        )
        blocker_values = {
            "worktree_clean": False,
            "head_matches": False,
            "unexplained_commit": True,
            "signatures_valid": False,
            "snapshot_digest_matches": False,
            "evidence_complete": False,
            "late_feedback_detected": True,
            "scope_requires_other_repository": True,
            "mutation_failed": True,
            "push_failed": True,
            "github_state_safe": False,
            "ci_state": "PENDING",
        }
        for key, blocked_value in blocker_values.items():
            value = plan(
                resolution,
                current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
            )
            value["session"][key] = blocked_value
            with (
                self.subTest(blocker=key),
                mock.patch.object(
                    actions,
                    "_load_inputs",
                    return_value=(value, evidence_snapshot(), repository_config()),
                ),
                mock.patch.object(actions, "LiveGitHub") as live_github,
                mock.patch.object(actions, "_read_json", wraps=actions._read_json) as read_json,
                mock.patch.object(actions, "_verify_retained_mutations") as retained,
                mock.patch.object(actions, "build_resolution_evidence") as resolution_evidence,
                self.assertRaises(actions.MutationBlocked),
            ):
                actions._command_mutation(arguments)
            live_github.assert_not_called()
            self.assertFalse(
                any(call.args and call.args[0] == "initial.json" for call in read_json.call_args_list)
            )
            retained.assert_not_called()
            resolution_evidence.assert_not_called()

    def test_command_verifies_all_prior_mutations_before_each_new_write(self) -> None:
        value = plan(operation())
        arguments = SimpleNamespace(
            command="react",
            plan="plan.json",
            snapshot="snapshot.json",
            config="config.json",
            operation_id="reaction-001",
            repo="SecPal/.github",
            pr=1,
            snapshot_digest=evidence_snapshot()["snapshot_digest"],
            expected_head=p21.HEAD,
            apply=True,
        )
        github = FakeGitHub()
        github.read_current_feedback = mock.Mock(
            return_value={
                "head_sha": p21.HEAD,
                "pr_state": "OPEN",
                "feedback": actions._snapshot_review_feedback(
                    evidence_snapshot(), value
                ),
            }
        )
        with (
            mock.patch.object(
                actions,
                "_load_inputs",
                return_value=(value, evidence_snapshot(), repository_config()),
            ),
            mock.patch.object(actions, "LiveGitHub", return_value=github),
            mock.patch.object(
                actions,
                "_verify_retained_mutations",
                return_value=set(),
            ) as retained,
            mock.patch.object(
                actions,
                "execute_operation",
                return_value={"status": "APPLIED"},
            ) as execute,
            mock.patch.object(actions.sys, "stdout", SimpleNamespace(buffer=io.BytesIO())),
        ):
            self.assertEqual(actions._command_mutation(arguments), 0)
        retained.assert_called_once_with(
            value,
            evidence_snapshot(),
            github,
            exclude_operation_id="reaction-001",
        )
        github.read_current_feedback.assert_called_once_with(value)
        execute.assert_called_once()
        self.assertIs(
            execute.call_args.kwargs["current_feedback"],
            github.read_current_feedback.return_value,
        )

    def test_resolution_blocks_on_pr_wide_feedback_before_readiness_validation(self) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            reaction=None,
        )
        value = plan(
            resolution,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        snapshot = evidence_snapshot()
        arguments = SimpleNamespace(
            command="resolve",
            plan="plan.json",
            snapshot="final.json",
            config="config.json",
            initial_snapshot="initial.json",
            operation_id="resolve-001",
            repo="SecPal/.github",
            pr=1,
            snapshot_digest=snapshot["snapshot_digest"],
            expected_head=p21.HEAD,
            apply=True,
        )
        github = FakeGitHub()
        github.read_current_feedback = mock.Mock(
            return_value={
                "head_sha": p21.HEAD,
                "pr_state": "OPEN",
                "feedback": {
                    "pull_request_reactions": [],
                    "reviews": [
                        {
                            "node_id": "REVIEW_LATE",
                            "body_digest": digest("Late review"),
                            "actor": copy.deepcopy(github.state["actor"]),
                            "state": "COMMENTED",
                            "commit_oid": p21.HEAD,
                            "reactions": [],
                        }
                    ],
                    "conversation_comments": [],
                    "threads": [],
                },
            }
        )
        with (
            mock.patch.object(
                actions,
                "_load_inputs",
                return_value=(value, snapshot, repository_config()),
            ),
            mock.patch.object(actions, "LiveGitHub", return_value=github),
            mock.patch.object(
                actions, "_verify_retained_mutations", return_value=set()
            ),
            mock.patch.object(actions, "_read_json", wraps=actions._read_json) as read_json,
            mock.patch.object(actions, "build_resolution_evidence") as readiness,
            self.assertRaisesRegex(actions.MutationBlocked, "PR-wide feedback changed"),
        ):
            actions._command_mutation(arguments)
        github.read_current_feedback.assert_called_once_with(value)
        self.assertFalse(
            any(call.args and call.args[0] == "initial.json" for call in read_json.call_args_list)
        )
        readiness.assert_not_called()

    def test_resolution_rechecks_pr_wide_feedback_after_readiness_validation(self) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            reaction=None,
        )
        value = plan(
            resolution,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        snapshot = evidence_snapshot()
        arguments = SimpleNamespace(
            command="resolve",
            plan="plan.json",
            snapshot="final.json",
            config="config.json",
            initial_snapshot="initial.json",
            operation_id="resolve-001",
            repo="SecPal/.github",
            pr=1,
            snapshot_digest=snapshot["snapshot_digest"],
            expected_head=p21.HEAD,
            apply=True,
        )
        github = FakeGitHub()
        expected_feedback = actions._snapshot_review_feedback(snapshot, value)
        late_feedback = copy.deepcopy(expected_feedback)
        late_feedback["reviews"].append(
            {
                "node_id": "REVIEW_LATE",
                "body_digest": digest("Late review after validation"),
                "actor": copy.deepcopy(github.state["actor"]),
                "state": "COMMENTED",
                "commit_oid": p21.HEAD,
                "reactions": [],
            }
        )
        github.read_current_feedback = mock.Mock(
            side_effect=[
                {
                    "head_sha": p21.HEAD,
                    "pr_state": "OPEN",
                    "feedback": expected_feedback,
                },
                {
                    "head_sha": p21.HEAD,
                    "pr_state": "OPEN",
                    "feedback": late_feedback,
                },
            ]
        )
        registered = actions.load_registry()
        with (
            mock.patch.object(
                actions,
                "_load_inputs",
                return_value=(value, snapshot, repository_config()),
            ),
            mock.patch.object(actions, "LiveGitHub", return_value=github),
            mock.patch.object(
                actions, "_verify_retained_mutations", return_value=set()
            ),
            mock.patch.object(actions, "load_registry", return_value=registered),
            mock.patch.object(actions, "_read_json", return_value=snapshot),
            mock.patch.object(
                actions,
                "build_resolution_evidence",
                return_value=complete_resolution_evidence(),
            ) as readiness,
            mock.patch.object(actions, "execute_operation") as execute,
            self.assertRaisesRegex(actions.MutationBlocked, "PR-wide feedback changed"),
        ):
            actions._command_mutation(arguments)
        self.assertEqual(github.read_current_feedback.call_count, 2)
        readiness.assert_called_once()
        execute.assert_not_called()

    def test_resolution_blocks_when_the_last_required_check_read_fails(self) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            reaction=None,
        )
        value = plan(
            resolution,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        github = FakeGitHub()
        github.state["target"].update(
            {
                "node_id": "THREAD_1",
                "database_id": None,
                "target_type": "PULL_REQUEST_REVIEW_THREAD",
                "body_digest": None,
                "is_resolved": False,
            }
        )
        github.verify_current_required_checks = mock.Mock(
            side_effect=actions.MutationBlocked("required check is no longer successful")
        )

        with self.assertRaisesRegex(actions.MutationBlocked, "required check"):
            actions.execute_operation(
                value,
                "resolve-001",
                evidence_snapshot(),
                repository_config(),
                github,
                apply=True,
                resolution_evidence=complete_resolution_evidence(),
            )
        github.verify_current_required_checks.assert_called_once_with(
            value, evidence_snapshot(), repository_config()
        )
        self.assertEqual(github.calls, [("READ", "current-state")])

    def test_resolution_readiness_uses_initial_snapshot_and_blocks_late_feedback(self) -> None:
        initial = evidence_snapshot()
        final = copy.deepcopy(initial)
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        result = actions.build_resolution_evidence(
            value,
            initial,
            final,
            repository_config(),
            p21.FakeGitRunner(),
            lambda _repository, _repository_root: True,
        )
        self.assertTrue(all(result.values()), result)

        late = copy.deepcopy(final)
        late["review_threads"][0]["comments"].append(
            p21.review_comment("RC_2", body="Late material feedback")
        )
        late = p21.finalize_snapshot(late)
        result = actions.build_resolution_evidence(
            value,
            initial,
            late,
            repository_config(),
            p21.FakeGitRunner(),
            lambda _repository, _repository_root: True,
        )
        self.assertFalse(result["no_late_feedback"])

        reaction_final = copy.deepcopy(final)
        recorded_reaction = p21.reaction("REACTION_NEW", "THUMBS_UP")
        recorded_reaction["user"] = p21.actor("aroviqen")
        reaction_final["review_threads"][0]["comments"][0]["reactions"] = [recorded_reaction]
        reaction_final = p21.finalize_snapshot(reaction_final)
        recorded = plan(
            operation(),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        recorded["operations"][0]["applied_mutation_identity"] = "REACTION_NEW"
        recorded["operations"][0]["expected_actor_identity"] = {
            "login": "aroviqen",
            "node_id": "ACTOR_aroviqen",
            "database_id": 7,
        }
        self.assertTrue(
            actions._no_late_feedback(
                recorded,
                initial,
                reaction_final,
                {"REACTION_NEW"},
            )
        )
        unexpected = copy.deepcopy(reaction_final)
        unexpected["review_threads"][0]["comments"][0]["reactions"].append(
            p21.reaction("REACTION_LATE", "THUMBS_DOWN")
        )
        unexpected = p21.finalize_snapshot(unexpected)
        self.assertFalse(
            actions._no_late_feedback(
                recorded,
                initial,
                unexpected,
                {"REACTION_NEW"},
            )
        )

        unclassified = copy.deepcopy(value)
        unclassified["findings"] = []
        result = actions.build_resolution_evidence(
            unclassified,
            initial,
            final,
            repository_config(),
            p21.FakeGitRunner(),
            lambda _repository, _repository_root: True,
        )
        self.assertFalse(result["all_threads_classified"])

    def test_inline_comment_reactions_are_independent_classification_sources(self) -> None:
        initial = evidence_snapshot()
        nested = p21.reaction("REACTION_NESTED", "THUMBS_UP")
        initial["review_threads"][0]["comments"][0]["reactions"] = [nested]
        initial = p21.finalize_snapshot(initial)
        value = plan()
        value["snapshot_digest"] = initial["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        value["findings"] = [finding()]
        self.assertFalse(actions._all_initial_threads_classified(value, initial))

        reaction_finding = finding(
            "finding-reaction",
            "INFORMATIONAL",
            disposition="NON_ACTIONABLE",
        )
        reaction_finding.update(
            {
                "source_node_ids": [nested["id"]],
                "source_database_ids": [],
            }
        )
        value["findings"].append(reaction_finding)
        self.assertTrue(actions._all_initial_threads_classified(value, initial))
        self.assertEqual(actions.validate_plan(value, initial, repository_config()), value)

    def test_pr_wide_feedback_projection_detects_late_top_level_feedback(self) -> None:
        snapshot = evidence_snapshot()
        snapshot["reviews"] = [p21.review_record()]
        snapshot = p21.finalize_snapshot(snapshot)
        value = plan()
        value["snapshot_digest"] = snapshot["snapshot_digest"]
        value["initial_snapshot_digest"] = snapshot["snapshot_digest"]
        current = {
            "head_sha": p21.HEAD,
            "pr_state": "OPEN",
            "feedback": actions._snapshot_review_feedback(snapshot, value),
        }
        actions._verify_current_feedback(value, snapshot, current)
        current["feedback"]["reviews"][0]["reactions"].append(
            {
                "mutation_id": "REACTION_LATE",
                "content": "THUMBS_UP",
                "actor": {
                    "login": "late-reviewer",
                    "node_id": "ACTOR_late",
                    "database_id": 19,
                },
            }
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "PR-wide feedback changed"):
            actions._verify_current_feedback(value, snapshot, current)

    def test_pr_wide_feedback_allows_only_the_pending_inline_write_delta(self) -> None:
        snapshot = evidence_snapshot()
        viewer = {"login": "aroviqen", "node_id": "USER_1", "database_id": 7}
        reaction_operation = operation()
        reaction_plan = plan(reaction_operation)
        reaction_feedback = actions._snapshot_review_feedback(
            snapshot, reaction_plan
        )
        reaction_feedback["threads"][0]["comments"][0]["reactions"].append(
            {
                "mutation_id": "REACTION_EXISTING",
                "content": "THUMBS_UP",
                "actor": viewer,
            }
        )
        actions._verify_current_feedback(
            reaction_plan,
            snapshot,
            {
                "head_sha": p21.HEAD,
                "pr_state": "OPEN",
                "feedback": reaction_feedback,
            },
            reaction_operation,
        )

        reply_operation = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        reply_plan = plan(reply_operation)
        reply_plan["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        reply_feedback = actions._snapshot_review_feedback(snapshot, reply_plan)
        reply_feedback["threads"][0]["comments"].append(
            {
                "node_id": "REPLY_EXISTING",
                "body_digest": digest(reply_operation["reply_body"]),
                "actor": viewer,
                "reply_to_id": "RC_1",
                "reactions": [],
            }
        )
        actions._verify_current_feedback(
            reply_plan,
            snapshot,
            {
                "head_sha": p21.HEAD,
                "pr_state": "OPEN",
                "feedback": reply_feedback,
            },
            reply_operation,
        )

        wrong_parent_feedback = actions._snapshot_review_feedback(
            snapshot, reply_plan
        )
        wrong_parent_feedback["threads"][0]["comments"].append(
            {
                "node_id": "REPLY_OTHER_PARENT",
                "body_digest": digest(reply_operation["reply_body"]),
                "actor": viewer,
                "reply_to_id": "RC_OTHER",
                "reactions": [],
            }
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "PR-wide feedback changed"):
            actions._verify_current_feedback(
                reply_plan,
                snapshot,
                {
                    "head_sha": p21.HEAD,
                    "pr_state": "OPEN",
                    "feedback": wrong_parent_feedback,
                },
                reply_operation,
            )

        reply_feedback["threads"][0]["comments"].append(
            {
                "node_id": "REPLY_LATE",
                "body_digest": digest("Late feedback"),
                "actor": copy.deepcopy(snapshot["review_threads"][0]["comments"][0]["author"]),
                "reply_to_id": "RC_1",
                "reactions": [],
            }
        )
        with self.assertRaisesRegex(actions.MutationBlocked, "PR-wide feedback changed"):
            actions._verify_current_feedback(
                reply_plan,
                snapshot,
                {
                    "head_sha": p21.HEAD,
                    "pr_state": "OPEN",
                    "feedback": reply_feedback,
                },
                reply_operation,
            )

    def test_recorded_inline_writes_are_part_of_the_expected_global_feedback(self) -> None:
        snapshot = evidence_snapshot()
        recorded_reaction = operation()
        recorded_reaction["applied_mutation_identity"] = "REACTION_RECORDED"
        reaction_plan = plan(recorded_reaction)
        reaction_plan["session"]["reaction_writes"] = 1
        reaction_feedback = actions._snapshot_review_feedback(snapshot, reaction_plan)
        self.assertEqual(
            reaction_feedback["threads"][0]["comments"][0]["reactions"][0][
                "mutation_id"
            ],
            "REACTION_RECORDED",
        )

        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["applied_mutation_identity"] = "REPLY_RECORDED"
        reply_plan = plan(recorded_reply)
        reply_plan["session"]["evidence_replies"] = 1
        reply_feedback = actions._snapshot_review_feedback(snapshot, reply_plan)
        self.assertEqual(
            reply_feedback["threads"][0]["comments"][-1]["node_id"],
            "REPLY_RECORDED",
        )

    def test_recorded_resolutions_are_the_only_allowed_pr_wide_state_delta(self) -> None:
        snapshot = evidence_snapshot()
        resolution = operation(
            "THREAD_RESOLUTION", operation_id="resolve-001", reaction=None
        )
        resolution["applied_mutation_identity"] = "THREAD_1"
        value = plan(
            resolution,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["session"]["thread_resolutions"] = 1
        current = {
            "head_sha": p21.HEAD,
            "pr_state": "OPEN",
            "feedback": actions._snapshot_review_feedback(snapshot, value),
        }
        self.assertTrue(current["feedback"]["threads"][0]["is_resolved"])
        actions._verify_current_feedback(value, snapshot, current)

    def test_recorded_reply_must_exist_in_the_final_snapshot(self) -> None:
        initial = evidence_snapshot()
        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["applied_mutation_identity"] = "RC_MISSING"
        value = plan(
            recorded_reply,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        value["session"]["evidence_replies"] = 1
        self.assertFalse(
            actions._no_late_feedback(value, initial, initial, {"RC_MISSING"})
        )

    def test_verified_recorded_reply_is_accepted_in_the_final_snapshot(self) -> None:
        initial = evidence_snapshot()
        final = copy.deepcopy(initial)
        reply = p21.review_comment("RC_REPLY", login="aroviqen", body="Independent evidence")
        reply["database_id"] = 22
        reply["reply_to_id"] = "RC_1"
        final["review_threads"][0]["comments"].append(reply)
        final = p21.finalize_snapshot(final)
        recorded_reply = operation(
            "EVIDENCE_REPLY",
            operation_id="reply-001",
            classification="INVALID_FALSE_OR_MISLEADING",
            reaction=None,
            reply_body="Independent evidence",
        )
        recorded_reply["applied_mutation_identity"] = "RC_REPLY"
        recorded_reply["expected_actor_identity"] = {
            "login": "aroviqen",
            "node_id": "ACTOR_aroviqen",
            "database_id": 7,
        }
        value = plan(
            recorded_reply,
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["findings"][0].update(
            {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
            }
        )
        value["session"]["evidence_replies"] = 1
        self.assertTrue(
            actions._no_late_feedback(value, initial, final, {"RC_REPLY"})
        )

    def test_recorded_reaction_already_in_initial_snapshot_is_satisfied(self) -> None:
        initial = evidence_snapshot()
        existing = p21.reaction("REACTION_EXISTING", "THUMBS_UP")
        existing["user"] = p21.actor("aroviqen")
        initial["review_threads"][0]["comments"][0]["reactions"] = [existing]
        initial = p21.finalize_snapshot(initial)
        recorded = plan(
            operation(),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        recorded["snapshot_digest"] = initial["snapshot_digest"]
        recorded["initial_snapshot_digest"] = initial["snapshot_digest"]
        recorded["operations"][0]["applied_mutation_identity"] = "REACTION_EXISTING"
        recorded["operations"][0]["expected_actor_identity"] = {
            "login": "aroviqen",
            "node_id": "ACTOR_aroviqen",
            "database_id": 7,
        }
        recorded["session"]["reaction_writes"] = 1
        self.assertTrue(
            actions._no_late_feedback(
                recorded,
                initial,
                initial,
                {"REACTION_EXISTING"},
            )
        )

    def test_recorded_feedback_requires_live_identity_verification(self) -> None:
        initial = evidence_snapshot()
        final = copy.deepcopy(initial)
        reaction = p21.reaction("REACTION_FORGED", "THUMBS_UP")
        reaction["user"] = {
            "login": "aroviqen",
            "node_id": "USER_1",
            "database_id": 7,
            "type": "user",
        }
        final["review_threads"][0]["comments"][0]["reactions"] = [reaction]
        final = p21.finalize_snapshot(final)
        recorded = plan(
            operation(),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        recorded["operations"][0]["applied_mutation_identity"] = "REACTION_FORGED"
        recorded["operations"][0]["expected_actor_identity"] = {
            "login": "aroviqen",
            "node_id": "USER_1",
            "database_id": 7,
        }
        recorded["session"]["reaction_writes"] = 1
        self.assertFalse(actions._no_late_feedback(recorded, initial, final))

        github = FakeGitHub()
        github.state["target"]["reactions"] = [
            {
                "mutation_id": "REACTION_FORGED",
                "content": "THUMBS_UP",
                "actor": copy.deepcopy(github.state["viewer"]),
            }
        ]
        github.state["target"]["thread_comments"][0]["reactions"] = copy.deepcopy(
            github.state["target"]["reactions"]
        )
        self.assertEqual(
            actions._verify_retained_mutations(recorded, final, github),
            {"REACTION_FORGED"},
        )

    def test_resolution_readiness_accepts_a_verified_descendant_remediation_head(self) -> None:
        initial = evidence_snapshot()
        final_head = "d" * 40
        final = copy.deepcopy(initial)
        final["pull_request"].update(
            {
                "head_oid_before": final_head,
                "head_oid_after": final_head,
                "check_commit_oid": final_head,
            }
        )
        remediation_commit = copy.deepcopy(final["commits"][-1])
        remediation_commit.update(
            {
                "oid": final_head,
                "parents": [p21.HEAD],
                "authored_at": "2026-07-19T01:00:00Z",
                "committed_at": "2026-07-19T01:00:00Z",
            }
        )
        final["commits"].append(remediation_commit)
        final = p21.finalize_snapshot(final)

        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["snapshot_digest"] = final["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        value["expected_head_sha"] = final_head

        runner = p21.FakeGitRunner()
        runner.set(["git", "rev-parse", "HEAD"], 0, f"{final_head}\n")
        runner.set(["git", "rev-parse", "@{upstream}"], 0, f"{final_head}\n")
        runner.set(
            ["git", "rev-list", "--reverse", f"{p21.BASE}..{final_head}"],
            0,
            f"{p21.HEAD}\n{final_head}\n",
        )
        runner.set(
            ["git", "cat-file", "commit", final_head],
            0,
            "tree deadbeef\ngpgsig -----BEGIN SSH SIGNATURE-----\n signature\n -----END SSH SIGNATURE-----\n\nmessage\n",
        )
        runner.set(
            ["git", "verify-commit", "--raw", final_head],
            0,
            "",
            'Good "git" signature for aroviqen with ED25519 key SHA256:test\n',
        )

        actions.validate_plan(value, final, repository_config())
        result = actions.build_resolution_evidence(
            value,
            initial,
            final,
            repository_config(),
            runner,
            lambda _repository, _repository_root: True,
        )
        self.assertTrue(all(result.values()), result)

    def test_resolution_requires_coverage_of_every_initial_thread_comment(self) -> None:
        initial = evidence_snapshot()
        second_comment = p21.review_comment("RC_2", body="Second independent finding")
        second_comment["database_id"] = 22
        initial["review_threads"][0]["comments"].append(second_comment)
        initial = p21.finalize_snapshot(initial)
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["snapshot_digest"] = initial["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        self.assertFalse(actions._all_initial_threads_classified(value, initial))

    def test_resolution_classifies_only_initial_snapshot_sources(self) -> None:
        initial = evidence_snapshot()
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        generated_write = finding(
            "finding-generated-write",
            "INFORMATIONAL",
            disposition="NON_ACTIONABLE",
        )
        generated_write.update(
            {
                "source_node_ids": ["REPLY_OWN"],
                "source_database_ids": [22],
                "commit_sha": None,
                "test_evidence": [],
            }
        )
        value["findings"].append(generated_write)

        self.assertFalse(actions._all_initial_threads_classified(value, initial))

    def test_resolution_requires_classification_of_resolved_initial_threads(self) -> None:
        initial = evidence_snapshot()
        initial["review_threads"][0]["is_resolved"] = True
        initial = p21.finalize_snapshot(initial)
        value = plan(current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        value["findings"] = []
        self.assertFalse(actions._all_initial_threads_classified(value, initial))

    def test_resolution_requires_a_safely_disposed_canonical_finding(self) -> None:
        initial = evidence_snapshot()
        second_comment = p21.review_comment("RC_2", body="Canonical finding")
        second_comment["database_id"] = 22
        initial["review_threads"].append(
            {
                **p21.thread("THREAD_2", comments=[second_comment]),
                "is_resolved": True,
            }
        )
        initial = p21.finalize_snapshot(initial)
        duplicate = finding(
            "finding-001",
            "DUPLICATE",
            disposition="DUPLICATE_OF_CANONICAL",
        )
        duplicate["canonical_finding_id"] = "finding-002"
        canonical = finding("finding-002", disposition="PENDING")
        canonical.update(
            {
                "source_node_ids": ["RC_2"],
                "source_database_ids": [22],
                "parent_thread_id": "THREAD_2",
                "commit_sha": None,
                "test_evidence": [],
            }
        )
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["findings"] = [duplicate, canonical]
        value["operations"][0]["classification"] = "DUPLICATE"
        self.assertFalse(actions._all_initial_threads_classified(value, initial))

    def test_resolution_blocks_pending_material_top_level_findings(self) -> None:
        initial = evidence_snapshot()
        review = p21.review_record()
        initial["reviews"] = [review]
        initial = p21.finalize_snapshot(initial)
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        self.assertFalse(actions._all_initial_threads_classified(value, initial))
        value["findings"].append(
            {
                **finding("top-level-pending", disposition="PENDING"),
                "source_node_ids": [review["id"]],
                "source_database_ids": [review["database_id"]],
                "parent_thread_id": None,
                "commit_sha": None,
            }
        )
        self.assertFalse(actions._all_initial_threads_classified(value, initial))

    def test_resolution_requires_classification_of_pr_level_reactions(self) -> None:
        initial = evidence_snapshot()
        initial["pull_request"]["reactions"] = [
            p21.reaction("PR_REACTION_1", "THUMBS_UP")
        ]
        initial = p21.finalize_snapshot(initial)
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        self.assertFalse(actions._all_initial_threads_classified(value, initial))
        value["findings"].append(
            {
                **finding(
                    "pr-reaction-informational",
                    "INFORMATIONAL",
                    thread_id=None,
                    disposition="NON_ACTIONABLE",
                ),
                "source_node_ids": ["PR_REACTION_1"],
                "source_database_ids": [],
                "commit_sha": None,
                "test_evidence": [],
            }
        )
        self.assertTrue(actions._all_initial_threads_classified(value, initial))
        value["snapshot_digest"] = initial["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        self.assertEqual(
            actions.validate_plan(value, initial, repository_config())["findings"][-1][
                "logical_finding_id"
            ],
            "pr-reaction-informational",
        )

    def test_resolution_evidence_runs_registered_validations_fail_closed(self) -> None:
        initial = evidence_snapshot()
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        observed: list[tuple[str, Path]] = []

        def reject_validations(repository: dict[str, Any], repository_root: Path) -> bool:
            observed.append((repository["repository"], repository_root))
            return False

        result = actions.build_resolution_evidence(
            value,
            initial,
            initial,
            repository_config(),
            p21.FakeGitRunner(),
            reject_validations,
        )
        self.assertEqual(observed, [("SecPal/.github", Path("/repo"))])
        self.assertFalse(result["registered_validation_verified"])

    def test_resolution_evidence_requires_explicit_manual_gate_evidence(self) -> None:
        initial = evidence_snapshot()
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["manual_gate_evidence"] = []
        with self.assertRaisesRegex(actions.PlanError, "manual gate"):
            actions.validate_plan(value, initial, repository_config())
        result = actions.build_resolution_evidence(
            value,
            initial,
            initial,
            repository_config(),
            p21.FakeGitRunner(),
            lambda _repository, _repository_root: True,
        )
        self.assertFalse(result["manual_gates_verified"])
        self.assertFalse(result["registered_validation_verified"])

    def test_resolution_reverifies_local_state_after_registered_validations(self) -> None:
        initial = evidence_snapshot()
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        runner = p21.FakeGitRunner()

        def dirty_worktree_after_validation(
            _repository: dict[str, Any], _repository_root: Path
        ) -> bool:
            runner.set(
                ["git", "status", "--porcelain=v2", "--untracked-files=all"],
                0,
                "? validation-created-file\n",
            )
            return True

        result = actions.build_resolution_evidence(
            value,
            initial,
            initial,
            repository_config(),
            runner,
            dirty_worktree_after_validation,
        )
        self.assertTrue(result["registered_validation_verified"])
        self.assertFalse(result["local_verified"])


class RegistryTests(TestCase):
    repositories = [
        "SecPal/.github", "SecPal/api", "SecPal/frontend", "SecPal/contracts", "SecPal/android",
        "SecPal/changelog", "SecPal/GuardGuide", "SecPal/guardguide.de", "SecPal/secpal.app",
    ]

    def test_registry_caps_match_unpaginated_nested_live_connections(self) -> None:
        registry = actions.load_registry()
        for entry in registry["repositories"]:
            with self.subTest(repository=entry["repository"]):
                self.assertLessEqual(entry["maximum_comments"], 200)
                self.assertLessEqual(entry["maximum_reactions"], 50)

    def test_registry_cases_61_to_69(self) -> None:
        registry = {"schema_version": "1.0", "repositories": [registry_entry(repo) for repo in self.repositories]}
        self.assertEqual([item["repository"] for item in actions.validate_registry(registry)["repositories"]], self.repositories)
        duplicate = copy.deepcopy(registry)
        duplicate["repositories"].append(copy.deepcopy(duplicate["repositories"][0]))
        with self.assertRaisesRegex(actions.RegistryError, "duplicate"):
            actions.validate_registry(duplicate)
        invalid = copy.deepcopy(registry)
        invalid["repositories"][0]["repository"] = "invalid"
        with self.assertRaises(actions.RegistryError):
            actions.validate_registry(invalid)
        shell_string = copy.deepcopy(registry)
        shell_string["repositories"][0]["focused_validation"][0]["argv"] = "npm test"
        with self.assertRaises(actions.RegistryError):
            actions.validate_registry(shell_string)
        destructive = copy.deepcopy(registry)
        destructive["repositories"][0]["focused_validation"][0]["argv"] = ["rm", "-rf", "."]
        with self.assertRaisesRegex(actions.RegistryError, "destructive"):
            actions.validate_registry(destructive)
        for unsafe_argv in (
            ["git", "clean", "-fdx"],
            ["python3", "-c", "print('dynamic')"],
            ["./../outside"],
            ["npm", "exec", "tool"],
        ):
            dynamic = copy.deepcopy(registry)
            dynamic["repositories"][0]["focused_validation"][0]["argv"] = unsafe_argv
            with self.subTest(argv=unsafe_argv), self.assertRaises(actions.RegistryError):
                actions.validate_registry(dynamic)
        no_gate = copy.deepcopy(registry)
        no_gate["repositories"][0]["required_local_validation"] = []
        no_gate["repositories"][0]["manual_gates"] = []
        with self.assertRaisesRegex(actions.RegistryError, "manual gate"):
            actions.validate_registry(no_gate)
        aliases = copy.deepcopy(registry)
        aliases["repositories"][0]["reviewer_identities"] = [
            p21.config()["reviewer_identities"][0]
        ]
        with self.assertRaises(actions.RegistryError):
            actions.validate_registry(aliases)
        with self.assertRaises(actions.RegistryError):
            actions.select_repository(registry, "SecPal/unsupported")

    def test_validation_executable_uses_only_explicit_trusted_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "validator"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            command = {
                "argv": ["validator"],
                "working_directory": ".",
                "purpose": "fixture",
            }
            with mock.patch.object(
                actions,
                "LOCAL_VALIDATION_COMMAND_DIRECTORIES",
                (Path(directory),),
            ):
                self.assertEqual(
                    actions._validation_executable(command, REPO_ROOT, REPO_ROOT),
                    str(executable),
                )

    def test_registered_validations_receive_a_minimal_secret_free_environment(self) -> None:
        repository = registry_entry("SecPal/.github")
        completed = SimpleNamespace(returncode=0)
        with (
            mock.patch.dict(
                actions.os.environ,
                {
                    "GH_TOKEN": "parent-token-placeholder",
                    "AWS_SECRET_ACCESS_KEY": "parent-secret",
                    "PYTHONPATH": "/tmp/parent-controlled-pythonpath",
                    "UNRELATED_PARENT_VALUE": "must-not-leak",
                },
                clear=False,
            ),
            mock.patch.object(
                actions,
                "_validation_executable",
                return_value="/usr/bin/true",
            ),
            mock.patch.object(
                actions.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            self.assertTrue(
                actions._run_registered_validations(repository, REPO_ROOT)
            )
        self.assertGreater(run.call_count, 0)
        for call in run.call_args_list:
            environment = call.kwargs["env"]
            self.assertNotIn("GH_TOKEN", environment)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
            self.assertNotIn("UNRELATED_PARENT_VALUE", environment)
            self.assertNotEqual(
                environment["PYTHONPATH"], "/tmp/parent-controlled-pythonpath"
            )
            self.assertNotEqual(environment.get("HOME"), str(actions.ACCOUNT_HOME))
            self.assertEqual(
                set(environment),
                {
                    "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_NOSYSTEM",
                    "GIT_NO_LAZY_FETCH",
                    "GIT_NO_REPLACE_OBJECTS",
                    "GIT_OPTIONAL_LOCKS",
                    "HOME",
                    "LANG",
                    "LC_ALL",
                    "LOGNAME",
                    "NO_COLOR",
                    "PAGER",
                    "PATH",
                    "PYTHONPATH",
                    "TMPDIR",
                    "USER",
                    "XDG_CACHE_HOME",
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                },
            )


class AuditModeTests(TestCase):
    def test_cases_80_to_90_have_no_default_writes_and_handle_untrusted_data(self) -> None:
        hostile = plan(operation())
        hostile["findings"][0]["test_evidence"] = ["`$(touch /tmp/never)` <script>\u0007"]
        normalized = actions.validate_plan(hostile, evidence_snapshot(), repository_config())
        github = FakeGitHub()
        result = self.apply_audit(normalized, github)
        self.assertEqual(result["status"], "VALIDATED_NO_MUTATION")
        self.assertFalse(any(call[0] == "WRITE" for call in github.calls))
        self.assertIn("$(touch /tmp/never)", actions.canonical_json_bytes(normalized).decode("utf-8"))
        deleted = p21.snapshot()
        deleted["review_threads"] = [p21.thread(comments=[p21.review_comment(login="reviewer")])]
        deleted["review_threads"][0]["comments"][0]["author"] = p21.actor(None)
        deleted["review_threads"][0]["path"] = None
        deleted = p21.finalize_snapshot(deleted)
        p21.review.validate_snapshot(deleted)
        fork = copy.deepcopy(deleted)
        fork["pull_request"]["head_repository"] = {"id": "FORK", "name_with_owner": "fork/repo", "url": "https://github.com/fork/repo"}
        fork = p21.finalize_snapshot(fork)
        p21.review.validate_snapshot(fork)

    def apply_audit(self, value: dict[str, Any], github: FakeGitHub) -> dict[str, Any]:
        return actions.execute_operation(value, "reaction-001", evidence_snapshot(), repository_config(), github, apply=False, resolution_evidence=None)

    def test_plan_loading_does_not_persist_outside_explicit_output(self) -> None:
        value = plan(operation())
        with tempfile.TemporaryDirectory() as directory:
            before = sorted(Path(directory).iterdir())
            actions.validate_plan(value, evidence_snapshot(), repository_config())
            self.assertEqual(sorted(Path(directory).iterdir()), before)

    def test_resolution_audit_does_not_build_or_run_remediation_validations(self) -> None:
        snapshot = evidence_snapshot()
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        github = FakeGitHub()
        github.state["target"].update(
            {
                "node_id": "THREAD_1",
                "database_id": None,
                "target_type": "PULL_REQUEST_REVIEW_THREAD",
                "body_digest": None,
            }
        )
        arguments = SimpleNamespace(
            command="resolve",
            plan="plan.json",
            snapshot="snapshot.json",
            config="config.json",
            operation_id="resolve-001",
            repo="SecPal/.github",
            pr=1,
            snapshot_digest=snapshot["snapshot_digest"],
            expected_head=p21.HEAD,
            apply=False,
            initial_snapshot="missing-in-audit-mode.json",
        )
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(actions, "_load_inputs", return_value=(value, snapshot, repository_config())),
            mock.patch.object(actions, "LiveGitHub", return_value=github),
            mock.patch.object(actions, "build_resolution_evidence") as build_evidence,
            mock.patch.object(actions.sys, "stdout", output),
        ):
            self.assertEqual(actions._command_mutation(arguments), 0)
        build_evidence.assert_not_called()
        self.assertEqual(json.loads(output.buffer.getvalue())["status"], "VALIDATED_NO_MUTATION")


class PolicyScriptTests(TestCase):
    def test_policy_script_has_deterministic_tool_and_baseline_guards(self) -> None:
        policy = (REPO_ROOT / "tests/secpal-pr-review-skill-policy.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("command -v rg", policy)
        self.assertNotIn("rg -n", policy)
        self.assertIn("git -C \"$REPO_ROOT\" cat-file -e", policy)
        self.assertIn(".github/workflows/secpal-pr-review.yaml", policy)
        quality = (REPO_ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
        self.assertNotIn("apt-get install", quality)
        self.assertNotIn("command -v rg", quality)


if __name__ == "__main__":
    main()
