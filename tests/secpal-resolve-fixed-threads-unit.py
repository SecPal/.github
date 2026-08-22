#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Sequence
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/secpal-resolve-fixed-threads.py"
SPEC = importlib.util.spec_from_file_location("secpal_resolve_fixed_threads", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from secpal_work_graph import github as work_graph_github  # noqa: E402
from secpal_work_graph import model as work_graph_model  # noqa: E402


class FakeGh:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, arguments: Sequence[str]) -> dict[str, Any]:
        self.calls.append(list(arguments))
        if not self.responses:
            raise AssertionError("unexpected gh call")
        return self.responses.pop(0)


class FakeGit:
    def __init__(
        self,
        *,
        expected_head: str,
        reviewed_head: str,
        tree: str,
        receipt_digest: str,
        repository: str = "SecPal/api",
        signature_valid: bool = True,
    ) -> None:
        self.expected_head = expected_head
        self.reviewed_head = reviewed_head
        self.tree = tree
        self.receipt_digest = receipt_digest
        self.repository = repository
        self.signature_valid = signature_valid
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        repository_root: Path,
        arguments: Sequence[str],
        *,
        allow_failure: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        del repository_root, allow_failure
        call = tuple(arguments)
        self.calls.append(call)
        if call == ("remote", "get-url", "origin"):
            stdout = f"https://github.com/{self.repository}.git\n"
        elif call == ("rev-parse", "HEAD"):
            stdout = f"{self.expected_head}\n"
        elif call == ("rev-parse", f"{self.expected_head}^{{tree}}"):
            stdout = f"{self.tree}\n"
        elif call == ("rev-list", "--parents", "-n", "1", self.expected_head):
            stdout = f"{self.expected_head} {self.reviewed_head}\n"
        elif call[0:2] == ("show", "-s"):
            stdout = f"{self.receipt_digest}\n"
        elif call == ("cat-file", "commit", self.expected_head):
            stdout = (
                f"tree {self.tree}\nparent {self.reviewed_head}\n"
                "gpgsig -----BEGIN SSH SIGNATURE-----\n signature\n"
                " -----END SSH SIGNATURE-----\n\nmessage\n"
            )
        elif call == ("verify-commit", "--raw", self.expected_head):
            if not self.signature_valid:
                return subprocess.CompletedProcess(call, 1, "", "bad signature")
            stdout = 'Good "git" signature for fixture\n'
        else:
            raise AssertionError(f"unexpected git call: {call}")
        return subprocess.CompletedProcess(call, 0, stdout, "")


def resolve_response(thread_id: str) -> dict[str, Any]:
    return {
        "data": {
            "resolveReviewThread": {
                "thread": {"id": thread_id, "isResolved": True}
            }
        }
    }


def target_response(
    thread_id: str,
    *,
    head: str = "a" * 40,
    repository: str = "SecPal/api",
    number: int = 123,
    state: str = "OPEN",
    resolved: bool = False,
    outdated: bool = False,
    comments: list[tuple[str, str, str | None]] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "data": {
            "node": {
                "__typename": "PullRequestReviewThread",
                "id": thread_id,
                "isResolved": resolved,
                "isOutdated": outdated,
                "pullRequest": {
                    "number": number,
                    "state": state,
                    "headRefOid": head,
                    "repository": {"nameWithOwner": repository},
                },
                "comments": {
                    "nodes": [
                        {
                            "id": comment_id,
                            "body": body,
                            "replyTo": (
                                {"id": reply_to_id}
                                if reply_to_id is not None
                                else None
                            ),
                        }
                        for comment_id, body, reply_to_id in (comments or [])
                    ],
                    "pageInfo": {
                        "hasNextPage": has_next_page,
                        "endCursor": end_cursor,
                    },
                },
            }
        }
    }


def work_graph_issue_response(
    number: int,
    *,
    blocked_by: tuple[int, ...] = (),
    labels_have_next_page: bool = False,
) -> Any:
    def references(numbers: tuple[int, ...]) -> list[dict[str, Any]]:
        return [
            {"number": item, "repository": {"nameWithOwner": "SecPal/api"}}
            for item in numbers
        ]

    issue = {
        "number": number,
        "title": f"Issue {number}",
        "url": f"https://github.com/SecPal/api/issues/{number}",
        "state": "OPEN",
        "stateReason": None,
        "body": "## Acceptance Criteria\n\n- [ ] Tracked responsibility",
        "repository": {"nameWithOwner": "SecPal/api"},
        "parent": None,
        "labels": {
            "nodes": [],
            "pageInfo": {
                "hasNextPage": labels_have_next_page,
                "endCursor": "labels-next" if labels_have_next_page else None,
            },
        },
        "subIssues": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
        "blockedBy": {
            "nodes": references(blocked_by),
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
        "blocking": {"totalCount": 0},
        "closedByPullRequestsReferences": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }
    return work_graph_github.GraphQLResponse(
        {"repository": {"issue": issue}},
        (),
    )


def work_graph_page_response(
    connection: str,
    *,
    has_next_page: bool,
    end_cursor: str | None,
) -> Any:
    return work_graph_github.GraphQLResponse(
        {
            "repository": {
                "issue": {
                    connection: {
                        "nodes": [],
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    }
                }
            }
        },
        (),
    )


def expected_thread_state(
    thread_id: str,
    comments: list[tuple[str, str, str | None]] | None = None,
    *,
    resolved: bool = False,
    outdated: bool = False,
) -> Any:
    states = [
        MODULE.ThreadCommentState(
            comment_id=comment_id,
            body_digest=MODULE._body_digest(body),
            reply_to_id=reply_to_id,
        )
        for comment_id, body, reply_to_id in (comments or [])
    ]
    return MODULE.ExpectedThreadState(
        thread_id=thread_id,
        is_resolved=resolved,
        is_outdated=outdated,
        comments=tuple(sorted(states, key=lambda item: item.comment_id)),
    )


def resolve_threads(
    repository: str,
    number: int,
    expected_head: str,
    thread_ids: list[str],
    *,
    apply: bool,
    runner: Any = MODULE._run_gh,
    reviewed_comments: dict[str, list[tuple[str, str, str | None]]] | None = None,
    expected_targets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    immutable_thread_ids = tuple(thread_ids)
    if expected_targets is None:
        comments_by_thread = reviewed_comments or {}
        expected_targets = {
            thread_id: expected_thread_state(
                thread_id,
                comments_by_thread.get(thread_id),
            )
            for thread_id in immutable_thread_ids
        }
    return MODULE.resolve_threads(
        repository,
        number,
        expected_head,
        immutable_thread_ids,
        apply=apply,
        expected_targets=expected_targets,
        reviewed_state_digest="c" * 64,
        validation_evidence_digest="d" * 64,
        eligibility_evidence_digest="e" * 64,
        runner=runner,
    )


def reviewed_state_payload(
    thread_id: str,
    comments: list[tuple[str, str, str | None]],
    *,
    resolved: bool = False,
    outdated: bool = False,
) -> dict[str, Any]:
    feedback = {
        "pull_request_reactions": [],
        "reviews": [],
        "conversation_comments": [],
        "threads": [
            {
                "node_id": thread_id,
                "is_resolved": resolved,
                "is_outdated": outdated,
                "comments": [
                    {
                        "node_id": comment_id,
                        "body_digest": MODULE._body_digest(body),
                        "actor": {
                            "login": "reviewer",
                            "node_id": "USER_reviewer",
                            "database_id": 7,
                        },
                        "reply_to_id": reply_to_id,
                        "reactions": [],
                    }
                    for comment_id, body, reply_to_id in comments
                ],
            }
        ],
    }
    identity = {
        "repository": "SecPal/api",
        "pull_request_number": 123,
        "head_sha": "a" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "pr_state": "OPEN",
    }
    return {
        "schema_version": "1.0",
        **identity,
        **feedback,
        "feedback_digest": MODULE._digest_json(feedback),
        "state_digest": MODULE._digest_json({**identity, "feedback": feedback}),
    }


def validation_attestation_payload(
    reviewed: dict[str, Any],
    eligibility_evidence_digest: str = "e" * 64,
) -> dict[str, Any]:
    binding = MODULE._validation_registry_binding(
        MODULE._load_repository_entry(reviewed["repository"])
    )
    manual_gate_evidence = [
        {
            "gate": gate,
            "satisfied": True,
            "evidence": f"Verified integration evidence {index}",
        }
        for index, gate in enumerate(binding["manual_gates"], start=1)
    ]
    receipt_fields = {
        "schema_version": "1.0",
        "kind": "VALIDATION_RECEIPT",
        "repository": reviewed["repository"],
        "head_sha": reviewed["head_sha"],
        "validated_tree_sha": "f" * 40,
        "registry_digest": MODULE._digest_json(binding),
        "command_set_digest": MODULE._digest_json(binding["validation"]),
        "successful_result": True,
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "manual_gate_evidence": manual_gate_evidence,
        "eligibility_evidence_digest": eligibility_evidence_digest,
    }
    fields = {
        "schema_version": "1.0",
        "repository": reviewed["repository"],
        "head_sha": "c" * 40,
        "registry_digest": MODULE._digest_json(binding),
        "command_set_digest": MODULE._digest_json(binding["validation"]),
        "successful_result": True,
        "reviewed_head_sha": reviewed["head_sha"],
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "validated_tree_sha": "f" * 40,
        "validation_receipt_digest": MODULE._digest_json(receipt_fields),
        "manual_gate_evidence": manual_gate_evidence,
        "eligibility_evidence_digest": eligibility_evidence_digest,
    }
    return {**fields, "attestation_digest": MODULE._digest_json(fields)}


def validation_receipt_payload(reviewed: dict[str, Any]) -> dict[str, Any]:
    binding = MODULE._validation_registry_binding(
        MODULE._load_repository_entry(reviewed["repository"])
    )
    manual_gate_evidence = [
        {
            "gate": gate,
            "satisfied": True,
            "evidence": f"Verified integration evidence {index}",
        }
        for index, gate in enumerate(binding["manual_gates"], start=1)
    ]
    fields = {
        "schema_version": "1.0",
        "kind": "VALIDATION_RECEIPT",
        "repository": reviewed["repository"],
        "head_sha": reviewed["head_sha"],
        "validated_tree_sha": "f" * 40,
        "registry_digest": MODULE._digest_json(binding),
        "command_set_digest": MODULE._digest_json(binding["validation"]),
        "successful_result": True,
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "manual_gate_evidence": manual_gate_evidence,
    }
    return {**fields, "receipt_digest": MODULE._digest_json(fields)}


def eligibility_payload(
    reviewed: dict[str, Any],
    thread_ids: Sequence[str],
) -> dict[str, Any]:
    fields = {
        "schema_version": "1.1",
        "repository": reviewed["repository"],
        "pull_request_number": reviewed["pull_request_number"],
        "reviewed_head_sha": reviewed["head_sha"],
        "reviewed_state_digest": reviewed["state_digest"],
        "eligible_threads": [
            {
                "thread_id": thread_id,
                "classification": "VALID_ACTIONABLE",
                "disposition": "CORRECTED_AND_VERIFIED",
                "finding_ids": [f"finding-{index}"],
                "evidence_digest": f"{index:x}" * 64,
                "follow_up": None,
            }
            for index, thread_id in enumerate(thread_ids, start=1)
        ],
    }
    return fields


class ResolveFixedThreadsTests(TestCase):
    def test_preflight_rejects_insufficient_thread_budget_before_first_write(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh([target_response(first), target_response(second)])
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=3,
            maximum_comments=20,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "thread limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [first, second],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 2)

    def test_changed_target_comments_block_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        initial = [("PRRC_root", "original", None)]
        changed_comment_sets = [
            [("PRRC_root", "edited", None)],
            [
                ("PRRC_root", "original", None),
                ("PRRC_reply", "new reply", "PRRC_root"),
            ],
            [("PRRC_root", "original", "PRRC_other")],
            [],
        ]

        for changed in changed_comment_sets:
            with self.subTest(changed=changed):
                fake = FakeGh(
                    [
                        target_response(thread_id, comments=initial),
                        target_response(thread_id, comments=changed),
                        target_response(thread_id, comments=changed),
                    ]
                )

                result = resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    [thread_id],
                    apply=True,
                    runner=fake,
                    reviewed_comments={thread_id: initial},
                )

                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["resolved"], [])
                self.assertEqual(result["failed"][0]["phase"], "recheck")
                self.assertIn(
                    "target thread changed",
                    result["failed"][0]["error"],
                )
                self.assertEqual(len(fake.calls), 3)

    def test_changed_outdated_state_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, outdated=False),
                target_response(thread_id, outdated=True),
                target_response(thread_id, outdated=True),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertIn("target thread changed", result["failed"][0]["error"])
        self.assertEqual(len(fake.calls), 3)

    def test_preflight_rejects_insufficient_comment_budget_before_first_write(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        comments = [
            ("PRRC_root", "root", None),
            ("PRRC_reply", "reply", "PRRC_root"),
        ]
        fake = FakeGh([target_response(thread_id, comments=comments)])
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=20,
            maximum_comments=3,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "comment limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                reviewed_comments={thread_id: comments},
            )

        self.assertEqual(len(fake.calls), 1)

    def test_preflight_rejects_insufficient_api_budget_before_first_write(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id)])
        limits = mock.Mock(
            maximum_api_calls=2,
            maximum_threads=20,
            maximum_comments=20,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "API call limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

    def test_preflight_uses_observed_sparse_page_counts_before_first_write(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh(
            [
                target_response(
                    first,
                    comments=[("PRRC_first", "first", None)],
                    has_next_page=True,
                    end_cursor="initial-first-page",
                ),
                target_response(first),
                target_response(second),
                target_response(
                    first,
                    comments=[("PRRC_first", "first", None)],
                    has_next_page=True,
                    end_cursor="recheck-first-page",
                ),
                target_response(first),
                resolve_response(first),
                target_response(second),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=7,
            maximum_threads=20,
            maximum_comments=20,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "API call limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [first, second],
                apply=True,
                runner=fake,
                reviewed_comments={
                    first: [("PRRC_first", "first", None)],
                },
            )

        self.assertEqual(len(fake.calls), 3)

    def test_target_comment_pagination_is_stable_across_recheck(self) -> None:
        thread_id = "PRRT_exampleOne"
        first_page = [
            (f"PRRC_comment{index}", f"body {index}", None)
            for index in range(100)
        ]
        second_page = [("PRRC_comment100", "body 100", "PRRC_comment0")]
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="initial-1",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="recheck-1",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="recheck-2",
                ),
                target_response(thread_id, comments=second_page),
                resolve_response(thread_id),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=10,
            maximum_comments=400,
        )

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=limits,
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                reviewed_comments={thread_id: [*first_page, *second_page]},
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(len(fake.calls), 7)
        self.assertIn("commentsAfter=initial-1", fake.calls[1])
        self.assertIn("commentsAfter=recheck-1", fake.calls[3])
        self.assertIn("commentsAfter=recheck-2", fake.calls[5])

    def test_second_recheck_projection_detects_earlier_page_edit(self) -> None:
        thread_id = "PRRT_exampleOne"
        first_page = [
            (f"PRRC_comment{index}", f"body {index}", None)
            for index in range(100)
        ]
        second_page = [("PRRC_comment100", "body 100", "PRRC_comment0")]
        edited_first_page = [
            (
                comment_id,
                "edited during pagination" if index == 0 else body,
                reply_to_id,
            )
            for index, (comment_id, body, reply_to_id) in enumerate(first_page)
        ]
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="initial",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="recheck-first-pass",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=edited_first_page,
                    has_next_page=True,
                    end_cursor="recheck-second-pass",
                ),
                target_response(thread_id, comments=second_page),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=20,
            maximum_comments=500,
        )

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=limits,
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                reviewed_comments={thread_id: [*first_page, *second_page]},
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertIn("changed while rechecking", result["failed"][0]["error"])
        self.assertEqual(len(fake.calls), 6)

    def test_reviewed_comment_state_mismatch_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        reviewed = [("PRRC_root", "reviewed body", None)]
        changed = [("PRRC_root", "new unseen body", None)]
        fake = FakeGh([target_response(thread_id, comments=changed)])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "differs from reviewed feedback",
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                expected_targets={
                    thread_id: expected_thread_state(thread_id, reviewed),
                },
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

    def test_callable_rejects_duplicate_thread_ids_before_reading(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "must be unique"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id, thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_request_requires_immutable_thread_id_tuple(self) -> None:
        with self.assertRaisesRegex(MODULE.ResolutionError, "immutable tuple"):
            MODULE.validate_request(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_exampleOne"],
                False,
            )

    def test_callable_rejects_malformed_request_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "positive"):
            resolve_threads(
                "SecPal/api",
                0,
                "not-an-oid",
                ["not-a-thread"],
                apply=False,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_callable_rejects_non_boolean_apply_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "apply must be boolean"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_exampleOne"],
                apply="yes",
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_unregistered_repository_is_rejected_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "unsupported repository"):
            resolve_threads(
                "Example/unregistered",
                123,
                "a" * 40,
                ["PRRT_exampleOne"],
                apply=True,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_repository_registry_must_match_authoritative_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "repositories.json"
            registry.write_text(
                json.dumps(
                    {
                        "repositories": [
                            {
                                "repository": "SecPal/api",
                                "maximum_api_calls": 200,
                                "maximum_threads": 500,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(MODULE, "REGISTRY_PATH", registry),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "registry is invalid",
                ),
            ):
                MODULE.load_repository_limits("SecPal/api")

    def test_registry_contract_keeps_resolution_ci_independent(self) -> None:
        registry = json.loads(MODULE.REGISTRY_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            registry["fixed_thread_resolution"],
            MODULE.FIXED_THREAD_RESOLUTION_CONTRACT,
        )
        self.assertEqual(
            registry["fixed_thread_resolution"]["allowed_github_operations"],
            [
                "READ_NAMED_REVIEW_THREAD",
                "READ_AUTHENTICATED_FOLLOW_UP_WORK_GRAPH",
                "RESOLVE_NAMED_REVIEW_THREAD",
            ],
        )
        self.assertIn(
            "MERGE_READINESS",
            registry["fixed_thread_resolution"]["prohibited_hosted_reads"],
        )

    def test_resolver_rejects_registry_without_resolution_contract(self) -> None:
        registry = json.loads(MODULE.REGISTRY_PATH.read_text(encoding="utf-8"))
        registry.pop("fixed_thread_resolution")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repositories.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with (
                mock.patch.object(MODULE, "REGISTRY_PATH", path),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "fixed-thread resolution registry contract is invalid",
                ),
            ):
                MODULE.load_repository_limits("SecPal/.github")

    def test_dry_run_reads_once_and_does_not_mutate(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id)])

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=False,
            runner=fake,
        )

        self.assertEqual(result["pending"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(fake.calls), 1)
        query_argument = next(
            argument
            for argument in fake.calls[0]
            if argument.startswith("query=")
        )
        for expected_fragment in (
            "pullRequest",
            "isOutdated",
            "comments(first: 100",
            "body",
            "replyTo",
        ):
            self.assertIn(expected_fragment, query_argument)

    def test_apply_resolves_each_open_target_once(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
                target_response(second),
                target_response(second),
                resolve_response(second),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [first, second])
        self.assertEqual(len(fake.calls), 8)

    def test_tracked_follow_up_is_verified_before_final_target_recheck(self) -> None:
        thread_id = "PRRT_exampleOne"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        canonical_manifest = MODULE._canonical_json_bytes(manifest)
        eligibility = MODULE.EligibilityEvidence(
            hashlib.sha256(canonical_manifest).hexdigest(),
            canonical_manifest,
        )
        fake = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
                resolve_response(thread_id),
            ]
        )
        verifier = mock.Mock()

        result = MODULE.resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            reviewed_state_digest="c" * 64,
            validation_evidence_digest="d" * 64,
            eligibility_evidence_digest=eligibility.evidence_digest,
            eligibility_evidence=eligibility,
            follow_up_verifier=verifier,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [thread_id])
        verifier.assert_called_once_with(identity, mock.ANY)
        self.assertEqual(len(fake.calls), 4)

        refused = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
            ]
        )
        result = MODULE.resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            reviewed_state_digest="c" * 64,
            validation_evidence_digest="d" * 64,
            eligibility_evidence_digest=eligibility.evidence_digest,
            eligibility_evidence=eligibility,
            follow_up_verifier=mock.Mock(
                side_effect=MODULE.ResolutionError("follow-up issue is closed")
            ),
            runner=refused,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"][0]["phase"], "follow-up")
        self.assertEqual(len(refused.calls), 1)

    def test_tracked_follow_up_rechecks_target_after_verification(self) -> None:
        thread_id = "PRRT_exampleOne"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        canonical_manifest = MODULE._canonical_json_bytes(manifest)
        eligibility = MODULE.EligibilityEvidence(
            hashlib.sha256(canonical_manifest).hexdigest(),
            canonical_manifest,
        )
        drifted = False
        mutation_calls = 0

        def runner(arguments: Sequence[str]) -> dict[str, Any]:
            nonlocal mutation_calls
            query = next(
                argument.removeprefix("query=")
                for argument in arguments
                if argument.startswith("query=")
            )
            if query == MODULE.TARGET_QUERY:
                return target_response(
                    thread_id,
                    head="b" * 40 if drifted else "a" * 40,
                )
            if query == MODULE.RESOLVE_MUTATION:
                mutation_calls += 1
                return resolve_response(thread_id)
            raise AssertionError("unexpected GraphQL document")

        def verifier(_identity: Any, *_args: Any) -> None:
            nonlocal drifted
            drifted = True

        result = MODULE.resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            reviewed_state_digest="c" * 64,
            validation_evidence_digest="d" * 64,
            eligibility_evidence_digest=eligibility.evidence_digest,
            eligibility_evidence=eligibility,
            follow_up_verifier=verifier,
            runner=runner,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(mutation_calls, 0)

    def test_resolution_succeeds_for_every_hosted_check_condition_without_reading_it(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        for condition in ("PENDING", "FAILED", None, "OMITTED"):
            with self.subTest(condition=condition):
                responses = [
                    target_response(thread_id),
                    target_response(thread_id),
                    target_response(thread_id),
                    resolve_response(thread_id),
                ]
                if condition != "OMITTED":
                    for response in responses[:3]:
                        response["data"]["node"]["pullRequest"][
                            "hostedChecks"
                        ] = condition
                fake = FakeGh(responses)

                result = resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    [thread_id],
                    apply=True,
                    runner=fake,
                )

                self.assertEqual(result["resolved"], [thread_id])
                serialized_calls = "\n".join(" ".join(call) for call in fake.calls)
                for prohibited in (
                    "checkSuites",
                    "statusCheckRollup",
                    "mergeable",
                    "mergeStateStatus",
                    "branchProtectionRule",
                    "codeScanningAlerts",
                    "workflowRuns",
                ):
                    self.assertNotIn(prohibited, serialized_calls)

    def test_already_resolved_target_is_idempotent(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, resolved=True),
                target_response(thread_id, resolved=True),
                target_response(thread_id, resolved=True),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
            expected_targets={
                thread_id: expected_thread_state(thread_id, resolved=True),
            },
        )

        self.assertEqual(result["already_resolved"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(fake.calls), 3)

    def test_initially_resolved_target_is_rechecked_before_success(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, resolved=True),
                target_response(thread_id, resolved=False),
                target_response(thread_id, resolved=False),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
            expected_targets={
                thread_id: expected_thread_state(thread_id, resolved=True),
            },
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["already_resolved"], [])
        self.assertEqual(result["failed"][0]["thread_id"], thread_id)
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(len(fake.calls), 3)

    def test_cli_requires_reviewed_state_digest_and_validation_evidence(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.parse_args(
                [
                    "--repo",
                    "SecPal/api",
                    "--pr",
                    "123",
                    "--expected-head",
                    "a" * 40,
                    "--reviewed-state",
                    "reviewed.json",
                    "--thread-id",
                    "PRRT_exampleOne",
                ]
            )

    def test_callable_requires_validation_binding_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "validation evidence digest is required",
        ):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ("PRRT_exampleOne",),
                apply=True,
                expected_targets={
                    "PRRT_exampleOne": expected_thread_state(
                        "PRRT_exampleOne"
                    ),
                },
                reviewed_state_digest="c" * 64,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_callable_requires_reviewed_target_state_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "reviewed target state must cover",
        ):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ("PRRT_exampleOne",),
                apply=True,
                reviewed_state_digest="c" * 64,
                validation_evidence_digest="d" * 64,
                eligibility_evidence_digest="e" * 64,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_reviewed_state_loader_binds_target_comment_digests(self) -> None:
        thread_id = "PRRT_exampleOne"
        comments = [("PRRC_root", "reviewed body", None)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(
                json.dumps(reviewed_state_payload(thread_id, comments)),
                encoding="utf-8",
            )

            reviewed = MODULE.load_reviewed_state(
                path,
                "SecPal/api",
                123,
                reviewed_state_payload(thread_id, comments)["state_digest"],
                (thread_id,),
            )

        self.assertEqual(
            reviewed.targets[thread_id],
            expected_thread_state(thread_id, comments),
        )

    def test_reviewed_state_loader_binds_resolution_state(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(
            thread_id,
            [("PRRC_root", "reviewed body", None)],
            resolved=True,
            outdated=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            reviewed = MODULE.load_reviewed_state(
                path,
                "SecPal/api",
                123,
                payload["state_digest"],
                (thread_id,),
            )

        self.assertEqual(
            reviewed.targets[thread_id],
            expected_thread_state(
                thread_id,
                [("PRRC_root", "reviewed body", None)],
                resolved=True,
                outdated=True,
            ),
        )

    def test_reopened_thread_after_reviewed_capture_blocks_before_mutation(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, resolved=False)])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "differs from reviewed feedback",
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                expected_targets={
                    thread_id: expected_thread_state(thread_id, resolved=True),
                },
            )

        self.assertEqual(len(fake.calls), 1)

    def test_outdated_change_after_reviewed_capture_remains_allowed_and_stable(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, outdated=True),
                target_response(thread_id, outdated=True),
                target_response(thread_id, outdated=True),
                resolve_response(thread_id),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(len(fake.calls), 4)

    def test_reviewed_state_digest_drift_blocks_before_validation_or_github(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "does not match the captured digest",
            ):
                MODULE.load_reviewed_state(
                    path,
                    "SecPal/api",
                    123,
                    "0" * 64,
                    (thread_id,),
                )

    def test_validation_attestation_binds_fix_head_and_reviewed_state(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attestation.json"
            path.write_text(json.dumps(attestation), encoding="utf-8")

            digest = MODULE.load_validation_evidence(
                path,
                "SecPal/api",
                "c" * 40,
                reviewed,
            )

        self.assertEqual(
            digest.evidence_digest,
            attestation["attestation_digest"],
        )

    def test_attestation_rejects_forged_receipt_and_missing_manual_gates(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        for mutation in ("receipt", "eligibility", "gates", "secret"):
            with self.subTest(mutation=mutation):
                changed = dict(attestation)
                if mutation == "receipt":
                    changed["validation_receipt_digest"] = "0" * 64
                elif mutation == "eligibility":
                    changed["eligibility_evidence_digest"] = "0" * 64
                else:
                    changed["manual_gate_evidence"] = (
                        []
                        if mutation == "gates"
                        else [
                            {
                                **attestation["manual_gate_evidence"][0],
                                "evidence": "Authorization: Bearer secret",
                            },
                            *attestation["manual_gate_evidence"][1:],
                        ]
                    )
                fields = {
                    key: value
                    for key, value in changed.items()
                    if key != "attestation_digest"
                }
                changed["attestation_digest"] = MODULE._digest_json(fields)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "attestation.json"
                    path.write_text(json.dumps(changed), encoding="utf-8")

                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        "validation evidence is invalid or stale",
                    ):
                        MODULE.load_validation_evidence(
                            path,
                            "SecPal/api",
                            "c" * 40,
                            reviewed,
                        )

    def test_validation_evidence_head_drift_blocks(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attestation.json"
            path.write_text(json.dumps(attestation), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "validation evidence does not match the fix commit",
            ):
                MODULE.load_validation_evidence(
                    path,
                    "SecPal/api",
                    "b" * 40,
                    reviewed,
                )

    def test_validation_receipt_cannot_authorize_no_change_resolution(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        receipt = validation_receipt_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "authenticated fix-commit attestation",
            ):
                MODULE.load_validation_evidence(
                    path,
                    "SecPal/api",
                    "a" * 40,
                    reviewed,
                )

    def test_local_commit_binding_rejects_tree_parent_and_trailer_drift(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "attestation.json"
            evidence_path.write_text(json.dumps(attestation), encoding="utf-8")
            validation = MODULE.load_validation_evidence(
                evidence_path,
                "SecPal/api",
                "c" * 40,
                reviewed,
            )
            cases = {
                "tree": {"tree": "0" * 40},
                "parent": {"reviewed_head": "0" * 40},
                "trailer": {"receipt_digest": "0" * 64},
            }
            for expected_error, changes in cases.items():
                with self.subTest(expected_error=expected_error):
                    fake = FakeGit(
                        expected_head="c" * 40,
                        reviewed_head=changes.get(
                            "reviewed_head", reviewed.head_sha
                        ),
                        tree=changes.get("tree", attestation["validated_tree_sha"]),
                        receipt_digest=changes.get(
                            "receipt_digest",
                            attestation["validation_receipt_digest"],
                        ),
                    )
                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        expected_error,
                    ):
                        MODULE.verify_local_fix_commit(
                            Path(directory),
                            "SecPal/api",
                            "c" * 40,
                            reviewed,
                            validation,
                            runner=fake,
                        )

    def test_local_commit_binding_rejects_wrong_origin_and_invalid_signature(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "attestation.json"
            evidence_path.write_text(json.dumps(attestation), encoding="utf-8")
            validation = MODULE.load_validation_evidence(
                evidence_path,
                "SecPal/api",
                "c" * 40,
                reviewed,
            )
            cases = {
                "origin": {"repository": "SecPal/frontend"},
                "signature": {"signature_valid": False},
            }
            for expected_error, changes in cases.items():
                with self.subTest(expected_error=expected_error):
                    fake = FakeGit(
                        expected_head="c" * 40,
                        reviewed_head=reviewed.head_sha,
                        tree=attestation["validated_tree_sha"],
                        receipt_digest=attestation[
                            "validation_receipt_digest"
                        ],
                        **changes,
                    )
                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        expected_error,
                    ):
                        MODULE.verify_local_fix_commit(
                            Path(directory),
                            "SecPal/api",
                            "c" * 40,
                            reviewed,
                            validation,
                            runner=fake,
                        )

    def test_local_commit_binding_rejects_an_unknown_evidence_kind(self) -> None:
        reviewed = mock.Mock(head_sha="a" * 40)
        validation = MODULE.ValidationEvidence(
            kind="caller-constructed",
            evidence_digest="d" * 64,
            validated_tree_sha="f" * 40,
            validation_receipt_digest="e" * 64,
            eligibility_evidence_digest="f" * 64,
        )
        fake = mock.Mock()
        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "validation evidence binding",
        ):
            MODULE.verify_local_fix_commit(
                Path("."),
                "SecPal/api",
                "c" * 40,
                reviewed,
                validation,
                runner=fake,
            )
        fake.assert_not_called()

    def test_missing_validation_evidence_blocks_before_github(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "validation evidence is unavailable",
            ):
                MODULE.load_validation_evidence(
                    Path(directory) / "missing-attestation.json",
                    "SecPal/api",
                    "a" * 40,
                    reviewed,
                )

    def test_eligibility_manifest_binds_every_requested_thread(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        payload = reviewed_state_payload(first, [])
        payload["threads"].append(
            {
                "node_id": second,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [],
            }
        )
        feedback = {
            key: payload[key]
            for key in (
                "pull_request_reactions",
                "reviews",
                "conversation_comments",
                "threads",
            )
        }
        payload["feedback_digest"] = MODULE._digest_json(feedback)
        identity = {
            key: payload[key]
            for key in (
                "repository",
                "pull_request_number",
                "head_sha",
                "base_ref",
                "base_sha",
                "pr_state",
            )
        }
        payload["state_digest"] = MODULE._digest_json(
            {**identity, "feedback": feedback}
        )
        manifest = eligibility_payload(payload, (first, second))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            evidence_digest = MODULE.load_eligibility_evidence(
                path,
                "SecPal/api",
                123,
                payload["head_sha"],
                payload["state_digest"],
                (first, second),
                authenticated_evidence_digest=MODULE._digest_json(manifest),
            )

        self.assertEqual(
            evidence_digest.evidence_digest,
            MODULE._digest_json(manifest),
        )

    def test_ineligible_or_unlisted_thread_blocks_before_github(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(payload, (thread_id,))
        cases = {
            "unlisted": [],
            "unsafe disposition": [
                {
                    **manifest["eligible_threads"][0],
                    "disposition": "UNRESOLVED_VALID_FINDING",
                }
            ],
        }
        for label, threads in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                changed = {**manifest, "eligible_threads": threads}
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(changed), encoding="utf-8")

                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "eligibility evidence",
                ):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        payload["head_sha"],
                        payload["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(
                            changed
                        ),
                    )

    def test_tracked_follow_up_eligibility_is_exact_and_authenticated(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(payload, (thread_id,))
        manifest["schema_version"] = "1.1"
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            evidence = MODULE.load_eligibility_evidence(
                path,
                "SecPal/api",
                123,
                payload["head_sha"],
                payload["state_digest"],
                (thread_id,),
                authenticated_evidence_digest=MODULE._digest_json(manifest),
            )
        self.assertEqual(evidence.evidence_digest, MODULE._digest_json(manifest))
        self.assertEqual(
            MODULE._tracked_follow_ups_from_payload(evidence.canonical_payload)[
                thread_id
            ].issue_number,
            123,
        )

        changed = copy.deepcopy(manifest)
        changed["eligible_threads"][0]["follow_up"] = {
            "repository": "SecPal/api",
            "issue_number": 124,
            "issue_url": "https://github.com/SecPal/api/issues/124",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.ResolutionError, "not authenticated"
            ):
                MODULE.load_eligibility_evidence(
                    path,
                    "SecPal/api",
                    123,
                    payload["head_sha"],
                    payload["state_digest"],
                    (thread_id,),
                    authenticated_evidence_digest=MODULE._digest_json(manifest),
                )

    def test_tracked_follow_up_identity_fails_closed_when_malformed(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        base = eligibility_payload(payload, (thread_id,))
        base["schema_version"] = "1.1"
        base["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
        )
        cases = {
            "missing": None,
            "malformed repository": {
                "repository": "SecPal",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
            "non-positive number": {
                "repository": "SecPal/api",
                "issue_number": 0,
                "issue_url": "https://github.com/SecPal/api/issues/0",
            },
            "pull URL": {
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/pull/123",
            },
            "wrong owner": {
                "repository": "SecPal/frontend",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
            "wrong number": {
                "repository": "SecPal/api",
                "issue_number": 124,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        }
        for label, follow_up in cases.items():
            manifest = copy.deepcopy(base)
            if follow_up is not None:
                manifest["eligible_threads"][0]["follow_up"] = follow_up
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.ResolutionError, "follow-up"):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        payload["head_sha"],
                        payload["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(manifest),
                    )

        duplicate = copy.deepcopy(base)
        duplicate["eligible_threads"][0]["follow_up"] = {
            "repository": "SecPal/api",
            "issue_number": 123,
            "issue_url": "https://github.com/SecPal/api/issues/123",
        }
        serialized = json.dumps(duplicate).replace(
            '"issue_number": 123',
            '"issue_number": 122, "issue_number": 123',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(serialized, encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ResolutionError, "malformed"):
                MODULE.load_eligibility_evidence(
                    path,
                    "SecPal/api",
                    123,
                    payload["head_sha"],
                    payload["state_digest"],
                    (thread_id,),
                    authenticated_evidence_digest=MODULE._digest_json(duplicate),
                )

    def test_live_follow_up_requires_open_structurally_complete_exact_issue(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        failures = {
            "missing": MODULE.ResolutionError("follow-up is inaccessible"),
            "closed": MODULE.LiveFollowUpState(
                identity, False, True, False, False, True
            ),
            "structurally incomplete": MODULE.LiveFollowUpState(
                identity, True, False, False, False, True
            ),
            "identity mismatch": MODULE.LiveFollowUpState(
                MODULE.FollowUpIdentity(
                    repository="SecPal/frontend",
                    issue_number=123,
                    issue_url="https://github.com/SecPal/frontend/issues/123",
                ),
                True,
                True,
                False,
                False,
                True,
            ),
        }
        for label, result in failures.items():
            def reader(_identity: Any, result: Any = result) -> Any:
                if isinstance(result, Exception):
                    raise result
                return result

            with self.subTest(label=label), self.assertRaisesRegex(
                MODULE.ResolutionError, "follow-up"
            ):
                MODULE.verify_live_follow_up(identity, state_reader=reader)

        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                MODULE.verify_live_follow_up(
                    identity,
                    state_reader=lambda _identity, blocked=blocked: MODULE.LiveFollowUpState(
                        identity,
                        True,
                        True,
                        blocked,
                        False,
                        True,
                    ),
                )

    def test_guarded_follow_up_binds_trusted_markdown_parser_context(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        state = MODULE.LiveFollowUpState(identity, True, True, False, False, True)
        parser_environment = {"PATH": "/usr/bin:/bin"}
        hostile_environment = {
            "PATH": "/workspace-controlled/bin",
            "NODE_OPTIONS": "--require=/workspace-controlled/preload.js",
            "NODE_PATH": "/workspace-controlled/modules",
        }

        def resolve_executable(name: str) -> str:
            self.assertEqual(name, "gh")
            return "/usr/bin/gh"

        with (
            mock.patch.dict(os.environ, hostile_environment, clear=True),
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                side_effect=resolve_executable,
            ),
            mock.patch.object(
                MODULE,
                "_resolve_trusted_markdown_node",
                return_value="/usr/bin/node",
            ),
            mock.patch.object(
                MODULE,
                "_markdown_parser_environment",
                return_value=parser_environment,
            ),
            mock.patch.object(
                MODULE.follow_up,
                "read_live_follow_up",
                return_value=state,
            ) as reader,
        ):
            observed = MODULE._read_authenticated_follow_up(
                identity,
                MODULE.InvocationBudget(10, 100, 100),
            )

        self.assertEqual(observed, state)
        self.assertEqual(reader.call_args.kwargs["node_executable"], "/usr/bin/node")
        self.assertEqual(
            reader.call_args.kwargs["parser_environment"],
            parser_environment,
        )
        self.assertNotIn("NODE_OPTIONS", parser_environment)
        self.assertNotIn("NODE_PATH", parser_environment)
        self.assertNotEqual(parser_environment["PATH"], hostile_environment["PATH"])

    def test_trusted_markdown_node_ignores_hostile_path_and_node_options(self) -> None:
        with (
            tempfile.TemporaryDirectory() as trusted_directory,
            tempfile.TemporaryDirectory() as hostile_directory,
        ):
            trusted_node = Path(trusted_directory) / "node"
            hostile_node = Path(hostile_directory) / "node"
            for executable in (trusted_node, hostile_node):
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o700)
            hostile_environment = {
                "PATH": hostile_directory,
                "NODE_OPTIONS": "--require=/workspace/preload.js",
                "NODE_PATH": "/workspace/modules",
                "NPM_CONFIG_NODE_OPTIONS": "--import=/workspace/import.mjs",
            }
            with (
                mock.patch.object(
                    MODULE.evidence,
                    "TRUSTED_COMMAND_DIRECTORIES",
                    (Path(trusted_directory),),
                ),
                mock.patch.object(
                    MODULE.evidence,
                    "TRUSTED_COMMAND_PATH",
                    trusted_directory,
                ),
                mock.patch.dict(os.environ, hostile_environment, clear=True),
            ):
                resolved = MODULE._resolve_trusted_markdown_node()
                environment = MODULE._markdown_parser_environment()

        self.assertEqual(resolved, str(trusted_node.resolve()))
        self.assertTrue(Path(resolved).is_absolute())
        self.assertEqual(environment, {"PATH": trusted_directory})
        self.assertNotIn("NODE_OPTIONS", environment)
        self.assertNotIn("NODE_PATH", environment)
        self.assertNotIn("NPM_CONFIG_NODE_OPTIONS", environment)

    def test_guarded_follow_up_fails_when_trusted_node_is_unavailable(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )

        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE,
                "_resolve_trusted_markdown_node",
                side_effect=MODULE.ResolutionError(
                    "trusted Markdown parser is unavailable"
                ),
            ),
            mock.patch.object(MODULE.follow_up, "read_live_follow_up") as reader,
            self.assertRaisesRegex(MODULE.ResolutionError, "trusted Markdown parser"),
        ):
            MODULE._read_authenticated_follow_up(
                identity,
                MODULE.InvocationBudget(10, 100, 100),
            )
        reader.assert_not_called()

    def test_live_follow_up_rejects_canonical_malformed_and_incomplete_graphs(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        key = "SecPal/api#123"
        malformed = work_graph_model.build_snapshot(
            [
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=123,
                    url=identity.issue_url,
                    parent=key,
                    has_acceptance_criteria=True,
                )
            ]
        )
        incomplete = work_graph_model.build_snapshot(
            [
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=123,
                    url=identity.issue_url,
                    children=("SecPal/api#124",),
                    has_acceptance_criteria=True,
                )
            ]
        )
        for label, snapshot in (
            ("malformed", malformed),
            ("incomplete", incomplete),
        ):
            with (
                self.subTest(label=label),
                mock.patch.object(
                    work_graph_github,
                    "load_snapshot",
                    return_value=(snapshot, key),
                ),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "malformed|incomplete",
                ),
            ):
                MODULE.verify_live_follow_up(
                    identity,
                    state_reader=lambda exact: MODULE.follow_up.read_live_follow_up(
                        exact
                    ),
                )

    def test_live_follow_up_rejects_canonical_structural_malformations(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )

        def node(number: int, **overrides: Any) -> Any:
            values = {
                "repository": "SecPal/api",
                "number": number,
                "has_acceptance_criteria": True,
            }
            values.update(overrides)
            return work_graph_model.Node(**values)

        root = "SecPal/api#123"
        shared = "SecPal/api#125"
        multiple_parents = work_graph_model.build_snapshot(
            [
                node(123, url=identity.issue_url, children=("SecPal/api#124",)),
                node(124, parent=root, children=(shared, shared)),
                node(125, parent="SecPal/api#124"),
            ]
        )

        sub_issue_children = tuple(
            f"SecPal/api#{number}"
            for number in range(
                200,
                200 + work_graph_model.MAX_SUB_ISSUES_PER_PARENT + 1,
            )
        )
        sub_issue_limit = work_graph_model.build_snapshot(
            [
                node(123, url=identity.issue_url, children=sub_issue_children),
                *(
                    node(number, parent=root)
                    for number in range(
                        200,
                        200 + work_graph_model.MAX_SUB_ISSUES_PER_PARENT + 1,
                    )
                ),
            ]
        )

        depth = work_graph_model.MAX_NESTING_DEPTH + 1
        nested_nodes = [node(123, url=identity.issue_url, children=("SecPal/api#300",))]
        nested_nodes.extend(
            node(
                300 + offset,
                parent=root if offset == 0 else f"SecPal/api#{299 + offset}",
                children=(f"SecPal/api#{301 + offset}",) if offset < depth - 1 else (),
            )
            for offset in range(depth)
        )
        nesting_limit = work_graph_model.build_snapshot(nested_nodes)

        dependency_numbers = range(
            400,
            400 + work_graph_model.MAX_DEPENDENCIES_PER_TYPE + 1,
        )
        dependency_limit = work_graph_model.build_snapshot(
            [
                node(
                    123,
                    url=identity.issue_url,
                    blocked_by=tuple(f"SecPal/api#{number}" for number in dependency_numbers),
                ),
                *(node(number, state="CLOSED", state_reason="completed") for number in dependency_numbers),
            ]
        )

        for label, snapshot in (
            ("multiple parents", multiple_parents),
            ("sub-issue limit", sub_issue_limit),
            ("nesting limit", nesting_limit),
            ("dependency limit", dependency_limit),
        ):
            with (
                self.subTest(label=label),
                mock.patch.object(
                    work_graph_github,
                    "load_snapshot",
                    return_value=(snapshot, root),
                ),
                self.assertRaisesRegex(MODULE.ResolutionError, "malformed"),
            ):
                MODULE.verify_live_follow_up(
                    identity,
                    state_reader=lambda exact: MODULE.follow_up.read_live_follow_up(exact),
                )

    def test_live_follow_up_accepts_canonically_valid_blocked_issue(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        root = "SecPal/api#123"
        snapshot = work_graph_model.build_snapshot(
            [
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=123,
                    url=identity.issue_url,
                    blocked_by=("SecPal/api#124",),
                    has_acceptance_criteria=True,
                ),
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=124,
                    has_acceptance_criteria=True,
                ),
            ]
        )
        with mock.patch.object(
            work_graph_github,
            "load_snapshot",
            return_value=(snapshot, root),
        ):
            state = MODULE.verify_live_follow_up(
                identity,
                state_reader=lambda exact: MODULE.follow_up.read_live_follow_up(exact),
            )
        self.assertTrue(state.blocked)
        self.assertFalse(state.malformed)
        self.assertTrue(state.graph_complete)

    def test_follow_up_traversal_and_pagination_share_invocation_budget(self) -> None:
        thread_id = "PRRT_exampleOne"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        canonical_manifest = MODULE._canonical_json_bytes(manifest)
        eligibility = MODULE.EligibilityEvidence(
            hashlib.sha256(canonical_manifest).hexdigest(),
            canonical_manifest,
        )

        cases = {
            "traversal": [
                work_graph_issue_response(123, blocked_by=(124,)),
                work_graph_issue_response(124, blocked_by=(125,)),
                work_graph_issue_response(125, blocked_by=(126,)),
                work_graph_issue_response(126),
            ],
            "pagination": [
                work_graph_issue_response(123, labels_have_next_page=True),
                work_graph_page_response(
                    "labels",
                    has_next_page=True,
                    end_cursor="labels-next-2",
                ),
                work_graph_page_response(
                    "labels",
                    has_next_page=True,
                    end_cursor="labels-next-3",
                ),
                work_graph_page_response(
                    "labels",
                    has_next_page=False,
                    end_cursor=None,
                ),
            ],
        }
        for label, responses in cases.items():
            with self.subTest(label=label):
                adapter = work_graph_github.GitHubReadAdapter(max_nodes=10)
                adapter.query = mock.Mock(side_effect=responses)
                target_runner = FakeGh(
                    [
                        target_response(thread_id),
                        target_response(thread_id),
                        target_response(thread_id),
                        resolve_response(thread_id),
                    ]
                )

                def verifier(
                    exact: Any,
                    budget: Any,
                    adapter: Any = adapter,
                ) -> Any:
                    return MODULE.verify_live_follow_up(
                        exact,
                        budget=budget,
                        state_reader=lambda expected: MODULE.follow_up.read_live_follow_up(
                            expected,
                            adapter=adapter,
                            query_consumer=MODULE._consume_api_call,
                            query_context=budget,
                        ),
                    )

                with mock.patch.object(
                    MODULE,
                    "load_repository_limits",
                    return_value=MODULE.RepositoryLimits(4, 100, 100),
                ):
                    result = MODULE.resolve_threads(
                        "SecPal/api",
                        123,
                        "a" * 40,
                        (thread_id,),
                        apply=True,
                        expected_targets={
                            thread_id: expected_thread_state(thread_id)
                        },
                        reviewed_state_digest="c" * 64,
                        validation_evidence_digest="d" * 64,
                        eligibility_evidence_digest=eligibility.evidence_digest,
                        eligibility_evidence=eligibility,
                        follow_up_verifier=verifier,
                        runner=target_runner,
                    )

                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failed"][0]["phase"], "follow-up")
                self.assertEqual(result["resolved"], [])
                self.assertEqual(len(target_runner.calls), 1)

    def test_valid_follow_up_query_consumes_shared_invocation_budget(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        adapter = work_graph_github.GitHubReadAdapter(max_nodes=10)
        adapter.query = mock.Mock(return_value=work_graph_issue_response(123))
        budget = MODULE.InvocationBudget(10, 100, 100)

        state = MODULE.follow_up.read_live_follow_up(
            identity,
            adapter=adapter,
            query_consumer=MODULE._consume_api_call,
            query_context=budget,
        )

        self.assertEqual(budget.api_calls, 1)
        self.assertTrue(state.open)
        self.assertTrue(state.structurally_complete)
        self.assertFalse(state.malformed)
        self.assertTrue(state.graph_complete)
        MODULE.verify_live_follow_up(identity, state_reader=lambda _exact: state)

    def test_eligibility_manifest_rejects_rehashed_binding_drift(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(payload, (thread_id,))
        cases = {
            "repository": "SecPal/frontend",
            "pull_request_number": 124,
            "reviewed_head_sha": "b" * 40,
            "reviewed_state_digest": "0" * 64,
        }
        for field, value in cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                changed = {**manifest, field: value}
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(changed), encoding="utf-8")

                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "eligibility evidence binding",
                ):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        payload["head_sha"],
                        payload["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(
                            changed
                        ),
                    )

    def test_eligibility_manifest_rejects_caller_rehashed_decision(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        trusted = eligibility_payload(payload, (thread_id,))
        changed = copy.deepcopy(trusted)
        changed["eligible_threads"][0]["finding_ids"] = ["unaddressed-finding"]
        changed["eligible_threads"][0]["evidence_digest"] = "f" * 64

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(changed), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "eligibility evidence is not authenticated",
            ):
                MODULE.load_eligibility_evidence(
                    path,
                    "SecPal/api",
                    123,
                    payload["head_sha"],
                    payload["state_digest"],
                    (thread_id,),
                    authenticated_evidence_digest=MODULE._digest_json(trusted),
                )

    def test_nonfinite_reviewed_state_is_reported_without_traceback(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with (
                self.subTest(constant=constant),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / "reviewed.json"
                path.write_text(
                    f'{{"pull_request_number": {constant}}}',
                    encoding="utf-8",
                )
                stderr = StringIO()

                with (
                    mock.patch("sys.stderr", stderr),
                    mock.patch.object(MODULE, "resolve_threads") as resolver,
                ):
                    exit_code = MODULE.main(
                        [
                            "--repo",
                            "SecPal/api",
                            "--pr",
                            "123",
                            "--repo-root",
                            ".",
                            "--expected-head",
                            "a" * 40,
                            "--reviewed-state",
                            str(path),
                            "--expected-reviewed-state-digest",
                            "c" * 64,
                            "--validation-evidence",
                            "attestation.json",
                            "--eligibility-evidence",
                            "eligibility.json",
                            "--thread-id",
                            "PRRT_exampleOne",
                        ]
                    )

                self.assertEqual(exit_code, 1)
                self.assertIn(
                    "ERROR: reviewed feedback state is unavailable or malformed",
                    stderr.getvalue(),
                )
                self.assertNotIn("Traceback", stderr.getvalue())
                resolver.assert_not_called()

    def test_reviewed_state_loader_rejects_tampered_feedback(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(
            thread_id,
            [("PRRC_root", "reviewed body", None)],
        )
        payload["threads"][0]["comments"][0]["body_digest"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "digest is invalid",
            ):
                MODULE.load_reviewed_state(
                    path,
                    "SecPal/api",
                    123,
                    payload["state_digest"],
                    (thread_id,),
                )

    def test_head_mismatch_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, head="b" * 40)])

        with self.assertRaisesRegex(MODULE.ResolutionError, "head changed"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_head_change_after_initial_read_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, head="a" * 40),
                target_response(thread_id, head="b" * 40),
                target_response(thread_id, head="b" * 40),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["failed"][0]["thread_id"], thread_id)
        self.assertIn("head changed", result["failed"][0]["error"])
        self.assertEqual(len(fake.calls), 3)

    def test_missing_target_blocks_before_mutation(self) -> None:
        fake = FakeGh([{"data": {"node": None}}])

        with self.assertRaisesRegex(MODULE.ResolutionError, "does not belong"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_missingThread"],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_target_from_another_pull_request_is_rejected(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, number=124)])

        with self.assertRaisesRegex(MODULE.ResolutionError, "does not belong"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

    def test_closed_pull_request_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, state="CLOSED")])

        with self.assertRaisesRegex(MODULE.ResolutionError, "not open"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_reads_only_requested_target_nodes(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh([target_response(first), target_response(second)])

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second],
            apply=False,
            runner=fake,
        )

        self.assertEqual(result["pending"], [first, second])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn(f"threadId={first}", fake.calls[0])
        self.assertIn(f"threadId={second}", fake.calls[1])

    def test_comment_budget_is_shared_across_target_reads(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=[
                        ("PRRC_one", "one", None),
                        ("PRRC_two", "two", None),
                        ("PRRC_three", "three", None),
                    ],
                )
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=20,
            maximum_comments=2,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(MODULE.ResolutionError, "comment limit"),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
                reviewed_comments={
                    thread_id: [
                        ("PRRC_one", "one", None),
                        ("PRRC_two", "two", None),
                        ("PRRC_three", "three", None),
                    ],
                },
            )

    def test_repeated_comment_identity_across_pages_fails_closed(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=[("PRRC_repeated", "first", None)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
                target_response(
                    thread_id,
                    comments=[("PRRC_repeated", "second", None)],
                ),
            ]
        )

        with self.assertRaisesRegex(MODULE.ResolutionError, "repeated comment"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
            )

    def test_repeated_comment_cursor_fails_closed(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=[("PRRC_one", "one", None)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
                target_response(
                    thread_id,
                    comments=[("PRRC_two", "two", None)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
            ]
        )

        with self.assertRaisesRegex(MODULE.ResolutionError, "did not advance"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
            )

    def test_missing_page_info_fails_closed_even_when_target_is_found(self) -> None:
        thread_id = "PRRT_exampleOne"
        response = target_response(thread_id)
        del response["data"]["node"]["comments"]["pageInfo"]
        fake = FakeGh([response])

        with self.assertRaisesRegex(MODULE.ResolutionError, "pagination is missing"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
            )

    def test_partial_failure_reports_applied_failed_and_unattempted(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        third = "PRRT_exampleThree"
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(third),
                target_response(first),
                target_response(first),
                resolve_response(first),
                target_response(second),
                target_response(second),
                {"errors": [{"message": "mutation failed"}]},
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second, third],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [first])
        self.assertEqual(
            result["failed"],
            [
                {
                    "thread_id": second,
                    "phase": "mutation",
                    "write_result": "unknown",
                    "error": "GitHub GraphQL request failed",
                }
            ],
        )
        self.assertEqual(result["unattempted"], [third])
        self.assertEqual(result["status"], "failed")

    def test_main_emits_partial_report_and_returns_nonzero(self) -> None:
        report = {
            "repository": "SecPal/api",
            "pull_request_number": 123,
            "head_sha": "a" * 40,
            "mode": "apply",
            "status": "failed",
            "already_resolved": [],
            "pending": [],
            "resolved": ["PRRT_exampleOne"],
            "failed": [
                {
                    "thread_id": "PRRT_exampleTwo",
                    "error": "GitHub GraphQL request failed",
                }
            ],
            "unattempted": [],
        }
        output = StringIO()
        reviewed = MODULE.ReviewedState(
            head_sha="a" * 40,
            state_digest="c" * 64,
            feedback_digest="e" * 64,
            targets={
                "PRRT_exampleOne": expected_thread_state("PRRT_exampleOne"),
            },
        )
        with (
            mock.patch.object(
                MODULE,
                "load_reviewed_state",
                return_value=reviewed,
            ),
            mock.patch.object(
                MODULE,
                "load_validation_evidence",
                return_value=MODULE.ValidationEvidence(
                    kind="attestation",
                    evidence_digest="d" * 64,
                    validated_tree_sha="f" * 40,
                    validation_receipt_digest="b" * 64,
                    eligibility_evidence_digest="e" * 64,
                ),
            ),
            mock.patch.object(MODULE, "verify_local_fix_commit") as verify_commit,
            mock.patch.object(
                MODULE,
                "load_eligibility_evidence",
                return_value=MODULE.EligibilityEvidence("e" * 64, b"{}"),
            ),
            mock.patch.object(MODULE, "resolve_threads", return_value=report),
            redirect_stdout(output),
        ):
            returncode = MODULE.main(
                [
                    "--repo",
                    "SecPal/api",
                    "--pr",
                    "123",
                    "--repo-root",
                    ".",
                    "--expected-head",
                    "a" * 40,
                    "--reviewed-state",
                    "reviewed.json",
                    "--expected-reviewed-state-digest",
                    "c" * 64,
                    "--validation-evidence",
                    "attestation.json",
                    "--eligibility-evidence",
                    "eligibility.json",
                    "--thread-id",
                    "PRRT_exampleOne",
                ]
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(json.loads(output.getvalue()), report)
        verify_commit.assert_called_once()

    def test_run_gh_uses_trusted_absolute_executable_and_environment(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr="",
        )
        trusted_environment = {
            "PATH": "/usr/bin:/bin",
            "GH_HOST": "github.com",
            "GH_PAGER": "cat",
        }
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value=trusted_environment,
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            arguments = [
                *MODULE.GH_GRAPHQL_PREFIX,
                "-f",
                f"query={MODULE.TARGET_QUERY}",
            ]
            self.assertEqual(MODULE._run_gh(arguments), {})

        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/gh", *arguments],
        )
        self.assertEqual(run.call_args.kwargs["env"], trusted_environment)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_graphql_explicitly_pins_github_host(self) -> None:
        fake = FakeGh([{"data": {}}])
        budget = MODULE.InvocationBudget(
            maximum_api_calls=1,
            maximum_threads=1,
            maximum_comments=1,
        )

        self.assertEqual(MODULE._graphql(MODULE.TARGET_QUERY, {}, fake, budget), {})

        self.assertEqual(
            fake.calls[0][:4],
            ["api", "--hostname", "github.com", "graphql"],
        )

    def test_graphql_rejects_documents_outside_the_allowlist(self) -> None:
        fake = FakeGh([])
        budget = MODULE.InvocationBudget(
            maximum_api_calls=1,
            maximum_threads=1,
            maximum_comments=1,
        )

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "outside the GraphQL document allowlist",
        ):
            MODULE._graphql("mutation { mergePullRequest }", {}, fake, budget)

        self.assertEqual(fake.calls, [])
        self.assertEqual(budget.api_calls, 0)

    def test_run_gh_rejects_commands_outside_pinned_graphql_surface(self) -> None:
        with mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "outside the allowed GraphQL surface",
            ):
                MODULE._run_gh(["pr", "merge", "591"])

        run.assert_not_called()

    def test_run_gh_rejects_unapproved_graphql_documents(self) -> None:
        with mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "outside the GraphQL document allowlist",
            ):
                MODULE._run_gh(
                    [
                        *MODULE.GH_GRAPHQL_PREFIX,
                        "-f",
                        "query=mutation { mergePullRequest }",
                    ]
                )

        run.assert_not_called()

    def test_run_gh_translates_process_launch_failure(self) -> None:
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value={"PATH": "/usr/bin:/bin"},
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                side_effect=OSError("executable disappeared"),
            ),
        ):
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "process launch failed",
            ):
                MODULE._run_gh(
                    [
                        *MODULE.GH_GRAPHQL_PREFIX,
                        "-f",
                        f"query={MODULE.TARGET_QUERY}",
                    ]
                )

    def test_run_gh_redacts_failure_diagnostic(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="token=supersecret",
        )
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value={"PATH": "/usr/bin:/bin"},
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ),
        ):
            with self.assertRaises(MODULE.ResolutionError) as raised:
                MODULE._run_gh(
                    [
                        *MODULE.GH_GRAPHQL_PREFIX,
                        "-f",
                        f"query={MODULE.TARGET_QUERY}",
                    ]
                )

        self.assertIn("[REDACTED]", str(raised.exception))
        self.assertNotIn("supersecret", str(raised.exception))

    def test_process_launch_failure_after_resolution_preserves_report(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        third = "PRRT_exampleThree"

        def completed(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )

        process_results: list[object] = [
            completed(target_response(first)),
            completed(target_response(second)),
            completed(target_response(third)),
            completed(target_response(first)),
            completed(target_response(first)),
            completed(resolve_response(first)),
            OSError("executable disappeared"),
        ]
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value={"PATH": "/usr/bin:/bin"},
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                side_effect=process_results,
            ),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [first, second, third],
                apply=True,
            )

        self.assertEqual(result["resolved"], [first])
        self.assertEqual(result["failed"][0]["thread_id"], second)
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(result["failed"][0]["write_result"], "not_attempted")
        self.assertEqual(result["unattempted"], [third])
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    main()
