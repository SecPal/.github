#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for lifecycle enrollment and terminal publication."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest import TestCase, main
from unittest.mock import patch

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_publication as publication

REPOSITORY = "SecPal/.github"
ISSUE = 752
PR = 753
SIGNER = "aroviqen@secpal.app"
OTHER_SIGNER = "other@secpal.app"
HEADS = [character * 40 for character in "abcdef1234567890"]
SECRET = b"lifecycle-publication-hermetic-signature"


def signer_for(identity: str = SIGNER) -> authority.Signer:
    def sign(payload: bytes, domain: str) -> dict[str, str]:
        value = hashlib.sha256(SECRET + identity.encode() + domain.encode() + payload).hexdigest()
        return {"format": "ssh", "signer_identity": identity, "value": value}
    return sign


def verify_signature(payload: bytes, signature: dict[str, Any], expected_signer: str,
                     domain: str) -> authority.VerifiedSignature:
    expected = signer_for(expected_signer)(payload, domain)["value"]
    if signature["value"] != expected or signature["signer_identity"] != expected_signer:
        raise ValueError("invalid test signature")
    return authority.VerifiedSignature(expected_signer, signature["format"])


class Chain:
    def __init__(self) -> None:
        self.initialization = authority.create_delivery_initialization(
            repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
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

    def append(self, transition: str, *, head: str | None = None,
               replacement_pull_request: int | None = None) -> None:
        resulting_head = head or self.head
        event = authority.create_transition_authorization(
            event_id=(f"genesis:{self.initialization['initialization_digest']}"
                      if not self.events else f"event-{len(self.events) + 1}"),
            repository=REPOSITORY, delivery_issue=ISSUE,
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
            authorization=event, signer_identity=SIGNER, authority_signer=signer_for(),
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=verify_signature,
        )
        self.events.append(event)
        self.authorities.append(snapshot)
        self.head = resulting_head
        if replacement_pull_request is not None:
            self.pull_request = replacement_pull_request

    def serialized(self) -> bytes:
        return authority.serialize_lifecycle_evidence(
            delivery_initialization=self.initialization,
            transition_authorizations=self.events,
            authority_chain=self.authorities,
        )


def recovered_ready_chain() -> Chain:
    chain = Chain()
    chain.append("INITIALIZED_DRAFT")
    chain.append("UNRESTRICTED_REVIEW_CONSUMED")
    chain.append("REMEDIATION_COMPLETED", head=HEADS[1])
    chain.append("REMEDIATION_COMPLETED", head=HEADS[2])
    chain.append("DRAFT_TO_READY")
    chain.append("EXCEPTIONAL_RECOVERY", head=HEADS[3])
    return chain


class LifecyclePublicationTests(TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="lifecycle-publication-")
        base = Path(self.directory.name)
        self.remote = base / "publication.git"
        self.root = base / "writer"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        trusted = authority.TrustedSigner(SIGNER, ("ssh-ed25519 AAAA",), ())
        self.policy = authority.LifecycleTrustPolicy(
            repository=REPOSITORY, accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}), signers={SIGNER: trusted},
            initialization_anchors=(), publication_signer_identities=frozenset({SIGNER}),
            publication_ref_namespace="refs/secpal/lifecycle-publications",
            publication_remote_url=str(self.remote),
        )
        self.policy_patch = patch.object(authority, "_load_lifecycle_trust_policy",
                                         return_value=self.policy)
        self.verifier_patch = patch.object(authority, "_policy_signature_verifier",
                                           return_value=verify_signature)
        self.policy_patch.start()
        self.verifier_patch.start()

    def tearDown(self) -> None:
        self.verifier_patch.stop()
        self.policy_patch.stop()
        self.directory.cleanup()

    def enroll(self, chain: Chain | None = None) -> tuple[Chain, publication.VerifiedLifecyclePublication]:
        selected = chain or recovered_ready_chain()
        result = publication.enroll_existing_lifecycle(
            self.root, selected.serialized(), signer_identity=SIGNER, signer=signer_for()
        )
        return selected, result

    def test_public_consumer_cannot_inject_trust_or_select_terminal_digest(self) -> None:
        parameters = inspect.signature(publication.verify_current_lifecycle_authority).parameters
        self.assertEqual(list(parameters),
                         ["repository", "delivery_issue", "expected"])
        self.assertNotIn("signer", parameters)
        self.assertNotIn("terminal_authority_digest", parameters)

    def test_valid_unpublished_lifecycle_cannot_be_selected_as_current(self) -> None:
        with self.assertRaisesRegex(publication.LifecyclePublicationError,
                                    "current lifecycle publication is unavailable"):
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)

    def test_historical_enrollment_preserves_complete_finite_lifecycle(self) -> None:
        chain, enrolled = self.enroll()
        state = enrolled.lifecycle.state
        self.assertEqual(enrolled.lifecycle.lifecycle_id, chain.lifecycle_id)
        self.assertEqual(enrolled.lifecycle.head_sha, HEADS[3])
        self.assertEqual(state["unrestricted_review_count"], 1)
        self.assertEqual(state["remediation_cycle_count"], 2)
        self.assertIs(state["cycle_3_absent"], True)
        self.assertIs(state["ready"], True)
        self.assertEqual(state["ready_transition_count"], 1)
        self.assertEqual(state["exceptional_recovery_count"], 1)
        self.assertEqual(state["exceptional_continuation_count"], 0)

    def test_exceptional_continuation_advances_current_and_stale_bundle_fails(self) -> None:
        chain, enrolled = self.enroll()
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        advanced = publication.advance_current_terminal(
            self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertNotEqual(advanced.publication_oid, enrolled.publication_oid)
        self.assertEqual(advanced.lifecycle.head_sha, HEADS[4])
        self.assertEqual(advanced.lifecycle.state["exceptional_continuation_count"], 1)
        with self.assertRaises(authority.LifecycleAuthorityError):
            publication.verify_current_lifecycle_authority(
                REPOSITORY, ISSUE,
                authority.ExpectedLifecycle(REPOSITORY, ISSUE, chain.lifecycle_id, PR, HEADS[3]),
            )

    def test_pr_rebound_preserves_root_and_history(self) -> None:
        chain, enrolled = self.enroll()
        chain.append("PR_REBOUND", replacement_pull_request=PR + 1)
        advanced = publication.advance_current_terminal(
            self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(advanced.lifecycle.pull_request, PR + 1)
        self.assertEqual(advanced.lifecycle.initialization_evidence_digest,
                         enrolled.lifecycle.initialization_evidence_digest)
        self.assertEqual(advanced.lifecycle.state, enrolled.lifecycle.state)

    def test_head_advancement_preserves_all_lifecycle_facts(self) -> None:
        chain, enrolled = self.enroll()
        chain.append("HEAD_ADVANCED", head=HEADS[4])
        advanced = publication.advance_current_terminal(
            self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for()
        )
        self.assertEqual(advanced.lifecycle.head_sha, HEADS[4])
        self.assertEqual(advanced.lifecycle.pull_request, enrolled.lifecycle.pull_request)
        self.assertEqual(advanced.lifecycle.state, enrolled.lifecycle.state)

    def test_ready_transition_publication_preserves_authenticated_history(self) -> None:
        chain, enrolled = self.enroll()
        chain.append("READY_TO_DRAFT")
        advanced = publication.advance_current_terminal(
            self.root, chain.serialized(), signer_identity=SIGNER,
            signer=signer_for())
        self.assertIs(advanced.lifecycle.state["draft"], True)
        self.assertEqual(advanced.lifecycle.state["ready_transition_count"], 1)
        self.assertEqual(len(advanced.lifecycle.state["ready_history"]), 2)
        self.assertEqual(advanced.lifecycle.state["exceptional_recovery_count"], 1)
        self.assertEqual(advanced.lifecycle.lifecycle_id, enrolled.lifecycle.lifecycle_id)

    def test_wrong_publication_signer_and_unsigned_document_fail_closed(self) -> None:
        chain = recovered_ready_chain()
        with self.assertRaises((publication.LifecyclePublicationError,
                                authority.LifecycleAuthorityError)):
            publication.enroll_existing_lifecycle(
                self.root, chain.serialized(), signer_identity=OTHER_SIGNER,
                signer=signer_for(OTHER_SIGNER),
            )
        _, enrolled = self.enroll(chain)
        document = json.loads(
            publication._read_publication_object(self.root, enrolled.publication_oid)[0]
        )
        document["signature"]["value"] = ""
        tampered_oid = publication._write_publication_object(
            self.root, authority.canonical_json_bytes(document), None
        )
        publication._cas_remote_ref(
            self.root, str(self.remote), enrolled.publication_ref, tampered_oid,
            enrolled.publication_oid)
        with self.assertRaises((publication.LifecyclePublicationError,
                                authority.LifecycleAuthorityError)):
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)

    def test_duplicate_and_unknown_publication_fields_fail_closed(self) -> None:
        _, enrolled = self.enroll()
        raw = publication._read_publication_object(self.root, enrolled.publication_oid)[0]
        duplicate = raw.replace(b'{"delivery_issue":',
                                b'{"delivery_issue":752,"delivery_issue":', 1)
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "duplicate"):
            publication._verify_publication_document(
                duplicate, object_oid=enrolled.publication_oid,
                expected_ref=enrolled.publication_ref)
        document = json.loads(raw)
        document["schema_version"] = "2.0"
        with self.assertRaisesRegex(publication.LifecyclePublicationError,
                                    "unknown publication version"):
            publication._verify_publication_document(
                authority.canonical_json_bytes(document), object_oid=enrolled.publication_oid,
                expected_ref=enrolled.publication_ref)

    def test_malformed_unknown_kind_namespace_and_root_substitution_fail_closed(self) -> None:
        _, enrolled = self.enroll()
        raw = publication._read_publication_object(self.root, enrolled.publication_oid)[0]
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "malformed"):
            publication._verify_publication_document(
                b"not-json", object_oid=enrolled.publication_oid,
                expected_ref=enrolled.publication_ref)
        document = json.loads(raw)
        variants = (
            ("kind", "UNKNOWN_PUBLICATION"),
            ("publication_ref", enrolled.publication_ref + "-substituted"),
            ("initialization_evidence_digest", "7" * 64),
            ("lifecycle_evidence_digest", "6" * 64),
        )
        for field, value in variants:
            with self.subTest(field=field):
                changed = copy.deepcopy(document)
                changed[field] = value
                with self.assertRaises((publication.LifecyclePublicationError,
                                        authority.LifecycleAuthorityError)):
                    publication._verify_publication_document(
                        authority.canonical_json_bytes(changed),
                        object_oid=enrolled.publication_oid,
                        expected_ref=enrolled.publication_ref)

    def test_cross_identity_substitution_fails_closed(self) -> None:
        _, enrolled = self.enroll()
        document = json.loads(
            publication._read_publication_object(self.root, enrolled.publication_oid)[0]
        )
        for field, value in (("repository", "Other/repo"), ("delivery_issue", ISSUE + 1),
                             ("lifecycle_id", "lifecycle:" + "9" * 64),
                             ("pull_request", PR + 1), ("head_sha", HEADS[5]),
                             ("terminal_authority_digest", "8" * 64)):
            with self.subTest(field=field):
                changed = copy.deepcopy(document)
                changed[field] = value
                with self.assertRaises((publication.LifecyclePublicationError,
                                        authority.LifecycleAuthorityError)):
                    publication._verify_publication_document(
                        authority.canonical_json_bytes(changed),
                        object_oid=enrolled.publication_oid,
                        expected_ref=enrolled.publication_ref)

    def test_exact_compare_and_swap_allows_only_one_concurrent_successor(self) -> None:
        _, enrolled = self.enroll()
        first = publication._write_publication_object(
            self.root, b"first orphan-safe successor", enrolled.publication_oid
        )
        second = publication._write_publication_object(
            self.root, b"second orphan-safe successor", enrolled.publication_oid
        )
        publication._cas_remote_ref(
            self.root, str(self.remote), enrolled.publication_ref, first,
            enrolled.publication_oid)
        with self.assertRaisesRegex(publication.LifecyclePublicationError,
                                    "compare-and-swap"):
            publication._cas_remote_ref(
                self.root, str(self.remote), enrolled.publication_ref, second,
                enrolled.publication_oid)
        self.assertEqual(
            publication._observe_remote_current_once(
                self.root, str(self.remote), enrolled.publication_ref), first)

    def test_current_ref_is_resolved_once_then_only_immutable_oids_are_read(self) -> None:
        self.enroll()
        original = publication._observe_remote_current_once
        calls = 0
        def counted(*args: Any, **kwargs: Any) -> str | None:
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)
        with patch.object(publication, "_observe_remote_current_once", side_effect=counted):
            publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
        self.assertEqual(calls, 1)

    def test_hostile_git_environment_cannot_redirect_publication_operations(self) -> None:
        hostile = self.root.parent / "hostile.git"
        subprocess.run(["git", "init", "--bare", "-q", str(hostile)], check=True)
        with patch.dict(os.environ, {
            "PATH": str(self.root.parent),
            "GIT_DIR": str(hostile),
            "GIT_OBJECT_DIRECTORY": str(hostile / "objects"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.alternateRefsCommand",
            "GIT_CONFIG_VALUE_0": "false",
        }):
            _, enrolled = self.enroll()
            current = publication.verify_current_lifecycle_authority(REPOSITORY, ISSUE)
        self.assertEqual(current.publication_oid, enrolled.publication_oid)

    def test_predecessor_substitution_fails_closed(self) -> None:
        chain, _ = self.enroll()
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        advanced = publication.advance_current_terminal(
            self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for())
        document = json.loads(
            publication._read_publication_object(self.root, advanced.publication_oid)[0]
        )
        document["predecessor_publication_oid"] = "9" * 40
        with self.assertRaises((publication.LifecyclePublicationError,
                                authority.LifecycleAuthorityError)):
            publication._verify_publication_document(
                authority.canonical_json_bytes(document),
                object_oid=advanced.publication_oid,
                expected_ref=advanced.publication_ref)

    def test_enrollment_cannot_be_replayed_or_advanced_from_a_stale_prefix(self) -> None:
        chain, _ = self.enroll()
        with self.assertRaisesRegex(publication.LifecyclePublicationError,
                                    "already enrolled"):
            publication.enroll_existing_lifecycle(
                self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for())
        chain.append("EXCEPTIONAL_CONTINUATION", head=HEADS[4])
        publication.advance_current_terminal(
            self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for())
        with self.assertRaisesRegex(publication.LifecyclePublicationError,
                                    "exact allowed successor"):
            publication.advance_current_terminal(
                self.root, chain.serialized(), signer_identity=SIGNER, signer=signer_for())


if __name__ == "__main__":
    main()
