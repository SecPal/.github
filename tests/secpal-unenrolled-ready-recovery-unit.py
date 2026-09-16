#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regressions for forward-only unenrolled Ready lifecycle recovery."""

from __future__ import annotations

import copy
from contextlib import nullcontext
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from scripts.secpal_pr_review import fast_path
from scripts.secpal_pr_review import bootstrap_source_admission as transport
from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_publication as publication


REPOSITORY = "SecPal/.github"
ISSUE = 956
PR = 957
SIGNER = "aroviqen@secpal.app"
OTHER_SIGNER = "other@secpal.app"
HEADS = [character * 40 for character in "abcdef1234567890"]
SECRET = b"unenrolled-ready-recovery-hermetic-signature"


def signer_for(identity: str = SIGNER) -> authority.Signer:
    def sign(payload: bytes, domain: str) -> dict[str, str]:
        value = hashlib.sha256(
            SECRET + identity.encode() + domain.encode() + payload
        ).hexdigest()
        return {"format": "ssh", "signer_identity": identity, "value": value}

    return sign


def verify_signature(
    payload: bytes,
    signature: dict[str, str],
    expected_signer: str,
    domain: str,
) -> authority.VerifiedSignature:
    expected = signer_for(expected_signer)(payload, domain)["value"]
    if (
        signature["value"] != expected
        or signature["signer_identity"] != expected_signer
    ):
        raise ValueError("invalid test signature")
    return authority.VerifiedSignature(expected_signer, signature["format"])


def state(*, remediation_cycles: int = 1) -> dict[str, object]:
    ready_observation = {
        "sequence": 1,
        "transition_kind": "DRAFT_TO_READY",
        "observation_digest": authority.digest_json(history()[2]),
    }
    return {
        "unrestricted_review_count": 1,
        "remediation_cycle_count": remediation_cycles,
        "cycle_3_absent": True,
        "draft": False,
        "ready": True,
        "ready_transition_count": 1,
        "ready_history": [ready_observation],
        "exceptional_recovery_count": 0,
        "exceptional_recovery_history": [],
        "exceptional_continuation_count": 0,
        "exceptional_continuation_history": [],
    }


def history() -> list[dict[str, object]]:
    return [
        {
            "sequence": 1,
            "kind": "PR_CREATED_DRAFT",
            "observed_at": "2026-09-16T18:00:00Z",
            "head_sha": HEADS[0],
            "reviewed_head_sha": None,
        },
        {
            "sequence": 2,
            "kind": "REVIEW_SUBMITTED",
            "observed_at": "2026-09-16T18:10:00Z",
            "head_sha": HEADS[1],
            "reviewed_head_sha": HEADS[1],
        },
        {
            "sequence": 3,
            "kind": "DRAFT_TO_READY_OBSERVED",
            "observed_at": "2026-09-16T18:20:00Z",
            "head_sha": HEADS[1],
            "reviewed_head_sha": None,
        },
        {
            "sequence": 4,
            "kind": "REMEDIATION_HEAD_OBSERVED",
            "observed_at": "2026-09-16T18:30:00Z",
            "head_sha": HEADS[2],
            "reviewed_head_sha": None,
        },
    ]


def validation(
    *,
    head: str = HEADS[2],
    parent: str = HEADS[1],
    tree: str = HEADS[4],
) -> fast_path.VerifiedValidationEvidence:
    reviewed = fast_path.StableFeedbackState(
        repository=REPOSITORY,
        pull_request_number=PR,
        head_sha=parent,
        base_ref="main",
        base_sha=HEADS[3],
        pr_state="OPEN",
        feedback={
            "pull_request_reactions": [],
            "reviews": [],
            "conversation_comments": [],
            "threads": [],
        },
    )
    registry = {"manual_gates": []}
    receipt = fast_path.create_validation_receipt(
        repository=REPOSITORY,
        head_sha=reviewed.head_sha,
        validated_tree_sha=tree,
        registry=registry,
        command_set=[],
        successful_result=True,
        reviewed_state=reviewed,
        manual_gate_evidence=[],
    )
    attestation = fast_path.create_validation_attestation(
        repository=REPOSITORY,
        head_sha=head,
        registry=registry,
        command_set=[],
        successful_result=True,
        reviewed_state=reviewed,
        validation_receipt=receipt,
    )
    return fast_path.verify_validation_attestation(
        attestation,
        repository=REPOSITORY,
        head_sha=head,
        registry=registry,
        command_set=[],
        reviewed_state=reviewed,
        commit_parent_sha=parent,
        commit_tree_sha=tree,
        commit_validation_receipt_digest=receipt["receipt_digest"],
    )


def commit(
    *, signer: str = SIGNER,
) -> authority.VerifiedUnenrolledReadySourceCommit:
    return authority._seal_unenrolled_ready_source_commit(
        repository=REPOSITORY,
        head_sha=HEADS[2],
        tree_sha=HEADS[4],
        parent_shas=[HEADS[1]],
        signer_identity=signer,
        signature_format="ssh",
        authentication_digest="9" * 64,
    )


def safety(*, base_sha: str = HEADS[3]) -> dict[str, object]:
    reviewed = fast_path.StableFeedbackState(
        repository=REPOSITORY,
        pull_request_number=PR,
        head_sha=HEADS[2],
        base_ref="main",
        base_sha=base_sha,
        pr_state="OPEN",
        feedback={
            "pull_request_reactions": [],
            "reviews": [],
            "conversation_comments": [],
            "threads": [],
        },
    )
    registry = {"manual_gates": [], "limits": {"maximum_items": 100}}
    receipt = fast_path.create_validation_receipt(
        repository=REPOSITORY,
        head_sha=HEADS[2],
        validated_tree_sha=HEADS[4],
        registry=registry,
        command_set=[],
        successful_result=True,
        reviewed_state=reviewed,
        manual_gate_evidence=[],
    )
    return fast_path.derive_ready_source_recovery_safety_facts(
        tooling_authority_main=HEADS[5],
        repository=REPOSITORY,
        pull_request_number=PR,
        head_sha=HEADS[2],
        tree_sha=HEADS[4],
        parent_shas=[HEADS[1]],
        expected_base_ref="main",
        expected_base_sha=base_sha,
        reviewed_state=reviewed,
        review_decision="NONE",
        feedback_findings=[],
        fresh_validation_receipt=receipt,
        registry=registry,
        command_set=[],
    )


def observation(**changes: object) -> authority.VerifiedUnenrolledReadyObservation:
    value = {
        "repository": REPOSITORY,
        "delivery_issue": ISSUE,
        "delivery_issue_state": "OPEN",
        "pull_request": PR,
        "pull_request_state": "OPEN",
        "pull_request_is_draft": False,
        "head_sha": HEADS[2],
        "tree_sha": HEADS[4],
        "parent_shas": [HEADS[1]],
        "expected_base_ref": "main",
        "observed_base_sha": HEADS[3],
        "observed_main_sha": HEADS[3],
        "journal_tip_oid": HEADS[5],
        "journal_tip_digest": "8" * 64,
        "lifecycle_root_status": "AUTHENTICATED_ABSENT",
        "current_publication_status": "AUTHENTICATED_ABSENT",
        "observed_history": history(),
        "review_provider_identities": ["copilot-pull-request-reviewer"],
    }
    value.update(changes)
    status_changes = {
        key: value.pop(key)
        for key in ("lifecycle_root_status", "current_publication_status")
        if key in changes
    }
    sealed = authority._seal_unenrolled_ready_observation(
        **{
            key: item
            for key, item in value.items()
            if key not in {"lifecycle_root_status", "current_publication_status"}
        }
    )
    if not status_changes:
        return sealed
    canonical = copy.deepcopy(sealed.canonical_observation)
    canonical.update(status_changes)
    return authority.VerifiedUnenrolledReadyObservation(
        canonical,
        authority._VERIFIED_UNENROLLED_READY_OBSERVATION,
    )


def policy() -> object:
    return type(
        "Policy",
        (),
        {
            "repository": REPOSITORY,
            "transition_signer_identities": frozenset({SIGNER}),
            "authority_signer_identities": frozenset({SIGNER}),
            "publication_signer_identities": frozenset({SIGNER}),
            "publication_branch": "refs/heads/secpal-lifecycle-publications",
            "publication_remote_url": "https://example.invalid/SecPal/.github.git",
        },
    )()


class UnenrolledReadyRecoveryTests(TestCase):
    def evidence(
        self,
        *,
        observation_changes: dict[str, object] | None = None,
        final_changes: dict[str, object] | None = None,
        **changes: object,
    ) -> object:
        arguments = {
            "initial_observation": observation(**(observation_changes or {})),
            "final_observation": observation(**(final_changes or {})),
            "expected_source_signer": SIGNER,
            "verified_source_commit": commit(),
            "validation_evidence": validation(),
            "recovery_safety_facts": safety(),
            "intended_state": state(),
            "observation_nonce": "recovery-observation-956-1",
        }
        arguments.update(changes)
        with patch.object(
            authority,
            "_load_delivery_signature_policy",
            return_value={
                "accepted_formats": ["ssh", "openpgp"],
                "require_github_verified": True,
            },
        ):
            return authority.authenticate_unenrolled_ready_recovery_evidence(
                **arguments
            )

    def signed_bundle(self) -> tuple[bytes, dict[str, object]]:
        evidence = self.evidence()
        authorization = authority.create_unenrolled_ready_recovery_authorization(
            verified_evidence=evidence,
            authorization_id="unenrolled-ready-recovery:956:1",
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        proof = authority.create_unenrolled_ready_recovery_proof(
            verified_evidence=evidence,
            authorization=authorization,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        return (
            authority.serialize_unenrolled_ready_recovery_evidence(
                recovery_proof=proof
            ),
            proof,
        )

    def signed_bundle_from_evidence(
        self, **changes: object
    ) -> tuple[bytes, dict[str, object]]:
        evidence = self.evidence().canonical_evidence
        evidence = copy.deepcopy(evidence)
        evidence.update(changes)
        evidence["recovery_evidence_digest"] = authority.digest_json(
            {
                key: value
                for key, value in evidence.items()
                if key != "recovery_evidence_digest"
            }
        )
        sealed = authority.VerifiedUnenrolledReadyRecoveryEvidence(
            evidence,
            authority._VERIFIED_UNENROLLED_READY_RECOVERY_EVIDENCE,
        )
        authorization = authority.create_unenrolled_ready_recovery_authorization(
            verified_evidence=sealed,
            authorization_id="unenrolled-ready-recovery:956:tamper-test",
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        proof = authority.create_unenrolled_ready_recovery_proof(
            verified_evidence=sealed,
            authorization=authorization,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        return authority.serialize_unenrolled_ready_recovery_evidence(
            recovery_proof=proof
        ), proof

    def test_exact_gap_establishes_one_forward_only_root(self) -> None:
        raw, proof = self.signed_bundle()
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
        ):
            verified = authority.verify_lifecycle_authority_for_publication(raw)

        self.assertEqual(verified.historical_proof_mode, "unenrolled_ready_recovery")
        self.assertTrue(verified.lifecycle_id.startswith("lifecycle-recovery:"))
        self.assertEqual(verified.state, state())
        self.assertEqual(verified.initialization_evidence_digest, proof["recovery_evidence_digest"])
        self.assertNotIn("READY_INTEGRATION_PRIOR_AUTHORITY", str(proof))
        self.assertNotIn("EXACT_STATE_ADOPTION", str(proof))
        self.assertFalse(proof["historical_lifecycle_authority_existed"])
        self.assertEqual(proof["authority_begins_at"], "RECOVERY_BOUNDARY")

    def test_live_observer_owns_issue_pr_source_main_and_absence_reads(self) -> None:
        responses = [
            {"state": "OPEN"},
            {
                "state": "OPEN",
                "isDraft": False,
                "headRefOid": HEADS[2],
                "baseRefName": "main",
                "baseRefOid": HEADS[3],
                "closingIssuesReferences": [{"number": ISSUE}],
            },
            {
                "sha": HEADS[2],
                "tree": {"sha": HEADS[4]},
                "parents": [{"sha": HEADS[1]}],
            },
            {"protected": True, "commit": {"sha": HEADS[3]}},
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "createdAt": "2026-09-16T18:00:00Z",
                            "timelineItems": {
                                "nodes": [
                                    {
                                        "__typename": "ReadyForReviewEvent",
                                        "createdAt": "2026-09-16T18:20:00Z",
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False},
                            },
                            "commits": {
                                "nodes": [
                                    {
                                        "commit": {
                                            "oid": HEADS[0],
                                            "committedDate": "2026-09-16T17:59:00Z",
                                        }
                                    },
                                    {
                                        "commit": {
                                            "oid": HEADS[1],
                                            "committedDate": "2026-09-16T18:05:00Z",
                                        }
                                    },
                                    {
                                        "commit": {
                                            "oid": HEADS[2],
                                            "committedDate": "2026-09-16T18:30:00Z",
                                        }
                                    },
                                ],
                                "pageInfo": {"hasNextPage": False},
                            },
                            "reviews": {
                                "nodes": [
                                    {
                                        "state": "COMMENTED",
                                        "submittedAt": "2026-09-16T18:10:00Z",
                                        "author": {
                                            "login": "copilot-pull-request-reviewer"
                                        },
                                        "commit": {"oid": HEADS[1]},
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False},
                            },
                        }
                    }
                }
            },
        ]
        completed = [
            subprocess.CompletedProcess([], 0, stdout=authority.canonical_json_bytes(item))
            for item in responses
        ]
        absence = publication.VerifiedPreEnrollmentAbsence(
            REPOSITORY,
            ISSUE,
            "refs/heads/secpal-lifecycle-publications",
            HEADS[5],
            "8" * 64,
        )
        with (
            patch.object(transport, "_run_bootstrap_gh", side_effect=completed) as reader,
            patch.object(publication, "verify_pre_enrollment_absence", return_value=absence),
        ):
            observed = authority.observe_unenrolled_ready_recovery_boundary(
                REPOSITORY, ISSUE, PR
            )
        self.assertEqual(reader.call_count, 5)
        self.assertEqual(observed.canonical_observation, observation().canonical_observation)

    def test_rejects_replay_and_scope_substitution(self) -> None:
        raw, proof = self.signed_bundle()
        authorization = copy.deepcopy(proof["authorization"])
        authorization["pull_request"] += 1
        proof["authorization"] = authorization
        tampered = authority.serialize_unenrolled_ready_recovery_evidence(
            recovery_proof=proof
        )
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
        ):
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError, "authorization"
            ):
                authority.verify_lifecycle_authority_for_publication(tampered)

        self.assertNotEqual(raw, tampered)

    def test_rejects_ready_churn_and_budget_reset(self) -> None:
        changed_history = history()
        changed_history.insert(
            3,
            {
                "sequence": 4,
                "kind": "READY_TO_DRAFT_OBSERVED",
                "observed_at": "2026-09-16T18:25:00Z",
                "head_sha": HEADS[0],
                "reviewed_head_sha": None,
            },
        )
        for sequence, item in enumerate(changed_history, 1):
            item["sequence"] = sequence
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.evidence(
                observation_changes={"observed_history": changed_history},
                final_changes={"observed_history": changed_history},
                intended_state=state(remediation_cycles=0),
                observation_nonce="recovery-observation-956-2",
            )

    def test_rejects_ineligible_live_states_and_toctou_drift(self) -> None:
        cases = (
            {"observation_changes": {"pull_request_is_draft": True}},
            {"observation_changes": {"pull_request_state": "CLOSED"}},
            {"observation_changes": {"pull_request_state": "MERGED"}},
            {"observation_changes": {"delivery_issue_state": "CLOSED"}},
            {"observation_changes": {"observed_main_sha": HEADS[6]}},
            {"final_changes": {"head_sha": HEADS[6]}},
            {
                "final_changes": {"observed_main_sha": HEADS[6]}
            },
            {
                "final_changes": {"lifecycle_root_status": "PRESENT"}
            },
            {
                "final_changes": {"current_publication_status": "PRESENT"}
            },
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    self.evidence(**mutation)

    def test_rejects_wrong_source_signer_and_validation_identity(self) -> None:
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.evidence(verified_source_commit=commit(signer=OTHER_SIGNER))
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.evidence(
                observation_changes={"head_sha": HEADS[6]},
                final_changes={"head_sha": HEADS[6]},
            )

    def test_rejects_incomplete_feedback_and_authorization_signer(self) -> None:
        incomplete = safety()
        incomplete["feedback_assessment_digest"] = "0" * 64
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.evidence(recovery_safety_facts=incomplete)

        evidence = self.evidence()
        authorization = authority.create_unenrolled_ready_recovery_authorization(
            verified_evidence=evidence,
            authorization_id="unenrolled-ready-recovery:956:wrong-signer",
            signer_identity=OTHER_SIGNER,
            signer=signer_for(OTHER_SIGNER),
        )
        proof = authority.create_unenrolled_ready_recovery_proof(
            verified_evidence=evidence,
            authorization=authorization,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        raw = authority.serialize_unenrolled_ready_recovery_evidence(
            recovery_proof=proof
        )
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            self.assertRaises(authority.LifecycleAuthorityError),
        ):
            authority.verify_lifecycle_authority_for_publication(raw)

    def test_existing_ready_prior_authority_shape_accepts_recovered_current(self) -> None:
        prior = {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
            "repository": REPOSITORY,
            "delivery_issue_number": ISSUE,
            "pull_request_number": PR,
            "prior_delivery_head_sha": HEADS[2],
            "prior_delivery_tree_sha": HEADS[4],
            "prior_validation_receipt_digest": "1" * 64,
            "prior_final_attestation_digest": "2" * 64,
            "expected_signer": {
                "kind": "SSH_PRINCIPAL",
                "identity": SIGNER,
            },
            "lifecycle": {
                "identity": "lifecycle-recovery:" + "3" * 64,
                "current_authority_digest": "4" * 64,
                "historical_proof_mode": "unenrolled_ready_recovery",
                "draft": False,
                "ready": True,
                "ready_transition": False,
                "unrestricted_reviews": 1,
                "remediation_cycles": 1,
                "exceptional_recoveries": 0,
                "exceptional_continuations": 0,
                "cycle_3": False,
            },
            "publication": {
                "object_oid": HEADS[5],
                "publication_digest": "5" * 64,
            },
        }
        normalized = fast_path.normalize_ready_integration_prior_authority(prior)
        self.assertEqual(
            normalized["lifecycle"]["historical_proof_mode"],
            "unenrolled_ready_recovery",
        )

    def test_head_advanced_uses_ordinary_successor_and_preserves_budgets(self) -> None:
        raw, proof = self.signed_bundle()
        lifecycle_id = proof["lifecycle_id"]
        event = authority.create_transition_authorization(
            event_id="authorization:ready-integration-after-recovery",
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle_id=lifecycle_id,
            pull_request=PR,
            predecessor_authority_digest=proof["proof_digest"],
            predecessor_head_sha=HEADS[2],
            resulting_head_sha=HEADS[6],
            transition_kind="HEAD_ADVANCED",
            replacement_pull_request=None,
            initialization_evidence_digest=proof["recovery_evidence_digest"],
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
        ):
            snapshot = authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=raw,
                authorization=event,
                signer_identity=SIGNER,
                authority_signer=signer_for(),
                current_head_evidence=validation(
                    head=HEADS[6], parent=HEADS[2], tree=HEADS[7]
                ),
            )
            successor = authority.serialize_unenrolled_ready_recovery_evidence(
                recovery_proof=proof,
                transition_authorizations=[event],
                authority_chain=[snapshot],
            )
            verified = authority._verify_lifecycle_authority_for_journal(successor)

        self.assertEqual(verified.head_sha, HEADS[6])
        self.assertEqual(verified.state, state())
        self.assertEqual(
            verified.historical_proof_mode, "unenrolled_ready_recovery"
        )

    def test_direct_prior_authority_substitution_remains_rejected(self) -> None:
        prior = {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
            "repository": REPOSITORY,
        }
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.normalize_ready_integration_prior_authority(prior)

    def test_existing_root_rejects_recovery_replay_and_second_root(self) -> None:
        raw, _ = self.signed_bundle()
        current = object()
        latest = {(REPOSITORY, ISSUE): (HEADS[6], {}, current)}
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            patch.object(publication, "_verify_live_protection"),
            patch.object(
                publication,
                "_isolated_repository",
                return_value=nullcontext((Path("/tmp/unused"), {})),
            ),
            patch.object(publication, "_observe_remote_current_once", return_value=HEADS[5]),
            patch.object(publication, "_walk_journal", return_value=([], latest, {})),
            self.assertRaisesRegex(
                publication.LifecyclePublicationError, "already enrolled"
            ),
        ):
            publication.enroll_existing_lifecycle(
                raw, signer_identity=SIGNER, signer=signer_for()
            )

    def test_publication_rejects_journal_drift_after_authorization(self) -> None:
        raw, _ = self.signed_bundle()
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            patch.object(publication, "_verify_live_protection"),
            patch.object(
                publication,
                "_isolated_repository",
                return_value=nullcontext((Path("/tmp/unused"), {})),
            ),
            patch.object(publication, "_observe_remote_current_once", return_value=HEADS[6]),
            self.assertRaisesRegex(
                publication.LifecyclePublicationError, "journal authority drifted"
            ),
        ):
            publication.enroll_existing_lifecycle(
                raw, signer_identity=SIGNER, signer=signer_for()
            )

    def test_recovery_requires_verifier_sealed_source_commit(self) -> None:
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "verifier-authenticated"
        ):
            self.evidence(verified_source_commit={"head_sha": HEADS[2]})

    def test_source_commit_seal_is_emitted_by_maintained_crypto_reader(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution

        authenticated = SimpleNamespace(
            repository=REPOSITORY,
            head_sha=HEADS[2],
            tree_sha=HEADS[4],
            parent_shas=(HEADS[1],),
            signer_identity=SIGNER,
            signer_kind="SSH_PRINCIPAL",
            authentication_digest="9" * 64,
        )
        with patch.object(
            lifecycle_execution,
            "_authenticate_source_commit",
            return_value=authenticated,
        ) as reader:
            verified = authority.authenticate_unenrolled_ready_source_commit(
                REPOSITORY, HEADS[2], SIGNER
            )
        reader.assert_called_once_with(REPOSITORY, HEADS[2], SIGNER)
        self.assertEqual(verified.tree_sha, HEADS[4])
        self.assertEqual(verified.parent_shas, (HEADS[1],))

    def test_serialized_proof_rechecks_ready_only_state_and_root_identity(self) -> None:
        invalid_state = state(remediation_cycles=1)
        invalid_state.update(
            {
                "draft": True,
                "ready": False,
                "ready_transition_count": 0,
                "ready_history": [],
            }
        )
        invalid_history = history()
        invalid_history.pop(2)
        for sequence, item in enumerate(invalid_history, 1):
            item["sequence"] = sequence
        raw, _ = self.signed_bundle_from_evidence(
            intended_state=invalid_state,
            intended_state_digest=authority.digest_json(invalid_state),
            observed_history=invalid_history,
            observed_history_digest=authority.digest_json(invalid_history),
        )
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            self.assertRaises(authority.LifecycleAuthorityError),
        ):
            authority.verify_lifecycle_authority_for_publication(raw)

        raw, proof = self.signed_bundle()
        proof["lifecycle_id"] = "lifecycle-recovery:" + "0" * 64
        signed = {key: value for key, value in proof.items() if key != "proof_digest"}
        signed["signature"] = signer_for()(
            authority.canonical_json_bytes(
                {key: value for key, value in signed.items() if key != "signature"}
            ),
            authority.UNENROLLED_READY_RECOVERY_PROOF_DOMAIN,
        )
        proof = {**signed, "proof_digest": authority.digest_json(signed)}
        raw = authority.serialize_unenrolled_ready_recovery_evidence(
            recovery_proof=proof
        )
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            self.assertRaisesRegex(authority.LifecycleAuthorityError, "lifecycle identity"),
        ):
            authority.verify_lifecycle_authority_for_publication(raw)

    def test_rejects_review_after_ready_and_untrusted_or_dismissed_review(self) -> None:
        changed = history()
        changed[1]["observed_at"] = "2026-09-16T18:25:00Z"
        changed[2]["observed_at"] = "2026-09-16T18:20:00Z"
        changed[1], changed[2] = changed[2], changed[1]
        for sequence, item in enumerate(changed, 1):
            item["sequence"] = sequence
        changed_state = state()
        changed_state["ready_history"] = [
            {
                "sequence": 1,
                "transition_kind": "DRAFT_TO_READY",
                "observation_digest": authority.digest_json(changed[1]),
            }
        ]
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "precede Ready"):
            self.evidence(
                observation_changes={"observed_history": changed},
                final_changes={"observed_history": changed},
                intended_state=changed_state,
            )

        for review_state, reviewer in (
            ("COMMENTED", "untrusted-reviewer"),
            ("DISMISSED", "copilot-pull-request-reviewer"),
        ):
            chronology = {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "createdAt": "2026-09-16T18:00:00Z",
                            "timelineItems": {"nodes": [{"__typename": "ReadyForReviewEvent", "createdAt": "2026-09-16T18:20:00Z"}], "pageInfo": {"hasNextPage": False}},
                            "commits": {"nodes": [{"commit": {"oid": HEADS[1], "committedDate": "2026-09-16T18:05:00Z"}}, {"commit": {"oid": HEADS[2], "committedDate": "2026-09-16T18:30:00Z"}}], "pageInfo": {"hasNextPage": False}},
                            "reviews": {"nodes": [{"state": review_state, "submittedAt": "2026-09-16T18:10:00Z", "author": {"login": reviewer}, "commit": {"oid": HEADS[1]}}], "pageInfo": {"hasNextPage": False}},
                        }
                    }
                }
            }
            with self.subTest(review_state=review_state, reviewer=reviewer), self.assertRaises(authority.LifecycleAuthorityError):
                authority._derive_unenrolled_ready_history(chronology, HEADS[2])

    def test_serialized_proof_rechecks_safety_identity(self) -> None:
        changed_safety = safety(base_sha=HEADS[6])
        raw, _ = self.signed_bundle_from_evidence(
            recovery_safety_facts=changed_safety,
            recovery_safety_facts_digest=changed_safety["safety_facts_digest"],
        )
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            self.assertRaisesRegex(authority.LifecycleAuthorityError, "delivery identity"),
        ):
            authority.verify_lifecycle_authority_for_publication(raw)

    def test_publication_reobserves_live_boundary_before_cas(self) -> None:
        raw, _ = self.signed_bundle()
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            patch.object(publication, "_verify_live_protection"),
            patch.object(publication, "_isolated_repository", return_value=nullcontext((Path("/tmp/unused"), {}))),
            patch.object(publication, "_observe_remote_current_once", return_value=HEADS[5]),
            patch.object(publication, "_walk_journal", return_value=([], {}, {})),
            patch.object(publication, "_write_publication_object", return_value=HEADS[6]),
            patch.object(publication, "_verify_publication_document", return_value=({}, object())),
            patch.object(authority, "observe_unenrolled_ready_recovery_boundary", return_value=observation(head_sha=HEADS[6])) as observe,
            patch.object(publication, "_cas_remote_ref") as cas,
            self.assertRaisesRegex(publication.LifecyclePublicationError, "live boundary drifted"),
        ):
            publication.enroll_existing_lifecycle(raw, signer_identity=SIGNER, signer=signer_for())
        observe.assert_called_once_with(REPOSITORY, ISSUE, PR)
        cas.assert_not_called()

    def test_publication_reobserves_and_establishes_exactly_one_current(self) -> None:
        raw, _ = self.signed_bundle()
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
        ):
            lifecycle = authority.verify_lifecycle_authority_for_publication(raw)
        document = {"publication_digest": "7" * 64}
        with (
            patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy()),
            patch.object(authority, "_policy_signature_verifier", return_value=verify_signature),
            patch.object(publication, "_verify_live_protection"),
            patch.object(publication, "_isolated_repository", return_value=nullcontext((Path("/tmp/unused"), {}))),
            patch.object(publication, "_observe_remote_current_once", return_value=HEADS[5]),
            patch.object(publication, "_walk_journal", return_value=([], {}, {})),
            patch.object(publication, "_write_publication_object", return_value=HEADS[6]),
            patch.object(publication, "_verify_publication_document", return_value=(document, lifecycle)),
            patch.object(authority, "observe_unenrolled_ready_recovery_boundary", return_value=observation()) as observe,
            patch.object(publication, "_cas_remote_ref") as cas,
        ):
            current = publication.enroll_existing_lifecycle(
                raw, signer_identity=SIGNER, signer=signer_for()
            )
        self.assertEqual(current.publication_oid, HEADS[6])
        self.assertEqual(current.lifecycle.lifecycle_id, lifecycle.lifecycle_id)
        observe.assert_called_once_with(REPOSITORY, ISSUE, PR)
        cas.assert_called_once()


if __name__ == "__main__":
    main()
