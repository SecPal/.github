#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for finite delivery-lifecycle orchestration."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_orchestration as orchestration

REPOSITORY = "SecPal/.github"
ISSUE = 692
PR = 800
REPLACEMENT_PR = 801
HEAD = "a" * 40
NEXT_HEAD = "b" * 40
LIFECYCLE = "lifecycle:" + "c" * 64


def current_lifecycle(*, ready: bool = True) -> authority.VerifiedLifecycleAuthority:
    state = authority.initial_state()
    state.update(
        {
            "unrestricted_review_count": 1,
            "remediation_cycle_count": 2,
            "draft": not ready,
            "ready": ready,
            "ready_transition_count": 1 if ready else 0,
            "ready_history": (
                [
                    {
                        "sequence": 1,
                        "transition_kind": "DRAFT_TO_READY",
                        "event_authorization_digest": "d" * 64,
                    }
                ]
                if ready
                else []
            ),
        }
    )
    return authority.VerifiedLifecycleAuthority(
        authority_digest="e" * 64,
        repository=REPOSITORY,
        delivery_issue=ISSUE,
        lifecycle_id=LIFECYCLE,
        initialization_evidence_digest="f" * 64,
        pull_request=PR,
        head_sha=HEAD,
        state=state,
        authority_signer_identity="aroviqen@secpal.app",
    )


def current_reader(lifecycle: authority.VerifiedLifecycleAuthority):
    def read(repository: str, delivery_issue: int):
        if (repository, delivery_issue) != (REPOSITORY, ISSUE):
            raise AssertionError("unexpected lifecycle selection")
        return SimpleNamespace(
            publication_oid="1" * 40,
            publication_digest="2" * 64,
            lifecycle=copy.deepcopy(lifecycle),
        )

    return read


class LifecycleOrchestrationTests(TestCase):
    def test_review_event_is_bounded_evidence_not_a_lifecycle_transition(self) -> None:
        lifecycle = current_lifecycle()
        decision = orchestration.orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "REVIEW_EVENT_OBSERVED",
                "event_id": "review-9001",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": None,
            },
            current_reader=current_reader(lifecycle),
        )

        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertTrue(decision.ready_transition_already_performed)
        self.assertFalse(decision.request_review)
        self.assertFalse(decision.transition_to_draft)
        self.assertTrue(decision.stop_after_bounded_pass)

    def test_ready_recovery_requires_exact_bounded_authorization_and_stays_ready(self) -> None:
        lifecycle = current_lifecycle()
        request = {
            "event_kind": "RECOVERY_COMMIT_PUSHED",
            "event_id": "recovery-1",
            "pull_request": PR,
            "head_sha": NEXT_HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": None,
        }
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration.orchestrate_event(
                REPOSITORY,
                ISSUE,
                request,
                current_reader=current_reader(lifecycle),
            )

        request["authorization"] = {
            "authorization_id": "user-recovery-1",
            "operation": "EXCEPTIONAL_RECOVERY",
            "reason": "Correct the exact material post-Ready finding F-1",
            "scope": {
                "pull_request": PR,
                "predecessor_head_sha": HEAD,
                "resulting_head_sha": NEXT_HEAD,
                "finding_ids": ["F-1"],
            },
            "bounded_uses": 1,
        }
        decision = orchestration.orchestrate_event(
            REPOSITORY,
            ISSUE,
            request,
            current_reader=current_reader(lifecycle),
        )

        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_RECOVERY")
        self.assertTrue(decision.preserve_ready)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.requires_fresh_head_evidence)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)

    def test_replacement_rebinds_the_existing_exhausted_lifecycle(self) -> None:
        lifecycle = current_lifecycle()
        decision = orchestration.orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "PR_REPLACED",
                "event_id": "replacement-1",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": REPLACEMENT_PR,
                "classification": None,
                "follow_up": None,
                "authorization": {
                    "authorization_id": "user-replacement-1",
                    "operation": "PR_REBOUND",
                    "reason": "Recover delivery on the canonical replacement PR",
                    "scope": {
                        "predecessor_pull_request": PR,
                        "replacement_pull_request": REPLACEMENT_PR,
                        "head_sha": HEAD,
                    },
                    "bounded_uses": 1,
                },
            },
            current_reader=current_reader(lifecycle),
        )

        self.assertEqual(decision.lifecycle_transition, "PR_REBOUND")
        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.cycle_3_absent)


if __name__ == "__main__":
    main()
