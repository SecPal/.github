#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import TestCase, main, mock

import jsonschema


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
fast_path = actions.fast_path
p21 = load_module("secpal_pr_review_p21_tests", P21_TESTS)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evidence_snapshot() -> dict[str, Any]:
    value = p21.snapshot()
    value["review_threads"] = [p21.thread()]
    return p21.finalize_snapshot(value)


def descendant_snapshot(
    initial: dict[str, Any], final_head: str = "d" * 40
) -> dict[str, Any]:
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
            "parents": [initial["pull_request"]["head_oid_after"]],
            "authored_at": "2026-07-19T01:00:00Z",
            "committed_at": "2026-07-19T01:00:00Z",
        }
    )
    final["commits"].append(remediation_commit)
    return p21.finalize_snapshot(final)


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
        "follow_up": None,
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
        "schema_version": "1.1",
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


def no_push_resolution_plan(*operations: dict[str, Any]) -> dict[str, Any]:
    value = plan(
        *operations,
        current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
    )
    value["cycle_number"] = 0
    value["session"].update(
        remediation_cycles=0,
        signed_commits=0,
        fast_forward_pushes=0,
    )
    for operation_value in value["operations"]:
        if operation_value["kind"] == "THREAD_RESOLUTION":
            operation_value["resolution_preconditions"]["pushed"] = False
    return value


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


def frontend_registry_entry() -> dict[str, Any]:
    value = registry_entry("SecPal/frontend")
    value["focused_validation"] = [
        {
            "argv": ["npm", "run", "test:migration-boundary"],
            "working_directory": ".",
            "purpose": "Run migration tests",
        },
        {
            "argv": ["npm", "run", "test:ui-csp"],
            "working_directory": ".",
            "purpose": "Run UI and CSP tests",
        },
        {
            "argv": ["npm", "run", "test:e2e:csp"],
            "working_directory": ".",
            "purpose": "Run local CSP browser tests",
            "execution_policy": "focused-only",
        },
    ]
    value["required_local_validation"] = [
        {
            "argv": ["npm", "run", "build:web"],
            "working_directory": ".",
            "purpose": "Build Web",
        },
        {
            "argv": ["npm", "run", "build:android"],
            "working_directory": ".",
            "purpose": "Build Android",
        },
    ]
    return value


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

    def read_current_feedback(self, plan_value: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("READ", "current-feedback"))
        snapshot = evidence_snapshot()
        return {
            "head_sha": p21.HEAD,
            "pr_state": "OPEN",
            "feedback": actions._snapshot_review_feedback(snapshot, plan_value),
        }

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

    def test_tracked_out_of_scope_finding_requires_exact_follow_up_identity(self) -> None:
        tracked = finding(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
        )
        tracked["follow_up"] = {
            "repository": "SecPal/api",
            "issue_number": 123,
            "issue_url": "https://github.com/SecPal/api/issues/123",
        }

        self.assertIn(
            "finding-001",
            actions._validate_finding_semantics([tracked]),
        )

        malformed = {
            "missing": None,
            "repository": {
                "repository": "SecPal",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
            "number": {
                "repository": "SecPal/api",
                "issue_number": 0,
                "issue_url": "https://github.com/SecPal/api/issues/0",
            },
            "non-issue URL": {
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/pull/123",
            },
            "repository mismatch": {
                "repository": "SecPal/frontend",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
            "number mismatch": {
                "repository": "SecPal/api",
                "issue_number": 124,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        }
        for label, follow_up in malformed.items():
            candidate = copy.deepcopy(tracked)
            candidate["follow_up"] = follow_up
            with self.subTest(label=label), self.assertRaisesRegex(
                actions.PlanError, "follow-up"
            ):
                actions._validate_finding_semantics([candidate])

    def test_tracked_follow_up_is_isolated_to_outside_scope(self) -> None:
        follow_up = {
            "repository": "SecPal/api",
            "issue_number": 123,
            "issue_url": "https://github.com/SecPal/api/issues/123",
        }
        incompatible = finding(
            classification="INFORMATIONAL",
            disposition="TRACKED_AS_FOLLOW_UP",
        )
        incompatible["follow_up"] = follow_up
        with self.assertRaisesRegex(actions.PlanError, "disposition"):
            actions._validate_finding_semantics([incompatible])

        untracked = finding(
            classification="OUTSIDE_PR_SCOPE",
            disposition="OUT_OF_SCOPE",
        )
        untracked["follow_up"] = None
        actions._validate_finding_semantics([untracked])
        self.assertNotIn("OUT_OF_SCOPE", actions.RESOLVABLE_DISPOSITIONS)

    def test_mutation_plan_schema_isolates_tracked_follow_up_classification(self) -> None:
        follow_up = {
            "repository": "SecPal/api",
            "issue_number": 123,
            "issue_url": "https://github.com/SecPal/api/issues/123",
        }
        tracked = plan()
        tracked["findings"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=follow_up,
        )
        schema = json.loads(actions.PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(tracked)

        untracked = copy.deepcopy(tracked)
        untracked["findings"][0].update(
            disposition="OUT_OF_SCOPE",
            follow_up=None,
        )
        validator.validate(untracked)

        classifications = schema["$defs"]["classification"]["enum"]
        for classification in classifications:
            if classification == "OUTSIDE_PR_SCOPE":
                continue
            incompatible = copy.deepcopy(tracked)
            incompatible["findings"][0]["classification"] = classification
            with self.subTest(classification=classification), self.assertRaises(
                jsonschema.ValidationError
            ):
                validator.validate(incompatible)

    def test_mutation_plan_v1_0_retains_recorded_session_state(self) -> None:
        recorded_reaction = operation()
        recorded_reaction["applied_mutation_identity"] = "REACTION_OWN"
        legacy = plan(recorded_reaction)
        legacy["schema_version"] = "1.0"
        legacy["session"]["reaction_writes"] = 1
        for item in legacy["findings"]:
            item.pop("follow_up")

        self.assertEqual(
            actions.validate_plan(
                legacy,
                evidence_snapshot(),
                repository_config(),
            ),
            legacy,
        )

    def test_mutation_plan_versions_reject_mixed_and_unknown_shapes(self) -> None:
        legacy = plan()
        legacy["schema_version"] = "1.0"
        legacy["findings"][0].pop("follow_up")

        legacy_with_follow_up = copy.deepcopy(legacy)
        legacy_with_follow_up["findings"][0]["follow_up"] = None
        with self.assertRaises(actions.PlanError):
            actions.validate_plan(
                legacy_with_follow_up,
                evidence_snapshot(),
                repository_config(),
            )

        legacy_tracked = copy.deepcopy(legacy)
        legacy_tracked["findings"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
        )
        with self.assertRaises(actions.PlanError):
            actions.validate_plan(
                legacy_tracked,
                evidence_snapshot(),
                repository_config(),
            )

        current_without_follow_up = plan()
        current_without_follow_up["findings"][0].pop("follow_up")
        with self.assertRaises(actions.PlanError):
            actions.validate_plan(
                current_without_follow_up,
                evidence_snapshot(),
                repository_config(),
            )

        unknown = plan()
        unknown["schema_version"] = "2.0"
        with self.assertRaisesRegex(
            actions.PlanError,
            "unsupported mutation plan schema version",
        ):
            actions.validate_plan(
                unknown,
                evidence_snapshot(),
                repository_config(),
            )

        self.assertEqual(
            actions.validate_plan(
                plan(),
                evidence_snapshot(),
                repository_config(),
            )["schema_version"],
            "1.1",
        )

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

    def test_version_one_resolution_plan_accepts_ignored_ci_compatibility_field(
        self,
    ) -> None:
        resolution = operation(
            "THREAD_RESOLUTION",
            operation_id="resolve-001",
            classification="INFORMATIONAL",
            reaction=None,
        )
        resolution["resolution_preconditions"].update(
            pushed=False,
            required_ci_succeeded=False,
        )
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
                                "oid": oid,
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
        self.assertIn("replyTo { id databaseId }", query)
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
                        "reviewDecision": "CHANGES_REQUESTED",
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
        self.assertEqual(current["review_decision"], "CHANGES_REQUESTED")
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

        changed_review_decision = copy.deepcopy(second_page)
        changed_review_decision["data"]["repository"]["pullRequest"][
            "reviewDecision"
        ] = "APPROVED"
        pages = iter((payload, changed_review_decision))
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
                ("READ", "current-feedback"),
                ("READ", "current-state"),
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

    def test_resolution_rechecks_feedback_after_required_check_verification(self) -> None:
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
        late_feedback = actions._snapshot_review_feedback(snapshot, value)
        late_feedback["reviews"].append(
            {
                "node_id": "REVIEW_LATE",
                "body_digest": digest("Late review after required checks"),
                "actor": copy.deepcopy(github.state["actor"]),
                "state": "COMMENTED",
                "commit_oid": p21.HEAD,
                "reactions": [],
            }
        )
        github.read_current_feedback = mock.Mock(
            return_value={
                "head_sha": p21.HEAD,
                "pr_state": "OPEN",
                "feedback": late_feedback,
            }
        )

        with self.assertRaisesRegex(actions.MutationBlocked, "PR-wide feedback changed"):
            actions.execute_operation(
                value,
                "resolve-001",
                snapshot,
                repository_config(),
                github,
                apply=True,
                resolution_evidence=complete_resolution_evidence(),
            )

        self.assertIn(("READ", "required-checks"), github.calls)
        self.assertNotIn(("WRITE", "THREAD_RESOLUTION"), github.calls)

    def test_resolution_readiness_uses_initial_snapshot_and_blocks_late_feedback(self) -> None:
        initial = evidence_snapshot()
        final = copy.deepcopy(initial)
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = no_push_resolution_plan(op)
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

    def test_resolution_rejects_a_reused_final_snapshot_as_the_initial_anchor(self) -> None:
        snapshot = evidence_snapshot()
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )

        result = actions.build_resolution_evidence(
            value,
            snapshot,
            snapshot,
            repository_config(),
            p21.FakeGitRunner(),
            lambda _repository, _repository_root: True,
        )

        self.assertFalse(all(result.values()), result)

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
        final = descendant_snapshot(initial, final_head)

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

    def test_resolution_rejects_head_advance_without_a_recorded_push(self) -> None:
        initial = evidence_snapshot()
        final_head = "d" * 40
        final = descendant_snapshot(initial, final_head)
        value = no_push_resolution_plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        )
        value["snapshot_digest"] = final["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        value["expected_head_sha"] = final_head

        with mock.patch.object(
            actions.evidence,
            "verify_local_against_snapshot",
            return_value={"blockers": [], "repository_root": "/repo"},
        ):
            result = actions.build_resolution_evidence(
                value,
                initial,
                final,
                repository_config(),
                validation_runner=lambda _repository, _repository_root: True,
            )

        self.assertFalse(all(result.values()), result)

    def test_resolution_requires_one_new_commit_per_recorded_signed_push(self) -> None:
        initial = evidence_snapshot()
        final_head = "d" * 40
        final = descendant_snapshot(initial, final_head)
        value = plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None),
            current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE",
        )
        value["cycle_number"] = 2
        value["session"].update(
            remediation_cycles=2,
            signed_commits=2,
            fast_forward_pushes=2,
        )
        value["snapshot_digest"] = final["snapshot_digest"]
        value["initial_snapshot_digest"] = initial["snapshot_digest"]
        value["expected_head_sha"] = final_head

        with mock.patch.object(
            actions.evidence,
            "verify_local_against_snapshot",
            return_value={"blockers": [], "repository_root": "/repo"},
        ):
            result = actions.build_resolution_evidence(
                value,
                initial,
                final,
                repository_config(),
                validation_runner=lambda _repository, _repository_root: True,
            )

        self.assertFalse(all(result.values()), result)

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
        value = no_push_resolution_plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
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
        value = no_push_resolution_plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
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
        value = no_push_resolution_plan(
            operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
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
        "SecPal/GuardGuide", "SecPal/guardguide.de", "SecPal/secpal.app",
        "SecPal/deployment",
    ]

    def test_deployment_repository_registration_matches_the_supported_schema(self) -> None:
        registry = actions.load_registry()
        self.assertEqual([item["repository"] for item in registry["repositories"]], self.repositories)
        deployment = actions.select_repository(registry, "SecPal/deployment")

        self.assertEqual(deployment["repository"], "SecPal/deployment")
        self.assertEqual(
            f"https://github.com/{deployment['repository']}",
            "https://github.com/SecPal/deployment",
        )
        self.assertEqual(deployment["default_branch"], "main")
        self.assertEqual(deployment["allowed_base_repositories"], ["SecPal/deployment"])
        self.assertEqual(deployment["reviewer_identities"], [])
        self.assertEqual(
            deployment["focused_validation"],
            [
                {
                    "argv": ["./scripts/local-integration.sh"],
                    "working_directory": ".",
                    "purpose": (
                        "Build and exercise the complete local API/frontend "
                        "integration stack"
                    ),
                    "execution_policy": "focused-only",
                }
            ],
        )
        self.assertEqual(
            deployment["required_local_validation"],
            [
                {
                    "argv": ["./scripts/preflight.sh"],
                    "working_directory": ".",
                    "purpose": "Run the deterministic deployment repository preflight",
                }
            ],
        )
        self.assertEqual(
            deployment["signature_policy"],
            {
                "require_github_verified": True,
                "require_local_verified": True,
                "accepted_formats": ["ssh", "openpgp"],
            },
        )
        self.assertEqual(
            deployment["check_policy"],
            {
                "require_ruleset_evidence": True,
                "require_branch_protection_evidence": True,
                "expected_skipped": "block",
            },
        )
        self.assertIn("BRANCH_WRITE", deployment["unsupported_operations"])
        self.assertEqual(
            set(deployment),
            {
                "repository",
                "default_branch",
                "allowed_base_repositories",
                "reviewer_identities",
                "focused_validation",
                "required_local_validation",
                "signature_policy",
                "check_policy",
                "manual_gates",
                "unsupported_operations",
                "maximum_api_calls",
                "maximum_items",
                "maximum_threads",
                "maximum_comments",
                "maximum_reactions",
            },
        )

    def test_registry_caps_match_unpaginated_nested_live_connections(self) -> None:
        registry = actions.load_registry()
        for entry in registry["repositories"]:
            with self.subTest(repository=entry["repository"]):
                self.assertLessEqual(entry["maximum_comments"], 200)
                self.assertLessEqual(entry["maximum_reactions"], 50)

    def test_registry_cases_61_to_69(self) -> None:
        registry = {
            "schema_version": "1.0",
            "fixed_thread_resolution": copy.deepcopy(
                actions.load_registry()["fixed_thread_resolution"]
            ),
            "repositories": [registry_entry(repo) for repo in self.repositories],
        }
        self.assertEqual([item["repository"] for item in actions.validate_registry(registry)["repositories"]], self.repositories)
        missing_resolution_contract = copy.deepcopy(registry)
        missing_resolution_contract.pop("fixed_thread_resolution")
        self.assertEqual(
            actions.validate_registry(missing_resolution_contract)["repositories"],
            registry["repositories"],
        )
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
            ["busybox", "sh", "-c", "printf unsafe"],
            ["cmd.exe", "/c", "echo unsafe"],
            ["composer", "exec", "tool"],
            ["dash", "-c", "printf unsafe"],
            ["git", "clean", "-fdx"],
            ["env", "bash", "-c", "printf unsafe"],
            ["find", ".", "-exec", "bash", ";"],
            ["python3", "-c", "print('dynamic')"],
            ["sudo", "bash"],
            ["systemd-run", "bash"],
            ["timeout", "10", "bash"],
            ["toybox", "sh", "-c", "printf unsafe"],
            ["unshare", "bash"],
            ["./../outside"],
            ["npm", "exec", "tool"],
            ["node", "--eval", "process.exit()"],
            ["python3", "-m", "pip", "install", "tool"],
            ["reuse", "download", "LICENSE"],
            ["xargs", "bash"],
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

    def test_playwright_browser_cache_uses_the_host_platform_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            account_home = Path(directory)
            expected_by_platform = {
                "linux": account_home / ".cache/ms-playwright",
                "darwin": account_home / "Library/Caches/ms-playwright",
            }

            for caches_exist in (False, True):
                if caches_exist:
                    for cache in expected_by_platform.values():
                        cache.mkdir(parents=True)
                for host_platform, expected in expected_by_platform.items():
                    with (
                        self.subTest(
                            host_platform=host_platform,
                            caches_exist=caches_exist,
                        ),
                        mock.patch.object(actions.sys, "platform", host_platform),
                    ):
                        self.assertEqual(
                            actions._playwright_browsers_path(account_home),
                            expected,
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
                    "PLAYWRIGHT_BROWSERS_PATH": "/tmp/parent-controlled-browser-cache",
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
            self.assertEqual(
                environment.get("PLAYWRIGHT_BROWSERS_PATH"),
                str(actions.PLAYWRIGHT_BROWSERS_PATH),
            )
            self.assertNotEqual(
                environment.get("PLAYWRIGHT_BROWSERS_PATH"),
                "/tmp/parent-controlled-browser-cache",
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
                    "PLAYWRIGHT_BROWSERS_PATH",
                    "PYTHONPATH",
                    "TMPDIR",
                    "USER",
                    "XDG_CACHE_HOME",
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                },
            )

    def test_registered_validation_nonzero_exit_identifies_the_exact_entry(self) -> None:
        repository = registry_entry("SecPal/.github")
        completed = [
            SimpleNamespace(returncode=0),
            SimpleNamespace(
                returncode=17,
                stdout="token=github_pat_command_output_must_not_leak",
                stderr="secret=command-output-must-not-leak",
            ),
        ]
        with (
            mock.patch.object(
                actions,
                "_validation_executable",
                return_value="/usr/bin/true",
            ),
            mock.patch.object(
                actions.subprocess,
                "run",
                side_effect=completed,
            ) as run,
        ):
            result = actions._run_registered_validations(repository, REPO_ROOT)

        self.assertFalse(result)
        self.assertEqual(
            result.failure_report(),
            {
                "category": "non-zero exit",
                "index": 2,
                "purpose": "Run lint",
            },
        )
        self.assertNotIn("command-output", str(result.failure_report()))
        self.assertEqual(run.call_count, 2)

    def test_registered_validation_timeout_reports_no_command_output(self) -> None:
        repository = registry_entry("SecPal/.github")
        timeout = actions.subprocess.TimeoutExpired(
            ["npm", "run", "test"],
            30,
            output="github_pat_timeout_output_must_not_leak",
            stderr="secret=timeout-output-must-not-leak",
        )
        with (
            mock.patch.object(
                actions,
                "_validation_executable",
                return_value="/usr/bin/true",
            ),
            mock.patch.object(
                actions.subprocess,
                "run",
                side_effect=timeout,
            ) as run,
        ):
            result = actions._run_registered_validations(repository, REPO_ROOT)

        self.assertFalse(result)
        self.assertEqual(
            result.failure_report(),
            {
                "category": "timeout",
                "index": 1,
                "purpose": "Run tests",
            },
        )
        self.assertNotIn("timeout-output", str(result.failure_report()))
        self.assertEqual(run.call_count, 1)

    def test_registered_validation_unavailable_executable_is_actionable(self) -> None:
        repository = registry_entry("SecPal/.github")
        with (
            mock.patch.object(
                actions,
                "_validation_executable",
                side_effect=actions.RegistryError(
                    "unavailable secret=resolution-detail-must-not-leak"
                ),
            ),
            mock.patch.object(actions.subprocess, "run") as run,
        ):
            result = actions._run_registered_validations(repository, REPO_ROOT)

        self.assertFalse(result)
        self.assertEqual(
            result.failure_report(),
            {
                "category": "unavailable executable",
                "index": 1,
                "purpose": "Run tests",
            },
        )
        self.assertNotIn("resolution-detail", str(result.failure_report()))
        run.assert_not_called()

    def test_registered_validation_unavailable_working_directory_is_actionable(
        self,
    ) -> None:
        repository = registry_entry("SecPal/.github")
        repository["focused_validation"] = []
        repository["required_local_validation"] = [
            {
                "argv": ["npm", "run", "test"],
                "working_directory": "missing",
                "purpose": "Run tests",
            }
        ]
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            mock.patch.object(actions, "_validation_executable") as executable,
            mock.patch.object(actions.subprocess, "run") as run,
        ):
            result = actions._run_registered_validations(
                repository,
                Path(temporary_directory),
            )

        self.assertFalse(result)
        self.assertEqual(
            result.failure_report(),
            {
                "category": "unavailable working directory",
                "index": 1,
                "purpose": "Run tests",
            },
        )
        executable.assert_not_called()
        run.assert_not_called()

    def test_registered_validation_unsafe_working_directory_stays_blocked(
        self,
    ) -> None:
        repository = registry_entry("SecPal/.github")
        repository["focused_validation"] = []
        repository["required_local_validation"] = [
            {
                "argv": ["npm", "run", "test"],
                "working_directory": "linked-outside",
                "purpose": "Run tests",
            }
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            repository_root = temporary / "repository"
            outside = temporary / "outside"
            repository_root.mkdir()
            outside.mkdir()
            (repository_root / "linked-outside").symlink_to(
                outside,
                target_is_directory=True,
            )
            with (
                mock.patch.object(actions, "_validation_executable") as executable,
                mock.patch.object(actions.subprocess, "run") as run,
            ):
                result = actions._run_registered_validations(
                    repository,
                    repository_root,
                )

        self.assertFalse(result)
        self.assertEqual(
            result.failure_report(),
            {
                "category": "unsafe working directory",
                "index": 1,
                "purpose": "Run tests",
            },
        )
        executable.assert_not_called()
        run.assert_not_called()

    def test_registered_validation_execution_error_discards_details_and_stops(
        self,
    ) -> None:
        repository = registry_entry("SecPal/.github")
        execution_error = OSError("secret=execution-detail-must-not-leak")
        with (
            mock.patch.object(
                actions,
                "_validation_executable",
                return_value="/usr/bin/true",
            ),
            mock.patch.object(
                actions.subprocess,
                "run",
                side_effect=execution_error,
            ) as run,
        ):
            result = actions._run_registered_validations(repository, REPO_ROOT)

        self.assertFalse(result)
        self.assertEqual(
            result.failure_report(),
            {
                "category": "execution error",
                "index": 1,
                "purpose": "Run tests",
            },
        )
        self.assertNotIn("execution-detail", str(result.failure_report()))
        self.assertEqual(run.call_count, 1)

    def test_complete_validation_excludes_focused_only_commands(self) -> None:
        repository = actions.select_repository(
            actions.load_registry(), "SecPal/frontend"
        )

        with (
            mock.patch.object(
                actions,
                "_validation_executable",
                return_value="/usr/bin/true",
            ),
            mock.patch.object(
                actions.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ) as run,
        ):
            self.assertTrue(
                actions._run_registered_validations(repository, REPO_ROOT)
            )

        executed_scripts = [call.args[0][-1] for call in run.call_args_list]
        self.assertEqual(
            executed_scripts,
            [
                "test:migration-boundary",
                "test:ui-csp",
                "format:check",
                "lint",
                "typecheck",
                "test:ci",
                "build:web",
                "build:android",
            ],
        )
        self.assertNotIn("test:e2e:csp", executed_scripts)
        self.assertNotIn("test:container", executed_scripts)
        self.assertNotIn("test:e2e:container", executed_scripts)

    def test_complete_validation_binding_excludes_focused_only_commands(self) -> None:
        repository = actions.select_repository(
            actions.load_registry(), "SecPal/frontend"
        )

        binding = actions._fast_registry_binding(repository)

        self.assertEqual(
            [command["argv"] for command in binding["validation"]],
            [
                ["npm", "run", "test:migration-boundary"],
                ["npm", "run", "test:ui-csp"],
                ["npm", "run", "format:check"],
                ["npm", "run", "lint"],
                ["npm", "run", "typecheck"],
                ["npm", "run", "test:ci"],
                ["npm", "run", "build:web"],
                ["npm", "run", "build:android"],
            ],
        )
        self.assertEqual(
            [command["argv"] for command in binding["focused_only_validation"]],
            [
                ["npm", "run", "test:e2e:csp"],
                ["npm", "run", "test:container"],
                ["npm", "run", "test:e2e:container"],
            ],
        )

    def test_deployment_validation_binding_separates_preflight_from_integration(
        self,
    ) -> None:
        repository = actions.select_repository(
            actions.load_registry(), "SecPal/deployment"
        )

        self.assertEqual(
            [command["argv"] for command in actions._complete_validation_commands(repository)],
            [["./scripts/preflight.sh"]],
        )
        binding = actions._fast_registry_binding(repository)
        self.assertEqual(
            [command["argv"] for command in binding["validation"]],
            [["./scripts/preflight.sh"]],
        )
        self.assertEqual(
            [command["argv"] for command in binding["focused_only_validation"]],
            [["./scripts/local-integration.sh"]],
        )

    def test_required_validation_rejects_focused_only_execution(self) -> None:
        registry = {
            "schema_version": "1.0",
            "fixed_thread_resolution": copy.deepcopy(
                actions.load_registry()["fixed_thread_resolution"]
            ),
            "repositories": [frontend_registry_entry()],
        }
        registry["repositories"][0]["required_local_validation"][0][
            "execution_policy"
        ] = "focused-only"

        with self.assertRaisesRegex(
            actions.RegistryError,
            "required local validation cannot use focused-only execution",
        ):
            actions.validate_registry(registry)


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


def fast_feedback(thread_count: int = 2, *, head_sha: str = p21.HEAD) -> Any:
    return fast_path.StableFeedbackState.from_payload(
        {
            "repository": "SecPal/.github",
            "pull_request_number": 1,
            "head_sha": head_sha,
            "base_ref": "main",
            "base_sha": p21.BASE,
            "pr_state": "OPEN",
            "pull_request_reactions": [],
            "reviews": [
                {
                    "node_id": "REVIEW_1",
                    "body_digest": digest("review summary"),
                    "actor": {"login": "reviewer", "node_id": "ACTOR_1", "database_id": 7},
                    "state": "COMMENTED",
                    "commit_oid": head_sha,
                    "reactions": [],
                }
            ],
            "conversation_comments": [],
            "threads": [
                {
                    "node_id": f"THREAD_{index}",
                    "is_resolved": False,
                    "is_outdated": False,
                    "comments": [
                        {
                            "node_id": f"COMMENT_{index}",
                            "body_digest": digest(f"finding {index}"),
                            "actor": {
                                "login": "reviewer",
                                "node_id": "ACTOR_1",
                                "database_id": 7,
                            },
                            "reply_to_id": None,
                            "reactions": [],
                        }
                    ],
                }
                for index in range(1, thread_count + 1)
            ],
            "required_checks": [{"name": "tests", "state": "SUCCESS"}],
        }
    )


def fast_registry() -> dict[str, Any]:
    return {
        "repository": "SecPal/.github",
        "default_branch": "main",
        "allowed_base_repositories": ["SecPal/.github"],
        "manual_gates": [],
        "signature_policy": {
            "accepted_formats": ["ssh", "openpgp"],
        },
        "check_policy": {
            "require_ruleset_evidence": True,
            "require_branch_protection_evidence": True,
            "expected_skipped": "block",
        },
        "limits": {
            "maximum_api_calls": 200,
            "maximum_items": 10000,
        },
        "validation": [
            {
                "argv": [
                    "python3",
                    "-m",
                    "unittest",
                    "tests/secpal-pr-review-actions-unit.py",
                ],
                "working_directory": ".",
            }
        ],
    }


def fast_attestation(reviewed: Any, *, head_sha: str = p21.HEAD) -> dict[str, Any]:
    registry = fast_registry()
    receipt = fast_path.create_validation_receipt(
        repository="SecPal/.github",
        head_sha=reviewed.head_sha,
        validated_tree_sha="a" * 40,
        registry=registry,
        command_set=registry["validation"],
        successful_result=True,
        reviewed_state=reviewed,
        manual_gate_evidence=[],
    )
    return fast_path.create_validation_attestation(
        repository="SecPal/.github",
        head_sha=head_sha,
        registry=registry,
        command_set=registry["validation"],
        successful_result=True,
        reviewed_state=reviewed,
        validation_receipt=receipt,
    )


def ready_integration_evidence(
    reviewed: Any,
    *,
    validated_tree: str,
    registry: dict[str, Any] | None = None,
    remediation_cycles: int = 1,
    exceptional_recoveries: int = 1,
    exceptional_continuations: int = 0,
) -> dict[str, Any]:
    registry = registry or fast_registry()
    authority = ready_integration_prior_authority(
        reviewed,
        remediation_cycles=remediation_cycles,
        exceptional_recoveries=exceptional_recoveries,
        exceptional_continuations=exceptional_continuations,
    )
    return {
        "schema_version": "1.1",
        "kind": "TWO_PARENT_READY_INTEGRATION",
        "authorization_id": "ready-integration-authorization-001",
        "repository": reviewed.repository,
        "delivery_issue_number": 9,
        "pull_request_number": reviewed.pull_request_number,
        "prior_delivery_head_sha": reviewed.head_sha,
        "prior_authority_digest": fast_path.digest_json(authority),
        "prior_authority_tag_object_sha": "1" * 40,
        "target_base": {
            "ref": reviewed.base_ref,
            "authorized_sha": reviewed.base_sha,
            "observed_sha": reviewed.base_sha,
        },
        "ordered_parent_shas": [reviewed.head_sha, reviewed.base_sha],
        "validated_tree_sha": validated_tree,
        "mechanical_merge_tree_sha": validated_tree,
        "mechanical_conflict_paths": [],
        "manual_conflict_resolution_delta": [],
        "reviewed_state_digest": reviewed.state_digest,
        "reviewed_feedback_digest": reviewed.feedback_digest,
        "validation_execution": {
            "registry_digest": fast_path.digest_json(registry),
            "command_set_digest": fast_path.digest_json(registry["validation"]),
        },
        "expected_signer": {
            "kind": "SSH_PRINCIPAL",
            "identity": "aroviqen",
        },
        "eligibility": {
            "eligible": True,
            "lifecycle_identity": "delivery-lifecycle-001",
            "draft_before": False,
            "draft_after": False,
            "ready_before": True,
            "ready_after": True,
            "ready_transition": False,
            "review_requested": False,
            "unrestricted_reviews_before": 1,
            "unrestricted_reviews_after": 1,
            "remediation_cycles_before": remediation_cycles,
            "remediation_cycles_after": remediation_cycles,
            "exceptional_recoveries_before": exceptional_recoveries,
            "exceptional_recoveries_after": exceptional_recoveries,
            "exceptional_continuations_before": exceptional_continuations,
            "exceptional_continuations_after": exceptional_continuations,
            "cycle_3": False,
        },
    }


def authenticated_integration_commit(
    head_sha: str,
    integration: dict[str, Any],
    *,
    signer: str = "aroviqen",
) -> fast_path.AuthenticatedIntegrationCommit:
    git_results = [
        subprocess.CompletedProcess(
            [], 0, "gpgsig -----BEGIN SSH SIGNATURE-----\n\n", ""
        ),
        subprocess.CompletedProcess(
            [],
            0,
            f'Good "git" signature for {signer} with ED25519 key SHA256:test\n',
            "",
        ),
    ]
    with mock.patch.object(
        fast_path, "_run_integration_commit_git", side_effect=git_results
    ):
        return fast_path.authenticate_integration_commit(
            repository_root=REPO_ROOT,
            head_sha=head_sha,
            expected_signer=integration["expected_signer"],
            signature_policy=fast_registry()["signature_policy"],
        )


def ready_integration_prior_authority(
    reviewed: Any,
    *,
    remediation_cycles: int = 1,
    exceptional_recoveries: int = 1,
    exceptional_continuations: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
        "repository": reviewed.repository,
        "delivery_issue_number": 9,
        "pull_request_number": reviewed.pull_request_number,
        "prior_delivery_head_sha": reviewed.head_sha,
        "prior_delivery_tree_sha": "a" * 40,
        "prior_validation_receipt_digest": "b" * 64,
        "prior_final_attestation_digest": "c" * 64,
        "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": "aroviqen"},
        "lifecycle": {
            "identity": "delivery-lifecycle-001",
            "current_authority_digest": "d" * 64,
            "historical_proof_mode": "legacy_migration_checkpoint",
            "draft": False,
            "ready": True,
            "ready_transition": False,
            "unrestricted_reviews": 1,
            "remediation_cycles": remediation_cycles,
            "exceptional_recoveries": exceptional_recoveries,
            "exceptional_continuations": exceptional_continuations,
            "cycle_3": False,
        },
        "publication": {
            "object_oid": "e" * 40,
            "publication_digest": "f" * 64,
        },
    }


def fast_request(
    reviewed: Any,
    thread_count: int = 2,
    *,
    cover_top_level: bool = True,
    cover_reactions: bool = True,
) -> Any:
    reviewed_threads = {
        item["node_id"]: item for item in reviewed.feedback["threads"]
    }
    receipt_digest = fast_attestation(reviewed)["validation_receipt_digest"]
    findings: list[dict[str, Any]] = []
    operation_finding_ids: dict[str, list[str]] = {}

    def add_finding(
        finding_id: str,
        thread_id: str | None,
        sources: list[dict[str, str]],
        *,
        classification: str = "INFORMATIONAL",
        disposition: str = "NON_ACTIONABLE",
    ) -> None:
        fixed = disposition in fast_path.FIXED_DISPOSITIONS
        findings.append(
            {
                "finding_id": finding_id,
                "thread_id": thread_id,
                "sources": sources,
                "source_subitem_id": None,
                "classification": classification,
                "disposition": disposition,
                "evidence_digest": digest(f"finding evidence {finding_id}"),
                "test_evidence_digest": receipt_digest if fixed else None,
                "commit_sha": p21.HEAD if fixed else None,
                "canonical_finding_id": None,
                "follow_up": None,
            }
        )
        if thread_id is not None:
            operation_finding_ids.setdefault(thread_id, []).append(finding_id)

    for index in range(1, thread_count + 1):
        thread_id = f"THREAD_{index}"
        thread = reviewed_threads[thread_id]
        add_finding(
            f"finding-{index}",
            thread_id,
            [
                {
                    "kind": "THREAD_COMMENT",
                    "node_id": item["node_id"],
                    "digest": item["body_digest"],
                }
                for item in thread["comments"]
            ],
            classification="VALID_ACTIONABLE",
            disposition="CORRECTED_AND_VERIFIED",
        )
        if cover_reactions:
            for comment_index, comment in enumerate(thread["comments"], 1):
                for reaction_index, reaction in enumerate(comment["reactions"], 1):
                    add_finding(
                        f"finding-{index}-comment-{comment_index}-reaction-{reaction_index}",
                        thread_id,
                        [
                            {
                                "kind": "THREAD_COMMENT_REACTION",
                                "node_id": reaction["mutation_id"],
                                "digest": fast_path.digest_json(reaction),
                            }
                        ],
                    )

    if cover_top_level:
        for index, reaction in enumerate(
            reviewed.feedback["pull_request_reactions"], 1
        ):
            add_finding(
                f"finding-pr-reaction-{index}",
                None,
                [
                    {
                        "kind": "PULL_REQUEST_REACTION",
                        "node_id": reaction["mutation_id"],
                        "digest": fast_path.digest_json(reaction),
                    }
                ],
            )
        for index, review in enumerate(reviewed.feedback["reviews"], 1):
            add_finding(
                f"finding-review-{index}",
                None,
                [
                    {
                        "kind": "REVIEW",
                        "node_id": review["node_id"],
                        "digest": review["body_digest"],
                    }
                ],
            )
            if cover_reactions:
                for reaction_index, reaction in enumerate(review["reactions"], 1):
                    add_finding(
                        f"finding-review-{index}-reaction-{reaction_index}",
                        None,
                        [
                            {
                                "kind": "REVIEW_REACTION",
                                "node_id": reaction["mutation_id"],
                                "digest": fast_path.digest_json(reaction),
                            }
                        ],
                    )
        for index, comment in enumerate(
            reviewed.feedback["conversation_comments"], 1
        ):
            add_finding(
                f"finding-conversation-{index}",
                None,
                [
                    {
                        "kind": "CONVERSATION_COMMENT",
                        "node_id": comment["node_id"],
                        "digest": comment["body_digest"],
                    }
                ],
            )
            if cover_reactions:
                for reaction_index, reaction in enumerate(comment["reactions"], 1):
                    add_finding(
                        f"finding-conversation-{index}-reaction-{reaction_index}",
                        None,
                        [
                            {
                                "kind": "CONVERSATION_REACTION",
                                "node_id": reaction["mutation_id"],
                                "digest": fast_path.digest_json(reaction),
                            }
                        ],
                    )

    return fast_path.BatchRequest.from_dict(
        {
            "schema_version": "1.3",
            "batch_id": "batch-001",
            "repository": "SecPal/.github",
            "pull_request_number": 1,
            "expected_head_sha": p21.HEAD,
            "expected_base_ref": reviewed.base_ref,
            "expected_base_sha": reviewed.base_sha,
            "expected_actor": {
                "login": "aroviqen",
                "node_id": "USER_1",
                "database_id": 7,
            },
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "findings": findings,
            "operations": [
                {
                    "operation_id": f"resolve-{index}",
                    "kind": "THREAD_RESOLUTION",
                    "thread_id": f"THREAD_{index}",
                    "finding_ids": operation_finding_ids[f"THREAD_{index}"],
                }
                for index in range(1, thread_count + 1)
            ]
        }
    )


class FakeFastGateway:
    def __init__(self, current_feedback: Any, validated_feedback: Any | None = None) -> None:
        self.current_feedback = current_feedback
        self.validated_feedback = validated_feedback or current_feedback
        self.calls: list[tuple[str, str]] = []
        self.checks = [
            {
                "stable_id": "check_run:tests",
                "name": "tests",
                "application": {"database_id": 1},
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "is_effective": True,
            }
        ]
        self.required_specs = [{"context": "tests", "integration_id": 1}]
        self.commits = [
            {
                "oid": p21.HEAD,
                "source": "USER",
                "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
                "github_verification": {"verified": True, "reason": "valid"},
            }
        ]
        self.fail_feedback_reads = 0
        self.fail_at_write: int | None = None
        self.unknown_at_write: int | None = None
        self.write_attempts: dict[str, int] = {}
        self.snapshot_calls = 0
        self.validation_runs = 0
        self.fail_target: str | None = None
        self.target_pr_state = "OPEN"
        self.target_base_ref = current_feedback.base_ref
        self.target_base_sha = current_feedback.base_sha
        self.target_mergeability = "MERGEABLE"
        self.target_merge_state_status = "CLEAN"

    def read_preflight(self, request: Any) -> Any:
        self.calls.append(("READ", "preflight"))
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=self.validated_feedback.head_sha,
            validated_tree_sha="a" * 40,
            registry=fast_registry(),
            command_set=fast_registry()["validation"],
            successful_result=True,
            reviewed_state=self.validated_feedback,
            manual_gate_evidence=[],
        )
        return fast_path.ReadinessState(
            repository="SecPal/.github",
            pull_request_number=1,
            head_sha=request.expected_head_sha,
            base_ref="main",
            base_sha=p21.BASE,
            base_repository="SecPal/.github",
            local_head_sha=request.expected_head_sha,
            remote_head_sha=request.expected_head_sha,
            head_parent_sha=self.validated_feedback.head_sha,
            head_tree_sha="a" * 40,
            validation_receipt_digest=receipt["receipt_digest"],
            worktree_clean=True,
            pull_request_open=True,
            mergeability="MERGEABLE",
            merge_state_status="CLEAN",
            actor={"login": "aroviqen", "node_id": "USER_1", "database_id": 7},
            commits=copy.deepcopy(self.commits),
        )

    def read_required_checks(
        self, _request: Any, _registry: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("READ", "required-checks"))
        return {
            "checks": copy.deepcopy(self.checks),
            "required_specs": copy.deepcopy(self.required_specs),
            "strict_base_required": False,
        }

    def read_stable_feedback(self, _request: Any) -> Any:
        self.calls.append(("READ", "stable-feedback"))
        if self.fail_feedback_reads:
            self.fail_feedback_reads -= 1
            raise fast_path.TransientReadFailure("temporary transport failure")
        return copy.deepcopy(self.current_feedback)

    def read_thread_target(self, _request: Any, operation_value: Any) -> dict[str, Any]:
        self.calls.append(("READ", f"target:{operation_value.thread_id}"))
        if self.fail_target == operation_value.thread_id:
            raise fast_path.TransientReadFailure("target read remained unavailable")
        thread = next(
            item
            for item in self.current_feedback.feedback["threads"]
            if item["node_id"] == operation_value.thread_id
        )
        return {
            "thread_id": operation_value.thread_id,
            "head_sha": self.current_feedback.head_sha,
            "pr_state": self.target_pr_state,
            "base_ref": self.target_base_ref,
            "base_sha": self.target_base_sha,
            "mergeability": self.target_mergeability,
            "merge_state_status": self.target_merge_state_status,
            "is_resolved": thread["is_resolved"],
            "thread": copy.deepcopy(thread),
        }

    def resolve_thread(self, _request: Any, operation_value: Any) -> dict[str, Any]:
        self.calls.append(("WRITE", operation_value.thread_id))
        attempt = self.write_attempts.get(operation_value.thread_id, 0) + 1
        self.write_attempts[operation_value.thread_id] = attempt
        write_number = sum(self.write_attempts.values())
        if self.unknown_at_write == write_number:
            raise fast_path.UnknownWriteResult("mutation response was lost")
        if self.fail_at_write == write_number:
            raise fast_path.MutationFailure("mutation was rejected")
        return {"thread_id": operation_value.thread_id, "is_resolved": True}


class FastPathTests(TestCase):
    def test_integration_tree_delta_recurses_to_exact_nested_leaf_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="secpal-integration-delta-") as directory:
            repository = Path(directory)

            def git(*arguments: str) -> str:
                return subprocess.run(
                    ["git", *arguments],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("init", "-q")
            git("config", "user.name", "Integration Delta Fixture")
            git("config", "user.email", "integration-delta@example.test")
            docs = repository / "docs"
            docs.mkdir()
            workflow = docs / "secpal-pr-review-workflow.md"
            sibling = docs / "sibling.md"
            workflow.write_text("base workflow\n", encoding="utf-8")
            sibling.write_text("base sibling\n", encoding="utf-8")
            (repository / "CHANGELOG.md").write_text("base changelog\n", encoding="utf-8")
            git("add", ".")
            mechanical_tree = git("write-tree")

            self.assertEqual(
                actions._integration_tree_delta(
                    repository, mechanical_tree, mechanical_tree
                ),
                [],
            )

            workflow.write_text("resolved workflow\n", encoding="utf-8")
            git("add", "docs/secpal-pr-review-workflow.md")
            nested_tree = git("write-tree")
            nested_delta = actions._integration_tree_delta(
                repository, mechanical_tree, nested_tree
            )
            self.assertEqual(
                [entry["path"] for entry in nested_delta],
                ["docs/secpal-pr-review-workflow.md"],
            )
            self.assertEqual(
                {entry["path"] for entry in nested_delta},
                {"docs/secpal-pr-review-workflow.md"},
            )

            sibling.write_text("unauthorized sibling\n", encoding="utf-8")
            git("add", "docs/sibling.md")
            sibling_tree = git("write-tree")
            sibling_delta = actions._integration_tree_delta(
                repository, mechanical_tree, sibling_tree
            )
            authenticated_conflicts = {"docs/secpal-pr-review-workflow.md"}
            self.assertEqual(
                {entry["path"] for entry in sibling_delta} - authenticated_conflicts,
                {"docs/sibling.md"},
            )

            git("reset", "-q", "--hard")
            git("read-tree", mechanical_tree)
            (repository / "CHANGELOG.md").write_text(
                "resolved changelog\n", encoding="utf-8"
            )
            git("add", "CHANGELOG.md")
            top_level_tree = git("write-tree")
            self.assertEqual(
                [
                    entry["path"]
                    for entry in actions._integration_tree_delta(
                        repository, mechanical_tree, top_level_tree
                    )
                ],
                ["CHANGELOG.md"],
            )

    def execute(self, reviewed: Any, gateway: FakeFastGateway, count: int = 2) -> dict[str, Any]:
        return fast_path.execute_resolution_batch(
            fast_request(reviewed, count),
            fast_attestation(reviewed),
            reviewed,
            fast_registry(),
            gateway,
        )

    def test_thirty_threads_share_one_attestation_checks_and_feedback_read(self) -> None:
        reviewed = fast_feedback(30)
        gateway = FakeFastGateway(reviewed)
        with mock.patch.object(
            fast_path,
            "verify_validation_attestation",
            wraps=fast_path.verify_validation_attestation,
        ) as verify_attestation:
            result = self.execute(reviewed, gateway, 30)
        self.assertEqual(result["status"], "BATCH_APPLIED")
        self.assertEqual(len(result["applied"]), 30)
        self.assertEqual(verify_attestation.call_count, 1)
        self.assertEqual(gateway.calls.count(("READ", "required-checks")), 1)
        self.assertEqual(gateway.calls.count(("READ", "stable-feedback")), 1)
        self.assertEqual(sum(kind == "WRITE" for kind, _ in gateway.calls), 30)
        self.assertEqual(gateway.validation_runs, 0)
        self.assertEqual(gateway.snapshot_calls, 0)

    def test_normal_two_thread_batch_has_no_package_snapshot_dependency(self) -> None:
        reviewed = fast_feedback()
        gateway = FakeFastGateway(reviewed)
        self.assertEqual(self.execute(reviewed, gateway)["status"], "BATCH_APPLIED")
        self.assertNotIn(("READ", "package-2.1-snapshot"), gateway.calls)
        self.assertNotIn(("READ", "package-2.2-snapshot"), gateway.calls)

    def test_legacy_batch_without_classified_findings_is_rejected(self) -> None:
        reviewed = fast_feedback(1)
        payload = fast_request(reviewed, 1).to_dict()
        payload["schema_version"] = "1.0"
        payload.pop("findings", None)
        payload["operations"] = [
            {
                "operation_id": "resolve-1",
                "kind": "THREAD_RESOLUTION",
                "thread_id": "THREAD_1",
                "disposition": "NON_ACTIONABLE",
            }
        ]
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.BatchRequest.from_dict(payload)

    def test_batch_rejects_secret_like_identifiers(self) -> None:
        payload = fast_request(fast_feedback()).to_dict()
        payload["batch_id"] = "github_pat_example"
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "secret"):
            fast_path.BatchRequest.from_dict(payload)

    def test_batch_rejects_incompatible_classification_and_disposition(self) -> None:
        payload = fast_request(fast_feedback()).to_dict()
        payload["findings"][0].update(
            classification="INFORMATIONAL",
            disposition="CORRECTED_AND_VERIFIED",
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "incompatible"):
            fast_path.BatchRequest.from_dict(payload)

    def test_fast_batch_binds_tracked_follow_up_into_authorization(self) -> None:
        payload = fast_request(fast_feedback(1), 1).to_dict()
        payload["schema_version"] = "1.3"
        for item in payload["findings"]:
            item["follow_up"] = None
        payload["findings"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            test_evidence_digest=None,
            commit_sha=None,
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        request = fast_path.BatchRequest.from_dict(payload)

        changed = copy.deepcopy(payload)
        changed["findings"][0]["follow_up"] = {
            "repository": "SecPal/api",
            "issue_number": 124,
            "issue_url": "https://github.com/SecPal/api/issues/124",
        }
        changed_request = fast_path.BatchRequest.from_dict(changed)

        self.assertNotEqual(
            request.authorization_digest,
            changed_request.authorization_digest,
        )

    def test_fast_batch_requires_authenticated_simple_resolver_for_tracked_follow_up(self) -> None:
        reviewed = fast_feedback(1)
        payload = fast_request(reviewed, 1).to_dict()
        payload["findings"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            test_evidence_digest=None,
            commit_sha=None,
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        request = fast_path.BatchRequest.from_dict(payload)
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker,
            "authenticated simple resolver",
        ):
            fast_path.execute_resolution_batch(
                request,
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertEqual(gateway.calls, [])

    def test_batch_requires_finding_coverage_for_every_unresolved_thread(self) -> None:
        reviewed = fast_feedback()
        payload = fast_request(reviewed).to_dict()
        payload["findings"] = payload["findings"][:1]
        payload["operations"] = payload["operations"][:1]
        request = fast_path.BatchRequest.from_dict(payload)
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "every unresolved"):
            fast_path.execute_resolution_batch(
                request,
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertEqual(gateway.calls, [])

    def test_batch_finding_source_must_match_reviewed_comment(self) -> None:
        reviewed = fast_feedback()
        payload = fast_request(reviewed).to_dict()
        payload["findings"][0]["sources"][0]["digest"] = digest(
            "forged source"
        )
        request = fast_path.BatchRequest.from_dict(payload)
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "source"):
            fast_path.execute_resolution_batch(
                request,
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertEqual(gateway.calls, [])

    def test_batch_finding_and_operation_counts_honor_registry_item_limit(self) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        registry["limits"]["maximum_items"] = 3
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "item limit"):
            fast_path.execute_resolution_batch(
                fast_request(reviewed),
                fast_attestation(reviewed),
                reviewed,
                registry,
                gateway,
            )
        self.assertEqual(gateway.calls, [])

    def test_corrected_finding_must_bind_the_remediation_head(self) -> None:
        reviewed = fast_feedback()
        alternate_commit = "f" * 40
        payload = fast_request(reviewed).to_dict()
        payload["findings"][0]["commit_sha"] = alternate_commit
        request = fast_path.BatchRequest.from_dict(payload)
        gateway = FakeFastGateway(reviewed)
        gateway.commits.append(
            {
                "oid": alternate_commit,
                "source": "USER",
                "local_signature": {
                    "verified": True,
                    "state": "valid",
                    "format": "ssh",
                },
                "github_verification": {"verified": True, "reason": "valid"},
            }
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "remediation head"):
            fast_path.execute_resolution_batch(
                request,
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_caller_authored_prior_results_are_rejected(self) -> None:
        request = fast_request(fast_feedback(1), 1)
        payload = request.to_dict()
        payload["prior_results"] = [
            {
                "operation_id": "resolve-1",
                "thread_id": "THREAD_1",
                "authorization_digest": request.authorization_digest,
                "mutation_identity": "THREAD_1",
                "status": "APPLIED",
            }
        ]
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "prior"):
            fast_path.BatchRequest.from_dict(payload)

    def test_non_open_reviewed_state_blocks_before_live_reads(self) -> None:
        reviewed = fast_feedback(1)
        reviewed.pr_state = "CLOSED"
        reviewed.refresh_digests()
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "reviewed.*open"):
            self.execute(reviewed, gateway, 1)
        self.assertEqual(gateway.calls, [])

    def test_unclassified_top_level_feedback_blocks_before_live_reads(self) -> None:
        for label, add_feedback in (
            (
                "review",
                lambda state: state.feedback["reviews"].append(
                    {
                        "node_id": "REVIEW_TOP_LEVEL",
                        "body_digest": digest("material review body"),
                        "actor": {
                            "login": "reviewer",
                            "node_id": "ACTOR_1",
                            "database_id": 7,
                        },
                        "state": "COMMENTED",
                        "commit_oid": p21.HEAD,
                        "reactions": [],
                    }
                ),
            ),
            (
                "conversation comment",
                lambda state: state.feedback["conversation_comments"].append(
                    {
                        "node_id": "COMMENT_TOP_LEVEL",
                        "body_digest": digest("material conversation comment"),
                        "actor": {
                            "login": "reviewer",
                            "node_id": "ACTOR_1",
                            "database_id": 7,
                        },
                        "updated_at": "2026-07-21T00:00:00Z",
                        "reactions": [],
                    }
                ),
            ),
        ):
            with self.subTest(label=label):
                reviewed = fast_feedback(1)
                add_feedback(reviewed)
                reviewed.refresh_digests()
                request = fast_request(reviewed, 1, cover_top_level=False)
                gateway = FakeFastGateway(reviewed)
                with self.assertRaisesRegex(fast_path.SecurityBlocker, "coverage"):
                    fast_path.execute_resolution_batch(
                        request,
                        fast_attestation(reviewed),
                        reviewed,
                        fast_registry(),
                        gateway,
                    )
                self.assertEqual(gateway.calls, [])

    def test_unclassified_reactions_block_before_live_reads(self) -> None:
        for label, add_reaction in (
            (
                "pull request",
                lambda state, reaction: state.feedback[
                    "pull_request_reactions"
                ].append(reaction),
            ),
            (
                "thread comment",
                lambda state, reaction: state.feedback["threads"][0]["comments"][
                    0
                ]["reactions"].append(reaction),
            ),
        ):
            with self.subTest(label=label):
                reviewed = fast_feedback(1)
                reaction = {
                    "mutation_id": f"REACTION_{label.replace(' ', '_')}",
                    "content": "THUMBS_UP",
                    "actor": {
                        "login": "reviewer",
                        "node_id": "ACTOR_1",
                        "database_id": 7,
                    },
                }
                add_reaction(reviewed, reaction)
                reviewed.refresh_digests()
                request = fast_request(
                    reviewed,
                    1,
                    cover_top_level=False,
                    cover_reactions=False,
                )
                gateway = FakeFastGateway(reviewed)
                with self.assertRaisesRegex(fast_path.SecurityBlocker, "coverage"):
                    fast_path.execute_resolution_batch(
                        request,
                        fast_attestation(reviewed),
                        reviewed,
                        fast_registry(),
                        gateway,
                )
                self.assertEqual(gateway.calls, [])

    def test_pr_eyes_reaction_rotation_is_not_stable_feedback(self) -> None:
        payload = fast_feedback(1).to_dict()

        def eyes(identity: str) -> dict[str, Any]:
            return {
                "mutation_id": identity,
                "content": "EYES",
                "actor": {
                    "login": "reviewer",
                    "node_id": "ACTOR_1",
                    "database_id": 7,
                },
            }

        payload["pull_request_reactions"] = [eyes("REACTION_PR_1")]
        first = fast_path.StableFeedbackState.from_payload(payload)
        payload["pull_request_reactions"] = [eyes("REACTION_PR_2")]
        payload["reviews"][0]["reactions"] = [eyes("REACTION_REVIEW")]
        second = fast_path.StableFeedbackState.from_payload(payload)

        self.assertEqual(first.feedback["pull_request_reactions"], [])
        self.assertEqual(second.feedback["pull_request_reactions"], [])
        self.assertEqual(
            second.feedback["reviews"][0]["reactions"][0]["mutation_id"],
            "REACTION_REVIEW",
        )
        payload["reviews"][0]["reactions"] = []
        second_without_nested_reaction = fast_path.StableFeedbackState.from_payload(
            payload
        )
        self.assertEqual(
            first.feedback_digest,
            second_without_nested_reaction.feedback_digest,
        )

    def test_complete_feedback_source_taxonomy_is_classified(self) -> None:
        reviewed = fast_feedback(1)

        def reaction(identity: str) -> dict[str, Any]:
            return {
                "mutation_id": identity,
                "content": "THUMBS_UP",
                "actor": {
                    "login": "reviewer",
                    "node_id": "ACTOR_1",
                    "database_id": 7,
                },
            }

        reviewed.feedback["pull_request_reactions"].append(reaction("REACTION_PR"))
        reviewed.feedback["reviews"].append(
            {
                "node_id": "REVIEW_TOP_LEVEL",
                "body_digest": digest("review body"),
                "actor": {
                    "login": "reviewer",
                    "node_id": "ACTOR_1",
                    "database_id": 7,
                },
                "state": "COMMENTED",
                "commit_oid": p21.HEAD,
                "reactions": [reaction("REACTION_REVIEW")],
            }
        )
        reviewed.feedback["conversation_comments"].append(
            {
                "node_id": "COMMENT_TOP_LEVEL",
                "body_digest": digest("conversation body"),
                "actor": {
                    "login": "reviewer",
                    "node_id": "ACTOR_1",
                    "database_id": 7,
                },
                "updated_at": "2026-07-21T00:00:00Z",
                "reactions": [reaction("REACTION_CONVERSATION")],
            }
        )
        reviewed.feedback["threads"][0]["comments"][0]["reactions"].append(
            reaction("REACTION_THREAD")
        )
        reviewed.refresh_digests()
        request = fast_request(reviewed, 1)
        observed_kinds = {
            source.kind
            for finding in request.findings
            for source in finding.sources
        }
        self.assertEqual(observed_kinds, fast_path.SOURCE_KINDS)
        result = fast_path.execute_resolution_batch(
            request,
            fast_attestation(reviewed),
            reviewed,
            fast_registry(),
            FakeFastGateway(reviewed),
        )
        self.assertEqual(result["status"], "BATCH_APPLIED")

    def test_fixed_finding_test_evidence_binds_validation_receipt(self) -> None:
        reviewed = fast_feedback(1)
        payload = fast_request(reviewed, 1).to_dict()
        payload["findings"][0]["test_evidence_digest"] = "f" * 64
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "test evidence"):
            fast_path.execute_resolution_batch(
                fast_path.BatchRequest.from_dict(payload),
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
        )
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_non_fixed_finding_rejects_fix_only_evidence(self) -> None:
        payload = fast_request(fast_feedback(1), 1).to_dict()
        payload["findings"][0].update(
            classification="INFORMATIONAL",
            disposition="NON_ACTIONABLE",
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "non-fixed"):
            fast_path.BatchRequest.from_dict(payload)

    def test_fast_policy_tables_match_the_legacy_resolution_invariants(self) -> None:
        self.assertEqual(fast_path.MERGE_STATE_POLICY, p21.review.MERGE_STATE_POLICY)
        self.assertEqual(
            set(fast_path.CLASSIFICATION_DISPOSITIONS) - {"OUTSIDE_PR_SCOPE"},
            actions.RESOLVABLE_CLASSIFICATIONS,
        )
        for classification, dispositions in fast_path.CLASSIFICATION_DISPOSITIONS.items():
            if classification == "OUTSIDE_PR_SCOPE":
                self.assertEqual(dispositions, {"TRACKED_AS_FOLLOW_UP"})
                self.assertFalse(dispositions & actions.RESOLVABLE_DISPOSITIONS)
                continue
            self.assertEqual(
                dispositions,
                actions.DISPOSITION_POLICY[classification]
                & actions.RESOLVABLE_DISPOSITIONS,
            )

    def test_fast_batch_schema_matches_runtime_security_policy(self) -> None:
        schema = json.loads(actions.FAST_BATCH_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.3")
        self.assertNotIn("prior_results", schema["properties"])
        self.assertEqual(
            set(schema["$defs"]["source"]["properties"]["kind"]["enum"]),
            fast_path.SOURCE_KINDS,
        )

    def test_fast_batch_schema_isolates_tracked_follow_up_classification(self) -> None:
        follow_up = {
            "repository": "SecPal/api",
            "issue_number": 123,
            "issue_url": "https://github.com/SecPal/api/issues/123",
        }
        tracked = fast_request(fast_feedback(1), 1).to_dict()
        tracked["findings"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            test_evidence_digest=None,
            commit_sha=None,
            follow_up=follow_up,
        )
        schema = json.loads(actions.FAST_BATCH_SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(tracked)

        untracked = copy.deepcopy(tracked)
        untracked["findings"][0].update(
            disposition="OUT_OF_SCOPE",
            follow_up=None,
        )
        validator.validate(untracked)

        classifications = schema["$defs"]["finding"]["properties"][
            "classification"
        ]["enum"]
        for classification in classifications:
            if classification == "OUTSIDE_PR_SCOPE":
                continue
            incompatible = copy.deepcopy(tracked)
            incompatible["findings"][0]["classification"] = classification
            with self.subTest(classification=classification), self.assertRaises(
                jsonschema.ValidationError
            ):
                validator.validate(incompatible)

    def test_actions_uses_the_canonical_fast_path_module(self) -> None:
        self.assertEqual(actions.fast_path.__name__, "secpal_pr_review.fast_path")
        self.assertIs(
            actions.fast_path,
            importlib.import_module("secpal_pr_review.fast_path"),
        )

    def test_fast_path_loader_rejects_a_preloaded_module_from_another_path(self) -> None:
        with mock.patch.dict(
            actions.sys.modules,
            {
                "secpal_pr_review.fast_path": SimpleNamespace(
                    __file__="/tmp/untrusted-fast-path.py"
                )
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected path"):
                actions._load_fast_path_helper()

    def test_fast_path_loader_removes_a_partially_initialized_module(self) -> None:
        module_name = "secpal_pr_review.fast_path"
        partial_module = SimpleNamespace(__file__=str(actions.FAST_PATH_HELPER))
        loader = SimpleNamespace(exec_module=mock.Mock(side_effect=SyntaxError("broken")))
        spec = SimpleNamespace(name=module_name, loader=loader)
        with (
            mock.patch.dict(actions.sys.modules, {module_name: None}),
            mock.patch.object(actions.importlib.util, "spec_from_file_location", return_value=spec),
            mock.patch.object(actions.importlib.util, "module_from_spec", return_value=partial_module),
        ):
            with self.assertRaisesRegex(SyntaxError, "broken"):
                actions._load_fast_path_helper()
            self.assertIsNone(actions.sys.modules.get(module_name))

    def test_batch_request_identity_must_match_reviewed_feedback(self) -> None:
        reviewed = fast_feedback()
        mismatches = {
            "repository": "SecPal/api",
            "pull_request_number": 2,
        }
        for field, value in mismatches.items():
            with self.subTest(field=field):
                payload = fast_request(reviewed).to_dict()
                payload[field] = value
                request = fast_path.BatchRequest.from_dict(payload)
                gateway = FakeFastGateway(reviewed)
                with self.assertRaisesRegex(
                    fast_path.SecurityBlocker,
                    "reviewed feedback identity",
                ):
                    fast_path.execute_resolution_batch(
                        request,
                        fast_attestation(reviewed),
                        reviewed,
                        fast_registry(),
                        gateway,
                    )
                self.assertEqual(gateway.calls, [])

    def test_batch_allows_the_attested_remediation_head_transition(self) -> None:
        reviewed = fast_feedback()
        remediation_head = "f" * 40
        current_payload = reviewed.to_dict()
        current_payload["head_sha"] = remediation_head
        current = fast_path.StableFeedbackState.from_payload(current_payload)
        payload = fast_request(reviewed).to_dict()
        payload["expected_head_sha"] = remediation_head
        for finding_value in payload["findings"]:
            if finding_value["disposition"] in fast_path.FIXED_DISPOSITIONS:
                finding_value["commit_sha"] = remediation_head
        gateway = FakeFastGateway(current, reviewed)
        gateway.commits.append(
            {
                "oid": remediation_head,
                "source": "USER",
                "local_signature": {
                    "verified": True,
                    "state": "valid",
                    "format": "ssh",
                },
                "github_verification": {"verified": True, "reason": "valid"},
            }
        )
        result = fast_path.execute_resolution_batch(
            fast_path.BatchRequest.from_dict(payload),
            fast_attestation(reviewed, head_sha=remediation_head),
            reviewed,
            fast_registry(),
            gateway,
        )
        self.assertEqual(result["status"], "BATCH_APPLIED")

    def test_attested_head_transition_allows_threads_to_become_outdated(self) -> None:
        reviewed = fast_feedback(1)
        remediation_head = "f" * 40
        current_payload = reviewed.to_dict()
        current_payload["head_sha"] = remediation_head
        current_payload["threads"][0]["is_outdated"] = True
        current = fast_path.StableFeedbackState.from_payload(current_payload)
        payload = fast_request(reviewed, 1).to_dict()
        payload["expected_head_sha"] = remediation_head
        payload["findings"][0]["commit_sha"] = remediation_head
        gateway = FakeFastGateway(current, reviewed)
        gateway.commits.append(
            {
                "oid": remediation_head,
                "source": "USER",
                "local_signature": {
                    "verified": True,
                    "state": "valid",
                    "format": "ssh",
                },
                "github_verification": {"verified": True, "reason": "valid"},
            }
        )
        result = fast_path.execute_resolution_batch(
            fast_path.BatchRequest.from_dict(payload),
            fast_attestation(reviewed, head_sha=remediation_head),
            reviewed,
            fast_registry(),
            gateway,
        )
        self.assertEqual(result["status"], "BATCH_APPLIED")

    def test_fast_registry_binds_default_branch_base_repository_and_manual_gates(self) -> None:
        entry = registry_entry("SecPal/.github")
        binding = actions._fast_registry_binding(entry)
        self.assertEqual(binding["default_branch"], "main")
        self.assertEqual(binding["allowed_base_repositories"], ["SecPal/.github"])
        self.assertEqual(binding["manual_gates"], entry["manual_gates"])

    def test_non_default_reviewed_base_blocks_before_live_reads(self) -> None:
        reviewed = fast_feedback()
        reviewed.base_ref = "release"
        reviewed.refresh_digests()
        gateway = FakeFastGateway(reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "default branch"):
            fast_path.execute_resolution_batch(
                fast_request(reviewed),
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertEqual(gateway.calls, [])

    def test_attestation_without_signed_validation_receipt_is_rejected(self) -> None:
        reviewed = fast_feedback()
        gateway = FakeFastGateway(reviewed)
        original = gateway.read_preflight

        def missing_receipt(request_value: Any) -> Any:
            readiness = original(request_value)
            readiness.validation_receipt_digest = None
            return readiness

        gateway.read_preflight = missing_receipt
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "validation receipt"):
            self.execute(reviewed, gateway)
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_manual_gate_evidence_is_bound_into_the_signed_receipt(self) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        registry["manual_gates"] = ["Confirm the exact changed-file validation."]
        evidence = [
            {
                "gate": registry["manual_gates"][0],
                "satisfied": True,
                "evidence": "pre-commit passed for the exact changed-file list",
            }
        ]
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha="a" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=evidence,
        )
        attestation = fast_path.create_validation_attestation(
            repository="SecPal/.github",
            head_sha=p21.HEAD,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            validation_receipt=receipt,
        )
        fast_path.verify_validation_attestation(
            attestation,
            repository="SecPal/.github",
            head_sha=p21.HEAD,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            commit_parent_sha=reviewed.head_sha,
            commit_tree_sha="a" * 40,
            commit_validation_receipt_digest=receipt["receipt_digest"],
        )
        forged_evidence = copy.deepcopy(evidence)
        forged_evidence[0]["evidence"] = "not actually run"
        forged_receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha="a" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=forged_evidence,
        )
        forged_attestation = fast_path.create_validation_attestation(
            repository="SecPal/.github",
            head_sha=p21.HEAD,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            validation_receipt=forged_receipt,
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "signed commit"):
            fast_path.verify_validation_attestation(
                forged_attestation,
                repository="SecPal/.github",
                head_sha=p21.HEAD,
                registry=registry,
                command_set=registry["validation"],
                reviewed_state=reviewed,
                commit_parent_sha=reviewed.head_sha,
                commit_tree_sha="a" * 40,
                commit_validation_receipt_digest=receipt["receipt_digest"],
            )

    def test_resolution_eligibility_is_bound_into_the_signed_receipt(self) -> None:
        payload = fast_feedback(thread_count=1).to_dict()
        payload["threads"][0]["node_id"] = "PRRT_exampleOne"
        reviewed = fast_path.StableFeedbackState.from_payload(payload)
        manifest = {
            "schema_version": "1.1",
            "repository": "SecPal/.github",
            "pull_request_number": 1,
            "reviewed_head_sha": reviewed.head_sha,
            "reviewed_state_digest": reviewed.state_digest,
            "eligible_threads": [
                {
                    "thread_id": "PRRT_exampleOne",
                    "classification": "VALID_ACTIONABLE",
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "finding_ids": ["finding-1"],
                    "evidence_digest": "a" * 64,
                    "follow_up": None,
                }
            ],
        }
        registry = fast_registry()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            eligibility_digest = actions._resolution_eligibility_digest(
                str(path), "SecPal/.github", reviewed
            )

        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha="a" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            eligibility_evidence_digest=eligibility_digest,
        )
        attestation = fast_path.create_validation_attestation(
            repository="SecPal/.github",
            head_sha=p21.HEAD,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            validation_receipt=receipt,
        )

        self.assertEqual(
            receipt["eligibility_evidence_digest"], eligibility_digest
        )
        self.assertEqual(
            attestation["eligibility_evidence_digest"], eligibility_digest
        )

    def test_empty_resolution_eligibility_authenticates_zero_targets(self) -> None:
        reviewed = fast_path.StableFeedbackState.from_payload(
            fast_feedback(thread_count=0).to_dict()
        )
        manifest = {
            "schema_version": "1.1",
            "repository": "SecPal/.github",
            "pull_request_number": 1,
            "reviewed_head_sha": reviewed.head_sha,
            "reviewed_state_digest": reviewed.state_digest,
            "eligible_threads": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            observed = actions._resolution_eligibility_digest(
                str(path), "SecPal/.github", reviewed
            )
        self.assertEqual(observed, fast_path.digest_json(manifest))

    def test_registered_manual_gates_require_explicit_satisfied_evidence(self) -> None:
        binding = actions._fast_registry_binding(registry_entry("SecPal/.github"))
        with self.assertRaisesRegex(
            fast_path.RecoverableLocalError, "manual gates"
        ):
            actions._load_fast_manual_gate_evidence(None, binding)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "not satisfied"):
            fast_path.validate_manual_gate_evidence(
                [
                    {
                        "gate": binding["manual_gates"][0],
                        "satisfied": False,
                        "evidence": "not run",
                    }
                ],
                binding["manual_gates"],
            )

        with self.assertRaisesRegex(fast_path.SecurityBlocker, "secret"):
            fast_path.validate_manual_gate_evidence(
                [
                    {
                        "gate": binding["manual_gates"][0],
                        "satisfied": True,
                        "evidence": "Authorization: Bearer example-token",
                    }
                ],
                binding["manual_gates"],
            )

    def test_registered_manual_gate_evidence_loads_from_ordered_json_list(self) -> None:
        binding = actions._fast_registry_binding(registry_entry("SecPal/.github"))
        evidence = [
            {
                "gate": gate,
                "satisfied": True,
                "evidence": f"verified gate {index}",
            }
            for index, gate in enumerate(binding["manual_gates"], start=1)
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence_path = Path(temporary_directory) / "manual-gates.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            self.assertEqual(
                actions._load_fast_manual_gate_evidence(
                    str(evidence_path), binding
                ),
                evidence,
            )

    def test_unregistered_base_repository_blocks_before_first_write(self) -> None:
        reviewed = fast_feedback()
        gateway = FakeFastGateway(reviewed)
        original = gateway.read_preflight

        def foreign_base(request_value: Any) -> Any:
            readiness = original(request_value)
            readiness.base_repository = "outside/fork"
            return readiness

        gateway.read_preflight = foreign_base
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "base repository"):
            self.execute(reviewed, gateway)
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_batch_schema_accepts_graphql_ids_with_padding(self) -> None:
        payload = fast_request(fast_feedback(), 1).to_dict()
        payload["expected_actor"]["node_id"] = "U_kgDOD9_SfQ=="
        actions._validate_schema(
            payload,
            actions.FAST_BATCH_SCHEMA_PATH,
            "fast batch",
            actions.PlanError,
        )
        fast_path.BatchRequest.from_dict(payload)

    def test_attestation_receipt_requires_matching_reviewed_identity(self) -> None:
        arguments = SimpleNamespace(
            expected_head=p21.HEAD,
            repo_root=str(REPO_ROOT),
            repo="SecPal/.github",
            reviewed_state="reviewed.json",
            registry="registry.json",
            bind_commit=False,
            receipt=None,
            output="receipt.json",
        )
        entry = {
            "repository": "SecPal/.github",
            "default_branch": "main",
            "allowed_base_repositories": ["SecPal/.github"],
            "manual_gates": [],
            "focused_validation": [],
            "required_local_validation": [],
            "signature_policy": {"accepted_formats": ["ssh", "openpgp"]},
            "check_policy": {
                "require_ruleset_evidence": True,
                "require_branch_protection_evidence": True,
                "expected_skipped": "block",
            },
            "maximum_api_calls": 200,
            "maximum_items": 10000,
        }
        mismatches = {
            "repository": fast_path.StableFeedbackState.from_payload(
                {**fast_feedback().to_dict(), "repository": "SecPal/api"}
            ),
            "head": fast_feedback(head_sha="e" * 40),
        }
        for field, reviewed in mismatches.items():
            with (
                self.subTest(field=field),
                mock.patch.object(
                    actions,
                    "_attestation_local_state",
                    return_value=(p21.HEAD, ""),
                ),
                mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
                mock.patch.object(actions, "load_registry", return_value={}),
                mock.patch.object(actions, "select_repository", return_value=entry),
                mock.patch.object(actions, "_staged_tree", return_value="a" * 40),
                mock.patch.object(actions, "_run_registered_validations", return_value=True),
                mock.patch.object(actions, "_write_fast_report"),
            ):
                with self.assertRaisesRegex(
                    fast_path.SecurityBlocker,
                    "reviewed feedback (repository|head)",
                ):
                    actions._command_attest_validation(arguments)

    def test_failed_complete_validation_invalidates_a_stale_receipt(self) -> None:
        entry = registry_entry("SecPal/.github")
        entry["manual_gates"] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "receipt.json"
            output.write_text(
                json.dumps({"receipt_digest": "stale-successful-receipt"}),
                encoding="utf-8",
            )
            arguments = SimpleNamespace(
                expected_head=p21.HEAD,
                repo_root=str(REPO_ROOT),
                repo="SecPal/.github",
                reviewed_state="reviewed.json",
                registry="registry.json",
                bind_commit=False,
                receipt=None,
                output=str(output),
                manual_gate_evidence=None,
            )

            with (
                mock.patch.object(
                    actions,
                    "_attestation_local_state",
                    return_value=(p21.HEAD, ""),
                ),
                mock.patch.object(
                    actions,
                    "_load_fast_state",
                    return_value=fast_feedback(),
                ),
                mock.patch.object(actions, "load_registry", return_value={}),
                mock.patch.object(actions, "select_repository", return_value=entry),
                mock.patch.object(actions, "_staged_tree", return_value="a" * 40),
                mock.patch.object(
                    actions,
                    "_run_registered_validations",
                    return_value=False,
                ),
            ):
                with self.assertRaisesRegex(
                    fast_path.SecurityBlocker,
                    "complete registered validation failed",
                ):
                    actions._command_attest_validation(arguments)

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {
                    "schema_version": "1.0",
                    "status": "VALIDATION_RECEIPT_INVALIDATED",
                    "head_sha": p21.HEAD,
                    "validated_tree_sha": "a" * 40,
                },
            )

    def test_attestation_cli_reports_failed_entry_without_output_or_retry(self) -> None:
        entry = registry_entry("SecPal/.github")
        entry["manual_gates"] = []
        completed = SimpleNamespace(
            returncode=9,
            stdout="github_pat_cli_output_must_not_leak",
            stderr="secret=cli-output-must-not-leak",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "receipt.json"
            error_output = io.StringIO()
            with (
                mock.patch.object(
                    actions,
                    "_attestation_local_state",
                    return_value=(p21.HEAD, ""),
                ),
                mock.patch.object(
                    actions,
                    "_load_fast_state",
                    return_value=fast_feedback(),
                ),
                mock.patch.object(actions, "load_registry", return_value={}),
                mock.patch.object(actions, "select_repository", return_value=entry),
                mock.patch.object(actions, "_staged_tree", return_value="a" * 40),
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
                mock.patch.object(actions.sys, "stderr", error_output),
            ):
                returncode = actions.main(
                    [
                        "attest-validation",
                        "--repo",
                        "SecPal/.github",
                        "--expected-head",
                        p21.HEAD,
                        "--reviewed-state",
                        "reviewed.json",
                        "--repo-root",
                        str(REPO_ROOT),
                        "--output",
                        str(output),
                    ]
                )

            diagnostic_text = error_output.getvalue()
            diagnostic = json.loads(diagnostic_text)
            self.assertEqual(returncode, 3)
            self.assertEqual(diagnostic["status"], "BLOCKED_SECURITY")
            self.assertFalse(diagnostic["retry_performed"])
            self.assertEqual(
                diagnostic["registered_validation_failure"],
                {
                    "category": "non-zero exit",
                    "index": 1,
                    "purpose": "Run tests",
                },
            )
            self.assertNotIn("cli-output", diagnostic_text)
            self.assertNotIn("github_pat_", diagnostic_text)
            self.assertEqual(run.call_count, 1)
            self.assertIsInstance(run.call_args.args[0], list)
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {
                    "schema_version": "1.0",
                    "status": "VALIDATION_RECEIPT_INVALIDATED",
                    "head_sha": p21.HEAD,
                    "validated_tree_sha": "a" * 40,
                },
            )

    def test_bound_commit_requires_receipt_for_reviewed_head(self) -> None:
        reviewed = fast_feedback()
        receipt_head = "e" * 40
        final_head = "d" * 40
        tree = "a" * 40
        entry = {
            "repository": "SecPal/.github",
            "default_branch": "main",
            "allowed_base_repositories": ["SecPal/.github"],
            "manual_gates": [],
            "focused_validation": [],
            "required_local_validation": [],
            "signature_policy": {"accepted_formats": ["ssh", "openpgp"]},
            "check_policy": {
                "require_ruleset_evidence": True,
                "require_branch_protection_evidence": True,
                "expected_skipped": "block",
            },
            "maximum_api_calls": 200,
            "maximum_items": 10000,
        }
        binding = actions._fast_registry_binding(entry)
        receipt = actions._validation_receipt(
            repository="SecPal/.github",
            head_sha=receipt_head,
            tree_sha=tree,
            binding=binding,
            reviewed=reviewed,
            manual_gate_evidence=[],
        )
        arguments = SimpleNamespace(
            expected_head=final_head,
            repo_root=str(REPO_ROOT),
            repo="SecPal/.github",
            reviewed_state="reviewed.json",
            registry="registry.json",
            bind_commit=True,
            receipt="receipt.json",
            output="attestation.json",
        )

        def git_result(
            _repository_root: Path,
            command: list[str],
            *,
            allow_failure: bool = False,
        ) -> Any:
            del allow_failure
            outputs = {
                ("rev-parse", "HEAD^"): receipt_head,
                ("rev-parse", "HEAD^{tree}"): tree,
                ("cat-file", "commit", final_head): (
                    "tree deadbeef\ngpgsig -----BEGIN SSH SIGNATURE-----\n"
                    " signature\n -----END SSH SIGNATURE-----\n\nmessage\n"
                ),
                ("verify-commit", "--raw", final_head): "",
            }
            return SimpleNamespace(
                returncode=0,
                stdout=outputs[tuple(command)],
                stderr=(
                    'Good "git" signature for aroviqen with ED25519 key SHA256:test\n'
                    if command[:2] == ["verify-commit", "--raw"]
                    else ""
                ),
            )

        with (
            mock.patch.object(
                actions,
                "_attestation_local_state",
                return_value=(final_head, ""),
            ),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value=entry),
            mock.patch.object(actions, "_read_json", return_value=receipt),
            mock.patch.object(actions, "_run_attestation_git", side_effect=git_result),
            mock.patch.object(actions, "_write_fast_report"),
        ):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker,
                "receipt head does not match reviewed feedback head",
            ):
                actions._command_attest_validation(arguments)

    def test_bound_commit_rejects_a_malformed_validation_receipt(self) -> None:
        reviewed = fast_feedback()
        entry = registry_entry("SecPal/.github")
        arguments = SimpleNamespace(
            expected_head="d" * 40,
            repo_root=str(REPO_ROOT),
            repo="SecPal/.github",
            reviewed_state="reviewed.json",
            registry="registry.json",
            bind_commit=True,
            receipt="receipt.json",
            output="attestation.json",
            manual_gate_evidence=None,
        )
        with (
            mock.patch.object(
                actions,
                "_attestation_local_state",
                return_value=(arguments.expected_head, ""),
            ),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value=entry),
            mock.patch.object(actions, "_read_json", return_value=[]),
        ):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "validation receipt is malformed"
            ):
                actions._command_attest_validation(arguments)

    def test_bound_commit_rejects_a_second_parent(self) -> None:
        head = "d" * 40
        first_parent = "e" * 40
        second_parent = "f" * 40
        with mock.patch.object(
            actions,
            "_run_attestation_git",
            return_value=SimpleNamespace(
                returncode=0,
                stdout=f"{head} {first_parent} {second_parent}\n",
                stderr="",
            ),
        ):
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "sole parent"):
                actions._validated_commit_parent(REPO_ROOT, head)

    def test_ready_integration_requires_independent_prior_ready_authority(self) -> None:
        reviewed = fast_feedback()
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        with self.assertRaises(fast_path.SecurityBlocker):
            actions._verify_ready_integration_prior_authority(
                arguments=SimpleNamespace(
                    repo="SecPal/.github", delivery_issue=9
                ),
                repository_root=REPO_ROOT,
                binding=fast_registry(),
                integration_evidence=integration,
                live_observation=None,
            )

    def test_ready_integration_prior_authority_lifecycle_is_closed_and_ready(
        self,
    ) -> None:
        authority = ready_integration_prior_authority(fast_feedback())
        fast_path.normalize_ready_integration_prior_authority(authority)
        cases = (
            ("unknown_field", lambda item: item.__setitem__("allow_ready", True)),
            ("wrong_kind", lambda item: item.__setitem__("kind", "REMEDIATION")),
            ("wrong_version", lambda item: item.__setitem__("schema_version", "2.0")),
            ("draft", lambda item: item["lifecycle"].__setitem__("draft", True)),
            ("not_ready", lambda item: item["lifecycle"].__setitem__("ready", False)),
            ("ready_transition", lambda item: item["lifecycle"].__setitem__("ready_transition", True)),
            ("review_counter", lambda item: item["lifecycle"].__setitem__("unrestricted_reviews", 2)),
            ("remediation_counter", lambda item: item["lifecycle"].__setitem__("remediation_cycles", 3)),
            ("recovery_counter", lambda item: item["lifecycle"].__setitem__("exceptional_recoveries", 2)),
            ("continuation_counter", lambda item: item["lifecycle"].__setitem__("exceptional_continuations", 2)),
            ("authority_digest", lambda item: item["lifecycle"].__setitem__("current_authority_digest", "x" * 64)),
            ("proof_mode", lambda item: item["lifecycle"].__setitem__("historical_proof_mode", "asserted")),
            ("publication_oid", lambda item: item["publication"].__setitem__("object_oid", "x" * 40)),
            ("cycle_3", lambda item: item["lifecycle"].__setitem__("cycle_3", True)),
        )
        for case, mutate in cases:
            candidate = copy.deepcopy(authority)
            mutate(candidate)
            with self.subTest(case=case), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_prior_authority(candidate)

    def test_ready_integration_prior_authority_rejects_caller_substitution(
        self,
    ) -> None:
        reviewed = fast_feedback()
        original = ready_integration_prior_authority(reviewed)
        cases = (
            ("repository", "SecPal/api"),
            ("delivery_issue_number", 10),
            ("pull_request_number", 2),
            ("prior_delivery_head_sha", "b" * 40),
        )
        for field, value in cases:
            authority = copy.deepcopy(original)
            authority[field] = value
            authority = fast_path.normalize_ready_integration_prior_authority(authority)
            integration = ready_integration_evidence(reviewed, validated_tree="a" * 40)
            integration["prior_authority_digest"] = fast_path.digest_json(authority)
            integration = fast_path.normalize_ready_integration_evidence(
                integration,
                repository="SecPal/.github",
                reviewed_state=reviewed,
                registry=fast_registry(),
                validated_tree_sha="a" * 40,
            )
            arguments = SimpleNamespace(
                repo="SecPal/.github",
                delivery_issue=9,
                prior_authority="authority.json",
                prior_reviewed_state="prior-reviewed.json",
                prior_receipt="prior-receipt.json",
                prior_attestation="prior-attestation.json",
                prior_authority_tag_ref="refs/tags/prior-authority",
                expected_prior_authority_signer="aroviqen",
            )
            with (
                self.subTest(field=field),
                mock.patch.object(actions, "_read_json", return_value=authority),
                self.assertRaisesRegex(fast_path.SecurityBlocker, "identity changed"),
            ):
                actions._verify_ready_integration_prior_authority(
                    arguments=arguments,
                    repository_root=REPO_ROOT,
                    binding=fast_registry(),
                    integration_evidence=integration,
                    live_observation=None,
                )

    def test_ready_integration_prior_authority_rejects_reviewed_pr_mismatch(
        self,
    ) -> None:
        reviewed = fast_feedback()
        authority = fast_path.normalize_ready_integration_prior_authority(
            ready_integration_prior_authority(reviewed)
        )
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        mismatched = fast_path.StableFeedbackState(
            repository=reviewed.repository,
            pull_request_number=reviewed.pull_request_number + 1,
            head_sha=reviewed.head_sha,
            base_ref=reviewed.base_ref,
            base_sha=reviewed.base_sha,
            pr_state=reviewed.pr_state,
            feedback=reviewed.feedback,
        )
        arguments = SimpleNamespace(
            repo="SecPal/.github",
            delivery_issue=9,
            prior_authority="authority.json",
            prior_reviewed_state="prior-reviewed.json",
            prior_receipt="prior-receipt.json",
            prior_attestation="prior-attestation.json",
            prior_authority_tag_ref="refs/tags/prior-authority",
            expected_prior_authority_signer="aroviqen",
        )
        with (
            mock.patch.object(actions, "_read_json", return_value=authority),
            mock.patch.object(actions, "_load_fast_state", return_value=mismatched),
            mock.patch.object(
                actions,
                "_validated_commit_parent",
                return_value="e" * 40,
            ),
            mock.patch.object(
                actions,
                "_run_attestation_git",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=authority["prior_delivery_tree_sha"],
                    stderr="",
                ),
            ),
            self.assertRaisesRegex(
                fast_path.SecurityBlocker,
                "prior delivery pull-request identity changed",
            ),
        ):
            actions._verify_ready_integration_prior_authority(
                arguments=arguments,
                repository_root=REPO_ROOT,
                binding=fast_registry(),
                integration_evidence=integration,
                live_observation=None,
            )

    def test_ready_integration_reconstructs_prior_policy_from_prior_commit(self) -> None:
        registry = json.loads(actions.REGISTRY_PATH.read_text(encoding="utf-8"))
        historical_binding = next(
            item
            for item in registry["repositories"]
            if item["repository"] == "SecPal/.github"
        )
        historical_binding["focused_validation"] = historical_binding[
            "focused_validation"
        ][:4]
        historical_validation_count = len(
            historical_binding["focused_validation"]
        ) + len(historical_binding["required_local_validation"])
        registry_raw = json.dumps(registry)
        with mock.patch.object(
            actions,
            "_run_attestation_git",
            return_value=SimpleNamespace(returncode=0, stdout=registry_raw, stderr=""),
        ) as git_read:
            binding = actions._prior_delivery_registry_binding(
                REPO_ROOT, "a" * 40, "SecPal/.github"
            )
        self.assertEqual(binding["repository"], "SecPal/.github")
        self.assertEqual(historical_validation_count, 10)
        self.assertEqual(len(binding["validation"]), historical_validation_count)
        self.assertEqual(
            git_read.call_args.args[1],
            [
                "show",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:.agents/skills/"
                "secpal-pr-review/references/repositories.json",
            ],
        )

    def test_ready_integration_prior_authority_rejects_delivery_evidence_drift(
        self,
    ) -> None:
        reviewed = fast_feedback()
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        authority = fast_path.normalize_ready_integration_prior_authority(
            ready_integration_prior_authority(reviewed)
        )
        arguments = SimpleNamespace(
            repo="SecPal/.github",
            delivery_issue=9,
            prior_authority="authority.json",
            prior_reviewed_state="prior-reviewed.json",
            prior_receipt="prior-receipt.json",
            prior_attestation="prior-attestation.json",
            prior_authority_tag_ref="refs/tags/prior-authority",
            expected_prior_authority_signer="aroviqen",
        )
        cases = (
            ("tree", "d" * 40, authority["prior_validation_receipt_digest"], authority["prior_final_attestation_digest"]),
            ("receipt", authority["prior_delivery_tree_sha"], "d" * 64, authority["prior_final_attestation_digest"]),
            ("attestation", authority["prior_delivery_tree_sha"], authority["prior_validation_receipt_digest"], "d" * 64),
        )
        for case, observed_tree, receipt_digest, attestation_digest in cases:
            def read_json(path: str, _label: str) -> Any:
                if path == "authority.json":
                    return authority
                if path == "prior-receipt.json":
                    return {"receipt_digest": receipt_digest}
                if path == "prior-attestation.json":
                    return {"attestation_digest": attestation_digest}
                raise AssertionError(path)

            with (
                self.subTest(case=case),
                mock.patch.object(actions, "_read_json", side_effect=read_json),
                mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
                mock.patch.object(actions, "_validated_commit_parent", return_value="e" * 40),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    return_value=SimpleNamespace(returncode=0, stdout=observed_tree, stderr=""),
                ),
                mock.patch.object(actions, "_commit_validation_receipt_digest", return_value="b" * 64),
                self.assertRaisesRegex(fast_path.SecurityBlocker, "evidence identity changed"),
            ):
                actions._verify_ready_integration_prior_authority(
                    arguments=arguments,
                    repository_root=REPO_ROOT,
                    binding=fast_registry(),
                    integration_evidence=integration,
                    live_observation=None,
                )

    def test_ready_integration_live_authority_rejects_ref_identity_drift(self) -> None:
        reviewed = fast_feedback()
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        observation = {
            "repository": "SecPal/.github",
            "pull_request_number": reviewed.pull_request_number,
            "state": "OPEN",
            "draft": False,
            "head_sha": reviewed.head_sha,
            "base_repository": "SecPal/.github",
            "base_ref": reviewed.base_ref,
            "base_sha": reviewed.base_sha,
        }
        actions._verify_ready_integration_live_observation(
            observation, integration, fast_registry()
        )
        cases = (
            ("repository", "SecPal/api"),
            ("pull_request_number", 2),
            ("state", "CLOSED"),
            ("draft", True),
            ("head_sha", "b" * 40),
            ("base_ref", "release"),
            ("base_sha", "9" * 40),
        )
        for field, value in cases:
            changed = {**observation, field: value}
            with self.subTest(field=field), self.assertRaisesRegex(
                fast_path.SecurityBlocker, "target-base authority drifted"
            ):
                actions._verify_ready_integration_live_observation(
                    changed, integration, fast_registry()
                )

    def test_ready_integration_live_authority_uses_current_default_branch_tip(self) -> None:
        payload = {
            "data": {
                "repository": {
                    "nameWithOwner": "SecPal/.github",
                    "defaultBranchRef": {
                        "name": "main",
                        "target": {"oid": "d" * 40},
                    },
                    "pullRequest": {
                        "number": 746,
                        "state": "OPEN",
                        "isDraft": False,
                        "headRefOid": "a" * 40,
                        "baseRefName": "main",
                        "baseRefOid": "b" * 40,
                        "baseRepository": {"nameWithOwner": "SecPal/.github"},
                    },
                }
            }
        }
        github = actions.LiveGitHub(
            SimpleNamespace(run=lambda _arguments: payload)
        )

        observed = github.observe_ready_integration_authority("SecPal/.github", 746)

        self.assertEqual(observed["base_ref"], "main")
        self.assertEqual(observed["base_sha"], "d" * 40)

    def test_ready_integration_accepts_current_base_after_feedback_base_advanced(self) -> None:
        reviewed = fast_feedback()
        integration = ready_integration_evidence(reviewed, validated_tree="a" * 40)
        integration["target_base"]["authorized_sha"] = "d" * 40
        integration["target_base"]["observed_sha"] = "d" * 40
        integration["ordered_parent_shas"][1] = "d" * 40

        normalized = fast_path.normalize_ready_integration_evidence(
            integration,
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )

        self.assertEqual(normalized["target_base"]["authorized_sha"], "d" * 40)

    def test_ready_integration_live_authority_fails_closed_when_unavailable_or_malformed(
        self,
    ) -> None:
        with (
            mock.patch.object(
                actions.LiveGitHub,
                "observe_ready_integration_authority",
                side_effect=actions.MutationFailure("unavailable"),
            ),
            self.assertRaisesRegex(fast_path.SecurityBlocker, "unavailable"),
        ):
            actions._observe_ready_integration_authority_once("SecPal/.github", 746)
        malformed = {
            "repository": "SecPal/.github",
            "pull_request_number": 746,
            "state": "OPEN",
            "draft": False,
            "head_sha": "a" * 40,
            "base_repository": "SecPal/api",
            "base_ref": "main",
            "base_sha": None,
        }
        with (
            mock.patch.object(
                actions.LiveGitHub,
                "observe_ready_integration_authority",
                return_value=malformed,
            ),
            self.assertRaisesRegex(fast_path.SecurityBlocker, "malformed"),
        ):
            actions._observe_ready_integration_authority_once("SecPal/.github", 746)

    def test_ready_integration_lifecycle_must_match_prior_authority(self) -> None:
        reviewed = fast_feedback()
        authority = fast_path.normalize_ready_integration_prior_authority(
            ready_integration_prior_authority(reviewed)
        )
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        actions._verify_ready_integration_lifecycle_authority(authority, integration)
        for field, value in (
            ("identity", "another-lifecycle"),
            ("unrestricted_reviews", 0),
            ("remediation_cycles", 0),
            ("exceptional_recoveries", 0),
            ("exceptional_continuations", 1),
        ):
            changed = copy.deepcopy(authority)
            changed["lifecycle"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                fast_path.SecurityBlocker, "lifecycle differs"
            ):
                actions._verify_ready_integration_lifecycle_authority(
                    changed, integration
                )

    def test_ready_integration_accepts_authenticated_current_ready_histories(self) -> None:
        reviewed = fast_feedback()
        histories = (
            ("native", 0, 0, 0),
            ("remediated_once", 1, 0, 0),
            ("remediated_twice", 2, 0, 0),
            ("historical_recovery", 2, 1, 0),
            ("historical_continuation", 2, 1, 1),
        )
        for name, remediations, recoveries, continuations in histories:
            with self.subTest(history=name):
                authority = fast_path.normalize_ready_integration_prior_authority(
                    ready_integration_prior_authority(
                        reviewed,
                        remediation_cycles=remediations,
                        exceptional_recoveries=recoveries,
                        exceptional_continuations=continuations,
                    )
                )
                integration = fast_path.normalize_ready_integration_evidence(
                    ready_integration_evidence(
                        reviewed,
                        validated_tree="a" * 40,
                        remediation_cycles=remediations,
                        exceptional_recoveries=recoveries,
                        exceptional_continuations=continuations,
                    ),
                    repository="SecPal/.github",
                    reviewed_state=reviewed,
                    registry=fast_registry(),
                    validated_tree_sha="a" * 40,
                )
                actions._verify_ready_integration_lifecycle_authority(
                    authority, integration
                )
                self.assertEqual(
                    integration["eligibility"]["exceptional_recoveries_after"],
                    recoveries,
                )
                self.assertEqual(
                    integration["eligibility"]["exceptional_continuations_after"],
                    continuations,
                )

    def test_ready_integration_rejects_caller_forged_history_changes(self) -> None:
        reviewed = fast_feedback()
        authority = fast_path.normalize_ready_integration_prior_authority(
            ready_integration_prior_authority(
                reviewed,
                exceptional_recoveries=0,
                exceptional_continuations=0,
            )
        )
        original = ready_integration_evidence(
            reviewed,
            validated_tree="a" * 40,
            exceptional_recoveries=0,
            exceptional_continuations=0,
        )
        for field, forged in (
            ("exceptional_recoveries_after", 1),
            ("exceptional_continuations_after", 1),
        ):
            candidate = copy.deepcopy(original)
            candidate["eligibility"][field] = forged
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_evidence(
                    candidate,
                    repository="SecPal/.github",
                    reviewed_state=reviewed,
                    registry=fast_registry(),
                    validated_tree_sha="a" * 40,
                )
        integration = fast_path.normalize_ready_integration_evidence(
            original,
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        for field, forged in (
            ("exceptional_recoveries", 1),
            ("exceptional_continuations", 1),
        ):
            changed = copy.deepcopy(authority)
            changed["lifecycle"][field] = forged
            with self.subTest(field=field), self.assertRaisesRegex(
                fast_path.SecurityBlocker, "lifecycle differs"
            ):
                actions._verify_ready_integration_lifecycle_authority(
                    changed, integration
                )

    def test_ready_integration_consumes_current_published_lifecycle_authority(
        self,
    ) -> None:
        reviewed = fast_feedback()
        authority = fast_path.normalize_ready_integration_prior_authority(
            ready_integration_prior_authority(reviewed)
        )
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        verified_lifecycle = SimpleNamespace(
            authority_digest=authority["lifecycle"]["current_authority_digest"],
            lifecycle_id=authority["lifecycle"]["identity"],
            historical_proof_mode=authority["lifecycle"]["historical_proof_mode"],
            state={"cycle_3_absent": True},
        )
        published = SimpleNamespace(
            publication_oid=authority["publication"]["object_oid"],
            publication_digest=authority["publication"]["publication_digest"],
            lifecycle=verified_lifecycle,
        )
        lifecycle_authority = SimpleNamespace(
            ExpectedLifecycle=SimpleNamespace,
            LifecycleAuthorityError=ValueError,
        )
        lifecycle_publication = SimpleNamespace(
            verify_current_lifecycle_authority=mock.Mock(return_value=published),
            LifecyclePublicationError=ValueError,
        )
        with mock.patch.object(
            actions,
            "_load_lifecycle_publication_helpers",
            return_value=(lifecycle_authority, lifecycle_publication),
        ):
            actions._verify_ready_integration_published_authority(
                authority, integration
            )
        expected = lifecycle_publication.verify_current_lifecycle_authority.call_args.args[2]
        self.assertEqual(expected.head_sha, reviewed.head_sha)
        self.assertEqual(expected.exceptional_recovery_count, 1)
        self.assertEqual(expected.exceptional_continuation_count, 0)

        published.publication_digest = "0" * 64
        with (
            mock.patch.object(
                actions,
                "_load_lifecycle_publication_helpers",
                return_value=(lifecycle_authority, lifecycle_publication),
            ),
            self.assertRaisesRegex(fast_path.SecurityBlocker, "binding changed"),
        ):
            actions._verify_ready_integration_published_authority(
                authority, integration
            )

    def test_ready_integration_binds_exact_adoption_source_evidence(self) -> None:
        reviewed = fast_feedback()
        raw_authority = ready_integration_prior_authority(reviewed)
        raw_authority["lifecycle"]["historical_proof_mode"] = (
            "exact_state_adoption"
        )
        authority = fast_path.normalize_ready_integration_prior_authority(
            raw_authority
        )
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github", reviewed_state=reviewed,
            registry=fast_registry(), validated_tree_sha="a" * 40,
        )
        verified_lifecycle = SimpleNamespace(
            authority_digest=authority["lifecycle"]["current_authority_digest"],
            lifecycle_id=authority["lifecycle"]["identity"],
            historical_proof_mode="exact_state_adoption",
            state={"cycle_3_absent": True},
            tree_sha=authority["prior_delivery_tree_sha"],
            validation_receipt_digest=authority[
                "prior_validation_receipt_digest"
            ],
            adoption_source_evidence_digest=authority[
                "prior_final_attestation_digest"
            ],
            source_validation_evidence_digest="e" * 64,
        )
        published = SimpleNamespace(
            publication_oid=authority["publication"]["object_oid"],
            publication_digest=authority["publication"]["publication_digest"],
            lifecycle=verified_lifecycle,
        )
        lifecycle_authority = SimpleNamespace(
            ExpectedLifecycle=SimpleNamespace, LifecycleAuthorityError=ValueError,
        )
        lifecycle_publication = SimpleNamespace(
            verify_current_lifecycle_authority=mock.Mock(return_value=published),
            LifecyclePublicationError=ValueError,
        )
        with mock.patch.object(
            actions, "_load_lifecycle_publication_helpers",
            return_value=(lifecycle_authority, lifecycle_publication),
        ):
            actions._verify_ready_integration_published_authority(
                authority,
                integration,
                verified_source_validation_evidence_digest="e" * 64,
            )
            published.lifecycle.source_validation_evidence_digest = "f" * 64
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "source evidence"
            ):
                actions._verify_ready_integration_published_authority(
                    authority,
                    integration,
                    verified_source_validation_evidence_digest="e" * 64,
                )
            published.lifecycle.adoption_source_evidence_digest = "0" * 64
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "adoption source evidence"
            ):
                actions._verify_ready_integration_published_authority(
                    authority,
                    integration,
                    verified_source_validation_evidence_digest="e" * 64,
                )

    def test_ready_integration_rejects_actual_default_branch_sha_drift(self) -> None:
        reviewed = fast_feedback()
        final_head = reviewed.head_sha
        tree = "a" * 40
        entry = registry_entry("SecPal/.github")
        entry["manual_gates"] = []
        binding = actions._fast_registry_binding(entry)
        integration = ready_integration_evidence(
            reviewed,
            validated_tree=tree,
            registry=binding,
        )
        receipt = actions._validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            tree_sha=tree,
            binding=binding,
            reviewed=reviewed,
            manual_gate_evidence=[],
        )
        integration = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=binding
        )
        arguments = SimpleNamespace(
            expected_head=final_head,
            repo_root=str(REPO_ROOT),
            repo="SecPal/.github",
            reviewed_state="reviewed.json",
            registry="registry.json",
            bind_commit=False,
            receipt=None,
            output="attestation.json",
            manual_gate_evidence=None,
            eligibility_evidence=None,
            integration_evidence="integration.json",
            delivery_issue=9,
            integration_authorization_id=integration["authorization_id"],
            expected_integration_signer=integration["expected_signer"]["identity"],
        )

        with (
            mock.patch.object(
                actions, "_attestation_local_state", return_value=(final_head, "")
            ),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value=entry),
            mock.patch.object(
                actions,
                "_read_json",
                side_effect=lambda path, _label: (
                    integration if path == "integration.json" else receipt
                ),
            ),
            mock.patch.object(
                actions,
                "_observe_ready_integration_authority_once",
                return_value={
                    "repository": "SecPal/.github",
                    "pull_request_number": reviewed.pull_request_number,
                    "state": "OPEN",
                    "draft": False,
                    "head_sha": reviewed.head_sha,
                    "base_repository": "SecPal/.github",
                    "ref": reviewed.base_ref,
                    "base_ref": reviewed.base_ref,
                    "base_sha": "9" * 40,
                },
            ),
            mock.patch.object(actions, "_verify_ready_integration_prior_authority"),
            mock.patch.object(actions, "_staged_tree", return_value=tree),
            mock.patch.object(actions, "_verify_integration_tree_delta"),
            mock.patch.object(
                actions, "_run_registered_validations", return_value=True
            ),
            mock.patch.object(actions, "_write_fast_report"),
            self.assertRaises(fast_path.SecurityBlocker),
        ):
            actions._command_attest_validation(arguments)

    def test_real_signed_two_parent_candidate_reproduces_sole_parent_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="secpal-integration-fail-first-") as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()

            def git(*arguments: str, input_text: str | None = None) -> str:
                result = subprocess.run(
                    ["git", *arguments],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                    input=input_text,
                )
                return result.stdout.strip()

            subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(root / "signing-key"),
                ],
                check=True,
                capture_output=True,
            )
            principal = "cycle1@example.test"
            (root / "allowed-signers").write_text(
                f"{principal} {(root / 'signing-key.pub').read_text()}",
                encoding="utf-8",
            )
            git("init", "-q")
            git("config", "user.name", "Cycle 1 Fixture")
            git("config", "user.email", principal)
            git("config", "gpg.format", "ssh")
            git("config", "user.signingkey", str(root / "signing-key"))
            git("config", "gpg.ssh.allowedSignersFile", str(root / "allowed-signers"))
            git("remote", "add", "origin", "https://github.com/SecPal/.github.git")
            (repository / "base.txt").write_text("base\n", encoding="utf-8")
            git("add", "base.txt")
            git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            (repository / "delivery.txt").write_text("delivery\n", encoding="utf-8")
            git("add", "delivery.txt")
            git("commit", "-q", "-m", "delivery")
            prior_head = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "target-main", base)
            (repository / "main.txt").write_text("main\n", encoding="utf-8")
            git("add", "main.txt")
            git("commit", "-q", "-m", "main")
            target_head = git("rev-parse", "HEAD")
            tree = git("merge-tree", "--write-tree", prior_head, target_head).splitlines()[0]
            reviewed = fast_path.StableFeedbackState(
                repository="SecPal/.github",
                pull_request_number=746,
                head_sha=prior_head,
                base_ref="main",
                base_sha=target_head,
                pr_state="OPEN",
                feedback={
                    "pull_request_reactions": [],
                    "reviews": [],
                    "conversation_comments": [],
                    "threads": [],
                },
            )
            registry = actions.load_registry()
            entry = actions.select_repository(registry, "SecPal/.github")
            binding = actions._fast_registry_binding(entry)
            manual_gates = [
                {"gate": gate, "satisfied": True, "evidence": "Hermetic fail-first fixture."}
                for gate in binding["manual_gates"]
            ]
            receipt = actions._validation_receipt(
                repository="SecPal/.github",
                head_sha=prior_head,
                tree_sha=tree,
                binding=binding,
                reviewed=reviewed,
                manual_gate_evidence=manual_gates,
            )
            candidate = git(
                "commit-tree",
                "-S",
                tree,
                "-p",
                prior_head,
                "-p",
                target_head,
                input_text=(
                    "signed two-parent candidate\n\n"
                    f"SecPal-Validation-Receipt: {receipt['receipt_digest']}\n"
                ),
            )
            git("checkout", "-q", "--detach", candidate)
            self.assertEqual(git("verify-commit", candidate), "")
            reviewed_path = root / "reviewed.json"
            receipt_path = root / "receipt.json"
            output_path = root / "attestation.json"
            reviewed_path.write_text(
                json.dumps(reviewed.to_dict()), encoding="utf-8"
            )
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ACTIONS_HELPER),
                    "attest-validation",
                    "--repo",
                    "SecPal/.github",
                    "--expected-head",
                    candidate,
                    "--reviewed-state",
                    str(reviewed_path),
                    "--repo-root",
                    str(repository),
                    "--receipt",
                    str(receipt_path),
                    "--bind-commit",
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "validated remediation commit must have a sole parent",
                result.stderr,
            )

    def test_real_signed_two_parent_candidate_passes_typed_entrypoint_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="secpal-integration-typed-") as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()

            def git(*arguments: str, input_text: str | None = None) -> str:
                return subprocess.run(
                    ["git", *arguments], cwd=repository, check=True,
                    capture_output=True, text=True, input=input_text,
                ).stdout.strip()

            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / "key")],
                check=True, capture_output=True,
            )
            principal = "cycle1@example.test"
            (root / "allowed").write_text(
                f"{principal} {(root / 'key.pub').read_text()}", encoding="utf-8"
            )
            git("init", "-q")
            for key, value in (
                ("user.name", "Cycle 1 Fixture"), ("user.email", principal),
                ("gpg.format", "ssh"), ("user.signingkey", str(root / "key")),
                ("gpg.ssh.allowedSignersFile", str(root / "allowed")),
            ):
                git("config", key, value)
            git("remote", "add", "origin", "https://github.com/SecPal/.github.git")
            (repository / "base.txt").write_text("base\n", encoding="utf-8")
            git("add", "base.txt"); git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "target-main", base)
            (repository / "main.txt").write_text("main\n", encoding="utf-8")
            git("add", "main.txt"); git("commit", "-q", "-m", "main")
            target = git("rev-parse", "HEAD")
            git("checkout", "-q", "--detach", base)
            (repository / "delivery.txt").write_text("delivery\n", encoding="utf-8")
            git("add", "delivery.txt")
            delivery_tree = git("write-tree")
            registry = actions.load_registry()
            entry = actions.select_repository(registry, "SecPal/.github")
            binding = actions._fast_registry_binding(entry)
            gates = [
                {"gate": gate, "satisfied": True, "evidence": "Hermetic typed fixture."}
                for gate in binding["manual_gates"]
            ]
            prior_reviewed = fast_path.StableFeedbackState(
                repository="SecPal/.github", pull_request_number=746,
                head_sha=base, base_ref="main", base_sha=target, pr_state="OPEN",
                feedback={"pull_request_reactions": [], "reviews": [], "conversation_comments": [], "threads": []},
            )
            prior_receipt = actions._validation_receipt(
                repository="SecPal/.github", head_sha=base, tree_sha=delivery_tree,
                binding=binding, reviewed=prior_reviewed, manual_gate_evidence=gates,
            )
            prior_head = git(
                "commit-tree", "-S", delivery_tree, "-p", base,
                input_text=("prior delivery\n\n" f"SecPal-Validation-Receipt: {prior_receipt['receipt_digest']}\n"),
            )
            git("reset", "--hard", "-q", prior_head)
            prior_attestation = fast_path.create_validation_attestation(
                repository="SecPal/.github", head_sha=prior_head, registry=binding,
                command_set=binding["validation"], successful_result=True,
                reviewed_state=prior_reviewed, validation_receipt=prior_receipt,
            )
            reviewed = fast_path.StableFeedbackState(
                repository="SecPal/.github", pull_request_number=746,
                head_sha=prior_head, base_ref="main", base_sha=target, pr_state="OPEN",
                feedback={"pull_request_reactions": [], "reviews": [], "conversation_comments": [], "threads": []},
            )
            tree = git("merge-tree", "--write-tree", prior_head, target).splitlines()[0]
            authority = ready_integration_prior_authority(reviewed)
            authority.update(
                prior_delivery_tree_sha=delivery_tree,
                prior_validation_receipt_digest=prior_receipt["receipt_digest"],
                prior_final_attestation_digest=prior_attestation["attestation_digest"],
                expected_signer={"kind": "SSH_PRINCIPAL", "identity": principal},
            )
            authority = fast_path.normalize_ready_integration_prior_authority(authority)
            authority_digest = fast_path.digest_json(authority)
            git("tag", "-s", "prior-authority", prior_head, "-m", "Prior Ready authority", "-m", f"SecPal-Prior-Authority: {authority_digest}")
            prior_authority_tag_object = git(
                "rev-parse", "prior-authority^{tag}"
            )
            integration = ready_integration_evidence(reviewed, validated_tree=tree, registry=binding)
            integration["prior_authority_digest"] = authority_digest
            integration["prior_authority_tag_object_sha"] = prior_authority_tag_object
            integration["expected_signer"] = {"kind": "SSH_PRINCIPAL", "identity": principal}
            integration["mechanical_merge_tree_sha"] = tree
            integration_digest = fast_path.digest_json(integration)
            receipt = actions._validation_receipt(
                repository="SecPal/.github", head_sha=prior_head, tree_sha=tree,
                binding=binding, reviewed=reviewed, manual_gate_evidence=gates,
                integration_evidence_digest=integration_digest,
            )
            candidate = git(
                "commit-tree", "-S", tree, "-p", prior_head, "-p", target,
                input_text=("typed integration\n\n"
                    f"SecPal-Validation-Receipt: {receipt['receipt_digest']}\n"
                    f"SecPal-Integration-Evidence: {integration_digest}\n"),
            )
            git("checkout", "-q", "--detach", candidate)
            files = {
                "reviewed.json": reviewed.to_dict(), "receipt.json": receipt,
                "integration.json": integration, "authority.json": authority,
                "prior-reviewed.json": prior_reviewed.to_dict(),
                "prior-receipt.json": prior_receipt, "prior-attestation.json": prior_attestation,
            }
            for name, value in files.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            argv = [
                "attest-validation", "--repo", "SecPal/.github", "--expected-head", candidate,
                "--reviewed-state", str(root / "reviewed.json"), "--repo-root", str(repository),
                "--receipt", str(root / "receipt.json"), "--bind-commit",
                "--output", str(root / "attestation.json"),
                "--integration-evidence", str(root / "integration.json"),
                "--delivery-issue", "9", "--integration-authorization-id", integration["authorization_id"],
                "--expected-integration-signer", principal,
                "--prior-authority", str(root / "authority.json"),
                "--prior-authority-tag-ref", "refs/tags/prior-authority",
                "--prior-reviewed-state", str(root / "prior-reviewed.json"),
                "--prior-receipt", str(root / "prior-receipt.json"),
                "--prior-attestation", str(root / "prior-attestation.json"),
                "--expected-prior-authority-signer", principal,
            ]
            observation = {
                "repository": "SecPal/.github", "pull_request_number": 746,
                "state": "OPEN", "draft": False, "head_sha": prior_head,
                "base_repository": "SecPal/.github", "base_ref": "main", "base_sha": target,
            }
            with (
                mock.patch.object(
                    actions, "_observe_ready_integration_authority_once", return_value=observation
                ) as observe,
                mock.patch.object(
                    actions, "_verify_ready_integration_published_authority"
                ),
                mock.patch.object(
                    actions,
                    "_prior_delivery_registry_binding",
                    return_value=binding,
                ),
            ):
                self.assertEqual(actions.main(argv), 0)
            observe.assert_not_called()
            ordinary = [
                "attest-validation",
                "--repo",
                "SecPal/.github",
                "--expected-head",
                candidate,
                "--reviewed-state",
                str(root / "reviewed.json"),
                "--repo-root",
                str(repository),
                "--receipt",
                str(root / "receipt.json"),
                "--bind-commit",
                "--output",
                str(root / "ordinary-attestation.json"),
            ]
            self.assertNotEqual(actions.main(ordinary), 0)

    def test_ready_integration_bind_accepts_an_explicit_signed_two_parent_candidate(
        self,
    ) -> None:
        reviewed = fast_feedback()
        final_head = "d" * 40
        tree = "a" * 40
        entry = registry_entry("SecPal/.github")
        entry["manual_gates"] = []
        binding = actions._fast_registry_binding(entry)
        eligibility_digest = "e" * 64
        integration = ready_integration_evidence(
            reviewed,
            validated_tree=tree,
            registry=binding,
        )
        receipt = actions._validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            tree_sha=tree,
            binding=binding,
            reviewed=reviewed,
            manual_gate_evidence=[],
            eligibility_evidence_digest=eligibility_digest,
            integration_evidence_digest=fast_path.digest_json(integration),
        )
        integration_digest = fast_path.digest_json(integration)
        arguments = SimpleNamespace(
            expected_head=final_head,
            repo_root=str(REPO_ROOT),
            repo="SecPal/.github",
            reviewed_state="reviewed.json",
            registry="registry.json",
            bind_commit=True,
            receipt="receipt.json",
            output="attestation.json",
            manual_gate_evidence=None,
            eligibility_evidence="eligibility.json",
            integration_evidence="integration.json",
            delivery_issue=9,
            integration_authorization_id="ready-integration-authorization-001",
            expected_integration_signer="aroviqen",
        )

        def read_json(path: str, _label: str) -> Any:
            return integration if path == "integration.json" else receipt

        def git_result(
            _repository_root: Path,
            command: list[str],
            *,
            allow_failure: bool = False,
        ) -> Any:
            del allow_failure
            if command[:4] == ["rev-list", "--parents", "-n", "1"]:
                stdout = f"{final_head} {reviewed.head_sha} {reviewed.base_sha}\n"
                stderr = ""
            elif command == ["rev-parse", "HEAD^{tree}"]:
                stdout = f"{tree}\n"
                stderr = ""
            elif command[:2] == ["show", "-s"]:
                trailer = (
                    integration_digest
                    if "SecPal-Integration-Evidence" in command[-2]
                    else receipt["receipt_digest"]
                )
                stdout = f"{trailer}\n"
                stderr = ""
            elif command[:2] == ["cat-file", "commit"]:
                stdout = (
                    "tree deadbeef\ngpgsig -----BEGIN SSH SIGNATURE-----\n"
                    " signature\n -----END SSH SIGNATURE-----\n\nmessage\n"
                )
                stderr = ""
            elif command[:2] == ["verify-commit", "--raw"]:
                stdout = ""
                stderr = (
                    'Good "git" signature for aroviqen with ED25519 key '
                    "SHA256:test\n"
                )
            elif command[:2] == ["merge-tree", "--write-tree"]:
                stdout = f"{tree}\x00"
                stderr = ""
            elif command[:2] == ["diff-tree", "--raw"]:
                stdout = ""
                stderr = ""
            else:
                raise AssertionError(command)
            return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

        with (
            mock.patch.object(
                actions,
                "_attestation_local_state",
                return_value=(final_head, ""),
            ),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value=entry),
            mock.patch.object(actions, "_read_json", side_effect=read_json),
            mock.patch.object(actions, "_run_attestation_git", side_effect=git_result),
            mock.patch.object(
                fast_path,
                "_run_integration_commit_git",
                side_effect=lambda root, command: git_result(root, command),
            ),
            mock.patch.object(actions, "_verify_ready_integration_prior_authority"),
            mock.patch.object(
                actions,
                "_resolution_eligibility_digest",
                return_value=eligibility_digest,
            ),
            mock.patch.object(actions, "_write_fast_report") as write_report,
        ):
            self.assertEqual(actions._command_attest_validation(arguments), 0)
        write_report.assert_called_once()
        self.assertEqual(
            write_report.call_args.args[1]["kind"],
            "ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION",
        )

    def test_ready_integration_evidence_fails_closed_for_identity_and_lifecycle_drift(
        self,
    ) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        tree = "a" * 40
        original = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=registry
        )
        cases = (
            "swapped_parents",
            "missing_parent",
            "extra_parent",
            "stale_first_parent",
            "substituted_first_parent",
            "substituted_second_parent",
            "base_snapshot_mismatch",
            "tree_mismatch",
            "repository_substitution",
            "pull_request_substitution",
            "topology_substitution",
            "version_substitution",
            "legacy_version",
            "ambiguous_topology",
            "conflict_path_substitution",
            "stale_reviewed_state",
            "stale_stable_feedback",
            "stale_registry",
            "stale_command_set",
            "bound_ref_drift",
            "draft_transition",
            "fabricated_ready_transition",
            "review_request",
            "review_counter_increment",
            "remediation_counter_increment",
            "cycle_3",
            "ineligible",
        )
        for case in cases:
            candidate = copy.deepcopy(original)
            observed_tree = tree
            if case == "swapped_parents":
                candidate["ordered_parent_shas"].reverse()
            elif case == "missing_parent":
                candidate["ordered_parent_shas"].pop()
            elif case == "extra_parent":
                candidate["ordered_parent_shas"].append("f" * 40)
            elif case == "stale_first_parent":
                candidate["prior_delivery_head_sha"] = "b" * 40
            elif case == "substituted_first_parent":
                candidate["ordered_parent_shas"][0] = "c" * 40
            elif case == "substituted_second_parent":
                candidate["ordered_parent_shas"][1] = "c" * 40
            elif case == "base_snapshot_mismatch":
                candidate["target_base"]["observed_sha"] = "d" * 40
            elif case == "tree_mismatch":
                observed_tree = "b" * 40
            elif case == "repository_substitution":
                candidate["repository"] = "SecPal/api"
            elif case == "pull_request_substitution":
                candidate["pull_request_number"] = 2
            elif case == "topology_substitution":
                candidate["kind"] = "GENERIC_MERGE"
            elif case == "version_substitution":
                candidate["schema_version"] = "2.0"
            elif case == "legacy_version":
                candidate["schema_version"] = "1.0"
            elif case == "ambiguous_topology":
                candidate["allow_merge_commit"] = True
            elif case == "conflict_path_substitution":
                candidate["mechanical_conflict_paths"] = ["z.txt", "a.txt"]
            elif case == "stale_reviewed_state":
                candidate["reviewed_state_digest"] = "0" * 64
            elif case == "stale_stable_feedback":
                candidate["reviewed_feedback_digest"] = "0" * 64
            elif case == "stale_registry":
                candidate["validation_execution"]["registry_digest"] = "0" * 64
            elif case == "stale_command_set":
                candidate["validation_execution"]["command_set_digest"] = "0" * 64
            elif case == "bound_ref_drift":
                candidate["target_base"]["ref"] = "release"
            elif case == "draft_transition":
                candidate["eligibility"]["draft_after"] = True
            elif case == "fabricated_ready_transition":
                candidate["eligibility"]["ready_transition"] = True
            elif case == "review_request":
                candidate["eligibility"]["review_requested"] = True
            elif case == "review_counter_increment":
                candidate["eligibility"]["unrestricted_reviews_after"] = 2
            elif case == "remediation_counter_increment":
                candidate["eligibility"]["remediation_cycles_after"] = 2
            elif case == "cycle_3":
                candidate["eligibility"]["cycle_3"] = True
            else:
                candidate["eligibility"]["eligible"] = False
            with self.subTest(case=case), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_evidence(
                    candidate,
                    repository="SecPal/.github",
                    reviewed_state=reviewed,
                    registry=registry,
                    validated_tree_sha=observed_tree,
                )

    def test_ready_integration_explicit_selection_rejects_issue_or_signer_substitution(
        self,
    ) -> None:
        reviewed = fast_feedback()
        integration = ready_integration_evidence(
            reviewed, validated_tree="a" * 40
        )
        base_arguments = {
            "delivery_issue": integration["delivery_issue_number"],
            "integration_authorization_id": integration["authorization_id"],
            "expected_integration_signer": integration["expected_signer"]["identity"],
        }
        actions._verify_integration_selection(
            integration, SimpleNamespace(**base_arguments)
        )
        for field, value in (
            ("delivery_issue", 10),
            ("integration_authorization_id", "another-authorization"),
            ("expected_integration_signer", "another-signer"),
        ):
            changed = {**base_arguments, field: value}
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                actions._verify_integration_selection(
                    integration, SimpleNamespace(**changed)
                )

    def test_ready_integration_commit_requires_exactly_two_ordered_parents(self) -> None:
        head = "d" * 40
        first = "e" * 40
        second = "f" * 40
        for case, output in (
            ("missing", f"{head} {first}\n"),
            ("swapped", f"{head} {second} {first}\n"),
            ("extra", f"{head} {first} {second} {'a' * 40}\n"),
            ("stale_first", f"{head} {'b' * 40} {second}\n"),
            ("stale_second", f"{head} {first} {'b' * 40}\n"),
        ):
            with (
                self.subTest(case=case),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    return_value=SimpleNamespace(stdout=output),
                ),
                self.assertRaisesRegex(fast_path.SecurityBlocker, "ordered parents"),
            ):
                actions._validated_integration_commit_parents(
                    REPO_ROOT, head, [first, second]
                )

    def test_ready_integration_manual_delta_must_match_the_exact_tree_delta(self) -> None:
        reviewed = fast_feedback()
        integration = fast_path.normalize_ready_integration_evidence(
            ready_integration_evidence(reviewed, validated_tree="a" * 40),
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=fast_registry(),
            validated_tree_sha="a" * 40,
        )
        raw_delta = (
            f":100644 100644 {'1' * 40} {'2' * 40} M\x00"
            "governance.md\x00"
        )
        with (
            mock.patch.object(
                actions,
                "_mechanical_integration_result",
                return_value=("a" * 40, []),
            ),
            mock.patch.object(
                actions,
                "_run_attestation_git",
                return_value=SimpleNamespace(returncode=0, stdout=raw_delta, stderr=""),
            ),
        ):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "not authenticated"
            ):
                actions._verify_integration_tree_delta(
                    REPO_ROOT, integration, "a" * 40
                )
        integration["manual_conflict_resolution_delta"] = [
            {
                "path": "governance.md",
                "status": "M",
                "old_mode": "100644",
                "new_mode": "100644",
                "old_oid": "1" * 40,
                "new_oid": "2" * 40,
            }
        ]
        with (
            mock.patch.object(
                actions,
                "_mechanical_integration_result",
                return_value=("a" * 40, []),
            ),
            mock.patch.object(
                actions,
                "_run_attestation_git",
                return_value=SimpleNamespace(returncode=0, stdout=raw_delta, stderr=""),
            ),
        ):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "clean mechanical integration"
            ):
                actions._verify_integration_tree_delta(
                    REPO_ROOT, integration, "a" * 40
                )
        with mock.patch.object(
            actions,
            "_mechanical_integration_result",
            return_value=("b" * 40, []),
        ):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "authorized parents"
            ):
                actions._verify_integration_tree_delta(
                    REPO_ROOT, integration, "a" * 40
                )

    def test_ready_integration_rejects_unchanged_synthetic_conflict_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="secpal-integration-conflict-") as directory:
            repository = Path(directory)

            def git(*arguments: str) -> str:
                return subprocess.run(
                    ["git", *arguments],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("init", "-q")
            git("config", "user.name", "Conflict Fixture")
            git("config", "user.email", "conflict@example.test")
            (repository / "conflict.txt").write_text("base\n", encoding="utf-8")
            git("add", "conflict.txt")
            git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "left")
            (repository / "conflict.txt").write_text("left\n", encoding="utf-8")
            git("commit", "-qam", "left")
            left = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "right", base)
            (repository / "conflict.txt").write_text("right\n", encoding="utf-8")
            git("commit", "-qam", "right")
            right = git("rev-parse", "HEAD")
            result = subprocess.run(
                [
                    "git",
                    "merge-tree",
                    "--write-tree",
                    "--no-messages",
                    "--name-only",
                    "-z",
                    left,
                    right,
                ],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            synthetic_tree = result.stdout.split("\x00")[0]
            self.assertIn("<<<<<<<", git("show", f"{synthetic_tree}:conflict.txt"))
            reviewed = fast_feedback(head_sha=left)
            reviewed = fast_path.StableFeedbackState(
                repository=reviewed.repository,
                pull_request_number=reviewed.pull_request_number,
                head_sha=left,
                base_ref=reviewed.base_ref,
                base_sha=right,
                pr_state=reviewed.pr_state,
                feedback=reviewed.feedback,
            )
            integration = fast_path.normalize_ready_integration_evidence(
                ready_integration_evidence(
                    reviewed, validated_tree=synthetic_tree
                ),
                repository="SecPal/.github",
                reviewed_state=reviewed,
                registry=fast_registry(),
                validated_tree_sha=synthetic_tree,
            )
            integration["mechanical_conflict_paths"] = ["conflict.txt"]
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "unresolved mechanical conflict"
            ):
                actions._verify_integration_tree_delta(
                    repository, integration, synthetic_tree
                )

    def test_ready_integration_authenticates_complete_bounded_conflict_resolution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="secpal-integration-resolution-") as directory:
            repository = Path(directory)

            def git(*arguments: str) -> str:
                return subprocess.run(
                    ["git", *arguments], cwd=repository, check=True,
                    capture_output=True, text=True,
                ).stdout.strip()

            git("init", "-q")
            git("config", "user.name", "Resolution Fixture")
            git("config", "user.email", "resolution@example.test")
            for path in ("a.txt", "b.txt"):
                (repository / path).write_text("base\n", encoding="utf-8")
            (repository / "bounded.txt").write_text("unchanged\n", encoding="utf-8")
            git("add", "."); git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "left")
            for path in ("a.txt", "b.txt"):
                (repository / path).write_text("left\n", encoding="utf-8")
            git("commit", "-qam", "left")
            left = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "right", base)
            for path in ("a.txt", "b.txt"):
                (repository / path).write_text("right\n", encoding="utf-8")
            git("commit", "-qam", "right")
            right = git("rev-parse", "HEAD")
            mechanical_tree, conflict_paths = actions._mechanical_integration_result(
                repository, [left, right]
            )
            self.assertEqual(conflict_paths, ["a.txt", "b.txt"])
            reviewed = fast_path.StableFeedbackState(
                repository="SecPal/.github", pull_request_number=746,
                head_sha=left, base_ref="main", base_sha=right, pr_state="OPEN",
                feedback={"pull_request_reactions": [], "reviews": [], "conversation_comments": [], "threads": []},
            )

            def candidate(
                updates: dict[str, str | bytes | None],
            ) -> tuple[str, dict[str, Any]]:
                git("read-tree", mechanical_tree)
                for path, content in updates.items():
                    target = repository / path
                    if content is None:
                        git("rm", "-q", "-f", "--cached", "--ignore-unmatch", path)
                    elif isinstance(content, bytes):
                        target.write_bytes(content)
                        git("add", path)
                    else:
                        target.write_text(content, encoding="utf-8")
                        git("add", path)
                tree = git("write-tree")
                value = ready_integration_evidence(
                    reviewed, validated_tree=tree
                )
                value["mechanical_merge_tree_sha"] = mechanical_tree
                value["mechanical_conflict_paths"] = conflict_paths
                value["manual_conflict_resolution_delta"] = (
                    actions._integration_tree_delta(
                        repository, mechanical_tree, tree
                    )
                )
                return tree, fast_path.normalize_ready_integration_evidence(
                    value, repository="SecPal/.github", reviewed_state=reviewed,
                    registry=fast_registry(), validated_tree_sha=tree,
                )

            resolved_tree, resolved = candidate(
                {"a.txt": "resolved a\n", "b.txt": "resolved b\n"}
            )
            actions._verify_integration_tree_delta(
                repository, resolved, resolved_tree
            )
            for case, content in (
                ("ordinary prose", "ordinary maintained text\n"),
                ("empty file", ""),
                ("documentation separator", "heading\n=======\nbody\n"),
                ("isolated base component", "||||||| base example\n"),
                ("isolated separator component", "=======\n"),
                ("isolated close component", ">>>>>>> closing example\n"),
                (
                    "opening-like text outside the grammar",
                    "<<<<<<<not-a-marker\n <<<<<<< indented\n<<<<<<<\ttabbed\n",
                ),
            ):
                with self.subTest(resolved_content=case):
                    text_tree, text_evidence = candidate(
                        {"a.txt": content, "b.txt": "resolved b\n"}
                    )
                    actions._verify_integration_tree_delta(
                        repository, text_evidence, text_tree
                    )
            deleted_tree, deleted = candidate({"a.txt": None, "b.txt": None})
            actions._verify_integration_tree_delta(
                repository, deleted, deleted_tree
            )
            partial_tree, partial = candidate({"a.txt": "resolved a\n"})
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "every unresolved mechanical conflict"
            ):
                actions._verify_integration_tree_delta(
                    repository, partial, partial_tree
                )
            extra_tree, extra = candidate(
                {
                    "a.txt": "resolved a\n",
                    "b.txt": "resolved b\n",
                    "bounded.txt": "unauthorized\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "every unresolved mechanical conflict"
            ):
                actions._verify_integration_tree_delta(
                    repository, extra, extra_tree
                )
            marker_tree, marker = candidate(
                {
                    "a.txt": "<<<<<<< retained\nleft\n=======\nright\n>>>>>>> retained\n",
                    "b.txt": "resolved b\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "retains Git conflict markers"
            ):
                actions._verify_integration_tree_delta(
                    repository, marker, marker_tree
                )
            diff3_tree, diff3 = candidate(
                {
                    "a.txt": (
                        "<<<<<<< ours\nleft\n||||||| base\nbase\n"
                        "=======\nright\n>>>>>>> theirs\n"
                    ),
                    "b.txt": "resolved b\n",
                }
            )
            bare_marker_tree, bare_marker = candidate(
                {
                    "a.txt": "<<<<<<<\nleft\n=======\nright\n>>>>>>>\n",
                    "b.txt": "resolved b\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "retains Git conflict markers"
            ):
                actions._verify_integration_tree_delta(
                    repository, bare_marker, bare_marker_tree
                )
            for case, content in (
                (
                    "diff3",
                    "<<<<<<< ours\nleft\n||||||| base\nbase\n=======\nright\n>>>>>>> theirs\n",
                ),
                (
                    "longer runs",
                    "<<<<<<<<< ours\nleft\n||||||||| base\nbase\n=========\nright\n>>>>>>>>> theirs\n",
                ),
                ("incomplete opening", "<<<<<<< unresolved\nleft\n"),
                (
                    "nested opening",
                    "<<<<<<< outer\n<<<<<<< inner\n=======\nright\n>>>>>>> outer\n",
                ),
                (
                    "extra separator in open conflict",
                    "<<<<<<< ours\n=======\n=======\nright\n>>>>>>> theirs\n",
                ),
                (
                    "truncated two-way tail",
                    "=======\ntheirs\n>>>>>>> branch\n",
                ),
                (
                    "truncated diff3 tail",
                    "||||||| base\nbase\n=======\ntheirs\n>>>>>>> branch\n",
                ),
                (
                    "malformed truncated diff3 tail",
                    "||||||| base\nbase\n>>>>>>> branch\n",
                ),
                (
                    "CRLF conflict",
                    "<<<<<<< ours\r\nleft\r\n=======\r\nright\r\n>>>>>>> theirs\r\n",
                ),
            ):
                with self.subTest(unresolved_content=case):
                    unresolved_tree, unresolved = candidate(
                        {"a.txt": content, "b.txt": "resolved b\n"}
                    )
                    with self.assertRaisesRegex(
                        fast_path.SecurityBlocker, "retains Git conflict markers"
                    ):
                        actions._verify_integration_tree_delta(
                            repository, unresolved, unresolved_tree
                        )

            configured_separator_tree, configured_separator = candidate(
                {"a.txt": "heading\n=======\nbody\n", "b.txt": "resolved b\n"}
            )
            for case, settings in (
                ("column", {"grep.column": "true"}),
                ("color", {"color.grep": "always"}),
                (
                    "column and color",
                    {"grep.column": "true", "color.grep": "always"},
                ),
            ):
                with self.subTest(ambient_git_configuration=case):
                    for key, value in settings.items():
                        git("config", key, value)
                    try:
                        actions._verify_integration_tree_delta(
                            repository, configured_separator, configured_separator_tree
                        )
                        for unresolved_tree, unresolved in (
                            (marker_tree, marker),
                            (diff3_tree, diff3),
                        ):
                            with self.assertRaisesRegex(
                                fast_path.SecurityBlocker,
                                "retains Git conflict markers",
                            ):
                                actions._verify_integration_tree_delta(
                                    repository, unresolved, unresolved_tree
                                )
                    finally:
                        for key in settings:
                            git("config", "--unset-all", key)

            binary_tree, binary = candidate(
                {
                    "a.txt": (
                        b"\x00<<<<<<< retained\nleft\n=======\nright\n"
                        b">>>>>>> retained\n"
                    ),
                    "b.txt": "resolved b\n",
                }
            )
            actions._verify_integration_tree_delta(repository, binary, binary_tree)
            late_nul_tree, late_nul = candidate(
                {
                    "a.txt": (
                        b"<<<<<<< retained\nleft\n=======\nright\n"
                        b">>>>>>> retained\n" + b"x" * 8000 + b"\x00"
                    ),
                    "b.txt": "resolved b\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "retains Git conflict markers"
            ):
                actions._verify_integration_tree_delta(
                    repository, late_nul, late_nul_tree
                )

            conflict_prefix = (
                b"<<<<<<< retained\nleft\n=======\nright\n>>>>>>> retained\n"
            )
            nul_before_boundary_tree, nul_before_boundary = candidate(
                {
                    "a.txt": (
                        conflict_prefix
                        + b"x" * (7999 - len(conflict_prefix))
                        + b"\x00"
                    ),
                    "b.txt": "resolved b\n",
                }
            )
            actions._verify_integration_tree_delta(
                repository, nul_before_boundary, nul_before_boundary_tree
            )
            nul_at_boundary_tree, nul_at_boundary = candidate(
                {
                    "a.txt": (
                        conflict_prefix
                        + b"x" * (8000 - len(conflict_prefix))
                        + b"\x00"
                    ),
                    "b.txt": "resolved b\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "retains Git conflict markers"
            ):
                actions._verify_integration_tree_delta(
                    repository, nul_at_boundary, nul_at_boundary_tree
                )
            multibyte_late_nul_tree, multibyte_late_nul = candidate(
                {
                    "a.txt": conflict_prefix + "é".encode("utf-8") * 5000 + b"\x00",
                    "b.txt": "resolved b\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "retains Git conflict markers"
            ):
                actions._verify_integration_tree_delta(
                    repository, multibyte_late_nul, multibyte_late_nul_tree
                )
            undecodable_text_tree, undecodable_text = candidate(
                {
                    "a.txt": conflict_prefix + b"\xff",
                    "b.txt": "resolved b\n",
                }
            )
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "retains Git conflict markers"
            ):
                actions._verify_integration_tree_delta(
                    repository, undecodable_text, undecodable_text_tree
                )

            limit = actions.MAX_INTEGRATION_CONFLICT_CONTENT_BYTES
            boundary_tree, boundary = candidate(
                {"a.txt": "=======\n" + "x" * (limit - 8), "b.txt": None}
            )
            actions._verify_integration_tree_delta(
                repository, boundary, boundary_tree
            )
            oversized_tree, oversized = candidate(
                {"a.txt": "x" * (limit + 1), "b.txt": None}
            )
            with (
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    wraps=actions._run_attestation_git,
                ) as run_git,
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker,
                    "conflict content exceeds the authenticated size bound",
                ),
            ):
                actions._verify_integration_tree_delta(
                    repository, oversized, oversized_tree
                )
            commands = [call.args[1] for call in run_git.call_args_list]
            self.assertTrue(
                any(command[:2] == ["cat-file", "-s"] for command in commands)
            )
            self.assertFalse(
                any(command[:2] == ["cat-file", "blob"] for command in commands)
            )

    def test_prior_771_resolved_tree_accepts_authenticated_separator_lines(
        self,
    ) -> None:
        prior_head = "4bea89ef822e31a37a6a679550ff9757853b1e55"
        current_main = "daa953695caaed338b81dad1fc8d8f7012382ae7"
        mechanical_tree = "78265627279ab10448a35659846f81d266cb7a1e"
        resolved_tree = "a95eeb850ff1b5158ba87da5e355f0d00ed7ee13"
        expected_conflict_paths = [
            ".agents/skills/secpal-pr-review/references/repositories.json",
            ".agents/skills/secpal-pr-review/references/repositories.schema.json",
            "CHANGELOG.md",
            "docs/native-lifecycle-genesis-admission.md",
            "docs/secpal-pr-review-workflow.md",
            "scripts/README.md",
            "scripts/secpal_pr_review/lifecycle_authority.py",
            "scripts/secpal_pr_review/lifecycle_publication.py",
            "tests/secpal-lifecycle-authority-unit.py",
            "tests/secpal-lifecycle-publication-unit.py",
            "tests/secpal-pr-review-skill-policy.sh",
        ]
        bundle = FIXTURES / "issue771-exact-candidate.bundle"
        with tempfile.TemporaryDirectory(prefix="secpal-issue771-candidate-") as directory:
            repository = Path(directory) / "repository"
            subprocess.run(
                ["git", "clone", "-q", "--no-checkout", str(REPO_ROOT), str(repository)],
                check=True,
            )
            subprocess.run(
                [
                    "git", "fetch", "-q", str(bundle),
                    "refs/heads/issue771-ready-counters:refs/heads/issue771-ready-counters",
                    "refs/heads/issue771-resolved-fixture:refs/heads/issue771-resolved-fixture",
                ],
                cwd=repository,
                check=True,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "rev-parse", "refs/heads/issue771-ready-counters"],
                    cwd=repository, check=True, capture_output=True, text=True,
                ).stdout.strip(),
                prior_head,
            )
            observed_resolved_tree = subprocess.run(
                ["git", "rev-parse", "refs/heads/issue771-resolved-fixture^{tree}"],
                cwd=repository, check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(observed_resolved_tree, resolved_tree)
            observed_mechanical_tree, conflict_paths = (
                actions._mechanical_integration_result(
                    repository, [prior_head, current_main]
                )
            )
            self.assertEqual(observed_mechanical_tree, mechanical_tree)
            self.assertEqual(conflict_paths, expected_conflict_paths)
            reviewed = fast_path.StableFeedbackState(
                repository="SecPal/.github",
                pull_request_number=772,
                head_sha=prior_head,
                base_ref="main",
                base_sha=current_main,
                pr_state="OPEN",
                feedback={
                    "pull_request_reactions": [],
                    "reviews": [],
                    "conversation_comments": [],
                    "threads": [],
                },
            )
            value = ready_integration_evidence(
                reviewed, validated_tree=resolved_tree
            )
            value["mechanical_merge_tree_sha"] = mechanical_tree
            value["mechanical_conflict_paths"] = conflict_paths
            value["manual_conflict_resolution_delta"] = (
                actions._integration_tree_delta(
                    repository, mechanical_tree, resolved_tree
                )
            )
            expected_delta_oids = {
                ".agents/skills/secpal-pr-review/references/repositories.json": (
                    "8a5cfe22c65344d07c67ead9451638db0c8786b9",
                    "46e5f260802319bf3ee05d1dbb3c0cda9d9e1639",
                ),
                ".agents/skills/secpal-pr-review/references/repositories.schema.json": (
                    "5692c76b1096ed46c08c58197329af233e4b223b",
                    "aedf34c46a49bb589169f2b2a1ac664b4b86bbfc",
                ),
                "CHANGELOG.md": (
                    "fc9fd01c480a68b41c827c5ff55177d7619b54f5",
                    "edb184325addf9da3c2fe279acb8403b914cfeb1",
                ),
                "docs/native-lifecycle-genesis-admission.md": (
                    "424223d808a31aa43aae19da453e438cb2906215",
                    "b8a27537f7a5685f2745a03da362008742f260ea",
                ),
                "docs/secpal-pr-review-workflow.md": (
                    "5f7a61d598a7c020d488888646ad589caafd9f1b",
                    "e551a54ae16061de895b76aeb6d384a94dc7ca67",
                ),
                "scripts/README.md": (
                    "c30c480daf38cd7b5da3a6255ca2641c30a9e5df",
                    "f8df0b6d87b7424543d2bf3faa59da1add655524",
                ),
                "scripts/secpal_pr_review/lifecycle_authority.py": (
                    "a04e1ab67f400d20ece90279edeef907daceb2c3",
                    "78d379455cf3e4b34d023e67d621e67c20bdc18b",
                ),
                "scripts/secpal_pr_review/lifecycle_publication.py": (
                    "13819a9de8b6e2944819a02c8fac9a16c92dd1cb",
                    "b1dc232e42f9dd6c6dff889d303ff44126acbc3e",
                ),
                "tests/secpal-lifecycle-authority-unit.py": (
                    "0e2522e79b7c1a44fbc582ceb2e21cfa2ea0fc3a",
                    "3c803689e5f66ba8a16419518c8ae0655b4160d8",
                ),
                "tests/secpal-lifecycle-publication-unit.py": (
                    "75a7844ee79235e80f2ed3896b7f81077033de03",
                    "810eb90147a30c7e9f35db4386f91a234785e577",
                ),
                "tests/secpal-pr-review-skill-policy.sh": (
                    "d00b04c7b0454b0682087b5bd260084b43bf0b67",
                    "36c54529315959d1838fe7b1ce6c51d1f58cd5e2",
                ),
            }
            self.assertEqual(
                value["ordered_parent_shas"], [prior_head, current_main]
            )
            self.assertEqual(
                {
                    item["path"]: (item["old_oid"], item["new_oid"])
                    for item in value["manual_conflict_resolution_delta"]
                },
                expected_delta_oids,
            )
            integration = fast_path.normalize_ready_integration_evidence(
                value,
                repository="SecPal/.github",
                reviewed_state=reviewed,
                registry=fast_registry(),
                validated_tree_sha=resolved_tree,
            )
            actions._verify_integration_tree_delta(
                repository, integration, resolved_tree
            )

    def test_shared_marker_primitive_is_integration_lifecycle_neutral(self) -> None:
        for topology in (
            "TWO_PARENT_READY_INTEGRATION",
            "PRE_ENROLLMENT_DRAFT_INTEGRATION",
        ):
            with (
                self.subTest(topology=topology),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    return_value=SimpleNamespace(
                        returncode=0, stdout="", stderr=""
                    ),
                ) as run_git,
            ):
                actions._reject_integration_conflict_markers(
                    REPO_ROOT, "a" * 40, ["authenticated-conflict.txt"]
                )
                self.assertNotIn(topology, run_git.call_args.args[1])

    def test_marker_primitive_rejects_unauthenticated_scan_results(self) -> None:
        tree = "a" * 40
        path = "authenticated-conflict.txt"
        oid = "b" * 40
        for case, returncode, output in (
            ("Git failure", 2, ""),
            ("truncated record", 0, f"100644 blob {oid}\t{path}"),
            ("wrong path", 0, f"100644 blob {oid}\tother.txt\x00"),
            (
                "multiple records",
                0,
                f"100644 blob {oid}\t{path}\x00100644 blob {oid}\t{path}\x00",
            ),
            ("tree entry", 0, f"040000 tree {oid}\t{path}\x00"),
            ("invalid object", 0, f"100644 blob invalid\t{path}\x00"),
        ):
            with (
                self.subTest(case=case),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    return_value=SimpleNamespace(
                        returncode=returncode, stdout=output, stderr="failed"
                    ),
                ),
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker, "cannot be authenticated"
                ),
            ):
                actions._reject_integration_conflict_markers(
                    REPO_ROOT, tree, [path]
                )

        valid_entry = SimpleNamespace(
            returncode=0,
            stdout=f"100644 blob {oid}\t{path}\x00",
            stderr="",
        )
        for case, second in (
            (
                "object size failure",
                SimpleNamespace(returncode=1, stdout="", stderr="failed"),
            ),
            (
                "malformed object size",
                SimpleNamespace(returncode=0, stdout="unknown\n", stderr=""),
            ),
        ):
            with (
                self.subTest(case=case),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    side_effect=[valid_entry, second],
                ),
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker, "cannot be authenticated"
                ),
            ):
                actions._reject_integration_conflict_markers(
                    REPO_ROOT, tree, [path]
                )

    def test_ready_integration_rejects_unexpected_merge_tree_status(self) -> None:
        with (
            mock.patch.object(
                actions,
                "_run_attestation_git",
                return_value=SimpleNamespace(returncode=2, stdout="", stderr="failed"),
            ),
            self.assertRaisesRegex(
                fast_path.SecurityBlocker, "cannot be derived"
            ),
        ):
            actions._mechanical_integration_result(
                REPO_ROOT, ["a" * 40, "b" * 40]
            )

    def test_ready_integration_prior_authority_rejects_receipt_chain_substitution(
        self,
    ) -> None:
        prior_reviewed = fast_feedback(head_sha="e" * 40)
        reviewed = fast_feedback(head_sha="d" * 40)
        registry = fast_registry()
        tree = "a" * 40
        receipt_a = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=prior_reviewed.head_sha,
            validated_tree_sha=tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=prior_reviewed,
            manual_gate_evidence=[],
        )
        attestation_a = fast_path.create_validation_attestation(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=prior_reviewed,
            validation_receipt=receipt_a,
        )
        authority = ready_integration_prior_authority(reviewed)
        authority.update(
            prior_delivery_tree_sha=tree,
            prior_validation_receipt_digest="f" * 64,
            prior_final_attestation_digest=attestation_a["attestation_digest"],
        )
        authority = fast_path.normalize_ready_integration_prior_authority(authority)
        integration = ready_integration_evidence(reviewed, validated_tree=tree)
        integration["prior_authority_digest"] = fast_path.digest_json(authority)
        integration = fast_path.normalize_ready_integration_evidence(
            integration,
            repository="SecPal/.github",
            reviewed_state=reviewed,
            registry=registry,
            validated_tree_sha=tree,
        )
        arguments = SimpleNamespace(
            repo="SecPal/.github",
            delivery_issue=9,
            prior_authority="authority.json",
            prior_reviewed_state="prior-reviewed.json",
            prior_receipt="prior-receipt.json",
            prior_attestation="prior-attestation.json",
            prior_authority_tag_ref="refs/tags/prior-authority",
            expected_prior_authority_signer="aroviqen",
        )

        def read_json(path: str, _label: str) -> Any:
            return {
                "authority.json": authority,
                "prior-receipt.json": {"receipt_digest": "f" * 64},
                "prior-attestation.json": attestation_a,
            }[path]

        def git_result(
            _repository_root: Path,
            command: list[str],
            *,
            allow_failure: bool = False,
        ) -> Any:
            del allow_failure
            if command[:2] == ["rev-parse", f"{reviewed.head_sha}^{{tree}}"]:
                stdout = tree
            elif command[:2] == ["cat-file", "commit"]:
                stdout = "tree deadbeef\ngpgsig -----BEGIN SSH SIGNATURE-----\n"
            elif command[:2] in (["verify-commit", "--raw"], ["verify-tag", "--raw"]):
                stdout = 'Good "git" signature for aroviqen with ED25519 key SHA256:test\n'
            elif command[:2] == ["rev-parse", "refs/tags/prior-authority^{}"]:
                stdout = reviewed.head_sha
            elif command[0] == "for-each-ref":
                stdout = fast_path.digest_json(authority)
            else:
                raise AssertionError(command)
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        with (
            mock.patch.object(actions, "_read_json", side_effect=read_json),
            mock.patch.object(actions, "_load_fast_state", return_value=prior_reviewed),
            mock.patch.object(actions, "_validated_commit_parent", return_value=prior_reviewed.head_sha),
            mock.patch.object(actions, "_run_attestation_git", side_effect=git_result),
            mock.patch.object(
                actions,
                "_prior_delivery_registry_binding",
                return_value=registry,
            ),
            mock.patch.object(
                actions,
                "_commit_validation_receipt_digest",
                return_value=receipt_a["receipt_digest"],
            ),
            self.assertRaisesRegex(
                fast_path.SecurityBlocker, "prior delivery receipt identity changed"
            ),
        ):
            actions._verify_ready_integration_prior_authority(
                arguments=arguments,
                repository_root=REPO_ROOT,
                binding=registry,
                integration_evidence=integration,
                live_observation=None,
            )

    def test_ready_integration_openpgp_accepts_authorized_primary_fingerprint(
        self,
    ) -> None:
        signing_subkey = "1" * 40
        primary_key = "2" * 40
        output = (
            "[GNUPG:] VALIDSIG "
            f"{signing_subkey} 2026-08-28 1787890000 0 4 0 1 10 00 {primary_key}\n"
        )
        actions._verify_integration_signer(
            output,
            {"kind": "OPENPGP_FINGERPRINT", "identity": primary_key},
        )
        for label, changed_output, expected in (
            ("wrong_primary", output, "3" * 40),
            (
                "unrelated_subkey",
                output.replace(signing_subkey, "4" * 40).replace(
                    primary_key, "5" * 40
                ),
                primary_key,
            ),
            ("missing_primary", output.rsplit(" ", 1)[0] + "\n", primary_key),
            ("ambiguous", output + output, primary_key),
        ):
            with (
                self.subTest(case=label),
                self.assertRaises(fast_path.SecurityBlocker),
            ):
                actions._verify_integration_signer(
                    changed_output,
                    {"kind": "OPENPGP_FINGERPRINT", "identity": expected},
                )

    def test_ready_integration_pins_one_real_authority_tag_object(self) -> None:
        with tempfile.TemporaryDirectory(prefix="secpal-authority-tag-race-") as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()

            def git(*arguments: str, input_text: str | None = None) -> str:
                return subprocess.run(
                    ["git", *arguments], cwd=repository, check=True,
                    capture_output=True, text=True, input=input_text,
                ).stdout.strip()

            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / "key")],
                check=True, capture_output=True,
            )
            principal = "authority@example.test"
            (root / "allowed").write_text(
                f"{principal} {(root / 'key.pub').read_text()}", encoding="utf-8"
            )
            git("init", "-q")
            for key, value in (
                ("user.name", "Authority Fixture"), ("user.email", principal),
                ("gpg.format", "ssh"), ("user.signingkey", str(root / "key")),
                ("gpg.ssh.allowedSignersFile", str(root / "allowed")),
            ):
                git("config", key, value)
            (repository / "base.txt").write_text("base\n", encoding="utf-8")
            git("add", "base.txt"); git("commit", "-q", "-S", "-m", "base")
            base = git("rev-parse", "HEAD")
            (repository / "delivery.txt").write_text("delivery\n", encoding="utf-8")
            git("add", "delivery.txt")
            receipt_digest = "b" * 64
            git("commit", "-q", "-S", "-m", "delivery", "-m", f"SecPal-Validation-Receipt: {receipt_digest}")
            head = git("rev-parse", "HEAD")
            tree = git("rev-parse", "HEAD^{tree}")
            reviewed = fast_feedback(head_sha=head)
            authority = ready_integration_prior_authority(reviewed)
            authority.update(
                prior_delivery_tree_sha=tree,
                prior_validation_receipt_digest=receipt_digest,
                expected_signer={"kind": "SSH_PRINCIPAL", "identity": principal},
            )
            authority = fast_path.normalize_ready_integration_prior_authority(authority)
            authority_digest = fast_path.digest_json(authority)
            wrong_digest = "f" * 64
            git("tag", "-s", "tag-a", head, "-m", "Tag A", "-m", f"SecPal-Prior-Authority: {wrong_digest}")
            git("tag", "-s", "tag-b", base, "-m", "Tag B", "-m", f"SecPal-Prior-Authority: {authority_digest}")
            tag_a = git("rev-parse", "tag-a^{tag}")
            tag_b = git("rev-parse", "tag-b^{tag}")
            git("update-ref", "refs/tags/prior-authority", tag_a)
            integration = ready_integration_evidence(reviewed, validated_tree=tree)
            integration["prior_authority_digest"] = authority_digest
            integration["prior_authority_tag_object_sha"] = tag_a
            integration = fast_path.normalize_ready_integration_evidence(
                integration, repository="SecPal/.github", reviewed_state=reviewed,
                registry=fast_registry(), validated_tree_sha=tree,
            )
            arguments = SimpleNamespace(
                repo="SecPal/.github", delivery_issue=9,
                prior_authority="authority.json", prior_reviewed_state="reviewed.json",
                prior_receipt="receipt.json", prior_attestation="attestation.json",
                prior_authority_tag_ref="refs/tags/prior-authority",
                expected_prior_authority_signer=principal,
            )
            original_run = actions._run_attestation_git
            moved = False

            def moving_run(
                repository_root: Path,
                command: list[str],
                *,
                allow_failure: bool = False,
            ) -> Any:
                nonlocal moved
                if command[:2] == ["verify-tag", "--raw"] and not moved:
                    git("update-ref", "refs/tags/prior-authority", tag_b)
                    moved = True
                return original_run(
                    repository_root, command, allow_failure=allow_failure
                )

            def read_json(path: str, _label: str) -> Any:
                return {
                    "authority.json": authority,
                    "receipt.json": {"receipt_digest": receipt_digest},
                    "attestation.json": {
                        "attestation_digest": authority["prior_final_attestation_digest"],
                        "validation_receipt_digest": receipt_digest,
                    },
                }[path]

            with (
                mock.patch.object(actions, "_read_json", side_effect=read_json),
                mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
                mock.patch.object(
                    fast_path,
                    "create_validation_receipt",
                    return_value={"receipt_digest": receipt_digest},
                ),
                mock.patch.object(fast_path, "verify_validation_attestation"),
                mock.patch.object(actions, "_run_attestation_git", side_effect=moving_run),
                mock.patch.object(
                    actions,
                    "_prior_delivery_registry_binding",
                    return_value=fast_registry(),
                ),
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker, "prior authority tag binding is invalid"
                ),
            ):
                actions._verify_ready_integration_prior_authority(
                    arguments=arguments, repository_root=repository,
                    binding=fast_registry(), integration_evidence=integration,
                    live_observation=None,
                )
            self.assertTrue(moved)

            git("tag", "-s", "tag-c", head, "-m", "Tag C", "-m", f"SecPal-Prior-Authority: {authority_digest}")
            tag_c = git("rev-parse", "tag-c^{tag}")
            git("update-ref", "refs/tags/prior-authority", tag_c)
            valid_integration = copy.deepcopy(integration)
            valid_integration["prior_authority_tag_object_sha"] = tag_c
            with (
                mock.patch.object(actions, "_read_json", side_effect=read_json),
                mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
                mock.patch.object(
                    fast_path,
                    "create_validation_receipt",
                    return_value={"receipt_digest": receipt_digest},
                ),
                mock.patch.object(fast_path, "verify_validation_attestation"),
                mock.patch.object(
                    actions,
                    "_prior_delivery_registry_binding",
                    return_value=fast_registry(),
                ),
                mock.patch.object(
                    actions,
                    "_verify_signature_policy_identity",
                    wraps=actions._verify_signature_policy_identity,
                ) as signature_policy,
                mock.patch.object(
                    actions, "_verify_ready_integration_published_authority"
                ),
            ):
                self.assertEqual(
                    actions._verify_ready_integration_prior_authority(
                        arguments=arguments, repository_root=repository,
                        binding=fast_registry(),
                        integration_evidence=valid_integration,
                        live_observation=None,
                    ),
                    authority,
                )
            self.assertEqual(
                [call.args[0] for call in signature_policy.call_args_list],
                [head, tag_c],
            )

            git("update-ref", "refs/tags/prior-authority", head)
            lightweight = copy.deepcopy(integration)
            lightweight["prior_authority_tag_object_sha"] = head
            with (
                mock.patch.object(actions, "_read_json", side_effect=read_json),
                mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
                mock.patch.object(
                    fast_path,
                    "create_validation_receipt",
                    return_value={"receipt_digest": receipt_digest},
                ),
                mock.patch.object(fast_path, "verify_validation_attestation"),
                mock.patch.object(
                    actions,
                    "_prior_delivery_registry_binding",
                    return_value=fast_registry(),
                ),
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker, "tag object is invalid"
                ),
            ):
                actions._verify_ready_integration_prior_authority(
                    arguments=arguments, repository_root=repository,
                    binding=fast_registry(), integration_evidence=lightweight,
                    live_observation=None,
                )

            git("update-ref", "refs/tags/prior-authority", tag_b)
            wrong_target = copy.deepcopy(integration)
            wrong_target["prior_authority_tag_object_sha"] = tag_b
            with (
                mock.patch.object(actions, "_read_json", side_effect=read_json),
                mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
                mock.patch.object(
                    fast_path,
                    "create_validation_receipt",
                    return_value={"receipt_digest": receipt_digest},
                ),
                mock.patch.object(fast_path, "verify_validation_attestation"),
                mock.patch.object(
                    actions,
                    "_prior_delivery_registry_binding",
                    return_value=fast_registry(),
                ),
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker, "tag binding is invalid"
                ),
            ):
                actions._verify_ready_integration_prior_authority(
                    arguments=arguments, repository_root=repository,
                    binding=fast_registry(), integration_evidence=wrong_target,
                    live_observation=None,
                )

    def test_ready_integration_tag_signature_policy_uses_tag_object_oid(self) -> None:
        tag_oid = "1" * 40
        head = "2" * 40
        local_signature = {
            "state": "valid", "verified": True, "format": "ssh"
        }
        with mock.patch.object(
            fast_path, "verify_commit_signatures", return_value=[]
        ) as verify:
            actions._verify_signature_policy_identity(
                tag_oid, local_signature, fast_registry()["signature_policy"]
            )
        self.assertEqual(verify.call_args.args[0][0]["oid"], tag_oid)
        self.assertNotEqual(verify.call_args.args[0][0]["oid"], head)

    def test_exceptional_recovery_evidence_preserves_exhausted_ready_lifecycle(
        self,
    ) -> None:
        original = fast_feedback(thread_count=5)
        feedback = copy.deepcopy(original.feedback)
        thread_ids = [f"PRRT_RECOVERY_{index}" for index in range(1, 6)]
        for thread, thread_id in zip(feedback["threads"], thread_ids, strict=True):
            thread["node_id"] = thread_id
        reviewed = fast_path.StableFeedbackState(
            repository=original.repository,
            pull_request_number=746,
            head_sha=original.head_sha,
            base_ref=original.base_ref,
            base_sha=original.base_sha,
            pr_state="OPEN",
            feedback=feedback,
        )
        eligibility_digest = "3" * 64
        value = {
            "schema_version": "1.0",
            "kind": "READY_EXCEPTIONAL_RECOVERY",
            "authorization_id": "user-authorized-recovery-746-1",
            "repository": "SecPal/.github",
            "delivery_issue_number": 745,
            "pull_request_number": 746,
            "prior_ready_head_sha": reviewed.head_sha,
            "prior_ready_tree_sha": "1" * 40,
            "recovery_tree_sha": "2" * 40,
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "eligibility_evidence_digest": eligibility_digest,
            "finding_ids": [f"ER746-{index}" for index in range(1, 6)],
            "thread_ids": thread_ids,
            "lifecycle": {
                "unrestricted_reviews": 1,
                "remediation_cycles": 2,
                "cycle_3": False,
                "draft": False,
                "ready": True,
                "ready_transition": False,
                "exceptional_recovery_count": 1,
            },
        }
        normalized = fast_path.normalize_exceptional_recovery_evidence(
            value,
            repository="SecPal/.github",
            reviewed_state=reviewed,
            validated_tree_sha="2" * 40,
            eligibility_evidence_digest=eligibility_digest,
        )
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha="2" * 40,
            registry=fast_registry(),
            command_set=fast_registry()["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            eligibility_evidence_digest=eligibility_digest,
            exceptional_recovery_evidence_digest=fast_path.digest_json(normalized),
        )
        attestation = fast_path.create_validation_attestation(
            repository="SecPal/.github",
            head_sha="4" * 40,
            registry=fast_registry(),
            command_set=fast_registry()["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            validation_receipt=receipt,
        )
        self.assertEqual(
            attestation["exceptional_recovery_evidence_digest"],
            fast_path.digest_json(normalized),
        )
        for case, mutate in (
            ("cycle_3", lambda item: item["lifecycle"].update(cycle_3=True)),
            ("draft", lambda item: item["lifecycle"].update(draft=True, ready=False)),
            ("counter", lambda item: item["lifecycle"].update(remediation_cycles=3)),
            ("thread", lambda item: item["thread_ids"].__setitem__(0, "PRRT_OTHER")),
            ("unknown", lambda item: item.update(allow_cycle_3=True)),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.subTest(case=case), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_exceptional_recovery_evidence(
                    changed,
                    repository="SecPal/.github",
                    reviewed_state=reviewed,
                    validated_tree_sha="2" * 40,
                    eligibility_evidence_digest=eligibility_digest,
                )

    def test_ready_integration_signature_requires_the_explicit_signer(self) -> None:
        actions._verify_integration_signer(
            'Good "git" signature for aroviqen with ED25519 key SHA256:test\n',
            {"kind": "SSH_PRINCIPAL", "identity": "aroviqen"},
        )
        for output in (
            "",
            'Good "git" signature for another with ED25519 key SHA256:test\n',
        ):
            with self.subTest(output=output), self.assertRaisesRegex(
                fast_path.SecurityBlocker, "accepted identity"
            ):
                actions._verify_integration_signer(
                    output,
                    {"kind": "SSH_PRINCIPAL", "identity": "aroviqen"},
                )
        integration = ready_integration_evidence(
            fast_feedback(), validated_tree="a" * 40
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "accepted identity"):
            authenticated_integration_commit(
                "d" * 40, integration, signer="another"
            )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "unsigned"):
            fast_path.verify_commit_signatures(
                [
                    {
                        "oid": "d" * 40,
                        "source": "USER",
                        "local_signature": {
                            "state": "unsigned",
                            "verified": False,
                            "format": "ssh",
                        },
                        "github_verification": {
                            "verified": False,
                            "reason": "unsigned",
                        },
                    }
                ],
                {"accepted_formats": ["ssh", "openpgp"]},
            )

    def test_caller_signature_claims_cannot_mint_integration_authority(self) -> None:
        with self.assertRaises(TypeError):
            fast_path.authenticate_integration_commit(
                head_sha="d" * 40,
                local_signature={
                    "state": "valid",
                    "verified": True,
                    "format": "ssh",
                },
                verification_output=(
                    'Good "git" signature for aroviqen with ED25519 key '
                    "SHA256:caller-claim\n"
                ),
                expected_signer={
                    "kind": "SSH_PRINCIPAL",
                    "identity": "aroviqen",
                },
                signature_policy=fast_registry()["signature_policy"],
            )

    def test_ready_integration_rejects_historical_first_parent_receipt_reuse(self) -> None:
        reviewed = fast_feedback()
        historical_reviewed = fast_feedback(head_sha="c" * 40)
        registry = fast_registry()
        historical_receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=historical_reviewed.head_sha,
            validated_tree_sha="a" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=historical_reviewed,
            manual_gate_evidence=[],
        )
        integration = ready_integration_evidence(
            reviewed, validated_tree="a" * 40, registry=registry
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "invalid or stale"):
            fast_path.create_ready_integration_attestation(
                repository="SecPal/.github",
                head_sha="d" * 40,
                registry=registry,
                command_set=registry["validation"],
                reviewed_state=reviewed,
                validation_receipt=historical_receipt,
                integration_evidence=integration,
            )

    def test_ready_integration_attestation_binds_resolution_eligibility(self) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        tree = "a" * 40
        eligibility_digest = "e" * 64
        integration = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=registry
        )
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha=tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            eligibility_evidence_digest=eligibility_digest,
            integration_evidence_digest=fast_path.digest_json(integration),
        )

        attestation = fast_path.create_ready_integration_attestation(
            repository="SecPal/.github",
            head_sha="d" * 40,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
        )

        self.assertEqual(attestation["schema_version"], "1.2")
        self.assertEqual(
            attestation["kind"],
            "ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION",
        )
        self.assertEqual(
            attestation["eligibility_evidence_digest"], eligibility_digest
        )

        verification = {
            "repository": "SecPal/.github",
            "head_sha": "d" * 40,
            "registry": registry,
            "command_set": registry["validation"],
            "reviewed_state": reviewed,
            "validation_receipt": receipt,
            "integration_evidence": integration,
            "commit_parent_shas": integration["ordered_parent_shas"],
            "commit_tree_sha": tree,
            "commit_validation_receipt_digest": receipt["receipt_digest"],
            "commit_integration_evidence_digest": fast_path.digest_json(
                integration
            ),
            "authenticated_integration_commit": authenticated_integration_commit(
                "d" * 40, integration
            ),
        }
        fast_path.verify_eligibility_bound_ready_integration_attestation(
            attestation, **verification
        )

        missing = copy.deepcopy(attestation)
        missing.pop("eligibility_evidence_digest")
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "eligibility-bound"
        ):
            fast_path.verify_eligibility_bound_ready_integration_attestation(
                missing, **verification
            )

        mismatched = copy.deepcopy(attestation)
        mismatched["eligibility_evidence_digest"] = "f" * 64
        mismatched_fields = {
            key: value
            for key, value in mismatched.items()
            if key != "attestation_digest"
        }
        mismatched["attestation_digest"] = fast_path.digest_json(
            mismatched_fields
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "eligibility differ"):
            fast_path.verify_eligibility_bound_ready_integration_attestation(
                mismatched, **verification
            )

        historical = fast_path.create_ready_integration_attestation(
            repository="SecPal/.github",
            head_sha="d" * 40,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=fast_path.create_validation_receipt(
                repository="SecPal/.github",
                head_sha=reviewed.head_sha,
                validated_tree_sha=tree,
                registry=registry,
                command_set=registry["validation"],
                successful_result=True,
                reviewed_state=reviewed,
                manual_gate_evidence=[],
                integration_evidence_digest=fast_path.digest_json(integration),
            ),
            integration_evidence=integration,
        )
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "eligibility-bound"
        ):
            fast_path.verify_eligibility_bound_ready_integration_attestation(
                historical, **verification
            )

    def test_remediation_evidence_cannot_select_ready_integration_topology(self) -> None:
        reviewed = fast_feedback()
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha="a" * 40,
            registry=fast_registry(),
            command_set=fast_registry()["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "malformed"):
            fast_path.normalize_ready_integration_evidence(
                receipt,
                repository="SecPal/.github",
                reviewed_state=reviewed,
                registry=fast_registry(),
                validated_tree_sha="a" * 40,
            )

    def test_ready_integration_attestation_rejects_stale_or_other_candidate_evidence(
        self,
    ) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        tree = "a" * 40
        head = "d" * 40
        integration = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=registry
        )
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha=tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            integration_evidence_digest=fast_path.digest_json(integration),
        )
        attestation = fast_path.create_ready_integration_attestation(
            repository="SecPal/.github",
            head_sha=head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
        )

        def verify(candidate: dict[str, Any], evidence_value: dict[str, Any]) -> None:
            fast_path.verify_ready_integration_attestation(
                candidate,
                repository="SecPal/.github",
                head_sha=head,
                registry=registry,
                command_set=registry["validation"],
                reviewed_state=reviewed,
                validation_receipt=receipt,
                integration_evidence=evidence_value,
                commit_parent_shas=integration["ordered_parent_shas"],
                commit_tree_sha=tree,
                commit_validation_receipt_digest=receipt["receipt_digest"],
                commit_integration_evidence_digest=fast_path.digest_json(evidence_value),
                authenticated_integration_commit=authenticated_integration_commit(
                    head, evidence_value
                ),
            )

        verify(attestation, integration)
        for field in ("head_sha", "validation_receipt_digest", "attestation_digest"):
            changed = copy.deepcopy(attestation)
            changed[field] = "0" * (40 if field == "head_sha" else 64)
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                verify(changed, integration)
        another = copy.deepcopy(integration)
        another["authorization_id"] = "ready-integration-authorization-002"
        with self.assertRaises(fast_path.SecurityBlocker):
            verify(attestation, another)

    def test_ready_integration_verification_yields_sealed_validation_evidence(
        self,
    ) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        tree = "a" * 40
        head = "d" * 40
        integration = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=registry
        )
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha=tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            integration_evidence_digest=fast_path.digest_json(integration),
        )
        attestation = fast_path.create_ready_integration_attestation(
            repository="SecPal/.github",
            head_sha=head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
        )

        verified = fast_path.verify_ready_integration_attestation(
            attestation,
            repository="SecPal/.github",
            head_sha=head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
            commit_parent_shas=integration["ordered_parent_shas"],
            commit_tree_sha=tree,
            commit_validation_receipt_digest=receipt["receipt_digest"],
            commit_integration_evidence_digest=fast_path.digest_json(integration),
            authenticated_integration_commit=authenticated_integration_commit(
                head, integration
            ),
        )

        self.assertTrue(fast_path.is_verified_validation_evidence(verified))
        self.assertEqual(verified.repository, "SecPal/.github")
        self.assertEqual(verified.delivery_issue_number, 9)
        self.assertEqual(verified.pull_request_number, reviewed.pull_request_number)
        self.assertEqual(verified.head_sha, head)
        self.assertEqual(verified.tree_sha, tree)
        self.assertEqual(
            verified.validation_receipt_digest, receipt["receipt_digest"]
        )
        self.assertEqual(
            verified.final_attestation_digest, attestation["attestation_digest"]
        )
        self.assertEqual(
            verified.source_validation_evidence_digest,
            fast_path.digest_json(
                {
                    "repository": integration["repository"],
                    "delivery_issue_number": integration[
                        "delivery_issue_number"
                    ],
                    "pull_request_number": integration["pull_request_number"],
                    "head_sha": head,
                    "tree_sha": tree,
                    "ordered_parent_shas": integration["ordered_parent_shas"],
                    "current_main": integration["target_base"],
                    "validation_receipt_digest": receipt["receipt_digest"],
                    "final_attestation_digest": attestation[
                        "attestation_digest"
                    ],
                    "integration_evidence": integration,
                    "reviewed_state_digest": reviewed.state_digest,
                    "reviewed_feedback_digest": reviewed.feedback_digest,
                    "expected_signer": integration["expected_signer"],
                    "evidence_schema_version": integration["schema_version"],
                    "evidence_kind": integration["kind"],
                    "attestation_schema_version": attestation[
                        "schema_version"
                    ],
                    "attestation_kind": attestation["kind"],
                }
            ),
        )
        for field, value in (
            ("repository", "Other/repository"),
            ("delivery_issue_number", 10),
            ("pull_request_number", verified.pull_request_number + 1),
            ("head_sha", "0" * 40),
            ("tree_sha", "1" * 40),
            ("validation_receipt_digest", "2" * 64),
            ("final_attestation_digest", "3" * 64),
            ("source_validation_evidence_digest", "4" * 64),
            ("_verification_seal", object()),
        ):
            changed = replace(verified, **{field: value})
            with self.subTest(field=field):
                self.assertFalse(fast_path.is_verified_validation_evidence(changed))
        with self.assertRaises(AttributeError):
            verified._verification_seal.binding_digest = "0" * 64

    def test_validation_evidence_authority_rejects_mutated_and_bypassed_seals(
        self,
    ) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        tree = "a" * 40
        head = "d" * 40
        integration = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=registry
        )
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha=tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            integration_evidence_digest=fast_path.digest_json(integration),
        )
        attestation = fast_path.create_ready_integration_attestation(
            repository="SecPal/.github",
            head_sha=head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
        )
        verified = fast_path.verify_ready_integration_attestation(
            attestation,
            repository="SecPal/.github",
            head_sha=head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
            commit_parent_shas=integration["ordered_parent_shas"],
            commit_tree_sha=tree,
            commit_validation_receipt_digest=receipt["receipt_digest"],
            commit_integration_evidence_digest=fast_path.digest_json(integration),
            authenticated_integration_commit=authenticated_integration_commit(
                head, integration
            ),
        )

        changed = replace(verified, repository="Other/repository")
        object.__setattr__(
            changed._verification_seal,
            "binding_digest",
            fast_path.digest_json(fast_path._validation_evidence_binding(changed)),
        )
        self.assertFalse(fast_path.is_verified_validation_evidence(changed))

        bypassed_seal = object.__new__(fast_path._VerifiedValidationEvidenceSeal)
        bypassed = replace(
            verified,
            head_sha="e" * 40,
            _verification_seal=bypassed_seal,
        )
        object.__setattr__(
            bypassed_seal,
            "binding_digest",
            fast_path.digest_json(fast_path._validation_evidence_binding(bypassed)),
        )
        self.assertFalse(fast_path.is_verified_validation_evidence(bypassed))

        forged = fast_path.VerifiedValidationEvidence(
            repository=verified.repository,
            delivery_issue_number=verified.delivery_issue_number,
            pull_request_number=verified.pull_request_number,
            head_sha=verified.head_sha,
            tree_sha=verified.tree_sha,
            validation_receipt_digest=verified.validation_receipt_digest,
            final_attestation_digest=verified.final_attestation_digest,
            source_validation_evidence_digest=(
                verified.source_validation_evidence_digest
            ),
            _verification_seal=verified._verification_seal,
        )
        self.assertFalse(fast_path.is_verified_validation_evidence(forged))
        self.assertFalse(
            hasattr(fast_path, "_register_verified_validation_evidence")
        )
        self.assertNotIn(
            "_register",
            fast_path.verify_validation_attestation.__kwdefaults__ or {},
        )
        self.assertNotIn(
            "_register",
            fast_path.verify_ready_integration_attestation.__kwdefaults__ or {},
        )
        candidate_self_sealed = fast_path._unregistered_validation_evidence(
            repository=verified.repository,
            delivery_issue_number=verified.delivery_issue_number,
            pull_request_number=verified.pull_request_number,
            head_sha=verified.head_sha,
            tree_sha=verified.tree_sha,
            validation_receipt_digest=verified.validation_receipt_digest,
            final_attestation_digest=verified.final_attestation_digest,
            source_validation_evidence_digest=(
                verified.source_validation_evidence_digest
            ),
        )
        self.assertFalse(
            fast_path.is_verified_validation_evidence(candidate_self_sealed)
        )

    def test_ready_integration_cannot_seal_without_commit_authentication(self) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        tree = "a" * 40
        head = "d" * 40
        integration = ready_integration_evidence(
            reviewed, validated_tree=tree, registry=registry
        )
        receipt = fast_path.create_validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            validated_tree_sha=tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
            integration_evidence_digest=fast_path.digest_json(integration),
        )
        attestation = fast_path.create_ready_integration_attestation(
            repository="SecPal/.github",
            head_sha=head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
        )
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "authenticated integration commit"
        ):
            fast_path.verify_ready_integration_attestation(
                attestation,
                repository="SecPal/.github",
                head_sha=head,
                registry=registry,
                command_set=registry["validation"],
                reviewed_state=reviewed,
                validation_receipt=receipt,
                integration_evidence=integration,
                commit_parent_shas=integration["ordered_parent_shas"],
                commit_tree_sha=tree,
                commit_validation_receipt_digest=receipt["receipt_digest"],
                commit_integration_evidence_digest=fast_path.digest_json(integration),
            )

        authenticated = authenticated_integration_commit(head, integration)
        self.assertFalse(
            hasattr(fast_path, "_register_authenticated_integration_commit")
        )
        bypassed = object.__new__(fast_path.AuthenticatedIntegrationCommit)
        for field in (
            "head_sha",
            "signer_kind",
            "signer_identity",
            "signature_fingerprint",
            "signature_classification",
            "authentication_digest",
        ):
            object.__setattr__(bypassed, field, getattr(authenticated, field))
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "authenticated integration commit"
        ):
            fast_path.verify_ready_integration_attestation(
                attestation,
                repository="SecPal/.github",
                head_sha=head,
                registry=registry,
                command_set=registry["validation"],
                reviewed_state=reviewed,
                validation_receipt=receipt,
                integration_evidence=integration,
                commit_parent_shas=integration["ordered_parent_shas"],
                commit_tree_sha=tree,
                commit_validation_receipt_digest=receipt["receipt_digest"],
                commit_integration_evidence_digest=fast_path.digest_json(integration),
                authenticated_integration_commit=bypassed,
            )

    def test_signed_validation_receipt_trailer_must_be_unique_and_well_formed(self) -> None:
        digest_value = "a" * 64
        for output, expected in (("\n", None), (f"{digest_value}\n", digest_value)):
            with (
                self.subTest(output=output),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    return_value=SimpleNamespace(stdout=output),
                ),
            ):
                self.assertEqual(
                    actions._commit_validation_receipt_digest(
                        REPO_ROOT, p21.HEAD
                    ),
                    expected,
                )
        for output in ("not-a-digest\n", f"{digest_value}\x00{digest_value}\n"):
            with (
                self.subTest(output=output),
                mock.patch.object(
                    actions,
                    "_run_attestation_git",
                    return_value=SimpleNamespace(stdout=output),
                ),
                self.assertRaisesRegex(fast_path.SecurityBlocker, "malformed"),
            ):
                actions._commit_validation_receipt_digest(REPO_ROOT, p21.HEAD)

    def test_bound_commit_accepts_local_signature_before_push(self) -> None:
        reviewed = fast_feedback()
        final_head = "d" * 40
        tree = "a" * 40
        entry = {
            "repository": "SecPal/.github",
            "default_branch": "main",
            "allowed_base_repositories": ["SecPal/.github"],
            "manual_gates": [],
            "focused_validation": [],
            "required_local_validation": [],
            "signature_policy": {
                "require_github_verified": True,
                "require_local_verified": True,
                "accepted_formats": ["ssh", "openpgp"],
            },
            "check_policy": {
                "require_ruleset_evidence": True,
                "require_branch_protection_evidence": True,
                "expected_skipped": "block",
            },
            "maximum_api_calls": 200,
            "maximum_items": 10000,
        }
        binding = actions._fast_registry_binding(entry)
        receipt = actions._validation_receipt(
            repository="SecPal/.github",
            head_sha=reviewed.head_sha,
            tree_sha=tree,
            binding=binding,
            reviewed=reviewed,
            manual_gate_evidence=[],
        )
        arguments = SimpleNamespace(
            expected_head=final_head,
            repo_root=str(REPO_ROOT),
            repo="SecPal/.github",
            reviewed_state="reviewed.json",
            registry="registry.json",
            bind_commit=True,
            receipt="receipt.json",
            output="attestation.json",
        )

        def git_result(
            _repository_root: Path,
            command: list[str],
            *,
            allow_failure: bool = False,
        ) -> Any:
            del allow_failure
            if command[:4] == ["rev-list", "--parents", "-n", "1"]:
                stdout = f"{final_head} {reviewed.head_sha}\n"
                stderr = ""
            elif command == ["rev-parse", "HEAD^{tree}"]:
                stdout = tree
                stderr = ""
            elif command[:2] == ["show", "-s"]:
                stdout = f"{receipt['receipt_digest']}\n"
                stderr = ""
            elif command[:2] == ["cat-file", "commit"]:
                stdout = (
                    "tree deadbeef\ngpgsig -----BEGIN PGP SIGNATURE-----\n"
                    " signature\n -----END PGP SIGNATURE-----\n\nmessage\n"
                )
                stderr = ""
            else:
                stdout = ""
                stderr = "gpg: Good signature from SecPal Test\n"
            return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

        with (
            mock.patch.object(
                actions,
                "_attestation_local_state",
                return_value=(final_head, ""),
            ),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value=entry),
            mock.patch.object(actions, "_read_json", return_value=receipt),
            mock.patch.object(actions, "_run_attestation_git", side_effect=git_result),
            mock.patch.object(actions, "_write_fast_report") as write_report,
        ):
            self.assertEqual(actions._command_attest_validation(arguments), 0)
        write_report.assert_called_once()

    def test_missing_upstream_is_a_recoverable_local_error(self) -> None:
        pull_request = {
            "number": 1,
            "headRepository": {"nameWithOwner": "SecPal/.github"},
            "headRefName": "feature",
            "headRefOid": p21.HEAD,
            "baseRefName": "main",
            "baseRefOid": p21.BASE,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "commits": {"nodes": [], "pageInfo": {"hasNextPage": False}},
        }
        github = SimpleNamespace(
            runner=SimpleNamespace(
                run=mock.Mock(
                    return_value={
                        "data": {
                            "viewer": {
                                "login": "aroviqen",
                                "id": "USER_1",
                                "databaseId": 7,
                            },
                            "repository": {
                                "nameWithOwner": "SecPal/.github",
                                "pullRequest": pull_request,
                            },
                        }
                    }
                )
            )
        )
        gateway = actions.FastPathGateway(
            REPO_ROOT,
            registry_entry("SecPal/.github"),
            github=github,
        )

        def git_result(command: list[str], *, allow_failure: bool = False) -> Any:
            del allow_failure
            values = {
                ("rev-parse", "HEAD"): (0, p21.HEAD),
                ("rev-parse", "@{upstream}"): (128, ""),
                ("branch", "--show-current"): (0, "feature"),
                ("status", "--porcelain=v2", "--untracked-files=all"): (0, ""),
                ("remote", "get-url", "origin"): (0, "https://github.com/SecPal/.github.git"),
            }
            returncode, stdout = values[tuple(command)]
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="no upstream")

        gateway._git = mock.Mock(side_effect=git_result)
        with self.assertRaisesRegex(
            fast_path.RecoverableLocalError,
            "configured upstream",
        ):
            gateway.read_preflight(fast_request(fast_feedback()))

    def test_stable_feedback_uses_the_selected_registry_entry(self) -> None:
        selected = registry_entry("SecPal/.github")
        selected["maximum_comments"] = 1
        payload = fast_feedback(1).to_dict()
        for key in (
            "schema_version",
            "repository",
            "pull_request_number",
            "state_digest",
            "feedback_digest",
        ):
            payload.pop(key)
        read_feedback = mock.Mock(return_value=payload)
        github = SimpleNamespace(_read_current_feedback_once=read_feedback)
        with mock.patch.object(
            actions,
            "load_registry",
            side_effect=AssertionError("default registry must not be reloaded"),
        ):
            gateway = actions.FastPathGateway(
                REPO_ROOT,
                selected,
                github=github,
            )
            state = gateway.capture_stable_feedback("SecPal/.github", 1)
        self.assertEqual(state.feedback_digest, fast_feedback(1).feedback_digest)
        self.assertEqual(read_feedback.call_args.args[1], selected)

    def test_required_checks_use_the_allowlisted_graphql_read(self) -> None:
        check_payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "id": "PR_1",
                        "headRefOid": p21.HEAD,
                        "state": "OPEN",
                        "baseRefName": "main",
                        "baseRefOid": p21.BASE,
                        "baseRepository": {"id": "REPO_1", "nameWithOwner": "SecPal/.github"},
                        "potentialMergeCommit": None,
                    },
                    "object": {
                        "oid": p21.HEAD,
                        "statusCheckRollup": {
                            "contexts": {
                                "nodes": [
                                    {
                                        "__typename": "CheckRun",
                                        "id": "CHECK_1",
                                        "name": "tests",
                                        "status": "COMPLETED",
                                        "conclusion": "SUCCESS",
                                        "startedAt": "2026-07-21T00:00:00Z",
                                        "detailsUrl": "https://example.invalid/tests",
                                        "checkSuite": {
                                            "app": {
                                                "id": "APP_1",
                                                "databaseId": 1,
                                                "name": "CI",
                                                "slug": "ci",
                                            }
                                        },
                                    },
                                    {
                                        "__typename": "StatusContext",
                                        "id": "STATUS_1",
                                        "context": "legacy",
                                        "state": "SUCCESS",
                                        "createdAt": "2026-07-21T00:00:00Z",
                                        "targetUrl": "https://example.invalid/legacy",
                                        "creator": {
                                            "__typename": "User",
                                            "id": "USER_1",
                                            "databaseId": 7,
                                            "login": "reviewer",
                                            "url": "https://example.invalid/reviewer",
                                        },
                                    },
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        },
                    },
                }
            }
        }

        def run(arguments: list[str]) -> Any:
            if arguments[4].startswith("repos/") and "/rules/branches/" in arguments[4]:
                return [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": "tests", "integration_id": 1},
                                {"context": "legacy", "integration_id": None},
                            ],
                            "strict_required_status_checks_policy": False,
                        },
                    }
                ]
            if arguments[4].startswith("repos/"):
                return {"strict": False, "contexts": [], "checks": []}
            return check_payload

        runner = SimpleNamespace(run=mock.Mock(side_effect=run))
        gateway = actions.FastPathGateway(
            REPO_ROOT,
            registry_entry("SecPal/.github"),
            github=SimpleNamespace(runner=runner),
        )
        result = gateway.read_required_checks(
            fast_request(fast_feedback()), fast_registry()
        )
        self.assertEqual(
            result["required_specs"],
            [
                {"context": "legacy", "integration_id": None},
                {"context": "tests", "integration_id": 1},
            ],
        )
        self.assertEqual([item["name"] for item in result["checks"]], ["tests", "legacy"])
        self.assertEqual(runner.run.call_count, 3)
        for call in runner.run.call_args_list:
            actions._validate_action_command(call.args[0])

    def test_fast_preflight_queries_the_signature_signer_as_a_user(self) -> None:
        signer_selection = actions.FAST_PATH_PREFLIGHT_QUERY.split("signer {", 1)[1]
        signer_selection = signer_selection.split("}", 1)[0]
        self.assertIn("id", signer_selection)
        self.assertIn("databaseId", signer_selection)
        self.assertIn("login", signer_selection)
        self.assertNotIn("... on", signer_selection)

    def test_stable_feedback_ignores_same_head_required_check_transitions(self) -> None:
        successful = fast_feedback()
        payload = successful.to_dict()
        payload["required_checks"] = [{"name": "tests", "state": "PENDING"}]
        pending = fast_path.StableFeedbackState.from_payload(payload)
        self.assertEqual(successful.state_digest, pending.state_digest)
        self.assertEqual(successful.feedback_digest, pending.feedback_digest)

    def test_stable_feedback_preserves_deleted_source_actor_identity(self) -> None:
        payload = fast_feedback(1).to_dict()
        payload["threads"][0]["comments"][0]["actor"] = {
            "login": None,
            "node_id": None,
            "database_id": None,
        }
        state = fast_path.StableFeedbackState.from_payload(payload)
        self.assertEqual(
            state.feedback["threads"][0]["comments"][0]["actor"],
            {"login": None, "node_id": None, "database_id": None},
        )

    def test_pending_or_failed_required_checks_block_before_first_write(self) -> None:
        for status in ("PENDING", "FAILURE"):
            with self.subTest(status=status):
                reviewed = fast_feedback()
                gateway = FakeFastGateway(reviewed)
                gateway.checks[0]["status"] = status
                with self.assertRaisesRegex(fast_path.SecurityBlocker, "required check"):
                    self.execute(reviewed, gateway)
                self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_missing_configured_required_check_blocks_before_first_write(self) -> None:
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "missing"):
            fast_path._verify_required_checks(
                [
                    {
                        "stable_id": "check_run:present",
                        "name": "present",
                        "application": {"database_id": 1},
                        "status": "COMPLETED",
                        "conclusion": "SUCCESS",
                    }
                ],
                [
                    {"context": "present", "integration_id": 1},
                    {"context": "never-reported", "integration_id": 2},
                ],
                {"expected_skipped": "block"},
            )

    def test_no_configured_required_checks_allows_an_empty_rollup(self) -> None:
        fast_path._verify_required_checks(
            [],
            [],
            {"expected_skipped": "block"},
        )

    def test_blocked_merge_gate_does_not_deadlock_thread_resolution(self) -> None:
        reviewed = fast_feedback(1)
        gateway = FakeFastGateway(reviewed)
        original_preflight = gateway.read_preflight

        def blocked(request_value: Any) -> Any:
            readiness = original_preflight(request_value)
            readiness.merge_state_status = "BLOCKED"
            return readiness

        gateway.read_preflight = blocked
        gateway.target_merge_state_status = "BLOCKED"

        result = self.execute(reviewed, gateway, 1)

        self.assertEqual(result["status"], "BATCH_APPLIED")
        self.assertEqual(
            [call for call in gateway.calls if call[0] == "WRITE"],
            [("WRITE", "THREAD_1")],
        )

    def test_base_change_blocks_before_first_write(self) -> None:
        reviewed = fast_feedback()
        request = fast_request(reviewed)
        request.expected_base_ref = "main"
        request.expected_base_sha = p21.BASE
        gateway = FakeFastGateway(reviewed)
        original = gateway.read_preflight

        def changed_base(request_value: Any) -> Any:
            readiness = original(request_value)
            readiness.base_ref = "release"
            readiness.base_sha = "f" * 40
            return readiness

        gateway.read_preflight = changed_base
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "base"):
            fast_path.execute_resolution_batch(
                request,
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_behind_merge_state_with_strict_checks_blocks_before_first_write(self) -> None:
        reviewed = fast_feedback()
        gateway = FakeFastGateway(reviewed)
        original_preflight = gateway.read_preflight
        original_checks = gateway.read_required_checks

        def behind(request_value: Any) -> Any:
            readiness = original_preflight(request_value)
            readiness.merge_state_status = "BEHIND"
            return readiness

        def strict_checks(
            request_value: Any, registry_value: dict[str, Any]
        ) -> dict[str, Any]:
            result = original_checks(request_value, registry_value)
            result["strict_base_required"] = True
            return result

        gateway.read_preflight = behind
        gateway.read_required_checks = strict_checks
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "behind"):
            self.execute(reviewed, gateway)
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_unknown_mergeability_enum_blocks_preflight_and_target(self) -> None:
        reviewed = fast_feedback(1)
        gateway = FakeFastGateway(reviewed)
        original_preflight = gateway.read_preflight

        def unexpected_mergeability(request_value: Any) -> Any:
            readiness = original_preflight(request_value)
            readiness.mergeability = "FUTURE_STATE"
            return readiness

        gateway.read_preflight = unexpected_mergeability
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "mergeability"):
            self.execute(reviewed, gateway, 1)
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

        gateway = FakeFastGateway(reviewed)
        gateway.target_mergeability = "FUTURE_STATE"
        result = self.execute(reviewed, gateway, 1)
        self.assertEqual(result["status"], "BLOCKED_TARGET_CHANGED")
        self.assertRegex(result["failed"][0]["error"], "mergeability")
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_feedback_changes_block_before_first_write(self) -> None:
        mutations = {
            "new comment": lambda state: state.feedback["conversation_comments"].append(
                {
                    "node_id": "COMMENT_NEW",
                    "body_digest": digest("new"),
                    "actor": {"login": "reviewer", "node_id": "ACTOR_1", "database_id": 7},
                    "updated_at": "2026-07-21T00:00:00Z",
                    "reactions": [],
                }
            ),
            "changed digest": lambda state: state.feedback["threads"][0]["comments"][0].update(
                body_digest=digest("changed")
            ),
            "new reaction": lambda state: state.feedback["threads"][0]["comments"][0]["reactions"].append(
                {
                    "mutation_id": "REACTION_1",
                    "content": "THUMBS_UP",
                    "actor": {"login": "other", "node_id": "ACTOR_2", "database_id": 8},
                }
            ),
            "changed thread": lambda state: state.feedback["threads"][0].update(is_outdated=True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                reviewed = fast_feedback()
                current = copy.deepcopy(reviewed)
                mutate(current)
                current.refresh_digests()
                gateway = FakeFastGateway(current, reviewed)
                with self.assertRaises(fast_path.SecurityBlocker):
                    self.execute(reviewed, gateway)
                self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_head_change_blocks_before_first_write(self) -> None:
        reviewed = fast_feedback()
        gateway = FakeFastGateway(reviewed)
        original = gateway.read_preflight

        def changed_head(request: Any) -> Any:
            value = original(request)
            value.head_sha = "f" * 40
            return value

        gateway.read_preflight = changed_head
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "head"):
            self.execute(reviewed, gateway)
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_base_change_during_feedback_freshness_blocks_before_first_write(self) -> None:
        reviewed = fast_feedback()
        current = copy.deepcopy(reviewed)
        current.base_ref = "release"
        current.base_sha = "f" * 40
        current.refresh_digests()
        gateway = FakeFastGateway(current, reviewed)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "base"):
            fast_path.execute_resolution_batch(
                fast_request(reviewed),
                fast_attestation(reviewed),
                reviewed,
                fast_registry(),
                gateway,
            )
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_recoverable_local_error_is_corrected_in_same_invocation(self) -> None:
        attempts = 0
        corrections = 0

        def command() -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise fast_path.RecoverableLocalError("self-supplied CLI argument was invalid")
            return "ok"

        def correct() -> None:
            nonlocal corrections
            corrections += 1

        self.assertEqual(fast_path.run_recoverable_local_step(command, correct), "ok")
        self.assertEqual((attempts, corrections), (2, 1))

    def test_one_transient_feedback_read_is_retried_once(self) -> None:
        reviewed = fast_feedback()
        gateway = FakeFastGateway(reviewed)
        gateway.fail_feedback_reads = 1
        self.assertEqual(self.execute(reviewed, gateway)["status"], "BATCH_APPLIED")
        self.assertEqual(gateway.calls.count(("READ", "stable-feedback")), 2)

    def test_exhausted_transient_read_has_performed_exactly_one_retry(self) -> None:
        attempts = 0

        def fail() -> None:
            nonlocal attempts
            attempts += 1
            raise fast_path.TransientReadFailure("still unavailable")

        with self.assertRaises(fast_path.TransientReadFailure):
            fast_path._read_with_one_retry(fail)
        self.assertEqual(attempts, 2)

    def test_mutation_failure_and_unknown_result_are_never_retried(self) -> None:
        for attribute, expected_status in (
            ("fail_at_write", "BLOCKED_MUTATION_FAILED"),
            ("unknown_at_write", "BLOCKED_UNKNOWN_WRITE_RESULT"),
        ):
            with self.subTest(attribute=attribute):
                reviewed = fast_feedback(3)
                gateway = FakeFastGateway(reviewed)
                setattr(gateway, attribute, 2)
                result = self.execute(reviewed, gateway, 3)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual([item["thread_id"] for item in result["applied"]], ["THREAD_1"])
                self.assertEqual(result["failed"][0]["thread_id"], "THREAD_2")
                self.assertEqual([item["thread_id"] for item in result["blocked"]], ["THREAD_3"])
                self.assertEqual(gateway.write_attempts["THREAD_2"], 1)
                self.assertNotIn("THREAD_3", gateway.write_attempts)

    def test_target_read_failure_retains_prior_writes_and_stops_batch(self) -> None:
        reviewed = fast_feedback(3)
        gateway = FakeFastGateway(reviewed)
        gateway.fail_target = "THREAD_2"
        result = self.execute(reviewed, gateway, 3)
        self.assertEqual(result["status"], "BLOCKED_TARGET_READ_FAILED")
        self.assertEqual([item["thread_id"] for item in result["applied"]], ["THREAD_1"])
        self.assertEqual(result["failed"][0]["thread_id"], "THREAD_2")
        self.assertEqual([item["thread_id"] for item in result["blocked"]], ["THREAD_3"])
        self.assertEqual(gateway.calls.count(("READ", "target:THREAD_2")), 2)
        self.assertFalse(any(identity == "THREAD_3" for kind, identity in gateway.calls if kind == "WRITE"))

    def test_last_moment_thread_feedback_change_blocks_the_write(self) -> None:
        reviewed = fast_feedback(1)
        gateway = FakeFastGateway(reviewed)
        original = gateway.read_thread_target

        def changed_target(request_value: Any, operation_value: Any) -> dict[str, Any]:
            target = original(request_value, operation_value)
            thread = copy.deepcopy(reviewed.feedback["threads"][0])
            thread["comments"].append(
                {
                    "node_id": "COMMENT_LATE",
                    "body_digest": digest("late feedback"),
                    "actor": {
                        "login": "reviewer",
                        "node_id": "ACTOR_1",
                        "database_id": 7,
                    },
                    "reply_to_id": "COMMENT_1",
                    "reactions": [],
                }
            )
            target["thread"] = thread
            return target

        gateway.read_thread_target = changed_target
        result = self.execute(reviewed, gateway, 1)
        self.assertEqual(result["status"], "BLOCKED_TARGET_CHANGED")
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_last_moment_pr_or_base_change_blocks_the_write(self) -> None:
        for attribute, value in (
            ("target_pr_state", "CLOSED"),
            ("target_base_ref", "release"),
            ("target_base_sha", "f" * 40),
        ):
            with self.subTest(attribute=attribute):
                reviewed = fast_feedback(1)
                gateway = FakeFastGateway(reviewed)
                setattr(gateway, attribute, value)
                result = self.execute(reviewed, gateway, 1)
                self.assertEqual(result["status"], "BLOCKED_TARGET_CHANGED")
                self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_last_moment_merge_state_change_blocks_the_write(self) -> None:
        reviewed = fast_feedback(1)
        gateway = FakeFastGateway(reviewed)
        gateway.target_merge_state_status = "BLOCKED"
        result = self.execute(reviewed, gateway, 1)
        self.assertEqual(result["status"], "BLOCKED_TARGET_CHANGED")
        self.assertRegex(result["failed"][0]["error"], "merge state")
        self.assertFalse(any(kind == "WRITE" for kind, _ in gateway.calls))

    def test_signature_sources_are_selected_once_per_commit(self) -> None:
        user_valid = {
            "oid": "1" * 40,
            "source": "USER",
            "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
            "github_verification": {"verified": False, "reason": "unknown_key"},
        }
        github_valid = {
            "oid": "2" * 40,
            "source": "GITHUB",
            "local_signature": {"verified": False, "state": "unknown_key", "format": "openpgp"},
            "github_verification": {"verified": True, "reason": "valid"},
        }
        result = fast_path.verify_commit_signatures([user_valid, github_valid])
        self.assertEqual([item["classification"] for item in result], ["LOCAL_SSH_VERIFIED", "GITHUB_VERIFIED"])
        self.assertEqual(result[1]["local_classification"], "UNKNOWN_LOCAL_KEY")
        openpgp_valid = copy.deepcopy(user_valid)
        openpgp_valid["local_signature"]["format"] = "openpgp"
        self.assertEqual(
            fast_path.verify_commit_signatures([openpgp_valid])[0]["classification"],
            "LOCAL_OPENPGP_VERIFIED",
        )
        for local_signature in (
            {"verified": False, "state": "unsigned", "format": None},
            {"verified": False, "state": "invalid", "format": "ssh"},
        ):
            candidate = copy.deepcopy(user_valid)
            candidate["local_signature"] = local_signature
            with self.assertRaises(fast_path.SecurityBlocker):
                fast_path.verify_commit_signatures([candidate])
        github_invalid = copy.deepcopy(github_valid)
        github_invalid["github_verification"] = {"verified": False, "reason": "bad_email"}
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.verify_commit_signatures([github_invalid])

    def test_user_commit_honors_required_github_verification(self) -> None:
        commit = {
            "oid": "1" * 40,
            "source": "USER",
            "local_signature": {
                "verified": True,
                "state": "valid",
                "format": "ssh",
            },
            "github_verification": {
                "verified": False,
                "reason": "unknown_key",
            },
        }
        policy = {
            "require_github_verified": True,
            "require_local_verified": True,
            "accepted_formats": ["ssh", "openpgp"],
        }

        with self.assertRaisesRegex(
            fast_path.SecurityBlocker,
            "GitHub verification rejected user-authored commit",
        ):
            fast_path.verify_commit_signatures([commit], policy)

        commit["github_verification"] = {"verified": True, "reason": "valid"}
        self.assertEqual(
            fast_path.verify_commit_signatures([commit], policy)[0][
                "classification"
            ],
            "LOCAL_SSH_VERIFIED",
        )

    def test_successful_batch_reports_every_thread_category(self) -> None:
        reviewed = fast_feedback(4)
        result = self.execute(reviewed, FakeFastGateway(reviewed), 4)
        self.assertEqual(
            [item["thread_id"] for item in result["applied"]],
            ["THREAD_1", "THREAD_2", "THREAD_3", "THREAD_4"],
        )
        self.assertEqual(result["blocked"], [])
        self.assertEqual(result["failed"], [])

    def test_applied_report_cannot_be_reused_as_authorization(self) -> None:
        reviewed = fast_feedback()
        request = fast_request(reviewed)
        first = self.execute(reviewed, FakeFastGateway(reviewed))
        repeated_payload = request.to_dict()
        repeated_payload["prior_results"] = first["applied"]
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "prior"):
            fast_path.BatchRequest.from_dict(repeated_payload)

    def test_batch_surface_cannot_gain_user_controlled_capabilities(self) -> None:
        self.assertEqual(fast_path.SUPPORTED_BATCH_CAPABILITIES, frozenset({"THREAD_RESOLUTION"}))
        reviewed = fast_feedback(1)
        for prohibited in actions.PROHIBITED_OPERATION_KINDS:
            payload = fast_request(reviewed, 1).to_dict()
            payload["operations"][0]["kind"] = prohibited
            with self.subTest(prohibited=prohibited), self.assertRaises(fast_path.SecurityBlocker):
                fast_path.BatchRequest.from_dict(payload)

    def test_attestation_is_deterministic_and_bound_to_all_inputs(self) -> None:
        reviewed = fast_feedback()
        attestation = fast_attestation(reviewed)
        self.assertEqual(attestation, fast_attestation(reviewed))
        self.assertFalse(
            {
                "repository",
                "head_sha",
                "registry_digest",
                "command_set_digest",
                "successful_result",
            }
            - set(attestation)
        )
        fast_path.verify_validation_attestation(
            attestation,
            repository="SecPal/.github",
            head_sha=p21.HEAD,
            registry=fast_registry(),
            command_set=fast_registry()["validation"],
            reviewed_state=reviewed,
            commit_parent_sha=reviewed.head_sha,
            commit_tree_sha="a" * 40,
            commit_validation_receipt_digest=attestation[
                "validation_receipt_digest"
            ],
        )
        for key, value in (
            ("head_sha", "f" * 40),
            ("registry_digest", "0" * 64),
            ("command_set_digest", "0" * 64),
            ("successful_result", False),
        ):
            changed = copy.deepcopy(attestation)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(fast_path.SecurityBlocker):
                fast_path.verify_validation_attestation(
                    changed,
                    repository="SecPal/.github",
                    head_sha=p21.HEAD,
                    registry=fast_registry(),
                    command_set=fast_registry()["validation"],
                    reviewed_state=reviewed,
                    commit_parent_sha=reviewed.head_sha,
                    commit_tree_sha="a" * 40,
                    commit_validation_receipt_digest=attestation[
                        "validation_receipt_digest"
                    ],
                )

    def test_validation_evidence_rejects_repository_substitution(self) -> None:
        reviewed = fast_feedback()
        registry = fast_registry()
        receipt = fast_path.create_validation_receipt(
            repository=reviewed.repository,
            head_sha=reviewed.head_sha,
            validated_tree_sha="a" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
        )
        attestation = fast_path.create_validation_attestation(
            repository=reviewed.repository,
            head_sha=p21.HEAD,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=reviewed,
            validation_receipt=receipt,
        )
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker,
            "reviewed repository identity changed",
        ):
            fast_path.verify_validation_attestation(
                attestation,
                repository="Other/governance",
                head_sha=p21.HEAD,
                registry=registry,
                command_set=registry["validation"],
                reviewed_state=reviewed,
                commit_parent_sha=reviewed.head_sha,
                commit_tree_sha="a" * 40,
                commit_validation_receipt_digest=receipt["receipt_digest"],
            )

    def test_validation_evidence_rejects_noncanonical_reviewed_state(self) -> None:
        for reviewed_state in (
            None,
            {},
            object(),
            SimpleNamespace(payload={"pull_request_number": 1}),
        ):
            with (
                self.subTest(reviewed_state=type(reviewed_state).__name__),
                self.assertRaisesRegex(
                    fast_path.SecurityBlocker,
                    "reviewed state is not canonical",
                ),
            ):
                fast_path.verify_validation_attestation(
                    {},
                    repository="SecPal/.github",
                    head_sha=p21.HEAD,
                    registry=fast_registry(),
                    command_set=fast_registry()["validation"],
                    reviewed_state=reviewed_state,
                    commit_parent_sha="a" * 40,
                    commit_tree_sha="b" * 40,
                    commit_validation_receipt_digest="c" * 64,
                )

    def test_atomic_json_output_supports_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fast path ") as directory:
            output = Path(directory) / "review state.json"
            fast_path.atomic_write_json(output, {"status": "ok"})
            self.assertEqual(json.loads(output.read_text()), {"status": "ok"})

    def test_batch_report_falls_back_with_applied_targets_after_output_failure(self) -> None:
        report = {
            "status": "BATCH_APPLIED",
            "batch_id": "batch-001",
            "applied": [{"operation_id": "resolve-1", "thread_id": "THREAD_1"}],
            "failed": [],
            "blocked": [],
        }
        error_output = SimpleNamespace(buffer=io.BytesIO())
        with (
            mock.patch.object(actions, "_write_fast_report", side_effect=OSError("disk full")),
            mock.patch.object(actions.sys, "stderr", error_output),
        ):
            self.assertFalse(actions._write_batch_report("missing/report.json", report))
        fallback = json.loads(error_output.buffer.getvalue())
        self.assertEqual(fallback["status"], "BLOCKED_REPORT_PERSISTENCE_FAILED")
        self.assertEqual(fallback["applied"], report["applied"])
        self.assertEqual(fallback["applied"], report["applied"])


class PolicyScriptTests(TestCase):
    def test_deployment_manual_gate_count_assertion_has_diagnostic(self) -> None:
        policy = (REPO_ROOT / "tests/secpal-pr-review-skill-policy.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'assert len(deployment["manual_gates"]) == 1, (\n'
            '    "SecPal/deployment must define exactly one manual gate"\n'
            ")",
            policy,
        )

    def test_reuse_precommit_hook_provisions_the_pinned_tool(self) -> None:
        pre_commit = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        reuse_hook = pre_commit.split("  # Code formatting", 1)[0]
        self.assertIn("language: python", reuse_hook)
        self.assertIn("additional_dependencies: [reuse==5.0.2]", reuse_hook)
        self.assertNotIn("language: system", reuse_hook)

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
