#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Behavior evidence for bounded work-graph hard-gate refresh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import gate_refresh, replanning, replan_cli  # noqa: E402


class FakeGateway:
    def __init__(self, pulls, results):
        self.pulls = tuple(pulls)
        self.results = dict(results)
        self.statuses = []

    def open_pull_requests(self, repository, limit):
        self.repository = repository
        self.limit = limit
        return self.pulls

    def publish(self, repository, pull, state, description):
        self.statuses.append((repository, pull.number, pull.head_sha, state, description))

    def assess(self, repository, pull):
        return self.results[pull.number]


class GateRefreshTests(TestCase):
    def test_refresh_invalidates_each_bounded_head_before_reassessment(self):
        pulls = (
            gate_refresh.PullRequest(10, "a" * 40),
            gate_refresh.PullRequest(11, "b" * 40),
        )
        gateway = FakeGateway(pulls, {10: 0, 11: 1})

        report = gate_refresh.refresh_repository(
            gateway, "SecPal/.github", maximum_pull_requests=100
        )

        self.assertEqual(
            [(item[3], item[1]) for item in gateway.statuses],
            [("pending", 10), ("pending", 11), ("success", 10), ("failure", 11)],
        )
        self.assertEqual(report["refreshed"], 2)
        self.assertEqual(report["failed"], [11])

    def test_unavailable_gate_evidence_finishes_as_error_not_success(self):
        pull = gate_refresh.PullRequest(10, "a" * 40)
        gateway = FakeGateway((pull,), {10: 3})

        report = gate_refresh.refresh_repository(gateway, "SecPal/.github")

        self.assertEqual(gateway.statuses[-1][3], "error")
        self.assertEqual(report["unavailable"], [10])

    def test_candidate_overflow_fails_before_any_status_write(self):
        pulls = tuple(
            gate_refresh.PullRequest(number, f"{number:040x}")
            for number in range(1, 102)
        )
        gateway = FakeGateway(pulls, {})

        with self.assertRaisesRegex(gate_refresh.RefreshError, "bounded candidate limit"):
            gate_refresh.refresh_repository(
                gateway, "SecPal/.github", maximum_pull_requests=100
            )

        self.assertEqual(gateway.statuses, [])

    def test_malformed_candidate_identity_fails_closed(self):
        with self.assertRaisesRegex(gate_refresh.RefreshError, "identity is malformed"):
            gate_refresh.PullRequest(True, "a" * 40)

    def test_refresh_workflow_covers_issue_edits_and_canonical_mutation_dispatch(self):
        workflow = (ROOT / ".github/workflows/work-graph-gate-refresh.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("issues:", workflow)
        self.assertIn("repository_dispatch:", workflow)
        self.assertIn("work_graph_mutated", workflow)
        self.assertIn("statuses: write", workflow)
        self.assertIn("scripts/secpal-work-graph-gate-refresh.py --apply", workflow)

    def test_canonical_replan_refreshes_every_affected_repository(self):
        classification = replanning.Classification(
            "NEW_RESPONSIBILITY",
            "CREATE_OWNED_SIBLING",
            False,
            True,
            "BEFORE_FREEZE",
            (),
        )
        plan = replanning.Plan(
            actor="alice",
            classification=classification,
            current_issue="SecPal/.github#735",
            owner="SecPal/.github#675",
            snapshot_digest="a" * 64,
            steps=(
                replanning.Step(
                    "ADD_BLOCKED_BY",
                    {
                        "blocked": "SecPal/.github#735",
                        "blocker": "SecPal/api#900",
                    },
                ),
            ),
            request={},
        )

        self.assertEqual(
            replan_cli._mutation_repositories(plan),
            ("SecPal/.github", "SecPal/api"),
        )

    def test_command_gateway_fails_closed_when_assessment_cannot_execute(self):
        gateway = gate_refresh.CommandGateway(gh="gh", repository_root=ROOT)

        with mock.patch.object(
            gate_refresh.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("advisory", 120),
        ):
            with self.assertRaisesRegex(
                gate_refresh.RefreshError, "canonical hard-gate assessment failed"
            ):
                gateway.assess(
                    "SecPal/.github",
                    gate_refresh.PullRequest(759, "a" * 40),
                )


if __name__ == "__main__":
    main()
