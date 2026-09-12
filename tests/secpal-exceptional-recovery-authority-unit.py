#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Composite authority regressions for existing Exceptional Recovery evidence."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import inspect
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import TestCase, main
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.secpal_pr_review import fast_path
from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_orchestration as orchestration
from scripts.secpal_pr_review import lifecycle_publication as publication


REPOSITORY = "example/project"
DELIVERY_ISSUE = 42
PULL_REQUEST = 43
SIGNER = "maintainer@example.invalid"
PUBLICATION_BRANCH = "refs/heads/secpal-lifecycle-publications"
PUBLICATION_RULESET = 101
SECRET = b"generic-exceptional-recovery-fixture"
FINDING_ID = "FINDING_ALPHA"
THREAD_ID = "PRRT_generic_alpha"


def signer_for(identity: str = SIGNER) -> authority.Signer:
    def sign(payload: bytes, domain: str) -> dict[str, str]:
        value = hashlib.sha256(
            SECRET + identity.encode() + domain.encode() + payload
        ).hexdigest()
        return {"format": "ssh", "signer_identity": identity, "value": value}

    return sign


def verify_signature(
    payload: bytes,
    signature: dict[str, Any],
    expected_signer: str,
    domain: str,
) -> authority.VerifiedSignature:
    expected = signer_for(expected_signer)(payload, domain)
    if signature != expected:
        raise ValueError("fixture signature is invalid")
    return authority.VerifiedSignature(expected_signer, signature["format"])


class Chain:
    def __init__(self, heads: list[str], *, pull_request: int = PULL_REQUEST) -> None:
        self.heads = heads
        self.pull_request = pull_request
        self.initialization = authority.create_delivery_initialization(
            repository=REPOSITORY,
            delivery_issue=DELIVERY_ISSUE,
            pull_request=pull_request,
            initial_head_sha=heads[0],
            validation_receipt_digest="1" * 64,
            final_attestation_digest="2" * 64,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        self.lifecycle_id = authority.delivery_initialization_lifecycle_id(
            self.initialization["initialization_digest"]
        )
        self.authorities: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.head = heads[0]
        self.checkpoint: dict[str, Any] | None = None

    def append(
        self,
        transition: str,
        *,
        head: str | None = None,
        event_id: str | None = None,
    ) -> None:
        resulting_head = head or self.head
        event = authority.create_transition_authorization(
            event_id=(
                f"genesis:{self.initialization['initialization_digest']}"
                if not self.events
                else event_id or f"generic-event-{len(self.events) + 1}"
            ),
            repository=REPOSITORY,
            delivery_issue=DELIVERY_ISSUE,
            lifecycle_id=self.lifecycle_id,
            pull_request=self.pull_request,
            predecessor_authority_digest=(
                None if not self.authorities else self.authorities[-1]["authority_digest"]
            ),
            predecessor_head_sha=None if not self.authorities else self.head,
            resulting_head_sha=resulting_head,
            transition_kind=transition,
            replacement_pull_request=None,
            initialization_evidence_digest=self.initialization[
                "initialization_digest"
            ],
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        snapshot = authority.issue_lifecycle_authority(
            predecessor_chain=self.authorities,
            transition_authorizations=self.events,
            authorization=event,
            signer_identity=SIGNER,
            authority_signer=signer_for(),
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=verify_signature,
        )
        self.events.append(event)
        self.authorities.append(snapshot)
        self.head = resulting_head

    def raw(self) -> bytes:
        return authority.serialize_lifecycle_evidence(
            delivery_initialization=self.initialization,
            transition_authorizations=self.events,
            authority_chain=self.authorities,
        )

    def published(self) -> bytes:
        if self.checkpoint is None:
            self.checkpoint = authority.create_legacy_adoption_checkpoint(
                self.raw(),
                migration_reason="Generic historical lifecycle fixture",
                authorization_identity="fixture:legacy-adoption",
                checkpoint_event_id="fixture-legacy-adoption",
                checkpoint_timestamp="2026-01-01T00:00:00Z",
                supporting_evidence_digests=["3" * 64],
                pr_replacement_history_summary=[],
                signer_identity=SIGNER,
                signer=signer_for(),
            )
        return authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=self.raw(),
            legacy_adoption_checkpoint=self.checkpoint,
        )


class RecoveryFixture:
    def __init__(
        self,
        root: Path,
        *,
        substituted_event_id: bool = False,
        later_successor: bool = False,
        transition_kind: str = "EXCEPTIONAL_RECOVERY",
        authorization_operation: str = "EXCEPTIONAL_RECOVERY",
        authorization_predecessor_head: str | None = None,
        authorization_resulting_head: str | None = None,
        authorization_reviewed_state_digest: str | None = None,
        authorization_reviewed_feedback_digest: str | None = None,
        authorization_eligibility_evidence_digest: str | None = None,
        authorization_finding_ids: list[str] | None = None,
        authorization_thread_ids: list[str] | None = None,
        authorization_scope_omissions: tuple[str, ...] = (),
        authorization_signer: str = SIGNER,
        authorization_delivery_issue: int = DELIVERY_ISSUE,
        authorization_pull_request: int | None = None,
        authorization_lifecycle_id: str | None = None,
        pull_request: int = PULL_REQUEST,
        reviewed_pull_request: int | bool | None = None,
        prior_continuation: bool = False,
    ) -> None:
        self.pull_request = pull_request
        self.source = root / "source"
        self.remote = root / "publication.git"
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "config", "user.name", "Fixture"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.source),
                "config",
                "user.email",
                "fixture@example.invalid",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.source),
                "remote",
                "add",
                "origin",
                f"https://github.com/{REPOSITORY}.git",
            ],
            check=True,
        )
        self.heads: list[str] = []
        self.trees: list[str] = []
        for index in range(5):
            (self.source / "fixture.txt").write_text(
                f"fixture {index}\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "-C", str(self.source), "add", "fixture.txt"], check=True
            )
            subprocess.run(
                ["git", "-C", str(self.source), "commit", "-qm", f"fixture {index}"],
                check=True,
            )
            self.heads.append(
                subprocess.run(
                    ["git", "-C", str(self.source), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            self.trees.append(
                subprocess.run(
                    ["git", "-C", str(self.source), "rev-parse", "HEAD^{tree}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )

        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(self.remote),
                "config",
                "receive.denyNonFastForwards",
                "true",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(self.remote),
                "config",
                "receive.denyDeletes",
                "true",
            ],
            check=True,
        )

        chain = Chain(self.heads, pull_request=pull_request)
        chain.append("INITIALIZED_DRAFT")
        chain.append("UNRESTRICTED_REVIEW_CONSUMED")
        chain.append("REMEDIATION_COMPLETED", head=self.heads[1])
        chain.append("REMEDIATION_COMPLETED", head=self.heads[2])
        chain.append("DRAFT_TO_READY")
        if prior_continuation:
            chain.append("EXCEPTIONAL_CONTINUATION")
        self.chain = chain

        self.predecessor = publication.enroll_existing_lifecycle(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=(
                pull_request
                if reviewed_pull_request is None
                else reviewed_pull_request
            ),
            head_sha=self.heads[2],
            base_ref="main",
            base_sha=self.heads[0],
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [
                    {
                        "node_id": THREAD_ID,
                        "is_resolved": False,
                        "is_outdated": True,
                        "comments": [],
                    }
                ],
            },
        )
        self.eligibility = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "pull_request_number": pull_request,
            "reviewed_head_sha": self.reviewed.head_sha,
            "reviewed_state_digest": self.reviewed.state_digest,
            "eligible_threads": [
                {
                    "thread_id": THREAD_ID,
                    "classification": "VALID_ACTIONABLE",
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "finding_ids": [FINDING_ID],
                    "evidence_digest": "4" * 64,
                    "follow_up": None,
                }
            ],
        }
        eligibility_digest = fast_path.digest_json(self.eligibility)
        effective_authorization_pull_request = (
            pull_request
            if authorization_pull_request is None
            else authorization_pull_request
        )
        authorization_lifecycle = replace(
            self.predecessor.lifecycle,
            lifecycle_id=(
                self.predecessor.lifecycle.lifecycle_id
                if authorization_lifecycle_id is None
                else authorization_lifecycle_id
            ),
            pull_request=effective_authorization_pull_request,
            head_sha=(
                self.heads[2]
                if authorization_predecessor_head is None
                else authorization_predecessor_head
            ),
        )
        authorization_scope = {
            "pull_request": effective_authorization_pull_request,
            "predecessor_head_sha": (
                self.heads[2]
                if authorization_predecessor_head is None
                else authorization_predecessor_head
            ),
            "resulting_head_sha": (
                self.heads[3]
                if authorization_resulting_head is None
                else authorization_resulting_head
            ),
            "reviewed_state_digest": (
                self.reviewed.state_digest
                if authorization_reviewed_state_digest is None
                else authorization_reviewed_state_digest
            ),
            "reviewed_feedback_digest": (
                self.reviewed.feedback_digest
                if authorization_reviewed_feedback_digest is None
                else authorization_reviewed_feedback_digest
            ),
            "eligibility_evidence_digest": (
                eligibility_digest
                if authorization_eligibility_evidence_digest is None
                else authorization_eligibility_evidence_digest
            ),
            "finding_ids": (
                [FINDING_ID]
                if authorization_finding_ids is None
                else authorization_finding_ids
            ),
            "thread_ids": (
                [THREAD_ID]
                if authorization_thread_ids is None
                else authorization_thread_ids
            ),
        }
        for omitted_field in authorization_scope_omissions:
            authorization_scope.pop(omitted_field)
        self.authorization = orchestration.create_user_authorization(
            authorization_id="fixture-recovery-authorization",
            repository=REPOSITORY,
            delivery_issue=authorization_delivery_issue,
            lifecycle=authorization_lifecycle,
            publication_oid=self.predecessor.publication_oid,
            publication_digest=self.predecessor.publication_digest,
            operation=authorization_operation,
            reason="Correct the exact generic finding",
            scope=authorization_scope,
            signer_identity=authorization_signer,
            signer=signer_for(authorization_signer),
        )
        authorization = authority.loads_closed_json(self.authorization)
        event_id = (
            "authorization:" + "f" * 64
            if substituted_event_id
            else f"authorization:{authorization['authorization_digest']}"
        )
        checkpoint = copy.deepcopy(chain.checkpoint)
        chain.append(transition_kind, head=self.heads[3], event_id=event_id)
        chain.checkpoint = checkpoint
        self.recovery_publication = publication.advance_current_terminal(
            chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        if later_successor:
            chain.append("EXCEPTIONAL_CONTINUATION", head=self.heads[4])
            chain.checkpoint = checkpoint
            self.current_publication = publication.advance_current_terminal(
                chain.published(), signer_identity=SIGNER, signer=signer_for()
            )
        else:
            self.current_publication = self.recovery_publication

        self.recovery = fast_path.normalize_exceptional_recovery_evidence(
            {
                "schema_version": "1.0",
                "kind": "READY_EXCEPTIONAL_RECOVERY",
                "authorization_id": authorization["authorization_id"],
                "repository": REPOSITORY,
                "delivery_issue_number": DELIVERY_ISSUE,
                "pull_request_number": pull_request,
                "prior_ready_head_sha": self.heads[2],
                "prior_ready_tree_sha": self.trees[2],
                "recovery_tree_sha": self.trees[3],
                "reviewed_state_digest": self.reviewed.state_digest,
                "reviewed_feedback_digest": self.reviewed.feedback_digest,
                "eligibility_evidence_digest": eligibility_digest,
                "finding_ids": [FINDING_ID],
                "thread_ids": [THREAD_ID],
                "lifecycle": {
                    "unrestricted_reviews": 1,
                    "remediation_cycles": 2,
                    "cycle_3": False,
                    "draft": False,
                    "ready": True,
                    "ready_transition": False,
                    "exceptional_recovery_count": 1,
                },
            },
            repository=REPOSITORY,
            reviewed_state=self.reviewed,
            validated_tree_sha=self.trees[3],
            eligibility_evidence_digest=eligibility_digest,
        )

    def verify(
        self,
        recovery: dict[str, Any] | None = None,
        *,
        authorization: bytes | str | None = None,
        reviewed: Any = None,
        eligibility: Any = None,
        repository_root: Path | None = None,
        repository: str = REPOSITORY,
        delivery_issue: int = DELIVERY_ISSUE,
        pull_request: int | None = None,
        resulting_head_sha: str | None = None,
    ) -> Any:
        return orchestration.verify_exceptional_recovery_authority(
            self.recovery if recovery is None else recovery,
            orchestration_authorization=(
                self.authorization if authorization is None else authorization
            ),
            reviewed_state_evidence=(
                self.reviewed.to_dict() if reviewed is None else reviewed
            ),
            eligibility_evidence=(
                self.eligibility if eligibility is None else eligibility
            ),
            repository_root=(
                self.source if repository_root is None else repository_root
            ),
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=(
                self.pull_request if pull_request is None else pull_request
            ),
            resulting_head_sha=(
                self.heads[3] if resulting_head_sha is None else resulting_head_sha
            ),
        )


class ContinuationFixture:
    def __init__(
        self,
        root: Path,
        *,
        transition_kind: str = "EXCEPTIONAL_CONTINUATION",
        authorization_operation: str = "EXCEPTIONAL_CONTINUATION",
        authorization_repository: str = REPOSITORY,
        authorization_delivery_issue: int = DELIVERY_ISSUE,
        authorization_pull_request: int = PULL_REQUEST,
        authorization_predecessor_head: str | None = None,
        authorization_resulting_head: str | None = None,
        authorization_finding_ids: list[str] | None = None,
        authorization_thread_ids: list[str] | None = None,
        authorization_signer: str = SIGNER,
    ) -> None:
        recovery = RecoveryFixture(root)
        self.source = recovery.source
        self.heads = recovery.heads
        self.trees = recovery.trees
        self.chain = recovery.chain
        self.predecessor = recovery.recovery_publication
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PULL_REQUEST,
            head_sha=self.heads[3],
            base_ref="main",
            base_sha=self.heads[0],
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [
                    {
                        "node_id": THREAD_ID,
                        "is_resolved": False,
                        "is_outdated": True,
                        "comments": [
                            {
                                "node_id": FINDING_ID,
                                "body_digest": "5" * 64,
                                "actor": {
                                    "login": "reviewer",
                                    "node_id": "ACTOR_GENERIC",
                                    "database_id": 1,
                                },
                                "reply_to_id": None,
                                "reactions": [],
                            }
                        ],
                    }
                ],
            },
        )
        self.eligibility = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "pull_request_number": PULL_REQUEST,
            "reviewed_head_sha": self.reviewed.head_sha,
            "reviewed_state_digest": self.reviewed.state_digest,
            "eligible_threads": [
                {
                    "thread_id": THREAD_ID,
                    "classification": "VALID_ACTIONABLE",
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "finding_ids": [FINDING_ID],
                    "evidence_digest": "6" * 64,
                    "follow_up": None,
                }
            ],
        }
        current_feedback = copy.deepcopy(self.reviewed.feedback)
        for thread in current_feedback["threads"]:
            thread["is_outdated"] = True
        self.current_feedback = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PULL_REQUEST,
            head_sha=self.heads[4],
            base_ref=self.reviewed.base_ref,
            base_sha=self.reviewed.base_sha,
            pr_state="OPEN",
            feedback=current_feedback,
        )
        eligibility_digest = fast_path.digest_json(self.eligibility)
        authorization_lifecycle = replace(
            self.predecessor.lifecycle,
            repository=authorization_repository,
            delivery_issue=authorization_delivery_issue,
            pull_request=authorization_pull_request,
            head_sha=(
                self.heads[3]
                if authorization_predecessor_head is None
                else authorization_predecessor_head
            ),
        )
        self.authorization = orchestration.create_user_authorization(
            authorization_id="fixture-continuation-authorization",
            repository=authorization_repository,
            delivery_issue=authorization_delivery_issue,
            lifecycle=authorization_lifecycle,
            publication_oid=self.predecessor.publication_oid,
            publication_digest=self.predecessor.publication_digest,
            operation=authorization_operation,
            reason="Correct the exact post-Recovery material finding",
            scope={
                "pull_request": authorization_pull_request,
                "predecessor_head_sha": (
                    self.heads[3]
                    if authorization_predecessor_head is None
                    else authorization_predecessor_head
                ),
                "resulting_head_sha": (
                    self.heads[4]
                    if authorization_resulting_head is None
                    else authorization_resulting_head
                ),
                "reviewed_state_digest": self.reviewed.state_digest,
                "reviewed_feedback_digest": self.reviewed.feedback_digest,
                "eligibility_evidence_digest": eligibility_digest,
                "finding_ids": (
                    [FINDING_ID]
                    if authorization_finding_ids is None
                    else authorization_finding_ids
                ),
                "thread_ids": (
                    [THREAD_ID]
                    if authorization_thread_ids is None
                    else authorization_thread_ids
                ),
            },
            signer_identity=authorization_signer,
            signer=signer_for(authorization_signer),
        )
        authorization = authority.loads_closed_json(self.authorization)
        self.chain.append(
            transition_kind,
            head=self.heads[4],
            event_id=f"authorization:{authorization['authorization_digest']}",
        )
        self.continuation_publication = publication.advance_current_terminal(
            self.chain.published(), signer_identity=SIGNER, signer=signer_for()
        )
        predecessor_state = self.predecessor.lifecycle.state
        self.continuation = fast_path.normalize_exceptional_continuation_evidence(
            {
                "schema_version": "1.0",
                "kind": "READY_EXCEPTIONAL_CONTINUATION",
                "authorization_id": authorization["authorization_id"],
                "repository": REPOSITORY,
                "delivery_issue_number": DELIVERY_ISSUE,
                "pull_request_number": PULL_REQUEST,
                "prior_ready_head_sha": self.heads[3],
                "prior_ready_tree_sha": self.trees[3],
                "continuation_tree_sha": self.trees[4],
                "reviewed_state_digest": self.reviewed.state_digest,
                "reviewed_feedback_digest": self.reviewed.feedback_digest,
                "eligibility_evidence_digest": eligibility_digest,
                "finding_ids": [FINDING_ID],
                "thread_ids": [THREAD_ID],
                "expected_signer": {
                    "kind": "SSH_PRINCIPAL",
                    "identity": SIGNER,
                },
                "lifecycle": {
                    "unrestricted_reviews": predecessor_state[
                        "unrestricted_review_count"
                    ],
                    "remediation_cycles": predecessor_state[
                        "remediation_cycle_count"
                    ],
                    "cycle_3": not predecessor_state["cycle_3_absent"],
                    "draft": predecessor_state["draft"],
                    "ready": predecessor_state["ready"],
                    "ready_transition_count": predecessor_state[
                        "ready_transition_count"
                    ],
                    "ready_history": predecessor_state["ready_history"],
                    "exceptional_recovery_count": predecessor_state[
                        "exceptional_recovery_count"
                    ],
                    "exceptional_recovery_history": predecessor_state[
                        "exceptional_recovery_history"
                    ],
                    "exceptional_continuation_predecessor_count": 0,
                    "exceptional_continuation_successor_count": 1,
                },
            },
            repository=REPOSITORY,
            reviewed_state=self.reviewed,
            validated_tree_sha=self.trees[4],
            eligibility_evidence=self.eligibility,
        )
        self.authenticated_commit = fast_path.AuthenticatedIntegrationCommit(
            repository=REPOSITORY,
            head_sha=self.heads[4],
            tree_sha=self.trees[4],
            parent_shas=(self.heads[3],),
            signer_kind="SSH_PRINCIPAL",
            signer_identity=SIGNER,
            signature_fingerprint=orchestration._ssh_public_key_fingerprint(
                "ssh-ed25519 AAAA"
            ),
            signature_classification="LOCAL_VERIFIED",
            signature_policy_digest="7" * 64,
            authentication_digest="8" * 64,
        )

    def verify(self, continuation: Any = None, **changes: Any) -> Any:
        with (
            patch.object(
                orchestration,
                "_authenticate_continuation_commit",
                return_value=self.authenticated_commit,
            ),
            patch.object(
                orchestration,
                "_capture_current_stable_feedback",
                return_value=self.current_feedback,
            ),
        ):
            return orchestration.verify_exceptional_continuation_authority(
                self.continuation if continuation is None else continuation,
                orchestration_authorization=changes.get(
                    "authorization", self.authorization
                ),
                reviewed_state_evidence=changes.get(
                    "reviewed", self.reviewed.to_dict()
                ),
                eligibility_evidence=changes.get(
                    "eligibility", self.eligibility
                ),
                repository_root=changes.get("repository_root", self.source),
                repository=changes.get("repository", REPOSITORY),
                delivery_issue=changes.get("delivery_issue", DELIVERY_ISSUE),
                pull_request=changes.get("pull_request", PULL_REQUEST),
                resulting_head_sha=changes.get("resulting_head_sha", self.heads[4]),
            )


class ExceptionalRecoveryAuthorityTests(TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(
            prefix="exceptional-recovery-authority-"
        )
        root = Path(self.directory.name)
        self.publication_remote = root / "publication.git"
        trusted = authority.TrustedSigner(SIGNER, ("ssh-ed25519 AAAA",), ())
        self.policy = authority.LifecycleTrustPolicy(
            repository=REPOSITORY,
            accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
            signers={SIGNER: trusted},
            initialization_anchors=(),
            publication_signer_identities=frozenset({SIGNER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
            publication_branch=PUBLICATION_BRANCH,
            publication_remote_url=str(self.publication_remote),
            publication_ruleset_id=PUBLICATION_RULESET,
            publication_required_rules=frozenset(
                {"deletion", "non_fast_forward"}
            ),
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
            return_value=PUBLICATION_RULESET,
        )
        self.policy_patch.start()
        self.verifier_patch.start()
        self.protection_patch.start()

    def tearDown(self) -> None:
        self.protection_patch.stop()
        self.verifier_patch.stop()
        self.policy_patch.stop()
        self.directory.cleanup()

    def fixture(self, **changes: Any) -> RecoveryFixture:
        return RecoveryFixture(Path(self.directory.name), **changes)

    def test_arbitrary_self_consistent_artifact_is_not_authority(self) -> None:
        fixture = self.fixture()
        forged = copy.deepcopy(fixture.recovery)
        forged["authorization_id"] = "fixture-forged-authorization"

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify(forged)

    def test_exact_recovery_projection_and_signed_authority_succeed(self) -> None:
        fixture = self.fixture()

        verified = fixture.verify()

        self.assertEqual(
            verified.recovery_digest, fast_path.digest_json(fixture.recovery)
        )
        self.assertEqual(verified.authorization_id, "fixture-recovery-authorization")
        self.assertEqual(verified.repository, REPOSITORY)
        self.assertEqual(verified.delivery_issue, DELIVERY_ISSUE)
        self.assertEqual(verified.pull_request, PULL_REQUEST)
        self.assertEqual(verified.prior_ready_head_sha, fixture.heads[2])
        self.assertEqual(verified.resulting_head_sha, fixture.heads[3])
        self.assertEqual(verified.prior_ready_tree_sha, fixture.trees[2])
        self.assertEqual(verified.recovery_tree_sha, fixture.trees[3])
        self.assertEqual(verified.finding_ids, (FINDING_ID,))
        self.assertEqual(verified.thread_ids, (THREAD_ID,))

    def test_reviewed_state_rejects_boolean_pull_request_identities(self) -> None:
        fixture = self.fixture()
        for boolean_identity in (True, False):
            with self.subTest(pull_request_number=boolean_identity):
                payload = fixture.reviewed.to_dict()
                payload["pull_request_number"] = boolean_identity
                with self.assertRaises(fast_path.SecurityBlocker):
                    internally_consistent = fast_path.StableFeedbackState.from_payload(
                        payload
                    ).to_dict()
                    fast_path.verify_reviewed_state_evidence(internally_consistent)

    def test_reviewed_state_accepts_positive_integer_pull_request_identities(
        self,
    ) -> None:
        fixture = self.fixture()
        for pull_request in (1, PULL_REQUEST):
            with self.subTest(pull_request_number=pull_request):
                payload = fixture.reviewed.to_dict()
                payload["pull_request_number"] = pull_request
                internally_consistent = fast_path.StableFeedbackState.from_payload(
                    payload
                ).to_dict()
                reviewed = fast_path.verify_reviewed_state_evidence(
                    internally_consistent
                )
                self.assertEqual(reviewed.pull_request_number, pull_request)

    def test_exceptional_recovery_rejects_boolean_integer_pr_alias(self) -> None:
        with self.assertRaises(
            (fast_path.SecurityBlocker, orchestration.LifecycleOrchestrationError)
        ):
            fixture = self.fixture(pull_request=1, reviewed_pull_request=True)
            fixture.verify()

    def test_signed_authorization_operation_mismatch_fails(self) -> None:
        fixture = self.fixture(authorization_operation="REMEDIATION_COMPLETED")

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_signed_authorization_predecessor_mismatch_fails(self) -> None:
        fixture = self.fixture(authorization_predecessor_head="0" * 40)

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_signed_authorization_resulting_head_mismatch_fails(self) -> None:
        fixture = self.fixture(authorization_resulting_head="0" * 40)

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_signed_authorization_finding_set_mismatch_fails(self) -> None:
        fixture = self.fixture(authorization_finding_ids=["FINDING_BETA"])

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_signed_authorization_required_review_scope_omission_fails(self) -> None:
        fixture = self.fixture(authorization_scope_omissions=("thread_ids",))

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_valid_signature_over_substituted_review_scope_fails(self) -> None:
        fixture = self.fixture(
            authorization_reviewed_state_digest="5" * 64,
            authorization_reviewed_feedback_digest="6" * 64,
            authorization_eligibility_evidence_digest="7" * 64,
            authorization_thread_ids=["PRRT_attacker_substitute"],
        )

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_non_recovery_lifecycle_transition_fails(self) -> None:
        fixture = self.fixture(transition_kind="HEAD_ADVANCED")

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_transition_event_identity_must_bind_authorization_digest(self) -> None:
        fixture = self.fixture(substituted_event_id=True)

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_historical_recovery_remains_verifiable_after_successor(self) -> None:
        fixture = self.fixture(later_successor=True)

        verified = fixture.verify()

        self.assertEqual(verified.recovery_digest, fast_path.digest_json(fixture.recovery))
        self.assertEqual(verified.resulting_head_sha, fixture.heads[3])
        self.assertNotEqual(
            fixture.recovery_publication.publication_oid,
            fixture.current_publication.publication_oid,
        )

    def test_existing_continuation_history_is_preserved(self) -> None:
        fixture = self.fixture(prior_continuation=True)

        verified = fixture.verify()

        self.assertEqual(verified.recovery_digest, fast_path.digest_json(fixture.recovery))

    def test_tree_substitution_matrix_fails(self) -> None:
        fixture = self.fixture()
        variants = {
            "prior": ("prior_ready_tree_sha", "0" * 40),
            "recovery": ("recovery_tree_sha", "0" * 40),
        }
        for label, (field, value) in variants.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(fixture.recovery)
                changed[field] = value
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    fixture.verify(changed)

    def test_reviewed_state_and_feedback_digest_substitution_fails(self) -> None:
        fixture = self.fixture()
        for field in ("state_digest", "feedback_digest"):
            with self.subTest(field=field):
                changed = fixture.reviewed.to_dict()
                changed[field] = "0" * 64
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    fixture.verify(reviewed=changed)

    def test_coordinated_review_authority_substitution_fails(self) -> None:
        fixture = self.fixture()
        reviewed_payload = fixture.reviewed.to_dict()
        reviewed_payload["threads"][0]["node_id"] = "PRRT_attacker_substitute"
        substituted_reviewed = fast_path.StableFeedbackState.from_payload(
            reviewed_payload
        )
        substituted_eligibility = copy.deepcopy(fixture.eligibility)
        substituted_eligibility[
            "reviewed_state_digest"
        ] = substituted_reviewed.state_digest
        substituted_eligibility["eligible_threads"][0][
            "thread_id"
        ] = "PRRT_attacker_substitute"
        substituted_eligibility_digest = fast_path.digest_json(
            substituted_eligibility
        )
        substituted_recovery = copy.deepcopy(fixture.recovery)
        substituted_recovery[
            "reviewed_state_digest"
        ] = substituted_reviewed.state_digest
        substituted_recovery[
            "reviewed_feedback_digest"
        ] = substituted_reviewed.feedback_digest
        substituted_recovery[
            "eligibility_evidence_digest"
        ] = substituted_eligibility_digest
        substituted_recovery["thread_ids"] = ["PRRT_attacker_substitute"]

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify(
                substituted_recovery,
                reviewed=substituted_reviewed.to_dict(),
                eligibility=substituted_eligibility,
            )

    def test_eligibility_and_thread_set_substitution_fails(self) -> None:
        fixture = self.fixture()
        changed_eligibility = copy.deepcopy(fixture.eligibility)
        changed_eligibility["eligible_threads"][0]["finding_ids"] = [
            "FINDING_BETA"
        ]
        changed_recovery = copy.deepcopy(fixture.recovery)
        changed_recovery["thread_ids"] = ["PRRT_unrelated"]
        for label, arguments in (
            ("eligibility", {"eligibility": changed_eligibility}),
            ("thread", {"recovery": changed_recovery}),
        ):
            with self.subTest(label=label):
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    fixture.verify(**arguments)

    def test_duplicate_eligibility_finding_fails(self) -> None:
        fixture = self.fixture()
        reviewed = fixture.reviewed.to_dict()
        second_thread = copy.deepcopy(reviewed["threads"][0])
        second_thread["node_id"] = "PRRT_generic_beta"
        reviewed["threads"].append(second_thread)
        reviewed_state = fast_path.StableFeedbackState.from_payload(reviewed)
        reviewed = reviewed_state.to_dict()
        eligibility = copy.deepcopy(fixture.eligibility)
        eligibility["reviewed_state_digest"] = reviewed_state.state_digest
        second_eligible = copy.deepcopy(eligibility["eligible_threads"][0])
        second_eligible["thread_id"] = "PRRT_generic_beta"
        eligibility["eligible_threads"].append(second_eligible)

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify(reviewed=reviewed, eligibility=eligibility)

    def test_replay_constraints_fail_closed(self) -> None:
        fixture = self.fixture()
        variants = (
            ("delivery", {"delivery_issue": DELIVERY_ISSUE + 1}),
            ("pull_request", {"pull_request": PULL_REQUEST + 1}),
            ("head", {"resulting_head_sha": fixture.heads[4]}),
            ("repository", {"repository": "example/other"}),
        )
        for label, arguments in variants:
            with self.subTest(label=label):
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    fixture.verify(**arguments)

    def test_cross_lifecycle_authorization_replay_fails(self) -> None:
        fixture = self.fixture(authorization_lifecycle_id="lifecycle:" + "9" * 64)

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_wrong_signer_fails(self) -> None:
        fixture = self.fixture(
            authorization_signer="untrusted@example.invalid"
        )
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_wrong_signature_fails(self) -> None:
        fixture = self.fixture()
        authorization = authority.loads_closed_json(fixture.authorization)
        authorization["signature"]["value"] = "0" * 64
        bad_signature = authority.canonical_json_bytes(authorization)
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify(authorization=bad_signature)

    def test_missing_historical_signed_authorization_fails(self) -> None:
        fixture = self.fixture()

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration.verify_exceptional_recovery_authority(
                fixture.recovery,
                orchestration_authorization=None,
                reviewed_state_evidence=fixture.reviewed.to_dict(),
                eligibility_evidence=fixture.eligibility,
                repository_root=fixture.source,
                repository=REPOSITORY,
                delivery_issue=DELIVERY_ISSUE,
                pull_request=PULL_REQUEST,
                resulting_head_sha=fixture.heads[3],
            )

    def test_future_recovery_version_fails(self) -> None:
        fixture = self.fixture()
        future = copy.deepcopy(fixture.recovery)
        future["schema_version"] = "1.1"

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify(future)

    def test_malformed_protected_lifecycle_chain_fails(self) -> None:
        fixture = self.fixture()
        with publication._isolated_repository(self.policy, write=True) as (
            root,
            credential_environment,
        ):
            tip = publication._observe_remote_current_once(
                root,
                self.policy.publication_remote_url,
                self.policy.publication_branch,
                credential_environment=credential_environment,
            )
            self.assertIsNotNone(tip)
            malformed = publication._write_publication_object(root, b"{}\n", tip)
            publication._cas_remote_ref(
                root,
                self.policy.publication_remote_url,
                self.policy.publication_branch,
                malformed,
                tip,
                credential_environment=credential_environment,
            )

        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            fixture.verify()

    def test_public_verifier_accepts_no_caller_selected_trust(self) -> None:
        parameters = inspect.signature(
            orchestration.verify_exceptional_recovery_authority
        ).parameters
        for forbidden in (
            "signer",
            "signature_verifier",
            "trust_policy",
            "publication_reader",
            "git_runner",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_verified_result_exposes_no_resolution_or_readiness_capability(self) -> None:
        fields = set(
            orchestration.VerifiedExceptionalRecoveryAuthority.__dataclass_fields__
        )
        self.assertFalse(
            fields
            & {
                "resolve",
                "resolution_mode",
                "checks",
                "ci",
                "merge",
                "merge_ready",
                "ready_transition",
            }
        )


class ExceptionalContinuationAuthorityTests(TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(
            prefix="exceptional-continuation-authority-"
        )
        root = Path(self.directory.name)
        self.publication_remote = root / "publication.git"
        trusted = authority.TrustedSigner(SIGNER, ("ssh-ed25519 AAAA",), ())
        self.policy = authority.LifecycleTrustPolicy(
            repository=REPOSITORY,
            accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
            signers={SIGNER: trusted},
            initialization_anchors=(),
            publication_signer_identities=frozenset({SIGNER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
            publication_branch=PUBLICATION_BRANCH,
            publication_remote_url=str(self.publication_remote),
            publication_ruleset_id=PUBLICATION_RULESET,
            publication_required_rules=frozenset({"deletion", "non_fast_forward"}),
        )
        self.patches = (
            patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=self.policy
            ),
            patch.object(
                authority, "_policy_signature_verifier", return_value=verify_signature
            ),
            patch.object(
                publication,
                "_verify_live_protection",
                return_value=PUBLICATION_RULESET,
            ),
        )
        for active in self.patches:
            active.start()

    def tearDown(self) -> None:
        for active in reversed(self.patches):
            active.stop()
        self.directory.cleanup()

    def fixture(self, **changes: Any) -> ContinuationFixture:
        return ContinuationFixture(Path(self.directory.name), **changes)

    def test_exact_continuation_projection_and_signed_authority_succeed(self) -> None:
        fixture = self.fixture()

        verified = fixture.verify()

        self.assertEqual(
            verified.continuation_digest,
            fast_path.digest_json(fixture.continuation),
        )
        self.assertEqual(verified.prior_ready_head_sha, fixture.heads[3])
        self.assertEqual(verified.resulting_head_sha, fixture.heads[4])
        self.assertEqual(verified.prior_ready_tree_sha, fixture.trees[3])
        self.assertEqual(verified.continuation_tree_sha, fixture.trees[4])
        self.assertEqual(verified.finding_ids, (FINDING_ID,))
        self.assertEqual(verified.thread_ids, (THREAD_ID,))
        self.assertEqual(verified.source_signer_identity, SIGNER)

    def test_recovery_and_continuation_evidence_are_not_interchangeable(self) -> None:
        fixture = self.fixture()
        recovery_shaped = copy.deepcopy(fixture.continuation)
        recovery_shaped["kind"] = "READY_EXCEPTIONAL_RECOVERY"
        recovery_shaped["recovery_tree_sha"] = recovery_shaped.pop(
            "continuation_tree_sha"
        )
        recovery_shaped.pop("expected_signer")

        for wrong in (
            recovery_shaped,
            {**fixture.continuation, "kind": "READY_EXCEPTIONAL_RECOVERY"},
        ):
            with self.subTest(kind=wrong.get("kind")), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                fixture.verify(wrong)

    def test_signed_authorization_identity_scope_and_transition_mismatch_fail(self) -> None:
        fixture = self.fixture()
        variants = {
            "operation": lambda item: item.update(operation="EXCEPTIONAL_RECOVERY"),
            "repository": lambda item: item.update(repository="other/project"),
            "issue": lambda item: item.update(delivery_issue=DELIVERY_ISSUE + 1),
            "pr": lambda item: item.update(pull_request=PULL_REQUEST + 1),
            "lifecycle": lambda item: item.update(lifecycle_id="lifecycle:" + "0" * 64),
            "publication": lambda item: item.update(publication_oid="0" * 40),
            "publication-digest": lambda item: item.update(
                publication_digest="0" * 64
            ),
            "authority-digest": lambda item: item.update(authority_digest="0" * 64),
            "bounded-uses": lambda item: item.update(bounded_uses=2),
            "wrong-signer": lambda item: item.update(
                signer_identity="attacker@example.invalid"
            ),
            "predecessor": lambda item: item["scope"].update(
                predecessor_head_sha="0" * 40
            ),
            "result": lambda item: item["scope"].update(
                resulting_head_sha="0" * 40
            ),
            "finding": lambda item: item["scope"].update(
                finding_ids=["INVENTED_FINDING"]
            ),
            "empty-finding": lambda item: item["scope"].update(finding_ids=[]),
            "thread": lambda item: item["scope"].update(
                thread_ids=["PRRT_UNRELATED"]
            ),
        }
        for label, mutate in variants.items():
            parsed = authority.loads_closed_json(fixture.authorization)
            unsigned = {
                key: copy.deepcopy(value)
                for key, value in parsed.items()
                if key not in {"signature", "authorization_digest"}
            }
            mutate(unsigned)
            signature = signer_for()(unsigned_bytes := authority.canonical_json_bytes(unsigned), orchestration.AUTHORIZATION_DOMAIN)
            signed = {**unsigned, "signature": signature}
            changed = authority.canonical_json_bytes(
                {
                    **signed,
                    "authorization_digest": authority.digest_json(signed),
                }
            )
            self.assertTrue(unsigned_bytes)
            with self.subTest(label=label), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                fixture.verify(authorization=changed)

    def test_continuation_projection_rejects_history_counter_and_tree_mutation(self) -> None:
        fixture = self.fixture()
        variants = (
            ("prior_ready_tree_sha", "0" * 40),
            ("continuation_tree_sha", "0" * 40),
            ("delivery_issue_number", DELIVERY_ISSUE + 1),
            ("pull_request_number", PULL_REQUEST + 1),
        )
        for field, value in variants:
            changed = copy.deepcopy(fixture.continuation)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                fixture.verify(changed)
        for field, value in (
            ("exceptional_recovery_count", 0),
            ("exceptional_continuation_predecessor_count", 1),
            ("exceptional_continuation_successor_count", 2),
            ("cycle_3", True),
            ("ready", False),
        ):
            changed = copy.deepcopy(fixture.continuation)
            changed["lifecycle"][field] = value
            with self.subTest(field=field), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                fixture.verify(changed)

    def test_source_commit_requires_authorized_signer_and_one_exact_parent(self) -> None:
        expected = {"kind": "SSH_PRINCIPAL", "identity": SIGNER}
        wrong_parent = fast_path.AuthenticatedIntegrationCommit(
            repository=REPOSITORY,
            head_sha="2" * 40,
            tree_sha="3" * 40,
            parent_shas=("4" * 40,),
            signer_kind="SSH_PRINCIPAL",
            signer_identity=SIGNER,
            signature_fingerprint=orchestration._ssh_public_key_fingerprint(
                "ssh-ed25519 AAAA"
            ),
            signature_classification="LOCAL_VERIFIED",
            signature_policy_digest="5" * 64,
            authentication_digest="6" * 64,
        )
        with (
            patch.object(
                fast_path, "authenticate_integration_commit", return_value=wrong_parent
            ),
            self.assertRaisesRegex(
                orchestration.LifecycleOrchestrationError, "exact predecessor"
            ),
        ):
            orchestration._authenticate_continuation_commit(
                Path(self.directory.name),
                REPOSITORY,
                "1" * 40,
                "2" * 40,
                expected,
            )
        wrong_key = replace(
            wrong_parent,
            parent_shas=("1" * 40,),
            signature_fingerprint="SHA256:caller-controlled-key",
        )
        with (
            patch.object(
                fast_path, "authenticate_integration_commit", return_value=wrong_key
            ),
            self.assertRaisesRegex(
                orchestration.LifecycleOrchestrationError, "maintained SSH key"
            ),
        ):
            orchestration._authenticate_continuation_commit(
                Path(self.directory.name),
                REPOSITORY,
                "1" * 40,
                "2" * 40,
                expected,
            )
        with self.assertRaisesRegex(
            orchestration.LifecycleOrchestrationError, "not authorized"
        ):
            orchestration._authenticate_continuation_commit(
                Path(self.directory.name),
                REPOSITORY,
                "1" * 40,
                "2" * 40,
                {"kind": "SSH_PRINCIPAL", "identity": "attacker@example.invalid"},
            )
        with (
            patch.object(
                fast_path,
                "authenticate_integration_commit",
                side_effect=fast_path.SecurityBlocker(
                    "commit signature is missing or invalid"
                ),
            ),
            self.assertRaisesRegex(
                orchestration.LifecycleOrchestrationError,
                "signed source commit is invalid",
            ),
        ):
            orchestration._authenticate_continuation_commit(
                Path(self.directory.name),
                REPOSITORY,
                "1" * 40,
                "2" * 40,
                expected,
            )

    def test_ready_head_advance_after_continuation_preserves_both_budgets(self) -> None:
        fixture = self.fixture()
        before = copy.deepcopy(fixture.continuation_publication.lifecycle.state)
        after = authority.derive_state(before, "HEAD_ADVANCED", "9" * 64)

        self.assertEqual(after["exceptional_recovery_count"], 1)
        self.assertEqual(after["exceptional_continuation_count"], 1)
        self.assertEqual(
            after["exceptional_recovery_history"],
            before["exceptional_recovery_history"],
        )
        self.assertEqual(
            after["exceptional_continuation_history"],
            before["exceptional_continuation_history"],
        )
        self.assertTrue(after["ready"])
        self.assertTrue(after["cycle_3_absent"])


class DiagnosticRecoveryTests(TestCase):
    source = b'''def _verify_python_version_tokens(blob: bytes, offsets: tuple[int, ...], version: str) -> None:
    lines = blob.decode("utf-8", errors="strict").splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line.encode("utf-8")))

    def byte_offset(position: tuple[int, int]) -> int:
        row, column = position
        return starts[row - 1] + len(lines[row - 1][:column].encode("utf-8"))

    spans = []
    try:
        interpolated = [
            (starts[node.lineno - 1] + node.col_offset,
             starts[node.end_lineno - 1] + node.end_col_offset)
            for node in ast.walk(ast.parse(blob)) if isinstance(node, ast.JoinedStr)
        ]
        if any(start <= offset < end for offset in offsets for start, end in interpolated):
            raise VersionCollisionError("Python version token replacement enters an interpolated string")
        for token in tokenize.generate_tokens(io.StringIO(blob.decode("utf-8")).readline):
            if token.type in {tokenize.STRING, tokenize.COMMENT}:
                spans.append((byte_offset(token.start), byte_offset(token.end)))
    except (tokenize.TokenError, IndentationError, SyntaxError, IndexError) as exc:
        raise VersionCollisionError("Python version token source is malformed") from exc
    if any(not any(start <= offset and offset + len(version) <= end for start, end in spans) for offset in offsets):
        raise VersionCollisionError("Python version token replacement changes executable syntax")
'''

    recovery_path = Path("scripts/secpal_pr_review/exceptional_recovery.py")
    large_path = Path("scripts/secpal-pr-review-actions.py")

    def create_maintained_fixture(
        self, fixture: Path,
    ) -> tuple[Path, Path, str]:
        accepted = fixture / "accepted"
        installed = fixture / "installed"
        sources = {
            self.recovery_path: b"# accepted Recovery authority\n",
            self.large_path: b"# large accepted source\n"
            + b"x = 1\n" * (70 * 1024 // 6),
        }
        for relative, content in sources.items():
            for root in (accepted, installed):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        subprocess.run(["git", "-C", str(accepted), "init", "--quiet"], check=True)
        subprocess.run(["git", "-C", str(accepted), "add", "."], check=True)
        subprocess.run(
            [
                "git", "-C", str(accepted), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "--quiet",
                "-m", "accepted maintained sources",
            ],
            check=True,
        )
        main_oid = subprocess.check_output(
            ["git", "-C", str(accepted), "rev-parse", "HEAD"], text=True,
        ).strip()
        return accepted, installed, main_oid

    def authenticate_fixture(
        self,
        accepted: Path,
        installed: Path,
        main_oid: str,
        *,
        branch_oid: str | None = None,
        listing_transform: Any = None,
    ) -> str:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        branch = authority.canonical_json_bytes(
            {"protected": True, "commit": {"sha": branch_oid or main_oid}}
        )
        original_git = diagnostic.transport._git

        def observed_git(root: Path, arguments: list[str], **keywords: Any) -> Any:
            result = original_git(root, arguments, **keywords)
            if listing_transform is not None and arguments[:4] == [
                "ls-tree", "-rz", "-r", main_oid,
            ]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=listing_transform(result.stdout),
                    stderr=b"",
                )
            return result

        with patch.object(
            diagnostic, "__file__", str(installed / self.recovery_path),
        ), patch.object(
            diagnostic.transport, "PROTECTED_MAIN_REMOTE_URL", str(accepted),
        ), patch.object(
            diagnostic.transport, "_observe_protected_main", return_value=object(),
        ), patch.object(
            diagnostic.transport, "_normalize_protected_main",
            return_value=SimpleNamespace(head_sha=main_oid),
        ), patch.object(
            diagnostic.transport, "_run_bootstrap_gh",
            return_value=SimpleNamespace(returncode=0, stdout=branch, stderr=b""),
        ), patch.object(diagnostic.transport, "_git", side_effect=observed_git):
            return diagnostic.authenticate_maintained_code()

    def test_large_accepted_main_maintained_source_authenticates_by_blob_identity(
        self,
    ) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        self.assertEqual(diagnostic.transport.MAXIMUM_EVIDENCE_BYTES, 64 * 1024)
        with tempfile.TemporaryDirectory() as directory:
            accepted, installed, main_oid = self.create_maintained_fixture(
                Path(directory)
            )
            self.assertGreater(
                (installed / self.large_path).stat().st_size,
                diagnostic.transport.MAXIMUM_EVIDENCE_BYTES,
            )
            self.assertEqual(
                self.authenticate_fixture(accepted, installed, main_oid), main_oid,
            )

    def test_maintained_source_inventory_and_installed_bytes_fail_closed(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        cases = (
            "changed-bytes",
            "missing-path",
            "extra-path",
            "wrong-mode",
            "symlink",
            "non-regular",
            "candidate-recovery-substitution",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                accepted, installed, main_oid = self.create_maintained_fixture(
                    Path(directory)
                )
                target = installed / self.large_path
                if case == "changed-bytes":
                    target.write_bytes(b"substituted\n")
                elif case == "missing-path":
                    target.unlink()
                elif case == "extra-path":
                    (installed / "scripts/extra.py").write_text(
                        "extra = True\n", encoding="utf-8"
                    )
                elif case == "wrong-mode":
                    target.chmod(0o755)
                elif case == "symlink":
                    target.unlink()
                    target.symlink_to(self.recovery_path.name)
                elif case == "non-regular":
                    target.unlink()
                    os.mkfifo(target)
                else:
                    (installed / self.recovery_path).write_bytes(b"candidate authority\n")
                with self.assertRaises(diagnostic.DiagnosticRecoveryError):
                    self.authenticate_fixture(accepted, installed, main_oid)

    def test_maintained_tree_metadata_and_protected_main_drift_fail_closed(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        def replace_metadata(index: int, replacement: str) -> Any:
            def transform(listing: bytes) -> bytes:
                records = listing.decode("utf-8").rstrip("\0").split("\0")
                metadata, separator, relative = records[0].partition("\t")
                fields = metadata.split()
                fields[index] = replacement
                records[0] = " ".join(fields) + separator + relative
                return ("\0".join(records) + "\0").encode("utf-8")

            return transform

        cases = (
            ("wrong-blob", replace_metadata(2, "f" * 40), None),
            ("wrong-object-format", replace_metadata(2, "f" * 64), None),
            ("wrong-mode", replace_metadata(0, "100600"), None),
            ("non-blob", replace_metadata(1, "tree"), None),
            ("unsafe-path", lambda value: value.replace(b"scripts/", b"scripts/../", 1), None),
            ("protected-main-drift", None, "f" * 40),
        )
        for case, transform, branch_oid in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                accepted, installed, main_oid = self.create_maintained_fixture(
                    Path(directory)
                )
                with self.assertRaises(diagnostic.DiagnosticRecoveryError):
                    self.authenticate_fixture(
                        accepted,
                        installed,
                        main_oid,
                        branch_oid=branch_oid,
                        listing_transform=transform,
                    )

    def test_exact_reproduction_and_correction_have_canonical_evidence(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        result = diagnostic.reproduce_security_diagnostic(self.source, self.source.replace(diagnostic.BEFORE, diagnostic.AFTER))
        digest = result.pop("evidence_digest")
        self.assertEqual(digest, authority.digest_json(result))
        self.assertEqual(result["prior_result"], "EXECUTABLE_TOKEN_ACCEPTED")
        self.assertEqual(result["correction_result"], "EXECUTABLE_TOKEN_REJECTED")
        self.assertEqual(result["severity"], "MATERIAL_SECURITY")
        self.assertNotIn("thread_ids", result)

    def test_reproduction_rejects_uncorrected_and_unrelated_changes(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        corrected = self.source.replace(diagnostic.BEFORE, diagnostic.AFTER)
        for proposed in (self.source, corrected + b"\nunrelated = True\n", corrected.replace(b"interpolated string", b"anything")):
            with self.subTest(proposed=hashlib.sha256(proposed).hexdigest()), self.assertRaisesRegex(ValueError, "exact maintained source delta"):
                diagnostic.reproduce_security_diagnostic(self.source, proposed)

    def test_reproduction_refuses_substituted_function_and_no_fail_first(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        for prior in (self.source.replace(diagnostic.BEFORE, diagnostic.AFTER), self.source.replace(b"spans = []", b"spans = []; return")):
            with self.subTest(prior=hashlib.sha256(prior).hexdigest()), self.assertRaisesRegex(ValueError, "profile"):
                diagnostic.reproduce_security_diagnostic(prior, prior.replace(diagnostic.BEFORE, diagnostic.AFTER))

    def test_substituted_fixture_cannot_establish_failure(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery as diagnostic

        with patch.object(diagnostic, "FIXTURE", b'value = f"{\'1.0\'}"\n'), self.assertRaisesRegex(ValueError, "fail-first"):
            diagnostic.reproduce_security_diagnostic(self.source, self.source.replace(diagnostic.BEFORE, diagnostic.AFTER))

    def test_encoding_reproduction_is_a_closed_maintained_profile(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery

        with self.assertRaisesRegex(ValueError, "profile"):
            exceptional_recovery.reproduce_security_diagnostic(b"caller assertion", b"fixed")

    def test_diagnostic_recovery_requires_exact_exhausted_ready_state(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery

        state = authority.initial_state()
        with self.assertRaisesRegex(ValueError, "exhausted Ready"):
            exceptional_recovery.require_diagnostic_recovery_state(state)

    def exhausted_ready_state(self) -> dict[str, Any]:
        state = authority.initial_state()
        state.update(
            {
                "unrestricted_review_count": 1,
                "remediation_cycle_count": 2,
                "draft": False,
                "ready": True,
                "ready_transition_count": 1,
                "ready_history": [
                    {
                        "sequence": 1,
                        "transition_kind": "DRAFT_TO_READY",
                        "event_authorization_digest": "1" * 64,
                    }
                ],
            }
        )
        return state

    def test_exact_exhausted_ready_state_is_required_without_cycle_three(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery

        expected = self.exhausted_ready_state()
        self.assertEqual(
            exceptional_recovery.require_diagnostic_recovery_state(expected),
            expected,
        )
        mutations = (
            ("review", "unrestricted_review_count", 0),
            ("remediation", "remediation_cycle_count", 1),
            ("recovery", "exceptional_recovery_count", 1),
            ("continuation", "exceptional_continuation_count", 1),
            ("cycle-three", "cycle_3_absent", False),
            ("draft", "draft", True),
            ("ready", "ready", False),
            ("ready-count", "ready_transition_count", 2),
        )
        for label, field, value in mutations:
            changed = copy.deepcopy(expected)
            changed[field] = value
            if field == "exceptional_recovery_count":
                changed["exceptional_recovery_history"] = [
                    {
                        "sequence": 1,
                        "transition_kind": "EXCEPTIONAL_RECOVERY",
                        "event_authorization_digest": "2" * 64,
                    }
                ]
            if field == "exceptional_continuation_count":
                changed["exceptional_continuation_history"] = [
                    {
                        "sequence": 1,
                        "transition_kind": "EXCEPTIONAL_CONTINUATION",
                        "event_authorization_digest": "3" * 64,
                    }
                ]
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError, "exhausted Ready"
            ):
                exceptional_recovery.require_diagnostic_recovery_state(changed)

    def test_authorization_scope_binds_successor_and_zero_thread_authority(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery

        evidence = {
            "pull_request_number": 896,
            "prior_ready_head_sha": "1" * 40,
            "finding_ids": [exceptional_recovery.FINDING_ID],
        }
        scope = exceptional_recovery.authorization_scope(evidence, "2" * 40)
        self.assertEqual(scope["resulting_head_sha"], "2" * 40)
        self.assertEqual(scope["recovery_evidence"], evidence)
        self.assertNotIn("thread_ids", scope)

    def test_tree_profile_rejects_unrelated_delta_and_wrong_topology(self) -> None:
        from scripts.secpal_pr_review import exceptional_recovery

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Fixture"],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "config", "user.email",
                    "fixture@example.invalid",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "remote", "add", "origin",
                    f"https://github.com/{REPOSITORY}.git",
                ],
                check=True,
            )
            source = root / exceptional_recovery.SOURCE_PATH
            source.parent.mkdir(parents=True)
            source.write_bytes(self.source)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "prior"],
                check=True,
            )
            prior_head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            prior_tree = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            source.write_bytes(
                self.source.replace(exceptional_recovery.BEFORE, exceptional_recovery.AFTER)
            )
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            proposed_tree = subprocess.run(
                ["git", "-C", str(root), "write-tree"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            evidence = exceptional_recovery.reproduce_tree_diagnostic(
                root, prior_tree, proposed_tree
            )
            self.assertEqual(evidence["finding_id"], exceptional_recovery.FINDING_ID)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "recovery"],
                check=True,
            )
            recovery_head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            recovery = {
                "repository": REPOSITORY,
                "recovery_tree_sha": proposed_tree,
                "prior_ready_head_sha": prior_head,
            }
            exceptional_recovery.require_successor(root, recovery, recovery_head)
            recovery["prior_ready_head_sha"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "sole-parent"):
                exceptional_recovery.require_successor(root, recovery, recovery_head)

            (root / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "unrelated.txt"], check=True
            )
            unrelated_tree = subprocess.run(
                ["git", "-C", str(root), "write-tree"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            with self.assertRaisesRegex(ValueError, "unrelated"):
                exceptional_recovery.reproduce_tree_diagnostic(
                    root, prior_tree, unrelated_tree
                )


if __name__ == "__main__":
    main()
