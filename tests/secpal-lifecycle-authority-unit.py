#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for persistent delivery lifecycle authority."""

from __future__ import annotations

import ast
from contextlib import nullcontext
import copy
from dataclasses import replace
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import TestCase, main
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import fast_path

REPOSITORY = "SecPal/.github"
ISSUE = 750
PR = 751
INITIALIZATION_DIGEST = "0" * 64
LIFECYCLE = authority.delivery_initialization_lifecycle_id(INITIALIZATION_DIGEST)
SIGNER = "aroviqen@secpal.app"
OTHER_SIGNER = "other@secpal.app"
HEADS = [character * 40 for character in "abcdef1234567890"]
TRUST_SECRET = b"hermetic-trusted-signature-adapter"


def signer_for(identity: str = SIGNER) -> authority.Signer:
    def sign(payload: bytes, domain: str) -> dict[str, str]:
        value = hashlib.sha256(
            TRUST_SECRET + identity.encode() + domain.encode() + payload
        ).hexdigest()
        return {"format": "ssh", "signer_identity": identity, "value": value}

    return sign


def verify_signature(
    payload: bytes,
    signature: dict[str, Any],
    expected_signer: str,
    domain: str,
) -> authority.VerifiedSignature:
    expected = signer_for(expected_signer)(payload, domain)["value"]
    if signature["value"] != expected or signature["signer_identity"] != expected_signer:
        raise ValueError("invalid test signature")
    return authority.VerifiedSignature(expected_signer, signature["format"])


class Chain:
    def __init__(self) -> None:
        self.authorities: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.pull_request = PR
        self.head = HEADS[0]
        self.event_number = 0

    def append(
        self,
        transition: str,
        *,
        head: str | None = None,
        replacement_pull_request: int | None = None,
        event_signer: str = SIGNER,
        authority_signer: str = SIGNER,
    ) -> dict[str, Any]:
        self.event_number += 1
        genesis = not self.authorities
        resulting_head = head or self.head
        event = authority.create_transition_authorization(
            event_id=(
                f"genesis:{INITIALIZATION_DIGEST}"
                if genesis
                else f"event-{self.event_number}"
            ),
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle_id=LIFECYCLE,
            pull_request=self.pull_request,
            predecessor_authority_digest=None if genesis else self.authorities[-1]["authority_digest"],
            predecessor_head_sha=None if genesis else self.head,
            resulting_head_sha=resulting_head,
            transition_kind=transition,
            replacement_pull_request=replacement_pull_request,
            initialization_evidence_digest=INITIALIZATION_DIGEST,
            signer_identity=event_signer,
            signer=signer_for(event_signer),
        )
        snapshot = authority.issue_lifecycle_authority(
            predecessor_chain=self.authorities,
            transition_authorizations=self.events,
            authorization=event,
            signer_identity=authority_signer,
            authority_signer=signer_for(authority_signer),
            accepted_event_signers=frozenset({SIGNER, event_signer}),
            accepted_authority_signers=frozenset({SIGNER, authority_signer}),
            signature_verifier=verify_signature,
        )
        self.events.append(event)
        self.authorities.append(snapshot)
        self.head = resulting_head
        if replacement_pull_request is not None:
            self.pull_request = replacement_pull_request
        return snapshot

    def verify(
        self, expected: authority.ExpectedLifecycle | None = None
    ) -> authority.VerifiedLifecycleAuthority:
        return authority._verify_lifecycle_authority_objects(
            self.authorities,
            self.events,
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=verify_signature,
            expected=expected,
        )


def genesis_chain() -> Chain:
    chain = Chain()
    chain.append("INITIALIZED_DRAFT")
    return chain


def reviewed_chain() -> Chain:
    chain = genesis_chain()
    chain.append("UNRESTRICTED_REVIEW_CONSUMED")
    return chain


def ready_chain() -> Chain:
    chain = reviewed_chain()
    chain.append("REMEDIATION_COMPLETED", head=HEADS[1])
    chain.append("DRAFT_TO_READY")
    return chain


def resign_authority(value: dict[str, Any], identity: str = SIGNER) -> dict[str, Any]:
    fields = copy.deepcopy(value)
    fields.pop("authority_digest", None)
    fields.pop("signature", None)
    fields["signer_identity"] = identity
    fields["signature"] = signer_for(identity)(
        authority.canonical_json_bytes(fields), authority.AUTHORITY_DOMAIN
    )
    fields["authority_digest"] = authority.digest_json(fields)
    return fields


def resign_event(value: dict[str, Any], identity: str = SIGNER) -> dict[str, Any]:
    fields = copy.deepcopy(value)
    fields.pop("event_digest", None)
    fields.pop("signature", None)
    fields["signer_identity"] = identity
    fields["signature"] = signer_for(identity)(
        authority.canonical_json_bytes(fields), authority.EVENT_DOMAIN
    )
    fields["event_digest"] = authority.digest_json(fields)
    return fields


def verify_raw(authorities: list[dict[str, Any]], events: list[dict[str, Any]]) -> Any:
    return authority._verify_lifecycle_authority_objects(
        authorities,
        events,
        accepted_event_signers=frozenset({SIGNER}),
        accepted_authority_signers=frozenset({SIGNER}),
        signature_verifier=verify_signature,
    )


def authenticated_external_evidence(
    *,
    observed: list[dict[str, Any]],
    state: dict[str, Any],
    repository: str = "Example/governance",
    delivery_issue: int = 41,
    pull_request: int = 42,
    admit_review_budget: bool = False,
    adoption_timestamp: str = "2026-08-03T00:00:00Z",
) -> authority.VerifiedExactStateAdoptionExternalEvidence:
    reviewed = fast_path.StableFeedbackState(
        repository=repository, pull_request_number=pull_request,
        head_sha=HEADS[1], base_ref="main", base_sha=HEADS[0],
        pr_state="OPEN", feedback={
            "pull_request_reactions": [], "reviews": [],
            "conversation_comments": [], "threads": [],
        },
    )
    registry = {"manual_gates": []}
    receipt = fast_path.create_validation_receipt(
        repository=repository, head_sha=reviewed.head_sha,
        validated_tree_sha=HEADS[3], registry=registry, command_set=[],
        successful_result=True, reviewed_state=reviewed,
        manual_gate_evidence=[],
    )
    attestation = fast_path.create_validation_attestation(
        repository=repository, head_sha=HEADS[2], registry=registry,
        command_set=[], successful_result=True, reviewed_state=reviewed,
        validation_receipt=receipt,
    )
    validation = fast_path.verify_validation_attestation(
        attestation, repository=repository, head_sha=HEADS[2],
        registry=registry, command_set=[], reviewed_state=reviewed,
        commit_parent_sha=HEADS[1], commit_tree_sha=HEADS[3],
        commit_validation_receipt_digest=receipt["receipt_digest"],
    )
    commit = {
        "oid": HEADS[2],
        "source": "USER",
        "signer_identity": SIGNER,
        "local_signature": {
            "verified": True, "state": "valid", "format": "ssh",
        },
        "github_verification": {"verified": True, "reason": "valid"},
    }
    review_budget_admission = None
    if admit_review_budget:
        verified_commit = fast_path.verify_commit_signatures(
            [commit],
            {
                "accepted_formats": ["ssh", "openpgp"],
                "require_github_verified": True,
            },
        )[0]
        review_budget_admission = (
            authority.create_pre_enrollment_review_budget_consumption_admission(
                admission_id="pre-enrollment-review-budget:generic-41",
                repository=repository,
                delivery_issue=delivery_issue,
                pull_request=pull_request,
                head_sha=HEADS[2],
                tree_sha=HEADS[3],
                pull_request_state="OPEN",
                commit_signature_evidence_digest=authority.digest_json(
                    verified_commit
                ),
                validation_receipt_digest=validation.validation_receipt_digest,
                source_validation_evidence_digest=(
                    validation.source_validation_evidence_digest
                ),
                adoption_source_evidence_digest=(
                    validation.final_attestation_digest
                ),
                observed_pre_enrollment_history=observed,
                intended_state=state,
                adoption_timestamp=adoption_timestamp,
                signer_identity=SIGNER,
                signer=signer_for(),
            )
        )
    with patch.object(
        authority,
        "_load_delivery_signature_policy",
        return_value={
            "accepted_formats": ["ssh", "openpgp"],
            "require_github_verified": True,
        },
    ):
        arguments = dict(
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            head_sha=HEADS[2],
            tree_sha=HEADS[3],
            pull_request_state="OPEN",
            commit_signature_evidence=commit,
            validation_evidence=validation,
            observed_pre_enrollment_history=observed,
            intended_state=state,
        )
        if review_budget_admission is not None:
            arguments["review_budget_consumption_admission"] = (
                review_budget_admission
            )
        return authority.authenticate_exact_state_adoption_external_evidence(
            **arguments
        )


class LifecycleAuthorityTests(TestCase):
    def test_target_827_validation_loss_admission_authenticates_adoption_source(self) -> None:
        head = "7fd0467c321f1c2b9a06494f4a0c46531c9cc006"
        tree = "ab8da939ca30a3b906f22c471031083f7132ff94"
        parent = "f6982d0808cace5a142445b52454dc83515fa297"
        historical = "d0905955b07c580930ddf05595372c5c13c74387a074907ede4a33ddf1eafb38"
        fresh = "e210f448c7ed9c123ef2e991684f3706a0ca30b096005fce37a2103a9bdcfa15"
        migration = "lifecycle-legacy-adoption@secpal.app"
        timestamp = "2026-09-06T12:00:00Z"
        state = authority.initial_state()
        state.update(unrestricted_review_count=1, remediation_cycle_count=2)
        observations = [
            {
                "sequence": sequence, "kind": kind,
                "observed_at": observed_at, "head_sha": observed_head,
                "reviewed_head_sha": None,
            }
            for sequence, (kind, observed_at, observed_head) in enumerate([
                ("PR_CREATED_DRAFT", "2026-09-05T14:26:48Z", "4b5dc277bfbee865de5fe5c6bf8874467930475b"),
                ("HEAD_ADVANCED_OBSERVED", "2026-09-05T14:30:14Z", "b3f45ab2c2351e18587ff92c9b143c0fb7c3ef75"),
                ("REMEDIATION_HEAD_OBSERVED", "2026-09-05T16:21:55Z", parent),
                ("REMEDIATION_HEAD_OBSERVED", "2026-09-05T22:14:03Z", head),
            ], 1)
        ]
        self.assertEqual(
            authority._normalize_observed_pre_enrollment_history(
                observations, expected_head=head, intended_state=state,
                review_budget_consumption_admitted=True,
            ),
            observations,
        )
        signature_policy = {
            "accepted_formats": ["ssh"], "require_github_verified": True,
        }
        commit = {
            "oid": head, "source": "USER", "signer_identity": SIGNER,
            "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
            "github_verification": {"verified": True, "reason": "valid"},
        }
        signature_digest = authority.digest_json(
            fast_path.verify_commit_signatures([commit], signature_policy)[0]
        )
        safety = {
            "receipt_digest": fresh,
            "validated_tree_sha": tree,
            "validation_policy_digest": "4" * 64,
            "command_set_digest": "5" * 64,
            "feedback_digest": "6" * 64,
            "technical_decisions": [
                {
                    "source_id": f"SEC827-REVIEW-{number:03}",
                    "source_digest": authority.digest_json({"finding": number}),
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "evidence_digest": authority.digest_json({"proof": number, "tree": tree}),
                }
                for number in (1, 2, 3)
            ],
            "successful_result": True,
        }
        fields = {
            "schema_version": "1.0",
            "kind": "SECPAL_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_ADMISSION",
            "domain": "secpal.pre-enrollment-validation-evidence-loss-admission/v1",
            "repository": REPOSITORY, "delivery_issue": 827, "pull_request": 830,
            "head_sha": head, "tree_sha": tree, "parent_sha": parent,
            "pull_request_state": "OPEN", "draft": True,
            "source_signer_identity": SIGNER,
            "commit_signature_evidence_digest": signature_digest,
            "historical_validation_receipt_digest": historical,
            "historical_package_status": "UNAVAILABLE",
            "historical_final_attestation_digest": None,
            "historical_bytes_reconstructed": False,
            "loss_proof_policy_digest": "7" * 64,
            "accepted_main_sha": "c7f9ea7efe2c1523a99e58bf9694f380a21acfeb",
            "current_safety": safety,
            "observed_pre_enrollment_history": observations,
            "intended_state": state,
            "adoption_timestamp": timestamp,
            "admission_id": "pre-enrollment-validation-loss:827:830",
            "bounded_uses": 1, "signer_identity": migration,
        }
        fields["signature"] = signer_for(migration)(
            authority.canonical_json_bytes(fields), fields["domain"]
        )
        admission = {**fields, "admission_digest": authority.digest_json(fields)}
        trust = authority.LifecycleTrustPolicy(
            repository=REPOSITORY, accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
            legacy_adoption_signer_identities=frozenset({migration}),
            signers={
                SIGNER: authority.TrustedSigner(SIGNER, ("source-key",), ()),
                migration: authority.TrustedSigner(migration, ("migration-key",), ()),
            },
            initialization_anchors=(),
        )
        with patch.object(authority, "_load_lifecycle_trust_policy", return_value=trust), patch.object(
            authority, "_policy_signature_verifier", return_value=verify_signature
        ), patch.object(authority, "_load_delivery_signature_policy", return_value=signature_policy):
            authority._verify_signature(
                authority.canonical_json_bytes({key: value for key, value in fields.items() if key != "signature"}),
                fields["signature"], migration, fields["domain"],
                trust.legacy_adoption_signer_identities, verify_signature,
            )
            context = {
                "repository": REPOSITORY, "delivery_issue": 827, "pull_request": 830,
                "head_sha": head, "tree_sha": tree, "pull_request_state": "OPEN",
                "commit_signature_evidence_digest": signature_digest,
                "validation_receipt_digest": historical,
                "source_validation_evidence_digest": authority.digest_json(safety),
                "adoption_source_evidence_digest": admission["admission_digest"],
                "adoption_timestamp": timestamp,
            }
            budget = authority.create_pre_enrollment_review_budget_consumption_admission(
                **context, admission_id="review-budget:827:830",
                observed_pre_enrollment_history=observations, intended_state=state,
                signer_identity=migration, signer=signer_for(migration),
            )
            authority.verify_pre_enrollment_review_budget_consumption_admission(
                budget, **context, observed_history_digest=authority.digest_json(observations),
                intended_state_digest=authority.digest_json(state),
            )
            verifier = getattr(authority, "verify_pre_enrollment_validation_evidence_loss_admission", None)
            self.assertTrue(
                callable(verifier),
                "exact-state adoption has no verified pre-enrollment validation-evidence-loss source mode",
            )
            from scripts.secpal_pr_review import validation_evidence_loss as loss

            with patch.object(loss, "_reauthenticate", return_value=None):
                verified_source = verifier(authority.canonical_json_bytes(admission))
            arguments = {
                "repository": REPOSITORY, "delivery_issue": 827, "pull_request": 830,
                "head_sha": head, "tree_sha": tree, "pull_request_state": "OPEN",
                "commit_signature_evidence": commit, "validation_evidence": None,
                "validation_evidence_loss_admission": verified_source,
                "observed_pre_enrollment_history": observations, "intended_state": state,
            }
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.authenticate_exact_state_adoption_external_evidence(**arguments)
            external = authority.authenticate_exact_state_adoption_external_evidence(
                **arguments, review_budget_consumption_admission=budget,
            )
            for supplied in ({}, {"receipt": "invalid"}, object()):
                with self.subTest(supplied_historical=type(supplied)):
                    with self.assertRaisesRegex(authority.LifecycleAuthorityError, "downgrade"):
                        authority.authenticate_exact_state_adoption_external_evidence(
                            **{**arguments, "validation_evidence": supplied},
                            review_budget_consumption_admission=budget,
                        )
            wrong_budget = copy.deepcopy(budget)
            wrong_budget["pull_request"] = 831
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.authenticate_exact_state_adoption_external_evidence(
                    **arguments, review_budget_consumption_admission=wrong_budget,
                )
            evidence = authority.create_exact_state_adoption_evidence(
                verified_external_evidence=external, adoption_timestamp=timestamp,
            )
            self.assertEqual(evidence["proof_version"], "3.0")
            authorization = authority.create_exact_state_adoption_authorization(
                adoption_evidence=evidence, authorization_id="adopt:827:830",
                bounded_uses=1, signer_identity=migration, signer=signer_for(migration),
            )
            proof = authority.create_exact_state_adoption_proof(
                adoption_evidence=evidence, authorization=authorization,
                signer_identity=migration, signer=signer_for(migration),
            )
            verified = authority.verify_exact_state_adoption_proof(proof)
            for version, domain in (("1.0", authority.EXACT_ADOPTION_PROOF_DOMAIN),
                                    ("2.0", authority.EXACT_ADOPTION_CONSUMPTION_PROOF_DOMAIN)):
                with self.subTest(old_wrapper=version):
                    changed = {**proof, "schema_version": version, "proof_version": version, "domain": domain}
                    with self.assertRaises(authority.LifecycleAuthorityError):
                        authority.verify_exact_state_adoption_proof(changed)
            self.assertEqual(verified.state, state)
            self.assertEqual(verified.validation_receipt_digest, historical)
            self.assertEqual(verified.source_validation_evidence_digest, authority.digest_json(safety))
            self.assertFalse(admission["historical_bytes_reconstructed"])
            self.assertIsNone(admission["historical_final_attestation_digest"])
            self.assertNotEqual(historical, fresh)

    def test_target_827_fresh_evidence_cannot_replace_signed_receipt(self) -> None:
        head = "7fd0467c321f1c2b9a06494f4a0c46531c9cc006"
        tree = "ab8da939ca30a3b906f22c471031083f7132ff94"
        historical = "d0905955b07c580930ddf05595372c5c13c74387a074907ede4a33ddf1eafb38"
        observed_fresh = "e210f448c7ed9c123ef2e991684f3706a0ca30b096005fce37a2103a9bdcfa15"
        parent = "f6982d0808cace5a142445b52454dc83515fa297"
        state = authority.initial_state()
        state.update(unrestricted_review_count=1, remediation_cycle_count=2)
        observations = [
            {
                "sequence": sequence,
                "kind": kind,
                "observed_at": observed_at,
                "head_sha": observed_head,
                "reviewed_head_sha": None,
            }
            for sequence, (kind, observed_at, observed_head) in enumerate(
                [
                    ("PR_CREATED_DRAFT", "2026-09-05T14:26:48Z", "4b5dc277bfbee865de5fe5c6bf8874467930475b"),
                    ("HEAD_ADVANCED_OBSERVED", "2026-09-05T14:30:14Z", "b3f45ab2c2351e18587ff92c9b143c0fb7c3ef75"),
                    ("REMEDIATION_HEAD_OBSERVED", "2026-09-05T16:21:55Z", "f6982d0808cace5a142445b52454dc83515fa297"),
                    ("REMEDIATION_HEAD_OBSERVED", "2026-09-05T22:14:03Z", head),
                ],
                1,
            )
        ]
        normalized = authority._normalize_observed_pre_enrollment_history(
            observations,
            expected_head=head,
            intended_state=state,
            review_budget_consumption_admitted=True,
        )
        self.assertEqual(normalized, observations)
        self.assertEqual(
            sum(item["kind"] == "REMEDIATION_HEAD_OBSERVED" for item in normalized),
            2,
        )
        self.assertNotEqual(historical, observed_fresh)
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=830,
            head_sha=parent,
            base_ref="main",
            base_sha="41f08b6d0f5d47664193ca283bdd9b744c19aee0",
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [], "reviews": [],
                "conversation_comments": [], "threads": [],
            },
        )
        registry = {"manual_gates": []}
        fixture_receipt = fast_path.create_validation_receipt(
            repository=REPOSITORY,
            head_sha=parent,
            validated_tree_sha=tree,
            registry=registry,
            command_set=[],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
        )
        fixture_attestation = fast_path.create_validation_attestation(
            repository=REPOSITORY,
            head_sha=head,
            registry=registry,
            command_set=[],
            successful_result=True,
            reviewed_state=reviewed,
            validation_receipt=fixture_receipt,
        )
        arguments = {
            "repository": REPOSITORY,
            "head_sha": head,
            "registry": registry,
            "command_set": [],
            "reviewed_state": reviewed,
            "commit_parent_sha": parent,
            "commit_tree_sha": tree,
        }
        positive = fast_path.verify_validation_attestation(
            fixture_attestation,
            **arguments,
            commit_validation_receipt_digest=fixture_receipt["receipt_digest"],
        )
        self.assertTrue(fast_path.is_verified_validation_evidence(positive))
        self.assertNotIn(
            fixture_receipt["receipt_digest"], (historical, observed_fresh)
        )
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "receipt"):
            fast_path.verify_validation_attestation(
                fixture_attestation,
                **arguments,
                commit_validation_receipt_digest=historical,
            )

    def test_exact_adoption_conservatively_preserves_pre_enrollment_review_budget(
        self,
    ) -> None:
        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=1,
            draft=True,
            ready=False,
            ready_transition_count=0,
            cycle_3_absent=True,
        )
        observed = [
            {
                "sequence": 1,
                "kind": "PR_CREATED_DRAFT",
                "observed_at": "2026-08-01T00:00:00Z",
                "head_sha": HEADS[1],
                "reviewed_head_sha": None,
            },
            {
                "sequence": 2,
                "kind": "REMEDIATION_HEAD_OBSERVED",
                "observed_at": "2026-08-02T00:00:00Z",
                "head_sha": HEADS[2],
                "reviewed_head_sha": None,
            },
        ]

        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "observed pre-enrollment history does not authenticate intended state",
        ):
            authenticated_external_evidence(observed=observed, state=state)

        adoption_policy = authority.LifecycleTrustPolicy(
            repository="Example/governance",
            accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({OTHER_SIGNER}),
            authority_signer_identities=frozenset({OTHER_SIGNER}),
            signers={
                SIGNER: authority.TrustedSigner(SIGNER, ("unused",), ()),
                OTHER_SIGNER: authority.TrustedSigner(
                    OTHER_SIGNER, ("also-unused",), ()
                ),
            },
            initialization_anchors=(),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
        )
        with patch.object(
            authority,
            "_load_lifecycle_trust_policy",
            return_value=adoption_policy,
        ), patch.object(
            authority,
            "_policy_signature_verifier",
            return_value=verify_signature,
        ):
            external = authenticated_external_evidence(
                observed=observed,
                state=state,
                admit_review_budget=True,
            )
            evidence = authority.create_exact_state_adoption_evidence(
                verified_external_evidence=external,
                adoption_timestamp="2026-08-03T00:00:00Z",
            )
            authorization = authority.create_exact_state_adoption_authorization(
                adoption_evidence=evidence,
                authorization_id="exact-adoption:generic-41",
                bounded_uses=1,
                signer_identity=SIGNER,
                signer=signer_for(),
            )
            proof = authority.create_exact_state_adoption_proof(
                adoption_evidence=evidence,
                authorization=authorization,
                signer_identity=SIGNER,
                signer=signer_for(),
            )
            verified = authority.verify_exact_state_adoption_proof(proof)

        self.assertEqual(
            [
                item["kind"]
                for item in external.observed_pre_enrollment_history
            ],
            ["PR_CREATED_DRAFT", "REMEDIATION_HEAD_OBSERVED"],
        )
        self.assertEqual(external.intended_state["unrestricted_review_count"], 1)
        self.assertEqual(
            evidence["proof_version"],
            authority.EXACT_ADOPTION_CONSUMPTION_VERSION,
        )
        self.assertEqual(
            evidence["domain"],
            authority.EXACT_ADOPTION_CONSUMPTION_EVIDENCE_DOMAIN,
        )
        self.assertEqual(
            authorization["domain"],
            authority.EXACT_ADOPTION_CONSUMPTION_AUTHORIZATION_DOMAIN,
        )
        self.assertEqual(
            proof["domain"], authority.EXACT_ADOPTION_CONSUMPTION_PROOF_DOMAIN
        )
        self.assertEqual(verified.state, state)
        self.assertEqual(verified.historical_proof_mode, "exact_state_adoption")

    def test_review_budget_admission_is_closed_and_disjoint_from_provider_mode(
        self,
    ) -> None:
        state = authority.initial_state()
        state.update(unrestricted_review_count=1, remediation_cycle_count=1)
        observed = [
            {
                "sequence": 1,
                "kind": "PR_CREATED_DRAFT",
                "observed_at": "2026-08-01T00:00:00Z",
                "head_sha": HEADS[1],
                "reviewed_head_sha": None,
            },
            {
                "sequence": 2,
                "kind": "REVIEW_SUBMITTED",
                "observed_at": "2026-08-02T00:00:00Z",
                "head_sha": HEADS[1],
                "reviewed_head_sha": HEADS[1],
            },
            {
                "sequence": 3,
                "kind": "REMEDIATION_HEAD_OBSERVED",
                "observed_at": "2026-08-03T00:00:00Z",
                "head_sha": HEADS[2],
                "reviewed_head_sha": None,
            },
        ]
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "modes are ambiguous"
        ):
            authority.create_pre_enrollment_review_budget_consumption_admission(
                admission_id="ambiguous-provider-and-admission",
                repository="Example/governance",
                delivery_issue=41,
                pull_request=42,
                head_sha=HEADS[2],
                tree_sha=HEADS[3],
                pull_request_state="OPEN",
                commit_signature_evidence_digest="1" * 64,
                validation_receipt_digest="2" * 64,
                source_validation_evidence_digest="3" * 64,
                adoption_source_evidence_digest="4" * 64,
                observed_pre_enrollment_history=observed,
                intended_state=state,
                adoption_timestamp="2026-08-04T00:00:00Z",
                signer_identity=SIGNER,
                signer=signer_for(),
            )

        parameters = inspect.signature(
            authority.create_pre_enrollment_review_budget_consumption_admission
        ).parameters
        self.assertNotIn("review_count", parameters)
        self.assertNotIn("review_consumed", parameters)
        self.assertNotIn("verdict", parameters)
        self.assertNotIn("findings", parameters)
        self.assertFalse(
            any("UNRESTRICTED_REVIEW_RESULT" in value for value in vars(authority))
        )

    def test_review_budget_admission_rejects_substitution_replay_and_state_scope(
        self,
    ) -> None:
        state = authority.initial_state()
        state.update(unrestricted_review_count=1, remediation_cycle_count=1)
        observed = [
            {
                "sequence": 1,
                "kind": "PR_CREATED_DRAFT",
                "observed_at": "2026-08-01T00:00:00Z",
                "head_sha": HEADS[1],
                "reviewed_head_sha": None,
            },
            {
                "sequence": 2,
                "kind": "REMEDIATION_HEAD_OBSERVED",
                "observed_at": "2026-08-02T00:00:00Z",
                "head_sha": HEADS[2],
                "reviewed_head_sha": None,
            },
        ]
        policy = authority.LifecycleTrustPolicy(
            repository="Example/governance",
            accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({OTHER_SIGNER}),
            authority_signer_identities=frozenset({OTHER_SIGNER}),
            signers={
                SIGNER: authority.TrustedSigner(SIGNER, ("unused",), ()),
                OTHER_SIGNER: authority.TrustedSigner(
                    OTHER_SIGNER, ("also-unused",), ()
                ),
            },
            initialization_anchors=(),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
        )
        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=policy
        ), patch.object(
            authority, "_policy_signature_verifier", return_value=verify_signature
        ):
            external = authenticated_external_evidence(
                observed=observed,
                state=state,
                admit_review_budget=True,
            )
            admission = copy.deepcopy(
                external.review_budget_consumption_admission
            )
            expected = {
                "repository": external.repository,
                "delivery_issue": external.delivery_issue,
                "pull_request": external.pull_request,
                "head_sha": external.head_sha,
                "tree_sha": external.tree_sha,
                "pull_request_state": external.pull_request_state,
                "commit_signature_evidence_digest": (
                    external.commit_signature_evidence_digest
                ),
                "validation_receipt_digest": external.validation_receipt_digest,
                "source_validation_evidence_digest": (
                    external.source_validation_evidence_digest
                ),
                "adoption_source_evidence_digest": (
                    external.adoption_source_evidence_digest
                ),
                "observed_history_digest": authority.digest_json(
                    list(external.observed_pre_enrollment_history)
                ),
                "intended_state_digest": authority.digest_json(
                    external.intended_state
                ),
                "adoption_timestamp": "2026-08-03T00:00:00Z",
            }
            verified = (
                authority.verify_pre_enrollment_review_budget_consumption_admission(
                    admission, **expected
                )
            )
            self.assertEqual(verified.admission_digest, admission["admission_digest"])

            mutations = (
                lambda value: value.update(schema_version="9.9"),
                lambda value: value.update(kind="UNRESTRICTED_REVIEW_RESULT"),
                lambda value: value.update(domain="wrong-domain"),
                lambda value: value.update(repository="Other/repository"),
                lambda value: value.update(delivery_issue=99),
                lambda value: value.update(pull_request=99),
                lambda value: value.update(head_sha=HEADS[4]),
                lambda value: value.update(tree_sha=HEADS[4]),
                lambda value: value.update(pull_request_state="CLOSED"),
                lambda value: value.update(
                    adoption_timestamp="2026-08-04T00:00:00Z"
                ),
                lambda value: value.update(
                    commit_signature_evidence_digest="0" * 64
                ),
                lambda value: value.update(validation_receipt_digest="0" * 64),
                lambda value: value.update(
                    source_validation_evidence_digest="0" * 64
                ),
                lambda value: value.update(
                    adoption_source_evidence_digest="0" * 64
                ),
                lambda value: value.update(observed_history_digest="0" * 64),
                lambda value: value.update(intended_state_digest="0" * 64),
                lambda value: value.update(provider_review_submission_count=1),
                lambda value: value.update(admitted_unrestricted_review_count=0),
                lambda value: value.update(historical_provenance_status="PRESENT"),
                lambda value: value.update(assertion="REVIEW_RECONSTRUCTED"),
                lambda value: value.update(bounded_uses=2),
                lambda value: value.update(adoption_context_digest="0" * 64),
                lambda value: value.update(signer_identity=OTHER_SIGNER),
                lambda value: value.update(admission_digest="0" * 64),
                lambda value: value.update(unknown_field=True),
                lambda value: value.pop("admission_id"),
            )
            for mutation in mutations:
                with self.subTest(mutation=mutation), self.assertRaises(
                    authority.LifecycleAuthorityError
                ):
                    changed = copy.deepcopy(admission)
                    mutation(changed)
                    authority.verify_pre_enrollment_review_budget_consumption_admission(
                        changed, **expected
                    )

            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.verify_pre_enrollment_review_budget_consumption_admission(
                    [admission, admission], **expected
                )
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.verify_pre_enrollment_review_budget_consumption_admission(
                    admission, **{**expected, "delivery_issue": 99}
                )

            wrong_signer = {
                key: copy.deepcopy(value)
                for key, value in admission.items()
                if key not in {"signature", "admission_digest"}
            }
            wrong_signer["signer_identity"] = OTHER_SIGNER
            wrong_signer["signature"] = signer_for(OTHER_SIGNER)(
                authority.canonical_json_bytes(wrong_signer),
                authority.PRE_ENROLLMENT_REVIEW_BUDGET_ADMISSION_DOMAIN,
            )
            wrong_signer["admission_digest"] = authority.digest_json(
                wrong_signer
            )
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError, "independently accepted"
            ):
                authority.verify_pre_enrollment_review_budget_consumption_admission(
                    wrong_signer, **expected
                )

        reset_state = copy.deepcopy(state)
        reset_state["unrestricted_review_count"] = 0
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "does not authenticate intended state",
        ):
            authenticated_external_evidence(observed=observed, state=reset_state)

        over_count = copy.deepcopy(state)
        over_count["unrestricted_review_count"] = 2
        with self.assertRaises(authority.LifecycleAuthorityError):
            authenticated_external_evidence(observed=observed, state=over_count)

        no_remediation_observation = observed[:1]
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "does not authenticate intended state",
        ):
            authority.create_pre_enrollment_review_budget_consumption_admission(
                admission_id="cannot-create-remediation",
                repository="Example/governance",
                delivery_issue=41,
                pull_request=42,
                head_sha=HEADS[1],
                tree_sha=HEADS[3],
                pull_request_state="OPEN",
                commit_signature_evidence_digest="1" * 64,
                validation_receipt_digest="2" * 64,
                source_validation_evidence_digest="3" * 64,
                adoption_source_evidence_digest="4" * 64,
                observed_pre_enrollment_history=no_remediation_observation,
                intended_state=state,
                adoption_timestamp="2026-08-04T00:00:00Z",
                signer_identity=SIGNER,
                signer=signer_for(),
            )

    def test_exact_adoption_constructor_requires_verified_external_evidence(self) -> None:
        parameters = inspect.signature(
            authority.create_exact_state_adoption_evidence
        ).parameters
        self.assertIn("verified_external_evidence", parameters)
        for caller_selected in (
            "commit_signature_status",
            "validation_receipt_digest",
            "source_validation_evidence_digest",
            "adoption_source_evidence_digest",
            "supporting_evidence",
            "supporting_evidence_digests",
        ):
            self.assertNotIn(caller_selected, parameters)

        forged = fast_path.VerifiedValidationEvidence(
            repository="Example/governance", pull_request_number=42,
            head_sha=HEADS[2],
            tree_sha=HEADS[3], validation_receipt_digest="2" * 64,
            final_attestation_digest="4" * 64,
            source_validation_evidence_digest="3" * 64,
            _verification_seal=object(),
        )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "validation evidence"
        ):
            authority.authenticate_exact_state_adoption_external_evidence(
                repository="Example/governance", delivery_issue=41,
                pull_request=42, head_sha=HEADS[2], tree_sha=HEADS[3],
                pull_request_state="OPEN", commit_signature_evidence={},
                validation_evidence=forged,
                observed_pre_enrollment_history=[], intended_state={},
            )

    def test_exact_adoption_rejects_fabricated_ordinary_ready_provenance(self) -> None:
        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
            ready_history=[
                {
                    "sequence": 1,
                    "transition_kind": "DRAFT_TO_READY",
                    "event_authorization_digest": "1" * 64,
                }
            ],
        )
        observed = [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT", "observed_at": "2026-08-01T00:00:00Z", "head_sha": HEADS[0], "reviewed_head_sha": None},
            {"sequence": 2, "kind": "DRAFT_TO_READY_OBSERVED", "observed_at": "2026-08-02T00:00:00Z", "head_sha": HEADS[0], "reviewed_head_sha": None},
            {"sequence": 3, "kind": "REVIEW_SUBMITTED", "observed_at": "2026-08-03T00:00:00Z", "head_sha": HEADS[0], "reviewed_head_sha": HEADS[0]},
            {"sequence": 4, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-08-04T00:00:00Z", "head_sha": HEADS[1], "reviewed_head_sha": None},
            {"sequence": 5, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-08-05T00:00:00Z", "head_sha": HEADS[2], "reviewed_head_sha": None},
        ]
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "ordinary authorization provenance",
        ):
            authenticated_external_evidence(observed=observed, state=state)

    def test_exact_adoption_rejects_duplicate_remediation_heads(self) -> None:
        observed = [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT", "observed_at": "2026-08-01T00:00:00Z", "head_sha": HEADS[0], "reviewed_head_sha": None},
            {"sequence": 2, "kind": "DRAFT_TO_READY_OBSERVED", "observed_at": "2026-08-02T00:00:00Z", "head_sha": HEADS[0], "reviewed_head_sha": None},
            {"sequence": 3, "kind": "REVIEW_SUBMITTED", "observed_at": "2026-08-03T00:00:00Z", "head_sha": HEADS[0], "reviewed_head_sha": HEADS[0]},
            {"sequence": 4, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-08-04T00:00:00Z", "head_sha": HEADS[2], "reviewed_head_sha": None},
            {"sequence": 5, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-08-05T00:00:00Z", "head_sha": HEADS[2], "reviewed_head_sha": None},
        ]
        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
            ready_history=[
                {
                    "sequence": 1,
                    "transition_kind": "DRAFT_TO_READY",
                    "observation_digest": authority.digest_json(observed[1]),
                }
            ],
        )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "remediation observation must advance the delivery head",
        ):
            authenticated_external_evidence(observed=observed, state=state)

    def test_adoption_timestamp_requires_a_real_canonical_utc_instant(self) -> None:
        for invalid in (
            "2026-99-99T99:99:99Z",
            "2026-02-30T12:00:00Z",
            "2026-08-01T24:00:00Z",
            "2026-08-01T12:60:00Z",
            "2026-08-01T12:00:60Z",
            "2026-08-01T12:00:00+00:00",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                authority.LifecycleAuthorityError
            ):
                authority._require_adoption_timestamp(invalid, "adoption timestamp")
        self.assertEqual(
            authority._require_adoption_timestamp(
                "2026-08-01T12:00:00Z", "adoption timestamp"
            ),
            "2026-08-01T12:00:00Z",
        )

    def test_exact_state_adoption_preserves_ready_before_review_observation(self) -> None:
        observed = [
            {
                "sequence": 1,
                "kind": "PR_CREATED_DRAFT",
                "observed_at": "2026-08-01T00:00:00Z",
                "head_sha": HEADS[0],
                "reviewed_head_sha": None,
            },
            {
                "sequence": 2,
                "kind": "DRAFT_TO_READY_OBSERVED",
                "observed_at": "2026-08-02T00:00:00Z",
                "head_sha": HEADS[0],
                "reviewed_head_sha": None,
            },
            {
                "sequence": 3,
                "kind": "REVIEW_SUBMITTED",
                "observed_at": "2026-08-03T00:00:00Z",
                "head_sha": HEADS[0],
                "reviewed_head_sha": HEADS[0],
            },
            {
                "sequence": 4,
                "kind": "REMEDIATION_HEAD_OBSERVED",
                "observed_at": "2026-08-04T00:00:00Z",
                "head_sha": HEADS[1],
                "reviewed_head_sha": None,
            },
            {
                "sequence": 5,
                "kind": "REMEDIATION_HEAD_OBSERVED",
                "observed_at": "2026-08-05T00:00:00Z",
                "head_sha": HEADS[2],
                "reviewed_head_sha": None,
            },
        ]
        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
            ready_history=[
                {
                    "sequence": 1,
                    "transition_kind": "DRAFT_TO_READY",
                    "observation_digest": authority.digest_json(observed[1]),
                }
            ],
        )

        # The ordinary engine truthfully rejects this chronology: Ready cannot
        # be derived before review.  Adoption must not "correct" that history.
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "Draft-to-Ready transition"
        ):
            authority.derive_state(
                authority.initial_state(), "DRAFT_TO_READY", "1" * 64
            )

        evidence = authority.create_exact_state_adoption_evidence(
            verified_external_evidence=authenticated_external_evidence(
                observed=observed, state=state
            ),
            adoption_timestamp="2026-08-06T00:00:00Z",
        )
        authorization = authority.create_exact_state_adoption_authorization(
            adoption_evidence=evidence,
            authorization_id="exact-adoption-authorization-1",
            bounded_uses=1,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        proof = authority.create_exact_state_adoption_proof(
            adoption_evidence=evidence,
            authorization=authorization,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        with patch.object(
            authority,
            "_load_lifecycle_trust_policy",
            return_value=authority.LifecycleTrustPolicy(
                repository="Example/governance",
                accepted_formats=frozenset({"ssh"}),
                transition_signer_identities=frozenset({SIGNER}),
                authority_signer_identities=frozenset({SIGNER}),
                signers={
                    SIGNER: authority.TrustedSigner(
                        SIGNER, ("ssh-ed25519 AAAA",), ()
                    )
                },
                initialization_anchors=(),
                legacy_adoption_signer_identities=frozenset({SIGNER}),
            ),
        ), patch.object(
            authority, "_policy_signature_verifier", return_value=verify_signature
        ):
            verified = authority.verify_exact_state_adoption_proof(proof)

        self.assertEqual(verified.state, state)
        self.assertEqual(
            [item["kind"] for item in proof["observed_pre_enrollment_history"]],
            [
                "PR_CREATED_DRAFT",
                "DRAFT_TO_READY_OBSERVED",
                "REVIEW_SUBMITTED",
                "REMEDIATION_HEAD_OBSERVED",
                "REMEDIATION_HEAD_OBSERVED",
            ],
        )
        self.assertEqual(proof["ordinary_lifecycle_events"], [])

        for field, replacement in (
            ("repository", "Other/governance"),
            ("delivery_issue", 99),
            ("pull_request", 100),
            ("head_sha", HEADS[4]),
            ("tree_sha", HEADS[5]),
            ("validation_receipt_digest", "7" * 64),
            ("source_validation_evidence_digest", "8" * 64),
            ("adoption_source_evidence_digest", "9" * 64),
            ("proof_version", "2.0"),
        ):
            changed = copy.deepcopy(evidence)
            changed[field] = replacement
            with self.subTest(evidence_field=field), self.assertRaises(
                authority.LifecycleAuthorityError
            ):
                authority._verify_exact_state_adoption_evidence(changed)

        missing_ready = copy.deepcopy(evidence)
        missing_ready["observed_pre_enrollment_history"].pop(1)
        for sequence, item in enumerate(
            missing_ready["observed_pre_enrollment_history"], 1
        ):
            item["sequence"] = sequence
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "intended state"
        ):
            authority._verify_exact_state_adoption_evidence(missing_ready)

        invented_review = copy.deepcopy(evidence)
        invented_review["observed_pre_enrollment_history"].insert(
            3,
            {
                "sequence": 4,
                "kind": "REVIEW_SUBMITTED",
                "observed_at": "2026-08-03T00:00:01Z",
                "head_sha": HEADS[0],
                "reviewed_head_sha": HEADS[0],
            },
        )
        for sequence, item in enumerate(
            invented_review["observed_pre_enrollment_history"], 1
        ):
            item["sequence"] = sequence
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "intended state"
        ):
            authority._verify_exact_state_adoption_evidence(invented_review)

        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "must have one use"
        ):
            authority.create_exact_state_adoption_authorization(
                adoption_evidence=evidence,
                authorization_id="exact-adoption-authorization-2",
                bounded_uses=2,
                signer_identity=SIGNER,
                signer=signer_for(),
            )

    def test_public_verifier_does_not_accept_consumer_trust_inputs(self) -> None:
        parameters = inspect.signature(authority.verify_lifecycle_authority).parameters
        self.assertEqual(list(parameters), ["serialized_evidence", "expected"])
        self.assertNotIn(
            "authority_digest", authority.ExpectedLifecycle.__dataclass_fields__
        )

    def test_lifecycle_identity_is_derived_from_initialization_anchor(self) -> None:
        digest = "1" * 64
        self.assertEqual(
            authority.delivery_initialization_lifecycle_id(digest),
            f"lifecycle:{digest}",
        )

    def test_noncanonical_git_oid_lengths_are_rejected(self) -> None:
        for length in (39, 41, 42, 63, 65):
            with self.subTest(length=length):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    authority._require_oid("a" * length, "test head")
        for length in (40, 64):
            self.assertEqual(
                authority._require_oid("a" * length, "test head"), "a" * length
            )

    def test_registry_rejects_second_initialization_for_same_issue(self) -> None:
        registry = json.loads(
            (REPO_ROOT / ".agents/skills/secpal-pr-review/references/repositories.json")
            .read_text(encoding="utf-8")
        )
        entry = next(
            item for item in registry["repositories"]
            if item["repository"] == REPOSITORY
        )
        anchors = authority._load_lifecycle_trust_policy(
            REPOSITORY
        ).initialization_anchors
        self.assertEqual(len(anchors), 3)
        delivered = {anchor.delivery_issue: anchor for anchor in anchors}
        self.assertEqual(set(delivered), {674, 692, 735})
        self.assertEqual(delivered[692].pull_request, 757)
        self.assertEqual(
            delivered[692].initialization_digest,
            "4e071bcbfc17a20cc54b3f608f10418b3cc376eddce0dfba6ddbe54e2e53108f",
        )
        self.assertEqual(delivered[674].pull_request, 758)
        self.assertEqual(
            delivered[674].initialization_digest,
            "2756e83b52c8af10c30926cb1d62d5501819a790158f560cf0f608587df321e9",
        )
        self.assertEqual(delivered[735].pull_request, 759)
        self.assertEqual(
            delivered[735].initialization_digest,
            "6b630e40702ae69145226f8b40c8e6540914cd6e12815720551330faa2ca9d3d",
        )
        entry["lifecycle_authority_policy"][
            "historical_compatibility_publications"
        ] = []
        entry["lifecycle_authority_policy"]["delivery_initializations"] = [
            {
                "delivery_issue": ISSUE,
                "pull_request": PR,
                "initial_head_sha": HEADS[0],
                "initialization_digest": "1" * 64,
                "current_pull_request": PR,
                "current_head_sha": HEADS[0],
                "current_authority_digest": "3" * 64,
            },
            {
                "delivery_issue": ISSUE,
                "pull_request": PR + 1,
                "initial_head_sha": HEADS[1],
                "initialization_digest": "2" * 64,
                "current_pull_request": PR + 1,
                "current_head_sha": HEADS[1],
                "current_authority_digest": "4" * 64,
            },
        ]
        with tempfile.TemporaryDirectory(prefix="lifecycle-policy-test-") as directory:
            policy_path = Path(directory) / "repositories.json"
            policy_path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.object(authority, "_TRUST_REGISTRY", policy_path):
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError, "ambiguous"
                ):
                    authority._load_lifecycle_trust_policy(REPOSITORY)
                entry["lifecycle_authority_policy"]["delivery_initializations"][1][
                    "delivery_issue"
                ] = ISSUE + 1
                policy_path.write_text(json.dumps(registry), encoding="utf-8")
                self.assertEqual(
                    len(authority._load_lifecycle_trust_policy(REPOSITORY).initialization_anchors),
                    2,
                )
                entry["lifecycle_authority_policy"]["delivery_initializations"][1][
                    "initialization_digest"
                ] = "1" * 64
                policy_path.write_text(json.dumps(registry), encoding="utf-8")
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError, "ambiguous"
                ):
                    authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_registry_closes_the_single_issue_736_bootstrap_repair(self) -> None:
        registry_path = (
            REPO_ROOT
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        policy = authority._load_lifecycle_trust_policy(REPOSITORY)
        self.assertEqual(len(policy.bootstrap_genesis_repairs), 1)
        repair = policy.bootstrap_genesis_repairs[0]
        self.assertEqual(repair.repair_issue, 774)
        self.assertEqual(repair.delivery_issue, 736)
        self.assertEqual(repair.pull_request, 760)
        self.assertEqual(
            repair.initial_head_sha,
            "9cce12e839e5f998137cc58fea90d0a5a0a45f63",
        )
        self.assertEqual(
            repair.initialization_digest,
            "6477407a86182f6bc9964089382f288e13dbb2e0b096edb2bf4e1c228452e628",
        )
        entry = next(
            item
            for item in registry["repositories"]
            if item["repository"] == REPOSITORY
        )
        repairs = entry["lifecycle_authority_policy"]["bootstrap_genesis_repairs"]
        repairs.append(copy.deepcopy(repairs[0]))
        with tempfile.TemporaryDirectory(prefix="bootstrap-repair-policy-") as directory:
            policy_path = Path(directory) / "repositories.json"
            policy_path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.object(authority, "_TRUST_REGISTRY", policy_path):
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError, "ambiguous"
                ):
                    authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_registry_closes_exact_historical_compatibility_publications(
        self,
    ) -> None:
        registry_path = (
            REPO_ROOT
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        policy = authority._load_lifecycle_trust_policy(REPOSITORY)
        historical = {
            item.delivery_issue: item
            for item in policy.historical_compatibility_publications
        }
        self.assertEqual(set(historical), {674, 692, 735})
        self.assertEqual(
            historical[692].enrollment_publication_oid,
            "52e76a4eef0fdbb297c16d4bcf64b813bef84062",
        )
        self.assertEqual(
            historical[674].enrollment_publication_oid,
            "80950f8908f29ead325eb99caf1977e51fad37e1",
        )
        self.assertEqual(
            historical[735].enrollment_publication_oid,
            "2a5c2d9554ca7b70fd4f2e486da18ae9697af912",
        )
        self.assertTrue(
            all(
                item.historical_proof_mode == authority.NATIVE_PROOF_MODE
                for item in historical.values()
            )
        )

        mutations = (
            lambda values: values.append(copy.deepcopy(values[0])),
            lambda values: values[1].update(
                enrollment_publication_oid=values[0][
                    "enrollment_publication_oid"
                ]
            ),
            lambda values: values[1].update(
                enrollment_publication_digest=values[0][
                    "enrollment_publication_digest"
                ]
            ),
            lambda values: values[0].update(repository="Other/repo"),
            lambda values: values[0].update(delivery_issue=999),
            lambda values: values[0].update(pull_request=999),
            lambda values: values[0].update(initial_head_sha=HEADS[9]),
            lambda values: values[0].update(initialization_digest="9" * 64),
            lambda values: values[0].update(
                historical_proof_mode="legacy_migration_checkpoint"
            ),
            lambda values: values[0].pop("enrollment_publication_digest"),
            lambda values: values[0].update(unknown_authority="forbidden"),
            lambda values: values[0].update(
                enrollment_publication_oid="not-an-oid"
            ),
            lambda values: values[0].update(
                enrollment_publication_digest="not-a-digest"
            ),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(registry)
                changed_entry = next(
                    item
                    for item in changed["repositories"]
                    if item["repository"] == REPOSITORY
                )
                values = changed_entry["lifecycle_authority_policy"][
                    "historical_compatibility_publications"
                ]
                mutation(values)
                with tempfile.TemporaryDirectory(
                    prefix="historical-compatibility-policy-"
                ) as directory:
                    policy_path = Path(directory) / "repositories.json"
                    policy_path.write_text(json.dumps(changed), encoding="utf-8")
                    with patch.object(authority, "_TRUST_REGISTRY", policy_path):
                        with self.assertRaises(
                            authority.LifecycleAuthorityError
                        ):
                            authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_registry_requires_cryptographically_distinct_legacy_adoption_credential(
        self,
    ) -> None:
        registry = json.loads(
            (REPO_ROOT / ".agents/skills/secpal-pr-review/references/repositories.json")
            .read_text(encoding="utf-8")
        )
        entry = next(
            item for item in registry["repositories"]
            if item["repository"] == REPOSITORY
        )
        policy = entry["lifecycle_authority_policy"]
        ordinary = next(
            signer for signer in policy["signers"]
            if signer["identity"] == SIGNER
        )
        legacy = next(
            signer for signer in policy["signers"]
            if signer["identity"] == "lifecycle-legacy-adoption@secpal.app"
        )
        self.assertTrue(
            set(ordinary["ssh_public_keys"]).isdisjoint(legacy["ssh_public_keys"])
        )
        legacy["ssh_public_keys"] = copy.deepcopy(ordinary["ssh_public_keys"])
        with tempfile.TemporaryDirectory(prefix="lifecycle-overlap-policy-") as directory:
            policy_path = Path(directory) / "repositories.json"
            policy_path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.object(authority, "_TRUST_REGISTRY", policy_path):
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError,
                    "cryptographically distinct credential",
                ):
                    authority._load_lifecycle_trust_policy(REPOSITORY)

    def test_legacy_adoption_domain_accepts_only_its_distinct_private_key(self) -> None:
        legacy_identity = "lifecycle-legacy-adoption@secpal.app"
        with tempfile.TemporaryDirectory(prefix="legacy-adoption-keys-") as directory:
            root = Path(directory)
            routine_key = root / "routine"
            legacy_key = root / "legacy"
            for key in (routine_key, legacy_key):
                subprocess.run(
                    ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                    check=True,
                )

            def public_key(key: Path) -> str:
                parts = key.with_suffix(".pub").read_text(encoding="utf-8").split()
                return f"{parts[0]} {parts[1]}"

            policy = authority.LifecycleTrustPolicy(
                repository=REPOSITORY,
                accepted_formats=frozenset({"ssh"}),
                transition_signer_identities=frozenset({SIGNER}),
                authority_signer_identities=frozenset({SIGNER}),
                signers={
                    SIGNER: authority.TrustedSigner(SIGNER, (public_key(routine_key),), ()),
                    legacy_identity: authority.TrustedSigner(
                        legacy_identity, (public_key(legacy_key),), ()
                    ),
                },
                initialization_anchors=(),
                publication_signer_identities=frozenset({SIGNER}),
                legacy_adoption_signer_identities=frozenset({legacy_identity}),
            )
            payload = b"explicit legacy migration checkpoint"

            def signature(key: Path, domain: str) -> dict[str, str]:
                result = subprocess.run(
                    ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", domain],
                    input=payload,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                return {
                    "format": "ssh",
                    "signer_identity": legacy_identity,
                    "value": result.stdout.decode("utf-8"),
                }

            verifier = authority._policy_signature_verifier(policy)
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority._verify_signature(
                    payload,
                    signature(routine_key, authority.LEGACY_ADOPTION_DOMAIN),
                    legacy_identity,
                    authority.LEGACY_ADOPTION_DOMAIN,
                    policy.legacy_adoption_signer_identities,
                    verifier,
                )
            authority._verify_signature(
                payload,
                signature(legacy_key, authority.LEGACY_ADOPTION_DOMAIN),
                legacy_identity,
                authority.LEGACY_ADOPTION_DOMAIN,
                policy.legacy_adoption_signer_identities,
                verifier,
            )
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority._verify_signature(
                    payload,
                    signature(legacy_key, authority.EVENT_DOMAIN),
                    legacy_identity,
                    authority.LEGACY_ADOPTION_DOMAIN,
                    policy.legacy_adoption_signer_identities,
                    verifier,
                )

    def test_public_serialized_boundary_and_anchored_real_ssh_chain(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lifecycle-ssh-test-") as directory:
            key = Path(directory) / "key"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                check=True,
            )
            public_key = key.with_suffix(".pub").read_text(encoding="utf-8").split()
            trusted = authority.TrustedSigner(
                SIGNER,
                (f"{public_key[0]} {public_key[1]}",),
                (),
            )

            def real_signer(payload: bytes, domain: str) -> dict[str, str]:
                result = subprocess.run(
                    ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", domain],
                    input=payload,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                return {
                    "format": "ssh",
                    "signer_identity": SIGNER,
                    "value": result.stdout.decode(),
                }

            initialization = authority.create_delivery_initialization(
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                initial_head_sha=HEADS[0],
                validation_receipt_digest="1" * 64,
                final_attestation_digest="2" * 64,
                signer_identity=SIGNER,
                signer=real_signer,
            )
            digest = initialization["initialization_digest"]
            lifecycle = authority.delivery_initialization_lifecycle_id(digest)
            policy = authority.LifecycleTrustPolicy(
                REPOSITORY,
                frozenset({"ssh"}),
                frozenset({SIGNER}),
                frozenset({SIGNER}),
                {SIGNER: trusted},
                (
                    authority.InitializationAnchor(
                        ISSUE,
                        PR,
                        HEADS[0],
                        digest,
                        PR,
                        HEADS[0],
                        "0" * 64,
                    ),
                ),
            )
            event = authority.create_transition_authorization(
                event_id=f"genesis:{digest}",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=lifecycle,
                pull_request=PR,
                predecessor_authority_digest=None,
                predecessor_head_sha=None,
                resulting_head_sha=HEADS[0],
                transition_kind="INITIALIZED_DRAFT",
                replacement_pull_request=None,
                initialization_evidence_digest=digest,
                signer_identity=SIGNER,
                signer=real_signer,
            )
            verifier = authority._policy_signature_verifier(policy)
            snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=[],
                transition_authorizations=[],
                authorization=event,
                signer_identity=SIGNER,
                authority_signer=real_signer,
                accepted_event_signers=policy.transition_signer_identities,
                accepted_authority_signers=policy.authority_signer_identities,
                signature_verifier=verifier,
            )
            review_event = authority.create_transition_authorization(
                event_id="same-head-review",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=lifecycle,
                pull_request=PR,
                predecessor_authority_digest=snapshot["authority_digest"],
                predecessor_head_sha=HEADS[0],
                resulting_head_sha=HEADS[0],
                transition_kind="UNRESTRICTED_REVIEW_CONSUMED",
                replacement_pull_request=None,
                initialization_evidence_digest=digest,
                signer_identity=SIGNER,
                signer=real_signer,
            )
            review_snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=[snapshot],
                transition_authorizations=[event],
                authorization=review_event,
                signer_identity=SIGNER,
                authority_signer=real_signer,
                accepted_event_signers=policy.transition_signer_identities,
                accepted_authority_signers=policy.authority_signer_identities,
                signature_verifier=verifier,
            )
            ready_event = authority.create_transition_authorization(
                event_id="same-head-ready",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=lifecycle,
                pull_request=PR,
                predecessor_authority_digest=review_snapshot["authority_digest"],
                predecessor_head_sha=HEADS[0],
                resulting_head_sha=HEADS[0],
                transition_kind="DRAFT_TO_READY",
                replacement_pull_request=None,
                initialization_evidence_digest=digest,
                signer_identity=SIGNER,
                signer=real_signer,
            )
            ready_snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=[snapshot, review_snapshot],
                transition_authorizations=[event, review_event],
                authorization=ready_event,
                signer_identity=SIGNER,
                authority_signer=real_signer,
                accepted_event_signers=policy.transition_signer_identities,
                accepted_authority_signers=policy.authority_signer_identities,
                signature_verifier=verifier,
            )
            rebound_event = authority.create_transition_authorization(
                event_id="same-head-rebound",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=lifecycle,
                pull_request=PR,
                predecessor_authority_digest=ready_snapshot["authority_digest"],
                predecessor_head_sha=HEADS[0],
                resulting_head_sha=HEADS[0],
                transition_kind="PR_REBOUND",
                replacement_pull_request=PR + 1,
                initialization_evidence_digest=digest,
                signer_identity=SIGNER,
                signer=real_signer,
            )
            rebound_snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=[snapshot, review_snapshot, ready_snapshot],
                transition_authorizations=[event, review_event, ready_event],
                authorization=rebound_event,
                signer_identity=SIGNER,
                authority_signer=real_signer,
                accepted_event_signers=policy.transition_signer_identities,
                accepted_authority_signers=policy.authority_signer_identities,
                signature_verifier=verifier,
            )
            raw = authority.serialize_lifecycle_evidence(
                delivery_initialization=initialization,
                transition_authorizations=[event],
                authority_chain=[snapshot],
            )
            review_raw = authority.serialize_lifecycle_evidence(
                delivery_initialization=initialization,
                transition_authorizations=[event, review_event],
                authority_chain=[snapshot, review_snapshot],
            )
            current_raw = authority.serialize_lifecycle_evidence(
                delivery_initialization=initialization,
                transition_authorizations=[
                    event,
                    review_event,
                    ready_event,
                    rebound_event,
                ],
                authority_chain=[
                    snapshot,
                    review_snapshot,
                    ready_snapshot,
                    rebound_snapshot,
                ],
            )
            current_policy = authority.LifecycleTrustPolicy(
                REPOSITORY,
                policy.accepted_formats,
                policy.transition_signer_identities,
                policy.authority_signer_identities,
                policy.signers,
                (
                    authority.InitializationAnchor(
                        ISSUE,
                        PR,
                        HEADS[0],
                        digest,
                        PR + 1,
                        HEADS[0],
                        rebound_snapshot["authority_digest"],
                    ),
                ),
            )
            with patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=current_policy
            ):
                result = authority.verify_lifecycle_authority(
                    current_raw,
                    authority.ExpectedLifecycle(
                        REPOSITORY, ISSUE, lifecycle, PR + 1, HEADS[0]
                    ),
                )
                self.assertEqual(result.lifecycle_id, lifecycle)
                self.assertTrue(result.state["ready"])
                self.assertEqual(result.pull_request, PR + 1)
                for malformed_transition in ([], {}, True, 1, None, "UNKNOWN"):
                    malformed = json.loads(current_raw)
                    malformed["transition_authorizations"][-1][
                        "transition_kind"
                    ] = malformed_transition
                    with self.subTest(transition_kind=malformed_transition):
                        with self.assertRaises(authority.LifecycleAuthorityError):
                            authority.verify_lifecycle_authority(
                                authority.canonical_json_bytes(malformed)
                            )
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError, "current terminal"
                ):
                    authority.verify_lifecycle_authority(
                        raw,
                        authority.ExpectedLifecycle(
                            REPOSITORY, ISSUE, lifecycle, PR, HEADS[0]
                        ),
                    )
                selector_variants = (
                    authority.InitializationAnchor(
                        ISSUE,
                        PR,
                        HEADS[0],
                        digest,
                        PR + 1,
                        HEADS[0],
                        ready_snapshot["authority_digest"],
                    ),
                    authority.InitializationAnchor(
                        ISSUE,
                        PR,
                        HEADS[0],
                        digest,
                        PR,
                        HEADS[0],
                        rebound_snapshot["authority_digest"],
                    ),
                    authority.InitializationAnchor(
                        ISSUE,
                        PR,
                        HEADS[0],
                        digest,
                        PR + 1,
                        HEADS[1],
                        rebound_snapshot["authority_digest"],
                    ),
                    authority.InitializationAnchor(
                        ISSUE,
                        PR,
                        HEADS[0],
                        digest,
                        PR + 1,
                        HEADS[0],
                        "9" * 64,
                    ),
                )
                for selector in selector_variants:
                    mismatched_policy = authority.LifecycleTrustPolicy(
                        REPOSITORY,
                        policy.accepted_formats,
                        policy.transition_signer_identities,
                        policy.authority_signer_identities,
                        policy.signers,
                        (selector,),
                    )
                    with self.subTest(selector=selector):
                        with patch.object(
                            authority,
                            "_load_lifecycle_trust_policy",
                            return_value=mismatched_policy,
                        ):
                            with self.assertRaises(authority.LifecycleAuthorityError):
                                authority.verify_lifecycle_authority(current_raw)
                missing_policy = authority.LifecycleTrustPolicy(
                    REPOSITORY,
                    policy.accepted_formats,
                    policy.transition_signer_identities,
                    policy.authority_signer_identities,
                    policy.signers,
                    (),
                )
                with patch.object(
                    authority,
                    "_load_lifecycle_trust_policy",
                    return_value=missing_policy,
                ):
                    with self.assertRaises(authority.LifecycleAuthorityError):
                        authority.verify_lifecycle_authority(current_raw)
                cross_issue_policy = authority.LifecycleTrustPolicy(
                    REPOSITORY,
                    policy.accepted_formats,
                    policy.transition_signer_identities,
                    policy.authority_signer_identities,
                    policy.signers,
                    (
                        authority.InitializationAnchor(
                            ISSUE + 1,
                            PR,
                            HEADS[0],
                            digest,
                            PR + 1,
                            HEADS[0],
                            rebound_snapshot["authority_digest"],
                        ),
                    ),
                )
                cross_repository_policy = authority.LifecycleTrustPolicy(
                    "Other/repository",
                    policy.accepted_formats,
                    policy.transition_signer_identities,
                    policy.authority_signer_identities,
                    policy.signers,
                    current_policy.initialization_anchors,
                )
                for mismatched_policy in (
                    cross_issue_policy,
                    cross_repository_policy,
                ):
                    with patch.object(
                        authority,
                        "_load_lifecycle_trust_policy",
                        return_value=mismatched_policy,
                    ):
                        with self.assertRaises(authority.LifecycleAuthorityError):
                            authority.verify_lifecycle_authority(current_raw)
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError, "current terminal"
                ):
                    authority.verify_lifecycle_authority(
                        review_raw,
                        authority.ExpectedLifecycle(
                            REPOSITORY, ISSUE, lifecycle, PR, HEADS[0]
                        ),
                    )
                with self.assertRaises(authority.LifecycleAuthorityError):
                    authority.verify_lifecycle_authority(json.loads(raw))
                for field in (
                    '"delivery_issue":750',
                    '"event_id":"genesis:',
                    '"initial_head_sha":"',
                ):
                    ambiguous = raw.decode().replace(field, field, 1)
                    if field == '"delivery_issue":750':
                        ambiguous = ambiguous.replace(
                            field, '"delivery_issue":999,"delivery_issue":750', 1
                        )
                    elif field == '"event_id":"genesis:':
                        ambiguous = ambiguous.replace(
                            field,
                            '"event_id":"other","event_id":"genesis:',
                            1,
                        )
                    else:
                        ambiguous = ambiguous.replace(
                            field,
                            '"initial_head_sha":"' + HEADS[1] + '","initial_head_sha":"',
                            1,
                        )
                    with self.assertRaisesRegex(
                        authority.LifecycleAuthorityError, "duplicate"
                    ):
                        authority.verify_lifecycle_authority(ambiguous)
                unanchored_policy = authority.LifecycleTrustPolicy(
                    REPOSITORY,
                    policy.accepted_formats,
                    policy.transition_signer_identities,
                    policy.authority_signer_identities,
                    policy.signers,
                    (
                        authority.InitializationAnchor(
                            ISSUE,
                            PR,
                            HEADS[0],
                            "9" * 64,
                            PR,
                            HEADS[0],
                            rebound_snapshot["authority_digest"],
                        ),
                    ),
                )
                with patch.object(
                    authority,
                    "_load_lifecycle_trust_policy",
                    return_value=unanchored_policy,
                ):
                    with self.assertRaisesRegex(
                        authority.LifecycleAuthorityError, "unique maintained"
                    ):
                        authority.verify_lifecycle_authority(raw)
                later_initialization = authority.create_delivery_initialization(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    initial_head_sha=HEADS[1],
                    validation_receipt_digest="3" * 64,
                    final_attestation_digest="4" * 64,
                    signer_identity=SIGNER,
                    signer=real_signer,
                )
                later_raw = authority.serialize_lifecycle_evidence(
                    delivery_initialization=later_initialization,
                    transition_authorizations=[event],
                    authority_chain=[snapshot],
                )
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError, "unique maintained"
                ):
                    authority.verify_lifecycle_authority(later_raw)

            authority_signature = real_signer(
                payload=b"payload", domain=authority.AUTHORITY_DOMAIN
            )
            with self.assertRaises(authority.LifecycleAuthorityError):
                verifier(
                    b"payload",
                    authority_signature,
                    SIGNER,
                    authority.EVENT_DOMAIN,
                )
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority._verify_signature(
                    b"payload",
                    {
                        "format": "ssh",
                        "signer_identity": OTHER_SIGNER,
                        "value": authority_signature["value"],
                    },
                    OTHER_SIGNER,
                    authority.EVENT_DOMAIN,
                    policy.transition_signer_identities,
                    verifier,
                )

    def test_genesis_requires_canonical_anchor_identity(self) -> None:
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "derived"):
            authority.create_transition_authorization(
                event_id=f"genesis:{INITIALIZATION_DIGEST}",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id="caller-selected-lifecycle",
                pull_request=PR,
                predecessor_authority_digest=None,
                predecessor_head_sha=None,
                resulting_head_sha=HEADS[0],
                transition_kind="INITIALIZED_DRAFT",
                replacement_pull_request=None,
                initialization_evidence_digest=INITIALIZATION_DIGEST,
                signer_identity=SIGNER,
                signer=signer_for(),
            )
        other_initialization = "3" * 64
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "derived"):
            authority.create_transition_authorization(
                event_id=f"genesis:{other_initialization}",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=LIFECYCLE,
                pull_request=PR,
                predecessor_authority_digest=None,
                predecessor_head_sha=None,
                resulting_head_sha=HEADS[1],
                transition_kind="INITIALIZED_DRAFT",
                replacement_pull_request=None,
                initialization_evidence_digest=other_initialization,
                signer_identity=SIGNER,
                signer=signer_for(),
            )
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "canonical"):
            authority.create_transition_authorization(
                event_id="alternate-root",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=LIFECYCLE,
                pull_request=PR,
                predecessor_authority_digest=None,
                predecessor_head_sha=None,
                resulting_head_sha=HEADS[0],
                transition_kind="INITIALIZED_DRAFT",
                replacement_pull_request=None,
                initialization_evidence_digest=INITIALIZATION_DIGEST,
                signer_identity=SIGNER,
                signer=signer_for(),
            )

    def test_nonfinite_and_noncanonical_raw_json_rejected(self) -> None:
        for raw in ('{"value":NaN}', '{"value":Infinity}'):
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.loads_closed_json(raw)
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "canonical"):
            authority.verify_lifecycle_authority("{}")

    def test_real_openpgp_policy_adapter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lifecycle-gpg-test-") as directory:
            environment = {**os.environ, "GNUPGHOME": directory}
            subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--passphrase",
                    "",
                    "--quick-gen-key",
                    SIGNER,
                    "ed25519",
                    "sign",
                    "0",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            listing = subprocess.run(
                ["gpg", "--batch", "--with-colons", "--list-secret-keys", SIGNER],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout
            fingerprint = next(
                line.split(":")[9]
                for line in listing.splitlines()
                if line.startswith("fpr:")
            )
            payload = authority.canonical_json_bytes({"domain": authority.EVENT_DOMAIN})
            signature = subprocess.run(
                ["gpg", "--batch", "--armor", "--detach-sign", "--output", "-"],
                env=environment,
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode()
            policy = authority.LifecycleTrustPolicy(
                REPOSITORY,
                frozenset({"openpgp"}),
                frozenset({SIGNER}),
                frozenset({SIGNER}),
                {SIGNER: authority.TrustedSigner(SIGNER, (), (fingerprint,))},
                (),
            )
            with patch.dict(os.environ, {"GNUPGHOME": directory}):
                verified = authority._policy_signature_verifier(policy)(
                    payload,
                    {
                        "format": "openpgp",
                        "signer_identity": SIGNER,
                        "value": signature,
                    },
                    SIGNER,
                    authority.EVENT_DOMAIN,
                )
            self.assertEqual(verified.signature_format, "openpgp")

    def test_authenticated_draft_genesis(self) -> None:
        chain = genesis_chain()
        result = chain.verify(
            authority.ExpectedLifecycle(REPOSITORY, ISSUE, LIFECYCLE, PR, HEADS[0])
        )
        self.assertEqual(result.state, authority.initial_state())
        self.assertFalse(result.state["ready"])
        self.assertTrue(result.state["cycle_3_absent"])

    def test_review_and_finite_remediation_progression(self) -> None:
        chain = reviewed_chain()
        self.assertEqual(chain.verify().state["unrestricted_review_count"], 1)
        chain.append("REMEDIATION_COMPLETED", head=HEADS[1])
        chain.append("REMEDIATION_COMPLETED", head=HEADS[2])
        self.assertEqual(chain.verify().state["remediation_cycle_count"], 2)
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "Cycle 3"):
            chain.append("REMEDIATION_COMPLETED", head=HEADS[3])

    def test_complete_positive_transition_chain_and_binding(self) -> None:
        chain = ready_chain()
        self.assertEqual(chain.verify().state["ready_transition_count"], 1)
        chain.append("HEAD_ADVANCED", head=HEADS[2])
        self.assertEqual(chain.verify().state["ready_transition_count"], 1)
        chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[3])
        self.assertTrue(chain.verify().state["ready"])
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        chain.append("READY_TO_DRAFT")
        chain.append("DRAFT_TO_READY")
        chain.append("PR_REBOUND", replacement_pull_request=752)
        result = chain.verify(
            authority.ExpectedLifecycle(
                REPOSITORY, ISSUE, LIFECYCLE, 752, HEADS[4],
                unrestricted_review_count=1, remediation_cycle_count=1,
                ready=True, ready_transition_count=2,
                exceptional_recovery_count=1, exceptional_continuation_count=1,
            )
        )
        self.assertEqual(
            [item["transition_kind"] for item in result.state["ready_history"]],
            ["DRAFT_TO_READY", "READY_TO_DRAFT", "DRAFT_TO_READY"],
        )
        binding = authority.lifecycle_authority_binding(result)
        self.assertEqual(binding["lifecycle_authority_digest"], result.authority_digest)
        self.assertEqual(binding["verified_facts"]["remediation_cycle_count"], 1)
        unsigned = {key: value for key, value in binding.items() if key != "binding_digest"}
        self.assertEqual(binding["binding_digest"], authority.digest_json(unsigned))

    def test_ready_draft_ready_preserves_counters_and_history(self) -> None:
        chain = ready_chain()
        chain.append("READY_TO_DRAFT")
        chain.append("DRAFT_TO_READY")
        result = chain.verify().state
        self.assertEqual(result["unrestricted_review_count"], 1)
        self.assertEqual(result["remediation_cycle_count"], 1)
        self.assertEqual(result["ready_transition_count"], 2)
        self.assertEqual(len(result["ready_history"]), 3)

    def test_head_recovery_continuation_and_replacement_preserve_state(self) -> None:
        chain = ready_chain()
        initial = chain.verify()
        chain.append("HEAD_ADVANCED", head=HEADS[2])
        chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[3])
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        before_replacement = chain.verify()
        self.assertEqual(before_replacement.state["ready_history"], initial.state["ready_history"])
        self.assertEqual(before_replacement.state["ready_transition_count"], 1)
        chain.append("PR_REBOUND", replacement_pull_request=752)
        result = chain.verify()
        self.assertEqual(result.lifecycle_id, initial.lifecycle_id)
        self.assertEqual(
            result.initialization_evidence_digest,
            initial.initialization_evidence_digest,
        )
        self.assertEqual(result.state, before_replacement.state)
        self.assertEqual(result.pull_request, 752)

    def test_ready_to_draft_requires_typed_authorization(self) -> None:
        chain = ready_chain()
        before = chain.verify().state
        chain.append("READY_TO_DRAFT")
        self.assertFalse(chain.verify().state["ready"])
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.derive_state(
                before, "HEAD_ADVANCED", "0" * 64, resulting_state={"ready": False}
            )

    def test_additional_review_authorization_is_persistent_without_new_cycle(self) -> None:
        chain = ready_chain()
        before = chain.verify()
        chain.append("ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED")
        after = chain.verify()

        self.assertNotEqual(after.authority_digest, before.authority_digest)
        self.assertEqual(after.state, before.state)
        self.assertEqual(after.state["unrestricted_review_count"], 1)
        self.assertEqual(after.state["remediation_cycle_count"], 1)
        self.assertTrue(after.state["cycle_3_absent"])

    def test_finite_budgets_and_event_replay_fail_closed(self) -> None:
        chain = reviewed_chain()
        with self.assertRaises(authority.LifecycleAuthorityError):
            chain.append("UNRESTRICTED_REVIEW_CONSUMED")
        chain = ready_chain()
        chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[2])
        with self.assertRaises(authority.LifecycleAuthorityError):
            chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[3])
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[3])
        with self.assertRaises(authority.LifecycleAuthorityError):
            chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        with self.assertRaises(authority.LifecycleAuthorityError):
            verify_raw(chain.authorities, [chain.events[0]] * len(chain.events))

    def test_missing_substituted_stale_or_truncated_predecessor_rejected(self) -> None:
        chain = reviewed_chain()
        cases: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = [
            (chain.authorities[1:], chain.events[1:]),
            (chain.authorities, chain.events[:-1]),
        ]
        changed = copy.deepcopy(chain.authorities)
        changed[1]["predecessor_authority_digest"] = "9" * 64
        changed[1] = resign_authority(changed[1])
        cases.append((changed, chain.events))
        stale = copy.deepcopy(chain.events)
        stale[1]["predecessor_authority_digest"] = "8" * 64
        stale[1] = resign_event(stale[1])
        cases.append((chain.authorities, stale))
        for snapshots, events in cases:
            with self.subTest(snapshots=len(snapshots), events=len(events)):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    verify_raw(snapshots, events)

    def test_repository_issue_pr_head_and_lifecycle_replay_rejected(self) -> None:
        chain = ready_chain()
        constraints = [
            authority.ExpectedLifecycle("Other/repo", ISSUE, LIFECYCLE, PR, HEADS[1]),
            authority.ExpectedLifecycle(REPOSITORY, 999, LIFECYCLE, PR, HEADS[1]),
            authority.ExpectedLifecycle(REPOSITORY, ISSUE, "other-lifecycle", PR, HEADS[1]),
            authority.ExpectedLifecycle(REPOSITORY, ISSUE, LIFECYCLE, 999, HEADS[1]),
            authority.ExpectedLifecycle(REPOSITORY, ISSUE, LIFECYCLE, PR, HEADS[9]),
        ]
        for expected in constraints:
            with self.subTest(expected=expected):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    chain.verify(expected)

    def test_counters_cycle3_and_ready_history_tampering_rejected(self) -> None:
        chain = ready_chain()
        mutations = [
            ("unrestricted_review_count", 0),
            ("remediation_cycle_count", 0),
            ("remediation_cycle_count", 3),
            ("cycle_3_absent", False),
            ("ready_transition_count", 0),
            ("ready_history", []),
            ("unrestricted_review_count", True),
        ]
        for field, value in mutations:
            tampered = copy.deepcopy(chain.authorities)
            tampered[-1]["state_after"][field] = value
            tampered[-1] = resign_authority(tampered[-1])
            with self.subTest(field=field, value=value):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    verify_raw(tampered, chain.events)

    def test_hidden_or_duplicated_ready_churn_rejected(self) -> None:
        chain = ready_chain()
        chain.append("READY_TO_DRAFT")
        chain.append("DRAFT_TO_READY")
        histories = [
            chain.authorities[-1]["state_after"]["ready_history"][-1:],
            chain.authorities[-1]["state_after"]["ready_history"] * 2,
        ]
        for history in histories:
            tampered = copy.deepcopy(chain.authorities)
            tampered[-1]["state_after"]["ready_history"] = history
            tampered[-1] = resign_authority(tampered[-1])
            with self.assertRaises(authority.LifecycleAuthorityError):
                verify_raw(tampered, chain.events)

    def test_erased_exceptional_histories_rejected(self) -> None:
        chain = ready_chain()
        chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[2])
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[3])
        fields = [
            ("exceptional_recovery_count", "exceptional_recovery_history"),
            ("exceptional_continuation_count", "exceptional_continuation_history"),
        ]
        for count, history in fields:
            tampered = copy.deepcopy(chain.authorities)
            tampered[-1]["state_after"][count] = 0
            tampered[-1]["state_after"][history] = []
            tampered[-1] = resign_authority(tampered[-1])
            with self.subTest(field=count):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    verify_raw(tampered, chain.events)

    def test_replacement_cannot_mint_lifecycle_or_cross_issue(self) -> None:
        chain = ready_chain()
        event = authority.create_transition_authorization(
            event_id="bad-replacement", repository=REPOSITORY, delivery_issue=999,
            lifecycle_id="minted-lifecycle", pull_request=PR,
            predecessor_authority_digest=chain.authorities[-1]["authority_digest"],
            predecessor_head_sha=chain.head, resulting_head_sha=chain.head,
            transition_kind="PR_REBOUND", replacement_pull_request=752,
            initialization_evidence_digest=INITIALIZATION_DIGEST,
            signer_identity=SIGNER, signer=signer_for(),
        )
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.issue_lifecycle_authority(
                predecessor_chain=chain.authorities,
                transition_authorizations=chain.events,
                authorization=event, signer_identity=SIGNER,
                authority_signer=signer_for(),
                accepted_event_signers=frozenset({SIGNER}),
                accepted_authority_signers=frozenset({SIGNER}),
                signature_verifier=verify_signature,
            )

    def test_unsigned_wrong_signer_and_malformed_signature_rejected(self) -> None:
        chain = genesis_chain()
        unsigned = copy.deepcopy(chain.authorities)
        unsigned[-1]["signature"] = None
        malformed = copy.deepcopy(chain.authorities)
        malformed[-1]["signature"]["value"] = ""
        wrong = copy.deepcopy(chain.authorities)
        wrong[-1] = resign_authority(wrong[-1], OTHER_SIGNER)
        for values in (unsigned, malformed, wrong):
            with self.assertRaises(authority.LifecycleAuthorityError):
                verify_raw(values, chain.events)

    def test_unknown_schema_kind_domain_transition_and_fields_rejected(self) -> None:
        chain = genesis_chain()
        variants: list[list[dict[str, Any]]] = []
        for field, value in (
            ("schema_version", "2.0"), ("kind", "OTHER"),
            ("domain", "other.domain/v1"),
            ("transition_kind", "CYCLE_3"),
            ("transition_kind", []),
            ("transition_kind", {}),
        ):
            changed = copy.deepcopy(chain.authorities)
            changed[-1][field] = value
            changed[-1] = resign_authority(changed[-1])
            variants.append(changed)
        extra = copy.deepcopy(chain.authorities)
        extra[-1]["extension"] = "unsafe"
        variants.append(extra)
        for values in variants:
            with self.assertRaises(authority.LifecycleAuthorityError):
                verify_raw(values, chain.events)
        for field, value in (
            ("schema_version", "2.0"),
            ("kind", "OTHER"),
            ("domain", "other.domain/v1"),
            ("transition_kind", "CYCLE_3"),
        ):
            changed_events = copy.deepcopy(chain.events)
            changed_events[-1][field] = value
            changed_events[-1] = resign_event(changed_events[-1])
            with self.subTest(event_field=field):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    verify_raw(chain.authorities, changed_events)

    def test_duplicate_json_fields_and_canonical_serialization(self) -> None:
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "duplicate"):
            authority.loads_closed_json('{"kind":"a","kind":"b"}')
        chain = genesis_chain()
        raw = authority.canonical_json_bytes(chain.authorities[-1])
        reordered = dict(reversed(list(chain.authorities[-1].items())))
        self.assertEqual(raw, authority.canonical_json_bytes(reordered))
        self.assertEqual(authority.loads_closed_json(raw), chain.authorities[-1])

    def test_consumer_generated_self_authority_rejected(self) -> None:
        chain = genesis_chain()
        forged = copy.deepcopy(chain.authorities[-1])
        forged["state_after"]["unrestricted_review_count"] = 1
        forged["state_after"]["remediation_cycle_count"] = 2
        forged = resign_authority(forged)
        with self.assertRaises(authority.LifecycleAuthorityError):
            verify_raw([forged], chain.events)
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.derive_state(
                authority.initial_state(), "HEAD_ADVANCED", "0" * 64,
                resulting_state={"remediation_cycle_count": 2},
            )
        with self.assertRaises(authority.LifecycleAuthorityError):
            chain.verify(
                authority.ExpectedLifecycle(
                    REPOSITORY,
                    ISSUE,
                    LIFECYCLE,
                    PR,
                    HEADS[0],
                    unrestricted_review_count=True,
                )
            )

    def test_predecessor_head_substitution_and_event_digest_mismatch_rejected(self) -> None:
        chain = reviewed_chain()
        changed = copy.deepcopy(chain.events)
        changed[-1]["predecessor_head_sha"] = HEADS[9]
        changed[-1] = resign_event(changed[-1])
        with self.assertRaises(authority.LifecycleAuthorityError):
            verify_raw(chain.authorities, changed)
        changed = copy.deepcopy(chain.events)
        changed[-1]["event_digest"] = "0" * 64
        with self.assertRaises(authority.LifecycleAuthorityError):
            verify_raw(chain.authorities, changed)


class ValidationEvidenceLossTests(TestCase):
    def setUp(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        self.loss = loss
        self.record = json.loads((REPO_ROOT / loss.POLICY_PATH).read_text())["admissions"][0]
        self.migration = "lifecycle-legacy-adoption@secpal.app"
        self.trust = authority.LifecycleTrustPolicy(
            repository=REPOSITORY, accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
            legacy_adoption_signer_identities=frozenset({self.migration}),
            signers={
                SIGNER: authority.TrustedSigner(SIGNER, ("source-key",), ()),
                self.migration: authority.TrustedSigner(self.migration, ("migration-key",), ()),
            }, initialization_anchors=(), publication_remote_url="https://github.com/SecPal/.github.git",
        )
        for name, value in (
            ("_load_lifecycle_trust_policy", self.trust),
            ("_policy_signature_verifier", verify_signature),
        ):
            patcher = patch.object(authority, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.acquired = {
            **{key: copy.deepcopy(value) for key, value in self.record.items()
               if key not in {"feedback_digest", "technical_decisions"}},
            "pull_request_state": "OPEN", "draft": True,
            "commit_signature_evidence_digest": "3" * 64,
            "loss_proof_policy_digest": authority.digest_json(self.record),
            "accepted_main_sha": "c" * 40,
            "intended_state": loss._intended_state(),
            "current_safety": {
                "receipt_digest": "e210f448c7ed9c123ef2e991684f3706a0ca30b096005fce37a2103a9bdcfa15",
                "validated_tree_sha": self.record["tree_sha"],
                "validation_policy_digest": "4" * 64,
                "command_set_digest": "5" * 64,
                "feedback_digest": self.record["feedback_digest"],
                "technical_decisions": [], "successful_result": True,
            },
        }
        self.document = self.sign({
            "schema_version": "1.0", "kind": loss.KIND, "domain": loss.DOMAIN,
            **self.acquired, "adoption_timestamp": "2026-09-06T12:00:00Z",
            "admission_id": "loss:827:830", "bounded_uses": 1,
            "signer_identity": self.migration,
        })

    def sign(self, value: dict[str, Any]) -> dict[str, Any]:
        fields = copy.deepcopy(value)
        fields.pop("admission_digest", None)
        fields.pop("signature", None)
        fields["signature"] = signer_for(fields["signer_identity"])(
            authority.canonical_json_bytes(fields), self.loss.DOMAIN,
        )
        return {**fields, "admission_digest": authority.digest_json(fields)}

    def test_public_verifier_reauthenticates_exact_signed_context(self) -> None:
        with patch.object(self.loss, "_acquire", return_value=self.acquired) as acquire:
            verified = self.loss.verify(authority.canonical_json_bytes(self.document))
            self.assertEqual(self.loss._verified_document(verified), self.document)
            acquire.assert_called_once_with(REPOSITORY, 827, execute_validation=False)
        substitutions = {
            "repository": "Example/governance", "delivery_issue": 828, "pull_request": 831,
            "head_sha": "a" * 40, "tree_sha": "b" * 40, "parent_sha": "d" * 40,
            "source_signer_identity": OTHER_SIGNER, "commit_signature_evidence_digest": "0" * 64,
            "loss_proof_policy_digest": "0" * 64, "accepted_main_sha": "d" * 40,
        }
        for field, replacement in substitutions.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(self.document)
                changed[field] = replacement
                with patch.object(self.loss, "_acquire", return_value=self.acquired):
                    with self.assertRaises(authority.LifecycleAuthorityError):
                        self.loss.verify(authority.canonical_json_bytes(self.sign(changed)))

    def test_closed_loss_truth_and_finite_state(self) -> None:
        substitutions = {
            "draft": False, "pull_request_state": "CLOSED", "bounded_uses": 2,
            "historical_package_status": "RECONSTRUCTED",
            "historical_final_attestation_digest": "2" * 64,
            "historical_bytes_reconstructed": True, "signer_identity": SIGNER,
            "observed_pre_enrollment_history": self.record["observed_pre_enrollment_history"][:-1],
        }
        for field, replacement in substitutions.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(self.document)
                changed[field] = replacement
                with self.assertRaises(authority.LifecycleAuthorityError):
                    self.loss._verify_document(self.sign(changed))
        for field, value in self.document["intended_state"].items():
            with self.subTest(counter=field):
                changed = copy.deepcopy(self.document)
                changed["intended_state"][field] = (
                    not value if type(value) is bool else
                    value + ["fabricated"] if isinstance(value, list) else value + 1
                )
                with self.assertRaises(authority.LifecycleAuthorityError):
                    self.loss._verify_document(self.sign(changed))
        changed = copy.deepcopy(self.document)
        changed["current_safety"]["successful_result"] = False
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.loss._verify_document(self.sign(changed))

    def test_no_unsigned_loss_or_signature_substitution(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["signature"] = signer_for(OTHER_SIGNER)(b"other context", self.loss.DOMAIN)
        changed["admission_digest"] = authority.digest_json({
            key: value for key, value in changed.items() if key != "admission_digest"
        })
        with self.assertRaises((authority.LifecycleAuthorityError, ValueError)):
            self.loss._verify_document(changed)
        for value in (self.document, SimpleNamespace(canonical_admission=self.document),
                      self.loss.VerifiedPreEnrollmentValidationEvidenceLossAdmission(self.document, object())):
            with self.subTest(value=type(value)):
                with self.assertRaises(authority.LifecycleAuthorityError):
                    self.loss._verified_document(value)

    def test_historical_package_never_downgrades(self) -> None:
        with patch.object(self.loss, "_acquire") as acquire:
            for package in (None, {}, {"receipt": {}}, b"reconstructed", self.document):
                with self.subTest(package=package):
                    with self.assertRaises(authority.LifecycleAuthorityError):
                        self.loss.issue(REPOSITORY, 827, historical_package=package)
            acquire.assert_not_called()

    def test_caller_cannot_select_acquisition_authority(self) -> None:
        for field in ("registry", "validation_commands", "successful_result", "feedback",
                      "signer", "intended_state", "source_identity", "current", "loss"):
            with self.subTest(field=field), patch.object(self.loss, "_acquire") as acquire:
                with self.assertRaises(TypeError):
                    self.loss.issue(REPOSITORY, 827, **{field: {}})
                acquire.assert_not_called()

    def test_live_current_presence_blocks_replay_not_historical_provenance(self) -> None:
        with patch.object(self.loss, "_acquire", side_effect=authority.LifecycleAuthorityError("CURRENT exists")):
            with self.assertRaisesRegex(authority.LifecycleAuthorityError, "CURRENT"):
                self.loss.verify(authority.canonical_json_bytes(self.document))
            self.assertEqual(self.loss._verify_document(self.document), self.document)

    def test_current_registered_validation_uses_entry_then_immutable_root(self) -> None:
        entry = {"name": REPOSITORY}
        reviewed = SimpleNamespace(state_digest="a" * 64, feedback_digest=self.record["feedback_digest"])

        def validate(actual_entry: Any, root: Any) -> bool:
            self.assertIs(actual_entry, entry)
            self.assertIsInstance(root, Path)
            self.assertTrue(root.is_dir())
            return True

        helper = SimpleNamespace(
            _fast_registry_binding=lambda entry: {"policy": "current"},
            _complete_validation_commands=lambda entry: (),
            _run_registered_validations=Mock(side_effect=validate),
        )

        def git_text(root: Path, arguments: list[str]) -> str:
            if arguments == ["rev-parse", "HEAD^{tree}"]:
                return self.record["tree_sha"]
            if arguments == ["rev-list", "--parents", "-n", "1", "HEAD"]:
                return f'{self.record["head_sha"]} {self.record["parent_sha"]}'
            if arguments == ["diff", "--name-only", "HEAD"]:
                return ""
            return self.record["head_sha"]

        with patch.object(self.loss, "_accepted_policy", return_value=("c" * 40, self.record, entry, self.trust)), patch.object(
            self.loss, "_observe", return_value=({}, reviewed)
        ), patch.object(self.loss.transport, "_load_actions_helper", return_value=helper), patch.object(
            self.loss.transport, "_git"
        ), patch.object(self.loss.transport, "_git_text", side_effect=git_text), patch.object(
            self.loss, "_source_signature", return_value="3" * 64
        ), patch.object(self.loss.transport, "_exact_trailer", return_value=self.record["historical_validation_receipt_digest"]):
            with patch.object(self.loss, "_prepare_dependencies"), patch.object(self.loss, "_verify_source_bytes"):
                result = self.loss._acquire(REPOSITORY, 827, execute_validation=True)
            self.assertTrue(result["current_safety"]["successful_result"])
            helper._run_registered_validations.assert_called_once()
            helper._run_registered_validations.reset_mock()
            with patch.object(self.loss, "_prepare_dependencies") as prepare, patch.object(self.loss, "_verify_source_bytes"):
                self.loss._acquire(REPOSITORY, 827, execute_validation=False)
            prepare.assert_not_called()
            helper._run_registered_validations.assert_not_called()

    def test_source_mutation_cannot_hide_behind_index_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for arguments in (["init", "--quiet"],):
                subprocess.run(["git", "-C", str(root), *arguments], check=True)
            source = root / "source.py"
            source.write_text("original\n")
            subprocess.run(["git", "-C", str(root), "add", "source.py"], check=True)
            tree = subprocess.check_output(["git", "-C", str(root), "write-tree"], text=True).strip()
            listing = self.loss._verify_source_bytes(root, tree)
            subprocess.run(["git", "-C", str(root), "update-index", "--assume-unchanged", "source.py"], check=True)
            source.write_text("mutated\n")
            with self.assertRaisesRegex(authority.LifecycleAuthorityError, "source bytes"):
                self.loss._verify_source_bytes(root, tree)
            with patch.object(self.loss.transport, "_git_text", side_effect=lambda actual_root, args: (
                subprocess.check_output(["git", "-C", str(actual_root), *args], text=True)
                if args[0] == "hash-object" else "substituted tree"
            )):
                with self.assertRaisesRegex(authority.LifecycleAuthorityError, "source bytes"):
                    self.loss._verify_source_bytes(root, tree, expected_listing=listing)
            source.unlink()
            source.symlink_to("/dev/null")
            with self.assertRaises(authority.LifecycleAuthorityError):
                self.loss._verify_source_bytes(root, tree)

    def test_dependency_setup_is_fixed_locked_and_credential_free(self) -> None:
        helper = SimpleNamespace(
            _validation_executable=lambda command, working, root: "/usr/bin/npm",
            LOCAL_VALIDATION_COMMAND_DIRECTORIES=(Path("/usr/bin"), Path("/bin")),
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(self.loss.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                self.loss._prepare_dependencies(Path(directory), helper)
            args, keywords = run.call_args
            self.assertEqual(args[0], ["/usr/bin/npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"])
            self.assertFalse(keywords.get("shell", False))
            self.assertEqual(keywords["timeout"], 600)
            self.assertEqual(set(keywords["env"]), {
                "HOME", "PATH", "LANG", "LC_ALL", "NPM_CONFIG_USERCONFIG", "NPM_CONFIG_GLOBALCONFIG",
            })
            self.assertNotEqual(keywords["env"]["NPM_CONFIG_USERCONFIG"], keywords["env"]["NPM_CONFIG_GLOBALCONFIG"])
            for key in ("NPM_CONFIG_USERCONFIG", "NPM_CONFIG_GLOBALCONFIG"):
                self.assertEqual(Path(keywords["env"][key]).parent, Path(keywords["env"]["HOME"]))

    def test_dependency_environment_is_accepted_by_real_npm(self) -> None:
        real_run = subprocess.run

        def probe_config(arguments: list[str], **keywords: Any) -> Any:
            return real_run([arguments[0], "config", "get", "ignore-scripts"], **keywords)

        with tempfile.TemporaryDirectory() as directory, patch.object(
            self.loss.subprocess, "run", side_effect=probe_config
        ):
            self.loss._prepare_dependencies(Path(directory), self.loss.transport._load_actions_helper())

    def provider_facts(self) -> list[Any]:
        history = self.record["observed_pre_enrollment_history"]
        target = {
            "number": 830, "state": "open", "draft": True, "merged_at": None,
            "head": {"sha": self.record["head_sha"], "repo": {"full_name": REPOSITORY}},
            "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
            "created_at": history[0]["observed_at"],
        }
        commits = [{
            "sha": observation["head_sha"],
            "parents": [{"sha": history[index - 1]["head_sha"] if index else "4" * 40}],
            "commit": {"committer": {"date": observation["observed_at"]}},
        } for index, observation in enumerate(history)]
        source = {
            "sha": self.record["head_sha"], "parents": [{"sha": self.record["parent_sha"]}],
            "commit": {"tree": {"sha": self.record["tree_sha"]}, "verification": {"verified": True}},
        }
        return [target, {"number": 827, "state": "open"}, commits, [], source]

    def reviewed_state(self) -> Any:
        return fast_path.StableFeedbackState(
            repository=REPOSITORY, pull_request_number=830,
            head_sha=self.record["head_sha"], base_ref="main", base_sha="c" * 40,
            pr_state="OPEN", feedback={
                "pull_request_reactions": [], "reviews": [], "conversation_comments": [], "threads": [],
            },
        )

    def observe(self, facts: list[Any], *, reviewed: Any = None) -> Any:
        helper = SimpleNamespace(FastPathGateway=lambda root, entry: SimpleNamespace(
            capture_stable_feedback=lambda repository, pr: reviewed or self.reviewed_state(),
        ))
        with patch.object(self.loss, "_gh_json", side_effect=facts), patch.object(
            self.loss.transport, "_load_actions_helper", return_value=helper
        ), patch.object(self.loss.publication, "require_unenrolled_delivery"):
            return self.loss._observe(self.record, {}, self.trust)

    def test_provider_acquisition_checks_exact_open_draft_history_and_signature(self) -> None:
        self.assertEqual(self.observe(self.provider_facts())[0]["sha"], self.record["head_sha"])
        cases = [
            (0, ("draft",), False), (0, ("state",), "closed"),
            (0, ("merged_at",), "2026-09-06T00:00:00Z"),
            (0, ("head", "sha"), "a" * 40),
            (0, ("head", "repo", "full_name"), "Example/governance"),
            (0, ("base", "ref"), "candidate"), (1, ("number",), 828),
            (4, ("sha",), "a" * 40), (4, ("commit", "tree", "sha"), "b" * 40),
            (4, ("commit", "verification", "verified"), False),
            (4, ("parents",), [{"sha": "d" * 40}]),
        ]
        for index, path, value in cases:
            with self.subTest(index=index, path=path):
                facts = self.provider_facts()
                current = facts[index]
                for key in path[:-1]:
                    current = current[key]
                current[path[-1]] = value
                with self.assertRaises(authority.LifecycleAuthorityError):
                    self.observe(facts)
        for index, value in ((2, self.provider_facts()[2][1:]), (3, [{"event": "ready_for_review"}]),
                             (3, [{"event": "convert_to_draft"}]), (3, [{}] * 100)):
            with self.subTest(history=index):
                facts = self.provider_facts()
                facts[index] = value
                with self.assertRaises(authority.LifecycleAuthorityError):
                    self.observe(facts)

    def test_resolved_outdated_replies_remain_complete_safety_sources(self) -> None:
        reviewed = self.reviewed_state()
        reviewed.feedback["threads"].append({
            "node_id": "thread", "is_resolved": True, "is_outdated": True,
            "comments": [
                {"node_id": "finding", "body_digest": "a" * 64, "reactions": []},
                {"node_id": "reply", "body_digest": "b" * 64, "reactions": []},
            ],
        })
        reviewed.feedback["conversation_comments"].append({
            "node_id": "conversation", "body_digest": "c" * 64, "reactions": [],
        })
        self.assertEqual(len(fast_path._classified_feedback_sources(reviewed)), 1)
        sources = fast_path._classified_feedback_sources(reviewed, include_resolved=True)
        self.assertEqual(len(sources), 3)
        self.record["feedback_digest"] = reviewed.feedback_digest
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "source-complete"):
            self.observe(self.provider_facts(), reviewed=reviewed)
        self.record["technical_decisions"] = [{
            "source_id": f"{kind}:{identity}", "source_digest": facts[0],
            "disposition": "CORRECTED_AND_VERIFIED", "evidence_digest": "d" * 64,
        } for (kind, identity), facts in sources.items()]
        self.observe(self.provider_facts(), reviewed=reviewed)
        self.record["technical_decisions"][0]["disposition"] = "BLOCKING"
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "blocking"):
            self.observe(self.provider_facts(), reviewed=reviewed)

    def test_source_signer_requires_local_crypto_success_and_exact_principal(self) -> None:
        for returncode, output in (
            (1, f'Good "git" signature for {SIGNER} with ED25519 key SHA256:test'),
            (0, f'Good "git" signature for {OTHER_SIGNER} with ED25519 key SHA256:test'),
            (0, "unsigned"),
        ):
            with self.subTest(returncode=returncode, output=output), patch.object(
                self.loss.transport, "_allowed_signers", return_value=Path("/public/allowed-signers")
            ), patch.object(self.loss.transport, "_run_bootstrap_git", return_value=SimpleNamespace(
                returncode=returncode, stdout=output.encode(), stderr=b"",
            )):
                with self.assertRaisesRegex(authority.LifecycleAuthorityError, "signer"):
                    self.loss._source_signature(REPO_ROOT, self.record, self.trust)

    def test_candidate_local_or_unprotected_main_cannot_issue(self) -> None:
        for protected, head, dirty in ((False, "c" * 40, ""), (True, "a" * 40, ""),
                                       (True, "c" * 40, "modified policy")):
            with self.subTest(protected=protected, head=head, dirty=dirty):
                responses = [
                    {"commit": {"sha": "c" * 40}, "protected": protected},
                    {"sha": "c" * 40, "commit": {"verification": {"verified": True}}},
                ]
                with patch.object(self.loss, "_gh_json", side_effect=responses), patch.object(
                    self.loss.transport, "_git_text", side_effect=lambda root, args: head if args == ["rev-parse", "HEAD"] else dirty
                ):
                    with self.assertRaises(authority.LifecycleAuthorityError):
                        self.loss._accepted_policy(REPOSITORY, 827)

    def test_unenrolled_check_uses_protected_journal_and_never_treats_failure_as_absence(self) -> None:
        publication = self.loss.publication
        with patch.object(publication, "_verify_live_protection"), patch.object(
            publication, "_isolated_repository", return_value=nullcontext((REPO_ROOT, {}))
        ), patch.object(publication, "_observe_remote_current_once", return_value="c" * 40):
            for latest, admissions in (({}, {}), ({(REPOSITORY, 827): object()}, {}),
                                       ({}, {(REPOSITORY, 827): object()})):
                with self.subTest(latest=bool(latest), admissions=bool(admissions)), patch.object(
                    publication, "_walk_journal", return_value=([], latest, admissions)
                ):
                    if latest or admissions:
                        with self.assertRaises(publication.LifecyclePublicationError):
                            publication.require_unenrolled_delivery(REPOSITORY, 827)
                    else:
                        publication.require_unenrolled_delivery(REPOSITORY, 827)
        with patch.object(publication, "_verify_live_protection", side_effect=publication.LifecyclePublicationError("provider failed")):
            with self.assertRaisesRegex(publication.LifecyclePublicationError, "provider failed"):
                publication.require_unenrolled_delivery(REPOSITORY, 827)

    def test_loss_execution_static_boundary(self) -> None:
        parsed = ast.parse(inspect.getsource(self.loss))
        imports = {alias.name for node in ast.walk(parsed) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {"copy", "os", "re", "stat", "subprocess", "tempfile"})
        from_imports = {
            (node.level, node.module, tuple(alias.name for alias in node.names))
            for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom)
        }
        self.assertEqual(from_imports, {
            (0, "__future__", ("annotations",)), (0, "dataclasses", ("dataclass",)),
            (0, "datetime", ("datetime", "timezone")), (0, "pathlib", ("Path",)),
            (0, "typing", ("Any", "Mapping")),
            (1, None, ("bootstrap_source_admission",)), (1, None, ("fast_path",)),
            (1, None, ("lifecycle_authority",)), (1, None, ("lifecycle_execution",)),
            (1, None, ("lifecycle_publication",)),
        })
        process_owners = []
        for function in parsed.body:
            if not isinstance(function, ast.FunctionDef):
                continue
            for call in ast.walk(function):
                if not isinstance(call, ast.Call):
                    continue
                if isinstance(call.func, ast.Name):
                    self.assertNotIn(call.func.id, {"eval", "exec", "compile", "__import__", "getattr"})
                if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                    if call.func.value.id == "subprocess":
                        process_owners.append((function.name, call.func.attr))
        self.assertEqual(process_owners, [("_prepare_dependencies", "run")])

    def test_issuer_uses_existing_migration_role_only_after_acquisition(self) -> None:
        with patch.object(self.loss, "_acquire", return_value=self.acquired) as acquire, patch.object(
            self.loss.execution, "_local_signer", return_value=signer_for(self.migration)
        ) as signer:
            issued = self.loss.issue(REPOSITORY, 827)
            acquire.assert_called_once_with(REPOSITORY, 827, execute_validation=True)
            signer.assert_called_once_with(self.migration)
            self.assertEqual(issued["signer_identity"], self.migration)
            self.assertEqual(issued["bounded_uses"], 1)
            self.assertEqual(issued["current_safety"], self.acquired["current_safety"])
        with patch.object(self.loss, "_acquire", side_effect=authority.LifecycleAuthorityError("registered validation failed")), patch.object(
            self.loss.execution, "_local_signer"
        ) as signer:
            with self.assertRaisesRegex(authority.LifecycleAuthorityError, "validation failed"):
                self.loss.issue(REPOSITORY, 827)
            signer.assert_not_called()

    def test_generic_v3_enrollment_uses_existing_journal_once(self) -> None:
        publication = self.loss.publication
        signature_policy = {"accepted_formats": ["ssh"], "require_github_verified": True}
        commit = {
            "oid": self.record["head_sha"], "source": "USER", "signer_identity": SIGNER,
            "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
            "github_verification": {"verified": True, "reason": "valid"},
        }
        signature_digest = authority.digest_json(fast_path.verify_commit_signatures([commit], signature_policy)[0])
        admission = self.sign({
            **self.document, "delivery_issue": ISSUE, "pull_request": PR,
            "commit_signature_evidence_digest": signature_digest,
        })
        context = {
            "repository": REPOSITORY, "delivery_issue": ISSUE, "pull_request": PR,
            "head_sha": admission["head_sha"], "tree_sha": admission["tree_sha"],
            "pull_request_state": "OPEN", "commit_signature_evidence_digest": signature_digest,
            "validation_receipt_digest": admission["historical_validation_receipt_digest"],
            "source_validation_evidence_digest": authority.digest_json(admission["current_safety"]),
            "adoption_source_evidence_digest": admission["admission_digest"],
            "adoption_timestamp": admission["adoption_timestamp"],
        }
        budget = authority.create_pre_enrollment_review_budget_consumption_admission(
            **context, admission_id="generic-budget", observed_pre_enrollment_history=admission["observed_pre_enrollment_history"],
            intended_state=admission["intended_state"], signer_identity=self.migration, signer=signer_for(self.migration),
        )
        with tempfile.TemporaryDirectory() as directory:
            remote = Path(directory) / "publication.git"
            subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
            trust = replace(self.trust, publication_remote_url=str(remote), publication_signer_identities=frozenset({SIGNER}))
            with patch.object(authority, "_load_lifecycle_trust_policy", return_value=trust), patch.object(
                publication, "_verify_live_protection"
            ), patch.object(self.loss, "_reauthenticate", side_effect=lambda doc: publication.require_unenrolled_delivery(
                doc["repository"], doc["delivery_issue"]
            )), patch.object(authority, "_load_delivery_signature_policy", return_value=signature_policy):
                sealed = self.loss.verify(authority.canonical_json_bytes(admission))
                external = authority.authenticate_exact_state_adoption_external_evidence(
                    repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
                    head_sha=admission["head_sha"], tree_sha=admission["tree_sha"], pull_request_state="OPEN",
                    commit_signature_evidence=commit, validation_evidence=None, validation_evidence_loss_admission=sealed,
                    review_budget_consumption_admission=budget,
                    observed_pre_enrollment_history=admission["observed_pre_enrollment_history"], intended_state=admission["intended_state"],
                )
                evidence = authority.create_exact_state_adoption_evidence(
                    verified_external_evidence=external, adoption_timestamp=admission["adoption_timestamp"],
                )
                authorization = authority.create_exact_state_adoption_authorization(
                    adoption_evidence=evidence, authorization_id="generic-v3-adoption", bounded_uses=1,
                    signer_identity=self.migration, signer=signer_for(self.migration),
                )
                proof = authority.create_exact_state_adoption_proof(
                    adoption_evidence=evidence, authorization=authorization,
                    signer_identity=self.migration, signer=signer_for(self.migration),
                )
                bundle = authority.serialize_exact_state_adoption_evidence(exact_state_adoption_proof=proof)
                enrolled = publication.enroll_existing_lifecycle(bundle, signer_identity=SIGNER, signer=signer_for())
                current = publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
                self.assertEqual(enrolled.lifecycle.authority_digest, current.lifecycle.authority_digest)
                self.assertEqual(current.lifecycle.state, self.loss._intended_state())
                with self.assertRaisesRegex(publication.LifecyclePublicationError, "enrolled"):
                    publication.enroll_existing_lifecycle(bundle, signer_identity=SIGNER, signer=signer_for())


if __name__ == "__main__":
    main(verbosity=2)
