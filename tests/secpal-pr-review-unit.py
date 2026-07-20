#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "secpal-pr-review.py"
FIXTURES = REPO_ROOT / "tests/fixtures/secpal-pr-review"
SPEC = importlib.util.spec_from_file_location("secpal_pr_review", HELPER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load helper at {HELPER}")
review = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)

HEAD = "a" * 40
BASE = "b" * 40
PARENT = "c" * 40
MERGE = "d" * 40


def uncontrolled_git_test_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in review.GIT_ENVIRONMENT_OVERRIDES:
        environment.pop(key, None)
    for key in tuple(environment):
        if review.GIT_CONFIG_PAIR.fullmatch(key) or review.GIT_TRACE_VARIABLE.match(key):
            environment.pop(key)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def fake_executable(directory: str, name: str) -> str:
    path = Path(directory) / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return str(path)


def actor(login: str | None = "reviewer", kind: str = "user") -> dict[str, Any]:
    if login is None:
        kind = "deleted_or_unavailable"
    return {
        "kind": kind,
        "login": login,
        "database_id": 7 if login else None,
        "node_id": f"ACTOR_{login}" if login else None,
        "url": f"https://github.com/{login}" if login else None,
    }


def signature(state: str = "valid", signature_format: str | None = "ssh") -> dict[str, Any]:
    return {
        "state": state,
        "verified": state == "valid",
        "format": signature_format,
        "reason": "valid" if state == "valid" else state,
        "signer": actor(),
    }


def reaction(reaction_id: str = "REACTION_1", content: str = "THUMBS_DOWN") -> dict[str, Any]:
    return {
        "id": reaction_id,
        "content": content,
        "created_at": "2026-07-19T00:01:00Z",
        "user": actor("reactor"),
    }


def config() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "repository": "SecPal/.github",
        "default_branch": "main",
        "allowed_base_repositories": ["SecPal/.github"],
        "reviewer_identities": [
            {
                "canonical_identity": "copilot",
                "kind": "bot",
                "graphql_aliases": ["copilot-pull-request-reviewer"],
                "rest_event_aliases": ["copilot-pull-request-reviewer[bot]"],
                "node_ids": [],
                "database_ids": [],
            },
            {
                "canonical_identity": "codex",
                "kind": "bot",
                "graphql_aliases": ["chatgpt-codex-connector"],
                "rest_event_aliases": ["chatgpt-codex-connector[bot]"],
                "node_ids": [],
                "database_ids": [],
            },
        ],
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
        "maximum_threads": 500,
        "maximum_comments": 100,
        "maximum_reactions": 25,
    }


def review_record(state: str = "COMMENTED", login: str = "reviewer", commit: str = HEAD) -> dict[str, Any]:
    return {
        "id": f"REVIEW_{state}_{login}_{commit[:4]}",
        "database_id": 11,
        "author": actor(login, "bot" if login != "reviewer" else "user"),
        "state": state,
        "body": "Informational review.",
        "url": "https://github.com/SecPal/.github/pull/1#pullrequestreview-11",
        "submitted_at": "2026-07-19T00:00:00Z",
        "commit_oid": commit,
        "reactions": [],
    }


def review_comment(
    comment_id: str = "RC_1", login: str = "reviewer", body: str = "Finding"
) -> dict[str, Any]:
    return {
        "id": comment_id,
        "database_id": 21,
        "author": actor(login, "bot" if login != "reviewer" else "user"),
        "body": body,
        "url": f"https://github.com/SecPal/.github/pull/1#discussion_r{comment_id[-1]}",
        "created_at": "2026-07-19T00:00:00Z",
        "updated_at": "2026-07-19T00:00:00Z",
        "reply_to_id": None,
        "review_id": "REVIEW_1",
        "reactions": [],
    }


def thread(
    thread_id: str = "THREAD_1",
    *,
    resolved: bool = False,
    outdated: bool = False,
    comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": thread_id,
        "is_resolved": resolved,
        "is_outdated": outdated,
        "path": "scripts/example.py",
        "line": 7,
        "original_line": 7,
        "side": "RIGHT",
        "start_line": None,
        "start_side": None,
        "comments": comments or [review_comment()],
    }


def check(
    name: str = "tests",
    status: str = "COMPLETED",
    conclusion: str | None = "SUCCESS",
) -> dict[str, Any]:
    return {
        "stable_id": f"check:1:{name}",
        "name": name,
        "application": {"id": "APP_1", "database_id": 1, "name": "Actions", "slug": "github-actions"},
        "status": status,
        "conclusion": conclusion,
        "requiredness": "required",
        "evidence_state": "required_successful",
        "details_url": "https://github.com/SecPal/.github/actions/runs/1",
    }


def finalize_snapshot(
    value: dict[str, Any],
    *,
    preserve_captured_counts: bool = False,
) -> dict[str, Any]:
    if not preserve_captured_counts:
        value["pull_request"]["captured_connection_counts"] = captured_connection_counts(value)
    counts = review.expected_connection_items(value)
    value["completeness"]["items"] = sum(counts.values())
    value["completeness"]["fully_paginated_connections"] = [
        {"connection": connection, "pages": 1, "items": count}
        for connection, count in sorted(counts.items())
    ]
    value["completeness"]["api_calls"] = review.expected_api_calls(
        value["completeness"]["fully_paginated_connections"]
    )
    return review.attach_digest(value)


def captured_connection_counts(value: dict[str, Any]) -> dict[str, int]:
    """Return the PR-level counts supplied by the capture anchors."""

    pull_request = value["pull_request"]
    return {
        "labels": len(pull_request["labels"]),
        "review_requests": len(pull_request["requested_reviewers"])
        + len(pull_request["requested_teams"]),
        "reviews": len(value["reviews"]),
        "pull_request_reactions": len(pull_request["reactions"]),
        "conversation_comments": len(value["conversation_comments"]),
        "review_threads": len(value["review_threads"]),
        "commits": len(value["commits"]),
    }


def snapshot() -> dict[str, Any]:
    value = {
        "schema_version": "1.0",
        "snapshot_digest_algorithm": "sha256",
        "snapshot_digest": "0" * 64,
        "repository": {
            "id": "REPO_1",
            "owner": "SecPal",
            "name": ".github",
            "name_with_owner": "SecPal/.github",
            "url": "https://github.com/SecPal/.github",
            "default_branch": "main",
        },
        "pull_request": {
            "id": "PR_1",
            "database_id": 1,
            "number": 1,
            "url": "https://github.com/SecPal/.github/pull/1",
            "title": "Fixture pull request",
            "body": "Fixture pull request body.",
            "state": "OPEN",
            "is_draft": False,
            "is_merged": False,
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "review_decision": None,
            "author": actor("author"),
            "base_repository": {
                "id": "REPO_1",
                "name_with_owner": "SecPal/.github",
                "url": "https://github.com/SecPal/.github",
            },
            "base_ref": "main",
            "base_oid": BASE,
            "head_repository": {
                "id": "REPO_1",
                "name_with_owner": "SecPal/.github",
                "url": "https://github.com/SecPal/.github",
            },
            "head_ref": "feat/test",
            "head_oid_before": HEAD,
            "head_oid_after": HEAD,
            "potential_merge_commit_oid": MERGE,
            "check_commit_oid": HEAD,
            "check_commit_source": "head",
            "labels": [],
            "requested_reviewers": [],
            "requested_teams": [],
            "reactions": [],
        },
        "reviews": [],
        "conversation_comments": [],
        "review_threads": [],
        "commits": [
            {
                "oid": HEAD,
                "parents": [PARENT],
                "authored_at": "2026-07-19T00:00:00Z",
                "committed_at": "2026-07-19T00:00:00Z",
                "github_signature": signature(),
                "local_signature": signature(),
            }
        ],
        "checks": [check()],
        "applicable_rules": {
            "rulesets": [
                {
                    "type": "required_status_checks",
                    "strict": True,
                    "required_checks": [{"context": "tests", "integration_id": 1}],
                }
            ],
            "branch_protection": {
                "strict": True,
                "contexts": ["tests"],
                "checks": [{"context": "tests", "app_id": 1}],
            },
            "evidence_complete": True,
        },
        "required_check_evidence": {
            "determination": "complete",
            "required": ["check:1:tests"],
            "missing": [],
            "sources": ["rulesets", "branch_protection"],
            "unknown_reasons": [],
        },
        "completeness": {
            "api_calls": 10,
            "items": 2,
            "configured_caps": {
                "maximum_api_calls": 200,
                "maximum_items": 10000,
                "maximum_threads": 500,
                "maximum_comments": 100,
                "maximum_reactions": 25,
            },
            "fully_paginated_connections": [
                {"connection": "reviews", "pages": 1, "items": 0},
                {"connection": "review_threads", "pages": 1, "items": 0},
            ],
            "warnings": [],
            "blocked_reason": None,
        },
    }
    value["pull_request"]["captured_connection_counts"] = captured_connection_counts(value)
    return finalize_snapshot(value)


def merged_snapshot(*, mergeable: str | None = "UNKNOWN") -> dict[str, Any]:
    """Return complete immutable evidence for an already-merged pull request."""

    value = snapshot()
    pull_request = value["pull_request"]
    pull_request["state"] = "MERGED"
    pull_request["is_merged"] = True
    pull_request["is_draft"] = False
    pull_request["mergeable"] = mergeable
    pull_request["merge_state_status"] = "UNKNOWN"
    pull_request["potential_merge_commit_oid"] = None
    pull_request["check_commit_oid"] = HEAD
    pull_request["check_commit_source"] = "head"
    return finalize_snapshot(value)


class FakeGitRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.overrides: dict[tuple[str, ...], review.CommandResult] = {}

    def set(self, arguments: list[str], returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.overrides[tuple(arguments)] = review.CommandResult(returncode, stdout, stderr)

    def run(self, arguments: list[str], *, allow_failure: bool = False) -> review.CommandResult:
        self.calls.append(arguments)
        key = tuple(arguments)
        if key in self.overrides:
            return self.overrides[key]
        defaults = {
            ("git", "rev-parse", "--show-toplevel"): review.CommandResult(0, "/repo\n", ""),
            ("git", "remote", "get-url", "origin"): review.CommandResult(
                0, "git@github.com:SecPal/.github.git\n", ""
            ),
            ("git", "status", "--porcelain=v2", "--untracked-files=all"): review.CommandResult(0, "", ""),
            ("git", "branch", "--show-current"): review.CommandResult(0, "feat/test\n", ""),
            (
                "git",
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            ): review.CommandResult(0, "origin/feat/test\n", ""),
            ("git", "rev-parse", "HEAD"): review.CommandResult(0, f"{HEAD}\n", ""),
            ("git", "rev-parse", "@{upstream}"): review.CommandResult(0, f"{HEAD}\n", ""),
            ("git", "rev-list", "--reverse", f"{'b' * 40}..{HEAD}"): review.CommandResult(
                0, f"{HEAD}\n", ""
            ),
            ("git", "cat-file", "commit", HEAD): review.CommandResult(
                0,
                "tree deadbeef\ngpgsig -----BEGIN SSH SIGNATURE-----\n signature\n -----END SSH SIGNATURE-----\n\nmessage\n",
                "",
            ),
            ("git", "verify-commit", "--raw", HEAD): review.CommandResult(
                0, "", 'Good "git" signature for aroviqen with ED25519 key SHA256:test\n'
            ),
        }
        result = defaults.get(key, review.CommandResult(2, "", f"unexpected command: {arguments}"))
        if result.returncode and not allow_failure:
            raise review.CommandFailure(arguments, result)
        return result


class SnapshotAndPaginationTests(unittest.TestCase):
    def test_merged_evidence_is_verified_without_authorizing_merge(self) -> None:
        for mergeable in ("UNKNOWN", None):
            with self.subTest(mergeable=mergeable):
                result = review.verify_snapshot_evidence(
                    merged_snapshot(mergeable=mergeable),
                    config(),
                )
                self.assertEqual(result["status"], "EVIDENCE_VERIFIED")
                self.assertTrue(result["evidence_verified"])
                self.assertEqual(result["pull_request_state"], "MERGED")
                self.assertFalse(result["merge_authorized"])
                self.assertEqual(result["blockers"], [])

    def test_merged_evidence_remains_ineligible_for_the_open_pr_gate(self) -> None:
        result = review.verify_snapshot_gate(merged_snapshot(), config())
        self.assertTrue(result["evidence_verified"])
        self.assertEqual(
            result["blockers"],
            [
                {
                    "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                    "reason": "PR is not an open non-draft merge candidate",
                }
            ],
        )

    def test_open_pr_gate_retains_its_existing_ready_result(self) -> None:
        evidence = review.verify_snapshot_evidence(snapshot(), config())
        gate = review.verify_snapshot_gate(snapshot(), config())
        self.assertTrue(evidence["evidence_verified"])
        self.assertEqual(evidence["status"], "EVIDENCE_VERIFIED")
        self.assertEqual(gate["status"], "PACKAGE_2_2_CLASSIFICATION_REQUIRED")
        self.assertEqual(gate["blockers"], [])

    def test_closed_pr_evidence_is_verified_but_cannot_pass_the_open_gate(self) -> None:
        value = snapshot()
        value["pull_request"]["state"] = "CLOSED"
        value["pull_request"]["mergeable"] = None
        value["pull_request"]["merge_state_status"] = "UNKNOWN"
        value["pull_request"]["potential_merge_commit_oid"] = None
        value = finalize_snapshot(value)
        evidence = review.verify_snapshot_evidence(value, config())
        gate = review.verify_snapshot_gate(value, config())
        self.assertTrue(evidence["evidence_verified"])
        self.assertEqual(evidence["pull_request_state"], "CLOSED")
        self.assertEqual(
            gate["blockers"],
            [
                {
                    "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                    "reason": "PR is not an open non-draft merge candidate",
                }
            ],
        )

    def test_open_pr_unknown_or_conflicting_mergeability_still_blocks_the_gate(self) -> None:
        for mergeable in ("UNKNOWN", "CONFLICTING"):
            with self.subTest(mergeable=mergeable):
                value = snapshot()
                value["pull_request"]["mergeable"] = mergeable
                result = review.verify_snapshot_gate(finalize_snapshot(value), config())
                self.assertTrue(result["evidence_verified"])
                self.assertIn(
                    {
                        "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                        "reason": "PR mergeability is conflicting or unknown",
                    },
                    result["blockers"],
                )

    def test_merged_raw_review_state_remains_visible_to_evidence_verification(self) -> None:
        value = merged_snapshot()
        informational = review_record("COMMENTED")
        informational["reactions"] = [reaction("REACTION_REVIEW")]
        historical_changes = review_record("CHANGES_REQUESTED", commit=PARENT)
        historical_changes["id"] = "REVIEW_HISTORICAL_CHANGES"
        historical_changes["database_id"] = 12
        historical_changes["submitted_at"] = "2026-07-18T00:00:00Z"
        value["reviews"] = [historical_changes, informational]
        value["conversation_comments"] = [
            {
                "id": "CONVERSATION_1",
                "database_id": 12,
                "author": actor("human"),
                "body": "Top-level context",
                "url": "https://github.com/SecPal/.github/pull/1#issuecomment-12",
                "created_at": "2026-07-19T00:00:00Z",
                "updated_at": "2026-07-19T00:00:00Z",
                "reactions": [reaction("REACTION_CONVERSATION")],
            }
        ]
        resolved_comment = review_comment("RC_RESOLVED")
        resolved_comment["reactions"] = [reaction("REACTION_THREAD")]
        value["review_threads"] = [
            thread("THREAD_RESOLVED", resolved=True, outdated=True, comments=[resolved_comment]),
            thread(
                "THREAD_UNRESOLVED",
                resolved=False,
                comments=[review_comment("RC_UNRESOLVED", login="human")],
            ),
        ]
        value["pull_request"]["reactions"] = [reaction("REACTION_PR")]
        value["pull_request"]["requested_reviewers"] = [actor("pending-reviewer")]
        value = finalize_snapshot(value)

        evidence = review.verify_snapshot_evidence(value, config())
        raw = evidence["raw_review_state"]
        self.assertTrue(evidence["evidence_verified"])
        self.assertEqual(raw["reviews"], 2)
        self.assertEqual(raw["conversation_comments"], 1)
        self.assertEqual(raw["review_threads"], 2)
        self.assertEqual(raw["resolved_threads"], 1)
        self.assertEqual(raw["unresolved_threads"], 1)
        self.assertEqual(raw["outdated_threads"], 1)
        self.assertEqual(raw["reactions"], 4)
        self.assertEqual(raw["requested_changes_reviews"], 1)
        self.assertFalse(raw["requested_changes"])
        self.assertTrue(raw["review_requested"])
        self.assertTrue(evidence["technical_classification_required"])
        self.assertIn(
            "NOT_READY_FOR_MERGE",
            [item["code"] for item in review.verify_snapshot_gate(value, config())["blockers"]],
        )

    def test_inconsistent_pr_lifecycle_states_are_rejected(self) -> None:
        cases = (
            ("merged_without_flag", {"state": "MERGED", "is_merged": False}),
            ("open_with_merged_flag", {"state": "OPEN", "is_merged": True}),
            ("closed_with_merged_flag", {"state": "CLOSED", "is_merged": True}),
            ("merged_draft", {"state": "MERGED", "is_merged": True, "is_draft": True}),
        )
        for name, changes in cases:
            with self.subTest(case=name):
                value = merged_snapshot()
                value["pull_request"].update(changes)
                with self.assertRaises(review.ContractError):
                    review.verify_snapshot_evidence(review.attach_digest(value), config())

    def test_evidence_rejects_unstable_or_incomplete_snapshot_contracts(self) -> None:
        cases = []
        moved = merged_snapshot()
        moved["pull_request"]["head_oid_after"] = PARENT
        cases.append(("moved_head", moved))
        missing_head = merged_snapshot()
        missing_head["commits"][0]["oid"] = PARENT
        cases.append(("missing_head_commit", finalize_snapshot(missing_head)))
        incomplete = merged_snapshot()
        incomplete["completeness"]["fully_paginated_connections"] = []
        cases.append(("incomplete_pagination", review.attach_digest(incomplete)))
        invalid_digest = merged_snapshot()
        invalid_digest["snapshot_digest"] = "0" * 64
        cases.append(("invalid_digest", invalid_digest))
        for name, value in cases:
            with self.subTest(case=name), self.assertRaises(review.ContractError):
                review.verify_snapshot_evidence(
                    review.attach_digest(value) if name == "moved_head" else value,
                    config(),
                )

    def test_evidence_blocks_required_signature_failures(self) -> None:
        cases = (
            ("github_invalid", "github_signature", "invalid"),
            ("local_unsigned", "local_signature", "unsigned"),
            ("local_unknown_key", "local_signature", "unknown_key"),
            ("local_object_unavailable", "local_signature", "object_unavailable"),
        )
        for name, signature_name, state in cases:
            with self.subTest(case=name):
                value = merged_snapshot()
                value["commits"][0][signature_name] = signature(state)
                result = review.verify_snapshot_evidence(finalize_snapshot(value), config())
                self.assertFalse(result["evidence_verified"])
                self.assertIn(
                    "BLOCKED_INVALID_SIGNATURE",
                    [item["code"] for item in result["blockers"]],
                )
                self.assertTrue(
                    any(state in item["reason"] for item in result["blockers"]),
                    result["blockers"],
                )

    def test_evidence_blocks_every_non_successful_required_check_outcome(self) -> None:
        outcomes = (
            ("pending", [check(status="IN_PROGRESS", conclusion=None)]),
            ("failed", [check(status="COMPLETED", conclusion="FAILURE")]),
            ("missing", []),
        )
        for name, raw_checks in outcomes:
            with self.subTest(outcome=name):
                value = merged_snapshot()
                raw = [
                    {
                        key: item[key]
                        for key in (
                            "stable_id",
                            "name",
                            "application",
                            "status",
                            "conclusion",
                            "details_url",
                        )
                    }
                    for item in raw_checks
                ]
                value["checks"], value["required_check_evidence"] = review.evaluate_checks(
                    raw,
                    [{"context": "tests", "integration_id": 1}],
                    config()["check_policy"],
                )
                result = review.verify_snapshot_evidence(finalize_snapshot(value), config())
                self.assertFalse(result["evidence_verified"])
                self.assertIn(
                    "BLOCKED_FAILED_OR_PENDING_CI",
                    [item["code"] for item in result["blockers"]],
                )

    def test_evidence_rejects_unknown_requiredness_and_incomplete_rules(self) -> None:
        unknown = merged_snapshot()
        unknown["checks"][0]["requiredness"] = "unknown"
        unknown["checks"][0]["evidence_state"] = "requiredness_unknown"
        unknown["required_check_evidence"]["determination"] = "incomplete"
        unknown["required_check_evidence"]["unknown_reasons"] = ["unknown"]
        incomplete_rules = merged_snapshot()
        incomplete_rules["applicable_rules"]["evidence_complete"] = False
        for value in (unknown, incomplete_rules):
            with self.assertRaises(review.ContractError):
                review.verify_snapshot_evidence(review.attach_digest(value), config())

    def test_01_zero_findings(self) -> None:
        result = review.verify_snapshot_gate(snapshot(), config())
        self.assertEqual(result["raw_review_state"]["unresolved_threads"], 0)
        self.assertFalse(result["raw_review_state"]["requested_changes"])

    def test_02_informational_review_only(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record()]
        value = finalize_snapshot(value)
        result = review.verify_snapshot_gate(value, config())
        self.assertEqual(result["raw_review_state"]["reviews"], 1)
        self.assertTrue(result["technical_classification_required"])

    def test_reaction_only_feedback_requires_classification(self) -> None:
        value = snapshot()
        value["pull_request"]["reactions"] = [reaction()]
        result = review.verify_snapshot_gate(finalize_snapshot(value), config())
        self.assertEqual(result["raw_review_state"]["reactions"], 1)
        self.assertTrue(result["technical_classification_required"])

    def test_raw_review_state_counts_reactions_on_every_supported_subject(self) -> None:
        value = snapshot()
        value["pull_request"]["reactions"] = [reaction("REACTION_PR")]
        submitted_review = review_record()
        submitted_review["reactions"] = [reaction("REACTION_REVIEW")]
        value["reviews"] = [submitted_review]
        comment = review_comment()
        comment["reactions"] = [reaction("REACTION_REVIEW_COMMENT")]
        value["review_threads"] = [thread(comments=[comment])]
        value["conversation_comments"] = [
            {
                "id": "CONVERSATION_1",
                "database_id": 12,
                "author": actor(),
                "body": "Reaction subject",
                "url": "https://github.com/SecPal/.github/pull/1#issuecomment-12",
                "created_at": "2026-07-19T00:00:00Z",
                "updated_at": "2026-07-19T00:00:00Z",
                "reactions": [reaction("REACTION_CONVERSATION")],
            }
        ]
        result = review.verify_snapshot_gate(finalize_snapshot(value), config())
        self.assertEqual(result["raw_review_state"]["reactions"], 4)

    def test_03_resolved_and_unresolved_threads(self) -> None:
        value = snapshot()
        value["review_threads"] = [
            thread("T1", resolved=True),
            thread("T2", resolved=False, comments=[review_comment("RC_2")]),
        ]
        value = finalize_snapshot(value)
        result = review.verify_snapshot_gate(value, config())
        self.assertEqual(result["raw_review_state"]["resolved_threads"], 1)
        self.assertEqual(result["raw_review_state"]["unresolved_threads"], 1)

    def test_04_outdated_thread_is_retained(self) -> None:
        value = snapshot()
        value["review_threads"] = [thread(outdated=True)]
        review.validate_snapshot(finalize_snapshot(value))
        self.assertTrue(value["review_threads"][0]["is_outdated"])

    def test_05_requested_changes_review(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record("CHANGES_REQUESTED")]
        value["pull_request"]["review_decision"] = "CHANGES_REQUESTED"
        result = review.verify_snapshot_gate(finalize_snapshot(value), config())
        self.assertTrue(result["raw_review_state"]["requested_changes"])

    def test_superseded_changes_request_does_not_block(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record("CHANGES_REQUESTED"), review_record("APPROVED")]
        value["reviews"][1]["id"] = "REVIEW_2"
        value["reviews"][1]["submitted_at"] = "2026-07-19T00:01:00Z"
        value["pull_request"]["review_decision"] = "APPROVED"
        result = review.verify_snapshot_gate(finalize_snapshot(value), config())
        self.assertFalse(result["raw_review_state"]["requested_changes"])
        self.assertNotIn("NOT_READY_FOR_MERGE", [item["code"] for item in result["blockers"]])

    def test_strict_required_checks_block_a_behind_branch(self) -> None:
        value = snapshot()
        value["pull_request"]["merge_state_status"] = "BEHIND"
        value["applicable_rules"]["branch_protection"]["strict"] = True
        value["applicable_rules"]["rulesets"][0]["strict"] = True
        result = review.verify_snapshot_gate(review.attach_digest(value), config())
        self.assertIn("BLOCKED_HEAD_BEHIND_BASE", [item["code"] for item in result["blockers"]])

    def test_ruleset_strictness_blocks_behind_without_branch_protection(self) -> None:
        value = snapshot()
        value["pull_request"]["merge_state_status"] = "BEHIND"
        value["required_check_evidence"]["sources"] = ["rulesets"]
        value["applicable_rules"]["branch_protection"] = {
            "strict": None,
            "contexts": [],
            "checks": [],
        }
        configuration = config()
        configuration["check_policy"]["require_branch_protection_evidence"] = False
        result = review.verify_snapshot_gate(finalize_snapshot(value), configuration)
        self.assertIn("BLOCKED_HEAD_BEHIND_BASE", [item["code"] for item in result["blockers"]])

    def test_loose_required_checks_do_not_block_a_behind_branch(self) -> None:
        value = snapshot()
        value["pull_request"]["merge_state_status"] = "BEHIND"
        value["applicable_rules"]["branch_protection"]["strict"] = False
        value["applicable_rules"]["rulesets"][0]["strict"] = False
        result = review.verify_snapshot_gate(review.attach_digest(value), config())
        self.assertNotIn("BLOCKED_HEAD_BEHIND_BASE", [item["code"] for item in result["blockers"]])

    def test_unsafe_merge_states_block_the_gate(self) -> None:
        for merge_state in ("DIRTY", "UNKNOWN", "BLOCKED", "DRAFT"):
            with self.subTest(merge_state=merge_state):
                value = snapshot()
                value["pull_request"]["merge_state_status"] = merge_state
                result = review.verify_snapshot_gate(review.attach_digest(value), config())
                self.assertIn(
                    "BLOCKED_UNSAFE_GITHUB_STATE",
                    [item["code"] for item in result["blockers"]],
                )

    def test_merge_states_delegated_to_granular_checks_do_not_add_a_state_blocker(self) -> None:
        for merge_state in ("CLEAN", "HAS_HOOKS", "UNSTABLE"):
            with self.subTest(merge_state=merge_state):
                value = snapshot()
                value["pull_request"]["merge_state_status"] = merge_state
                result = review.verify_snapshot_gate(review.attach_digest(value), config())
                self.assertNotIn(
                    "BLOCKED_UNSAFE_GITHUB_STATE",
                    [item["code"] for item in result["blockers"]],
                )

    def test_merge_state_policy_covers_the_authoritative_enum(self) -> None:
        self.assertEqual(
            review.MERGE_STATE_POLICY,
            {
                "DIRTY": "block",
                "UNKNOWN": "block",
                "BLOCKED": "block",
                "BEHIND": "strict_base",
                "DRAFT": "block",
                "UNSTABLE": "required_checks",
                "HAS_HOOKS": "allow",
                "CLEAN": "allow",
            },
        )
        self.assertEqual(review.MERGE_STATE_STATUSES, set(review.MERGE_STATE_POLICY))

    def test_strict_policy_without_required_checks_does_not_require_current_base(self) -> None:
        value = snapshot()
        value["applicable_rules"]["rulesets"][0]["required_checks"] = []
        value["applicable_rules"]["branch_protection"]["contexts"] = []
        value["applicable_rules"]["branch_protection"]["checks"] = []
        self.assertFalse(review.strict_checks_require_current_base(value, config()["check_policy"]))

    def test_06_unresolved_human_thread(self) -> None:
        value = snapshot()
        value["review_threads"] = [thread(comments=[review_comment(login="human")])]
        result = review.verify_snapshot_gate(finalize_snapshot(value), config())
        self.assertEqual(result["raw_review_state"]["unresolved_threads"], 1)

    def test_review_required_is_a_mechanical_blocker(self) -> None:
        value = snapshot()
        value["pull_request"]["review_decision"] = "REVIEW_REQUIRED"
        result = review.verify_snapshot_gate(review.attach_digest(value), config())
        self.assertIn("NOT_READY_FOR_MERGE", [item["code"] for item in result["blockers"]])

    def test_requested_review_is_a_mechanical_blocker(self) -> None:
        value = snapshot()
        value["pull_request"]["requested_reviewers"] = [actor("pending-reviewer")]
        result = review.verify_snapshot_gate(finalize_snapshot(value), config())
        self.assertIn("NOT_READY_FOR_MERGE", [item["code"] for item in result["blockers"]])
        self.assertTrue(result["raw_review_state"]["review_requested"])

    def test_gate_reapplies_current_skipped_check_policy(self) -> None:
        capture_configuration = config()
        capture_configuration["check_policy"]["expected_skipped"] = "allow"
        raw = [check(status="COMPLETED", conclusion="SKIPPED") | {"requiredness": None, "evidence_state": None}]
        checks, evidence = review.evaluate_checks(
            raw,
            [{"context": "tests", "integration_id": 1}],
            capture_configuration["check_policy"],
        )
        value = snapshot()
        value["checks"] = checks
        value["required_check_evidence"] = evidence
        value = review.attach_digest(value)

        gate_configuration = config()
        gate_configuration["check_policy"]["expected_skipped"] = "block"
        result = review.verify_snapshot_gate(value, gate_configuration)

        self.assertIn("BLOCKED_FAILED_OR_PENDING_CI", [item["code"] for item in result["blockers"]])

    def test_gate_rejects_missing_pagination_evidence(self) -> None:
        value = snapshot()
        value["completeness"]["fully_paginated_connections"] = []
        value = review.attach_digest(value)
        with self.assertRaises(review.ContractError):
            review.verify_snapshot_gate(value, config())

    def test_gate_rejects_capture_warnings(self) -> None:
        value = snapshot()
        value["completeness"]["warnings"] = ["partial capture"]
        value = review.attach_digest(value)
        with self.assertRaises(review.ContractError):
            review.verify_snapshot_gate(value, config())

    def test_gate_rejects_required_rule_source_missing_from_snapshot(self) -> None:
        value = snapshot()
        value["required_check_evidence"]["sources"].remove("rulesets")
        value["applicable_rules"]["rulesets"] = []
        value = finalize_snapshot(value)
        result = review.verify_snapshot_gate(value, config())
        self.assertIn(review.BLOCKED_INCOMPLETE, [item["code"] for item in result["blockers"]])

    def test_gate_preserves_report_when_current_branch_protection_evidence_is_absent(self) -> None:
        value = snapshot()
        value["required_check_evidence"]["sources"] = ["rulesets"]
        value["applicable_rules"]["branch_protection"] = {
            "strict": None,
            "contexts": [],
            "checks": [],
        }
        value = finalize_snapshot(value)

        result = review.verify_snapshot_gate(value, config())

        self.assertEqual(result["snapshot_digest"], value["snapshot_digest"])
        self.assertIn(review.BLOCKED_INCOMPLETE, [item["code"] for item in result["blockers"]])

    def test_gate_enforces_all_current_capture_caps(self) -> None:
        value = snapshot()
        comment = review_comment()
        comment["reactions"] = [
            {
                "id": "REACTION_CAP",
                "content": "EYES",
                "created_at": "2026-07-19T00:01:00Z",
                "user": actor("reactor"),
            }
        ]
        value["review_threads"] = [thread(comments=[comment])]
        value = finalize_snapshot(value)
        for cap in (
            "maximum_api_calls",
            "maximum_items",
            "maximum_threads",
            "maximum_comments",
            "maximum_reactions",
        ):
            with self.subTest(cap=cap):
                configuration = config()
                configuration[cap] = 1
                result = review.verify_snapshot_gate(value, configuration)
                blockers = [item for item in result["blockers"] if item["code"] == review.BLOCKED_INCOMPLETE]
                self.assertTrue(any(cap in item["reason"] for item in blockers), blockers)

    def test_gate_accepts_intentionally_disabled_rule_sources(self) -> None:
        value = snapshot()
        value["required_check_evidence"] = {
            "determination": "complete",
            "required": [],
            "missing": [],
            "sources": [],
            "unknown_reasons": [],
        }
        value["checks"][0]["requiredness"] = "non_required"
        value["checks"][0]["evidence_state"] = "non_required_successful"
        value["applicable_rules"] = {
            "rulesets": [],
            "branch_protection": {"strict": None, "contexts": [], "checks": []},
            "evidence_complete": True,
        }
        value = finalize_snapshot(value)
        configuration = config()
        configuration["check_policy"]["require_ruleset_evidence"] = False
        configuration["check_policy"]["require_branch_protection_evidence"] = False
        result = review.verify_snapshot_gate(value, configuration)
        self.assertEqual(result["blockers"], [])

    def test_gate_source_policy_transition_matrix_is_fail_closed_without_exceptions(self) -> None:
        source_names = {"rulesets", "branch_protection"}
        source_sets = (
            set(),
            {"rulesets"},
            {"branch_protection"},
            source_names,
        )
        for captured_sources in source_sets:
            value = snapshot()
            value["required_check_evidence"]["sources"] = sorted(captured_sources)
            if "rulesets" not in captured_sources:
                value["applicable_rules"]["rulesets"] = []
            if "branch_protection" not in captured_sources:
                value["applicable_rules"]["branch_protection"] = {
                    "strict": None,
                    "contexts": [],
                    "checks": [],
                }
            if not captured_sources:
                value["required_check_evidence"]["required"] = []
                value["checks"][0]["requiredness"] = "non_required"
                value["checks"][0]["evidence_state"] = "non_required_successful"
            value = finalize_snapshot(value)
            for required_sources in source_sets:
                with self.subTest(
                    captured=sorted(captured_sources),
                    required=sorted(required_sources),
                ):
                    configuration = config()
                    configuration["check_policy"]["require_ruleset_evidence"] = (
                        "rulesets" in required_sources
                    )
                    configuration["check_policy"]["require_branch_protection_evidence"] = (
                        "branch_protection" in required_sources
                    )
                    result = review.verify_snapshot_gate(value, configuration)
                    incomplete = review.BLOCKED_INCOMPLETE in {
                        item["code"] for item in result["blockers"]
                    }
                    self.assertEqual(incomplete, bool(required_sources - captured_sources))

    def test_snapshot_rejects_mismatched_connection_item_count(self) -> None:
        value = snapshot()
        value["completeness"]["fully_paginated_connections"][0]["items"] += 1
        value = review.attach_digest(value)
        with self.assertRaises(review.ContractError):
            review.validate_snapshot(value)

    def test_snapshot_rejects_mismatched_api_call_count(self) -> None:
        value = snapshot()
        value["completeness"]["api_calls"] -= 1
        value = review.attach_digest(value)
        with self.assertRaises(review.ContractError):
            review.validate_snapshot(value)

    def test_snapshot_rejects_every_connection_that_exceeds_its_page_capacity(self) -> None:
        value = finalize_snapshot(snapshot())
        connections = value["completeness"]["fully_paginated_connections"]
        for index, item in enumerate(connections):
            with self.subTest(connection=item["connection"]):
                candidate = copy.deepcopy(value)
                candidate["completeness"]["fully_paginated_connections"][index]["items"] = 101
                candidate = review.attach_digest(candidate)
                with self.assertRaisesRegex(review.ContractError, "page capacity"):
                    review.validate_snapshot(candidate)

    def test_snapshot_accepts_an_exact_full_page(self) -> None:
        value = snapshot()
        value["pull_request"]["labels"] = [f"label-{index}" for index in range(100)]
        review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_commit_evidence_without_the_head_commit(self) -> None:
        value = snapshot()
        value["commits"][0]["oid"] = PARENT
        with self.assertRaisesRegex(review.ContractError, "head commit"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_checks_bound_to_the_wrong_commit(self) -> None:
        value = snapshot()
        value["pull_request"]["check_commit_oid"] = MERGE
        with self.assertRaisesRegex(review.ContractError, "wrong commit"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_an_indeterminate_open_mergeable_check_target(self) -> None:
        value = snapshot()
        value["pull_request"]["potential_merge_commit_oid"] = None
        with self.assertRaisesRegex(review.ContractError, "Potential merge commit"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_accepts_nonempty_checks_bound_to_the_test_merge_commit(self) -> None:
        value = snapshot()
        value["pull_request"]["potential_merge_commit_oid"] = MERGE
        value["pull_request"]["check_commit_oid"] = MERGE
        value["pull_request"]["check_commit_source"] = "test_merge"
        review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_an_empty_test_merge_check_selection(self) -> None:
        value = snapshot()
        value["pull_request"]["potential_merge_commit_oid"] = MERGE
        value["pull_request"]["check_commit_oid"] = MERGE
        value["pull_request"]["check_commit_source"] = "test_merge"
        value["checks"] = []
        value["required_check_evidence"]["missing"] = ["check:1:tests"]
        with self.assertRaisesRegex(review.ContractError, "cannot be empty"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_required_check_metadata_that_disagrees_with_rules(self) -> None:
        value = snapshot()
        value["required_check_evidence"]["required"] = []
        with self.assertRaisesRegex(review.ContractError, "Required-check metadata"):
            review.validate_snapshot(review.attach_digest(value))

    def test_snapshot_rejects_unknown_reasons_for_complete_required_check_evidence(self) -> None:
        value = snapshot()
        value["required_check_evidence"]["unknown_reasons"] = ["required checks may be incomplete"]
        with self.assertRaises(review.ContractError):
            review.validate_snapshot(review.attach_digest(value))

    def test_snapshot_rejects_a_duplicate_check_identity(self) -> None:
        value = snapshot()
        duplicate = copy.deepcopy(value["checks"][0])
        duplicate["name"] = "another-name"
        duplicate["requiredness"] = "non_required"
        duplicate["evidence_state"] = "non_required_successful"
        value["checks"].append(duplicate)
        with self.assertRaisesRegex(review.ContractError, "duplicate check identity"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_duplicate_review_identities(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record(), review_record()]
        with self.assertRaisesRegex(review.ContractError, "duplicate review identity"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_duplicate_reaction_identities_across_subjects(self) -> None:
        duplicate = {
            "id": "REACTION_1",
            "content": "EYES",
            "created_at": "2026-07-19T00:01:00Z",
            "user": actor("reactor"),
        }
        value = snapshot()
        value["pull_request"]["reactions"] = [copy.deepcopy(duplicate)]
        submitted_review = review_record()
        submitted_review["reactions"] = [copy.deepcopy(duplicate)]
        value["reviews"] = [submitted_review]
        with self.assertRaisesRegex(review.ContractError, "duplicate reaction identity"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_check_requiredness_that_disagrees_with_rules(self) -> None:
        value = snapshot()
        value["checks"][0]["requiredness"] = "non_required"
        value["checks"][0]["evidence_state"] = "non_required_successful"
        with self.assertRaisesRegex(review.ContractError, "requiredness"):
            review.validate_snapshot(review.attach_digest(value))

    def test_snapshot_rejects_repository_identity_components_that_disagree(self) -> None:
        value = snapshot()
        value["repository"]["owner"] = "Other"
        with self.assertRaisesRegex(review.ContractError, "repository identity"):
            review.validate_snapshot(review.attach_digest(value))

    def test_snapshot_rejects_a_base_repository_unrelated_to_the_queried_repository(self) -> None:
        value = snapshot()
        value["pull_request"]["base_repository"]["name_with_owner"] = "SecPal/other"
        with self.assertRaisesRegex(review.ContractError, "base repository"):
            review.validate_snapshot(review.attach_digest(value))

    def test_snapshot_rejects_inconsistent_merged_state(self) -> None:
        value = snapshot()
        value["pull_request"]["state"] = "MERGED"
        with self.assertRaisesRegex(review.ContractError, "merged state"):
            review.validate_snapshot(review.attach_digest(value))

    def test_snapshot_rejects_duplicate_commit_oids(self) -> None:
        value = snapshot()
        duplicate = copy.deepcopy(value["commits"][0])
        duplicate["oid"] = duplicate["oid"].upper()
        value["commits"].append(duplicate)
        with self.assertRaisesRegex(review.ContractError, "duplicate commit OID"):
            review.validate_snapshot(finalize_snapshot(value))

    def test_snapshot_rejects_a_commit_omitted_from_the_captured_count(self) -> None:
        value = snapshot()
        value["pull_request"]["captured_connection_counts"] = captured_connection_counts(value)
        value["pull_request"]["captured_connection_counts"]["commits"] = 2
        with self.assertRaisesRegex(review.ContractError, "captured commit count"):
            review.validate_snapshot(finalize_snapshot(value, preserve_captured_counts=True))

    def test_snapshot_rejects_every_mismatched_captured_connection_count(self) -> None:
        for connection in review.CAPTURED_CONNECTIONS:
            with self.subTest(connection=connection):
                value = snapshot()
                value["pull_request"]["captured_connection_counts"][connection] += 1
                with self.assertRaisesRegex(review.ContractError, "captured .* count"):
                    review.validate_snapshot(
                        finalize_snapshot(value, preserve_captured_counts=True)
                    )

    def test_snapshot_rejects_inconsistent_signature_verification_flags(self) -> None:
        for signature_name in ("github_signature", "local_signature"):
            for state, verified in (("valid", False), ("invalid", True)):
                with self.subTest(signature=signature_name, state=state, verified=verified):
                    value = snapshot()
                    value["commits"][0][signature_name]["state"] = state
                    value["commits"][0][signature_name]["verified"] = verified
                    with self.assertRaisesRegex(review.ContractError, "signature evidence"):
                        review.validate_snapshot(finalize_snapshot(value))

    def test_completeness_accounts_for_volatile_evidence_revalidation(self) -> None:
        value = snapshot()
        value["review_threads"] = [thread()]
        expected = review.expected_connection_items(value)
        self.assertEqual(expected["labels.revalidation"], 0)
        self.assertEqual(expected["review_requests.revalidation"], 0)
        self.assertEqual(expected["reviews.revalidation"], 0)
        self.assertEqual(expected["commits.revalidation"], 1)
        self.assertEqual(expected[f"commit.{HEAD}.parents.revalidation"], 1)
        self.assertEqual(expected["head_checks.revalidation"], 1)
        self.assertEqual(expected["rulesets.revalidation"], 1)
        self.assertEqual(expected["branch_protection.revalidation"], 1)
        self.assertEqual(expected["review_threads.revalidation"], 1)
        self.assertEqual(expected["review_thread.THREAD_1.comments.revalidation"], 1)
        self.assertEqual(expected["review_comment.RC_1.reactions.revalidation"], 0)

    def test_revalidation_observations_count_against_item_kind_caps(self) -> None:
        value = snapshot()
        comment = review_comment()
        comment["reactions"] = [
            {
                "id": "REACTION_1",
                "content": "THUMBS_UP",
                "created_at": "2026-07-19T00:01:00Z",
                "user": actor(),
            }
        ]
        value["review_threads"] = [thread(comments=[comment])]
        for cap in ("maximum_threads", "maximum_comments", "maximum_reactions"):
            with self.subTest(cap=cap):
                candidate = copy.deepcopy(value)
                candidate["completeness"]["configured_caps"][cap] = 1
                with self.assertRaises(review.ContractError):
                    review.validate_snapshot(finalize_snapshot(candidate))

    def test_reaction_change_during_capture_is_terminal(self) -> None:
        before = [review_comment()]
        after = copy.deepcopy(before)
        after[0]["reactions"] = [
            {
                "id": "REACTION_1",
                "content": "THUMBS_UP",
                "created_at": "2026-07-19T00:01:00Z",
                "user": actor(),
            }
        ]
        with self.assertRaises(review.BlockedError) as raised:
            review.ensure_revalidated_evidence("review reactions", before, after)
        self.assertEqual(raised.exception.code, review.BLOCKED_INCOMPLETE)

    def test_check_change_during_capture_is_terminal(self) -> None:
        before = [check()]
        after = [check(status="COMPLETED", conclusion="FAILURE")]
        with self.assertRaises(review.BlockedError):
            review.ensure_revalidated_evidence("head checks", before, after)

    def test_required_rule_change_during_capture_is_terminal(self) -> None:
        before = snapshot()["applicable_rules"]
        after = copy.deepcopy(before)
        after["rulesets"][0]["required_checks"].append(
            {"context": "new-required-check", "integration_id": 1}
        )
        with self.assertRaises(review.BlockedError):
            review.ensure_revalidated_evidence("required rules", before, after)

    def test_07_copilot_and_codex_are_distinct_configured_identities(self) -> None:
        identities = review.index_reviewer_identities(config())
        self.assertEqual(identities["copilot-pull-request-reviewer"], "copilot")
        self.assertEqual(identities["copilot-pull-request-reviewer[bot]"], "copilot")
        self.assertEqual(identities["chatgpt-codex-connector"], "codex")

    def test_08_multiple_review_submissions_keep_commit_oids(self) -> None:
        value = snapshot()
        first = review_record(commit=PARENT)
        second = review_record(commit=HEAD)
        second["submitted_at"] = "2026-07-19T00:01:00Z"
        value["reviews"] = [first, second]
        normalized = review.normalize_snapshot(value)
        self.assertEqual([item["commit_oid"] for item in normalized["reviews"]], [PARENT, HEAD])

    def test_09_multiple_outer_pages(self) -> None:
        pages = {
            None: review.Page([1], True, "cursor-1"),
            "cursor-1": review.Page([2], False, "cursor-2"),
        }
        budget = review.Budget(config())
        self.assertEqual(review.collect_pages("review_threads", pages.__getitem__, budget), [1, 2])

    def test_10_multiple_comment_pages_in_one_thread(self) -> None:
        pages = {
            None: review.Page(["first"], True, "comment-1"),
            "comment-1": review.Page(["reply"], False, "comment-2"),
        }
        budget = review.Budget(config())
        self.assertEqual(review.collect_pages("review_threads.T1.comments", pages.__getitem__, budget), ["first", "reply"])

    def test_thread_metadata_query_does_not_multiply_nested_connections(self) -> None:
        self.assertNotIn("comments(first:", review.REVIEW_THREADS_QUERY)
        self.assertIn("comments(first:100", review.REVIEW_THREAD_COMMENTS_QUERY)

    def test_all_graphql_page_sizes_match_the_snapshot_capacity_invariant(self) -> None:
        sizes = {
            int(size)
            for name, document in vars(review).items()
            if name.endswith("_QUERY") and isinstance(document, str)
            for size in re.findall(r"first:(\d+)", document)
        }
        self.assertEqual(sizes, {review.CAPTURE_PAGE_SIZE})

    def test_review_and_pull_request_reactions_have_independent_paginated_queries(self) -> None:
        self.assertIn("reactions(first:100)", review.PULL_REQUEST_REVIEWS_QUERY)
        self.assertIn("... on PullRequestReview", review.REVIEW_REACTIONS_QUERY)
        self.assertIn("reactions(first:100", review.REVIEW_REACTIONS_QUERY)
        self.assertIn("reactions(first:100", review.PULL_REQUEST_REACTIONS_QUERY)
        self.assertIn("reactions { totalCount }", review.PULL_REQUEST_ANCHOR_QUERY)

    def test_review_normalization_retains_summary_reactions(self) -> None:
        value = {
            "id": "REVIEW_1",
            "databaseId": 11,
            "author": {
                "__typename": "User",
                "id": "USER_1",
                "databaseId": 1,
                "login": "reviewer",
                "url": "https://github.com/reviewer",
            },
            "state": "COMMENTED",
            "body": "Summary",
            "url": "https://github.com/SecPal/.github/pull/1#pullrequestreview-11",
            "submittedAt": "2026-07-19T00:00:00Z",
            "commit": {"oid": HEAD},
            "reactions": {
                "nodes": [
                    {
                        "id": "REACTION_1",
                        "content": "EYES",
                        "createdAt": "2026-07-19T00:01:00Z",
                        "user": {
                            "__typename": "User",
                            "id": "USER_2",
                            "databaseId": 2,
                            "login": "reactor",
                            "url": "https://github.com/reactor",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
        self.assertEqual(review._normalize_review(value)["reactions"][0]["content"], "EYES")

    def test_11_unequal_connection_page_counts_do_not_refetch(self) -> None:
        calls: dict[str, list[str | None]] = {"reviews": [], "comments": []}

        def reviews(cursor: str | None) -> review.Page:
            calls["reviews"].append(cursor)
            return review.Page(["review"], False, "r1")

        comment_pages = {None: review.Page([1], True, "c1"), "c1": review.Page([2], False, "c2")}

        def comments(cursor: str | None) -> review.Page:
            calls["comments"].append(cursor)
            return comment_pages[cursor]

        budget = review.Budget(config())
        review.collect_pages("reviews", reviews, budget)
        review.collect_pages("comments", comments, budget)
        self.assertEqual(calls, {"reviews": [None], "comments": [None, "c1"]})

    def test_12_multiple_reaction_pages(self) -> None:
        pages = {
            None: review.Page(["THUMBS_UP"], True, "reaction-1"),
            "reaction-1": review.Page(["THUMBS_DOWN"], False, "reaction-2"),
        }
        budget = review.Budget(config())
        self.assertEqual(
            review.collect_pages("review_comment.R1.reactions", pages.__getitem__, budget, kind="reactions"),
            ["THUMBS_UP", "THUMBS_DOWN"],
        )

    def test_13_exact_cap_exhaustion_blocks_when_more_pages_exist(self) -> None:
        limited = config()
        limited["maximum_items"] = 1
        pages = {None: review.Page([1], True, "next")}
        with self.assertRaises(review.BlockedError) as raised:
            review.collect_pages("reviews", pages.__getitem__, review.Budget(limited))
        self.assertEqual(raised.exception.code, "BLOCKED_INCOMPLETE_REVIEW_STATE")
        self.assertEqual(raised.exception.connection, "reviews")
        self.assertEqual(raised.exception.cursor, "next")

    def test_14_mid_page_api_failure_is_terminal(self) -> None:
        def fetch(cursor: str | None) -> review.Page:
            if cursor is not None:
                raise review.BlockedError("BLOCKED_INCOMPLETE_REVIEW_STATE", "partial API failure", "reviews", cursor)
            return review.Page([1], True, "next")

        with self.assertRaises(review.BlockedError):
            review.collect_pages("reviews", fetch, review.Budget(config()))

    def test_15_rate_limit_failure_is_terminal_without_retry(self) -> None:
        failure = review.classify_api_failure("API rate limit exceeded")
        self.assertEqual(failure.code, "BLOCKED_INCOMPLETE_REVIEW_STATE")
        self.assertIn("rate limit", failure.message.lower())

    def test_16_malformed_json(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.parse_api_json("not-json", "reviews")

    def test_17_graphql_errors_with_http_success(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.parse_graphql_payload('{"data": {}, "errors": [{"message": "denied"}]}', "reviews")

    def test_18_null_repository_or_pull_request(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.extract_anchor({"data": {"repository": None}})
        with self.assertRaises(review.BlockedError):
            review.extract_anchor({"data": {"repository": {"pullRequest": None}}})

    def test_merged_pull_request_anchor_is_supported(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        fixture["data"]["repository"]["pullRequest"]["state"] = "MERGED"
        fixture["data"]["repository"]["pullRequest"]["merged"] = True
        anchor = review.extract_anchor(fixture)
        self.assertEqual(anchor["pull_request"]["state"], "MERGED")

    def test_draft_merge_state_is_captured_and_blocked_by_lifecycle_gate(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        fixture["data"]["repository"]["pullRequest"]["isDraft"] = True
        fixture["data"]["repository"]["pullRequest"]["mergeStateStatus"] = "DRAFT"
        anchor = review.extract_anchor(fixture)
        self.assertEqual(anchor["pull_request"]["mergeStateStatus"], "DRAFT")

        value = snapshot()
        value["pull_request"]["is_draft"] = True
        value["pull_request"]["merge_state_status"] = "DRAFT"
        result = review.verify_snapshot_gate(review.attach_digest(value), config())
        self.assertIn("BLOCKED_UNSAFE_GITHUB_STATE", [item["code"] for item in result["blockers"]])

    def test_19_deleted_author_is_explicit(self) -> None:
        self.assertEqual(review.normalize_actor(None), actor(None))

    def test_20_null_path_and_line_are_preserved(self) -> None:
        value = thread()
        value["path"] = None
        value["line"] = None
        normalized = review.normalize_review_thread(value)
        self.assertIsNone(normalized["path"])
        self.assertIsNone(normalized["line"])


class LocalGitTests(unittest.TestCase):
    def assert_blocker(self, result: dict[str, Any], code: str) -> None:
        self.assertIn(code, [item["code"] for item in result["blockers"]])

    def test_21_clean_matching_local_remote_pr_head(self) -> None:
        result = review.verify_local_against_snapshot(snapshot(), config(), FakeGitRunner(), None)
        self.assertEqual(result["blockers"], [])

    def test_22_dirty_tracked_state(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "status", "--porcelain=v2", "--untracked-files=all"], 0, "1 .M N... file\n")
        self.assert_blocker(review.verify_local_against_snapshot(snapshot(), config(), runner, None), "BLOCKED_UNCLEAN_WORKTREE")

    def test_23_untracked_state(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "status", "--porcelain=v2", "--untracked-files=all"], 0, "? hostile name\n")
        self.assert_blocker(review.verify_local_against_snapshot(snapshot(), config(), runner, None), "BLOCKED_UNCLEAN_WORKTREE")

    def test_24_wrong_branch(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "branch", "--show-current"], 0, "other\n")
        self.assert_blocker(review.verify_local_against_snapshot(snapshot(), config(), runner, None), "BLOCKED_HEAD_MOVED")

    def test_25_missing_upstream(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], 128, stderr="no upstream")
        self.assert_blocker(review.verify_local_against_snapshot(snapshot(), config(), runner, None), "BLOCKED_HEAD_MOVED")

    def test_26_remote_ahead_of_local(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "rev-parse", "@{upstream}"], 0, f"{'d' * 40}\n")
        self.assert_blocker(review.verify_local_against_snapshot(snapshot(), config(), runner, None), "BLOCKED_HEAD_MOVED")

    def test_27_local_ahead_of_remote(self) -> None:
        value = snapshot()
        value["pull_request"]["head_oid_before"] = "d" * 40
        value["pull_request"]["head_oid_after"] = "d" * 40
        value["pull_request"]["check_commit_oid"] = "d" * 40
        value["commits"][0]["oid"] = "d" * 40
        value = finalize_snapshot(value)
        self.assert_blocker(review.verify_local_against_snapshot(value, config(), FakeGitRunner(), None), "BLOCKED_HEAD_MOVED")

    def test_28_pr_head_mismatch(self) -> None:
        self.assert_blocker(
            review.verify_local_against_snapshot(snapshot(), config(), FakeGitRunner(), "d" * 40),
            "BLOCKED_HEAD_MOVED",
        )

    def test_29_head_movement_during_capture(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.ensure_unchanged_head(HEAD, "d" * 40)

    def test_non_head_anchor_movement_during_capture(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        before = review.extract_anchor(copy.deepcopy(fixture))
        changed = copy.deepcopy(fixture)
        changed["data"]["repository"]["pullRequest"]["isDraft"] = True
        after = review.extract_anchor(changed)
        with self.assertRaises(review.BlockedError):
            review.ensure_unchanged_anchor(before, after)

    def test_anchor_query_captures_review_update_sentinels(self) -> None:
        self.assertIn("updatedAt", review.PULL_REQUEST_ANCHOR_QUERY)
        for connection in (
            "labels",
            "reviewRequests",
            "reviews",
            "comments",
            "reviewThreads",
            "commits",
            "reactions",
        ):
            with self.subTest(connection=connection):
                self.assertIn(f"{connection} {{ totalCount }}", review.PULL_REQUEST_ANCHOR_QUERY)

    def test_anchor_captures_the_potential_test_merge_commit(self) -> None:
        self.assertIn("potentialMergeCommit { oid }", review.PULL_REQUEST_ANCHOR_QUERY)

    def test_test_merge_checks_take_precedence_when_present(self) -> None:
        self.assertEqual(
            review.select_effective_check_target(HEAD, MERGE, [check()]),
            (MERGE, "test_merge"),
        )
        self.assertEqual(
            review.select_effective_check_target(HEAD, MERGE, []),
            (HEAD, "head"),
        )

    def test_effective_check_capture_falls_back_to_head_only_for_an_empty_test_merge(self) -> None:
        client = object()
        with mock.patch.object(
            review,
            "_capture_checks",
            side_effect=[[], [check()]],
        ) as capture:
            checks, oid, source = review._capture_effective_checks(client, HEAD, MERGE)
        self.assertEqual((checks, oid, source), ([check()], HEAD, "head"))
        self.assertEqual(
            capture.call_args_list,
            [
                mock.call(client, MERGE, "test_merge_checks"),
                mock.call(client, HEAD, "head_checks"),
            ],
        )

    def test_effective_check_capture_does_not_mix_head_and_test_merge_contexts(self) -> None:
        client = object()
        with mock.patch.object(review, "_capture_checks", return_value=[check()]) as capture:
            checks, oid, source = review._capture_effective_checks(client, HEAD, MERGE)
        self.assertEqual((checks, oid, source), ([check()], MERGE, "test_merge"))
        capture.assert_called_once_with(client, MERGE, "test_merge_checks")

    def test_anchor_requires_review_update_sentinels(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        pull_request = fixture["data"]["repository"]["pullRequest"]
        pull_request["updatedAt"] = "2026-07-19T00:00:00Z"
        for connection in (
            "labels",
            "reviewRequests",
            "reviews",
            "comments",
            "reviewThreads",
            "commits",
            "reactions",
        ):
            pull_request[connection] = {"totalCount": 0}
        before = review.extract_anchor(copy.deepcopy(fixture))
        changed = copy.deepcopy(fixture)
        changed["data"]["repository"]["pullRequest"]["updatedAt"] = "2026-07-19T00:01:00Z"
        after = review.extract_anchor(changed)
        with self.assertRaises(review.BlockedError):
            review.ensure_unchanged_anchor(before, after)

        del fixture["data"]["repository"]["pullRequest"]["updatedAt"]
        with self.assertRaises(review.BlockedError):
            review.extract_anchor(fixture)

    def test_anchor_requires_well_formed_potential_merge_commit_evidence(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        del fixture["data"]["repository"]["pullRequest"]["potentialMergeCommit"]
        with self.assertRaisesRegex(review.BlockedError, "Potential merge commit"):
            review.extract_anchor(fixture)

    def test_anchor_blocks_when_test_merge_generation_is_still_indeterminate(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        pull_request = fixture["data"]["repository"]["pullRequest"]
        pull_request["mergeable"] = "UNKNOWN"
        pull_request["potentialMergeCommit"] = None
        with self.assertRaisesRegex(review.BlockedError, "still being generated"):
            review.extract_anchor(fixture)

    def test_conflicting_anchor_can_have_no_potential_merge_commit(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        pull_request = fixture["data"]["repository"]["pullRequest"]
        pull_request["mergeable"] = "CONFLICTING"
        pull_request["mergeStateStatus"] = "DIRTY"
        pull_request["potentialMergeCommit"] = None
        self.assertIsNone(review.extract_anchor(fixture)["pull_request"]["potentialMergeCommit"])

    def test_anchor_counts_must_match_captured_collections(self) -> None:
        fixture = json.loads(
            (FIXTURES / "fake-github-pages.json").read_text(encoding="utf-8")
        )["graphql"]["PullRequestAnchor"]["null"]
        pull_request = review.extract_anchor(fixture)["pull_request"]
        captured = {
            connection: pull_request[connection]["totalCount"]
            for connection in review.ANCHOR_CONNECTIONS
        }
        review.ensure_anchor_counts_match(pull_request, captured)
        captured["reviews"] -= 1
        with self.assertRaises(review.BlockedError):
            review.ensure_anchor_counts_match(pull_request, captured)

    def test_30_unexpected_base_branch(self) -> None:
        value = snapshot()
        value["pull_request"]["base_ref"] = "develop"
        value = review.attach_digest(value)
        self.assert_blocker(review.verify_local_against_snapshot(value, config(), FakeGitRunner(), None), "BLOCKED_UNSAFE_GITHUB_STATE")

    def test_31_unavailable_commit_object(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "cat-file", "commit", HEAD], 1, stderr="missing")
        result = review.verify_local_against_snapshot(snapshot(), config(), runner, None)
        self.assertEqual(result["commit_signatures"][0]["state"], "object_unavailable")

    def test_local_commit_set_must_match_pr(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "rev-list", "--reverse", f"{'b' * 40}..{HEAD}"], 0, "")
        result = review.verify_local_against_snapshot(snapshot(), config(), runner, None)
        self.assert_blocker(result, "BLOCKED_UNEXPLAINED_COMMIT")


class SignatureAndCheckTests(unittest.TestCase):
    def test_32_valid_ssh_signature(self) -> None:
        value = review.interpret_local_signature(0, 'Good "git" signature for user with ED25519 key')
        self.assertEqual((value["state"], value["format"]), ("valid", "ssh"))

    def test_33_valid_openpgp_signature(self) -> None:
        value = review.interpret_local_signature(0, "gpg: Good signature from user")
        self.assertEqual((value["state"], value["format"]), ("valid", "openpgp"))

    def test_34_unsigned_commit(self) -> None:
        self.assertEqual(review.interpret_local_signature(1, "does not have a signature")["state"], "unsigned")

    def test_35_invalid_signature(self) -> None:
        self.assertEqual(review.interpret_local_signature(1, "BAD signature")["state"], "invalid")

    def test_36_unknown_signing_key(self) -> None:
        self.assertEqual(review.interpret_local_signature(1, "No public key")["state"], "unknown_key")

    def test_37_verification_pending_or_unavailable(self) -> None:
        value = review.normalize_github_signature({"isValid": False, "state": "PENDING", "__typename": "SshSignature"})
        self.assertEqual(value["state"], "verification_pending")

    def test_successful_x509_signature_is_not_mislabeled_openpgp(self) -> None:
        value = review.interpret_local_signature(0, "gpgsm: Good signature from user")
        self.assertEqual((value["state"], value["format"]), ("valid", "smime"))

    def test_openpgp_status_record_wins_over_signer_uid_text(self) -> None:
        value = review.interpret_local_signature(
            0,
            "gpg: Signature made\n[GNUPG:] GOODSIG 0123456789ABCDEF ssh@example.com",
        )
        self.assertEqual((value["state"], value["format"]), ("valid", "openpgp"))

    def test_ambiguous_gnupg_record_is_not_assumed_openpgp(self) -> None:
        value = review.interpret_local_signature(
            0,
            "[GNUPG:] GOODSIG 0123456789ABCDEF signer@example.com",
        )
        self.assertEqual((value["state"], value["format"]), ("valid", "unknown"))

    def test_raw_openpgp_status_uses_commit_signature_envelope(self) -> None:
        runner = FakeGitRunner()
        runner.set(
            ["git", "cat-file", "commit", HEAD],
            0,
            "tree deadbeef\ngpgsig -----BEGIN PGP SIGNATURE-----\n signature\n -----END PGP SIGNATURE-----\n\nmessage\n",
        )
        runner.set(
            ["git", "verify-commit", "--raw", HEAD],
            0,
            stderr="[GNUPG:] GOODSIG 0123456789ABCDEF signer@example.com",
        )
        value = review.local_signature_for_commit(runner, HEAD)
        self.assertEqual((value["state"], value["format"]), ("valid", "openpgp"))

    def test_raw_x509_status_uses_commit_signature_envelope(self) -> None:
        runner = FakeGitRunner()
        runner.set(
            ["git", "cat-file", "commit", HEAD],
            0,
            "tree deadbeef\ngpgsig -----BEGIN SIGNED MESSAGE-----\n signature\n -----END SIGNED MESSAGE-----\n\nmessage\n",
        )
        runner.set(
            ["git", "verify-commit", "--raw", HEAD],
            0,
            stderr="[GNUPG:] GOODSIG 0123456789ABCDEF signer@example.com",
        )
        value = review.local_signature_for_commit(runner, HEAD)
        self.assertEqual((value["state"], value["format"]), ("valid", "smime"))

    def test_failed_x509_signature_is_not_mislabeled_openpgp(self) -> None:
        value = review.interpret_local_signature(1, "gpgsm: BAD signature from user")
        self.assertEqual((value["state"], value["format"]), ("invalid", "smime"))

    def test_local_verification_enforces_accepted_signature_formats(self) -> None:
        configuration = config()
        configuration["signature_policy"]["accepted_formats"] = ["ssh"]
        runner = FakeGitRunner()
        runner.set(
            ["git", "verify-commit", "--raw", HEAD],
            0,
            stderr="gpg: Good signature from reviewer",
        )
        result = review.verify_local_against_snapshot(snapshot(), configuration, runner, None)
        self.assertIn("BLOCKED_INVALID_SIGNATURE", [item["code"] for item in result["blockers"]])

    def test_local_verification_honors_disabled_signature_requirement(self) -> None:
        configuration = config()
        configuration["signature_policy"]["require_local_verified"] = False
        runner = FakeGitRunner()
        runner.set(
            ["git", "verify-commit", "--raw", HEAD],
            1,
            stderr="does not have a signature",
        )
        result = review.verify_local_against_snapshot(snapshot(), configuration, runner, None)
        self.assertNotIn("BLOCKED_INVALID_SIGNATURE", [item["code"] for item in result["blockers"]])

    def evaluated(self, status: str, conclusion: str | None, expected_skipped: str = "block") -> list[dict[str, Any]]:
        raw = [
            {
                "stable_id": "check:1:tests",
                "name": "tests",
                "application": {"id": "APP_1", "database_id": 1, "name": "Actions", "slug": "github-actions"},
                "status": status,
                "conclusion": conclusion,
                "details_url": None,
            }
        ]
        policy = config()["check_policy"] | {"expected_skipped": expected_skipped}
        return review.evaluate_checks(raw, [{"context": "tests", "integration_id": 1}], policy)[0]

    def test_38_all_required_checks_successful(self) -> None:
        self.assertEqual(self.evaluated("COMPLETED", "SUCCESS")[0]["evidence_state"], "required_successful")

    def test_39_required_check_pending(self) -> None:
        self.assertEqual(self.evaluated("IN_PROGRESS", None)[0]["evidence_state"], "required_pending")

    def test_40_required_check_failed(self) -> None:
        self.assertEqual(self.evaluated("COMPLETED", "FAILURE")[0]["evidence_state"], "required_failed")

    def test_41_required_check_missing(self) -> None:
        checks, evidence = review.evaluate_checks([], [{"context": "tests", "integration_id": 1}], config()["check_policy"])
        self.assertEqual(checks[0]["evidence_state"], "required_missing")
        self.assertEqual(evidence["missing"], ["check:1:tests"])

    def test_newer_check_run_supersedes_an_older_failure_from_the_same_app(self) -> None:
        raw = []
        for stable_id, conclusion, started_at in (
            ("check_run:OLD", "FAILURE", "2026-07-20T08:45:24Z"),
            ("check_run:NEW", "SUCCESS", "2026-07-20T09:04:05Z"),
        ):
            raw.append(
                {
                    "stable_id": stable_id,
                    "name": "tests",
                    "application": {
                        "id": "APP_1",
                        "database_id": 1,
                        "name": "Actions",
                        "slug": "github-actions",
                    },
                    "status": "COMPLETED",
                    "conclusion": conclusion,
                    "started_at": started_at,
                    "created_at": None,
                    "details_url": f"https://github.com/SecPal/.github/actions/runs/{stable_id[-3:]}",
                }
            )

        checks, evidence = review.evaluate_checks(
            raw,
            [{"context": "tests", "integration_id": 1}],
            config()["check_policy"],
        )
        by_id = {item["stable_id"]: item for item in checks}
        self.assertFalse(by_id["check_run:OLD"]["is_effective"])
        self.assertTrue(by_id["check_run:NEW"]["is_effective"])

        value = snapshot()
        value["checks"] = checks
        value["required_check_evidence"] = evidence
        result = review.verify_snapshot_evidence(finalize_snapshot(value), config())
        self.assertTrue(result["evidence_verified"])
        self.assertEqual(result["blockers"], [])

    def test_latest_required_check_failure_cannot_be_hidden_by_an_older_success(self) -> None:
        raw = []
        for stable_id, conclusion, started_at in (
            ("check_run:OLD", "SUCCESS", "2026-07-20T08:45:24Z"),
            ("check_run:NEW", "FAILURE", "2026-07-20T09:04:05Z"),
        ):
            raw.append(
                {
                    "stable_id": stable_id,
                    "name": "tests",
                    "application": {
                        "id": "APP_1",
                        "database_id": 1,
                        "name": "Actions",
                        "slug": "github-actions",
                    },
                    "status": "COMPLETED",
                    "conclusion": conclusion,
                    "started_at": started_at,
                    "created_at": None,
                    "details_url": f"https://github.com/SecPal/.github/actions/runs/{stable_id[-3:]}",
                }
            )

        checks, evidence = review.evaluate_checks(
            raw,
            [{"context": "tests", "integration_id": 1}],
            config()["check_policy"],
        )
        value = snapshot()
        value["checks"] = checks
        value["required_check_evidence"] = evidence
        result = review.verify_snapshot_evidence(finalize_snapshot(value), config())
        self.assertFalse(result["evidence_verified"])
        self.assertEqual(
            [item["reason"] for item in result["blockers"]],
            ["tests: required_failed"],
        )

    def test_duplicate_check_runs_without_ordering_evidence_remain_fail_closed(self) -> None:
        raw = [
            {
                "stable_id": f"check_run:{suffix}",
                "name": "tests",
                "application": {
                    "id": "APP_1",
                    "database_id": 1,
                    "name": "Actions",
                    "slug": "github-actions",
                },
                "status": "COMPLETED",
                "conclusion": conclusion,
                "details_url": None,
            }
            for suffix, conclusion in (("OLD", "FAILURE"), ("NEW", "SUCCESS"))
        ]
        checks, evidence = review.evaluate_checks(
            raw,
            [{"context": "tests", "integration_id": 1}],
            config()["check_policy"],
        )
        self.assertTrue(all(item["is_effective"] for item in checks))
        value = snapshot()
        value["checks"] = checks
        value["required_check_evidence"] = evidence
        result = review.verify_snapshot_evidence(finalize_snapshot(value), config())
        self.assertFalse(result["evidence_verified"])
        self.assertIn("tests: required_failed", [item["reason"] for item in result["blockers"]])

    def test_generic_requirement_is_satisfied_by_the_only_present_context_kind(self) -> None:
        raw = [check() | {"requiredness": None, "evidence_state": None}]
        _, evidence = review.evaluate_checks(
            raw,
            [
                {"context": "tests", "integration_id": None},
                {"context": "tests", "integration_id": 1},
            ],
            config()["check_policy"],
        )
        self.assertEqual(evidence["missing"], [])

    def test_same_named_check_and_status_are_both_evaluated_as_required(self) -> None:
        raw = [
            check() | {"requiredness": None, "evidence_state": None},
            {
                "stable_id": "status_context:STATUS_1",
                "name": "tests",
                "application": {
                    "id": None,
                    "database_id": None,
                    "name": "legacy-status",
                    "slug": "legacy-status",
                },
                "status": "FAILURE",
                "conclusion": "FAILURE",
                "details_url": None,
            },
        ]
        checks, evidence = review.evaluate_checks(
            raw,
            [{"context": "tests", "integration_id": None}],
            config()["check_policy"],
        )
        self.assertEqual(evidence["missing"], [])
        states = {item["stable_id"]: item["evidence_state"] for item in checks}
        self.assertEqual(
            states,
            {
                "check:1:tests": "required_successful",
                "status_context:STATUS_1": "required_failed",
            },
        )

    def test_status_creator_id_does_not_satisfy_app_requirement(self) -> None:
        raw = review._normalize_check(
            {
                "__typename": "StatusContext",
                "id": "STATUS_1",
                "context": "tests",
                "state": "SUCCESS",
                "targetUrl": None,
                "creator": {
                    "__typename": "User",
                    "id": "USER_1",
                    "databaseId": 1,
                    "login": "reviewer",
                    "url": "https://github.com/reviewer",
                },
            }
        )
        checks, evidence = review.evaluate_checks(
            [raw],
            [{"context": "tests", "integration_id": 1}],
            config()["check_policy"],
        )
        status_context = next(item for item in checks if item["stable_id"] == "status_context:STATUS_1")
        self.assertEqual(status_context["requiredness"], "non_required")
        self.assertEqual(evidence["missing"], ["check:1:tests"])

    def test_42_requiredness_unknown(self) -> None:
        raw = [check() | {"requiredness": None, "evidence_state": None}]
        checks, evidence = review.evaluate_checks(raw, None, config()["check_policy"])
        self.assertEqual(checks[0]["evidence_state"], "requiredness_unknown")
        self.assertEqual(evidence["determination"], "incomplete")

    def test_43_optional_check_failed(self) -> None:
        raw = [check("optional", conclusion="FAILURE") | {"requiredness": None, "evidence_state": None}]
        checks, _ = review.evaluate_checks(raw, [], config()["check_policy"])
        self.assertEqual(checks[0]["evidence_state"], "non_required_failed")

    def test_44_expected_skipped_check_follows_policy(self) -> None:
        self.assertEqual(self.evaluated("COMPLETED", "SKIPPED", "block")[0]["evidence_state"], "required_failed")
        self.assertEqual(self.evaluated("COMPLETED", "SKIPPED", "allow")[0]["evidence_state"], "required_successful")

    def test_45_inaccessible_ruleset_evidence(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.require_rule_evidence(None, {}, config()["check_policy"])

    def test_required_workflow_rule_blocks_as_unsupported_requiredness(self) -> None:
        with self.assertRaisesRegex(review.BlockedError, "workflow"):
            review.require_rule_evidence(
                [
                    {
                        "type": "workflows",
                        "parameters": {
                            "workflows": [
                                {
                                    "path": ".github/workflows/quality.yml",
                                    "repository_id": 1,
                                }
                            ]
                        },
                    }
                ],
                {"strict": True, "contexts": [], "checks": []},
                config()["check_policy"],
            )

    def test_normalized_required_workflow_rule_cannot_bypass_gate_validation(self) -> None:
        value = snapshot()
        value["applicable_rules"]["rulesets"] = [{"type": "workflows"}]
        value = review.attach_digest(value)
        with self.assertRaisesRegex(review.ContractError, "workflow"):
            review.validate_snapshot(value)

    def test_ruleset_generic_requirement_survives_app_bound_branch_protection(self) -> None:
        required = review.require_rule_evidence(
            [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [
                            {"context": "tests", "integration_id": None}
                        ],
                        "strict_required_status_checks_policy": True,
                    },
                }
            ],
            {
                "strict": True,
                "contexts": ["tests"],
                "checks": [{"context": "tests", "app_id": 1}],
            },
            config()["check_policy"],
        )
        self.assertEqual(
            required,
            [
                {"context": "tests", "integration_id": None},
                {"context": "tests", "integration_id": 1},
            ],
        )
        checks, evidence = review.evaluate_checks(
            [
                check() | {"requiredness": None, "evidence_state": None},
                {
                    "stable_id": "status_context:STATUS_1",
                    "name": "tests",
                    "application": {
                        "id": None,
                        "database_id": None,
                        "name": "legacy-status",
                        "slug": "legacy-status",
                    },
                    "status": "FAILURE",
                    "conclusion": "FAILURE",
                    "details_url": None,
                },
            ],
            required,
            config()["check_policy"],
        )
        self.assertEqual(evidence["missing"], [])
        states = {item["stable_id"]: item["evidence_state"] for item in checks}
        self.assertEqual(states["check:1:tests"], "required_successful")
        self.assertEqual(states["status_context:STATUS_1"], "required_failed")

    def test_branch_protection_app_requirement_still_refines_its_legacy_context(self) -> None:
        required = review.require_rule_evidence(
            [],
            {
                "strict": True,
                "contexts": ["tests"],
                "checks": [{"context": "tests", "app_id": 1}],
            },
            config()["check_policy"],
        )
        self.assertEqual(required, [{"context": "tests", "integration_id": 1}])

    def test_branch_protection_preserves_required_check_with_null_app_id(self) -> None:
        required = review.require_rule_evidence(
            [],
            {
                "strict": True,
                "contexts": ["tests"],
                "checks": [{"context": "tests", "app_id": None}],
            },
            config()["check_policy"],
        )
        self.assertEqual(required, [{"context": "tests", "integration_id": None}])

    def test_branch_protection_any_app_sentinel_is_generic(self) -> None:
        required = review.require_rule_evidence(
            [],
            {
                "strict": True,
                "contexts": [],
                "checks": [{"context": "tests", "app_id": -1}],
            },
            config()["check_policy"],
        )
        self.assertEqual(required, [{"context": "tests", "integration_id": None}])

    def test_malformed_strict_check_policy_is_incomplete(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.require_rule_evidence(
                [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [],
                            "strict_required_status_checks_policy": None,
                        },
                    }
                ],
                {"strict": True, "contexts": [], "checks": []},
                config()["check_policy"],
            )


class SecurityAndOutputTests(unittest.TestCase):
    def test_non_object_json_roots_return_structured_invalid_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, value in enumerate(([], None, "configuration", 1, True)):
                with self.subTest(config=value):
                    config_path = root / f"config-{index}.json"
                    config_path.write_text(json.dumps(value), encoding="utf-8")
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        exit_code = review.main(
                            [
                                "snapshot",
                                "--repo",
                                "SecPal/.github",
                                "--pr",
                                "1",
                                "--config",
                                str(config_path),
                            ]
                        )
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(
                        json.loads(stderr.getvalue())["status"],
                        "INVALID_OR_UNSAFE_INPUT",
                    )
            snapshot_path = root / "snapshot.json"
            snapshot_path.write_text("[]\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = review.main(["verify-gate", "--snapshot", str(snapshot_path)])
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stderr.getvalue())["status"], "INVALID_OR_UNSAFE_INPUT")

    def test_46_hostile_markdown_is_escaped(self) -> None:
        self.assertNotIn("<script>", review.escape_markdown("<script>alert(1)</script>"))

    def test_47_html_comment_terminator_is_escaped(self) -> None:
        self.assertNotIn("-->", review.escape_markdown("payload --> tail"))

    def test_48_code_fences_inside_body_cannot_close_renderer_block(self) -> None:
        value = snapshot()
        value["conversation_comments"] = [
            {
                "id": "IC_1",
                "database_id": 1,
                "author": actor(),
                "body": "```\nhostile\n```",
                "url": "https://github.com/SecPal/.github/pull/1#issuecomment-1",
                "created_at": "2026-07-19T00:00:00Z",
                "updated_at": "2026-07-19T00:00:00Z",
                "reactions": [],
            }
        ]
        rendered = review.render_markdown(finalize_snapshot(value))
        self.assertNotIn("```\nhostile", rendered)

    def test_49_deceptive_links_and_images_are_not_trusted(self) -> None:
        rendered = review.escape_markdown("![x](https://evil.example) [login](https://evil.example)")
        self.assertNotIn("](https://evil.example)", rendered)

    def test_50_unicode_and_control_characters_are_deterministic(self) -> None:
        first = review.escape_markdown("Grüße\x00🙂")
        second = review.escape_markdown("Grüße\x00🙂")
        self.assertEqual(first, second)
        self.assertNotIn("\x00", first)

    def test_51_shell_significant_data_stays_an_argument(self) -> None:
        arguments = review.graphql_arguments("SecPal", "repo;$(touch nope)", 1, "cursor`id`", "query X { viewer { login } }")
        self.assertIn("name=repo;$(touch nope)", arguments)
        self.assertNotIn("sh", arguments[:2])

    def test_52_symlink_output_target_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_text("original")
            link = root / "output"
            link.symlink_to(target)
            with self.assertRaises(review.OutputSafetyError):
                review.atomic_write_many({link: b"replacement"})
            self.assertEqual(target.read_text(), "original")

    def test_53_partial_staging_failure_preserves_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first.write_text("old-one")
            second.write_text("old-two")
            with mock.patch.object(review, "_stage_atomic_file", side_effect=[Path(directory) / "temp", OSError("fail")]):
                with self.assertRaises(OSError):
                    review.atomic_write_many({first: b"new-one", second: b"new-two"})
            self.assertEqual(first.read_text(), "old-one")
            self.assertEqual(second.read_text(), "old-two")

    def test_54_deterministic_repeated_output(self) -> None:
        value = snapshot()
        first = review.canonical_json_bytes(value)
        second = review.canonical_json_bytes(copy.deepcopy(value))
        self.assertEqual(first, second)
        self.assertTrue(review.verify_digest(value))

    def test_output_path_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            output = root / "snapshot.json"
            alias = nested / ".." / "snapshot.json"
            with self.assertRaises(review.OutputSafetyError):
                review.prepare_outputs(snapshot(), str(output), str(alias))
            with self.assertRaises(review.OutputSafetyError):
                review.atomic_write_many({output: b"json", alias: b"markdown"})

    def test_55_stdout_mode_has_zero_persistent_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            before = list(Path(directory).iterdir())
            payloads = review.prepare_outputs(snapshot(), None, None)
            after = list(Path(directory).iterdir())
        self.assertEqual(payloads, {})
        self.assertEqual(before, after)

    def test_56_read_only_api_policy_rejects_mutations(self) -> None:
        query_arguments = review.graphql_arguments(
            "SecPal",
            ".github",
            1,
            None,
            "query X { viewer { login } }",
        )
        self.assertEqual(query_arguments[2:4], ["--hostname", "github.com"])
        review.validate_external_command(query_arguments)
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(
                ["gh", "api", "graphql", "-f", "query=query X { viewer { login } }"]
            )
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "--method",
                    "POST",
                    "repos/SecPal/.github/issues",
                ]
            )
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["gh", "pr", "view"])
        for arguments in (
            ["gh", "api", "repos/SecPal/.github/issues/1/comments", "-f", "body=write"],
            ["gh", "api", "repos/SecPal/.github/issues/1/labels", "-F", "labels[]=security"],
            ["gh", "api", "repos/SecPal/.github/issues/1", "--input", "payload.json"],
            ["gh", "api", "-X", "PATCH", "repos/SecPal/.github/issues/1"],
            ["gh", "api", "--method=DELETE", "repos/SecPal/.github/issues/1"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(review.CommandPolicyError):
                review.validate_external_command(arguments)

    def test_graphql_string_variables_cannot_trigger_field_file_reads(self) -> None:
        arguments = review.graphql_arguments(
            "SecPal",
            ".github",
            1,
            "@/etc/passwd",
            "query X($after:String) { viewer { login } }",
        )
        index = arguments.index("after=@/etc/passwd")
        self.assertEqual(arguments[index - 1], "-f")
        review.validate_external_command(arguments)

    def test_command_runner_pins_github_host(self) -> None:
        arguments = review.graphql_arguments(
            "SecPal",
            ".github",
            1,
            None,
            "query X { viewer { login } }",
        )
        with tempfile.TemporaryDirectory() as directory:
            completed = mock.Mock(returncode=0, stdout="{}", stderr="")
            with mock.patch.object(review.subprocess, "run", return_value=completed) as run:
                review.CommandRunner({"gh": fake_executable(directory, "gh")}).run(arguments)
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["GH_HOST"], "github.com")
        self.assertEqual(environment["PATH"], review.TRUSTED_COMMAND_PATH)
        self.assertTrue(Path(run.call_args.args[0][0]).is_absolute())
        self.assertEqual(run.call_args.args[0][2:4], ["--hostname", "github.com"])

    def test_command_runner_does_not_resolve_allowlisted_tools_from_inherited_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "shim-ran"
            shim = root / "git"
            shim.write_text(
                "#!/bin/sh\n"
                f": > {str(marker)!r}\n"
                f"printf '%s\\n' {HEAD!r}\n",
                encoding="utf-8",
            )
            shim.chmod(0o700)
            inherited_path = f"{root}{os.pathsep}{os.environ.get('PATH', '')}"
            with mock.patch.dict(review.os.environ, {"PATH": inherited_path}):
                review.CommandRunner().run(["git", "rev-parse", "HEAD"], allow_failure=True)
            self.assertFalse(marker.exists())

    def test_command_runner_bounds_execution_and_closes_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expired = review.subprocess.TimeoutExpired(["git", "rev-parse", "HEAD"], 1)
            with mock.patch.object(review.subprocess, "run", side_effect=expired) as run:
                with self.assertRaises(review.CommandFailure):
                    review.CommandRunner({"git": fake_executable(directory, "git")}).run(
                        ["git", "rev-parse", "HEAD"]
                    )
        self.assertEqual(run.call_args.kwargs["stdin"], review.subprocess.DEVNULL)
        self.assertEqual(
            run.call_args.kwargs["timeout"],
            review.DEFAULT_EXTERNAL_COMMAND_TIMEOUT_SECONDS,
        )

    def test_command_runner_sanitizes_git_repository_and_object_overrides(self) -> None:
        repository_overrides = {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CEILING_DIRECTORIES",
            "GIT_COMMON_DIR",
            "GIT_CONFIG",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_SYSTEM",
            "GIT_DIR",
            "GIT_DISCOVERY_ACROSS_FILESYSTEM",
            "GIT_EXEC_PATH",
            "GIT_GRAFT_FILE",
            "GIT_IMPLICIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_NAMESPACE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_PREFIX",
            "GIT_REPLACE_REF_BASE",
            "GIT_SHALLOW_FILE",
            "GIT_WORK_TREE",
        }
        poisoned_environment = {key: f"hostile-{key.lower()}" for key in repository_overrides}
        poisoned_environment |= {
            "GIT_CONFIG_KEY_0": "core.sshCommand",
            "GIT_CONFIG_VALUE_0": "hostile-command",
            "GIT_CONFIG_KEY_99": "gpg.ssh.program",
            "GIT_CONFIG_VALUE_99": "hostile-verifier",
            "GIT_NO_REPLACE_OBJECTS": "0",
            "GIT_OPTIONAL_LOCKS": "1",
            "GIT_TRACE": "/tmp/hostile-trace",
            "GIT_TRACE2_EVENT": "/tmp/hostile-trace2",
        }
        completed = mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            review.os.environ, poisoned_environment, clear=True
        ), mock.patch.object(review.subprocess, "run", return_value=completed) as run:
            review.CommandRunner({"git": fake_executable(directory, "git")}).run(
                ["git", "status", "--porcelain=v2", "--untracked-files=all"]
            )

        environment = run.call_args.kwargs["env"]
        inherited_overrides = repository_overrides | {
            "GIT_CONFIG_KEY_99",
            "GIT_CONFIG_VALUE_99",
            "GIT_TRACE",
            "GIT_TRACE2_EVENT",
        }
        self.assertEqual(sorted((inherited_overrides - {"GIT_CONFIG_COUNT"}) & environment.keys()), [])
        configured_count = int(environment["GIT_CONFIG_COUNT"])
        safe_config = {
            environment[f"GIT_CONFIG_KEY_{index}"]: environment[f"GIT_CONFIG_VALUE_{index}"]
            for index in range(configured_count)
        }
        self.assertEqual(safe_config, dict(review.SAFE_GIT_CONFIG))
        self.assertEqual(
            set(safe_config),
            {
                "core.fsmonitor",
                "gpg.program",
                "gpg.openpgp.program",
                "gpg.ssh.program",
                "gpg.x509.program",
            },
        )
        self.assertEqual(safe_config["core.fsmonitor"], "false")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")

    def test_command_runner_disables_a_configured_fsmonitor_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "fsmonitor-ran"
            hook = root / "fsmonitor-hook"
            hook.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
                "print('token')\n",
                encoding="utf-8",
            )
            hook.chmod(0o700)
            subprocess_environment = uncontrolled_git_test_environment()
            review.subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                env=subprocess_environment,
                check=True,
            )
            review.subprocess.run(
                ["git", "config", "core.fsmonitor", str(hook)],
                cwd=root,
                env=subprocess_environment,
                check=True,
            )
            review.subprocess.run(
                ["git", "status", "--porcelain=v2", "--untracked-files=all"],
                cwd=root,
                env=subprocess_environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(marker.exists())
            marker.unlink()

            with contextlib.chdir(root):
                review.CommandRunner().run(
                    ["git", "status", "--porcelain=v2", "--untracked-files=all"]
                )
            self.assertFalse(marker.exists())

    def test_command_runner_pins_the_ssh_signature_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "verifier-ran"
            verifier = root / "hostile-verifier"
            verifier.write_text(
                "#!/bin/sh\n"
                f": > \"{marker}\"\n"
                "exit 1\n",
                encoding="utf-8",
            )
            verifier.chmod(0o700)
            subprocess_environment = uncontrolled_git_test_environment()
            review.subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                env=subprocess_environment,
                check=True,
            )
            tree = review.subprocess.run(
                ["git", "hash-object", "-t", "tree", "-w", "--stdin"],
                cwd=root,
                env=subprocess_environment,
                input=b"",
                capture_output=True,
                check=True,
            ).stdout.decode().strip()
            commit = (
                f"tree {tree}\n"
                "author Reviewer <reviewer@example.com> 0 +0000\n"
                "committer Reviewer <reviewer@example.com> 0 +0000\n"
                "gpgsig -----BEGIN SSH SIGNATURE-----\n"
                " invalid\n"
                " -----END SSH SIGNATURE-----\n\n"
                "message\n"
            ).encode()
            oid = review.subprocess.run(
                ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
                cwd=root,
                env=subprocess_environment,
                input=commit,
                capture_output=True,
                check=True,
            ).stdout.decode().strip()
            review.subprocess.run(
                ["git", "config", "gpg.ssh.program", str(verifier)],
                cwd=root,
                env=subprocess_environment,
                check=True,
            )
            allowed_signers = root / "allowed-signers"
            allowed_signers.write_text("", encoding="utf-8")
            review.subprocess.run(
                ["git", "config", "gpg.ssh.allowedSignersFile", str(allowed_signers)],
                cwd=root,
                env=subprocess_environment,
                check=True,
            )
            review.subprocess.run(
                ["git", "verify-commit", "--raw", oid],
                cwd=root,
                env=subprocess_environment,
                check=False,
            )
            self.assertTrue(marker.exists())
            marker.unlink()

            with contextlib.chdir(root):
                review.CommandRunner().run(
                    ["git", "verify-commit", "--raw", oid],
                    allow_failure=True,
                )
            self.assertFalse(marker.exists())

    def test_disabled_rule_sources_are_not_called(self) -> None:
        configuration = config()
        policy = configuration["check_policy"] | {
            "require_ruleset_evidence": False,
            "require_branch_protection_evidence": False,
        }

        class Client:
            owner = "SecPal"
            name = ".github"
            budget = review.Budget(configuration)

            def rest(self, *_: Any, **__: Any) -> Any:
                raise AssertionError("disabled evidence source was called")

        applicable, required, sources = review._capture_rules(Client(), "main", policy)
        self.assertEqual(required, [])
        self.assertEqual(sources, [])
        self.assertEqual(applicable["rulesets"], [])

    def test_57_no_polling_or_retries(self) -> None:
        calls = 0

        def fail(_: str | None) -> review.Page:
            nonlocal calls
            calls += 1
            raise review.BlockedError("BLOCKED_INCOMPLETE_REVIEW_STATE", "failure", "reviews", None)

        with self.assertRaises(review.BlockedError):
            review.collect_pages("reviews", fail, review.Budget(config()))
        self.assertEqual(calls, 1)

    def test_58_git_write_commands_are_rejected(self) -> None:
        for command in ("push", "commit", "checkout", "switch", "reset", "clean", "stash"):
            with self.subTest(command=command), self.assertRaises(review.CommandPolicyError):
                review.validate_external_command(["git", command])

    def test_git_allowlist_rejects_unexpected_read_subcommand_arguments(self) -> None:
        review.validate_external_command(["git", "cat-file", "commit", HEAD])
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["git", "show", "--output=/tmp/unexpected", "HEAD"])
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["git", "cat-file", "commit", "HEAD"])
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["git", "status", "--porcelain=v2", "--ignored"])

    def test_59_review_request_operations_are_rejected(self) -> None:
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["gh", "pr", "review", "1"])
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["gh", "pr", "ready", "1"])

    def test_60_merge_operations_are_rejected(self) -> None:
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["gh", "pr", "merge", "1"])

    def test_configuration_schema_and_identity_aliases(self) -> None:
        review.validate_config(config())
        broken = config()
        broken["reviewer_identities"][0]["canonical_identity"] = ""
        with self.assertRaises(review.ContractError):
            review.validate_config(broken)

    def test_reviewer_database_ids_must_be_globally_unique(self) -> None:
        candidate = config()
        candidate["reviewer_identities"][0]["database_ids"] = [42]
        candidate["reviewer_identities"][1]["database_ids"] = [42]
        with self.assertRaisesRegex(review.ContractError, "alias is duplicated"):
            review.validate_config(candidate)
        with self.assertRaisesRegex(review.ContractError, "alias is duplicated"):
            review.index_reviewer_identities(candidate)

    def test_reviewer_string_aliases_must_be_unique_across_namespaces(self) -> None:
        string_namespaces = ("graphql_aliases", "rest_event_aliases", "node_ids")
        for first_namespace in string_namespaces:
            for second_namespace in string_namespaces:
                with self.subTest(first=first_namespace, second=second_namespace):
                    candidate = config()
                    candidate["reviewer_identities"][0][first_namespace] = ["SHARED_ALIAS"]
                    candidate["reviewer_identities"][1][second_namespace] = ["SHARED_ALIAS"]
                    with self.assertRaisesRegex(review.ContractError, "alias is duplicated"):
                        review.validate_config(candidate)
                    with self.assertRaisesRegex(review.ContractError, "alias is duplicated"):
                        review.index_reviewer_identities(candidate)

    def test_one_reviewer_may_share_an_alias_across_namespaces(self) -> None:
        string_namespaces = ("graphql_aliases", "rest_event_aliases", "node_ids")
        for first_namespace in string_namespaces:
            for second_namespace in string_namespaces:
                with self.subTest(first=first_namespace, second=second_namespace):
                    candidate = config()
                    candidate["reviewer_identities"][0][first_namespace] = ["SHARED_ALIAS"]
                    candidate["reviewer_identities"][0][second_namespace] = ["SHARED_ALIAS"]
                    review.validate_config(candidate)
                    self.assertEqual(
                        review.index_reviewer_identities(candidate)["SHARED_ALIAS"],
                        "copilot",
                    )

    def test_unenforced_local_validation_commands_are_rejected(self) -> None:
        candidate = config()
        candidate.setdefault("required_local_validation", []).append(
            {"name": "must-run", "command": ["false"]}
        )
        with self.assertRaisesRegex(review.ContractError, "required_local_validation"):
            review.validate_config(candidate)

    def test_nested_snapshot_schema_is_enforced(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record()]
        value["reviews"][0]["unexpected"] = True
        value = review.attach_digest(value)
        with self.assertRaises(review.ContractError):
            review.validate_snapshot(value)

    def test_digest_excludes_only_digest_field(self) -> None:
        value = snapshot()
        digest = value["snapshot_digest"]
        value["snapshot_digest"] = "f" * 64
        self.assertEqual(review.compute_digest(value), digest)
        value["snapshot_digest_algorithm"] = "sha512"
        self.assertNotEqual(review.compute_digest(value), digest)

    def test_atomic_output_mode_is_0600(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            review.atomic_write_many({path: b"{}\n"})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_unvalidated_non_github_url_is_not_a_link(self) -> None:
        self.assertFalse(review.trusted_github_url("https://evil.example/SecPal/.github"))
        self.assertFalse(review.trusted_github_url("https://github.com:invalid/path"))
        self.assertTrue(review.trusted_github_url("https://github.com/SecPal/.github/pull/1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
