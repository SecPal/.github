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
            r"standalone.*(?:itself|requested issue)",
            r"incomplete|malformed",
            r"do not (?:guess|invent).*(?:scope|ready|next)",
        )

    def test_resolved_cases_have_the_required_advisory_outcomes(self) -> None:
        # These are representative, already-resolved envelopes. The test checks
        # the instruction-layer response and deliberately derives no graph state.
        cases = {
            "aligned": {
                "resolved": {"ready": True, "leaf": True},
                "ready": ["SecPal/example#10"],
                "next": "SecPal/example#10",
                "patterns": (r"aligned.*continue",),
            },
            "ready_not_next": {
                "resolved": {"ready": True, "leaf": True},
                "ready": ["SecPal/example#10", "SecPal/example#11"],
                "next": "SecPal/example#11",
                "patterns": (r"advisory mismatch", r"continue.*explicitly selected"),
            },
            "blocked": {
                "resolved": {"ready": False, "blocked": True, "reasons": ["unsatisfied_dependency"]},
                "ready": ["SecPal/example#11"],
                "next": "SecPal/example#11",
                "patterns": (r"blocked.*(?:blocker|reason)", r"do not.*ready"),
            },
            "non_leaf": {
                "resolved": {"ready": False, "leaf": False, "children": ["SecPal/example#11"]},
                "ready": ["SecPal/example#11"],
                "next": "SecPal/example#11",
                "patterns": (r"non.leaf.*descendant.*ready.*next",),
            },
            "structurally_incomplete": {
                "resolved": {"ready": False, "reasons": ["missing_acceptance_criteria"]},
                "ready": [],
                "next": None,
                "patterns": (r"structurally incomplete.*exact.*reason", r"do not invent.*ready"),
            },
            "malformed": {
                "complete": False,
                "status": "incomplete_inputs",
                "next": None,
                "patterns": (r"fail.closed", r"do not (?:guess|invent).*(?:ready|next)"),
            },
        }

        for name, fixture in cases.items():
            with self.subTest(case=name, fixture=fixture):
                self.assert_semantics(*fixture["patterns"])

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
