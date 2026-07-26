#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Sequence
from unittest import TestCase, main

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
                resolve_response(first),
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
        self.assertEqual(len(fake.calls), 3)

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


if __name__ == "__main__":
    main()
