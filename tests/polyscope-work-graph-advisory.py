#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Contract tests for Polyscope's managed advisory work-graph instructions."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS_PATH = REPOSITORY_ROOT / "templates" / "polyscope-codex-AGENTS.md"
SECTION_HEADING = "## Advisory work-graph selection"


def advisory_section() -> str:
    text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(SECTION_HEADING)}\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing {SECTION_HEADING!r} section")
    return re.sub(r"\s+", " ", match.group("body")).strip().casefold()


class AdvisoryWorkGraphInstructionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.section = advisory_section()

    def assert_semantics(self, *patterns: str) -> None:
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                self.assertRegex(self.section, pattern)

    def assert_absent(self, *patterns: str) -> None:
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.section, pattern)

    def test_activation_uses_only_the_structured_current_workspace_assignment(self) -> None:
        self.assert_semantics(
            r"polyscope.*session",
            r"current workspace.*worktrees\.path|worktrees\.path.*current workspace",
            r"repositories\.name",
            r"issue_number",
            r"issue_url",
            r"read.only",
            r"before (?:the )?first implementation side effect",
            r"no structured issue assignment.*(?:unavailable|do not invent)",
            r"branch name.*(?:not|never)|(?:not|never).*branch name",
            r"free.form.*(?:not|never)|(?:not|never).*free.form",
        )

    def test_existing_resolver_owns_graph_semantics_and_scope(self) -> None:
        self.assert_semantics(
            r"docs/work-graph-contract\.md",
            r"scripts/secpal-work-graph\.py",
            r"secpal-work-graph/v1",
            r"`validate-issue`",
            r"`show`",
            r"`ready`",
            r"`next`",
            r"native ancestor",
            r"nearest containing native (?:epic|sub.epic)",
            r"#664.*#667.*#672.*scope.*#667",
            r"standalone.*(?:itself|requested issue)",
            r"incomplete|malformed",
            r"do not (?:guess|invent).*(?:scope|ready|next)",
        )
        self.assert_absent(r"outermost resolved native ancestor")

    def test_scope_distinguishes_requested_leaves_from_non_leaves(self) -> None:
        self.assert_semantics(
            r"requested issue is a non.leaf.*scope.*requested issue",
            r"root epic.*scope.*requested",
            r"non.leaf.*descendant.*ready.*next",
            r"requested issue is a leaf.*nearest containing native (?:epic|sub.epic)",
            r"standalone root leaf.*scope.*requested",
            r"do not (?:guess|infer).*node role",
        )
        self.assert_absent(
            r"requested issue is a non.leaf.{0,120}(?:nearest containing|scope (?:is|=) (?:its )?parent)"
        )

    def test_structured_assignment_must_be_unique_and_internally_consistent(self) -> None:
        self.assert_semantics(
            r"exactly one active.*worktrees\.path|worktrees\.path.*exactly one active",
            r"zero.*(?:multiple|more than one).*(?:unavailable|malformed)",
            r"do not (?:select|guess).*(?:row|record|identity)",
            r"parse.*issue_url",
            r"issue_url.*repository.*issue number",
            r"repositories\.name.*issue_number",
            r"same.*repository.*(?:number|issue)|match.*repository.*(?:number|issue)",
            r"(?:disagree|mismatch|inconsistent).*(?:malformed|unavailable)",
        )

    def test_resolver_exit_status_preserves_reported_results_and_real_failures(self) -> None:
        self.assert_semantics(
            r"capture.*stdout.*exit status|capture.*exit status.*stdout",
            r"(?:exit|status).*0.*1.*secpal-work-graph/v1.*(?:consume|surface)",
            r"(?:exit|status).*1.*(?:reported|meaningful).*(?:not|never).*command failure",
            r"(?:exit|status).*2.*3.*(?:unavailable|fail)",
            r"(?:missing|invalid).*json.*(?:unavailable|fail)",
            r"schema.*secpal-work-graph/v1.*(?:unavailable|fail)",
            r"do not invent.*graph state",
        )

    def test_resolved_cases_have_the_required_advisory_outcomes(self) -> None:
        self.assert_semantics(
            r"aligned.*continue",
            r"advisory mismatch",
            r"continue.*explicitly selected",
            r"blocked.*(?:blocker|reason)",
            r"do not.*ready",
            r"non.leaf.*descendant.*ready.*next",
            r"structurally incomplete.*exact.*reason",
            r"do not invent.*ready",
            r"fail.closed",
            r"do not (?:guess|invent).*(?:ready|next)",
        )

    def test_parallelism_override_and_mutation_boundaries_are_explicit(self) -> None:
        self.assert_semantics(
            r"ready.*siblings.*parallel|parallel.*ready.*siblings",
            r"next.*ranking.*not.*topology|next.*not.*(?:block|dependency)",
            r"do not (?:add|create).*dependenc",
            r"do not reorder",
            r"do not.*mutate.*graph",
            r"structured.*explicitly selected",
            r"advisory rollout behavior",
            r"continue.*selected issue",
            r"hard enforcement.*#675|#675.*hard enforcement",
        )

    def test_body_mirrors_are_never_selection_inputs(self) -> None:
        self.assert_semantics(
            r"body.only.*never.*execution input|never.*body.only.*execution input",
            r"`parent:`",
            r"`order:`",
            r"`blocked by:`",
            r"markdown child lists",
        )

    def test_advisory_state_alone_never_hard_refuses_work(self) -> None:
        self.assert_semantics(
            r"no hard work.graph refusal|does not.*hard work.graph refusal",
            r"blocked.*non.leaf.*mismatch|mismatch.*blocked.*non.leaf",
            r"security.*sandbox",
        )


if __name__ == "__main__":
    unittest.main()
