#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "secpal-pr-review.py"
SPEC = importlib.util.spec_from_file_location("secpal_pr_review", HELPER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load helper at {HELPER}")
review = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)

HEAD = "a" * 40
BASE = "b" * 40
PARENT = "c" * 40


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
        "required_local_validation": [{"name": "unit", "command": ["python3", "-m", "unittest"]}],
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
        "maximum_comments": 10000,
        "maximum_reactions": 10000,
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
    name: str = "tests", status: str = "COMPLETED", conclusion: str | None = "SUCCESS"
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
            "state": "OPEN",
            "is_draft": False,
            "is_merged": False,
            "mergeable": "MERGEABLE",
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
            "labels": [],
            "requested_reviewers": [],
            "requested_teams": [],
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
            "rulesets": [{"type": "required_status_checks", "required_checks": [{"context": "tests", "integration_id": 1}]}],
            "branch_protection": {"contexts": ["tests"], "checks": [{"context": "tests", "app_id": 1}]},
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
                "maximum_comments": 10000,
                "maximum_reactions": 10000,
            },
            "fully_paginated_connections": [
                {"connection": "reviews", "pages": 1, "items": 0},
                {"connection": "review_threads", "pages": 1, "items": 0},
            ],
            "warnings": [],
            "blocked_reason": None,
        },
    }
    return review.attach_digest(value)


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
            ("git", "cat-file", "-e", f"{HEAD}^{{commit}}"): review.CommandResult(0, "", ""),
            ("git", "verify-commit", "--raw", HEAD): review.CommandResult(
                0, "", 'Good "git" signature for aroviqen with ED25519 key SHA256:test\n'
            ),
        }
        result = defaults.get(key, review.CommandResult(2, "", f"unexpected command: {arguments}"))
        if result.returncode and not allow_failure:
            raise review.CommandFailure(arguments, result)
        return result


class SnapshotAndPaginationTests(unittest.TestCase):
    def test_01_zero_findings(self) -> None:
        result = review.verify_snapshot_gate(snapshot(), config())
        self.assertEqual(result["raw_review_state"]["unresolved_threads"], 0)
        self.assertFalse(result["raw_review_state"]["requested_changes"])

    def test_02_informational_review_only(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record()]
        value = review.attach_digest(value)
        result = review.verify_snapshot_gate(value, config())
        self.assertEqual(result["raw_review_state"]["reviews"], 1)
        self.assertTrue(result["technical_classification_required"])

    def test_03_resolved_and_unresolved_threads(self) -> None:
        value = snapshot()
        value["review_threads"] = [thread("T1", resolved=True), thread("T2", resolved=False)]
        value = review.attach_digest(value)
        result = review.verify_snapshot_gate(value, config())
        self.assertEqual(result["raw_review_state"]["resolved_threads"], 1)
        self.assertEqual(result["raw_review_state"]["unresolved_threads"], 1)

    def test_04_outdated_thread_is_retained(self) -> None:
        value = snapshot()
        value["review_threads"] = [thread(outdated=True)]
        review.validate_snapshot(review.attach_digest(value))
        self.assertTrue(value["review_threads"][0]["is_outdated"])

    def test_05_requested_changes_review(self) -> None:
        value = snapshot()
        value["reviews"] = [review_record("CHANGES_REQUESTED")]
        value["pull_request"]["review_decision"] = "CHANGES_REQUESTED"
        result = review.verify_snapshot_gate(review.attach_digest(value), config())
        self.assertTrue(result["raw_review_state"]["requested_changes"])

    def test_06_unresolved_human_thread(self) -> None:
        value = snapshot()
        value["review_threads"] = [thread(comments=[review_comment(login="human")])]
        result = review.verify_snapshot_gate(review.attach_digest(value), config())
        self.assertEqual(result["raw_review_state"]["unresolved_threads"], 1)

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
        value = review.attach_digest(value)
        self.assert_blocker(review.verify_local_against_snapshot(value, config(), FakeGitRunner(), None), "BLOCKED_HEAD_MOVED")

    def test_28_pr_head_mismatch(self) -> None:
        self.assert_blocker(
            review.verify_local_against_snapshot(snapshot(), config(), FakeGitRunner(), "d" * 40),
            "BLOCKED_HEAD_MOVED",
        )

    def test_29_head_movement_during_capture(self) -> None:
        with self.assertRaises(review.BlockedError):
            review.ensure_unchanged_head(HEAD, "d" * 40)

    def test_30_unexpected_base_branch(self) -> None:
        value = snapshot()
        value["pull_request"]["base_ref"] = "develop"
        value = review.attach_digest(value)
        self.assert_blocker(review.verify_local_against_snapshot(value, config(), FakeGitRunner(), None), "BLOCKED_UNSAFE_GITHUB_STATE")

    def test_31_unavailable_commit_object(self) -> None:
        runner = FakeGitRunner()
        runner.set(["git", "cat-file", "-e", f"{HEAD}^{{commit}}"], 1, stderr="missing")
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


class SecurityAndOutputTests(unittest.TestCase):
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
        rendered = review.render_markdown(review.attach_digest(value))
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

    def test_55_stdout_mode_has_zero_persistent_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            before = list(Path(directory).iterdir())
            payloads = review.prepare_outputs(snapshot(), None, None)
            after = list(Path(directory).iterdir())
        self.assertEqual(payloads, {})
        self.assertEqual(before, after)

    def test_56_read_only_api_policy_rejects_mutations(self) -> None:
        review.validate_external_command(["gh", "api", "graphql", "-f", "query=query X { viewer { login } }"])
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["gh", "api", "--method", "POST", "repos/SecPal/.github/issues"])

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
        with self.assertRaises(review.CommandPolicyError):
            review.validate_external_command(["git", "show", "--output=/tmp/unexpected", "HEAD"])
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
