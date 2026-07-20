#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
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
            "is_resolved": False if kind == "THREAD_RESOLUTION" else None,
            "is_outdated": False,
            "material_misunderstanding": kind == "EVIDENCE_REPLY",
        },
        "expected_actor_identity": {
            "login": "aroviqen",
            "node_id": "USER_1",
            "database_id": 7,
        },
        "classification": classification,
        "evidence_digest": digest(f"evidence-{operation_id}"),
        "reaction": reaction,
        "reply_body": reply_body,
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
    return {
        "schema_version": "1.0",
        "repository": "SecPal/.github",
        "pull_request_number": 1,
        "snapshot_digest": snapshot["snapshot_digest"],
        "initial_snapshot_digest": snapshot["snapshot_digest"],
        "expected_head_sha": p21.HEAD,
        "created_for_state": current_state,
        "cycle_number": 1,
        "session": base_session(),
        "findings": [finding()],
        "operations": list(operations),
    }


def registry_entry(repository: str) -> dict[str, Any]:
    return {
        "repository": repository,
        "default_branch": "main",
        "allowed_base_repositories": [repository],
        "reviewer_identities": p21.config()["reviewer_identities"],
        "focused_validation": [
            {"argv": ["npm", "test"], "working_directory": ".", "purpose": "Run tests"}
        ],
        "required_local_validation": [
            {"argv": ["npm", "run", "lint"], "working_directory": ".", "purpose": "Run lint"}
        ],
        "signature_policy": p21.config()["signature_policy"],
        "check_policy": p21.config()["check_policy"],
        "manual_gates": ["Confirm any environment-dependent validation with the user."],
        "unsupported_operations": list(actions.PROHIBITED_OPERATION_KINDS),
        "maximum_api_calls": 200,
        "maximum_items": 10000,
        "maximum_threads": 500,
        "maximum_comments": 10000,
        "maximum_reactions": 10000,
    }


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = False
        self.state = {
            "head_sha": p21.HEAD,
            "actor": {"login": "aroviqen", "node_id": "USER_1", "database_id": 7},
            "target": {
                "node_id": "RC_1",
                "database_id": 21,
                "parent_thread_id": "THREAD_1",
                "target_type": "PULL_REQUEST_REVIEW_COMMENT",
                "body_digest": digest("Finding"),
                "is_resolved": None,
                "is_outdated": False,
                "reactions": [],
                "replies": [],
            },
        }

    def read_current_state(self, _plan: dict[str, Any], _operation: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("READ", "current-state"))
        return copy.deepcopy(self.state)

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


class ContractTests(unittest.TestCase):
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

    def test_plan_is_deterministic_and_bound_to_p21_snapshot(self) -> None:
        value = plan(operation())
        normalized = actions.validate_plan(value, evidence_snapshot(), p21.config())
        self.assertEqual(actions.canonical_json_bytes(normalized), actions.canonical_json_bytes(normalized))
        changed = copy.deepcopy(value)
        changed["snapshot_digest"] = "0" * 64
        with self.assertRaisesRegex(actions.PlanError, "snapshot digest"):
            actions.validate_plan(changed, evidence_snapshot(), p21.config())
        changed = copy.deepcopy(value)
        changed["expected_head_sha"] = "f" * 40
        with self.assertRaisesRegex(actions.PlanError, "head"):
            actions.validate_plan(changed, evidence_snapshot(), p21.config())
        changed = copy.deepcopy(value)
        changed["findings"][0]["source_node_ids"] = ["MISSING_SOURCE"]
        with self.assertRaisesRegex(actions.PlanError, "source node"):
            actions.validate_plan(changed, evidence_snapshot(), p21.config())

    def test_compound_source_items_require_stable_distinct_logical_findings(self) -> None:
        value = plan(operation())
        value["findings"].append(finding("finding-002", "INFORMATIONAL"))
        normalized = actions.validate_plan(value, evidence_snapshot(), p21.config())
        self.assertEqual(len(normalized["findings"]), 2)
        value["findings"][1]["logical_finding_id"] = "finding-001"
        with self.assertRaisesRegex(actions.PlanError, "logical finding"):
            actions.validate_plan(value, evidence_snapshot(), p21.config())

    def test_duplicate_findings_require_a_canonical_root(self) -> None:
        value = plan(operation())
        value["findings"] = [finding(classification="DUPLICATE", disposition="DUPLICATE_OF_CANONICAL")]
        with self.assertRaisesRegex(actions.PlanError, "canonical"):
            actions.validate_plan(value, evidence_snapshot(), p21.config())

    def test_disallowed_operation_kinds_and_capabilities_are_rejected(self) -> None:
        self.assertEqual(set(actions.ALLOWED_OPERATION_KINDS), {"REACTION", "EVIDENCE_REPLY", "THREAD_RESOLUTION"})
        prohibited = {
            "REVIEW_REQUEST", "READY_TRANSITION", "LABEL", "ISSUE", "REVIEW_SUBMISSION",
            "MERGE", "AUTO_MERGE", "COMMENT_DELETE", "REVIEW_DISMISSAL", "BRANCH_WRITE",
        }
        self.assertEqual(set(actions.PROHIBITED_OPERATION_KINDS), prohibited)
        value = plan(operation())
        value["operations"][0]["kind"] = "MERGE"
        with self.assertRaises(actions.PlanError):
            actions.validate_plan(value, evidence_snapshot(), p21.config())

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
                actions.validate_plan(value, evidence_snapshot(), p21.config())

    def test_fixed_or_status_replies_are_refused(self) -> None:
        for body in ("fixed", "Addressed.", f"Fixed in {p21.HEAD}", "status: complete"):
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
                actions.validate_plan(value, evidence_snapshot(), p21.config())

    def test_at_most_one_reaction_per_initial_finding_and_ten_replies_total(self) -> None:
        value = plan(operation(), operation(operation_id="reaction-002"))
        with self.assertRaisesRegex(actions.PlanError, "reaction"):
            actions.validate_plan(value, evidence_snapshot(), p21.config())
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
            findings.append(finding(finding_id, "INVALID_FALSE_OR_MISLEADING", disposition="DISPROVEN_WITH_EVIDENCE"))
        value = plan(*replies)
        value["findings"] = findings
        with self.assertRaisesRegex(actions.PlanError, "evidence repl"):
            actions.validate_plan(value, evidence_snapshot(), p21.config())


class MutationTests(unittest.TestCase):
    def apply(self, value: dict[str, Any], operation_id: str, github: FakeGitHub, *, apply: bool = True) -> dict[str, Any]:
        return actions.execute_operation(
            value,
            operation_id,
            evidence_snapshot(),
            p21.config(),
            github,
            apply=apply,
            resolution_evidence=None,
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

    def test_existing_actor_reaction_is_idempotent_and_other_actor_is_preserved(self) -> None:
        github = FakeGitHub()
        github.state["target"]["reactions"] = [
            {"content": "THUMBS_UP", "actor": {"login": "someone-else", "node_id": "OTHER", "database_id": 8}},
            {"content": "THUMBS_UP", "actor": copy.deepcopy(github.state["actor"])},
        ]
        result = self.apply(plan(operation()), "reaction-001", github)
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
            {"body": op["reply_body"], "actor": copy.deepcopy(github.state["actor"])}
        ]
        self.assertEqual(self.apply(value, "reply-001", github)["status"], "ALREADY_APPLIED")
        self.assertNotIn(("WRITE", "EVIDENCE_REPLY"), github.calls)

    def test_changed_head_actor_or_target_identity_is_refused(self) -> None:
        mutations = (
            ("head_sha", "f" * 40),
            ("actor.login", "intruder"),
            ("target.node_id", "CHANGED"),
        )
        for path, replacement in mutations:
            github = FakeGitHub()
            parent, key = (github.state, path) if "." not in path else (github.state[path.split(".")[0]], path.split(".")[1])
            parent[key] = replacement
            with self.subTest(path=path), self.assertRaises(actions.MutationBlocked):
                self.apply(plan(operation()), "reaction-001", github)
            self.assertFalse(any(call[0] == "WRITE" for call in github.calls))

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
        reaction = [
            "gh", "api", "--hostname", "github.com",
            "repos/SecPal/.github/pulls/comments/21/reactions",
            "--method", "POST", "--header", "Accept: application/vnd.github+json",
            "-f", "content=+1",
        ]
        actions._validate_action_command(reaction)
        for unsafe in (
            ["gh", "api", "--hostname", "github.com", "repos/SecPal/.github/issues"],
            [*reaction, "--input", "payload.json"],
            [*query, "-f", "extra=value"],
        ):
            with self.subTest(arguments=unsafe), self.assertRaises(actions.MutationBlocked):
                actions._validate_action_command(unsafe)

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
        complete = {"local_verified": True, "final_evidence_verified": True, "no_late_feedback": True, "all_threads_classified": True}
        result = actions.execute_operation(
            value, "resolve-001", evidence_snapshot(), p21.config(), github, apply=True,
            resolution_evidence=complete,
        )
        self.assertEqual(result["status"], "APPLIED")
        for key in complete:
            github = FakeGitHub()
            github.state["target"].update({"node_id": "THREAD_1", "database_id": None, "target_type": "PULL_REQUEST_REVIEW_THREAD", "body_digest": None, "is_resolved": False})
            incomplete = copy.deepcopy(complete)
            incomplete[key] = False
            with self.subTest(precondition=key), self.assertRaises(actions.MutationBlocked):
                actions.execute_operation(value, "resolve-001", evidence_snapshot(), p21.config(), github, apply=True, resolution_evidence=incomplete)

    def test_already_resolved_thread_is_refused_idempotently(self) -> None:
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        github = FakeGitHub()
        github.state["target"].update({"node_id": "THREAD_1", "database_id": None, "target_type": "PULL_REQUEST_REVIEW_THREAD", "body_digest": None, "is_resolved": True})
        evidence = {"local_verified": True, "final_evidence_verified": True, "no_late_feedback": True, "all_threads_classified": True}
        result = actions.execute_operation(value, "resolve-001", evidence_snapshot(), p21.config(), github, apply=True, resolution_evidence=evidence)
        self.assertEqual(result["status"], "ALREADY_APPLIED")
        self.assertNotIn(("WRITE", "THREAD_RESOLUTION"), github.calls)

    def test_resolution_readiness_uses_initial_snapshot_and_blocks_late_feedback(self) -> None:
        initial = evidence_snapshot()
        final = copy.deepcopy(initial)
        op = operation("THREAD_RESOLUTION", operation_id="resolve-001", reaction=None)
        value = plan(op, current_state="RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE")
        result = actions.build_resolution_evidence(
            value,
            initial,
            final,
            p21.config(),
            p21.FakeGitRunner(),
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
            p21.config(),
            p21.FakeGitRunner(),
        )
        self.assertFalse(result["no_late_feedback"])

        unclassified = copy.deepcopy(value)
        unclassified["findings"] = []
        result = actions.build_resolution_evidence(
            unclassified,
            initial,
            final,
            p21.config(),
            p21.FakeGitRunner(),
        )
        self.assertFalse(result["all_threads_classified"])


class RegistryTests(unittest.TestCase):
    repositories = [
        "SecPal/.github", "SecPal/api", "SecPal/frontend", "SecPal/contracts", "SecPal/android",
        "SecPal/changelog", "SecPal/GuardGuide", "SecPal/guardguide.de", "SecPal/secpal.app",
    ]

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
        no_gate = copy.deepcopy(registry)
        no_gate["repositories"][0]["required_local_validation"] = []
        no_gate["repositories"][0]["manual_gates"] = []
        with self.assertRaisesRegex(actions.RegistryError, "manual gate"):
            actions.validate_registry(no_gate)
        aliases = copy.deepcopy(registry)
        aliases["repositories"][0]["reviewer_identities"].append(copy.deepcopy(aliases["repositories"][0]["reviewer_identities"][0]))
        aliases["repositories"][0]["reviewer_identities"][-1]["canonical_identity"] = "other"
        with self.assertRaises(actions.RegistryError):
            actions.validate_registry(aliases)
        with self.assertRaises(actions.RegistryError):
            actions.select_repository(registry, "SecPal/unsupported")


class AuditModeTests(unittest.TestCase):
    def test_cases_80_to_90_have_no_default_writes_and_handle_untrusted_data(self) -> None:
        hostile = plan(operation())
        hostile["findings"][0]["test_evidence"] = ["`$(touch /tmp/never)` <script>\u0007"]
        normalized = actions.validate_plan(hostile, evidence_snapshot(), p21.config())
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
        return actions.execute_operation(value, "reaction-001", evidence_snapshot(), p21.config(), github, apply=False, resolution_evidence=None)

    def test_plan_loading_does_not_persist_outside_explicit_output(self) -> None:
        value = plan(operation())
        with tempfile.TemporaryDirectory() as directory:
            before = sorted(Path(directory).iterdir())
            actions.validate_plan(value, evidence_snapshot(), p21.config())
            self.assertEqual(sorted(Path(directory).iterdir()), before)


if __name__ == "__main__":
    unittest.main()
