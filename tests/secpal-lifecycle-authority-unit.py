#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for persistent delivery lifecycle authority."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import TestCase, main
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.secpal_pr_review import lifecycle_authority as authority

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


class LifecycleAuthorityTests(TestCase):
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
        entry["lifecycle_authority_policy"][
            "historical_compatibility_publications"
        ] = []
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


if __name__ == "__main__":
    main(verbosity=2)
