#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock

from scripts.secpal_pr_review import governance_amendment as amendment
from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_publication as publication

SIGNER = "lifecycle-legacy-adoption@secpal.app"
SOURCE = "aroviqen@secpal.app"
HEAD = "a" * 40
TREE = "b" * 40
PARENT = "c" * 40


def signer(payload: bytes, domain: str) -> dict[str, str]:
    return {
        "format": "ssh", "signer_identity": SIGNER,
        "value": hashlib.sha256(domain.encode() + payload).hexdigest(),
    }


def verifier(payload: bytes, signature: dict[str, str], identity: str, domain: str) -> authority.VerifiedSignature:
    if signature != signer(payload, domain) or identity != SIGNER:
        raise authority.LifecycleAuthorityError("bad fixture signature")
    return authority.VerifiedSignature(identity, "ssh")


def state() -> dict[str, object]:
    value = authority.initial_state()
    value.update(unrestricted_review_count=1, remediation_cycle_count=1)
    return value


def history() -> list[dict[str, object]]:
    return [
        {"sequence": 1, "kind": "PR_CREATED_DRAFT", "observed_at": "2026-09-18T10:00:00Z", "head_sha": PARENT, "reviewed_head_sha": None},
        {"sequence": 2, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-09-18T11:00:00Z", "head_sha": HEAD, "reviewed_head_sha": None},
    ]


def authorization() -> dict[str, object]:
    qualified = amendment._load_policy()["qualified_source"]
    changed = [
        {"path": "policies/governance-amendment-bootstrap.json", "blob_oid": "d" * 40, "mode": "100644"},
        {"path": "scripts/secpal_pr_review/governance_amendment.py", "blob_oid": "e" * 40, "mode": "100644"},
    ]
    value = {
        "schema_version": "1.0", "kind": amendment.KIND, "domain": amendment.DOMAIN,
        "purpose": amendment.PURPOSE, "repository": "SecPal/.github",
        "delivery_issue": 960, "pull_request": 961, "pull_request_state": "OPEN",
        "qualified_source": qualified, "head_sha": HEAD, "tree_sha": TREE,
        "ordered_parent_shas": [PARENT],
        "accepted_main_sha": "3887b00e1b84ef0d14ab2846507a3100512c2c28",
        "changed_files": changed, "change_digest": "",
        "source_signature": {
            "signer_identity": SOURCE,
            "signature_evidence_digest": authority.digest_json({
                "oid": HEAD, "source": "USER", "signer_identity": SOURCE,
                "classification": "LOCAL_SSH_VERIFIED",
            }),
            "verified": True,
        },
        "natural_ci": {"head_sha": HEAD, "workflow_identity": "pull-request-ci", "result": "PASS", "evidence_digest": "2" * 64},
        "independent_qualification": {"verifier_identity": "verifier", "conversation_id": "new-verifier", "head_sha": HEAD, "tree_sha": TREE, "result": "PASS", "qualification_digest": "3" * 64},
        "current_validation": {"accepted_main_sha": "3887b00e1b84ef0d14ab2846507a3100512c2c28", "policy_digest": "4" * 64, "command_set_digest": "5" * 64, "result": "PASS"},
        "feedback": {"state_digest": "6" * 64, "feedback_digest": "7" * 64, "thread_inventory_digest": "8" * 64, "material_finding_ids": []},
        "observed_pre_enrollment_history": history(), "intended_state": state(),
        "historical_evidence": amendment.historical_evidence(),
        "historical_absence_proof": {
            "head_sha": HEAD,
            "verification_authority": "PROTECTED_DELIVERY_HISTORY_AND_ARTIFACT_AUDIT",
            "history_digest": "9" * 64,
            "artifact_audit_digest": "a" * 64,
            "result": "NO_HISTORICAL_RECEIPT_ISSUED",
        },
        "architecture_necessity": {
            "existing_authority_result": "INSUFFICIENT",
            "smaller_nonrecursive_extension": "NONE",
            "recursive_self_bootstrap": "PROVEN",
            "evidence_digest": "b" * 64,
        },
        "concepts": amendment._load_policy()["concepts"],
        "human_authority_identity": amendment._load_policy()["human_authority_identity"],
        "human_authorization_digest": amendment._load_policy()["human_authorization_digest"],
        "authorization_id": amendment._load_policy()["authorization_id"],
        "bounded_uses": 1, "signer_identity": SIGNER, "signature": {},
        "authorization_digest": "",
    }
    return reseal(value)


def reseal(value: dict[str, object]) -> dict[str, object]:
    value = copy.deepcopy(value)
    value["change_digest"] = authority.digest_json({
        key: value[key] for key in (
            "repository", "delivery_issue", "pull_request", "head_sha", "tree_sha",
            "ordered_parent_shas", "accepted_main_sha", "changed_files",
        )
    })
    unsigned = {key: copy.deepcopy(item) for key, item in value.items() if key not in {"authorization_digest", "signature"}}
    value["signature"] = signer(authority.canonical_json_bytes(unsigned), amendment.DOMAIN)
    signed = {key: copy.deepcopy(item) for key, item in value.items() if key != "authorization_digest"}
    value["authorization_digest"] = authority.digest_json(signed)
    return value


class GovernanceAmendmentTests(TestCase):
    def patches(self):
        return (
            mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=SimpleNamespace(legacy_adoption_signer_identities=frozenset({SIGNER}))),
            mock.patch.object(authority, "_policy_signature_verifier", return_value=verifier),
        )

    def test_exact_amendment_creates_truthful_nullable_exact_adoption(self) -> None:
        trust = authority._load_lifecycle_trust_policy("SecPal/.github")
        value = authorization()
        first, second = self.patches()
        with first, second:
            verified = amendment.verify(value)
            self.assertTrue(amendment.is_verified(verified))
            with mock.patch.object(authority, "verify_commit_signatures", return_value=[{"oid": HEAD, "source": "USER", "signer_identity": SOURCE, "classification": "LOCAL_SSH_VERIFIED"}]):
                external = authority.authenticate_exact_state_adoption_external_evidence(
                    repository="SecPal/.github", delivery_issue=960, pull_request=961,
                    head_sha=HEAD, tree_sha=TREE, pull_request_state="OPEN",
                    commit_signature_evidence={"oid": HEAD}, validation_evidence=None,
                    observed_pre_enrollment_history=history(), intended_state=state(),
                    governance_amendment_authorization=value,
                )
            evidence = authority.create_exact_state_adoption_evidence(
                verified_external_evidence=external,
                adoption_timestamp="2026-09-18T11:00:01Z",
            )
            self.assertEqual(evidence["proof_version"], "4.0")
            self.assertIsNone(evidence["validation_receipt_digest"])
            self.assertIsNone(evidence["source_validation_evidence_digest"])
            self.assertEqual(evidence["historical_evidence"], amendment.historical_evidence())
            self.assertEqual(
                authority.exact_state_adoption_historical_evidence(evidence),
                amendment.historical_evidence(),
            )
            exact_authorization = authority.create_exact_state_adoption_authorization(
                adoption_evidence=evidence, authorization_id="adopt-960",
                bounded_uses=1, signer_identity=SIGNER, signer=signer,
            )
            proof = authority.create_exact_state_adoption_proof(
                adoption_evidence=evidence, authorization=exact_authorization,
                signer_identity=SIGNER, signer=signer,
            )
            result = authority.verify_exact_state_adoption_proof(proof)
            published = authority.verify_lifecycle_authority_for_publication(
                authority.serialize_exact_state_adoption_evidence(
                    exact_state_adoption_proof=proof
                )
            )
            bundle = authority.serialize_exact_state_adoption_evidence(
                exact_state_adoption_proof=proof
            )
        self.assertEqual(result.state, state())
        self.assertEqual(published.authority_digest, result.authority_digest)
        self.assertIsNone(result.validation_receipt_digest)
        self.assertEqual(result.adoption_source_evidence_digest, value["authorization_digest"])
        with tempfile.TemporaryDirectory() as directory:
            remote = Path(directory) / "publication.git"
            subprocess.run(
                ["git", "init", "--bare", "--quiet", str(remote)], check=True
            )
            publication_trust = replace(
                trust,
                publication_remote_url=str(remote),
                publication_signer_identities=frozenset({SIGNER}),
            )
            with mock.patch.object(
                authority, "_load_lifecycle_trust_policy",
                return_value=publication_trust,
            ), mock.patch.object(
                authority, "_policy_signature_verifier", return_value=verifier
            ), mock.patch.object(publication, "_verify_live_protection"):
                enrolled = publication.enroll_existing_lifecycle(
                    bundle, signer_identity=SIGNER, signer=signer
                )
                self.assertEqual(
                    enrolled.lifecycle.authority_digest, result.authority_digest
                )
                with self.assertRaisesRegex(
                    publication.LifecyclePublicationError, "enrolled"
                ):
                    publication.enroll_existing_lifecycle(
                        bundle, signer_identity=SIGNER, signer=signer
                    )

    def test_scope_and_absence_substitutions_fail_closed(self) -> None:
        mutations = {
            "repository": lambda v: v.update(repository="SecPal/api"),
            "issue": lambda v: v.update(delivery_issue=959),
            "pull request": lambda v: v.update(pull_request=962),
            "head": lambda v: v.update(head_sha="9" * 40),
            "tree": lambda v: v.update(tree_sha="9" * 40),
            "parents": lambda v: v.update(ordered_parent_shas=["9" * 40]),
            "source signer": lambda v: v["source_signature"].update(signer_identity="other"),
            "stale main": lambda v: v.update(accepted_main_sha="9" * 40),
            "caller absence": lambda v: v["historical_evidence"].update(state="UNAVAILABLE"),
            "absence receipt": lambda v: v["historical_evidence"].update(validation_receipt_digest="9" * 64),
            "absence source digest": lambda v: v["historical_evidence"].update(source_validation_evidence_digest="9" * 64),
            "absence attestation digest": lambda v: v["historical_evidence"].update(final_attestation_digest="9" * 64),
            "caller asserted absence": lambda v: v["historical_absence_proof"].update(verification_authority="CALLER_ASSERTION"),
            "unproven recursion": lambda v: v["architecture_necessity"].update(recursive_self_bootstrap="ASSERTED"),
            "unknown reason": lambda v: v.update(purpose="OTHER"),
            "failed validation": lambda v: v["current_validation"].update(result="FAIL"),
            "blocking feedback": lambda v: v["feedback"].update(material_finding_ids=["finding"]),
            "other qualification": lambda v: v["qualified_source"].update(head_sha="9" * 40),
            "counter reset": lambda v: v["intended_state"].update(remediation_cycle_count=0),
            "fabricated Ready": lambda v: v["intended_state"].update(draft=False, ready=True, ready_transition_count=1),
            "Cycle 3": lambda v: v["intended_state"].update(cycle_3_absent=False),
            "cross delivery": lambda v: v.update(authorization_id="governance-amendment:other"),
            "product source": lambda v: v["changed_files"].append({"path":"src/runtime.py","blob_oid":"f"*40,"mode":"100644"}),
            "second use": lambda v: v.update(bounded_uses=2),
        }
        for label, mutate in mutations.items():
            changed = authorization(); mutate(changed); changed = reseal(changed)
            if label == "parents":
                # Final topology is dynamically authorized. Exercise cross-topology
                # replay by tampering after the exact signed authorization exists.
                changed["ordered_parent_shas"] = ["8" * 40]
            first, second = self.patches()
            with self.subTest(label=label), first, second, self.assertRaises((amendment.GovernanceAmendmentError, authority.LifecycleAuthorityError)):
                amendment.verify(changed)

    def test_policy_requires_the_accepted_registry_entry(self) -> None:
        value = authorization()
        first, second = self.patches()
        real_loads = amendment.json.loads

        def unregistered(raw: str):
            parsed = real_loads(raw)
            if isinstance(parsed, dict) and "repositories" in parsed:
                parsed["repositories"][0].pop("governance_amendment_policy")
            return parsed

        with first, second, mock.patch.object(amendment.json, "loads", side_effect=unregistered):
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "not registered"
            ):
                amendment.verify(value)

    def test_candidate_local_and_mixed_historical_authority_fail_closed(self) -> None:
        value = authorization()
        with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=SimpleNamespace(legacy_adoption_signer_identities=frozenset({SIGNER}))), mock.patch.object(authority, "_policy_signature_verifier", return_value=lambda *_: (_ for _ in ()).throw(authority.LifecycleAuthorityError("untrusted"))):
            with self.assertRaises(amendment.GovernanceAmendmentError):
                amendment.verify(value)
        first, second = self.patches()
        with first, second, self.assertRaises(authority.LifecycleAuthorityError):
            authority.authenticate_exact_state_adoption_external_evidence(
                repository="SecPal/.github", delivery_issue=960, pull_request=961,
                head_sha=HEAD, tree_sha=TREE, pull_request_state="OPEN",
                commit_signature_evidence={"oid": HEAD}, validation_evidence=SimpleNamespace(),
                observed_pre_enrollment_history=history(), intended_state=state(),
                governance_amendment_authorization=value,
            )


if __name__ == "__main__":
    main()
