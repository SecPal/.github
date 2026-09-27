#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from unittest import TestCase, main, mock


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/work-graph-contract.md"
ROLLOUT = ROOT / "scripts/polyscope-rollout.py"
POLYSCOPE_RUNTIME_TEMPLATE = ROOT / "templates/polyscope-codex-AGENTS.md"


def load_rollout():
    spec = importlib.util.spec_from_file_location("draft_first_rollout", ROLLOUT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {ROLLOUT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section(markdown: str, heading: str) -> str:
    match = re.search(
        rf"^### {re.escape(heading)}\n(?P<body>.*?)(?=^### |^## |\Z)",
        markdown,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing canonical section: {heading}")
    return match.group("body")


def text_blocks(markdown: str) -> list[str]:
    return re.findall(r"^```text\n(.*?)^```$", markdown, re.MULTILINE | re.DOTALL)


class DeliveryLifecycleGovernanceTests(TestCase):
    def test_canonical_delivery_lifecycle_is_draft_first_and_finite(self) -> None:
        lifecycle = section(
            CONTRACT.read_text(encoding="utf-8"), "5.3 Delivery PR lifecycle"
        )

        required_semantics = (
            r"every new SecPal delivery pull request.*MUST.*Draft",
            r"MUST\s+NOT.*directly.*Ready",
            r"direct.Ready.*NOT equivalent.*Draft.*Ready",
            r"explicit.*operator.*authoriz.*Draft.*Ready",
            r"exactly one.*Draft.*Ready",
            r"Ready.*monotonic",
            r"Ready.*Draft.*exact.*operator.*authoriz",
            r"later.*Draft.*Ready.*own.*operator.*authoriz",
            r"ordinary.*Ready.Draft churn.*prohibit",
            r"new\s+commit.*does not.*authoriz.*another review",
            r"remediat.*no.*new review request",
        )
        for semantic in required_semantics:
            with self.subTest(semantic=semantic):
                self.assertRegex(lifecycle, re.compile(semantic, re.IGNORECASE | re.DOTALL))

        blocks = text_blocks(lifecycle)
        self.assertGreaterEqual(len(blocks), 3)
        state_machine = blocks[0]
        lifecycle_order = [
            "CREATE_AS_DRAFT",
            "PRE_READY",
            "DRAFT_TO_READY",
            "FINITE_REVIEW",
            "OPTIONAL_SINGLE_REMEDIATION_COMMIT",
            "MERGE",
        ]
        for state in lifecycle_order:
            with self.subTest(state=state):
                self.assertIn(state, state_machine)
        positions = [state_machine.find(state) for state in lifecycle_order]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

        lifecycle_examples = "\n".join(blocks[1:])
        normalized_examples = lifecycle_examples.replace(
            "OPTIONAL_SINGLE_REMEDIATION_COMMIT", ""
        )
        self.assertNotIn("REMEDIATION COMMIT", normalized_examples)
        self.assertIn("OPTIONAL_SINGLE_REMEDIATION_COMMIT", lifecycle_examples)

        self.assertRegex(lifecycle, r"NEW\s*->\s*DRAFT\s*->\s*READY\s*->\s*MERGED")
        self.assertRegex(lifecycle, r"NEW\s*->\s*READY.*invalid")
        self.assertRegex(
            lifecycle,
            r"READY\s*->\s*DRAFT\s*->\s*READY.*invalid: ordinary or unauthorized",
        )

    def test_every_polyscope_pr_creation_path_requires_draft(self) -> None:
        rollout = load_rollout()
        spec = {
            "agent_instructions": "SecPal/deployment/AGENTS.md",
            "display_name": "SecPal/deployment",
            "focus_instruction_paths": [],
            "review_focus": "deployment governance",
        }
        with mock.patch.object(
            rollout,
            "load_runtime_instructions_text",
            return_value="# Scope and Safety\n\n- Keep one topic.\n",
        ):
            prompts = rollout.build_prompt_bundle(spec)

        for prompt_name in ("pr_prompt", "draft_pr_prompt"):
            with self.subTest(prompt_name=prompt_name):
                prompt = prompts[prompt_name]
                self.assertRegex(prompt, re.compile(r"create.*draft PR", re.IGNORECASE))
                self.assertRegex(prompt, re.compile(r"must not.*directly.*Ready", re.IGNORECASE))
                self.assertIn("English PR body", prompt)

        runtime_template = POLYSCOPE_RUNTIME_TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(
            runtime_template,
            re.compile(r"every new SecPal delivery pull request.*created as Draft", re.IGNORECASE),
        )
        self.assertRegex(
            runtime_template,
            re.compile(r"must not.*directly.*Ready", re.IGNORECASE | re.DOTALL),
        )


if __name__ == "__main__":
    main()
