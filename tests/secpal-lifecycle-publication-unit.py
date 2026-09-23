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
from scripts.secpal_pr_review import lifecycle_execution as execution
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
CONTRACTS_REPOSITORY = "SecPal/contracts"
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
    def __init__(
        self,
        issue: int = ISSUE,
        *,
        repository: str = REPOSITORY,
        pull_request: int = PR,
    ) -> None:
        self.issue = issue
        self.repository = repository
        self.initialization = authority.create_delivery_initialization(
            repository=repository, delivery_issue=issue, pull_request=pull_request,
            initial_head_sha=HEADS[0], validation_receipt_digest="1" * 64,
            final_attestation_digest="2" * 64, signer_identity=SIGNER,
            signer=signer_for(),
        )
        self.lifecycle_id = authority.delivery_initialization_lifecycle_id(
            self.initialization["initialization_digest"]
        )
        self.authorities: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.pull_request = pull_request
        self.head = HEADS[0]
        self.checkpoint: dict[str, Any] | None = None

    def append(self, transition: str, *, head: str | None = None,
               replacement_pull_request: int | None = None) -> None:
        resulting_head = head or self.head
        event = authority.create_transition_authorization(
            event_id=(f"genesis:{self.initialization['initialization_digest']}"
                      if not self.events else f"event-{len(self.events) + 1}"),
            repository=self.repository, delivery_issue=self.issue,
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
        "signature_policy": {"accepted_formats": ["ssh", "openpgp"]},
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
                [], 0, "https://github.com/SecPal/.github.git\n", ""
            ),
            subprocess.CompletedProcess(
                [],
                0,
                (
                    f"tree {tree}\n"
                    + "".join(
                        f"parent {parent_sha}\n"
                        for parent_sha in integration["ordered_parent_shas"]
                    )
                    + "gpgsig -----BEGIN SSH SIGNATURE-----\n\n"
                ),
                "",
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
                repository_root=Path(__file__).resolve().parents[1],
                signature_policy=registry["signature_policy"],
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

    def test_typed_normal_review_publishes_once_and_rejects_second_use(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        lifecycle = replace(
            authority._verify_lifecycle_authority_objects(
                chain.authorities, chain.events,
                accepted_event_signers=frozenset({SIGNER}),
                accepted_authority_signers=frozenset({SIGNER}),
                signature_verifier=verify_signature,
            ),
            tree_sha=HEADS[9], validation_receipt_digest="8" * 64,
            adoption_source_evidence_digest="9" * 64,
        )
        current = publication.VerifiedLifecyclePublication(
            HEADS[7], "7" * 64, BRANCH, HEADS[6], HEADS[5], lifecycle,
            chain.raw(),
        )
        qualification_fields = {
            "repository": REPOSITORY, "delivery_issue": ISSUE,
            "pull_request": PR, "head_sha": lifecycle.head_sha,
            "tree_sha": lifecycle.tree_sha,
            "author_conversation_id": "11111111-1111-4111-8111-111111111111",
            "author_workspace": "/author", "author_profile_id": "author-profile",
            "verifier_conversation_id": "22222222-2222-4222-8222-222222222222",
            "verifier_workspace": "/verifier", "verifier_profile_id": "verifier-profile",
            "verifier_execution_status": "finished",
            "execution_isolation": authority.NORMAL_REVIEW_ISOLATION,
            "author_verifier_distinct": True, "verifier_secret_refs": [],
            "verifier_runtime_credential_bindings": [], "verifier_mcp_modules": [],
            "github_write_count": 0, "lifecycle_write_count": 0,
            "mutation_mcp_count": 0, "result": "PASS",
            "complete_material_finding_ids": [], "finish_event_id": "finish-event",
            "finish_message_digest": "a" * 64,
            "control_plane_evidence_digest": "b" * 64,
        }
        qualification = authority.AuthenticatedNormalReviewQualification(
            repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
            head_sha=lifecycle.head_sha, tree_sha=lifecycle.tree_sha,
            author_conversation_id=qualification_fields["author_conversation_id"],
            author_workspace="/author", author_profile_id="author-profile",
            verifier_conversation_id=qualification_fields["verifier_conversation_id"],
            verifier_workspace="/verifier", verifier_profile_id="verifier-profile",
            verifier_execution_status="finished", result="PASS",
            material_finding_ids=(), finish_event_id="finish-event",
            finish_message_digest="a" * 64,
            control_plane_evidence_digest="b" * 64,
            qualification_digest=authority.digest_json(qualification_fields),
            _verification_seal=authority._AUTHENTICATED_NORMAL_REVIEW_QUALIFICATION,
        )
        admission = authority._create_normal_review_admission(
            admission_id="normal-review-publication", qualification=qualification,
            lifecycle_id=lifecycle.lifecycle_id,
            current_publication_oid=current.publication_oid,
            current_publication_digest=current.publication_digest,
            current_authority_digest=lifecycle.authority_digest,
            validation_receipt_digest=lifecycle.validation_receipt_digest,
            final_attestation_digest=lifecycle.adoption_source_evidence_digest,
            signer_identity=SIGNER, signer=signer_for(),
        )
        policy = replace(
            self.policy,
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
        )
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )
        captured: list[bytes] = []

        def publish(raw: bytes, **_kwargs: Any) -> publication.VerifiedLifecyclePublication:
            captured.append(raw)
            bundle = json.loads(raw)
            self.assertEqual(
                bundle["transition_authorizations"][-1]["normal_review_admission_digest"],
                admission["admission_digest"],
            )
            reviewed_lifecycle = replace(
                lifecycle,
                authority_digest=bundle["authority_chain"][-1]["authority_digest"],
                state=copy.deepcopy(bundle["authority_chain"][-1]["state_after"]),
            )
            return replace(
                current, publication_oid=HEADS[8], publication_digest="c" * 64,
                lifecycle=reviewed_lifecycle, serialized_lifecycle_evidence=raw,
            )

        published: list[publication.VerifiedLifecyclePublication] = []

        def publish_and_remember(
            raw: bytes, **kwargs: Any
        ) -> publication.VerifiedLifecyclePublication:
            result = publish(raw, **kwargs)
            published.append(result)
            return result

        reads = 0

        def read_current(*_args: Any) -> publication.VerifiedLifecyclePublication:
            nonlocal reads
            reads += 1
            return published[-1] if published else current

        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=policy
        ), patch.object(
            authority, "_policy_signature_verifier", return_value=verify_signature
        ), patch.object(
            publication, "verify_current_lifecycle_authority",
            side_effect=read_current,
        ), patch.object(
            publication, "advance_current_terminal", side_effect=publish_and_remember
        ):
            result = execution.publish_typed_normal_review(
                REPOSITORY, ISSUE, admission, signers
            )
        self.assertEqual(result.lifecycle.state["unrestricted_review_count"], 1)
        self.assertEqual(len(captured), 1)
        with patch.object(
            publication, "verify_current_lifecycle_authority", return_value=result
        ), self.assertRaisesRegex(
            execution.LifecycleExecutionError, "exact native Draft CURRENT"
        ):
            execution.publish_typed_normal_review(
                REPOSITORY, ISSUE, admission, signers
            )

    def correction_fixture(
        self,
    ) -> tuple[
        Chain,
        publication.VerifiedLifecyclePublication,
        dict[str, Any],
        authority.LifecycleTrustPolicy,
    ]:
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
        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=policy
        ):
            publication.admit_native_genesis(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            publication.enroll_existing_lifecycle(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            chain.append("UNRESTRICTED_REVIEW_CONSUMED")
            current = publication.advance_current_terminal(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
        invalid = chain.events[-1]
        correction = (
            authority.create_invalid_review_consumption_correction_authorization(
                event_id="correction-1",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=chain.lifecycle_id,
                pull_request=PR,
                predecessor_authority_digest=current.lifecycle.authority_digest,
                head_sha=current.lifecycle.head_sha,
                initialization_evidence_digest=chain.initialization[
                    "initialization_digest"
                ],
                current_publication_oid=current.publication_oid,
                current_publication_digest=current.publication_digest,
                current_tree_sha=HEADS[9],
                invalid_event_id=invalid["event_id"],
                invalid_event_digest=invalid["event_digest"],
                invalid_event_predecessor_authority_digest=invalid[
                    "predecessor_authority_digest"
                ],
                signer_identity=SIGNER,
                signer=signer_for(),
            )
        )
        return chain, current, correction, policy

    def ready_correction_fixture(
        self,
    ) -> tuple[
        Chain,
        publication.VerifiedLifecyclePublication,
        dict[str, Any],
        authority.LifecycleTrustPolicy,
        tuple[publication.GitHubPullRequestTimelineEvent, ...],
        tuple[publication.GitHubPullRequestTimelineEvent, ...],
    ]:
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
        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=policy
        ):
            publication.admit_native_genesis(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            publication.enroll_existing_lifecycle(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            chain.append("UNRESTRICTED_REVIEW_CONSUMED")
            publication.advance_current_terminal(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            chain.append("DRAFT_TO_READY")
            current = publication.advance_current_terminal(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
        invalid_review = chain.events[1]
        unauthorized_ready = chain.events[2]
        correction = authority.create_invalid_review_derived_ready_correction_authorization(
            event_id="ready-correction-1",
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle_id=chain.lifecycle_id,
            pull_request=PR,
            predecessor_authority_digest=current.lifecycle.authority_digest,
            head_sha=current.lifecycle.head_sha,
            initialization_evidence_digest=chain.initialization[
                "initialization_digest"
            ],
            current_publication_oid=current.publication_oid,
            current_publication_digest=current.publication_digest,
            current_tree_sha=HEADS[9],
            invalid_review_event_id=invalid_review["event_id"],
            invalid_review_event_digest=invalid_review["event_digest"],
            unauthorized_ready_event_id=unauthorized_ready["event_id"],
            unauthorized_ready_event_digest=unauthorized_ready["event_digest"],
            unauthorized_ready_predecessor_authority_digest=(
                unauthorized_ready["predecessor_authority_digest"]
            ),
            github_ready_event_database_id=31627413421,
            github_ready_event_node_id="RFRE_lADOQFR1MM8AAAABSTyF988AAAAHXSQHrQ",
            github_ready_event_actor="aroviqen",
            github_ready_event_created_at="2026-09-22T19:51:55Z",
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        ready = publication.GitHubPullRequestTimelineEvent(
            "READY_FOR_REVIEW",
            31627413421,
            "RFRE_lADOQFR1MM8AAAABSTyF988AAAAHXSQHrQ",
            "aroviqen",
            "2026-09-22T19:51:55Z",
        )
        converted = publication.GitHubPullRequestTimelineEvent(
            "CONVERT_TO_DRAFT",
            31627419999,
            "CTDE_exact_correction",
            "aroviqen",
            "2026-09-22T21:45:00Z",
        )
        return chain, current, correction, policy, (ready,), (ready, converted)

    @staticmethod
    def resign_correction(value: dict[str, Any]) -> dict[str, Any]:
        fields = copy.deepcopy(value)
        fields.pop("event_digest", None)
        fields.pop("signature", None)
        fields["signature"] = signer_for()(
            authority.canonical_json_bytes(fields), authority.EVENT_DOMAIN
        )
        fields["event_digest"] = authority.digest_json(fields)
        return fields

    def test_ready_correction_converges_once_and_is_idempotent(self) -> None:
        chain, current, correction, policy, before, after = (
            self.ready_correction_fixture()
        )
        ready_live = execution.LivePullRequest(
            REPOSITORY, PR, "OPEN", chain.head, False
        )
        draft_live = replace(ready_live, draft=True)
        ready_api = {
            "repository": REPOSITORY,
            "pull_request": PR,
            "state": "OPEN",
            "draft": False,
            "head_sha": chain.head,
        }
        draft_api = {**ready_api, "draft": True}
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )
        preserved = copy.deepcopy(chain.events)

        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
            ),
            patch.object(
                execution, "_read_live_github",
                side_effect=[ready_live, draft_live, draft_live, draft_live],
            ),
            patch.object(
                publication, "_observe_pre_enrollment_pull_request",
                side_effect=[ready_api, draft_api],
            ),
            patch.object(
                publication, "_observe_pull_request_lifecycle_timeline",
                side_effect=[before, before, after, after, after, after],
            ),
            patch.object(
                execution, "_write_live_github", return_value="SUCCESS"
            ) as github_write,
        ):
            corrected = execution.execute_invalid_review_derived_ready_correction(
                correction, signers
            )
            replay = execution.execute_invalid_review_derived_ready_correction(
                correction, signers
            )

        github_write.assert_called_once_with(REPOSITORY, PR, "READY_TO_DRAFT")
        self.assertEqual(replay, corrected)
        bundle = json.loads(corrected.serialized_lifecycle_evidence)
        self.assertEqual(bundle["transition_authorizations"][:3], preserved)
        self.assertEqual(
            bundle["transition_authorizations"][-1]["transition_kind"],
            "INVALID_REVIEW_DERIVED_READY_CORRECTED",
        )
        expected = copy.deepcopy(current.lifecycle.state)
        expected.update(
            unrestricted_review_count=0,
            draft=True,
            ready=False,
            ready_transition_count=0,
            ready_history=[],
        )
        self.assertEqual(corrected.lifecycle.state, expected)

    def test_ready_correction_resumes_authenticated_draft_interruption(self) -> None:
        chain, _current, correction, policy, _before, after = (
            self.ready_correction_fixture()
        )
        draft_live = execution.LivePullRequest(
            REPOSITORY, PR, "OPEN", chain.head, True
        )
        draft_api = {
            "repository": REPOSITORY,
            "pull_request": PR,
            "state": "OPEN",
            "draft": True,
            "head_sha": chain.head,
        }
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )
        conversion = publication._authenticate_ready_correction_conversion(
            authorization=correction, before=after[:-1], after=after
        )
        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
            ),
            patch.object(
                execution, "_read_live_github",
                side_effect=[draft_live, draft_live],
            ),
            patch.object(
                publication, "_observe_pre_enrollment_pull_request",
                side_effect=[draft_api, draft_api],
            ),
            patch.object(
                publication, "_observe_pull_request_lifecycle_timeline",
                side_effect=[after, after, after, after],
            ),
            patch.object(
                execution, "_write_live_github",
                side_effect=AssertionError("resume must not mutate GitHub"),
            ) as github_write,
        ):
            corrected = execution.execute_invalid_review_derived_ready_correction(
                correction, signers, ready_correction_conversion=conversion
            )
        github_write.assert_not_called()
        self.assertTrue(corrected.lifecycle.state["draft"])
        self.assertFalse(corrected.lifecycle.state["ready"])

    def test_ready_correction_conversion_is_bound_to_exact_authorization(self) -> None:
        _chain, _current, correction, _policy, before, after = (
            self.ready_correction_fixture()
        )
        conversion = publication._authenticate_ready_correction_conversion(
            authorization=correction, before=before, after=after
        )
        substituted = copy.deepcopy(correction)
        substituted["event_id"] = "ready-correction-substituted"
        substituted = self.resign_correction(substituted)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "this correction attempt"
        ):
            publication._require_ready_correction_conversion(
                conversion, substituted, after
            )

    def test_ready_correction_publication_requires_conversion_evidence(self) -> None:
        _chain, current, correction, policy, _before, _after = (
            self.ready_correction_fixture()
        )
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )
        successor = execution._derive_invalid_review_ready_correction_successor(
            current, correction, signers
        )
        with patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=policy
        ), self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "requires exact Draft conversion evidence",
        ):
            publication.advance_current_terminal(
                successor, signer_identity=SIGNER, signer=signer_for()
            )

    def test_lifecycle_timeline_capture_is_bounded_and_accepts_app_actor(self) -> None:
        app_event = {
            "event": "ready_for_review", "id": 1, "node_id": "RFRE_app",
            "actor": {"login": "review-app[bot]"},
            "created_at": "2026-09-23T00:00:00Z", "commit_id": None,
        }
        with patch.object(
            publication, "_run_gh",
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps([app_event]).encode(), b""
            ),
        ) as run:
            observed = publication._observe_pull_request_lifecycle_timeline(
                REPOSITORY, PR
            )
        self.assertEqual(observed[0].actor, "review-app[bot]")
        command = run.call_args.args[0]
        self.assertNotIn("--paginate", command)
        self.assertNotIn("--slurp", command)
        self.assertIn("X-GitHub-Api-Version: 2026-03-10", command)
        with patch.object(
            publication, "_run_gh",
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps([{} for _ in range(100)]).encode(), b""
            ),
        ), self.assertRaisesRegex(
            publication.LifecyclePublicationError, "closed 99-event bound"
        ):
            publication._observe_pull_request_lifecycle_timeline(REPOSITORY, PR)

    def test_ready_correction_rejects_identity_history_and_convergence_drift(self) -> None:
        chain, current, correction, policy, before, after = (
            self.ready_correction_fixture()
        )
        ready_live = execution.LivePullRequest(
            REPOSITORY, PR, "OPEN", chain.head, False
        )
        draft_live = replace(ready_live, draft=True)
        ready_api = {
            "repository": REPOSITORY,
            "pull_request": PR,
            "state": "OPEN",
            "draft": False,
            "head_sha": chain.head,
        }
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )

        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
            ),
            patch.object(
                publication, "verify_current_lifecycle_authority",
                return_value=current,
            ),
            patch.object(
                publication, "_observe_pre_enrollment_pull_request",
                return_value=ready_api,
            ),
            patch.object(
                publication, "_observe_pull_request_lifecycle_timeline",
                return_value=before,
            ),
        ):
            self.assertIs(
                publication.verify_invalid_review_derived_ready_correction(
                    correction
                ),
                current,
            )
            for field, value in (
                ("repository", "Other/repository"),
                ("delivery_issue", ISSUE + 1),
                ("pull_request", PR + 1),
                ("lifecycle_id", "lifecycle:" + "7" * 64),
                ("resulting_head_sha", HEADS[7]),
                ("current_publication_oid", HEADS[7]),
                ("current_publication_digest", "7" * 64),
                ("current_tree_sha", HEADS[7]),
                ("invalid_review_event_digest", "7" * 64),
                ("unauthorized_ready_event_digest", "7" * 64),
                ("github_ready_event_database_id", 31627413422),
                ("github_ready_event_node_id", "RFRE_wrong"),
                ("github_ready_event_actor", "other"),
                ("github_ready_event_created_at", "2026-09-22T19:51:56Z"),
            ):
                changed = copy.deepcopy(correction)
                changed[field] = value
                with self.subTest(field=field), self.assertRaises(
                    (authority.LifecycleAuthorityError,
                     publication.LifecyclePublicationError)
                ):
                    publication.verify_invalid_review_derived_ready_correction(
                        self.resign_correction(changed)
                    )

        later = after + (
            publication.GitHubPullRequestTimelineEvent(
                "READY_FOR_REVIEW", 31627420000, "RFRE_later", "aroviqen",
                "2026-09-22T21:46:00Z",
            ),
        )
        cases = (
            ("draft without exact event", draft_live, before, "SUCCESS"),
            ("unknown write result", ready_live, before, "UNKNOWN"),
            ("write did not converge", ready_live, before, "AMBIGUOUS"),
            ("later event", ready_live, later, "SUCCESS"),
        )
        for label, live_after, timeline_after, outcome in cases:
            with (
                self.subTest(label=label),
                patch.object(
                    authority, "_load_lifecycle_trust_policy", return_value=policy
                ),
                patch.object(
                    publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
                ),
                patch.object(
                    execution, "_read_live_github",
                    side_effect=(
                        [draft_live]
                        if label == "draft without exact event"
                        else [ready_live, live_after]
                    ),
                ),
                patch.object(
                    publication, "_observe_pre_enrollment_pull_request",
                    return_value=ready_api,
                ),
                patch.object(
                    publication, "_observe_pull_request_lifecycle_timeline",
                    side_effect=(
                        [before, before]
                        if label == "draft without exact event"
                        else [before, before, timeline_after]
                    ),
                ),
                patch.object(
                    execution, "_write_live_github", return_value=outcome
                ),
                self.assertRaises(
                    (execution.LifecycleExecutionError,
                     publication.LifecyclePublicationError)
                ),
            ):
                execution.execute_invalid_review_derived_ready_correction(
                    correction, signers
                )
            self.assertEqual(self.remote_tip(), current.publication_oid)

    def test_correction_executor_composes_append_only_cas_and_one_later_review(
        self,
    ) -> None:
        chain, reviewed, correction, policy = self.correction_fixture()
        state_before = copy.deepcopy(reviewed.lifecycle.state)
        invalid_event = copy.deepcopy(chain.events[-1])
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )

        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
            ),
            patch.object(
                publication, "_observe_pre_enrollment_pull_request",
                return_value={
                    "repository": REPOSITORY, "pull_request": PR,
                    "state": "OPEN", "draft": True, "head_sha": chain.head,
                },
            ) as github_observation,
            patch.object(
                execution, "_write_live_github",
                side_effect=AssertionError("correction must not mutate GitHub"),
            ) as github_write,
        ):
            corrected = execution.execute_invalid_review_consumption_correction(
                correction, signers
            )

            self.assertEqual(self.remote_tip(), corrected.publication_oid)
            self.assertEqual(
                corrected.predecessor_publication_oid, reviewed.publication_oid
            )
            bundle = json.loads(corrected.serialized_lifecycle_evidence)
            self.assertEqual(bundle["transition_authorizations"][1], invalid_event)
            self.assertEqual(
                bundle["transition_authorizations"][-1]["transition_kind"],
                "INVALID_REVIEW_CONSUMPTION_CORRECTED",
            )
            expected = copy.deepcopy(state_before)
            expected["unrestricted_review_count"] = 0
            self.assertEqual(corrected.lifecycle.state, expected)
            self.assertGreaterEqual(github_observation.call_count, 1)
            github_write.assert_not_called()

            review = authority.create_transition_authorization(
                event_id="independent-review-after-correction",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=chain.lifecycle_id,
                pull_request=PR,
                predecessor_authority_digest=corrected.lifecycle.authority_digest,
                predecessor_head_sha=corrected.lifecycle.head_sha,
                resulting_head_sha=corrected.lifecycle.head_sha,
                transition_kind="UNRESTRICTED_REVIEW_CONSUMED",
                replacement_pull_request=None,
                initialization_evidence_digest=chain.initialization[
                    "initialization_digest"
                ],
                signer_identity=SIGNER,
                signer=signer_for(),
            )
            events = bundle["transition_authorizations"]
            snapshots = bundle["authority_chain"]
            review_snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=snapshots,
                transition_authorizations=events,
                authorization=review,
                signer_identity=SIGNER,
                authority_signer=signer_for(),
                accepted_event_signers=policy.transition_signer_identities,
                accepted_authority_signers=policy.authority_signer_identities,
                signature_verifier=verify_signature,
            )
            events.append(review)
            snapshots.append(review_snapshot)
            reviewed_again = publication.advance_current_terminal(
                authority.canonical_json_bytes(bundle),
                signer_identity=SIGNER,
                signer=signer_for(),
            )
            self.assertEqual(
                reviewed_again.lifecycle.state["unrestricted_review_count"], 1
            )
            self.assertEqual(
                {
                    key: value
                    for key, value in reviewed_again.lifecycle.state.items()
                    if key != "unrestricted_review_count"
                },
                {
                    key: value
                    for key, value in expected.items()
                    if key != "unrestricted_review_count"
                },
            )

            second_review = authority.create_transition_authorization(
                event_id="prohibited-second-review",
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                lifecycle_id=chain.lifecycle_id,
                pull_request=PR,
                predecessor_authority_digest=reviewed_again.lifecycle.authority_digest,
                predecessor_head_sha=reviewed_again.lifecycle.head_sha,
                resulting_head_sha=reviewed_again.lifecycle.head_sha,
                transition_kind="UNRESTRICTED_REVIEW_CONSUMED",
                replacement_pull_request=None,
                initialization_evidence_digest=chain.initialization[
                    "initialization_digest"
                ],
                signer_identity=SIGNER,
                signer=signer_for(),
            )
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError, "budget is exhausted"
            ):
                authority.issue_lifecycle_authority(
                    predecessor_chain=snapshots,
                    transition_authorizations=events,
                    authorization=second_review,
                    signer_identity=SIGNER,
                    authority_signer=signer_for(),
                    accepted_event_signers=policy.transition_signer_identities,
                    accepted_authority_signers=policy.authority_signer_identities,
                    signature_verifier=verify_signature,
                )
            self.assertEqual(self.remote_tip(), reviewed_again.publication_oid)

    def test_correction_executor_rejects_stale_replay_mutation_and_result_input(
        self,
    ) -> None:
        _chain, reviewed, correction, policy = self.correction_fixture()
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )
        real_advance = publication.advance_current_terminal

        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
            ),
            patch.object(
                publication, "_observe_pre_enrollment_pull_request",
                return_value={
                    "repository": REPOSITORY, "pull_request": PR,
                    "state": "OPEN", "draft": True, "head_sha": reviewed.lifecycle.head_sha,
                },
            ),
            patch.object(
                publication,
                "advance_current_terminal",
                wraps=real_advance,
            ) as advance,
        ):
            for field, value in (
                ("current_publication_oid", HEADS[8]),
                ("current_publication_digest", "8" * 64),
                ("invalid_event_id", "review:substituted"),
                ("invalid_event_digest", "8" * 64),
                ("repository", "Other/repository"),
                ("delivery_issue", ISSUE + 1),
                ("pull_request", PR + 1),
                ("lifecycle_id", "lifecycle:" + "8" * 64),
                ("resulting_head_sha", HEADS[8]),
            ):
                with self.subTest(field=field), self.assertRaises(
                    (authority.LifecycleAuthorityError,
                     publication.LifecyclePublicationError)
                ):
                    changed = copy.deepcopy(correction)
                    changed[field] = value
                    execution.execute_invalid_review_consumption_correction(
                        self.resign_correction(changed), signers
                    )
                self.assertEqual(advance.call_count, 0)

            with self.assertRaises(TypeError):
                execution.execute_invalid_review_consumption_correction(
                    correction, signers, resulting_state={"unrestricted_review_count": 0}
                )
            self.assertEqual(advance.call_count, 0)

            corrected = execution.execute_invalid_review_consumption_correction(
                correction, signers
            )
            self.assertEqual(advance.call_count, 1)

            with self.assertRaises(publication.LifecyclePublicationError):
                execution.execute_invalid_review_consumption_correction(
                    correction, signers
                )
            self.assertEqual(advance.call_count, 1)
            self.assertEqual(self.remote_tip(), corrected.publication_oid)
            self.assertNotEqual(reviewed.publication_oid, corrected.publication_oid)

    def test_direct_correction_publication_reauthenticates_eligibility(self) -> None:
        chain, reviewed, correction, policy = self.correction_fixture()
        snapshot = authority.issue_lifecycle_authority(
            predecessor_chain=chain.authorities,
            transition_authorizations=chain.events,
            authorization=correction,
            signer_identity=SIGNER,
            authority_signer=signer_for(),
            accepted_event_signers=policy.transition_signer_identities,
            accepted_authority_signers=policy.authority_signer_identities,
            signature_verifier=verify_signature,
        )
        chain.events.append(correction)
        chain.authorities.append(snapshot)

        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication,
                "verify_invalid_review_consumption_correction",
                side_effect=publication.LifecyclePublicationError(
                    "live correction eligibility changed"
                ),
            ) as eligibility,
            self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "live correction eligibility changed",
            ),
        ):
            publication.advance_current_terminal(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )

        eligibility.assert_called_once_with(correction)
        self.assertEqual(self.remote_tip(), reviewed.publication_oid)

    def test_correction_executor_fails_closed_on_publication_cas_race(self) -> None:
        chain, reviewed, correction, policy = self.correction_fixture()
        signers = execution.SigningAuthorities(
            SIGNER, signer_for(), SIGNER, signer_for(), SIGNER, signer_for()
        )
        real_cas = publication._cas_remote_ref
        race_oid: str | None = None

        def lose_race(
            root: Path,
            remote_url: str,
            branch: str,
            new_oid: str,
            old_oid: str | None,
            **kwargs: Any,
        ) -> None:
            nonlocal race_oid
            self.assertEqual(old_oid, reviewed.publication_oid)
            publication._observe_remote_current_once(self.probe, str(self.remote), BRANCH)
            race_oid = publication._write_publication_object(
                self.probe, b"concurrent journal successor", old_oid
            )
            real_cas(self.probe, str(self.remote), BRANCH, race_oid, old_oid)
            real_cas(
                root, remote_url, branch, new_oid, old_oid,
                credential_environment=kwargs.get("credential_environment"),
            )

        with (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=policy
            ),
            patch.object(
                publication, "_resolve_delivery_head_tree", return_value=HEADS[9]
            ),
            patch.object(
                publication, "_observe_pre_enrollment_pull_request",
                return_value={
                    "repository": REPOSITORY, "pull_request": PR,
                    "state": "OPEN", "draft": True, "head_sha": chain.head,
                },
            ),
            patch.object(publication, "_cas_remote_ref", side_effect=lose_race),
        ):
            with self.assertRaisesRegex(
                publication.LifecyclePublicationError, "compare-and-swap"
            ):
                execution.execute_invalid_review_consumption_correction(
                    correction, signers
                )
        self.assertIsNotNone(race_oid)
        self.assertEqual(self.remote_tip(), race_oid)
        self.assertNotEqual(self.remote_tip(), reviewed.publication_oid)

    def exact_adoption_current(
        self,
        *,
        ordinary_provider_head: str | None = None,
        historical_provider_head: str = HEADS[0],
    ) -> tuple[
        publication.VerifiedLifecyclePublication,
        dict[str, Any],
        Any,
    ]:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
        )
        state["ready_history"] = [{
            "sequence": 1,
            "transition_kind": "DRAFT_TO_READY",
            "observation_digest": "6" * 64,
        }]
        lifecycle = authority.VerifiedLifecycleAuthority(
            authority_digest="7" * 64,
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle_id="lifecycle-adoption:" + "8" * 64,
            initialization_evidence_digest="8" * 64,
            pull_request=PR,
            head_sha=HEADS[2],
            state=state,
            authority_signer_identity=LEGACY_SIGNER,
            historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
            legacy_adoption_checkpoint_digest="9" * 64,
            tree_sha=HEADS[3],
        )
        loss_admission = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "delivery_issue": ISSUE,
            "pull_request": PR,
            "head_sha": HEADS[2],
        }
        proof = {
            "repository": REPOSITORY,
            "delivery_issue": ISSUE,
            "pull_request": PR,
            "head_sha": HEADS[2],
            "lifecycle_id": lifecycle.lifecycle_id,
            "validation_evidence_loss_admission": loss_admission,
        }
        events: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []
        if ordinary_provider_head is not None:
            before = copy.deepcopy(state)
            before["remediation_cycle_count"] = 1
            event = {
                "transition_kind": "REMEDIATION_COMPLETED",
                "repository": REPOSITORY,
                "delivery_issue": ISSUE,
                "pull_request": PR,
                "lifecycle_id": lifecycle.lifecycle_id,
                "predecessor_head_sha": ordinary_provider_head,
                "resulting_head_sha": HEADS[2],
                "event_digest": "a" * 64,
            }
            events.append(event)
            snapshots.append({
                "predecessor_head_sha": ordinary_provider_head,
                "head_sha": HEADS[2],
                "state_before": before,
                "state_after": copy.deepcopy(state),
            })
        bundle = {
            "schema_version": "1.0",
            "kind": "SECPAL_EXACT_STATE_ADOPTION_PUBLICATION_EVIDENCE",
            "domain": "secpal.exact-state-adoption-publication-evidence/v1",
            "enrollment_mode": "EXACT_STATE_ADOPTION",
            "exact_state_adoption_proof": proof,
            "transition_authorizations": events,
            "authority_chain": snapshots,
        }
        current = publication.VerifiedLifecyclePublication(
            publication_oid="b" * 40,
            publication_digest="c" * 64,
            publication_branch=BRANCH,
            journal_predecessor_oid="d" * 40,
            predecessor_publication_oid=None,
            lifecycle=lifecycle,
            serialized_lifecycle_evidence=authority.canonical_json_bytes(bundle),
        )
        historical = loss.HistoricalProviderBinding(
            repository=REPOSITORY,
            pull_request=PR,
            current_head_sha=HEADS[2],
            provider_head_sha=historical_provider_head,
            summary_digest="e" * 64,
        )
        return current, proof, historical

    def test_ready_source_provider_binding_derives_attested_ready_predecessor(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        chain.append("UNRESTRICTED_REVIEW_CONSUMED")
        chain.append("REMEDIATION_COMPLETED", head=HEADS[1])
        chain.append("DRAFT_TO_READY")
        chain.append("REMEDIATION_COMPLETED", head=HEADS[2])
        _, current = self.enroll(chain)

        binding = publication.derive_ready_source_recovery_provider_binding(
            current
        )

        self.assertEqual(binding.repository, REPOSITORY)
        self.assertEqual(binding.delivery_issue, ISSUE)
        self.assertEqual(binding.pull_request, PR)
        self.assertEqual(binding.current_head_sha, HEADS[2])
        self.assertEqual(binding.provider_head_sha, HEADS[1])
        self.assertEqual(
            publication.ready_source_recovery_provider_head(
                binding,
                repository=REPOSITORY,
                pull_request=PR,
                current_head_sha=HEADS[2],
            ),
            HEADS[1],
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "stale or substituted"
        ):
            publication.ready_source_recovery_provider_head(
                replace(binding, provider_head_sha=HEADS[0]),
                repository=REPOSITORY,
                pull_request=PR,
                current_head_sha=HEADS[2],
            )

    def test_ready_source_provider_binding_accepts_native_publication_wrapper(
        self,
    ) -> None:
        chain = Chain(ISSUE + 10)
        chain.append("INITIALIZED_DRAFT")
        chain.append("UNRESTRICTED_REVIEW_CONSUMED")
        chain.append("DRAFT_TO_READY")
        chain.append("REMEDIATION_COMPLETED", head=HEADS[1])
        serialized = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )
        verified = authority._verify_lifecycle_authority_for_journal(
            serialized,
            admitted_initialization=chain.initialization,
        )
        current = publication.VerifiedLifecyclePublication(
            "1" * 40,
            "2" * 64,
            BRANCH,
            "3" * 40,
            "4" * 40,
            verified,
            serialized,
        )

        binding = publication.derive_ready_source_recovery_provider_binding(current)

        self.assertEqual(binding.provider_head_sha, HEADS[0])

    def test_ready_source_provider_binding_rejects_nonexact_lifecycle_shapes(self) -> None:
        missing_remediation = Chain(ISSUE + 1)
        missing_remediation.append("INITIALIZED_DRAFT")
        missing_remediation.append("UNRESTRICTED_REVIEW_CONSUMED")
        missing_remediation.append("DRAFT_TO_READY")
        _, current = self.enroll(missing_remediation)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "remediation lineage"
        ):
            publication.derive_ready_source_recovery_provider_binding(current)

        not_ready = Chain(ISSUE + 2)
        not_ready.append("INITIALIZED_DRAFT")
        not_ready.append("UNRESTRICTED_REVIEW_CONSUMED")
        not_ready.append("REMEDIATION_COMPLETED", head=HEADS[1])
        _, current = self.enroll(not_ready)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "remediation lineage"
        ):
            publication.derive_ready_source_recovery_provider_binding(current)

        valid = Chain(ISSUE + 3)
        valid.append("INITIALIZED_DRAFT")
        valid.append("UNRESTRICTED_REVIEW_CONSUMED")
        valid.append("DRAFT_TO_READY")
        valid.append("REMEDIATION_COMPLETED", head=HEADS[1])
        valid.append("REMEDIATION_COMPLETED", head=HEADS[2])
        _, current = self.enroll(valid)
        binding = publication.derive_ready_source_recovery_provider_binding(current)
        self.assertEqual(binding.provider_head_sha, HEADS[0])
        self.assertEqual(len(binding.remediation_event_digests), 2)

        raw = json.loads(current.serialized_lifecycle_evidence)
        lifecycle = raw.get("lifecycle_evidence", raw)
        lifecycle["transition_authorizations"][-1][
            "predecessor_head_sha"
        ] = HEADS[9]
        substituted = replace(
            current,
            serialized_lifecycle_evidence=fast_path.canonical_json_bytes(raw),
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "lifecycle evidence is invalid"
        ):
            publication.derive_ready_source_recovery_provider_binding(substituted)

        with self.assertRaises(authority.LifecycleAuthorityError):
            valid.append("REMEDIATION_COMPLETED", head=HEADS[3])
        with self.assertRaises(authority.LifecycleAuthorityError):
            valid.append("UNRESTRICTED_REVIEW_CONSUMED")

    def test_exact_adoption_v11_derives_historical_provider_binding(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, proof, historical = self.exact_adoption_current()
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=current.lifecycle,
        ) as verify_adoption, patch.object(
            loss,
            "authenticate_historical_provider_binding",
            return_value=historical,
        ) as verify_loss:
            binding = publication.derive_ready_source_recovery_provider_binding(
                current
            )

        self.assertEqual(binding.provider_head_sha, historical.provider_head_sha)
        self.assertEqual(binding.remediation_event_digests, ())
        self.assertEqual(
            binding.provider_binding_sources,
            (publication.EXACT_ADOPTION_V1_1_HISTORICAL_PROVIDER_BINDING,),
        )
        self.assertIs(binding.historical_provider_binding, historical)
        verify_adoption.assert_called_once_with(proof)
        verify_loss.assert_called_once_with(
            proof["validation_evidence_loss_admission"]
        )

    def test_exact_adoption_requires_authenticated_v11_loss_provenance(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, proof, _historical = self.exact_adoption_current()
        del proof["validation_evidence_loss_admission"]
        parsed = json.loads(current.serialized_lifecycle_evidence)
        parsed["exact_state_adoption_proof"] = proof
        current = replace(
            current,
            serialized_lifecycle_evidence=authority.canonical_json_bytes(parsed),
        )
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=current.lifecycle,
        ), patch.object(
            loss, "authenticate_historical_provider_binding"
        ) as verify_loss, self.assertRaisesRegex(
            publication.LifecyclePublicationError, "remediation lineage"
        ):
            publication.derive_ready_source_recovery_provider_binding(current)
        verify_loss.assert_not_called()

        current, _proof, _historical = self.exact_adoption_current()
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=current.lifecycle,
        ), patch.object(
            loss,
            "authenticate_historical_provider_binding",
            side_effect=authority.LifecycleAuthorityError(
                "historical provider binding requires v1.1 loss provenance"
            ),
        ), self.assertRaisesRegex(
            publication.LifecyclePublicationError, "v1.1 historical provenance"
        ):
            publication.derive_ready_source_recovery_provider_binding(current)

    def test_exact_adoption_rejects_historical_binding_scope_substitution(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, _proof, historical = self.exact_adoption_current()
        substitutions = (
            replace(historical, repository="Other/project"),
            replace(historical, pull_request=PR + 1),
            replace(historical, current_head_sha=HEADS[3]),
        )
        for substituted in substitutions:
            with self.subTest(substituted=substituted), patch.object(
                authority,
                "_verify_lifecycle_authority_for_journal",
                return_value=current.lifecycle,
            ), patch.object(
                authority,
                "verify_exact_state_adoption_proof",
                return_value=current.lifecycle,
            ), patch.object(
                loss,
                "authenticate_historical_provider_binding",
                return_value=substituted,
            ), self.assertRaisesRegex(
                publication.LifecyclePublicationError,
                "historical provenance is invalid",
            ):
                publication.derive_ready_source_recovery_provider_binding(current)

    def test_exact_adoption_v11_rejects_conflicting_dual_derivation(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, _proof, historical = self.exact_adoption_current(
            ordinary_provider_head=HEADS[1], historical_provider_head=HEADS[0]
        )
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=current.lifecycle,
        ), patch.object(
            loss,
            "authenticate_historical_provider_binding",
            return_value=historical,
        ), self.assertRaisesRegex(
            publication.LifecyclePublicationError, "provider heads conflict"
        ):
            publication.derive_ready_source_recovery_provider_binding(current)

    def test_exact_adoption_successor_preserves_ordinary_provider_derivation(
        self,
    ) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, proof, _historical = self.exact_adoption_current(
            ordinary_provider_head=HEADS[1]
        )
        proof["head_sha"] = HEADS[1]
        proof["validation_evidence_loss_admission"]["head_sha"] = HEADS[1]
        parsed = json.loads(current.serialized_lifecycle_evidence)
        parsed["exact_state_adoption_proof"] = proof
        current = replace(
            current,
            serialized_lifecycle_evidence=authority.canonical_json_bytes(parsed),
        )
        adoption = replace(
            current.lifecycle,
            authority_digest="f" * 64,
            head_sha=HEADS[1],
        )
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=adoption,
        ), patch.object(
            loss, "authenticate_historical_provider_binding"
        ) as verify_loss:
            binding = publication.derive_ready_source_recovery_provider_binding(
                current
            )

        self.assertEqual(binding.provider_head_sha, HEADS[1])
        self.assertEqual(
            binding.provider_binding_sources,
            (publication.ORDINARY_REMEDIATION_SUFFIX,),
        )
        verify_loss.assert_not_called()

    def test_exact_adoption_matching_dual_derivation_is_deterministic(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, _proof, historical = self.exact_adoption_current(
            ordinary_provider_head=HEADS[1], historical_provider_head=HEADS[1]
        )
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=current.lifecycle,
        ), patch.object(
            loss,
            "authenticate_historical_provider_binding",
            return_value=historical,
        ):
            binding = publication.derive_ready_source_recovery_provider_binding(
                current
            )

        self.assertEqual(binding.provider_head_sha, HEADS[1])
        self.assertEqual(
            binding.provider_binding_sources,
            (
                publication.ORDINARY_REMEDIATION_SUFFIX,
                publication.EXACT_ADOPTION_V1_1_HISTORICAL_PROVIDER_BINDING,
            ),
        )

    def test_exact_adoption_provider_binding_reauthenticates_before_use(self) -> None:
        from scripts.secpal_pr_review import validation_evidence_loss as loss

        current, _proof, historical = self.exact_adoption_current()
        with patch.object(
            authority,
            "_verify_lifecycle_authority_for_journal",
            return_value=current.lifecycle,
        ), patch.object(
            authority,
            "verify_exact_state_adoption_proof",
            return_value=current.lifecycle,
        ), patch.object(
            loss,
            "authenticate_historical_provider_binding",
            return_value=historical,
        ):
            binding = publication.derive_ready_source_recovery_provider_binding(
                current
            )
            with patch.object(
                publication,
                "verify_current_lifecycle_authority",
                return_value=current,
            ):
                self.assertEqual(
                    binding.provider_head(
                        repository=REPOSITORY,
                        pull_request=PR,
                        current_head_sha=HEADS[2],
                    ),
                    historical.provider_head_sha,
                )
                with self.assertRaisesRegex(
                    publication.LifecyclePublicationError,
                    "stale or substituted",
                ):
                    replace(
                        binding, provider_head_sha=HEADS[1]
                    ).provider_head(
                        repository=REPOSITORY,
                        pull_request=PR,
                        current_head_sha=HEADS[2],
                    )

    def test_pre_enrollment_absence_is_bound_to_the_observed_protected_tip(self) -> None:
        absence = publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)
        self.assertEqual(absence.repository, REPOSITORY)
        self.assertEqual(absence.delivery_issue, ISSUE)
        self.assertEqual(absence.publication_branch, BRANCH)
        self.assertIsNone(absence.observed_tip_oid)
        self.assertRegex(absence.evidence_digest, r"^[0-9a-f]{64}$")

    def test_pre_enrollment_delivery_genesis_requires_typed_live_pr_head(self) -> None:
        admission = SimpleNamespace(
            subtype="PRE_ENROLLMENT_DRAFT_INTEGRATION_SOURCE",
            purpose="PRE_ENROLLMENT_IMPLEMENTATION_BOOTSTRAP",
            delivery_issue=ISSUE,
            pull_request=PR,
        )
        policy = replace(
            self.policy, bootstrap_source_admissions=(admission,)
        )
        ordinary = Chain().initialization
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "typed integrated head"
        ):
            publication._verify_pre_enrollment_genesis_boundary(policy, ordinary)

        typed = copy.deepcopy(ordinary)
        typed["schema_version"] = "1.1"
        typed["initial_head_proof"] = {
            "kind": "AUTHENTICATED_PRE_ENROLLMENT_DRAFT_INTEGRATION_HEAD"
        }
        with patch.object(
            publication,
            "_observe_pre_enrollment_pull_request",
            return_value={
                "repository": REPOSITORY, "pull_request": PR,
                "state": "OPEN", "draft": True,
                "head_sha": typed["initial_head_sha"],
            },
        ):
            publication._verify_pre_enrollment_genesis_boundary(policy, typed)

        with patch.object(
            publication,
            "_observe_pre_enrollment_pull_request",
            return_value={
                "repository": REPOSITORY, "pull_request": PR,
                "state": "OPEN", "draft": True, "head_sha": "f" * 40,
            },
        ), self.assertRaisesRegex(
            publication.LifecyclePublicationError, "live PR head"
        ):
            publication._verify_pre_enrollment_genesis_boundary(policy, typed)

    def test_pre_enrollment_absence_rejects_existing_native_genesis(self) -> None:
        chain = Chain()
        chain.append("INITIALIZED_DRAFT")
        publication.admit_native_genesis(
            chain.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "already has native genesis or CURRENT",
        ):
            publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)

    def test_pre_enrollment_absence_accepts_signed_unrelated_modern_history(self) -> None:
        other_issue = ISSUE + 1
        fields = {
            "schema_version": publication.SCHEMA_VERSION,
            "kind": publication.PUBLICATION_KIND,
            "domain": publication.PUBLICATION_DOMAIN,
            "operation": "ENROLL_EXISTING_LIFECYCLE",
            "repository": REPOSITORY,
            "delivery_issue": other_issue,
            "lifecycle_id": "lifecycle:unrelated-exact-adoption",
            "initialization_evidence_digest": "1" * 64,
            "pull_request": PR + 1,
            "head_sha": HEADS[1],
            "terminal_authority_digest": "2" * 64,
            "historical_proof_mode": "exact_state_adoption",
            "legacy_adoption_checkpoint_digest": None,
            "lifecycle_evidence": {
                "kind": "SECPAL_EXACT_STATE_ADOPTION_EVIDENCE",
                "proof_version": "3.0",
            },
            "lifecycle_evidence_digest": "",
            "publication_branch": BRANCH,
            "journal_predecessor_oid": None,
            "predecessor_publication_oid": None,
            "predecessor_publication_digest": None,
            "predecessor_terminal_authority_digest": None,
            "signer_identity": SIGNER,
        }
        evidence_raw = authority.canonical_json_bytes(fields["lifecycle_evidence"])
        fields["lifecycle_evidence_digest"] = hashlib.sha256(evidence_raw).hexdigest()
        raw = publication._sign_publication(fields, signer_for())
        oid = publication._write_publication_object(self.probe, raw, None)
        publication._cas_remote_ref(self.probe, str(self.remote), BRANCH, oid, None)

        absence = publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)
        self.assertEqual(absence.observed_tip_oid, oid)
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "already has native genesis or CURRENT",
        ):
            publication.verify_pre_enrollment_absence(REPOSITORY, other_issue)

    def test_pre_enrollment_absence_rejects_corrupt_unrelated_publication(self) -> None:
        fields = {
            "schema_version": publication.SCHEMA_VERSION,
            "kind": publication.PUBLICATION_KIND,
            "domain": publication.PUBLICATION_DOMAIN,
            "operation": "ENROLL_EXISTING_LIFECYCLE",
            "repository": REPOSITORY,
            "delivery_issue": ISSUE + 1,
            "lifecycle_id": "lifecycle:corrupt",
            "initialization_evidence_digest": "1" * 64,
            "pull_request": PR + 1,
            "head_sha": HEADS[1],
            "terminal_authority_digest": "2" * 64,
            "historical_proof_mode": "exact_state_adoption",
            "legacy_adoption_checkpoint_digest": None,
            "lifecycle_evidence": {"kind": "corrupt"},
            "lifecycle_evidence_digest": "3" * 64,
            "publication_branch": BRANCH,
            "journal_predecessor_oid": None,
            "predecessor_publication_oid": None,
            "predecessor_publication_digest": None,
            "predecessor_terminal_authority_digest": None,
            "signer_identity": SIGNER,
        }
        raw = publication._sign_publication(fields, signer_for())
        oid = publication._write_publication_object(self.probe, raw, None)
        publication._cas_remote_ref(self.probe, str(self.remote), BRANCH, oid, None)

        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "lifecycle-evidence digest mismatch",
        ):
            publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)

    def test_pre_enrollment_absence_rejects_unknown_proof_mode(self) -> None:
        fields = {
            "schema_version": publication.SCHEMA_VERSION,
            "kind": publication.PUBLICATION_KIND,
            "domain": publication.PUBLICATION_DOMAIN,
            "operation": "ENROLL_EXISTING_LIFECYCLE",
            "repository": REPOSITORY,
            "delivery_issue": ISSUE + 1,
            "lifecycle_id": "lifecycle:unknown",
            "initialization_evidence_digest": "1" * 64,
            "pull_request": PR + 1,
            "head_sha": HEADS[1],
            "terminal_authority_digest": "2" * 64,
            "historical_proof_mode": "future_unreviewed_mode",
            "legacy_adoption_checkpoint_digest": None,
            "lifecycle_evidence": {"kind": "unknown"},
            "lifecycle_evidence_digest": "",
            "publication_branch": BRANCH,
            "journal_predecessor_oid": None,
            "predecessor_publication_oid": None,
            "predecessor_publication_digest": None,
            "predecessor_terminal_authority_digest": None,
            "signer_identity": SIGNER,
        }
        fields["lifecycle_evidence_digest"] = hashlib.sha256(
            authority.canonical_json_bytes(fields["lifecycle_evidence"])
        ).hexdigest()
        raw = publication._sign_publication(fields, signer_for())
        oid = publication._write_publication_object(self.probe, raw, None)
        publication._cas_remote_ref(self.probe, str(self.remote), BRANCH, oid, None)

        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "historical-proof mode is invalid",
        ):
            publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)

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

    def test_pre_persistence_ready_recovery_is_explicit_published_and_one_use(self) -> None:
        chain, enrolled = self.enroll()
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PR,
            head_sha=chain.head,
            base_ref="main",
            base_sha=HEADS[9],
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [{
                    "node_id": "THREAD_RECOVERY",
                    "is_resolved": True,
                    "is_outdated": False,
                    "comments": [{
                        "node_id": "COMMENT_RECOVERY",
                        "body_digest": hashlib.sha256(
                            b"technically blocking authentication bypass"
                        ).hexdigest(),
                        "actor": {
                            "login": "reviewer", "node_id": "ACTOR_RECOVERY",
                            "database_id": 17,
                        },
                        "reply_to_id": None,
                        "reactions": [],
                    }],
                }],
            },
        )
        registry = {
            "manual_gates": [],
            "validation": [],
            "limits": {"maximum_items": 10000},
        }
        fresh_receipt = fast_path.create_validation_receipt(
            repository=REPOSITORY,
            head_sha=chain.head,
            validated_tree_sha=HEADS[8],
            registry=registry,
            command_set=[],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
        )
        commit = {
            "oid": chain.head,
            "source": "USER",
            "signer_identity": SIGNER,
            "local_signature": {
                "verified": True,
                "state": "valid",
                "format": "ssh",
            },
            "github_verification": {"verified": True, "reason": "valid"},
        }
        with patch.object(
            authority,
            "_load_delivery_signature_policy",
            return_value={
                "accepted_formats": ["ssh"],
                "require_github_verified": True,
            },
        ):
            safety = fast_path.derive_ready_source_recovery_safety_facts(
                tooling_authority_main="f" * 40,
                repository=REPOSITORY,
                pull_request_number=PR,
                head_sha=chain.head,
                tree_sha=HEADS[8],
                parent_shas=[HEADS[7]],
                expected_base_ref="main",
                expected_base_sha=HEADS[9],
                reviewed_state=reviewed,
                review_decision="APPROVED",
                feedback_findings=[{
                    "finding_id": "signed-resolved-safe-decision",
                    "thread_id": "THREAD_RECOVERY",
                    "sources": [{
                        "kind": "THREAD_COMMENT",
                        "node_id": "COMMENT_RECOVERY",
                        "digest": reviewed.feedback["threads"][0]["comments"][0][
                            "body_digest"
                        ],
                    }],
                    "classification": "INFORMATIONAL",
                    "disposition": "NON_ACTIONABLE",
                    "evidence_digest": "8" * 64,
                    "technically_blocking": False,
                }],
                fresh_validation_receipt=fresh_receipt,
                registry=registry,
                command_set=[],
            )
        self.assertNotIn("signature", safety)
        self.assertFalse(hasattr(fast_path, "is_verified_ready_source_recovery_safety"))
        actions = load_actions()
        entry = copy.deepcopy(actions.select_repository(
            actions.load_registry(), REPOSITORY
        ))
        entry["manual_gates"] = []
        observation = reviewed.to_dict()
        observation["review_decision"] = "APPROVED"
        observation["is_draft"] = False
        gateway = SimpleNamespace(
            observe_stable_feedback=lambda *_: observation,
            observe_ready_source_recovery_approval_policy=lambda *_: True,
            observe_ready_source_recovery_delivery=lambda *_: commit,
        )
        harness_path = actions.READY_SOURCE_RECOVERY_CURRENT_SAFETY_PATH
        safety_command = {
            "argv": ["python3", harness_path], "working_directory": ".",
            "purpose": "Validate Ready-source recovery current safety",
        }
        current_safety_profile = {
            "schema_version": "1.0",
            "policy": "READY_SOURCE_RECOVERY_CURRENT_SAFETY",
            "harness": [{
                "path": harness_path, "mode": "100644",
                "blob_oid": "e" * 40, "size": 1,
            }],
            "validation_command_set": [safety_command],
            "validation_command_set_digest": authority.digest_json([safety_command]),
            "timeout_seconds": 120,
            "required_invariants": list(
                actions.READY_SOURCE_RECOVERY_CURRENT_SAFETY_INVARIANTS
            ),
            "validation_results": [{
                "command_digest": authority.digest_json(safety_command),
                "exit_status": 0, "successful": True,
            }],
        }
        with (
            patch.object(
                actions, "_ready_source_recovery_current_safety_profile",
                return_value=current_safety_profile,
            ),
            patch.object(
                actions, "_attestation_local_state",
                side_effect=[(chain.head, ""), (chain.head, "")],
            ),
            patch.object(
                actions, "_run_attestation_git",
                return_value=SimpleNamespace(stdout=HEADS[8]),
            ),
            patch.object(
                actions, "_validated_commit_parent", return_value=HEADS[7]
            ),
            patch.object(
                authority, "_load_delivery_signature_policy",
                return_value={
                    "accepted_formats": ["ssh"],
                    "require_github_verified": True,
                },
            ),
        ):
            recovery = actions._issue_ready_source_recovery_authorization(
                repository=REPOSITORY, delivery_issue=ISSUE,
                pull_request_number=PR, expected_head_sha=chain.head,
                repository_root=Path(self.directory.name),
                feedback_findings=safety["feedback_findings"],
                manual_gate_evidence=[],
                historical_validation_receipt_digest=(
                    chain.initialization["validation_receipt_digest"]
                ),
                historical_final_attestation_digest=(
                    chain.initialization["final_attestation_digest"]
                ),
                recovery_user_authorization=b"authorization",
                expected_commit_signer={
                    "kind": "SSH_PRINCIPAL", "identity": SIGNER,
                },
                signer_identity=SIGNER, signer=signer_for(),
                _policy_loader=lambda _: ("f" * 40, entry),
                _gateway_factory=lambda *_: gateway,
                _validation_runner=lambda *_: actions.RegisteredValidationResult(),
                _issuer_source_verifier=lambda _: None,
                _current_lifecycle_loader=lambda *_: enrolled,
                _authorization_factory=(
                    authority._sign_ready_source_recovery_authorization
                ),
                _recovery_user_authorization_verifier=lambda *_: {
                    "authorization_id": "ready-source-recovery-1",
                    "authorization_digest": "7" * 64,
                },
            )

        with self.assertRaises((
            authority.LifecycleAuthorityError,
            publication.LifecyclePublicationError,
        )):
            publication.publish_ready_source_recovery(
                safety, signer_identity=SIGNER, signer=signer_for()
            )

        tampered = copy.deepcopy(recovery)
        tampered_facts = tampered["recovery_safety_facts"]
        tampered_facts["feedback_findings"][0]["evidence_digest"] = "9" * 64
        tampered_facts["feedback_assessment_digest"] = fast_path.digest_json({
            "review_decision": tampered_facts["review_decision"],
            "approval_required": tampered_facts["approval_required"],
            "findings": tampered_facts["feedback_findings"],
        })
        unsigned_facts = {
            key: copy.deepcopy(value)
            for key, value in tampered_facts.items()
            if key != "safety_facts_digest"
        }
        tampered_facts["safety_facts_digest"] = fast_path.digest_json(
            unsigned_facts
        )
        tampered["feedback_assessment_digest"] = fast_path.digest_json({
            "review_decision": tampered_facts["review_decision"],
            "findings": tampered_facts["feedback_findings"],
        })
        tampered["authorization_digest"] = authority.digest_json({
            key: copy.deepcopy(value)
            for key, value in tampered.items()
            if key != "authorization_digest"
        })
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_ready_source_recovery_authorization(
                tampered, current_lifecycle=enrolled.lifecycle,
                current_publication_oid=enrolled.publication_oid,
                current_publication_digest=enrolled.publication_digest,
            )

        wrong_signer = copy.deepcopy(recovery)
        wrong_signer["signer_identity"] = OTHER_SIGNER
        wrong_signer["signature"] = signer_for(OTHER_SIGNER)(
            authority.canonical_json_bytes(authority._unsigned(
                wrong_signer, "authorization_digest", "signature"
            )),
            authority.READY_SOURCE_RECOVERY_AUTHORIZATION_DOMAIN,
        )
        wrong_signer["authorization_digest"] = authority.digest_json({
            key: copy.deepcopy(value)
            for key, value in wrong_signer.items()
            if key != "authorization_digest"
        })
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_ready_source_recovery_authorization(
                wrong_signer, current_lifecycle=enrolled.lifecycle,
                current_publication_oid=enrolled.publication_oid,
                current_publication_digest=enrolled.publication_digest,
            )

        recovered = publication.publish_ready_source_recovery(
            recovery,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        tip = self.remote_tip()
        verified = publication.verify_current_ready_source_recovery(
            REPOSITORY, ISSUE
        )

        self.assertEqual(verified.publication_oid, recovered.publication_oid)
        self.assertEqual(verified.authorization_id, "ready-source-recovery-1")
        self.assertEqual(verified.head_sha, chain.head)
        self.assertEqual(verified.tree_sha, HEADS[8])
        self.assertEqual(
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
            .publication_oid,
            enrolled.publication_oid,
        )
        unrelated_issue = ISSUE + 1
        absence = publication.verify_pre_enrollment_absence(
            REPOSITORY, unrelated_issue
        )
        self.assertEqual(absence.observed_tip_oid, recovered.publication_oid)
        publication.require_unenrolled_delivery(REPOSITORY, unrelated_issue)
        publication._observe_remote_current_once(
            self.probe, str(self.remote), BRANCH
        )
        projected_publications, projected_admissions = (
            publication._walk_journal_identity_projection(
                self.probe, recovered.publication_oid, BRANCH
            )
        )
        self.assertEqual(projected_publications, {(REPOSITORY, ISSUE)})
        self.assertEqual(projected_admissions, set())

        base_recovery_fields = publication._ready_source_recovery_fields(
            recovery,
            publication_branch=BRANCH,
            journal_predecessor_oid=enrolled.publication_oid,
            signer_identity=SIGNER,
        )

        def assert_rejected_by_both(raw: bytes, parent: str | None) -> None:
            object_oid = publication._write_publication_object(
                self.probe, raw, parent
            )
            with self.assertRaises((
                authority.LifecycleAuthorityError,
                publication.LifecyclePublicationError,
            )):
                publication._walk_journal(
                    self.probe, object_oid, BRANCH, include_recoveries=True
                )
            with self.assertRaises((
                authority.LifecycleAuthorityError,
                publication.LifecyclePublicationError,
            )):
                publication._walk_journal_identity_projection(
                    self.probe, object_oid, BRANCH
                )

        malformed_kind = copy.deepcopy(base_recovery_fields)
        malformed_kind["kind"] = []
        malformed_kind_oid = publication._write_publication_object(
            self.probe,
            authority.canonical_json_bytes(malformed_kind),
            enrolled.publication_oid,
        )
        for walker in (
            publication._walk_journal,
            publication._walk_journal_identity_projection,
        ):
            with self.assertRaises(publication.LifecyclePublicationError):
                walker(
                    self.probe, malformed_kind_oid, BRANCH
                )

        field_mutations = {
            "wrong domain": ("domain", "secpal.lifecycle-authority-publication/v1"),
            "wrong branch": ("publication_branch", "refs/heads/other"),
            "wrong repository": ("repository", "SecPal/contracts"),
            "wrong issue": ("delivery_issue", ISSUE + 1),
            "invalid authorization binding": (
                "recovery_authorization_digest", "0" * 64
            ),
            "invalid CURRENT reference": ("current_publication_oid", HEADS[9]),
        }
        for name, (field, value) in field_mutations.items():
            with self.subTest(recovery_projection=name):
                changed = copy.deepcopy(base_recovery_fields)
                changed[field] = value
                assert_rejected_by_both(
                    publication._sign_ready_source_recovery(
                        changed, signer_for()
                    ),
                    enrolled.publication_oid,
                )

        for field in ("repository", "delivery_issue"):
            with self.subTest(recovery_projection=f"unhashable {field}"):
                changed = copy.deepcopy(base_recovery_fields)
                changed[field] = []
                with self.assertRaises(publication.LifecyclePublicationError):
                    publication._walk_journal_identity_projection(
                        self.probe,
                        publication._write_publication_object(
                            self.probe,
                            publication._sign_ready_source_recovery(
                                changed, signer_for()
                            ),
                            enrolled.publication_oid,
                        ),
                        BRANCH,
                    )

        current_raw, current_parent = publication._read_publication_object(
            self.probe, enrolled.publication_oid
        )
        future_current_fields = json.loads(current_raw)
        future_current_fields["lifecycle_evidence"]["proof_version"] = "999.0"
        future_current_fields["lifecycle_evidence_digest"] = hashlib.sha256(
            authority.canonical_json_bytes(
                future_current_fields["lifecycle_evidence"]
            )
        ).hexdigest()
        future_current_fields = {
            key: value for key, value in future_current_fields.items()
            if key not in {"signature", "publication_digest"}
        }
        future_current_raw = publication._sign_publication(
            future_current_fields, signer_for()
        )
        future_current_oid = publication._write_publication_object(
            self.probe, future_current_raw, current_parent
        )
        future_current_document = json.loads(future_current_raw)
        future_authorization_fields = {
            key: copy.deepcopy(value) for key, value in recovery.items()
            if key not in {"signature", "authorization_digest"}
        }
        future_authorization_fields["current_publication_oid"] = (
            future_current_oid
        )
        future_authorization_fields["current_publication_digest"] = (
            future_current_document["publication_digest"]
        )
        future_authorization_signature = authority._normalize_signature(
            signer_for()(
                authority.canonical_json_bytes(future_authorization_fields),
                authority.READY_SOURCE_RECOVERY_AUTHORIZATION_DOMAIN,
            ),
            SIGNER,
        )
        future_authorization_signed = {
            **future_authorization_fields,
            "signature": future_authorization_signature,
        }
        future_authorization = {
            **future_authorization_signed,
            "authorization_digest": authority.digest_json(
                future_authorization_signed
            ),
        }
        future_recovery_fields = publication._ready_source_recovery_fields(
            future_authorization,
            publication_branch=BRANCH,
            journal_predecessor_oid=future_current_oid,
            signer_identity=SIGNER,
        )
        future_recovery_raw = publication._sign_ready_source_recovery(
            future_recovery_fields, signer_for()
        )
        future_recovery_oid = publication._write_publication_object(
            self.probe, future_recovery_raw, future_current_oid
        )
        with self.assertRaises((
            authority.LifecycleAuthorityError,
            publication.LifecyclePublicationError,
        )):
            publication._walk_journal(
                self.probe, future_recovery_oid, BRANCH, include_recoveries=True
            )
        projected, _ = publication._walk_journal_identity_projection(
            self.probe, future_recovery_oid, BRANCH
        )
        self.assertEqual(projected, {(REPOSITORY, ISSUE)})

        valid_raw = publication._sign_ready_source_recovery(
            base_recovery_fields, signer_for()
        )
        unknown_field = json.loads(valid_raw)
        unknown_field["unknown"] = True
        assert_rejected_by_both(
            authority.canonical_json_bytes(unknown_field),
            enrolled.publication_oid,
        )
        missing_field = json.loads(valid_raw)
        del missing_field["tree_sha"]
        assert_rejected_by_both(
            authority.canonical_json_bytes(missing_field),
            enrolled.publication_oid,
        )
        masquerade = copy.deepcopy(base_recovery_fields)
        masquerade["kind"] = publication.PUBLICATION_KIND
        assert_rejected_by_both(
            publication._sign_ready_source_recovery(masquerade, signer_for()),
            enrolled.publication_oid,
        )
        invalid_signature = json.loads(valid_raw)
        invalid_signature["signature"]["value"] = "0" * 64
        invalid_signature["publication_digest"] = authority.digest_json({
            key: copy.deepcopy(value)
            for key, value in invalid_signature.items()
            if key != "publication_digest"
        })
        assert_rejected_by_both(
            authority.canonical_json_bytes(invalid_signature),
            enrolled.publication_oid,
        )
        wrong_predecessor = copy.deepcopy(base_recovery_fields)
        wrong_predecessor["journal_predecessor_oid"] = None
        assert_rejected_by_both(
            publication._sign_ready_source_recovery(
                wrong_predecessor, signer_for()
            ),
            enrolled.publication_oid,
        )
        before_current = copy.deepcopy(base_recovery_fields)
        before_current["journal_predecessor_oid"] = None
        assert_rejected_by_both(
            publication._sign_ready_source_recovery(
                before_current, signer_for()
            ),
            None,
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "already has native genesis or CURRENT",
        ):
            publication.verify_pre_enrollment_absence(REPOSITORY, ISSUE)
        self.assertNotIn("reviewed_state", recovery)
        self.assertNotIn("validation_receipt", recovery)

        repeated = publication.publish_ready_source_recovery(
            recovery,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        self.assertEqual(repeated.publication_oid, recovered.publication_oid)
        self.assertEqual(self.remote_tip(), tip)

        publication._observe_remote_current_once(self.probe, str(self.remote), BRANCH)
        replay_fields = publication._ready_source_recovery_fields(
            recovery,
            publication_branch=BRANCH,
            journal_predecessor_oid=recovered.publication_oid,
            signer_identity=SIGNER,
        )
        replay_raw = publication._sign_ready_source_recovery(
            replay_fields, signer_for()
        )
        replay_oid = publication._write_publication_object(
            self.probe, replay_raw, recovered.publication_oid
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "replayed"
        ):
            publication._walk_journal(
                self.probe, replay_oid, BRANCH, include_recoveries=True
            )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "replayed"
        ):
            publication._walk_journal_identity_projection(
                self.probe, replay_oid, BRANCH
            )

        predecessor_fields = copy.deepcopy(replay_fields)
        predecessor_fields["journal_predecessor_oid"] = enrolled.publication_oid
        predecessor_raw = publication._sign_ready_source_recovery(
            predecessor_fields, signer_for()
        )
        predecessor_oid = publication._write_publication_object(
            self.probe, predecessor_raw, recovered.publication_oid
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "parent binding"
        ):
            publication._walk_journal(
                self.probe, predecessor_oid, BRANCH, include_recoveries=True
            )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "parent binding"
        ):
            publication._walk_journal_identity_projection(
                self.probe, predecessor_oid, BRANCH
            )

        replay = copy.deepcopy(recovery)
        replay["authorization_id"] = "ready-source-recovery-replay"
        with self.assertRaises((
            authority.LifecycleAuthorityError,
            publication.LifecyclePublicationError,
        )):
            publication.publish_ready_source_recovery(
                replay,
                signer_identity=SIGNER,
                signer=signer_for(),
            )

        checkpoint = copy.deepcopy(chain.checkpoint)
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[6])
        chain.checkpoint = checkpoint
        publication.advance_current_terminal(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError, "no longer binds CURRENT"
        ):
            publication.verify_current_ready_source_recovery(REPOSITORY, ISSUE)

    def test_ready_recovery_accepts_only_verified_exact_adoption_history(self) -> None:
        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
            ready_history=[{
                "sequence": 1,
                "transition_kind": "DRAFT_TO_READY",
                "observation_digest": "7" * 64,
            }],
        )
        self.assertEqual(
            authority._ready_source_recovery_state(
                state,
                historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
            )["ready_history"],
            state["ready_history"],
        )
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority._ready_source_recovery_state(
                state,
                historical_proof_mode=authority.NATIVE_PROOF_MODE,
            )
    def test_exact_adoption_ready_recovery_publishes_and_verifies(self) -> None:
        serialized, _ = exact_adoption_evidence()
        enrolled = publication.enroll_existing_lifecycle(
            serialized, signer_identity=SIGNER, signer=signer_for()
        )
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PR,
            head_sha=HEADS[2],
            base_ref="main",
            base_sha=HEADS[9],
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        registry = {
            "manual_gates": [],
            "validation": [],
            "limits": {"maximum_items": 10000},
        }
        receipt = fast_path.create_validation_receipt(
            repository=REPOSITORY,
            head_sha=HEADS[2],
            validated_tree_sha=HEADS[3],
            registry=registry,
            command_set=[],
            successful_result=True,
            reviewed_state=reviewed,
            manual_gate_evidence=[],
        )
        safety = fast_path.derive_ready_source_recovery_safety_facts(
            tooling_authority_main="f" * 40,
            repository=REPOSITORY,
            pull_request_number=PR,
            head_sha=HEADS[2],
            tree_sha=HEADS[3],
            parent_shas=[HEADS[1]],
            expected_base_ref="main",
            expected_base_sha=HEADS[9],
            reviewed_state=reviewed,
            review_decision="APPROVED",
            feedback_findings=[],
            fresh_validation_receipt=receipt,
            registry=registry,
            command_set=[],
        )
        commit = {
            "oid": HEADS[2],
            "source": "USER",
            "signer_identity": SIGNER,
            "local_signature": {
                "verified": True,
                "state": "valid",
                "format": "ssh",
            },
            "github_verification": {"verified": True, "reason": "valid"},
        }
        with patch.object(
            authority,
            "_load_delivery_signature_policy",
            return_value={
                "accepted_formats": ["ssh"],
                "require_github_verified": True,
            },
        ):
            recovery = authority._sign_ready_source_recovery_authorization(
                current_lifecycle=enrolled.lifecycle,
                current_publication_oid=enrolled.publication_oid,
                current_publication_digest=enrolled.publication_digest,
                recovery_safety_facts=safety,
                commit_signature_evidence=commit,
                historical_validation_receipt_digest=(
                    enrolled.lifecycle.validation_receipt_digest
                ),
                historical_final_attestation_digest=(
                    enrolled.lifecycle.adoption_source_evidence_digest
                ),
                historical_evidence_loss_proof_digest="7" * 64,
                authorization_id="exact-adoption-ready-recovery",
                bounded_uses=1,
                expected_commit_signer={
                    "kind": "SSH_PRINCIPAL",
                    "identity": SIGNER,
                },
                signer_identity=SIGNER,
                signer=signer_for(),
            )
        published = publication.publish_ready_source_recovery(
            recovery, signer_identity=SIGNER, signer=signer_for()
        )
        verified = publication.verify_current_ready_source_recovery(
            REPOSITORY, ISSUE
        )
        self.assertEqual(verified.publication_oid, published.publication_oid)
        self.assertEqual(verified.head_sha, HEADS[2])
        self.assertEqual(
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
            .publication_oid,
            enrolled.publication_oid,
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

        def issue_successor(**kwargs: Any) -> dict[str, Any]:
            provenance = json.loads(
                current_validation._verification_seal.provenance_json
            )
            integration = provenance["integration_evidence"]
            git_results = [
                subprocess.CompletedProcess(
                    [], 0, "https://github.com/SecPal/.github.git\n", ""
                ),
                subprocess.CompletedProcess(
                    [],
                    0,
                    (
                        f"tree {integration['validated_tree_sha']}\n"
                        + "".join(
                            f"parent {parent_sha}\n"
                            for parent_sha in integration["ordered_parent_shas"]
                        )
                        + "gpgsig -----BEGIN SSH SIGNATURE-----\n\n"
                    ),
                    "",
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
                fast_path,
                "_run_integration_commit_git",
                side_effect=git_results,
            ):
                return authority.issue_exact_state_adoption_successor_authority(
                    **kwargs
                )

        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "verified current evidence"
        ):
            issue_successor(
                serialized_adoption_evidence=serialized, authorization=event,
                signer_identity=SIGNER, authority_signer=signer_for(),
                current_head_evidence=replace(
                    current_validation, _verification_seal=object()
                ),
            )
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError, "verified current evidence"
        ):
            issue_successor(
                serialized_adoption_evidence=serialized, authorization=event,
                signer_identity=SIGNER, authority_signer=signer_for(),
                current_head_evidence=verified_validation_evidence(
                    head=HEADS[4], tree=HEADS[5], parent=HEADS[2],
                    ready_integration=True, delivery_issue=ISSUE + 1,
                ),
            )
        snapshot = issue_successor(
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


class ContractsLifecyclePolicyTests(TestCase):
    """Compose the accepted contracts policy through the generic lifecycle."""

    SYNTHETIC_ISSUE = 900001
    SYNTHETIC_PR = 900002

    def setUp(self) -> None:
        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".agents/skills/secpal-pr-review/references/repositories.json"
        )
        self.registry = registry_path.read_bytes()
        self.accepted_policy = authority._parse_lifecycle_trust_policy(
            self.registry, CONTRACTS_REPOSITORY
        )
        self.directory = tempfile.TemporaryDirectory(
            prefix="contracts-lifecycle-publication-"
        )
        base = Path(self.directory.name)
        self.remote = base / "publication.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(
            [
                "git", "--git-dir", str(self.remote), "config",
                "receive.denyNonFastForwards", "true",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git", "--git-dir", str(self.remote), "config",
                "receive.denyDeletes", "true",
            ],
            check=True,
        )
        self.policy = replace(
            self.accepted_policy, publication_remote_url=str(self.remote)
        )
        self.policy_patch = patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=self.policy
        )
        self.verifier_patch = patch.object(
            authority, "_policy_signature_verifier", return_value=verify_signature
        )
        self.protection_patch = patch.object(
            publication,
            "_verify_live_protection",
            return_value=self.policy.publication_ruleset_id,
        )
        self.policy_patch.start()
        self.verifier_patch.start()
        self.protection_patch.start()

    def tearDown(self) -> None:
        self.protection_patch.stop()
        self.verifier_patch.stop()
        self.policy_patch.stop()
        self.directory.cleanup()

    def chain(self) -> Chain:
        return Chain(
            self.SYNTHETIC_ISSUE,
            repository=CONTRACTS_REPOSITORY,
            pull_request=self.SYNTHETIC_PR,
        )

    def test_contracts_policy_composes_first_publication_current_and_ready(self) -> None:
        absence = publication.verify_pre_enrollment_absence(
            CONTRACTS_REPOSITORY, self.SYNTHETIC_ISSUE
        )
        publication.require_unenrolled_delivery(
            CONTRACTS_REPOSITORY, self.SYNTHETIC_ISSUE
        )
        self.assertEqual(absence.repository, CONTRACTS_REPOSITORY)
        self.assertIsNone(absence.observed_tip_oid)

        chain = self.chain()
        chain.append("INITIALIZED_DRAFT")
        admission = publication.admit_native_genesis(
            chain.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        enrolled = publication.enroll_existing_lifecycle(
            chain.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        current = publication.verify_current_lifecycle_authority(
            CONTRACTS_REPOSITORY, self.SYNTHETIC_ISSUE
        )
        self.assertEqual(admission.repository, CONTRACTS_REPOSITORY)
        self.assertEqual(enrolled.journal_predecessor_oid, admission.admission_oid)
        self.assertEqual(current.publication_oid, enrolled.publication_oid)
        self.assertTrue(current.lifecycle.state["draft"])
        self.assertFalse(current.lifecycle.state["ready"])

        predecessor = enrolled
        for transition, head in (
            ("UNRESTRICTED_REVIEW_CONSUMED", None),
            ("REMEDIATION_COMPLETED", HEADS[1]),
            ("REMEDIATION_COMPLETED", HEADS[2]),
            ("DRAFT_TO_READY", None),
        ):
            chain.append(transition, head=head)
            ready = publication.advance_current_terminal(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )
            self.assertEqual(
                ready.predecessor_publication_oid, predecessor.publication_oid
            )
            predecessor = ready
        current = publication.verify_current_lifecycle_authority(
            CONTRACTS_REPOSITORY, self.SYNTHETIC_ISSUE
        )
        self.assertEqual(current.publication_oid, ready.publication_oid)
        self.assertFalse(current.lifecycle.state["draft"])
        self.assertTrue(current.lifecycle.state["ready"])
        self.assertEqual(current.lifecycle.state["ready_transition_count"], 1)
        self.assertTrue(current.lifecycle.state["cycle_3_absent"])

        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "already has native genesis or CURRENT",
        ):
            publication.verify_pre_enrollment_absence(
                CONTRACTS_REPOSITORY, self.SYNTHETIC_ISSUE
            )

    def test_contracts_policy_rejects_duplicate_genesis_and_wrong_signer(self) -> None:
        chain = self.chain()
        chain.append("INITIALIZED_DRAFT")
        with self.assertRaises(
            (publication.LifecyclePublicationError, authority.LifecycleAuthorityError)
        ):
            publication.admit_native_genesis(
                chain.raw(),
                signer_identity=OTHER_SIGNER,
                signer=signer_for(OTHER_SIGNER),
            )
        publication.admit_native_genesis(
            chain.raw(), signer_identity=SIGNER, signer=signer_for()
        )
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "already admitted or enrolled",
        ):
            publication.admit_native_genesis(
                chain.raw(), signer_identity=SIGNER, signer=signer_for()
            )

        competing = Chain(
            self.SYNTHETIC_ISSUE,
            repository=CONTRACTS_REPOSITORY,
            pull_request=self.SYNTHETIC_PR + 1,
        )
        competing.append("INITIALIZED_DRAFT")
        with self.assertRaisesRegex(
            publication.LifecyclePublicationError,
            "already admitted or enrolled",
        ):
            publication.admit_native_genesis(
                competing.raw(), signer_identity=SIGNER, signer=signer_for()
            )

    def test_contracts_policy_rejects_repository_and_remote_substitution(self) -> None:
        for substituted_remote in (
            "https://github.com/SecPal/.github.git",
            "https://github.com/SecPal/deployment.git",
        ):
            with self.subTest(remote=substituted_remote):
                registry = json.loads(self.registry)
                contracts = next(
                    item
                    for item in registry["repositories"]
                    if item["repository"] == CONTRACTS_REPOSITORY
                )
                contracts["lifecycle_authority_policy"][
                    "publication_remote_url"
                ] = substituted_remote
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError,
                    "publication remote does not match repository",
                ):
                    authority._parse_lifecycle_trust_policy(
                        authority.canonical_json_bytes(registry),
                        CONTRACTS_REPOSITORY,
                    )

        registry = json.loads(self.registry)
        contracts = next(
            item
            for item in registry["repositories"]
            if item["repository"] == CONTRACTS_REPOSITORY
        )
        contracts["repository"] = "SecPal/other"
        with self.assertRaisesRegex(
            authority.LifecycleAuthorityError,
            "no unique maintained trust policy",
        ):
            authority._parse_lifecycle_trust_policy(
                authority.canonical_json_bytes(registry), CONTRACTS_REPOSITORY
            )


if __name__ == "__main__":
    main()
