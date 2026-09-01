#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Composite authority regressions for existing Exceptional Recovery evidence."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import inspect
import subprocess
import sys
import tempfile
from pathlib import Path
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


if __name__ == "__main__":
    main()
