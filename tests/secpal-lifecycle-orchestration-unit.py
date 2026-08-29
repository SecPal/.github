#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for finite delivery-lifecycle orchestration."""

from __future__ import annotations

import copy
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_orchestration as orchestration

REPOSITORY = "SecPal/.github"
ISSUE = 692
PR = 800
REPLACEMENT_PR = 801
HEAD = "a" * 40
NEXT_HEAD = "b" * 40
LIFECYCLE = "lifecycle:" + "c" * 64


def current_lifecycle(
    *,
    ready: bool = True,
    ready_regressed: bool = False,
    exceptional_recoveries: int = 0,
    exceptional_continuations: int = 0,
    head_sha: str = HEAD,
    remediation_cycles: int = 2,
) -> authority.VerifiedLifecycleAuthority:
    state = authority.initial_state()
    state.update(
        {
            "unrestricted_review_count": 1,
            "remediation_cycle_count": remediation_cycles,
            "draft": not ready,
            "ready": ready,
            "ready_transition_count": 1 if ready or ready_regressed else 0,
            "ready_history": (
                [
                    {
                        "sequence": 1,
                        "transition_kind": "DRAFT_TO_READY",
                        "event_authorization_digest": "d" * 64,
                    }
                ]
                if ready or ready_regressed
                else []
            ),
            "exceptional_recovery_count": exceptional_recoveries,
            "exceptional_recovery_history": [
                {
                    "sequence": 1,
                    "transition_kind": "EXCEPTIONAL_RECOVERY",
                    "event_authorization_digest": "9" * 64,
                }
            ][:exceptional_recoveries],
            "exceptional_continuation_count": exceptional_continuations,
            "exceptional_continuation_history": [
                {
                    "sequence": 1,
                    "transition_kind": "EXCEPTIONAL_CONTINUATION",
                    "event_authorization_digest": "8" * 64,
                }
            ][:exceptional_continuations],
        }
    )
    if ready_regressed:
        state["ready_history"].append(
            {
                "sequence": 2,
                "transition_kind": "READY_TO_DRAFT",
                "event_authorization_digest": "7" * 64,
            }
        )
    return authority.VerifiedLifecycleAuthority(
        authority_digest="e" * 64,
        repository=REPOSITORY,
        delivery_issue=ISSUE,
        lifecycle_id=LIFECYCLE,
        initialization_evidence_digest="f" * 64,
        pull_request=PR,
        head_sha=head_sha,
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
    def test_public_orchestrator_accepts_no_consumer_authority_sources(self) -> None:
        self.assertEqual(
            list(inspect.signature(orchestration.orchestrate_event).parameters),
            ["repository", "delivery_issue", "request"],
        )

    def test_review_event_is_bounded_evidence_not_a_lifecycle_transition(self) -> None:
        lifecycle = current_lifecycle()
        decision = orchestration._orchestrate_event(
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
            orchestration._orchestrate_event(
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
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            request,
            current_reader=current_reader(lifecycle),
        )

        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_RECOVERY")
        self.assertEqual(decision.resulting_head_sha, NEXT_HEAD)
        self.assertTrue(decision.preserve_ready)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.requires_fresh_head_evidence)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)

    def test_bounded_normal_remediation_changes_ready_head_in_place(self) -> None:
        lifecycle = current_lifecycle(remediation_cycles=1)
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "REMEDIATION_COMMIT_PUSHED",
                "event_id": "remediation-2",
                "pull_request": PR,
                "head_sha": NEXT_HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": {
                    "authorization_id": "bounded-remediation-2",
                    "operation": "REMEDIATION_COMPLETED",
                    "reason": "Correct the exact authorized Cycle-2 findings",
                    "scope": {
                        "pull_request": PR,
                        "predecessor_head_sha": HEAD,
                        "resulting_head_sha": NEXT_HEAD,
                        "finding_ids": ["F-C2-1"],
                    },
                    "bounded_uses": 1,
                },
            },
            current_reader=current_reader(lifecycle),
        )

        self.assertEqual(decision.lifecycle_transition, "REMEDIATION_COMPLETED")
        self.assertEqual(decision.resulting_head_sha, NEXT_HEAD)
        self.assertTrue(decision.preserve_ready)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.requires_fresh_head_evidence)

    def test_replacement_rebinds_the_existing_exhausted_lifecycle(self) -> None:
        lifecycle = current_lifecycle()
        decision = orchestration._orchestrate_event(
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
        self.assertEqual(decision.resulting_pull_request, REPLACEMENT_PR)
        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.cycle_3_absent)

    def test_ci_reopen_and_ready_integration_observations_create_no_cycle(self) -> None:
        lifecycle = current_lifecycle(exceptional_continuations=1)
        for event_kind in (
            "CI_OBSERVED",
            "PR_REOPENED",
            "READY_INTEGRATION_VALIDATED",
        ):
            with self.subTest(event_kind=event_kind):
                decision = orchestration._orchestrate_event(
                    REPOSITORY,
                    ISSUE,
                    {
                        "event_kind": event_kind,
                        "event_id": f"observation-{event_kind}",
                        "pull_request": PR,
                        "head_sha": HEAD,
                        "replacement_pull_request": None,
                        "classification": None,
                        "follow_up": None,
                        "authorization": None,
                    },
                    current_reader=current_reader(lifecycle),
                )
                self.assertIsNone(decision.lifecycle_transition)
                self.assertEqual(decision.remediation_cycles, 2)
                self.assertEqual(decision.exceptional_continuations, 1)
                self.assertFalse(decision.request_review)
                self.assertFalse(decision.transition_to_draft)
                self.assertFalse(decision.transition_to_ready)

    def test_material_post_ready_finding_blocks_without_cycle_three(self) -> None:
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "LATE_FEEDBACK_CLASSIFIED",
                "event_id": "finding-material-1",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": {
                    "classification": "IN_CONTRACT_DEFECT",
                    "technically_blocking": True,
                    "mechanically_blocking": True,
                    "timing": "AFTER_FREEZE",
                    "risk": ["P2", "INTEGRITY"],
                },
                "follow_up": None,
                "authorization": None,
            },
            current_reader=current_reader(current_lifecycle()),
        )

        self.assertTrue(decision.technically_blocking)
        self.assertTrue(decision.mechanically_blocking)
        self.assertFalse(decision.merge_ready)
        self.assertTrue(decision.explicit_recovery_required)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.cycle_3_absent)

    def test_authenticated_tracked_follow_up_is_not_reported_as_fixed(self) -> None:
        observed = []

        def verify(identity):
            observed.append(identity)
            return SimpleNamespace(identity=identity, open=True, structurally_complete=True)

        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "LATE_FEEDBACK_CLASSIFIED",
                "event_id": "finding-follow-up-1",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": {
                    "classification": "NON_BLOCKING_FOLLOWUP",
                    "technically_blocking": False,
                    "mechanically_blocking": True,
                    "timing": "AFTER_FREEZE",
                    "risk": ["P3"],
                },
                "follow_up": {
                    "repository": "SecPal/.github",
                    "issue_number": 674,
                    "issue_url": "https://github.com/SecPal/.github/issues/674",
                },
                "authorization": None,
            },
            current_reader=current_reader(current_lifecycle()),
            follow_up_verifier=verify,
        )

        self.assertEqual(len(observed), 1)
        self.assertFalse(decision.technically_blocking)
        self.assertTrue(decision.mechanically_blocking)
        self.assertFalse(decision.resolution_eligible)
        self.assertTrue(decision.guarded_resolution_candidate)
        self.assertTrue(decision.authenticated_resolution_required)
        self.assertEqual(
            decision.resolution_meaning_if_applied,
            "SAFELY_DISPOSITIONED_TRACKED",
        )
        self.assertNotIn(
            decision.resolution_meaning_if_applied,
            {"FIXED", "IMPLEMENTED", "COMPLETED"},
        )

    def test_high_risk_finding_cannot_be_converted_to_follow_up(self) -> None:
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                {
                    "event_kind": "LATE_FEEDBACK_CLASSIFIED",
                    "event_id": "finding-security-1",
                    "pull_request": PR,
                    "head_sha": HEAD,
                    "replacement_pull_request": None,
                    "classification": {
                        "classification": "NON_BLOCKING_FOLLOWUP",
                        "technically_blocking": False,
                        "mechanically_blocking": True,
                        "timing": "AFTER_FREEZE",
                        "risk": ["SECURITY"],
                    },
                    "follow_up": {
                        "repository": "SecPal/.github",
                        "issue_number": 674,
                        "issue_url": "https://github.com/SecPal/.github/issues/674",
                    },
                    "authorization": None,
                },
                current_reader=current_reader(current_lifecycle()),
            )

    def test_ready_to_draft_requires_exact_user_reason_and_authorization(self) -> None:
        base = {
            "event_kind": "READY_TO_DRAFT",
            "event_id": "draft-regression-1",
            "pull_request": PR,
            "head_sha": HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": None,
        }
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                base,
                current_reader=current_reader(current_lifecycle()),
            )
        base["authorization"] = {
            "authorization_id": "user-draft-1",
            "operation": "READY_TO_DRAFT",
            "reason": "Pause this exact PR for a user-controlled contract reassessment",
            "scope": {"pull_request": PR, "head_sha": HEAD},
            "bounded_uses": 1,
        }
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            base,
            current_reader=current_reader(current_lifecycle()),
        )
        self.assertEqual(decision.lifecycle_transition, "READY_TO_DRAFT")
        self.assertTrue(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)

    def test_ready_after_user_draft_regression_requires_separate_authorization(self) -> None:
        regressed = current_lifecycle(ready=False, ready_regressed=True)
        request = {
            "event_kind": "DRAFT_TO_READY",
            "event_id": "ready-again-1",
            "pull_request": PR,
            "head_sha": HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": {
                "authorization_id": "user-ready-again-1",
                "operation": "DRAFT_TO_READY",
                "reason": "Resume this exact PR after the separately authorized pause",
                "scope": {"pull_request": PR, "head_sha": HEAD},
                "bounded_uses": 1,
            },
        }
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            request,
            current_reader=current_reader(regressed),
        )
        self.assertEqual(decision.lifecycle_transition, "DRAFT_TO_READY")
        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.transition_to_ready)

    def test_one_additional_review_is_authorized_without_counter_change(self) -> None:
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "ADDITIONAL_REVIEW_AUTHORIZED",
                "event_id": "bounded-review-1",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": {
                    "authorization_id": "user-review-1",
                    "operation": "ADDITIONAL_REVIEW",
                    "reason": "Assess the exact current head once after recovery",
                    "scope": {
                        "pull_request": PR,
                        "head_sha": HEAD,
                        "observation_id": "bounded-review-1",
                    },
                    "bounded_uses": 1,
                },
            },
            current_reader=current_reader(current_lifecycle()),
        )
        self.assertTrue(decision.additional_review_authorized)
        self.assertTrue(decision.stop_after_bounded_pass)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertFalse(decision.request_review)

    def test_exhausted_exceptional_recovery_is_not_a_generic_escape_hatch(self) -> None:
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                {
                    "event_kind": "RECOVERY_COMMIT_PUSHED",
                    "event_id": "recovery-2",
                    "pull_request": PR,
                    "head_sha": NEXT_HEAD,
                    "replacement_pull_request": None,
                    "classification": None,
                    "follow_up": None,
                    "authorization": {
                        "authorization_id": "user-recovery-2",
                        "operation": "EXCEPTIONAL_RECOVERY",
                        "reason": "Attempt a second bounded recovery",
                        "scope": {
                            "pull_request": PR,
                            "predecessor_head_sha": HEAD,
                            "resulting_head_sha": NEXT_HEAD,
                            "finding_ids": ["F-2"],
                        },
                        "bounded_uses": 1,
                    },
                },
                current_reader=current_reader(
                    current_lifecycle(exceptional_recoveries=1)
                ),
            )

    def test_automated_review_on_recovery_head_is_one_non_recursive_pass(self) -> None:
        recovered = current_lifecycle(
            exceptional_recoveries=1,
            head_sha=NEXT_HEAD,
        )
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "REVIEW_EVENT_OBSERVED",
                "event_id": "configured-review-on-recovery-head",
                "pull_request": PR,
                "head_sha": NEXT_HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": None,
            },
            current_reader=current_reader(recovered),
        )

        self.assertEqual(decision.head_sha, NEXT_HEAD)
        self.assertTrue(decision.ready)
        self.assertTrue(decision.ready_transition_already_performed)
        self.assertEqual(decision.exceptional_recoveries, 1)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertFalse(decision.request_review)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.stop_after_bounded_pass)


if __name__ == "__main__":
    main()
