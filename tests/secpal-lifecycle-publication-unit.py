#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for protected lifecycle publication and legacy adoption."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import importlib.util
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
from unittest.mock import patch

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_publication as publication
from scripts.secpal_pr_review import fast_path


def load_actions() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts/secpal-pr-review-actions.py"
    spec = importlib.util.spec_from_file_location("secpal_actions_for_publication", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load action helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

REPOSITORY = "SecPal/.github"
ISSUE = 752
PR = 753
SIGNER = "aroviqen@secpal.app"
LEGACY_SIGNER = "lifecycle-legacy-adoption@secpal.app"
OTHER_SIGNER = "other@secpal.app"
HEADS = [character * 40 for character in "abcdef1234567890"]
SECRET = b"lifecycle-publication-hermetic-signature"
BRANCH = "refs/heads/secpal-lifecycle-publications"
RULESET_ID = 21769814
ISSUE_736 = 736
PR_760 = 760
INITIAL_HEAD_736 = "9cce12e839e5f998137cc58fea90d0a5a0a45f63"
CURRENT_HEAD_736 = "40e218ade8b4f6c9121cebbfe286dfc077d185e3"
INITIALIZATION_DIGEST_736 = (
    "6477407a86182f6bc9964089382f288e13dbb2e0b096edb2bf4e1c228452e628"
)
RECEIPT_DIGEST_736 = (
    "ae9cf6c0480aae0effa72bc8128e569db82f84b86351642c14c37ecabdccecc4"
)
ATTESTATION_DIGEST_736 = (
    "dad96cfa78d2a2c4d09818b761ec88d9385569e24a8e5117bab16be2351cbd25"
)
REAL_SIGNING_KEY = (
    "ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIDDKiPWdlHKFaHJL+GQ3EQRs9St95lITw217D17rZ2qB"
)
INITIALIZATION_SIGNATURE_736 = """-----BEGIN SSH SIGNATURE-----
U1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAgMMqI9Z2UcoVockv4ZDcRBGz1K3
3mUhPDbXsPXutnaoEAAAArc2VjcGFsLmRlbGl2ZXJ5LWxpZmVjeWNsZS1pbml0aWFsaXph
dGlvbi92MQAAAAAAAAAGc2hhNTEyAAAAUwAAAAtzc2gtZWQyNTUxOQAAAEBPW9HoSyuSvG
OJlECFurceXxvpEtXnEVHKkVJAmmUG94F0LXvzaYo8F3VI149HLSctY33Cs8W9vZn1jZ+2
IhwP
-----END SSH SIGNATURE-----
"""


def signer_for(identity: str = SIGNER) -> authority.Signer:
    def sign(payload: bytes, domain: str) -> dict[str, str]:
        value = hashlib.sha256(SECRET + identity.encode() + domain.encode() + payload).hexdigest()
        return {"format": "ssh", "signer_identity": identity, "value": value}
    return sign


def verify_signature(payload: bytes, signature: dict[str, Any], expected_signer: str,
                     domain: str) -> authority.VerifiedSignature:
    if signature["value"].startswith("-----BEGIN SSH SIGNATURE-----"):
        if expected_signer != SIGNER or signature["signer_identity"] != SIGNER:
            raise ValueError("real SSH test signature belongs to a different signer")
        authority._verify_ssh_signature(
            payload,
            signature["value"],
            authority.TrustedSigner(SIGNER, (REAL_SIGNING_KEY,), ()),
            domain,
        )
        return authority.VerifiedSignature(expected_signer, signature["format"])
    expected = signer_for(expected_signer)(payload, domain)["value"]
    if signature["value"] != expected or signature["signer_identity"] != expected_signer:
        raise ValueError("invalid test signature")
    return authority.VerifiedSignature(expected_signer, signature["format"])


class Chain:
    def __init__(self, issue: int = ISSUE) -> None:
        self.issue = issue
        self.initialization = authority.create_delivery_initialization(
            repository=REPOSITORY, delivery_issue=issue, pull_request=PR,
            initial_head_sha=HEADS[0], validation_receipt_digest="1" * 64,
            final_attestation_digest="2" * 64, signer_identity=SIGNER,
            signer=signer_for(),
        )
        self.lifecycle_id = authority.delivery_initialization_lifecycle_id(
            self.initialization["initialization_digest"]
        )
        self.authorities: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.pull_request = PR
        self.head = HEADS[0]
        self.checkpoint: dict[str, Any] | None = None

    def append(self, transition: str, *, head: str | None = None,
               replacement_pull_request: int | None = None) -> None:
        resulting_head = head or self.head
        event = authority.create_transition_authorization(
            event_id=(f"genesis:{self.initialization['initialization_digest']}"
                      if not self.events else f"event-{len(self.events) + 1}"),
            repository=REPOSITORY, delivery_issue=self.issue,
            lifecycle_id=self.lifecycle_id, pull_request=self.pull_request,
            predecessor_authority_digest=(None if not self.authorities
                                          else self.authorities[-1]["authority_digest"]),
            predecessor_head_sha=None if not self.authorities else self.head,
            resulting_head_sha=resulting_head, transition_kind=transition,
            replacement_pull_request=replacement_pull_request,
            initialization_evidence_digest=self.initialization["initialization_digest"],
            signer_identity=SIGNER, signer=signer_for(),
        )
        snapshot = authority.issue_lifecycle_authority(
            predecessor_chain=self.authorities, transition_authorizations=self.events,
            authorization=event, signer_identity=SIGNER,
            authority_signer=signer_for(),
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=verify_signature,
        )
        self.events.append(event)
        self.authorities.append(snapshot)
        self.head = resulting_head
        if replacement_pull_request is not None:
            self.pull_request = replacement_pull_request

    def raw(self) -> bytes:
        return authority.serialize_lifecycle_evidence(
            delivery_initialization=self.initialization,
            transition_authorizations=self.events,
            authority_chain=self.authorities,
        )

    def create_checkpoint(self, *, signer_identity: str = LEGACY_SIGNER,
                          signer: authority.Signer | None = None) -> dict[str, Any]:
        self.checkpoint = authority.create_legacy_adoption_checkpoint(
            self.raw(), migration_reason="Predates installed lifecycle authority",
            authorization_identity="user-authorization:legacy-adoption-1",
            checkpoint_event_id="legacy-adoption-1",
            checkpoint_timestamp="2026-08-28T00:00:00Z",
            supporting_evidence_digests=["3" * 64, "4" * 64],
            pr_replacement_history_summary=[], signer_identity=signer_identity,
            signer=signer or signer_for(signer_identity),
        )
        return self.checkpoint

    def published(self) -> bytes:
        if self.checkpoint is None:
            self.create_checkpoint()
        return authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=self.raw(), legacy_adoption_checkpoint=self.checkpoint
        )


def issue_736_chain() -> Chain:
    chain = Chain(ISSUE_736)
    chain.initialization = {
        "schema_version": "1.0",
        "kind": authority.INITIALIZATION_KIND,
        "domain": authority.INITIALIZATION_DOMAIN,
        "repository": REPOSITORY,
        "delivery_issue": ISSUE_736,
        "pull_request": PR_760,
        "initial_head_sha": INITIAL_HEAD_736,
        "validation_receipt_digest": RECEIPT_DIGEST_736,
        "final_attestation_digest": ATTESTATION_DIGEST_736,
        "signer_identity": SIGNER,
        "signature": {
            "format": "ssh",
            "signer_identity": SIGNER,
            "value": INITIALIZATION_SIGNATURE_736,
        },
        "initialization_digest": INITIALIZATION_DIGEST_736,
    }
    chain.lifecycle_id = authority.delivery_initialization_lifecycle_id(
        INITIALIZATION_DIGEST_736
    )
    chain.pull_request = PR_760
    chain.head = INITIAL_HEAD_736
    chain.append("INITIALIZED_DRAFT")
    chain.append("UNRESTRICTED_REVIEW_CONSUMED")
    chain.append("REMEDIATION_COMPLETED", head="1" * 40)
    chain.append("DRAFT_TO_READY")
    chain.append("REMEDIATION_COMPLETED", head=CURRENT_HEAD_736)
    return chain


def recovered_ready_chain(issue: int = ISSUE) -> Chain:
    chain = Chain(issue)
    chain.append("INITIALIZED_DRAFT")
    chain.append("UNRESTRICTED_REVIEW_CONSUMED")
    chain.append("REMEDIATION_COMPLETED", head=HEADS[1])
    chain.append("REMEDIATION_COMPLETED", head=HEADS[2])
    chain.append("DRAFT_TO_READY")
    chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[3])
    return chain


def exact_adoption_evidence(
    *, admit_review_budget: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if admit_review_budget:
        history = [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT",
             "observed_at": "2026-08-01T00:00:00Z", "head_sha": HEADS[0],
             "reviewed_head_sha": None},
            {"sequence": 2, "kind": "REMEDIATION_HEAD_OBSERVED",
             "observed_at": "2026-08-04T00:00:00Z", "head_sha": HEADS[2],
             "reviewed_head_sha": None},
        ]
    else:
        history = [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT",
             "observed_at": "2026-08-01T00:00:00Z", "head_sha": HEADS[0],
             "reviewed_head_sha": None},
            {"sequence": 2, "kind": "DRAFT_TO_READY_OBSERVED",
             "observed_at": "2026-08-02T00:00:00Z", "head_sha": HEADS[0],
             "reviewed_head_sha": None},
            {"sequence": 3, "kind": "REVIEW_SUBMITTED",
             "observed_at": "2026-08-03T00:00:00Z", "head_sha": HEADS[0],
             "reviewed_head_sha": HEADS[0]},
            {"sequence": 4, "kind": "REMEDIATION_HEAD_OBSERVED",
             "observed_at": "2026-08-04T00:00:00Z", "head_sha": HEADS[1],
             "reviewed_head_sha": None},
            {"sequence": 5, "kind": "REMEDIATION_HEAD_OBSERVED",
             "observed_at": "2026-08-05T00:00:00Z", "head_sha": HEADS[2],
             "reviewed_head_sha": None},
        ]
    state = authority.initial_state()
    state.update(
        unrestricted_review_count=1,
        remediation_cycle_count=1 if admit_review_budget else 2,
        draft=True if admit_review_budget else False,
        ready=False if admit_review_budget else True,
        ready_transition_count=0 if admit_review_budget else 1,
        ready_history=[] if admit_review_budget else [{
            "sequence": 1, "transition_kind": "DRAFT_TO_READY",
            "observation_digest": authority.digest_json(history[1]),
        }],
    )
    validation = verified_validation_evidence(
        head=HEADS[2], tree=HEADS[3], parent=HEADS[1]
    )
    commit = {
        "oid": HEADS[2], "source": "USER", "signer_identity": SIGNER,
        "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
        "github_verification": {"verified": True, "reason": "valid"},
    }
    review_budget_admission = None
    if admit_review_budget:
        verified_commit = fast_path.verify_commit_signatures(
            [commit],
            {"accepted_formats": ["ssh"], "require_github_verified": True},
        )[0]
        review_budget_admission = (
            authority.create_pre_enrollment_review_budget_consumption_admission(
                admission_id="publication-review-budget-admission",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
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
                observed_pre_enrollment_history=history,
                intended_state=state,
                adoption_timestamp="2026-08-06T00:00:00Z",
                signer_identity=LEGACY_SIGNER,
                signer=signer_for(LEGACY_SIGNER),
            )
        )
    with patch.object(
        authority, "_load_delivery_signature_policy",
        return_value={"accepted_formats": ["ssh"], "require_github_verified": True},
    ):
        arguments = dict(
            repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
            head_sha=HEADS[2], tree_sha=HEADS[3], pull_request_state="OPEN",
            commit_signature_evidence=commit, validation_evidence=validation,
            observed_pre_enrollment_history=history, intended_state=state,
        )
        if review_budget_admission is not None:
            arguments["review_budget_consumption_admission"] = (
                review_budget_admission
            )
        external = authority.authenticate_exact_state_adoption_external_evidence(
            **arguments
        )
    evidence = authority.create_exact_state_adoption_evidence(
        verified_external_evidence=external,
        adoption_timestamp="2026-08-06T00:00:00Z",
    )
    authorization = authority.create_exact_state_adoption_authorization(
        adoption_evidence=evidence, authorization_id="exact-adoption-auth-1",
        bounded_uses=1, signer_identity=LEGACY_SIGNER,
        signer=signer_for(LEGACY_SIGNER),
    )
    proof = authority.create_exact_state_adoption_proof(
        adoption_evidence=evidence, authorization=authorization,
        signer_identity=LEGACY_SIGNER, signer=signer_for(LEGACY_SIGNER),
    )
    return authority.serialize_exact_state_adoption_evidence(
        exact_state_adoption_proof=proof
    ), proof


def verified_validation_evidence(
    *,
    head: str,
    tree: str,
    parent: str,
    pull_request: int = PR,
    ready_integration: bool = False,
    delivery_issue: int = ISSUE,
) -> fast_path.VerifiedValidationEvidence:
    reviewed = fast_path.StableFeedbackState(
        repository=REPOSITORY, pull_request_number=pull_request, head_sha=parent,
        base_ref="main", base_sha=HEADS[0], pr_state="OPEN",
        feedback={"pull_request_reactions": [], "reviews": [],
                  "conversation_comments": [], "threads": []},
    )
    registry = {
        "default_branch": "main",
        "manual_gates": [],
        "validation": [],
    }
    integration = None
    eligibility_digest = None
    if ready_integration:
        eligibility_digest = "e" * 64
        integration = {
            "schema_version": "1.1",
            "kind": "TWO_PARENT_READY_INTEGRATION",
            "authorization_id": "ready-integration-authorization-001",
            "repository": REPOSITORY,
            "delivery_issue_number": delivery_issue,
            "pull_request_number": pull_request,
            "prior_delivery_head_sha": parent,
            "prior_authority_digest": "6" * 64,
            "prior_authority_tag_object_sha": "7" * 40,
            "target_base": {
                "ref": "main",
                "authorized_sha": HEADS[0],
                "observed_sha": HEADS[0],
            },
            "ordered_parent_shas": [parent, HEADS[0]],
            "validated_tree_sha": tree,
            "mechanical_merge_tree_sha": tree,
            "mechanical_conflict_paths": [],
            "manual_conflict_resolution_delta": [],
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "validation_execution": {
                "registry_digest": fast_path.digest_json(registry),
                "command_set_digest": fast_path.digest_json(registry["validation"]),
            },
            "expected_signer": {
                "kind": "SSH_PRINCIPAL",
                "identity": SIGNER,
            },
            "eligibility": {
                "eligible": True,
                "lifecycle_identity": "lifecycle-1",
                "draft_before": False,
                "draft_after": False,
                "ready_before": True,
                "ready_after": True,
                "ready_transition": False,
                "review_requested": False,
                "unrestricted_reviews_before": 1,
                "unrestricted_reviews_after": 1,
                "remediation_cycles_before": 2,
                "remediation_cycles_after": 2,
                "exceptional_recoveries_before": 0,
                "exceptional_recoveries_after": 0,
                "exceptional_continuations_before": 0,
                "exceptional_continuations_after": 0,
                "cycle_3": False,
            },
        }
    receipt = fast_path.create_validation_receipt(
        repository=REPOSITORY, head_sha=parent, validated_tree_sha=tree,
        registry=registry, command_set=[], successful_result=True,
        reviewed_state=reviewed, manual_gate_evidence=[],
        eligibility_evidence_digest=eligibility_digest,
        integration_evidence_digest=(
            fast_path.digest_json(integration) if integration is not None else None
        ),
    )
    if integration is not None:
        attestation = fast_path.create_ready_integration_attestation(
            repository=REPOSITORY,
            head_sha=head,
            registry=registry,
            command_set=[],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
        )
        git_results = [
            subprocess.CompletedProcess(
                [], 0, "gpgsig -----BEGIN SSH SIGNATURE-----\n\n", ""
            ),
            subprocess.CompletedProcess(
                [],
                0,
                f'Good "git" signature for {SIGNER} with ED25519 key '
                "SHA256:test\n",
                "",
            ),
        ]
        with patch.object(
            fast_path, "_run_integration_commit_git", side_effect=git_results
        ):
            authenticated_commit = fast_path.authenticate_integration_commit(
                repository_root=Path(__file__).resolve().parents[1],
                head_sha=head,
                expected_signer=integration["expected_signer"],
                signature_policy={"accepted_formats": ["ssh", "openpgp"]},
            )
        return fast_path.verify_eligibility_bound_ready_integration_attestation(
            attestation,
            repository=REPOSITORY,
            head_sha=head,
            registry=registry,
            command_set=[],
            reviewed_state=reviewed,
            validation_receipt=receipt,
            integration_evidence=integration,
            commit_parent_shas=integration["ordered_parent_shas"],
            commit_tree_sha=tree,
            commit_validation_receipt_digest=receipt["receipt_digest"],
            commit_integration_evidence_digest=fast_path.digest_json(integration),
            authenticated_integration_commit=authenticated_commit,
        )
    attestation = fast_path.create_validation_attestation(
        repository=REPOSITORY, head_sha=head, registry=registry,
        command_set=[], successful_result=True, reviewed_state=reviewed,
        validation_receipt=receipt,
    )
    return fast_path.verify_validation_attestation(
        attestation, repository=REPOSITORY, head_sha=head, registry=registry,
        command_set=[], reviewed_state=reviewed, commit_parent_sha=parent,
        commit_tree_sha=tree,
        commit_validation_receipt_digest=receipt["receipt_digest"],
    )


class LifecyclePublicationTests(TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="lifecycle-publication-")
        base = Path(self.directory.name)
        self.remote = base / "publication.git"
        self.probe = base / "probe"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(["git", "--git-dir", str(self.remote), "config",
                        "receive.denyNonFastForwards", "true"], check=True)
        subprocess.run(["git", "--git-dir", str(self.remote), "config",
                        "receive.denyDeletes", "true"], check=True)
        subprocess.run(["git", "init", "--bare", "-q", str(self.probe)], check=True)
        trusted = authority.TrustedSigner(SIGNER, ("ssh-ed25519 AAAA",), ())
        legacy_trusted = authority.TrustedSigner(
            LEGACY_SIGNER, ("ssh-ed25519 AAAA",), ()
        )
        self.policy = authority.LifecycleTrustPolicy(
            repository=REPOSITORY, accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
            signers={SIGNER: trusted, LEGACY_SIGNER: legacy_trusted},
            initialization_anchors=(), publication_signer_identities=frozenset({SIGNER}),
            genesis_admission_signer_identities=frozenset({SIGNER}),
            legacy_adoption_signer_identities=frozenset({LEGACY_SIGNER}),
            publication_branch=BRANCH, publication_remote_url=str(self.remote),
            publication_ruleset_id=RULESET_ID,
            publication_required_rules=frozenset({"deletion", "non_fast_forward"}),
        )
        self.policy_patch = patch.object(authority, "_load_lifecycle_trust_policy",
                                         return_value=self.policy)
        self.verifier_patch = patch.object(authority, "_policy_signature_verifier",
                                           return_value=verify_signature)
        self.protection_patch = patch.object(publication, "_verify_live_protection",
                                             return_value=RULESET_ID)
        self.policy_patch.start()
        self.verifier_patch.start()
        self.protection_patch.start()

    def tearDown(self) -> None:
        self.protection_patch.stop()
        self.verifier_patch.stop()
        self.policy_patch.stop()
        self.directory.cleanup()

    def enroll(self, chain: Chain | None = None) -> tuple[Chain, publication.VerifiedLifecyclePublication]:
        selected = chain or recovered_ready_chain()
        result = publication.enroll_existing_lifecycle(
            selected.published(), signer_identity=SIGNER, signer=signer_for()
        )
        return selected, result

    def remote_tip(self) -> str:
        value = subprocess.run(
            ["git", "--git-dir", str(self.remote), "rev-parse", BRANCH],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        return value

    def test_real_ssh_verifier_proves_the_requested_signer(self) -> None:
        initialization = issue_736_chain().initialization
        payload = authority.canonical_json_bytes(
            authority._unsigned(
                initialization, "initialization_digest", "signature"
            )
        )

        verified = verify_signature(
            payload,
            initialization["signature"],
            SIGNER,
            authority.INITIALIZATION_DOMAIN,
        )
        self.assertEqual(verified.signer_identity, SIGNER)
        substituted_signature = copy.deepcopy(initialization["signature"])
        substituted_signature["signer_identity"] = OTHER_SIGNER
        with self.assertRaises(ValueError):
            verify_signature(
                payload,
                substituted_signature,
                OTHER_SIGNER,
                authority.INITIALIZATION_DOMAIN,
            )

    def test_public_consumer_cannot_inject_trust_or_select_terminal(self) -> None:
        parameters = inspect.signature(publication.verify_current_lifecycle_authority).parameters
        self.assertEqual(list(parameters), ["repository", "delivery_issue", "expected"])
        for forbidden in ("signer", "remote", "publication_branch", "terminal_authority_digest"):
            self.assertNotIn(forbidden, parameters)
        writer = inspect.signature(publication.enroll_existing_lifecycle).parameters
        self.assertNotIn("repository_root", writer)
        self.assertNotIn("remote", writer)
        enrollment = inspect.signature(
            authority.verify_lifecycle_authority_for_publication
        ).parameters
        self.assertEqual(list(enrollment), ["serialized_evidence", "expected"])
        for forbidden in ("require_current_tip", "skip_current_selector", "journal_context"):
            self.assertNotIn(forbidden, enrollment)

    def test_native_mode_rejects_unanchored_fake_receipt_and_attestation(self) -> None:
        chain = recovered_ready_chain()
        native = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "maintained trust anchor"):
            authority.verify_lifecycle_authority_for_publication(native)
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_lifecycle_authority_for_publication(chain.raw())
        with self.assertRaises(
            (authority.LifecycleAuthorityError, publication.LifecyclePublicationError)
        ):
            publication.enroll_existing_lifecycle(
                native, signer_identity=SIGNER, signer=signer_for()
            )

    def test_valid_legacy_checkpoint_imports_exact_finite_baseline_once(self) -> None:
        chain, enrolled = self.enroll()
        state = enrolled.lifecycle.state
        self.assertEqual(enrolled.lifecycle.historical_proof_mode,
                         authority.LEGACY_PROOF_MODE)
        self.assertEqual(enrolled.lifecycle.lifecycle_id, chain.lifecycle_id)
        self.assertEqual(state["unrestricted_review_count"], 1)
        self.assertEqual(state["remediation_cycle_count"], 2)
        self.assertIs(state["cycle_3_absent"], True)
        self.assertIs(state["ready"], True)
        self.assertEqual(state["ready_transition_count"], 1)
        self.assertEqual(state["exceptional_recovery_count"], 1)
        self.assertEqual(state["exceptional_continuation_count"], 0)
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "already enrolled"):
            publication.enroll_existing_lifecycle(
                chain.published(), signer_identity=SIGNER, signer=signer_for()
            )

    def test_exact_adoption_enrolls_once_and_uses_normal_successor_path(self) -> None:
        self.assertIn(
            "current_head_evidence",
            inspect.signature(
                authority.issue_exact_state_adoption_successor_authority
            ).parameters,
        )
        serialized, proof = exact_adoption_evidence()
        self.assertEqual(proof["schema_version"], authority.SCHEMA_VERSION)
        self.assertEqual(proof["domain"], authority.EXACT_ADOPTION_PROOF_DOMAIN)
        self.assertNotIn("review_budget_consumption_admission", proof)
        enrolled = publication.enroll_existing_lifecycle(
            serialized, signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(
            enrolled.lifecycle.historical_proof_mode,
            authority.EXACT_ADOPTION_PROOF_MODE,
        )
        self.assertEqual(enrolled.lifecycle.authority_digest, proof["proof_digest"])
        self.assertEqual(enrolled.lifecycle.state["remediation_cycle_count"], 2)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "already enrolled"
        ):
            publication.enroll_existing_lifecycle(
                serialized, signer_identity=SIGNER, signer=signer_for()
            )

        event = authority.create_transition_authorization(
            event_id="adopted-head-advanced-1", repository=REPOSITORY,
            delivery_issue=ISSUE, lifecycle_id=enrolled.lifecycle.lifecycle_id,
            pull_request=PR,
            predecessor_authority_digest=enrolled.lifecycle.authority_digest,
            predecessor_head_sha=HEADS[2], resulting_head_sha=HEADS[4],
            transition_kind="HEAD_ADVANCED", replacement_pull_request=None,
            initialization_evidence_digest=(
                enrolled.lifecycle.initialization_evidence_digest
            ),
            signer_identity=SIGNER, signer=signer_for(),
        )
        current_validation = verified_validation_evidence(
            head=HEADS[4], tree=HEADS[5], parent=HEADS[2],
            ready_integration=True,
        )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "verified current evidence"
        ):
            authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=serialized, authorization=event,
                signer_identity=SIGNER, authority_signer=signer_for(),
                current_head_evidence=replace(
                    current_validation, _verification_seal=object()
                ),
            )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "verified current evidence"
        ):
            authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=serialized, authorization=event,
                signer_identity=SIGNER, authority_signer=signer_for(),
                current_head_evidence=verified_validation_evidence(
                    head=HEADS[4], tree=HEADS[5], parent=HEADS[2],
                    ready_integration=True, delivery_issue=ISSUE + 1,
                ),
            )
        snapshot = authority.issue_exact_state_adoption_successor_authority(
            serialized_adoption_evidence=serialized, authorization=event,
            signer_identity=SIGNER, authority_signer=signer_for(),
            current_head_evidence=current_validation,
        )
        successor = authority.serialize_exact_state_adoption_evidence(
            exact_state_adoption_proof=proof,
            transition_authorizations=[event], authority_chain=[snapshot],
        )
        advanced = publication.advance_current_terminal(
            successor, signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(advanced.lifecycle.head_sha, HEADS[4])
        self.assertEqual(advanced.lifecycle.tree_sha, HEADS[5])
        self.assertNotEqual(
            advanced.lifecycle.validation_receipt_digest,
            enrolled.lifecycle.validation_receipt_digest,
        )
        self.assertNotEqual(
            advanced.lifecycle.source_validation_evidence_digest,
            enrolled.lifecycle.source_validation_evidence_digest,
        )
        self.assertNotEqual(
            advanced.lifecycle.adoption_source_evidence_digest,
            enrolled.lifecycle.adoption_source_evidence_digest,
        )
        self.assertEqual(advanced.lifecycle.state, enrolled.lifecycle.state)
        self.assertEqual(
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
            .lifecycle.authority_digest,
            snapshot["authority_digest"],
        )
        manifest = {
            "repository": REPOSITORY,
            "delivery_issue_number": ISSUE,
            "pull_request_number": PR,
            "prior_delivery_head_sha": advanced.lifecycle.head_sha,
            "prior_delivery_tree_sha": advanced.lifecycle.tree_sha,
            "prior_validation_receipt_digest": (
                advanced.lifecycle.validation_receipt_digest
            ),
            "prior_final_attestation_digest": (
                advanced.lifecycle.adoption_source_evidence_digest
            ),
            "lifecycle": {
                "identity": advanced.lifecycle.lifecycle_id,
                "current_authority_digest": advanced.lifecycle.authority_digest,
                "historical_proof_mode": authority.EXACT_ADOPTION_PROOF_MODE,
                "unrestricted_reviews": 1,
                "remediation_cycles": 2,
                "exceptional_recoveries": 0,
                "exceptional_continuations": 0,
            },
            "publication": {
                "object_oid": advanced.publication_oid,
                "publication_digest": advanced.publication_digest,
            },
        }
        integration = {"eligibility": {"lifecycle_identity": advanced.lifecycle.lifecycle_id}}
        self.assertEqual(
            advanced.lifecycle.tree_sha, manifest["prior_delivery_tree_sha"]
        )
        self.assertEqual(
            advanced.lifecycle.validation_receipt_digest,
            manifest["prior_validation_receipt_digest"],
        )
        self.assertEqual(
            advanced.lifecycle.adoption_source_evidence_digest,
            manifest["prior_final_attestation_digest"],
        )
        self.assertFalse(
            advanced.lifecycle.tree_sha != manifest["prior_delivery_tree_sha"]
            or advanced.lifecycle.validation_receipt_digest
            != manifest["prior_validation_receipt_digest"]
            or advanced.lifecycle.adoption_source_evidence_digest
            != manifest["prior_final_attestation_digest"]
            or advanced.lifecycle.source_validation_evidence_digest
            != advanced.lifecycle.source_validation_evidence_digest
        )
        actions = load_actions()
        with patch.object(
            actions,
            "_load_lifecycle_publication_helpers",
            return_value=(authority, SimpleNamespace(
                verify_current_lifecycle_authority=lambda *_: advanced,
                LifecyclePublicationError=publication.LifecyclePublicationError,
            )),
        ):
            actions._verify_ready_integration_published_authority(
                manifest,
                integration,
                verified_source_validation_evidence_digest=(
                    advanced.lifecycle.source_validation_evidence_digest
                ),
            )
            stale = copy.deepcopy(manifest)
            stale["prior_delivery_tree_sha"] = enrolled.lifecycle.tree_sha
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                actions._verify_ready_integration_published_authority(
                    stale,
                    integration,
                    verified_source_validation_evidence_digest=(
                        advanced.lifecycle.source_validation_evidence_digest
                    ),
                )
            for field, stale_value in (
                ("prior_validation_receipt_digest", enrolled.lifecycle.validation_receipt_digest),
                ("prior_final_attestation_digest", enrolled.lifecycle.adoption_source_evidence_digest),
            ):
                changed = copy.deepcopy(manifest)
                changed[field] = stale_value
                with self.subTest(stale_field=field), self.assertRaises(
                    actions.fast_path.SecurityBlocker
                ):
                    actions._verify_ready_integration_published_authority(
                        changed,
                        integration,
                        verified_source_validation_evidence_digest=(
                            advanced.lifecycle.source_validation_evidence_digest
                        ),
                    )
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                actions._verify_ready_integration_published_authority(
                    manifest,
                    integration,
                    verified_source_validation_evidence_digest=(
                        enrolled.lifecycle.source_validation_evidence_digest
                    ),
                )

    def test_review_budget_admission_enrolls_exact_finite_state_once(self) -> None:
        serialized, proof = exact_adoption_evidence(admit_review_budget=True)
        enrolled = publication.enroll_existing_lifecycle(
            serialized, signer_identity=SIGNER, signer=signer_for()
        )

        self.assertEqual(proof["schema_version"], "2.0")
        self.assertEqual(
            enrolled.lifecycle.historical_proof_mode,
            authority.EXACT_ADOPTION_PROOF_MODE,
        )
        self.assertEqual(enrolled.lifecycle.state["unrestricted_review_count"], 1)
        self.assertEqual(enrolled.lifecycle.state["remediation_cycle_count"], 1)
        self.assertIs(enrolled.lifecycle.state["draft"], True)
        self.assertIs(enrolled.lifecycle.state["ready"], False)
        self.assertEqual(enrolled.lifecycle.state["ready_transition_count"], 0)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "already enrolled"
        ):
            publication.enroll_existing_lifecycle(
                serialized, signer_identity=SIGNER, signer=signer_for()
            )

    def test_exact_adoption_pr_rebound_requires_replacement_pr_evidence(self) -> None:
        serialized, proof = exact_adoption_evidence()
        event = authority.create_transition_authorization(
            event_id="adopted-pr-rebound-1",
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle_id=proof["lifecycle_id"],
            pull_request=PR,
            predecessor_authority_digest=proof["proof_digest"],
            predecessor_head_sha=HEADS[2],
            resulting_head_sha=HEADS[2],
            transition_kind="PR_REBOUND",
            replacement_pull_request=PR + 1,
            initialization_evidence_digest=proof["adoption_evidence_digest"],
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "delivery-identity-changing adopted successor requires verified current evidence",
        ):
            authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=serialized,
                authorization=event,
                signer_identity=SIGNER,
                authority_signer=signer_for(),
            )
        old_pr_evidence = verified_validation_evidence(
            head=HEADS[2], tree=HEADS[3], parent=HEADS[1]
        )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "verified current evidence",
        ):
            authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=serialized,
                authorization=event,
                signer_identity=SIGNER,
                authority_signer=signer_for(),
                current_head_evidence=old_pr_evidence,
            )

        current = verified_validation_evidence(
            head=HEADS[2],
            tree=HEADS[3],
            parent=HEADS[1],
            pull_request=PR + 1,
        )
        snapshot = authority.issue_exact_state_adoption_successor_authority(
            serialized_adoption_evidence=serialized,
            authorization=event,
            signer_identity=SIGNER,
            authority_signer=signer_for(),
            current_head_evidence=current,
        )
        self.assertEqual(snapshot["pull_request"], PR + 1)
        self.assertEqual(
            snapshot["current_head_evidence"]["source_validation_evidence_digest"],
            current.source_validation_evidence_digest,
        )

    def test_legacy_checkpoint_requires_dedicated_role_and_valid_authorization(self) -> None:
        chain = recovered_ready_chain()
        chain.create_checkpoint(signer_identity=OTHER_SIGNER)
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_lifecycle_authority_for_publication(chain.published())
        chain = recovered_ready_chain()
        chain.create_checkpoint(signer_identity=SIGNER)
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_lifecycle_authority_for_publication(chain.published())
        chain = recovered_ready_chain()
        checkpoint = chain.create_checkpoint()
        checkpoint["authorization_identity"] = ""
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_lifecycle_authority_for_publication(
                authority.serialize_publication_lifecycle_evidence(
                    lifecycle_evidence=chain.raw(), legacy_adoption_checkpoint=checkpoint
                )
            )

    def test_invalid_legacy_checkpoint_limits_and_identity_fail_closed(self) -> None:
        chain = recovered_ready_chain()
        checkpoint = chain.create_checkpoint()
        variants = (
            ("repository", "Other/repo"),
            ("delivery_issue", ISSUE + 1),
            ("current_pull_request", PR + 1),
            ("current_head_sha", HEADS[8]),
        )
        for field, value in variants:
            with self.subTest(field=field):
                changed = copy.deepcopy(checkpoint)
                changed[field] = value
                with self.assertRaises(authority.LifecycleAuthorityError):
                    authority.verify_lifecycle_authority_for_publication(
                        authority.serialize_publication_lifecycle_evidence(
                            lifecycle_evidence=chain.raw(), legacy_adoption_checkpoint=changed
                        )
                    )
        for field, value in (("cycle_3_absent", False),
                             ("remediation_cycle_count", 3),
                             ("unrestricted_review_count", 2)):
            changed = copy.deepcopy(checkpoint)
            changed["state"][field] = value
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.verify_lifecycle_authority_for_publication(
                    authority.serialize_publication_lifecycle_evidence(
                        lifecycle_evidence=chain.raw(), legacy_adoption_checkpoint=changed
                    )
                )
        anchored = replace(
            self.policy,
            initialization_anchors=(
                authority.InitializationAnchor(
                    ISSUE, PR, HEADS[0], chain.initialization["initialization_digest"],
                    PR, HEADS[3], chain.authorities[-1]["authority_digest"],
                ),
            ),
        )
        with patch.object(authority, "_load_lifecycle_trust_policy", return_value=anchored):
            with self.assertRaisesRegex(authority.LifecycleAuthorityError, "natively anchored"):
                authority.verify_lifecycle_authority_for_publication(chain.published())

    def test_exceptional_continuation_advances_after_checkpoint_and_stale_fails(self) -> None:
        chain, enrolled = self.enroll()
        checkpoint = copy.deepcopy(chain.checkpoint)
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        chain.checkpoint = checkpoint
        advanced = publication.advance_current_terminal(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertNotEqual(advanced.publication_oid, enrolled.publication_oid)
        self.assertEqual(advanced.lifecycle.state["exceptional_continuation_count"], 1)
        self.assertEqual(advanced.lifecycle.state["exceptional_recovery_count"], 1)
        self.assertEqual(advanced.lifecycle.legacy_adoption_checkpoint_digest,
                         enrolled.lifecycle.legacy_adoption_checkpoint_digest)
        with self.assertRaises(authority.LifecycleAuthorityError):
            publication.verify_current_lifecycle_authority(
                REPOSITORY, ISSUE,
                authority.ExpectedLifecycle(REPOSITORY, ISSUE, chain.lifecycle_id, PR, HEADS[3]),
            )
        replacement_checkpoint = authority.create_legacy_adoption_checkpoint(
            chain.raw(), migration_reason="Unauthorized second migration",
            authorization_identity="user-authorization:legacy-adoption-2",
            checkpoint_event_id="legacy-adoption-2",
            checkpoint_timestamp="2026-08-28T00:00:01Z",
            supporting_evidence_digests=["5" * 64],
            pr_replacement_history_summary=[], signer_identity=LEGACY_SIGNER,
            signer=signer_for(LEGACY_SIGNER),
        )
        second_migration = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw(),
            legacy_adoption_checkpoint=replacement_checkpoint,
        )
        with self.assertRaises(publication.LifecyclePublicationError):
            publication.advance_current_terminal(
                second_migration, signer_identity=SIGNER, signer=signer_for()
            )

    def test_initial_enrollment_cannot_skip_post_checkpoint_publications(self) -> None:
        chain = recovered_ready_chain()
        checkpoint = copy.deepcopy(chain.create_checkpoint())
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        chain.checkpoint = checkpoint
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "exact migration checkpoint terminal",
        ):
            publication.enroll_existing_lifecycle(
                chain.published(), signer_identity=SIGNER, signer=signer_for()
            )

    def test_public_verifier_rejects_every_post_checkpoint_transition_folded_into_enrollment(
        self,
    ) -> None:
        variants = (
            ("EXCEPTIONAL_CONTINUATION", {"head": HEADS[4]}),
            ("PR_REBOUND", {"replacement_pull_request": PR + 1}),
            ("READY_TO_DRAFT", {}),
        )
        for transition, arguments in variants:
            with self.subTest(transition=transition):
                chain = recovered_ready_chain()
                checkpoint = copy.deepcopy(chain.create_checkpoint())
                checkpoint_terminal = checkpoint["terminal_authority_digest"]
                chain.append(transition, **arguments)
                chain.checkpoint = checkpoint
                bundle, bundle_raw = publication._canonical_bundle(chain.published())
                successor = authority._verify_lifecycle_authority_for_journal(bundle_raw)
                self.assertNotEqual(successor.authority_digest, checkpoint_terminal)
                fields = publication._publication_fields(
                    operation="ENROLL_EXISTING_LIFECYCLE",
                    verified=successor,
                    bundle=bundle,
                    bundle_raw=bundle_raw,
                    publication_branch=BRANCH,
                    journal_predecessor_oid=None,
                    predecessor=None,
                    predecessor_oid=None,
                    signer_identity=SIGNER,
                )
                raw = publication._sign_publication(fields, signer_for())
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError,
                    "exact migration checkpoint terminal",
                ):
                    publication._verify_publication_document(
                        raw, object_oid=HEADS[9], expected_branch=BRANCH
                    )

    def test_native_journal_advances_without_weakening_static_current_tip_verification(
        self,
    ) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        anchor = authority.InitializationAnchor(
            ISSUE,
            PR,
            HEADS[0],
            chain.initialization["initialization_digest"],
            PR,
            chain.head,
            chain.authorities[-1]["authority_digest"],
        )
        policy = replace(self.policy, initialization_anchors=(anchor,))
        native_h = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )
        with patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy):
            publication.admit_native_genesis(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            enrolled = publication.enroll_existing_lifecycle(
                native_h, signer_identity=SIGNER, signer=signer_for()
            )
            chain.append("HEAD_ADVANCED", head=HEADS[1])
            native_h2 = authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=chain.raw()
            )
            h2 = publication.advance_current_terminal(
                native_h2, signer_identity=SIGNER, signer=signer_for()
            )
            chain.append("HEAD_ADVANCED", head=HEADS[2])
            native_h3 = authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=chain.raw()
            )
            h3 = publication.advance_current_terminal(
                native_h3, signer_identity=SIGNER, signer=signer_for()
            )
            current = publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
            self.assertEqual(current.publication_oid, h3.publication_oid)
            self.assertNotEqual(current.publication_oid, enrolled.publication_oid)
            self.assertNotEqual(current.publication_oid, h2.publication_oid)
            with self.assertRaises(authority.LifecycleAuthorityError):
                publication.verify_current_lifecycle_authority(
                    REPOSITORY,
                    ISSUE,
                    authority.ExpectedLifecycle(
                        REPOSITORY, ISSUE, chain.lifecycle_id, PR, HEADS[0]
                    ),
                )
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError,
                "maintained current terminal authority",
            ):
                authority.verify_lifecycle_authority(
                    authority.canonical_json_bytes(
                        json.loads(native_h2)["lifecycle_evidence"]
                    )
                )

    def test_native_enrollment_requires_prior_global_genesis_admission(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        native = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )

        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "native genesis is not independently admitted",
        ):
            publication.enroll_existing_lifecycle(
                native, signer_identity=SIGNER, signer=signer_for()
            )

        admission = publication.admit_native_genesis(
            chain.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(admission.delivery_issue, ISSUE)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "unavailable"
        ):
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)

        enrolled = publication.enroll_existing_lifecycle(
            native, signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(enrolled.journal_predecessor_oid, admission.admission_oid)
        self.assertEqual(
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
            .lifecycle.initialization_evidence_digest,
            chain.initialization["initialization_digest"],
        )

    def test_static_root_does_not_admit_a_new_enrollment_publication(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        anchor = authority.InitializationAnchor(
            ISSUE,
            PR,
            HEADS[0],
            chain.initialization["initialization_digest"],
            PR,
            chain.head,
            chain.authorities[-1]["authority_digest"],
        )
        historical_bundle, historical_raw = publication._canonical_bundle(
            authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=chain.raw()
            )
        )
        historical_lifecycle = authority.verify_native_lifecycle_for_genesis_admission(
            chain.raw()
        )
        historical_fields = publication._publication_fields(
            operation="ENROLL_EXISTING_LIFECYCLE",
            verified=historical_lifecycle,
            bundle=historical_bundle,
            bundle_raw=historical_raw,
            publication_branch=BRANCH,
            journal_predecessor_oid=None,
            predecessor=None,
            predecessor_oid=None,
            signer_identity=SIGNER,
        )
        historical_document = publication._sign_publication(
            historical_fields, signer_for()
        )
        historical_oid = publication._write_publication_object(
            self.probe, historical_document, None
        )
        historical_digest = json.loads(historical_document)["publication_digest"]
        compatibility = authority.HistoricalCompatibilityPublication(
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            pull_request=PR,
            initial_head_sha=HEADS[0],
            initialization_digest=chain.initialization["initialization_digest"],
            enrollment_publication_oid=historical_oid,
            enrollment_publication_digest=historical_digest,
            historical_proof_mode=authority.NATIVE_PROOF_MODE,
        )
        compatibility_policy = replace(
            self.policy,
            initialization_anchors=(anchor,),
            historical_compatibility_publications=(compatibility,),
        )
        with patch.object(
            authority,
            "_load_lifecycle_trust_policy",
            return_value=compatibility_policy,
        ):
            entries, latest, admissions = publication._walk_journal(
                self.probe, historical_oid, BRANCH
            )
        self.assertEqual([item[0] for item in entries], [historical_oid])
        self.assertEqual(latest[(REPOSITORY, ISSUE)][0], historical_oid)
        self.assertEqual(admissions[(REPOSITORY, ISSUE)].admission_digest,
                         historical_digest)

        incompatible_identities = (
            replace(compatibility, enrollment_publication_oid=HEADS[9]),
            replace(compatibility, enrollment_publication_digest="9" * 64),
            replace(compatibility, repository="Other/repo"),
            replace(compatibility, delivery_issue=ISSUE + 1),
            replace(compatibility, pull_request=PR + 1),
            replace(compatibility, initial_head_sha=HEADS[9]),
            replace(compatibility, initialization_digest="8" * 64),
        )
        for incompatible in incompatible_identities:
            with self.subTest(incompatible=incompatible):
                changed_policy = replace(
                    compatibility_policy,
                    historical_compatibility_publications=(incompatible,),
                )
                with patch.object(
                    authority,
                    "_load_lifecycle_trust_policy",
                    return_value=changed_policy,
                ):
                    with self.assertRaisesRegex(
                        publication.LifecyclePublicationError,
                        "native genesis is not independently admitted",
                    ):
                        publication._walk_journal(
                            self.probe, historical_oid, BRANCH
                        )

        tree = publication._run_git(
            self.probe, ["rev-parse", f"{historical_oid}^{{tree}}"]
        ).stdout.decode("ascii").strip()
        copied_object = publication._run_git(
            self.probe,
            ["commit-tree", tree],
            input_bytes=b"Copied immutable publication object\n",
            extra_environment={
                "GIT_AUTHOR_NAME": "SecPal Lifecycle Publication",
                "GIT_AUTHOR_EMAIL": "publication@secpal.invalid",
                "GIT_AUTHOR_DATE": "@1 +0000",
                "GIT_COMMITTER_NAME": "SecPal Lifecycle Publication",
                "GIT_COMMITTER_EMAIL": "publication@secpal.invalid",
                "GIT_COMMITTER_DATE": "@1 +0000",
            },
        ).stdout.decode("ascii").strip()
        self.assertNotEqual(copied_object, historical_oid)
        with patch.object(
            authority,
            "_load_lifecycle_trust_policy",
            return_value=compatibility_policy,
        ):
            with self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "native genesis is not independently admitted",
            ):
                publication._walk_journal(self.probe, copied_object, BRANCH)

        chain.append("HEAD_ADVANCED", head=HEADS[1])
        candidate_bundle, candidate_raw = publication._canonical_bundle(
            authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=chain.raw()
            )
        )
        candidate_lifecycle = authority.verify_native_lifecycle_for_genesis_admission(
            chain.raw()
        )
        candidate_fields = publication._publication_fields(
            operation="ENROLL_EXISTING_LIFECYCLE",
            verified=candidate_lifecycle,
            bundle=candidate_bundle,
            bundle_raw=candidate_raw,
            publication_branch=BRANCH,
            journal_predecessor_oid=None,
            predecessor=None,
            predecessor_oid=None,
            signer_identity=SIGNER,
        )
        candidate_document = publication._sign_publication(
            candidate_fields, signer_for()
        )
        candidate_oid = publication._write_publication_object(
            self.probe, candidate_document, None
        )
        self.assertNotEqual(candidate_oid, historical_oid)
        self.assertNotEqual(
            json.loads(candidate_document)["publication_digest"],
            json.loads(historical_document)["publication_digest"],
        )

        with patch.object(
            authority,
            "_load_lifecycle_trust_policy",
            return_value=compatibility_policy,
        ):
            with self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "native genesis is not independently admitted",
            ):
                publication._walk_journal(self.probe, candidate_oid, BRANCH)

    def test_exact_issue_736_genesis_repairs_without_changing_current(self) -> None:
        chain = issue_736_chain()
        bundle, bundle_raw = publication._canonical_bundle(chain.raw())
        verified = authority.verify_native_lifecycle_for_genesis_admission(bundle_raw)
        fields = publication._publication_fields(
            operation="ENROLL_EXISTING_LIFECYCLE",
            verified=verified,
            bundle=bundle,
            bundle_raw=bundle_raw,
            publication_branch=BRANCH,
            journal_predecessor_oid=None,
            predecessor=None,
            predecessor_oid=None,
            signer_identity=SIGNER,
        )
        raw = publication._sign_publication(fields, signer_for())
        enrollment_oid = publication._write_publication_object(
            self.probe, raw, None
        )
        enrollment_digest = json.loads(raw)["publication_digest"]
        publication._cas_remote_ref(
            self.probe, str(self.remote), BRANCH, enrollment_oid, None
        )
        repair = authority.BootstrapGenesisRepair(
            repair_issue=774,
            delivery_issue=ISSUE_736,
            pull_request=PR_760,
            initial_head_sha=INITIAL_HEAD_736,
            initialization_digest=INITIALIZATION_DIGEST_736,
            validation_receipt_digest=RECEIPT_DIGEST_736,
            final_attestation_digest=ATTESTATION_DIGEST_736,
            enrollment_publication_oid=enrollment_oid,
            enrollment_publication_digest=enrollment_digest,
        )
        repaired_policy = replace(
            self.policy, bootstrap_genesis_repairs=(repair,)
        )

        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=repaired_policy
        ):
            with self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "native genesis is not independently admitted",
            ):
                publication.verify_current_lifecycle_authority(
                    REPOSITORY, ISSUE_736
                )
            admission = publication.repair_published_native_genesis(
                REPOSITORY,
                ISSUE_736,
                repair_issue=774,
                signer_identity=SIGNER,
                signer=signer_for(),
            )
            current = publication.verify_current_lifecycle_authority(
                REPOSITORY, ISSUE_736
            )

        self.assertEqual(current.publication_oid, enrollment_oid)
        self.assertEqual(current.lifecycle.lifecycle_id, chain.lifecycle_id)
        self.assertEqual(current.lifecycle.initialization_evidence_digest,
                         INITIALIZATION_DIGEST_736)
        self.assertEqual(current.lifecycle.pull_request, PR_760)
        self.assertEqual(current.lifecycle.head_sha, CURRENT_HEAD_736)
        self.assertEqual(current.lifecycle.state["unrestricted_review_count"], 1)
        self.assertEqual(current.lifecycle.state["remediation_cycle_count"], 2)
        self.assertEqual(current.lifecycle.state["exceptional_recovery_count"], 0)
        self.assertEqual(current.lifecycle.state["exceptional_continuation_count"], 0)
        self.assertEqual(current.lifecycle.state["ready_transition_count"], 1)
        self.assertIs(current.lifecycle.state["ready"], True)
        self.assertEqual(admission.bootstrap_repair_issue, 774)
        self.assertEqual(admission.journal_predecessor_oid, enrollment_oid)
        self.assertEqual(self.remote_tip(), admission.admission_oid)
        ancestry = subprocess.run(
            ["git", "--git-dir", str(self.remote), "rev-list", self.remote_tip()],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(ancestry, [admission.admission_oid, enrollment_oid])

    def test_branch_local_anchor_cannot_publish_before_global_admission(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        branch_local_policy = replace(
            self.policy,
            initialization_anchors=(
                authority.InitializationAnchor(
                    ISSUE,
                    PR,
                    HEADS[0],
                    chain.initialization["initialization_digest"],
                    PR,
                    chain.head,
                    chain.authorities[-1]["authority_digest"],
                ),
            ),
        )
        native = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )

        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=branch_local_policy
        ):
            with self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "native genesis is not independently admitted",
            ):
                publication.enroll_existing_lifecycle(
                    native, signer_identity=SIGNER, signer=signer_for()
                )

    def test_independent_native_deliveries_do_not_share_source_state(self) -> None:
        first = Chain()
        first.append("INITIALIZED_DRAFT")
        second = Chain(ISSUE + 1)
        second.append("INITIALIZED_DRAFT")

        first_admission = publication.admit_native_genesis(
            first.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        first_publication = publication.enroll_existing_lifecycle(
            authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=first.raw()
            ),
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        second_admission = publication.admit_native_genesis(
            second.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        second_publication = publication.enroll_existing_lifecycle(
            authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=second.raw()
            ),
            signer_identity=SIGNER,
            signer=signer_for(),
        )

        self.assertEqual(first_publication.journal_predecessor_oid,
                         first_admission.admission_oid)
        self.assertEqual(second_admission.journal_predecessor_oid,
                         first_publication.publication_oid)
        self.assertEqual(second_publication.journal_predecessor_oid,
                         second_admission.admission_oid)
        self.assertEqual(
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
            .lifecycle.lifecycle_id,
            first.lifecycle_id,
        )
        self.assertEqual(
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE + 1)
            .lifecycle.lifecycle_id,
            second.lifecycle_id,
        )

    def test_native_genesis_admission_is_closed_unique_and_not_legacy(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        admission = publication.admit_native_genesis(
            chain.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "already admitted"
        ):
            publication.admit_native_genesis(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )

        competitor = Chain()
        competitor.initialization["initial_head_sha"] = HEADS[1]
        with self.assertRaises(authority.LifecycleAuthorityError):
            publication.admit_native_genesis(
                competitor.raw(), signer_identity=SIGNER, signer=signer_for()
            )

        with self.assertRaises(
            (authority.LifecycleAuthorityError, publication.LifecyclePublicationError)
        ):
            publication.admit_native_genesis(
                chain.raw(),
                signer_identity=OTHER_SIGNER,
                signer=signer_for(OTHER_SIGNER),
            )

        publication._observe_remote_current_once(
            self.probe, str(self.remote), BRANCH
        )
        admission_raw = publication._read_publication_object(
            self.probe, admission.admission_oid
        )[0]
        document = json.loads(admission_raw)
        mutations = (
            ("repository", "Other/repo"),
            ("delivery_issue", ISSUE + 1),
            ("pull_request", PR + 1),
            ("initial_head_sha", HEADS[9]),
            ("initialization_digest", "9" * 64),
            ("validation_receipt_digest", "8" * 64),
            ("final_attestation_digest", "7" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(document)
                changed[field] = value
                with self.assertRaises(
                    (authority.LifecycleAuthorityError,
                     publication.LifecyclePublicationError)
                ):
                    publication._verify_genesis_admission_document(
                        authority.canonical_json_bytes(changed),
                        object_oid=admission.admission_oid,
                        expected_branch=BRANCH,
                    )

        legacy = recovered_ready_chain(ISSUE)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "admitted native genesis cannot use legacy adoption",
        ):
            publication.enroll_existing_lifecycle(
                legacy.published(), signer_identity=SIGNER, signer=signer_for()
            )

    def test_concurrent_genesis_admission_cas_has_one_winner(self) -> None:
        first = Chain()
        first.append("INITIALIZED_DRAFT")
        second = Chain(ISSUE + 1)
        second.append("INITIALIZED_DRAFT")
        objects: list[str] = []
        for chain in (first, second):
            fields = publication._genesis_admission_fields(
                initialization=chain.initialization,
                publication_branch=BRANCH,
                journal_predecessor_oid=None,
                signer_identity=SIGNER,
            )
            raw = publication._sign_genesis_admission(fields, signer_for())
            objects.append(
                publication._write_publication_object(self.probe, raw, None)
            )

        publication._cas_remote_ref(
            self.probe, str(self.remote), BRANCH, objects[0], None
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "compare-and-swap"
        ):
            publication._cas_remote_ref(
                self.probe, str(self.remote), BRANCH, objects[1], None
            )
        self.assertEqual(self.remote_tip(), objects[0])
        _, latest, admissions = publication._walk_journal(
            self.probe, objects[0], BRANCH
        )
        self.assertEqual(latest, {})
        self.assertEqual(set(admissions), {(REPOSITORY, ISSUE)})

    def test_native_journal_rejects_wrong_predecessor_and_identity_substitution(
        self,
    ) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        anchor = authority.InitializationAnchor(
            ISSUE,
            PR,
            HEADS[0],
            chain.initialization["initialization_digest"],
            PR,
            chain.head,
            chain.authorities[-1]["authority_digest"],
        )
        policy = replace(self.policy, initialization_anchors=(anchor,))
        native_h = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )
        with patch.object(authority, "_load_lifecycle_trust_policy", return_value=policy):
            admission = publication.admit_native_genesis(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            publication.enroll_existing_lifecycle(
                native_h, signer_identity=SIGNER, signer=signer_for()
            )
            chain.append("HEAD_ADVANCED", head=HEADS[1])
            native_h2 = authority.serialize_publication_lifecycle_evidence(
                lifecycle_evidence=chain.raw()
            )
            h2 = publication.advance_current_terminal(
                native_h2, signer_identity=SIGNER, signer=signer_for()
            )
            publication._observe_remote_current_once(self.probe, str(self.remote), BRANCH)
            h2_raw = publication._read_publication_object(
                self.probe, h2.publication_oid
            )[0]
            h2_document, h2_lifecycle = publication._verify_publication_document(
                h2_raw,
                object_oid=h2.publication_oid,
                expected_branch=BRANCH,
                native_genesis_admission=admission,
            )
            chain.append("HEAD_ADVANCED", head=HEADS[2])
            native_h3, native_h3_raw = publication._canonical_bundle(
                authority.serialize_publication_lifecycle_evidence(
                    lifecycle_evidence=chain.raw()
                )
            )
            h3_lifecycle = authority._verify_lifecycle_authority_for_journal(
                native_h3_raw,
                admitted_initialization=chain.initialization,
            )
            publication._require_exact_successor(
                h2_lifecycle,
                h2_document,
                h3_lifecycle,
                {"lifecycle_evidence": native_h3},
            )
            for changed in (
                replace(h3_lifecycle, delivery_issue=ISSUE + 1),
                replace(h3_lifecycle, initialization_evidence_digest="9" * 64),
            ):
                with self.assertRaisesRegex(
                    publication.LifecyclePublicationError,
                    "exact allowed successor",
                ):
                    publication._require_exact_successor(
                        h2_lifecycle,
                        h2_document,
                        changed,
                        {"lifecycle_evidence": native_h3},
                    )
            wrong_fields = publication._publication_fields(
                operation="ADVANCE_CURRENT_TERMINAL",
                verified=h3_lifecycle,
                bundle=native_h3,
                bundle_raw=native_h3_raw,
                publication_branch=BRANCH,
                journal_predecessor_oid=h2.publication_oid,
                predecessor=h2_document,
                predecessor_oid=HEADS[9],
                signer_identity=SIGNER,
            )
            wrong_raw = publication._sign_publication(wrong_fields, signer_for())
            wrong_oid = publication._write_publication_object(
                self.probe, wrong_raw, h2.publication_oid
            )
            publication._cas_remote_ref(
                self.probe,
                str(self.remote),
                BRANCH,
                wrong_oid,
                h2.publication_oid,
            )
            with self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "predecessor binding",
            ):
                publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)

    def test_pr_rebound_preserves_legacy_root_and_history(self) -> None:
        chain, enrolled = self.enroll()
        checkpoint = copy.deepcopy(chain.checkpoint)
        chain.append("PR_REBOUND", replacement_pull_request=PR + 1)
        chain.checkpoint = checkpoint
        advanced = publication.advance_current_terminal(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(advanced.lifecycle.pull_request, PR + 1)
        self.assertEqual(advanced.lifecycle.state, enrolled.lifecycle.state)
        self.assertEqual(advanced.lifecycle.legacy_adoption_checkpoint_digest,
                         enrolled.lifecycle.legacy_adoption_checkpoint_digest)

    def test_protected_journal_rejects_rollback_and_deletion(self) -> None:
        chain, enrolled = self.enroll()
        checkpoint = copy.deepcopy(chain.checkpoint)
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        chain.checkpoint = checkpoint
        advanced = publication.advance_current_terminal(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        rollback = subprocess.run(
            ["git", "--git-dir", str(self.probe), "push", "--force", str(self.remote),
             f"{enrolled.publication_oid}:{BRANCH}"],
            capture_output=True, text=True,
        )
        deletion = subprocess.run(
            ["git", "--git-dir", str(self.probe), "push", str(self.remote), f":{BRANCH}"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(rollback.returncode, 0)
        self.assertNotEqual(deletion.returncode, 0)
        self.assertEqual(self.remote_tip(), advanced.publication_oid)
        current = publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
        self.assertEqual(current.publication_oid, advanced.publication_oid)

    def test_exact_compare_and_swap_allows_only_one_concurrent_successor(self) -> None:
        _, enrolled = self.enroll()
        publication._observe_remote_current_once(self.probe, str(self.remote), BRANCH)
        first = publication._write_publication_object(
            self.probe, b"first orphan-safe successor", enrolled.publication_oid
        )
        second = publication._write_publication_object(
            self.probe, b"second orphan-safe successor", enrolled.publication_oid
        )
        publication._cas_remote_ref(
            self.probe, str(self.remote), BRANCH, first, enrolled.publication_oid
        )
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "compare-and-swap"):
            publication._cas_remote_ref(
                self.probe, str(self.remote), BRANCH, second, enrolled.publication_oid
            )
        self.assertEqual(self.remote_tip(), first)

    def test_same_head_successor_invalidates_prior_current(self) -> None:
        chain, enrolled = self.enroll()
        checkpoint = copy.deepcopy(chain.checkpoint)
        chain.append("READY_TO_DRAFT")
        chain.checkpoint = checkpoint
        advanced = publication.advance_current_terminal(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(advanced.lifecycle.head_sha, enrolled.lifecycle.head_sha)
        self.assertNotEqual(advanced.publication_oid, enrolled.publication_oid)
        self.assertEqual(publication.verify_current_lifecycle_authority(
            REPOSITORY, ISSUE).publication_oid, advanced.publication_oid)

    def test_global_journal_selects_latest_event_per_delivery(self) -> None:
        first_chain, first = self.enroll()
        second_chain = recovered_ready_chain(ISSUE + 1)
        _, second = self.enroll(second_chain)
        self.assertEqual(second.journal_predecessor_oid, first.publication_oid)
        self.assertEqual(publication.verify_current_lifecycle_authority(
            REPOSITORY, ISSUE).publication_oid, first.publication_oid)
        self.assertEqual(publication.verify_current_lifecycle_authority(
            REPOSITORY, ISSUE + 1).publication_oid, second.publication_oid)
        self.assertEqual(first_chain.lifecycle_id,
                         publication.verify_current_lifecycle_authority(
                             REPOSITORY, ISSUE).lifecycle.lifecycle_id)

    def test_hostile_git_configuration_cannot_redirect_maintained_remote(self) -> None:
        hostile = self.remote.parent / "hostile.git"
        hostile_home = self.remote.parent / "hostile-home"
        subprocess.run(["git", "init", "--bare", "-q", str(hostile)], check=True)
        hostile_home.mkdir()
        (hostile_home / ".gitconfig").write_text(
            f"[url \"{hostile}\"]\n\tinsteadOf = {self.remote}\n", encoding="utf-8"
        )
        subprocess.run(["git", "--git-dir", str(self.probe), "config",
                        f"url.{hostile}.insteadOf", str(self.remote)], check=True)
        environment = {
            "HOME": str(hostile_home), "PATH": str(hostile_home),
            "GIT_CONFIG_GLOBAL": str(hostile_home / ".gitconfig"),
            "GIT_CONFIG_SYSTEM": str(hostile_home / ".gitconfig"),
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "url.fake.insteadOf",
            "GIT_CONFIG_VALUE_0": str(self.remote), "GIT_SSH_COMMAND": "false",
            "GIT_ASKPASS": "false", "SSH_ASKPASS": "false",
            "SSH_AUTH_SOCK": str(hostile_home / "agent"), "GNUPGHOME": str(hostile_home),
            "LD_PRELOAD": str(hostile_home / "inject.so"),
        }
        with patch.dict(os.environ, environment):
            _, enrolled = self.enroll()
            current = publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
        self.assertEqual(current.publication_oid, enrolled.publication_oid)
        hostile_ref = subprocess.run(
            ["git", "--git-dir", str(hostile), "rev-parse", "--verify", "--quiet", BRANCH],
            capture_output=True,
        )
        self.assertNotEqual(hostile_ref.returncode, 0)

    def test_live_protection_contract_requires_exact_active_ruleset(self) -> None:
        self.protection_patch.stop()
        payload = {
            "id": RULESET_ID, "target": "branch", "enforcement": "active",
            "bypass_actors": [],
            "conditions": {"ref_name": {"include": [BRANCH], "exclude": []}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}],
        }
        good = subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b"")
        try:
            with patch.object(publication, "_run_gh", return_value=good):
                self.assertEqual(publication._verify_live_protection(self.policy), RULESET_ID)
            for mutation in (
                lambda value: value.update(enforcement="disabled"),
                lambda value: value.update(bypass_actors=[{"actor_type": "OrganizationAdmin"}]),
                lambda value: value.pop("bypass_actors"),
                lambda value: value["rules"].pop(),
                lambda value: value["conditions"]["ref_name"].update(include=["refs/heads/other"]),
            ):
                changed = copy.deepcopy(payload)
                mutation(changed)
                result = subprocess.CompletedProcess([], 0, json.dumps(changed).encode(), b"")
                with patch.object(publication, "_run_gh", return_value=result):
                    with self.assertRaises(publication.LifecyclePublicationError):
                        publication._verify_live_protection(self.policy)
        finally:
            self.protection_patch.start()

    def test_wrong_publication_signer_and_tampered_document_fail_closed(self) -> None:
        chain = recovered_ready_chain()
        with self.assertRaises((publication.LifecyclePublicationError,
                                authority.LifecycleAuthorityError)):
            publication.enroll_existing_lifecycle(
                chain.published(), signer_identity=OTHER_SIGNER,
                signer=signer_for(OTHER_SIGNER),
            )
        _, enrolled = self.enroll(chain)
        publication._observe_remote_current_once(self.probe, str(self.remote), BRANCH)
        raw = publication._read_publication_object(self.probe, enrolled.publication_oid)[0]
        document = json.loads(raw)
        document["signature"]["value"] = ""
        tampered = authority.canonical_json_bytes(document)
        with self.assertRaises((publication.LifecyclePublicationError,
                                authority.LifecycleAuthorityError)):
            publication._verify_publication_document(
                tampered, object_oid=enrolled.publication_oid, expected_branch=BRANCH
            )

    def test_duplicate_unknown_and_cross_identity_inputs_fail_closed(self) -> None:
        _, enrolled = self.enroll()
        publication._observe_remote_current_once(self.probe, str(self.remote), BRANCH)
        raw = publication._read_publication_object(self.probe, enrolled.publication_oid)[0]
        duplicate = raw.replace(b'{"delivery_issue":',
                                b'{"delivery_issue":752,"delivery_issue":', 1)
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "duplicate"):
            publication._verify_publication_document(
                duplicate, object_oid=enrolled.publication_oid, expected_branch=BRANCH
            )
        document = json.loads(raw)
        for field, value in (
            ("schema_version", "2.0"), ("repository", "Other/repo"),
            ("delivery_issue", ISSUE + 1), ("lifecycle_id", "lifecycle:" + "9" * 64),
            ("pull_request", PR + 1), ("head_sha", HEADS[7]),
            ("terminal_authority_digest", "8" * 64), ("publication_branch", "refs/heads/other"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(document)
                changed[field] = value
                with self.assertRaises((publication.LifecyclePublicationError,
                                        authority.LifecycleAuthorityError)):
                    publication._verify_publication_document(
                        authority.canonical_json_bytes(changed),
                        object_oid=enrolled.publication_oid, expected_branch=BRANCH,
                    )

    def test_zero_enrollment_remains_valid_but_required_publication_fails(self) -> None:
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "unavailable"):
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)


if __name__ == "__main__":
    main()
