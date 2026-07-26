#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Sequence
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/secpal-resolve-fixed-threads.py"
SPEC = importlib.util.spec_from_file_location("secpal_resolve_fixed_threads", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeGh:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, arguments: Sequence[str]) -> dict[str, Any]:
        self.calls.append(list(arguments))
        if not self.responses:
            raise AssertionError("unexpected gh call")
        return self.responses.pop(0)


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
            MODULE.resolve_threads(
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
                    ]
                )

                result = MODULE.resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    [thread_id],
                    apply=True,
                    runner=fake,
                )

                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["resolved"], [])
                self.assertEqual(result["failed"][0]["phase"], "recheck")
                self.assertIn(
                    "target thread changed",
                    result["failed"][0]["error"],
                )
                self.assertEqual(len(fake.calls), 2)

    def test_changed_outdated_state_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, outdated=False),
                target_response(thread_id, outdated=True),
            ]
        )

        result = MODULE.resolve_threads(
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
        self.assertEqual(len(fake.calls), 2)

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
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
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
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

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
                resolve_response(thread_id),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=10,
            maximum_comments=250,
        )

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=limits,
        ):
            result = MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(len(fake.calls), 5)
        self.assertIn("commentsAfter=initial-1", fake.calls[1])
        self.assertIn("commentsAfter=recheck-1", fake.calls[3])

    def test_callable_rejects_duplicate_thread_ids_before_reading(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "must be unique"):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id, thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_callable_rejects_malformed_request_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "positive"):
            MODULE.resolve_threads(
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
            MODULE.resolve_threads(
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
            MODULE.resolve_threads(
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

    def test_dry_run_reads_once_and_does_not_mutate(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id)])

        result = MODULE.resolve_threads(
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
                resolve_response(first),
                target_response(second),
                resolve_response(second),
            ]
        )

        result = MODULE.resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [first, second])
        self.assertEqual(len(fake.calls), 6)

    def test_already_resolved_target_is_idempotent(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, resolved=True)])

        result = MODULE.resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["already_resolved"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(fake.calls), 1)

    def test_head_mismatch_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, head="b" * 40)])

        with self.assertRaisesRegex(MODULE.ResolutionError, "head changed"):
            MODULE.resolve_threads(
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
            ]
        )

        result = MODULE.resolve_threads(
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
        self.assertEqual(len(fake.calls), 2)

    def test_missing_target_blocks_before_mutation(self) -> None:
        fake = FakeGh([{"data": {"node": None}}])

        with self.assertRaisesRegex(MODULE.ResolutionError, "does not belong"):
            MODULE.resolve_threads(
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
            MODULE.resolve_threads(
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
            MODULE.resolve_threads(
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

        result = MODULE.resolve_threads(
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
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
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
            MODULE.resolve_threads(
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
            MODULE.resolve_threads(
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
            MODULE.resolve_threads(
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
                resolve_response(first),
                target_response(second),
                {"errors": [{"message": "mutation failed"}]},
            ]
        )

        result = MODULE.resolve_threads(
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
        with (
            mock.patch.object(MODULE, "resolve_threads", return_value=report),
            redirect_stdout(output),
        ):
            returncode = MODULE.main(
                [
                    "--repo",
                    "SecPal/api",
                    "--pr",
                    "123",
                    "--expected-head",
                    "a" * 40,
                    "--thread-id",
                    "PRRT_exampleOne",
                ]
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(json.loads(output.getvalue()), report)

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
            self.assertEqual(MODULE._run_gh(["api", "graphql"]), {})

        self.assertEqual(run.call_args.args[0], ["/usr/bin/gh", "api", "graphql"])
        self.assertEqual(run.call_args.kwargs["env"], trusted_environment)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

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
                MODULE._run_gh(["api", "graphql"])

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
                MODULE._run_gh(["api", "graphql"])

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
            result = MODULE.resolve_threads(
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
