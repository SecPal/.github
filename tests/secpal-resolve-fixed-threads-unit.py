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


def read_response(
    *,
    head: str = "a" * 40,
    state: str = "OPEN",
    threads: list[tuple[str, bool]] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "state": state,
                    "headRefOid": head,
                    "reviewThreads": {
                        "nodes": [
                            {"id": thread_id, "isResolved": resolved}
                            for thread_id, resolved in (threads or [])
                        ],
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    },
                }
            }
        }
    }


def resolve_response(thread_id: str) -> dict[str, Any]:
    return {
        "data": {
            "resolveReviewThread": {
                "thread": {"id": thread_id, "isResolved": True}
            }
        }
    }


class ResolveFixedThreadsTests(TestCase):
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
        fake = FakeGh([read_response(threads=[(thread_id, False)])])

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

    def test_apply_resolves_each_open_target_once(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh(
            [
                read_response(threads=[(first, False), (second, False)]),
                read_response(threads=[(first, False)]),
                resolve_response(first),
                read_response(threads=[(second, False)]),
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
        self.assertEqual(len(fake.calls), 5)

    def test_already_resolved_target_is_idempotent(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([read_response(threads=[(thread_id, True)])])

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
        fake = FakeGh([read_response(head="b" * 40, threads=[(thread_id, False)])])

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
                read_response(head="a" * 40, threads=[(thread_id, False)]),
                read_response(head="b" * 40, threads=[(thread_id, False)]),
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
        fake = FakeGh([read_response(threads=[])])

        with self.assertRaisesRegex(MODULE.ResolutionError, "do not belong"):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_missingThread"],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_closed_pull_request_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [read_response(state="CLOSED", threads=[(thread_id, False)])]
        )

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

    def test_paginates_only_until_all_requested_targets_are_found(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh(
            [
                read_response(
                    threads=[(first, False)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
                read_response(threads=[(second, False)]),
            ]
        )

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

    def test_thread_pagination_fails_closed_at_registered_limit(self) -> None:
        responses: list[dict[str, Any]] = []
        for page in range(6):
            responses.append(
                read_response(
                    threads=[
                        (f"PRRT_page{page}item{item}", False)
                        for item in range(100)
                    ],
                    has_next_page=True,
                    end_cursor=f"cursor-{page}",
                )
            )
        fake = FakeGh(responses)

        with self.assertRaisesRegex(MODULE.ResolutionError, "thread limit"):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_missingThread"],
                apply=False,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 5)

    def test_repeated_thread_identity_across_pages_fails_closed(self) -> None:
        repeated = "PRRT_repeatedThread"
        fake = FakeGh(
            [
                read_response(
                    threads=[(repeated, False)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
                read_response(
                    threads=[(repeated, True)],
                    has_next_page=False,
                ),
            ]
        )

        with self.assertRaisesRegex(MODULE.ResolutionError, "repeated thread"):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_missingThread"],
                apply=False,
                runner=fake,
            )

    def test_missing_page_info_fails_closed_even_when_target_is_found(self) -> None:
        thread_id = "PRRT_exampleOne"
        response = read_response(threads=[(thread_id, False)])
        del response["data"]["repository"]["pullRequest"]["reviewThreads"][
            "pageInfo"
        ]
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
                read_response(
                    threads=[(first, False), (second, False), (third, False)]
                ),
                read_response(threads=[(first, False)]),
                resolve_response(first),
                read_response(threads=[(second, False)]),
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
            completed(
                read_response(
                    threads=[(first, False), (second, False), (third, False)]
                )
            ),
            completed(read_response(threads=[(first, False)])),
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
