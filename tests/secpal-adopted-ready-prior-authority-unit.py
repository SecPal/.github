#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Exact-State-Adoption v3 Ready prior-authority bridge regressions."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase, main, mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.secpal_pr_review import legacy_enrolled_package_loss as legacy_loss

SPEC = importlib.util.spec_from_file_location(
    "secpal_adopted_ready_prior_authority_actions",
    ROOT / "scripts/secpal-pr-review-actions.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load action helper")
actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actions)
fast_path = actions.fast_path
lifecycle_authority, lifecycle_publication = (
    actions._load_lifecycle_publication_helpers()
)

REPOSITORY = "SecPal/.github"
ISSUE = 827
PR = 830
HEAD = "7fd0467c321f1c2b9a06494f4a0c46531c9cc006"
TREE = "ab8da939ca30a3b906f22c471031083f7132ff94"
PARENT = "f6982d0808cace5a142445b52454dc83515fa297"
SIGNER = "aroviqen@secpal.app"
PROOF = "8b6494b62e0b60ff5a5bfb70d0433196d7db3fed309a34c9392363ccff53c972"
AUTHORIZATION = "a4b5f488430b349370a309d99744323aea1776cc3975928e079f36026a090e4c"
LOSS = "996c5a8af805f406e02ebb0cac7e3dc3eb30e9a335c1782262c54b410282b5a2"
REVIEWED_STATE = "6" * 64
REVIEWED_FEEDBACK = "7" * 64
CURRENT_SAFETY = {
    "receipt_digest": "8" * 64,
    "reviewed_state_digest": REVIEWED_STATE,
    "reviewed_feedback_digest": REVIEWED_FEEDBACK,
}
SAFETY = fast_path.digest_json(CURRENT_SAFETY)
BUDGET = "cb9b4be5ef026a088ec33eeb367c32db0b99bc7363241fc4b3ebbd805a4ecf21"
ENROLLMENT_OID = "37ffb1110e5f95829bcc3612ede8ac48092744fa"
ENROLLMENT_DIGEST = "aa4b1f7598e8bc4e3c044f698c1d79f9b6725b5ecdc11195ff510844b4e57d7f"
CURRENT_OID = "7f2390b9a98650a833f21c765b02f7af89814aa0"
CURRENT_DIGEST = "1cbd45b2c6498cb4cb7a28fc3afe8066fc981cc9b727b56de08e2f53f16422a7"
READY_AUTHORIZATION = "authorization:1a6ec11a0232ef467c41236e4349a942872bc7346748b637c35c43f45e3a2c2c"
READY_EVENT = "a92ef35d8471ff3ed5913e07c8498d3565afb0232633901eb3ae3dba67588ca5"
LEGACY_ISSUE = 792
LEGACY_PR = 793
LEGACY_HEAD = "5b8a661cec134256cf31273ab30c38b048999978"
LEGACY_TREE = "c98663dbcde480c1dcac7858595dabff3cb2fd2c"
LEGACY_PARENT = "401f0886fdfee9525ced24f703e31087dfa35096"
LEGACY_REVIEWED_HEAD = "15b0934cc8bd00055311c65eeb9a5e3144e4fe8a"
LEGACY_LIFECYCLE = (
    "lifecycle-adoption:"
    "67799903a7b2c1ffc6e0fafaf18d3127c39b0d02c94928ec4ec33396e21e85f6"
)
LEGACY_PROOF = "2cc834e6a37ae41038838f1d663b0ac787a50b2ee57df5fb115d27dc8060f1d1"
LEGACY_AUTHORIZATION = (
    "9ae01fca3801cfaf3d74d41c0b06b4ebed400d79e21e18e0fe23b537be2b99d1"
)
LEGACY_SIGNATURE = (
    "03ec1b0b217ea7ebecf32e80bbdde28ba07d9c0029bd3a491c9e757c19cea124"
)
LEGACY_REGISTRY = (
    "38629c17e2397bfc1df44e5fa65fc176326f47fdf9dbfee98d1de52ecd093340"
)
LEGACY_COMMAND_SET = (
    "15d370f613fb13d39bcf5136ffb4ebae298eb78e0acfaf18635253571f9ff12a"
)
LEGACY_SOURCE_VALIDATION = (
    "951af9087c60ac6da16f8f94f6bde89a42035938a0377ea94a2e583f28d39259"
)
LEGACY_RECEIPT = (
    "008128e9edf6b3ad9b166f4641698a6849593006a70a8df09afb65b66dd81065"
)
LEGACY_ATTESTATION = (
    "c824f0f207b8aae00a8b2019ea6e4870279524eb884fcba0af4bff6c322f6b42"
)
LEGACY_CURRENT_OID = "afa542a289bb43cecac326b24e041c3fb68bad7a"
LEGACY_CURRENT_DIGEST = (
    "275e56d899450fef017fadc9913cdb3062b6650ceea1f3fffd11e5a067aa9cec"
)


def state() -> dict[str, object]:
    return {
        "draft": False,
        "ready": True,
        "unrestricted_review_count": 1,
        "remediation_cycle_count": 2,
        "ready_transition_count": 1,
        "ready_history": [{
            "sequence": 1,
            "transition_kind": "DRAFT_TO_READY",
            "event_authorization_digest": READY_EVENT,
        }],
        "exceptional_recovery_count": 0,
        "exceptional_recovery_history": [],
        "exceptional_continuation_count": 0,
        "exceptional_continuation_history": [],
        "cycle_3_absent": True,
    }


def proof() -> dict[str, object]:
    return {
        "schema_version": "3.0",
        "proof_version": "3.0",
        "repository": REPOSITORY,
        "delivery_issue": ISSUE,
        "pull_request": PR,
        "head_sha": HEAD,
        "tree_sha": TREE,
        "historical_proof_mode": "exact_state_adoption",
        "commit_signature_evidence_digest": "1" * 64,
        "validation_receipt_digest": "2" * 64,
        "source_validation_evidence_digest": SAFETY,
        "observed_history_digest": "3" * 64,
        "intended_state_digest": "4" * 64,
        "ordinary_lifecycle_events": [],
        "head_advanced_count": 2,
        "head_advanced_history_digest": "5" * 64,
        "supporting_evidence_digests": [BUDGET],
        "proof_digest": PROOF,
        "authorization_digest": AUTHORIZATION,
        "authorization": {"authorization_id": "adopt:827:830"},
        "validation_evidence_loss_admission": {
            "admission_id": "pre-enrollment-validation-loss:827:830",
            "admission_digest": LOSS,
            "repository": REPOSITORY,
            "delivery_issue": ISSUE,
            "pull_request": PR,
            "head_sha": HEAD,
            "tree_sha": TREE,
            "parent_sha": PARENT,
            "source_signer_identity": SIGNER,
            "commit_signature_evidence_digest": "1" * 64,
            "historical_validation_receipt_digest": "2" * 64,
            "historical_package_status": "UNAVAILABLE",
            "historical_final_attestation_digest": None,
            "historical_bytes_reconstructed": False,
            "current_safety": CURRENT_SAFETY,
        },
        "review_budget_consumption_admission": {
            "admission_id": "review-budget:827:830",
            "admission_digest": BUDGET,
        },
    }


def published(proof_value: dict[str, object] | None = None) -> SimpleNamespace:
    lifecycle = SimpleNamespace(
        repository=REPOSITORY,
        delivery_issue=ISSUE,
        pull_request=PR,
        head_sha=HEAD,
        tree_sha=TREE,
        lifecycle_id="lifecycle-adoption:" + "7" * 64,
        authority_digest="8" * 64,
        historical_proof_mode="exact_state_adoption",
        state=state(),
    )
    bundle = {
        "exact_state_adoption_proof": proof_value or proof(),
        "transition_authorizations": [{
            "event_id": READY_AUTHORIZATION,
            "event_digest": READY_EVENT,
            "transition_kind": "DRAFT_TO_READY",
            "predecessor_authority_digest": PROOF,
            "predecessor_head_sha": HEAD,
            "resulting_head_sha": HEAD,
        }],
        "authority_chain": [{"authority_digest": lifecycle.authority_digest}],
    }
    return SimpleNamespace(
        publication_oid=CURRENT_OID,
        publication_digest=CURRENT_DIGEST,
        predecessor_publication_oid=ENROLLMENT_OID,
        lifecycle=lifecycle,
        serialized_lifecycle_evidence=(json.dumps(bundle).encode() + b"\n"),
    )


def transition(current: SimpleNamespace | None = None) -> SimpleNamespace:
    current = current or published()
    predecessor = SimpleNamespace(
        publication_oid=ENROLLMENT_OID,
        publication_digest=ENROLLMENT_DIGEST,
        lifecycle=SimpleNamespace(authority_digest=PROOF, head_sha=HEAD),
    )
    return SimpleNamespace(
        predecessor=predecessor,
        successor=current,
        event_id=READY_AUTHORIZATION,
        event_digest=READY_EVENT,
        transition_kind="DRAFT_TO_READY",
        predecessor_authority_digest=PROOF,
        predecessor_head_sha=HEAD,
        resulting_head_sha=HEAD,
    )


def legacy_proof() -> dict[str, object]:
    intended_state = state()
    intended_state["ready_history"] = [{
        "sequence": 1,
        "transition_kind": "DRAFT_TO_READY",
        "observation_digest": (
            "b337d3925348e38a5df9fffad029964bd3f1bac71b1cdb8205581f7a50bd16c3"
        ),
    }]
    return {
        "schema_version": "1.0",
        "proof_version": "1.0",
        "repository": REPOSITORY,
        "delivery_issue": LEGACY_ISSUE,
        "pull_request": LEGACY_PR,
        "head_sha": LEGACY_HEAD,
        "tree_sha": LEGACY_TREE,
        "historical_proof_mode": "exact_state_adoption",
        "commit_signature_evidence_digest": LEGACY_SIGNATURE,
        "validation_receipt_digest": LEGACY_RECEIPT,
        "source_validation_evidence_digest": LEGACY_SOURCE_VALIDATION,
        "adoption_source_evidence_digest": LEGACY_ATTESTATION,
        "observed_history_digest": (
            "5728c21f8af3f8eb73d852659f258d9bc19cfa2ee537353dea03497faf93c10d"
        ),
        "intended_state_digest": (
            "f23d8736597f7c9af4e8311beeadc4660c14a5a5419880e9ca50c8198008d6b9"
        ),
        "ordinary_lifecycle_events": [],
        "head_advanced_count": 0,
        "head_advanced_history_digest": (
            "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
        ),
        "supporting_evidence_digests": sorted([
            LEGACY_RECEIPT,
            LEGACY_SIGNATURE,
            "5728c21f8af3f8eb73d852659f258d9bc19cfa2ee537353dea03497faf93c10d",
            LEGACY_SOURCE_VALIDATION,
            LEGACY_ATTESTATION,
        ]),
        "proof_digest": LEGACY_PROOF,
        "authorization_digest": LEGACY_AUTHORIZATION,
        "authorization": {
            "authorization_id": "sec792-exact-adoption-67799903a7b2c1ff-20260901T224824Z",
        },
        "intended_state": intended_state,
    }


def legacy_published() -> SimpleNamespace:
    proof_value = legacy_proof()
    lifecycle = SimpleNamespace(
        repository=REPOSITORY,
        delivery_issue=LEGACY_ISSUE,
        pull_request=LEGACY_PR,
        head_sha=LEGACY_HEAD,
        tree_sha=LEGACY_TREE,
        lifecycle_id=LEGACY_LIFECYCLE,
        authority_digest=LEGACY_PROOF,
        historical_proof_mode="exact_state_adoption",
        state=copy.deepcopy(proof_value["intended_state"]),
        validation_receipt_digest=LEGACY_RECEIPT,
        source_validation_evidence_digest=LEGACY_SOURCE_VALIDATION,
        adoption_source_evidence_digest=LEGACY_ATTESTATION,
    )
    bundle = {
        "exact_state_adoption_proof": proof_value,
        "transition_authorizations": [],
        "authority_chain": [],
    }
    return SimpleNamespace(
        publication_oid=LEGACY_CURRENT_OID,
        publication_digest=LEGACY_CURRENT_DIGEST,
        predecessor_publication_oid=None,
        lifecycle=lifecycle,
        serialized_lifecycle_evidence=(json.dumps(bundle).encode() + b"\n"),
    )


def legacy_loss_authentication() -> dict[str, object]:
    current = legacy_published()
    proof_value = legacy_proof()
    safety = {
        "accepted_main_sha": "9" * 40,
        "repository_admission_digest": "a" * 64,
        "current_command_set_digest": "b" * 64,
        "current_signature_policy_digest": "c" * 64,
        "source_signer_identity": SIGNER,
        "ready_prior_authority_schema_version": "1.2",
        "ready_integration_schema_version": "1.2",
        "operation": "READY_INTEGRATION_PRIOR_AUTHORITY",
        "trust_source": "AUTHENTICATED_PROTECTED_MAIN",
        "integration_transition": "HEAD_ADVANCED",
        "reviewed_state_digest": REVIEWED_STATE,
        "reviewed_feedback_digest": REVIEWED_FEEDBACK,
        "thread_resolution_authority": 0,
        "recovery_consumed": False,
        "successful_result": True,
    }
    safety["current_safety_digest"] = fast_path.digest_json(safety)
    return {
        "schema_version": "1.0",
        "kind": "SECPAL_LEGACY_ENROLLED_PACKAGE_LOSS_AUTHENTICATION",
        "domain": "secpal.legacy-enrolled-package-loss-authentication/v1",
        "authority_temporality": "AUTHENTICATED_NOW_NOT_HISTORICAL",
        "repository": REPOSITORY,
        "delivery_issue": LEGACY_ISSUE,
        "pull_request": LEGACY_PR,
        "lifecycle_id": LEGACY_LIFECYCLE,
        "historical_proof_mode": "exact_state_adoption",
        "proof_version": "1.0",
        "adoption_proof_digest": LEGACY_PROOF,
        "adoption_authorization_id": proof_value["authorization"]["authorization_id"],
        "adoption_authorization_digest": LEGACY_AUTHORIZATION,
        "current_authority_digest": LEGACY_PROOF,
        "current_publication_oid": LEGACY_CURRENT_OID,
        "current_publication_digest": LEGACY_CURRENT_DIGEST,
        "head_sha": LEGACY_HEAD,
        "tree_sha": LEGACY_TREE,
        "parent_sha": LEGACY_PARENT,
        "source_signer_identity": SIGNER,
        "commit_signature_evidence_digest": LEGACY_SIGNATURE,
        "historical_provider_summary_digest": "1" * 64,
        "evidence_time_registry_digest": LEGACY_REGISTRY,
        "historical_command_set_digest": LEGACY_COMMAND_SET,
        "source_validation_evidence_digest": LEGACY_SOURCE_VALIDATION,
        "historical_validation_receipt_digest": LEGACY_RECEIPT,
        "historical_final_attestation_digest": LEGACY_ATTESTATION,
        "observed_history_digest": proof_value["observed_history_digest"],
        "intended_state_digest": proof_value["intended_state_digest"],
        "head_advanced_count": 0,
        "head_advanced_history_digest": proof_value["head_advanced_history_digest"],
        "accepted_main_sha": "9" * 40,
        "loss_policy_record_digest": "d" * 64,
        "package_store_survey_digest": "e" * 64,
        "historical_package_status": "UNAVAILABLE",
        "historical_bytes_reconstructed": False,
        "current_safety": safety,
        "thread_resolution_authority": 0,
        "recovery_consumed": False,
        "authentication_digest": "f" * 64,
    }
class AdoptedReadyPriorAuthorityTests(TestCase):
    def test_authority_imports_ignore_repository_bytecode_caches(self) -> None:
        cache_root = Path(actions.sys.pycache_prefix).resolve(strict=True)
        self.assertFalse(cache_root.is_relative_to(ROOT))

    def derive(
        self,
        current: SimpleNamespace | None = None,
        *,
        reviewed_state_digest: str | None = None,
        reviewed_feedback_digest: str | None = None,
    ) -> dict[str, object]:
        current = current or published()
        with (
            mock.patch.object(
                actions,
                "_load_lifecycle_publication_helpers",
                return_value=(lifecycle_authority, lifecycle_publication),
            ),
            mock.patch.object(
                actions,
                "_require_accepted_main_bridge_source",
                return_value="9" * 40,
            ),
            mock.patch.object(lifecycle_publication, "verify_current_lifecycle_authority", return_value=current),
            mock.patch.object(lifecycle_publication, "_verify_historical_lifecycle_transition", return_value=transition(current)),
            mock.patch.object(lifecycle_authority, "verify_exact_state_adoption_proof", return_value=current.lifecycle),
            mock.patch.object(
                actions,
                "_verified_prior_delivery_commit",
                return_value={
                    "parent_sha": PARENT,
                    "tree_sha": TREE,
                    "signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
                },
            ),
            mock.patch.object(
                lifecycle_authority,
                "authenticate_legacy_enrolled_validation_evidence_loss",
                side_effect=lifecycle_authority.LifecycleAuthorityError(
                    "no maintained legacy loss"
                ),
            ),
        ):
            return actions._derive_exact_state_adoption_ready_prior_authority(
                repository_root=ROOT.parent,
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                binding={"signature_policy": {"accepted_formats": ["ssh"]}},
                reviewed_state_digest=reviewed_state_digest,
                reviewed_feedback_digest=reviewed_feedback_digest,
            )

    def derive_legacy(
        self,
        current: SimpleNamespace | None = None,
        authenticated_loss: dict[str, object] | None = None,
        *,
        reviewed_state_digest: str | None = None,
        reviewed_feedback_digest: str | None = None,
    ) -> dict[str, object]:
        current = current or legacy_published()
        authenticated_loss = authenticated_loss or legacy_loss_authentication()
        with (
            mock.patch.object(
                actions,
                "_load_lifecycle_publication_helpers",
                return_value=(lifecycle_authority, lifecycle_publication),
            ),
            mock.patch.object(
                actions,
                "_require_accepted_main_bridge_source",
                return_value="9" * 40,
            ),
            mock.patch.object(
                lifecycle_publication,
                "verify_current_lifecycle_authority",
                return_value=current,
            ),
            mock.patch.object(
                lifecycle_authority,
                "verify_exact_state_adoption_proof",
                return_value=current.lifecycle,
            ),
            mock.patch.object(
                actions,
                "_verified_prior_delivery_commit",
                return_value={
                    "parent_sha": LEGACY_PARENT,
                    "tree_sha": LEGACY_TREE,
                    "signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
                },
            ),
            mock.patch.object(
                lifecycle_authority,
                "authenticate_legacy_enrolled_validation_evidence_loss",
                return_value=object(),
            ),
            mock.patch.object(
                lifecycle_authority,
                "legacy_enrolled_validation_evidence_loss_binding",
                return_value=authenticated_loss,
            ),
        ):
            return actions._derive_exact_state_adoption_ready_prior_authority(
                repository_root=ROOT.parent,
                repository=REPOSITORY,
                delivery_issue=LEGACY_ISSUE,
                pull_request=LEGACY_PR,
                binding={"signature_policy": {"accepted_formats": ["ssh"]}},
                reviewed_state_digest=reviewed_state_digest,
                reviewed_feedback_digest=reviewed_feedback_digest,
            )

    def test_target_827_shape_derives_v3_ready_prior_authority(self) -> None:
        manifest = self.derive()
        self.assertEqual(manifest["schema_version"], "1.2")
        self.assertEqual(manifest["source_authority_mode"], "EXACT_STATE_ADOPTION_V3")
        self.assertEqual(manifest["prior_delivery_head_sha"], HEAD)
        self.assertEqual(manifest["prior_delivery_tree_sha"], TREE)
        self.assertEqual(manifest["source_authority"]["source_parent_sha"], PARENT)
        self.assertEqual(manifest["source_authority"]["adoption_proof_digest"], PROOF)
        self.assertEqual(manifest["source_authority"]["loss_admission_digest"], LOSS)
        self.assertEqual(manifest["source_authority"]["review_budget_admission_digest"], BUDGET)
        self.assertEqual(manifest["source_authority"]["enrollment_publication"]["object_oid"], ENROLLMENT_OID)
        self.assertEqual(manifest["lifecycle"]["ready_transition_count"], 1)
        self.assertEqual(manifest["historical_companions"], {
            "reviewed_state_bytes": "UNAVAILABLE",
            "validation_receipt_bytes": "UNAVAILABLE",
            "final_attestation_bytes": "UNAVAILABLE",
            "historical_bytes_reconstructed": False,
        })
        self.assertEqual(
            fast_path.normalize_ready_integration_prior_authority(manifest), manifest
        )

    def test_target_792_shape_derives_authenticated_legacy_loss_authority(self) -> None:
        manifest = self.derive_legacy()
        self.assertEqual(manifest["schema_version"], "1.2")
        self.assertEqual(
            manifest["source_authority_mode"],
            "EXACT_STATE_ADOPTION_LEGACY_ENROLLED_LOSS",
        )
        self.assertEqual(manifest["prior_delivery_head_sha"], LEGACY_HEAD)
        self.assertEqual(manifest["prior_delivery_tree_sha"], LEGACY_TREE)
        self.assertEqual(manifest["prior_validation_receipt_digest"], LEGACY_RECEIPT)
        self.assertEqual(manifest["prior_final_attestation_digest"], LEGACY_ATTESTATION)
        self.assertEqual(manifest["lifecycle"]["identity"], LEGACY_LIFECYCLE)
        self.assertEqual(manifest["publication"], {
            "object_oid": LEGACY_CURRENT_OID,
            "publication_digest": LEGACY_CURRENT_DIGEST,
        })
        self.assertEqual(manifest["historical_companions"], {
            "reviewed_state_bytes": "UNAVAILABLE",
            "validation_receipt_bytes": "UNAVAILABLE",
            "final_attestation_bytes": "UNAVAILABLE",
            "historical_bytes_reconstructed": False,
        })
        self.assertEqual(
            fast_path.normalize_ready_integration_prior_authority(manifest), manifest
        )

    def test_legacy_loss_exact_delivery_and_digest_bindings_fail_closed(self) -> None:
        mutations = {
            "repository": "SecPal/api",
            "delivery_issue": 791,
            "pull_request": 794,
            "lifecycle_id": "lifecycle-adoption:" + "0" * 64,
            "historical_proof_mode": "native_lifecycle",
            "proof_version": "2.0",
            "current_publication_oid": "0" * 40,
            "current_publication_digest": "0" * 64,
            "head_sha": "0" * 40,
            "tree_sha": "0" * 40,
            "parent_sha": "0" * 40,
            "source_signer_identity": "alternate@secpal.app",
            "commit_signature_evidence_digest": "0" * 64,
            "source_validation_evidence_digest": "0" * 64,
            "historical_validation_receipt_digest": "0" * 64,
            "historical_final_attestation_digest": "0" * 64,
            "observed_history_digest": "0" * 64,
            "intended_state_digest": "0" * 64,
            "head_advanced_count": 1,
            "head_advanced_history_digest": "0" * 64,
            "adoption_proof_digest": "0" * 64,
            "adoption_authorization_id": "invented:792",
            "adoption_authorization_digest": "0" * 64,
            "accepted_main_sha": "0" * 40,
            "historical_package_status": "NOT_SUPPLIED",
            "historical_bytes_reconstructed": True,
            "thread_resolution_authority": 1,
            "recovery_consumed": True,
        }
        for field, value in mutations.items():
            authentication = legacy_loss_authentication()
            authentication[field] = value
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                self.derive_legacy(authenticated_loss=authentication)

    def test_legacy_loss_current_safety_is_accepted_main_selected(self) -> None:
        mutations = {
            "accepted_main_sha": "0" * 40,
            "operation": "THREAD_RESOLUTION",
            "trust_source": "CANDIDATE",
            "integration_transition": "PR_REBOUND",
            "ready_prior_authority_schema_version": "1.1",
            "ready_integration_schema_version": "1.1",
            "thread_resolution_authority": 1,
            "recovery_consumed": True,
            "successful_result": False,
        }
        for field, value in mutations.items():
            authentication = legacy_loss_authentication()
            authentication["current_safety"][field] = value
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                self.derive_legacy(authenticated_loss=authentication)

    def test_legacy_loss_lifecycle_is_finite_and_has_no_ready_churn(self) -> None:
        mutations = {
            "draft": True,
            "ready": False,
            "unrestricted_review_count": 2,
            "remediation_cycle_count": 3,
            "ready_transition_count": 2,
            "exceptional_recovery_count": 1,
            "exceptional_continuation_count": 1,
            "cycle_3_absent": False,
        }
        for field, value in mutations.items():
            current = legacy_published()
            current.lifecycle.state[field] = value
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                self.derive_legacy(current=current)
        current = legacy_published()
        current.lifecycle.state["ready_history"][0]["transition_kind"] = (
            "READY_TO_DRAFT"
        )
        with self.assertRaises(fast_path.SecurityBlocker):
            self.derive_legacy(current=current)

    def test_legacy_loss_reviewed_predecessor_matches_current_safety(self) -> None:
        self.derive_legacy(
            reviewed_state_digest=REVIEWED_STATE,
            reviewed_feedback_digest=REVIEWED_FEEDBACK,
        )
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "reviewed predecessor"
        ):
            self.derive_legacy(
                reviewed_state_digest="0" * 64,
                reviewed_feedback_digest=REVIEWED_FEEDBACK,
            )

    def test_legacy_loss_normalization_rejects_laundering_and_thread_authority(self) -> None:
        manifest = self.derive_legacy()
        cases = [
            ("historical_companions", "reviewed_state_bytes", "AVAILABLE"),
            ("historical_companions", "historical_bytes_reconstructed", True),
            ("source_authority", "thread_resolution_authority", 1),
            ("source_authority", "recovery_consumed", True),
            ("source_authority", "package_store_survey_digest", "0" * 64),
        ]
        for section, field, value in cases:
            candidate = copy.deepcopy(manifest)
            candidate[section][field] = value
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                actions._require_exact_adopted_ready_manifest(candidate, manifest)

    def test_legacy_loss_store_survey_is_bounded_and_fail_closed(self) -> None:
        record = legacy_loss._validate_record(
            json.loads(
                (ROOT / "policies/legacy-enrolled-package-loss.json").read_text()
            )["authentications"][0]
        )
        current = SimpleNamespace(
            publication_oid=LEGACY_CURRENT_OID,
            publication_digest=LEGACY_CURRENT_DIGEST,
        )

        def git_projection(
            _root: Path, arguments: list[str], _label: str
        ) -> str:
            if arguments == ["remote", "get-url", "origin"]:
                return "git@github.com:SecPal/.github.git\n"
            if arguments[0] == "show":
                return ".context/\n"
            head = arguments[-1].split("^", 1)[0]
            history = next(item for item in record["source_history"] if item["head_sha"] == head)
            if arguments[0] == "rev-parse":
                return history["tree_sha"] + "\n"
            if arguments[0] == "rev-list":
                return f'{head} {history["parent_sha"]}\n'
            if arguments[0] == "ls-tree":
                return ".gitignore\nAGENTS.md\n"
            raise AssertionError(arguments)

        with mock.patch.object(
            legacy_loss, "_git_text", side_effect=git_projection
        ):
            survey = legacy_loss._survey_package_stores(ROOT, record, current)
        self.assertEqual(survey["result"], "UNAVAILABLE")
        self.assertFalse(survey["historical_bytes_reconstructed"])

        def tracked_artifact(
            root: Path, arguments: list[str], label: str
        ) -> str:
            result = git_projection(root, arguments, label)
            if arguments[0] == "ls-tree":
                return result + ".context/validation-receipt.json\n"
            return result

        with mock.patch.object(
            legacy_loss, "_git_text", side_effect=tracked_artifact
        ), self.assertRaisesRegex(
            legacy_loss.authority.LifecycleAuthorityError,
            "bytes exist or a maintained store is unsurveyed",
        ):
            legacy_loss._survey_package_stores(ROOT, record, current)

    def test_legacy_loss_policy_digest_binds_every_historical_identity(self) -> None:
        source = json.loads(
            (ROOT / "policies/legacy-enrolled-package-loss.json").read_text()
        )["authentications"][0]
        legacy_loss._validate_record(source)
        for field in (
            "evidence_time_registry_digest",
            "historical_command_set_digest",
            "source_validation_evidence_digest",
            "historical_validation_receipt_digest",
            "historical_final_attestation_digest",
            "historical_provider_summary_digest",
            "current_publication_digest",
            "package_store_survey_digest",
        ):
            changed = copy.deepcopy(source)
            changed[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(
                legacy_loss.authority.LifecycleAuthorityError
            ):
                legacy_loss._validate_record(changed)
        changed = copy.deepcopy(source)
        changed["persistence_contract"]["unsurveyed_maintained_stores"] = [
            "CALLER_WORKSPACE"
        ]
        with self.assertRaisesRegex(
            legacy_loss.authority.LifecycleAuthorityError,
            "persistence boundary",
        ):
            legacy_loss._validate_record(changed)

    def test_legacy_provider_summary_requires_exact_pinned_bytes(self) -> None:
        body = "\n".join([
            fast_path.CODEX_REVIEW_SUMMARY_MARKER,
            "| Review | Status | Commit | Review trigger |",
            "| --- | --- | --- | --- |",
            (
                "| 📝 **Code Review** | ✅ **Completed** | "
                f"`{LEGACY_REVIEWED_HEAD[:7]}` | Manual request |"
            ),
        ])
        binding = legacy_loss.VerifiedLegacyProviderHeadBinding(
            repository=REPOSITORY,
            delivery_issue=LEGACY_ISSUE,
            pull_request=LEGACY_PR,
            lifecycle_id=LEGACY_LIFECYCLE,
            current_head_sha=LEGACY_HEAD,
            provider_head_sha=LEGACY_REVIEWED_HEAD,
            current_authority_digest=LEGACY_PROOF,
            current_publication_oid=LEGACY_CURRENT_OID,
            current_publication_digest=LEGACY_CURRENT_DIGEST,
            adoption_proof_digest=LEGACY_PROOF,
            historical_provider_summary_digest=fast_path.digest_text(body),
        )
        with mock.patch.object(
            legacy_loss.VerifiedLegacyProviderHeadBinding,
            "_reauthenticate",
        ):
            binding.verify_historical_provider_summary(
                body=body,
                repository=REPOSITORY,
                pull_request=LEGACY_PR,
                current_head_sha=LEGACY_HEAD,
            )
            actions._require_review_providers_terminal(
                {
                    "headRefOid": LEGACY_HEAD,
                    "isDraft": False,
                    "comments": {
                        "nodes": [{
                            "body": body,
                            "author": {"login": "chatgpt-codex-connector"},
                        }],
                        "pageInfo": {"hasNextPage": False},
                    },
                    "reviewRequests": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False},
                    },
                },
                repository=REPOSITORY,
                pull_request_number=LEGACY_PR,
                ready_source_provider_binding=binding,
            )
            for changed in (
                body + "\ncaller text",
                body.replace("Completed", "Running"),
                body + "\n| 🔒 **Security Review** | ✅ **Completed** | `5b8a661` | Manual request |",
            ):
                with self.subTest(changed=changed[-20:]), self.assertRaises(
                    legacy_loss.fast_path.SecurityBlocker
                ):
                    binding.verify_historical_provider_summary(
                        body=changed,
                        repository=REPOSITORY,
                        pull_request=LEGACY_PR,
                        current_head_sha=LEGACY_HEAD,
                    )

    def test_legacy_loss_binding_rejects_caller_created_or_changed_facts(self) -> None:
        authentication = legacy_loss_authentication()
        unsigned = copy.deepcopy(authentication)
        unsigned.pop("authentication_digest")
        authentication["authentication_digest"] = (
            legacy_loss.authority.digest_json(unsigned)
        )
        sealed = legacy_loss.VerifiedLegacyEnrolledPackageLoss(
            authentication, legacy_loss._VERIFIED
        )
        self.assertEqual(
            legacy_loss.verified_binding(sealed), authentication
        )
        with self.assertRaisesRegex(
            legacy_loss.authority.LifecycleAuthorityError, "verifier-derived"
        ):
            legacy_loss.verified_binding(authentication)
        changed = copy.deepcopy(authentication)
        changed["head_sha"] = "0" * 40
        with self.assertRaisesRegex(
            legacy_loss.authority.LifecycleAuthorityError, "digest changed"
        ):
            legacy_loss.verified_binding(
                legacy_loss.VerifiedLegacyEnrolledPackageLoss(
                    changed, legacy_loss._VERIFIED
                )
            )

    def test_v12_reviewed_predecessor_matches_authenticated_current_safety(self) -> None:
        self.derive(
            reviewed_state_digest=REVIEWED_STATE,
            reviewed_feedback_digest=REVIEWED_FEEDBACK,
        )
        for field in ("reviewed_state_digest", "reviewed_feedback_digest"):
            arguments = {
                "reviewed_state_digest": REVIEWED_STATE,
                "reviewed_feedback_digest": REVIEWED_FEEDBACK,
            }
            arguments[field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(
                fast_path.SecurityBlocker,
                "authenticated adopted Ready safety",
            ):
                self.derive(**arguments)

    def test_requires_exactly_one_real_ready_transition_and_finite_history(self) -> None:
        cases = {
            "zero Ready transitions": ("ready_transition_count", 0),
            "wrong Ready count": ("ready_transition_count", 2),
            "boolean Ready count": ("ready_transition_count", True),
            "wrong review count": ("unrestricted_review_count", 2),
            "boolean review count": ("unrestricted_review_count", True),
            "negative remediation count": ("remediation_cycle_count", -1),
            "exceptional recovery": ("exceptional_recovery_count", 1),
            "exceptional continuation": ("exceptional_continuation_count", 1),
            "Cycle 3": ("cycle_3_absent", False),
        }
        for label, (field, value) in cases.items():
            current = published()
            current.lifecycle.state[field] = value
            with self.subTest(label=label), self.assertRaises(fast_path.SecurityBlocker):
                self.derive(current)

        current = published()
        current.lifecycle.state["ready_history"][0]["transition_kind"] = "READY_TO_DRAFT"
        with self.assertRaises(fast_path.SecurityBlocker):
            self.derive(current)

    def test_preserves_authenticated_finite_remediation_count(self) -> None:
        for count in (0, 1, 2):
            current = published()
            current.lifecycle.state["remediation_cycle_count"] = count
            with self.subTest(count=count):
                manifest = self.derive(current)
                self.assertEqual(manifest["lifecycle"]["remediation_cycles"], count)
                self.assertEqual(
                    fast_path.normalize_ready_integration_prior_authority(manifest),
                    manifest,
                )

    def test_rejects_boolean_ready_transition_count(self) -> None:
        manifest = self.derive()
        manifest["lifecycle"]["ready_transition_count"] = True
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.normalize_ready_integration_prior_authority(manifest)

    def test_rejects_native_v1_v2_and_synthetic_v3_provenance(self) -> None:
        for version in ("1.0", "2.0"):
            changed = proof()
            changed["schema_version"] = changed["proof_version"] = version
            with self.subTest(version=version), self.assertRaises(fast_path.SecurityBlocker):
                self.derive(published(changed))
        current = published()
        current.lifecycle.historical_proof_mode = "native_lifecycle"
        with self.assertRaises(fast_path.SecurityBlocker):
            self.derive(current)

    def test_caller_authored_or_reconstructed_source_facts_fail_closed(self) -> None:
        manifest = self.derive()
        mutations = (
            ("repository", "SecPal/api"),
            ("delivery_issue_number", 828),
            ("pull_request_number", 831),
            ("prior_delivery_head_sha", "a" * 40),
            ("prior_delivery_tree_sha", "b" * 40),
        )
        for field, value in mutations:
            candidate = copy.deepcopy(manifest)
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises(fast_path.SecurityBlocker):
                actions._require_exact_adopted_ready_manifest(candidate, manifest)
        candidate = copy.deepcopy(manifest)
        candidate["historical_companions"]["historical_bytes_reconstructed"] = True
        with self.assertRaises(fast_path.SecurityBlocker):
            actions._require_exact_adopted_ready_manifest(candidate, manifest)
        for field in (
            "source_parent_sha",
            "source_signer_identity",
            "commit_signature_evidence_digest",
            "historical_receipt_provenance_digest",
            "current_safety_digest",
            "observed_history_digest",
            "intended_state_digest",
            "head_advanced_count",
            "head_advanced_history_digest",
            "loss_admission_id",
            "loss_admission_digest",
            "review_budget_admission_id",
            "review_budget_admission_digest",
            "adoption_proof_digest",
            "adoption_authorization_id",
            "adoption_authorization_digest",
        ):
            candidate = copy.deepcopy(manifest)
            old = candidate["source_authority"][field]
            candidate["source_authority"][field] = (
                old + "-changed" if isinstance(old, str) else old + 1
            )
            with self.subTest(source_field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                actions._require_exact_adopted_ready_manifest(candidate, manifest)
        for publication_field in ("object_oid", "publication_digest"):
            candidate = copy.deepcopy(manifest)
            old = candidate["publication"][publication_field]
            candidate["publication"][publication_field] = "a" * len(old)
            with self.subTest(current=publication_field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                actions._require_exact_adopted_ready_manifest(candidate, manifest)
            candidate = copy.deepcopy(manifest)
            old = candidate["source_authority"]["enrollment_publication"][
                publication_field
            ]
            candidate["source_authority"]["enrollment_publication"][
                publication_field
            ] = "a" * len(old)
            with self.subTest(enrollment=publication_field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                actions._require_exact_adopted_ready_manifest(candidate, manifest)

    def test_invalid_ordinary_manifest_cannot_fall_through(self) -> None:
        ordinary = {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
        }
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.normalize_ready_integration_prior_authority(ordinary)

    def test_candidate_local_827_code_cannot_select_bridge(self) -> None:
        with mock.patch.object(
            actions, "_load_lifecycle_publication_helpers"
        ) as load_helpers, mock.patch.object(
            actions,
            "_require_accepted_main_bridge_source",
            side_effect=fast_path.SecurityBlocker(
                "candidate-local Ready prior-authority bridge is forbidden"
            ),
        ), self.assertRaisesRegex(fast_path.SecurityBlocker, "candidate-local"):
            actions._derive_exact_state_adoption_ready_prior_authority(
                repository_root=ROOT.parent,
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                binding={"signature_policy": {"accepted_formats": ["ssh"]}},
            )
        load_helpers.assert_not_called()

    def test_accepted_main_tooling_and_candidate_repository_are_distinct(self) -> None:
        current = published()
        source = {
            "parent_sha": PARENT,
            "tree_sha": TREE,
            "signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
        }
        with (
            mock.patch.object(
                actions,
                "_require_accepted_main_bridge_source",
                return_value="9" * 40,
            ) as accepted_source,
            mock.patch.object(
                actions,
                "_load_lifecycle_publication_helpers",
                return_value=(lifecycle_authority, lifecycle_publication),
            ),
            mock.patch.object(
                lifecycle_publication,
                "verify_current_lifecycle_authority",
                return_value=current,
            ),
            mock.patch.object(
                lifecycle_publication,
                "_verify_historical_lifecycle_transition",
                return_value=transition(current),
            ),
            mock.patch.object(
                lifecycle_authority,
                "verify_exact_state_adoption_proof",
                return_value=current.lifecycle,
            ),
            mock.patch.object(
                actions, "_verified_prior_delivery_commit", return_value=source
            ) as verify_candidate,
        ):
            with tempfile.TemporaryDirectory() as directory:
                candidate_root = Path(directory)
                candidate_actions = candidate_root / "scripts/secpal-pr-review-actions.py"
                candidate_actions.parent.mkdir(parents=True)
                candidate_actions.write_text(
                    "# candidate implementation intentionally differs\n",
                    encoding="utf-8",
                )
                self.assertNotEqual(
                    candidate_actions.read_bytes(),
                    (ROOT / "scripts/secpal-pr-review-actions.py").read_bytes(),
                )
                manifest = actions._derive_exact_state_adoption_ready_prior_authority(
                    repository_root=candidate_root,
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    binding={"signature_policy": {"accepted_formats": ["ssh"]}},
                )
        self.assertEqual(manifest["prior_delivery_tree_sha"], TREE)
        self.assertTrue(
            all(call.args[0] == REPOSITORY for call in accepted_source.call_args_list)
        )
        verify_candidate.assert_called_once_with(
            candidate_root, HEAD, SIGNER,
            mock.ANY,
        )

    def test_import_provenance_rejects_mixed_module_origin(self) -> None:
        module = SimpleNamespace(
            __file__=str(ROOT / "scripts/secpal_pr_review/fast_path.py"),
            __spec__=SimpleNamespace(
                origin=str(ROOT / "scripts/secpal_pr_review/fast_path.py"),
            ),
        )
        actions._require_bridge_import_provenance(
            {"fast_path": (module.__file__, module.__spec__.origin)},
            {"fast_path": ROOT / "scripts/secpal_pr_review/fast_path.py"},
        )
        module.__file__ = "/candidate/scripts/secpal_pr_review/fast_path.py"
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "mixed verifier"):
            actions._require_bridge_import_provenance(
                {"fast_path": (module.__file__, module.__spec__.origin)},
                {"fast_path": ROOT / "scripts/secpal_pr_review/fast_path.py"},
            )

    def test_import_provenance_rejects_symlinked_module_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            alias = root / "alias.py"
            alias.symlink_to(source)
            module = SimpleNamespace(
                __file__=str(alias),
                __spec__=SimpleNamespace(
                    origin=str(alias),
                ),
            )
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "mixed verifier"):
                actions._require_bridge_import_provenance(
                    {"module": (module.__file__, module.__spec__.origin)},
                    {"module": alias},
                )

    def test_preloaded_candidate_module_is_rejected(self) -> None:
        name = "secpal_pr_review.pre_enrollment_integration"
        previous = sys.modules.get(name)
        candidate = SimpleNamespace(__file__="/candidate/pre_enrollment_integration.py")
        sys.modules[name] = candidate
        try:
            with self.assertRaisesRegex(RuntimeError, "unexpected path"):
                actions._load_pre_enrollment_integration_helper()
        finally:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def test_preloaded_same_path_module_is_reloaded_from_source(self) -> None:
        name = "secpal_pr_review.pre_enrollment_integration"
        previous = sys.modules.get(name)
        candidate = SimpleNamespace(
            __file__=str(actions.PRE_ENROLLMENT_INTEGRATION_HELPER)
        )
        sys.modules[name] = candidate
        try:
            loaded = actions._load_pre_enrollment_integration_helper()
            self.assertIsNot(loaded, candidate)
            self.assertEqual(
                Path(loaded.__spec__.origin).absolute(),
                actions.PRE_ENROLLMENT_INTEGRATION_HELPER.absolute(),
            )
        finally:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def test_failed_helper_load_does_not_leave_partial_module(self) -> None:
        for loader_name, module_name, helper_path in (
            (
                "_load_evidence_helper",
                "secpal_pr_review_evidence_shared",
                actions.EVIDENCE_HELPER,
            ),
            (
                "_load_pre_enrollment_integration_helper",
                "secpal_pr_review.pre_enrollment_integration",
                actions.PRE_ENROLLMENT_INTEGRATION_HELPER,
            ),
        ):
            previous = sys.modules.pop(module_name, None)
            spec = importlib.util.spec_from_file_location(module_name, helper_path)
            if spec is None or spec.loader is None:
                self.fail("test helper spec is unavailable")
            try:
                with (
                    self.subTest(loader=loader_name),
                    mock.patch.object(
                        actions.importlib.util,
                        "spec_from_file_location",
                        return_value=spec,
                    ),
                    mock.patch.object(
                        spec.loader,
                        "exec_module",
                        side_effect=RuntimeError("load failed"),
                    ),
                    self.assertRaisesRegex(RuntimeError, "load failed"),
                ):
                    getattr(actions, loader_name)()
                self.assertNotIn(module_name, sys.modules)
            finally:
                if previous is not None:
                    sys.modules[module_name] = previous

    def test_candidate_root_cannot_alias_executing_tooling(self) -> None:
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "must be distinct"):
            actions._require_distinct_candidate_repository_root(ROOT)
        actions._require_distinct_candidate_repository_root(ROOT / "scripts")
        actions._require_distinct_candidate_repository_root(ROOT.parent)

    def test_accepted_main_blob_rejects_dirty_and_symlinked_tooling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@example.com"],
                check=True,
            )
            source = root / "tool.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tool.py"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "tool"], check=True
            )
            accepted = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            actions._require_exact_accepted_main_blob(root, accepted, "tool.py")
            source.chmod(0o755)
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "tooling provenance"
            ):
                actions._require_exact_accepted_main_blob(root, accepted, "tool.py")
            source.chmod(0o644)
            source.write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "tooling provenance"
            ):
                actions._require_exact_accepted_main_blob(root, accepted, "tool.py")
            source.unlink()
            target = root / "target.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            source.symlink_to(target)
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "tooling provenance"
            ):
                actions._require_exact_accepted_main_blob(root, accepted, "tool.py")

    def test_accepted_main_gate_requires_protection_and_bounded_metadata(self) -> None:
        repository = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {"full_name": REPOSITORY, "default_branch": "main"}
            ),
            stderr="",
        )
        branch = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"sha": "9" * 40, "protected": True}), stderr=""
        )
        commit = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"sha": "9" * 40, "verified": True}), stderr=""
        )
        with (
            mock.patch.object(
                actions, "_run_bridge_gh", side_effect=[repository, branch, commit]
            ) as run_gh,
            mock.patch.object(
                actions, "_require_accepted_main_tooling_blobs"
            ),
            mock.patch.object(actions, "_require_bridge_import_provenance"),
        ):
            self.assertEqual(
                actions._require_accepted_main_bridge_source(REPOSITORY),
                "9" * 40,
            )
        calls = [item.args[0] for item in run_gh.call_args_list]
        self.assertEqual(len(calls), 3)
        self.assertIn("--jq", calls[0])
        self.assertIn("--jq", calls[1])
        self.assertIn("--jq", calls[2])

        unprotected = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"sha": "9" * 40, "protected": False}), stderr=""
        )
        with mock.patch.object(actions, "_run_bridge_gh", return_value=unprotected), self.assertRaises(
            fast_path.SecurityBlocker
        ):
            actions._require_accepted_main_bridge_source(REPOSITORY)

        with (
            mock.patch.object(
                actions,
                "_run_bridge_gh",
                side_effect=[repository, branch, commit],
            ),
            mock.patch.object(actions, "_require_accepted_main_tooling_blobs"),
            mock.patch.object(actions, "_require_bridge_import_provenance"),
            self.assertRaisesRegex(fast_path.SecurityBlocker, "changed during"),
        ):
            actions._require_accepted_main_bridge_source(
                REPOSITORY, expected_main="a" * 40
            )

    def test_bridge_provider_failures_are_guarded(self) -> None:
        with mock.patch.object(
            actions,
            "_run_bridge_gh",
            side_effect=fast_path.SecurityBlocker("bridge observation unavailable"),
        ), self.assertRaisesRegex(fast_path.SecurityBlocker, "observation unavailable"):
            actions._require_accepted_main_bridge_source(REPOSITORY)

        with (
            mock.patch.object(
                actions, "_require_accepted_main_bridge_source", return_value="9" * 40
            ),
            mock.patch.object(
                actions,
                "_load_lifecycle_publication_helpers",
                side_effect=RuntimeError("unavailable"),
            ),
            self.assertRaisesRegex(
                fast_path.SecurityBlocker, "publication verifier is unavailable"
            ),
        ):
            actions._derive_exact_state_adoption_ready_prior_authority(
                repository_root=ROOT.parent,
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                binding={"signature_policy": {"accepted_formats": ["ssh"]}},
            )

    def test_v3_authority_normalizes_into_the_existing_integration_verifier(self) -> None:
        manifest = self.derive()
        integration = {
            "pull_request_number": PR,
            "prior_delivery_head_sha": HEAD,
            "prior_authority_digest": fast_path.digest_json(manifest),
            "prior_authority_tag_object_sha": "9" * 40,
            "reviewed_state_digest": REVIEWED_STATE,
            "reviewed_feedback_digest": REVIEWED_FEEDBACK,
            "eligibility": {
                "lifecycle_identity": manifest["lifecycle"]["identity"],
                "unrestricted_reviews_before": 1,
                "unrestricted_reviews_after": 1,
                "remediation_cycles_before": 2,
                "remediation_cycles_after": 2,
                "exceptional_recoveries_before": 0,
                "exceptional_recoveries_after": 0,
                "exceptional_continuations_before": 0,
                "exceptional_continuations_after": 0,
                "draft_before": False,
                "ready_before": True,
                "ready_transition": False,
                "cycle_3": False,
            },
        }
        arguments = SimpleNamespace(
            repo=REPOSITORY,
            delivery_issue=ISSUE,
            prior_authority="authority.json",
            prior_authority_tag_ref=(
                f"refs/tags/secpal-ready-integration-prior-authority-"
                f"{ISSUE}-{PR}-{HEAD}"
            ),
            expected_prior_authority_signer=SIGNER,
            prior_reviewed_state=None,
            prior_receipt=None,
            prior_attestation=None,
        )
        with (
            mock.patch.object(actions, "_read_json", return_value=manifest),
            mock.patch.object(
                actions,
                "_derive_exact_state_adoption_ready_prior_authority",
                return_value=manifest,
            ),
            mock.patch.object(actions, "_verify_prior_authority_tag") as tag,
        ):
            self.assertEqual(
                actions._verify_ready_integration_prior_authority(
                    arguments=arguments,
                    repository_root=ROOT,
                    binding={"signature_policy": {"accepted_formats": ["ssh"]}},
                    integration_evidence=integration,
                    live_observation=None,
                ),
                manifest,
            )
        tag.assert_called_once()

    def test_canonical_tag_target_identity_and_idempotency_are_exact(self) -> None:
        manifest = self.derive()
        self.assertEqual(
            actions._require_exact_adopted_ready_manifest(manifest, manifest),
            manifest,
        )
        self.assertEqual(
            actions._canonical_ready_prior_authority_tag_ref(manifest),
            f"refs/tags/secpal-ready-integration-prior-authority-{ISSUE}-{PR}-{HEAD}",
        )
        changed = copy.deepcopy(manifest)
        changed["source_authority"]["adoption_proof_digest"] = "a" * 64
        with self.assertRaises(fast_path.SecurityBlocker):
            actions._require_exact_adopted_ready_manifest(changed, manifest)

        integration = {
            "pull_request_number": PR,
            "prior_delivery_head_sha": HEAD,
            "prior_authority_digest": fast_path.digest_json(manifest),
            "reviewed_state_digest": REVIEWED_STATE,
            "reviewed_feedback_digest": REVIEWED_FEEDBACK,
        }
        arguments = SimpleNamespace(
            repo=REPOSITORY,
            delivery_issue=ISSUE,
            prior_authority="authority.json",
            prior_authority_tag_ref="refs/tags/caller-selected",
            expected_prior_authority_signer=SIGNER,
            prior_reviewed_state=None,
            prior_receipt=None,
            prior_attestation=None,
        )
        with (
            mock.patch.object(actions, "_read_json", return_value=manifest),
            mock.patch.object(
                actions,
                "_derive_exact_state_adoption_ready_prior_authority",
                return_value=manifest,
            ),
            mock.patch.object(actions, "_verify_prior_authority_tag") as tag,
            self.assertRaisesRegex(fast_path.SecurityBlocker, "tag identity"),
        ):
            actions._verify_ready_integration_prior_authority(
                arguments=arguments,
                repository_root=ROOT,
                binding={"signature_policy": {"accepted_formats": ["ssh"]}},
                integration_evidence=integration,
                live_observation=None,
            )
        tag.assert_not_called()

    def test_invalid_ordinary_evidence_does_not_select_v3_bridge(self) -> None:
        ordinary = {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
            "repository": REPOSITORY,
            "delivery_issue_number": ISSUE,
            "pull_request_number": PR,
            "prior_delivery_head_sha": HEAD,
            "prior_delivery_tree_sha": TREE,
            "prior_validation_receipt_digest": "2" * 64,
            "prior_final_attestation_digest": "3" * 64,
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
            "lifecycle": {
                "identity": "lifecycle-ordinary",
                "current_authority_digest": "4" * 64,
                "historical_proof_mode": "native_lifecycle",
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
                "object_oid": "5" * 40,
                "publication_digest": "6" * 64,
            },
        }
        arguments = SimpleNamespace(
            repo=REPOSITORY,
            delivery_issue=ISSUE,
            prior_authority="ordinary.json",
            prior_authority_tag_ref="refs/tags/ordinary",
            expected_prior_authority_signer=SIGNER,
            prior_reviewed_state=None,
            prior_receipt=None,
            prior_attestation=None,
        )
        integration = {
            "pull_request_number": PR,
            "prior_delivery_head_sha": HEAD,
            "prior_authority_digest": fast_path.digest_json(ordinary),
        }
        with (
            mock.patch.object(actions, "_read_json", return_value=ordinary),
            mock.patch.object(
                actions, "_derive_exact_state_adoption_ready_prior_authority"
            ) as bridge,
            self.assertRaisesRegex(fast_path.SecurityBlocker, "historical companions"),
        ):
            actions._verify_ready_integration_prior_authority(
                arguments=arguments,
                repository_root=ROOT,
                binding={"signature_policy": {"accepted_formats": ["ssh"]}},
                integration_evidence=integration,
                live_observation=None,
            )
        bridge.assert_not_called()


if __name__ == "__main__":
    main()
