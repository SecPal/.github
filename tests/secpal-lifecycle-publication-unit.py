#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for protected lifecycle publication and legacy adoption."""

from __future__ import annotations

import copy
from dataclasses import replace
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
LEGACY_SIGNER = "lifecycle-legacy-adoption@secpal.app"
OTHER_SIGNER = "other@secpal.app"
HEADS = [character * 40 for character in "abcdef1234567890"]
SECRET = b"lifecycle-publication-hermetic-signature"
BRANCH = "refs/heads/secpal-lifecycle-publications"
RULESET_ID = 21769814


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


def recovered_ready_chain(issue: int = ISSUE) -> Chain:
    chain = Chain(issue)
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

    def test_public_consumer_cannot_inject_trust_or_select_terminal(self) -> None:
        parameters = inspect.signature(publication.verify_current_lifecycle_authority).parameters
        self.assertEqual(list(parameters), ["repository", "delivery_issue", "expected"])
        for forbidden in ("signer", "remote", "publication_branch", "terminal_authority_digest"):
            self.assertNotIn(forbidden, parameters)
        writer = inspect.signature(publication.enroll_existing_lifecycle).parameters
        self.assertNotIn("repository_root", writer)
        self.assertNotIn("remote", writer)

    def test_native_mode_rejects_unanchored_fake_receipt_and_attestation(self) -> None:
        chain = recovered_ready_chain()
        native = authority.serialize_publication_lifecycle_evidence(
            lifecycle_evidence=chain.raw()
        )
        with self.assertRaisesRegex(authority.LifecycleAuthorityError, "maintained trust anchor"):
            authority.verify_lifecycle_authority_for_publication(native)
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.verify_lifecycle_authority_for_publication(chain.raw())
        with self.assertRaises(authority.LifecycleAuthorityError):
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
            publication.LifecyclePublicationError,
            "exact migration checkpoint terminal",
        ):
            publication.enroll_existing_lifecycle(
                chain.published(), signer_identity=SIGNER, signer=signer_for()
            )

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
