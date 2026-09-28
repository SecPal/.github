# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hermetic regressions for authenticated pre-enrollment Draft integration."""

from __future__ import annotations

import importlib.util
import copy
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import ExitStack, nullcontext
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
from unittest import TestCase, main, mock

from scripts.secpal_pr_review import fast_path
from scripts.secpal_pr_review import bootstrap_source_admission
from scripts.secpal_pr_review import lifecycle_authority
from scripts.secpal_pr_review import pre_enrollment_integration as integration


ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "scripts" / "secpal-pr-review-actions.py"
SPEC = importlib.util.spec_from_file_location("pre_enrollment_actions", ACTIONS)
assert SPEC is not None and SPEC.loader is not None
actions = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = actions
SPEC.loader.exec_module(actions)


class PreEnrollmentIntegrationBoundaryTests(TestCase):
    def test_typed_pre_enrollment_error_is_a_bounded_cli_security_failure(self) -> None:
        with mock.patch.object(
            actions, "_command_attest_validation",
            side_effect=actions.pre_enrollment.PreEnrollmentIntegrationError("bad typed evidence"),
        ):
            self.assertEqual(actions.main(["attest-validation", "--repo", "SecPal/.github", "--expected-head", "a" * 40, "--reviewed-state", "reviewed.json", "--output", "out.json"]), 3)

    def test_completed_dependency_inventory_does_not_override_canonical_ready(self) -> None:
        graph = {
            "complete": True,
            "issue": {
                "key": "SecPal/.github#776",
                "leaf": True,
                "ready": True,
                "blocked": False,
                "malformed": False,
                "reasons": [],
                "blocked_by": ["SecPal/.github#787", "SecPal/.github#771"],
            },
        }

        actions._verify_pre_enrollment_work_graph_result(
            graph,
            repository="SecPal/.github",
            delivery_issue=776,
            expected_digest=fast_path.digest_json(graph),
        )

    def test_nonready_blocked_or_malformed_work_graph_fails_closed(self) -> None:
        base = {
            "complete": True,
            "issue": {
                "key": "SecPal/.github#776",
                "leaf": True,
                "ready": True,
                "blocked": False,
                "malformed": False,
                "reasons": [],
                "blocked_by": [],
            },
        }
        mutations = (
            {"ready": False},
            {"ready": False, "blocked": True, "reasons": ["unsatisfied dependency"]},
            {"ready": False, "malformed": True, "reasons": ["malformed graph"]},
            {"ready": True, "blocked": False, "malformed": False, "reasons": ["ambiguous"]},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                graph = copy.deepcopy(base)
                graph["issue"].update(mutation)
                with self.assertRaises(actions.fast_path.SecurityBlocker):
                    actions._verify_pre_enrollment_work_graph_result(
                        graph,
                        repository="SecPal/.github",
                        delivery_issue=776,
                        expected_digest=fast_path.digest_json(graph),
                    )

    def test_attestation_cli_can_select_typed_draft_pre_enrollment_integration(self) -> None:
        arguments = actions.build_parser().parse_args(
            [
                "attest-validation",
                "--repo",
                "SecPal/.github",
                "--expected-head",
                "a" * 40,
                "--reviewed-state",
                "reviewed.json",
                "--output",
                "attestation.json",
                "--pre-enrollment-integration-evidence",
                "integration.json",
                "--delivery-issue",
                "776",
                "--integration-authorization-id",
                "pre-enrollment-776-001",
                "--expected-integration-signer",
                "aroviqen",
            ]
        )

        self.assertEqual(
            arguments.pre_enrollment_integration_evidence,
            "integration.json",
        )

    def test_attestation_cli_emits_typed_pre_enrollment_receipt(self) -> None:
        reviewed = fast_path.StableFeedbackState(
            repository="SecPal/.github",
            pull_request_number=800,
            head_sha=PARENT_1,
            base_ref="main",
            base_sha=PARENT_2,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        arguments = actions.build_parser().parse_args(
            [
                "attest-validation", "--repo", "SecPal/.github",
                "--expected-head", PARENT_1, "--reviewed-state", "reviewed.json",
                "--output", "receipt.json", "--repo-root", str(ROOT),
                "--pre-enrollment-integration-evidence", "integration.json",
                "--delivery-issue", "776", "--integration-authorization-id",
                "pre-enrollment-776-001", "--expected-integration-signer", SIGNER,
                "--validation-receipt-id", "receipt-001",
                "--final-attestation-id", "attestation-001",
            ]
        )
        live = {
            "repository": "SecPal/.github", "pull_request_number": 800,
            "state": "OPEN", "draft": True, "head_sha": PARENT_1,
            "base_repository": "SecPal/.github", "base_ref": "main",
            "head_repository": "SecPal/.github",
            "base_sha": PARENT_2,
            "closing_issues": [
                {"repository": "SecPal/.github", "number": 776, "state": "OPEN"}
            ],
            "closing_issues_complete": True,
        }
        with (
            mock.patch.object(actions, "_attestation_local_state", return_value=(PARENT_1, " M file\n")),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value={}),
            mock.patch.object(actions, "_fast_registry_binding", return_value=registry()),
            mock.patch.object(actions, "_read_json", return_value=evidence()),
            mock.patch.object(actions, "_read_pre_enrollment_json", return_value=evidence()),
            mock.patch.object(actions, "_load_fast_manual_gate_evidence", return_value=[]),
            mock.patch.object(actions, "_staged_tree", return_value=TREE),
            mock.patch.object(actions, "_verify_integration_tree_delta"),
            mock.patch.object(actions, "_run_registered_validations", return_value=True),
            mock.patch.object(actions, "_verify_pre_enrollment_external_authority"),
            mock.patch.object(actions.LiveGitHub, "observe_ready_integration_authority", return_value=live),
            mock.patch.object(actions, "_write_fast_report") as write_report,
        ):
            self.assertEqual(actions._command_attest_validation(arguments), 0)
        self.assertEqual(
            write_report.call_args.args[1]["kind"], integration.RECEIPT_KIND
        )

    def test_attestation_cli_binds_typed_pre_enrollment_commit_signature(self) -> None:
        reviewed = fast_path.StableFeedbackState(
            repository="SecPal/.github", pull_request_number=800,
            head_sha=PARENT_1, base_ref="main", base_sha=PARENT_2,
            pr_state="OPEN", feedback={"pull_request_reactions": [], "reviews": [], "conversation_comments": [], "threads": []},
        )
        selected = integration.normalize_evidence(evidence(), registry=registry())
        receipt = integration.create_validation_receipt(
            evidence=selected, registry=registry(), successful_result=True,
            receipt_id="receipt-001",
        )
        arguments = actions.build_parser().parse_args([
            "attest-validation", "--repo", "SecPal/.github",
            "--expected-head", CANDIDATE, "--reviewed-state", "reviewed.json",
            "--output", "attestation.json", "--repo-root", str(ROOT),
            "--pre-enrollment-integration-evidence", "integration.json",
            "--delivery-issue", "776", "--integration-authorization-id",
            "pre-enrollment-776-001", "--expected-integration-signer", SIGNER,
            "--validation-receipt-id", "receipt-001",
            "--final-attestation-id", "attestation-001",
            "--bind-commit", "--receipt", "receipt.json",
        ])
        live = {
            "repository": "SecPal/.github", "pull_request_number": 800,
            "state": "OPEN", "draft": True, "head_sha": PARENT_1,
            "base_repository": "SecPal/.github", "base_ref": "main",
            "head_repository": "SecPal/.github", "base_sha": PARENT_2,
            "closing_issues": [{"repository": "SecPal/.github", "number": 776, "state": "OPEN"}],
            "closing_issues_complete": True,
        }
        signature = {"format": "ssh", "state": "valid", "verified": True}
        with (
            mock.patch.object(actions, "_attestation_local_state", return_value=(CANDIDATE, "")),
            mock.patch.object(actions, "_load_fast_state", return_value=reviewed),
            mock.patch.object(actions, "load_registry", return_value={}),
            mock.patch.object(actions, "select_repository", return_value={}),
            mock.patch.object(actions, "_fast_registry_binding", return_value=registry()),
            mock.patch.object(actions, "_read_pre_enrollment_json", side_effect=[receipt, selected]),
            mock.patch.object(actions, "_verify_pre_enrollment_external_authority"),
            mock.patch.object(actions.LiveGitHub, "observe_ready_integration_authority", return_value=live),
            mock.patch.object(actions, "_validated_integration_commit_parents", return_value=[PARENT_1, PARENT_2]),
            mock.patch.object(actions, "_verify_integration_tree_delta"),
            mock.patch.object(actions, "_run_attestation_git", side_effect=[
                SimpleNamespace(stdout=TREE, stderr="", returncode=0),
                SimpleNamespace(stdout="tree record", stderr="", returncode=0),
                SimpleNamespace(stdout="Good git signature for " + SIGNER, stderr="", returncode=0),
            ]),
            mock.patch.object(actions, "_commit_trailer_digest", side_effect=[receipt["receipt_digest"], fast_path.digest_json(selected)]),
            mock.patch.object(actions.evidence, "interpret_local_signature", return_value=signature),
            mock.patch.object(actions, "_verify_signature_policy_identity"),
            mock.patch.object(actions, "_verify_integration_signer"),
            mock.patch.object(actions, "_write_fast_report") as write_report,
        ):
            self.assertEqual(actions._command_attest_validation(arguments), 0)
        self.assertEqual(write_report.call_args.args[1]["kind"], integration.ATTESTATION_KIND)


PARENT_1 = "a" * 40
PARENT_2 = "b" * 40
CANDIDATE = "c" * 40
TREE = "d" * 40
MECHANICAL = "e" * 40
SIGNER = "delivery@example.test"
AUTHORIZER = "authority@example.test"


def fake_signer(_payload: bytes, _domain: str) -> dict[str, str]:
    return {"format": "ssh", "signer_identity": AUTHORIZER, "value": "signed"}


def lifecycle_signer(_payload: bytes, _domain: str) -> dict[str, str]:
    return {"format": "ssh", "signer_identity": SIGNER, "value": "signed"}


def verified_candidate() -> object:
    return integration._seal_verified_candidate_commit(
        {
            "head_sha": CANDIDATE,
            "tree_sha": TREE,
            "parent_shas": [PARENT_1, PARENT_2],
            "verified_signer": SIGNER,
            "signature_format": "ssh",
        }
    )


def registry() -> dict[str, object]:
    return {
        "repository": "SecPal/.github",
        "default_branch": "main",
        "signature_policy": {
            "require_github_verified": True,
            "require_local_verified": True,
            "accepted_formats": ["ssh", "openpgp"],
        },
        "validation": [{"argv": ["./scripts/preflight.sh"]}],
        "pre_enrollment_integration_policy": {
            "schema_version": "1.0",
            "command": "integrate-pre-enrollment-draft",
            "topology_kind": integration.KIND,
            "allowed_mutation": "NON_FORCE_PUSH_EXACT_PR_BRANCH",
            "maximum_candidates": 1,
            "maximum_pushes": 1,
            "force_push": False,
            "automatic_retry": False,
            "merge_pull_request": False,
        },
    }


def evidence(*, conflict_path: str | None = None) -> dict[str, object]:
    authorization = integration.create_authorization(
        authorization_id="pre-enrollment-776-001",
        repository="SecPal/.github",
        delivery_issue=776,
        pull_request=800,
        draft_head_sha=PARENT_1,
        current_main_sha=PARENT_2,
        expected_signer=SIGNER,
        signer_identity=AUTHORIZER,
        signer=fake_signer,
    )
    conflicts = [] if conflict_path is None else [conflict_path]
    delta = [] if conflict_path is None else [
        {
            "path": conflict_path,
            "status": "M",
            "old_mode": "100644",
            "new_mode": "100644",
            "old_oid": MECHANICAL,
            "new_oid": TREE,
        }
    ]
    item = {
        "schema_version": integration.SCHEMA_VERSION,
        "kind": integration.KIND,
        "domain": integration.DOMAIN,
        "repository": "SecPal/.github",
        "delivery_issue": 776,
        "pull_request": 800,
        "authorization": authorization,
        "authorization_digest": authorization["authorization_digest"],
        "draft_pr": {
            "state": "OPEN",
            "draft": True,
            "head_sha": PARENT_1,
            "observation_digest": "1" * 64,
        },
        "current_main": {
            "ref": "main",
            "sha": PARENT_2,
            "observation_digest": "2" * 64,
        },
        "ordered_parent_shas": [PARENT_1, PARENT_2],
        "validated_tree_sha": TREE,
        "mechanical_merge_tree_sha": TREE if conflict_path is None else MECHANICAL,
        "mechanical_conflict_paths": conflicts,
        "manual_conflict_resolution_delta": delta,
        "work_graph": {
            "leaf": True,
            "hard_dependencies_satisfied": True,
            "ready": True,
            "evidence_digest": "3" * 64,
        },
        "lifecycle_absence": {
            "current_publication": False,
            "native_genesis": False,
            "lifecycle_aware_head_advancement": False,
            "evidence_digest": "4" * 64,
        },
        "validation_execution": {
            "registry_digest": fast_path.digest_json(registry()),
            "command_set_digest": fast_path.digest_json(registry()["validation"]),
        },
        "expected_signer": SIGNER,
    }
    return item


class PreEnrollmentIntegrationContractTests(TestCase):
    def normalized(self, item: dict[str, object] | None = None) -> dict[str, object]:
        return integration.normalize_evidence(item or evidence(), registry=registry())

    def test_clean_draft_pre_enrollment_integration(self) -> None:
        normalized = self.normalized()
        integration.verify_combined_tree(
            normalized,
            mechanical_tree_sha=TREE,
            conflict_paths=[],
            observed_delta=[],
            retained_conflict_markers=False,
        )
        self.assertEqual(normalized["kind"], integration.KIND)
        self.assertNotEqual(normalized["kind"], fast_path.READY_INTEGRATION_KIND)

    def test_bounded_conflict_and_changelog_shaped_conflict(self) -> None:
        for path in ("notes.txt", "CHANGELOG.md"):
            with self.subTest(path=path):
                normalized = self.normalized(evidence(conflict_path=path))
                integration.verify_combined_tree(
                    normalized,
                    mechanical_tree_sha=MECHANICAL,
                    conflict_paths=[path],
                    observed_delta=normalized["manual_conflict_resolution_delta"],
                    retained_conflict_markers=False,
                )

    def test_wrong_swapped_missing_extra_and_stale_parents(self) -> None:
        cases = {
            "wrong": ["f" * 40, PARENT_2],
            "swapped": [PARENT_2, PARENT_1],
            "missing": [PARENT_1],
            "extra": [PARENT_1, PARENT_2, "f" * 40],
            "stale-main": [PARENT_1, "f" * 40],
        }
        for name, parents in cases.items():
            with self.subTest(name=name):
                item = evidence()
                item["ordered_parent_shas"] = parents
                with self.assertRaises(integration.PreEnrollmentIntegrationError):
                    self.normalized(item)

    def test_wrong_repository_issue_pr_and_cross_delivery_replay(self) -> None:
        for path, value in (
            (("repository",), "SecPal/api"),
            (("delivery_issue",), 777),
            (("pull_request",), 801),
        ):
            item = evidence()
            item[path[0]] = value
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                self.normalized(item)

    def test_duplicate_unknown_and_non_finite_json_are_rejected(self) -> None:
        for raw in (
            '{"kind":"a","kind":"b"}',
            '{"value":NaN}',
        ):
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.loads_closed_json(raw)
        item = evidence(); item["allow_generic_merge"] = True
        with self.assertRaises(integration.PreEnrollmentIntegrationError):
            self.normalized(item)

    def test_pr_head_main_draft_and_open_drift_fail_before_write(self) -> None:
        normalized = self.normalized()
        cases = []
        moved_head = copy.deepcopy(normalized["draft_pr"]); moved_head["head_sha"] = "f" * 40; cases.append((moved_head, normalized["current_main"]))
        ready = copy.deepcopy(normalized["draft_pr"]); ready["draft"] = False; cases.append((ready, normalized["current_main"]))
        closed = copy.deepcopy(normalized["draft_pr"]); closed["state"] = "CLOSED"; cases.append((closed, normalized["current_main"]))
        moved_main = copy.deepcopy(normalized["current_main"]); moved_main["sha"] = "f" * 40; cases.append((normalized["draft_pr"], moved_main))
        for live_pr, live_main in cases:
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.verify_fresh_state(normalized, live_pr=live_pr, live_main=live_main, work_graph=normalized["work_graph"], lifecycle_absence=normalized["lifecycle_absence"])

    def test_already_enrolled_genesis_or_lifecycle_advancement_is_rejected(self) -> None:
        for field in ("current_publication", "native_genesis", "lifecycle_aware_head_advancement"):
            item = evidence(); item["lifecycle_absence"][field] = True
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                self.normalized(item)

    def test_unsigned_or_wrong_authorization_signer_is_rejected(self) -> None:
        normalized = self.normalized()
        with self.assertRaises(integration.PreEnrollmentIntegrationError):
            integration.verify_authorization(normalized["authorization"], accepted_signers=frozenset({AUTHORIZER}), verifier=lambda *_: False)
        with self.assertRaises(integration.PreEnrollmentIntegrationError):
            integration.verify_authorization(normalized["authorization"], accepted_signers=frozenset({"other"}), verifier=lambda *_: True)

    def test_tree_mismatch_extra_delta_omission_and_markers_are_rejected(self) -> None:
        normalized = self.normalized(evidence(conflict_path="notes.txt"))
        cases = (
            {"mechanical_tree_sha": "f" * 40, "conflict_paths": ["notes.txt"], "observed_delta": normalized["manual_conflict_resolution_delta"], "retained_conflict_markers": False},
            {"mechanical_tree_sha": MECHANICAL, "conflict_paths": [], "observed_delta": [], "retained_conflict_markers": False},
            {"mechanical_tree_sha": MECHANICAL, "conflict_paths": ["notes.txt"], "observed_delta": [], "retained_conflict_markers": False},
            {"mechanical_tree_sha": MECHANICAL, "conflict_paths": ["notes.txt"], "observed_delta": normalized["manual_conflict_resolution_delta"], "retained_conflict_markers": True},
        )
        for case in cases:
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.verify_combined_tree(normalized, **case)
        extra = evidence(conflict_path="notes.txt")
        extra["manual_conflict_resolution_delta"].append({**extra["manual_conflict_resolution_delta"][0], "path": "unrelated.txt"})
        with self.assertRaises(integration.PreEnrollmentIntegrationError):
            self.normalized(extra)

    def test_receipt_and_attestation_bind_exact_candidate_and_delivery(self) -> None:
        normalized = self.normalized()
        receipt = integration.create_validation_receipt(evidence=normalized, registry=registry(), successful_result=True, receipt_id="receipt-001")
        attestation = integration.create_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, candidate_head_sha=CANDIDATE, candidate_parent_shas=[PARENT_1, PARENT_2], candidate_tree_sha=TREE, verified_signer=SIGNER, signature_format="ssh", attestation_id="attestation-001")
        proof = integration.verify_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, attestation=attestation, commit_trailers={"SecPal-Pre-Enrollment-Integration": attestation["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"]}, verified_candidate=verified_candidate())
        self.assertEqual(proof.initial_head_sha, CANDIDATE)
        for mutation in ("receipt", "attestation", "cross-issue", "cross-pr"):
            bad_receipt = copy.deepcopy(receipt); bad_attestation = copy.deepcopy(attestation); bad_evidence = copy.deepcopy(normalized)
            if mutation == "receipt": bad_receipt["receipt_id"] = "stale"
            elif mutation == "attestation": bad_attestation["attestation_id"] = "stale"
            elif mutation == "cross-issue": bad_evidence["delivery_issue"] = 777
            else: bad_evidence["pull_request"] = 801
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.verify_final_attestation(evidence=bad_evidence, registry=registry(), receipt=bad_receipt, attestation=bad_attestation, commit_trailers={}, verified_candidate=verified_candidate())

        with self.assertRaises(integration.PreEnrollmentIntegrationError):
            integration.verify_final_attestation(
                evidence=normalized, registry=registry(), receipt=receipt,
                attestation=attestation,
                commit_trailers={"SecPal-Pre-Enrollment-Integration": attestation["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"]},
                verified_candidate={
                    "head_sha": CANDIDATE, "tree_sha": TREE,
                    "parent_shas": [PARENT_1, PARENT_2],
                    "verified_signer": SIGNER, "signature_format": "ssh",
                },
            )

    def test_candidate_parent_tree_and_signer_are_exact(self) -> None:
        normalized = self.normalized()
        receipt = integration.create_validation_receipt(evidence=normalized, registry=registry(), successful_result=True, receipt_id="receipt-001")
        cases = ([PARENT_2, PARENT_1], [PARENT_1], [PARENT_1, PARENT_2, "f" * 40])
        for parents in cases:
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.create_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, candidate_head_sha=CANDIDATE, candidate_parent_shas=parents, candidate_tree_sha=TREE, verified_signer=SIGNER, signature_format="ssh", attestation_id="a")
        for signer, fmt, tree in (("wrong", "ssh", TREE), (SIGNER, "unsigned", TREE), (SIGNER, "ssh", "f" * 40)):
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.create_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, candidate_head_sha=CANDIDATE, candidate_parent_shas=[PARENT_1, PARENT_2], candidate_tree_sha=tree, verified_signer=signer, signature_format=fmt, attestation_id="a")

    def test_verified_head_handoff_initializes_canonical_zero_counter_draft(self) -> None:
        normalized = self.normalized()
        receipt = integration.create_validation_receipt(evidence=normalized, registry=registry(), successful_result=True, receipt_id="receipt-001")
        attestation = integration.create_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, candidate_head_sha=CANDIDATE, candidate_parent_shas=[PARENT_1, PARENT_2], candidate_tree_sha=TREE, verified_signer=SIGNER, signature_format="ssh", attestation_id="attestation-001")
        proof = integration.verify_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, attestation=attestation, commit_trailers={"SecPal-Pre-Enrollment-Integration": attestation["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"]}, verified_candidate=verified_candidate())
        initialization = lifecycle_authority.create_delivery_initialization(repository="SecPal/.github", delivery_issue=776, pull_request=800, initial_head_sha=CANDIDATE, validation_receipt_digest=receipt["receipt_digest"], final_attestation_digest=attestation["attestation_digest"], signer_identity=SIGNER, signer=lifecycle_signer, initial_head_proof=proof)
        policy = lifecycle_authority.LifecycleTrustPolicy(repository="SecPal/.github", accepted_formats=frozenset({"ssh"}), transition_signer_identities=frozenset({SIGNER}), authority_signer_identities=frozenset({SIGNER}), signers={}, initialization_anchors=())
        verified = lifecycle_authority._verify_delivery_initialization(initialization, policy=policy, signature_verifier=lambda *_: lifecycle_authority.VerifiedSignature(SIGNER, "ssh"), require_maintained_anchor=False)
        lifecycle_id = lifecycle_authority.delivery_initialization_lifecycle_id(
            initialization["initialization_digest"]
        )
        event = lifecycle_authority.create_transition_authorization(
            event_id=f'genesis:{initialization["initialization_digest"]}',
            repository="SecPal/.github", delivery_issue=776,
            lifecycle_id=lifecycle_id, pull_request=800,
            predecessor_authority_digest=None, predecessor_head_sha=None,
            resulting_head_sha=CANDIDATE, transition_kind="INITIALIZED_DRAFT",
            replacement_pull_request=None,
            initialization_evidence_digest=initialization["initialization_digest"],
            signer_identity=SIGNER, signer=lifecycle_signer,
        )
        snapshot = lifecycle_authority.issue_lifecycle_authority(
            predecessor_chain=[], transition_authorizations=[], authorization=event,
            signer_identity=SIGNER, authority_signer=lifecycle_signer,
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=lambda *_: lifecycle_authority.VerifiedSignature(SIGNER, "ssh"),
        )
        bundle = lifecycle_authority.loads_closed_json(
            lifecycle_authority.serialize_lifecycle_evidence(
                delivery_initialization=initialization,
                transition_authorizations=[event], authority_chain=[snapshot],
            )
        )
        native = lifecycle_authority._verify_lifecycle_bundle_from_initialization(
            bundle, verified, policy,
            lambda *_: lifecycle_authority.VerifiedSignature(SIGNER, "ssh"),
        )
        state = lifecycle_authority.initial_state()
        self.assertEqual(verified["initial_head_sha"], CANDIDATE)
        self.assertEqual(native.head_sha, CANDIDATE)
        self.assertEqual(state["unrestricted_review_count"], 0)
        self.assertEqual(state["remediation_cycle_count"], 0)
        self.assertTrue(state["draft"]); self.assertFalse(state["ready"])
        self.assertEqual(state["ready_transition_count"], 0)
        self.assertEqual(state["exceptional_recovery_count"], 0)
        self.assertEqual(state["exceptional_continuation_count"], 0)
        self.assertTrue(state["cycle_3_absent"])

    def test_bootstrap_validation_composes_with_historical_adoption(self) -> None:
        normalized = self.normalized()
        receipt = integration.create_validation_receipt(
            evidence=normalized,
            registry=registry(),
            successful_result=True,
            receipt_id="bridge-receipt",
        )
        attestation = integration.create_final_attestation(
            evidence=normalized,
            registry=registry(),
            receipt=receipt,
            candidate_head_sha=CANDIDATE,
            candidate_parent_shas=[PARENT_1, PARENT_2],
            candidate_tree_sha=TREE,
            verified_signer=SIGNER,
            signature_format="ssh",
            attestation_id="bridge-attestation",
        )
        proof = integration.verify_final_attestation(
            evidence=normalized,
            registry=registry(),
            receipt=receipt,
            attestation=attestation,
            verified_candidate=verified_candidate(),
            commit_trailers={
                "SecPal-Pre-Enrollment-Integration": fast_path.digest_json(normalized),
                "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"],
            },
        )
        initialization = lifecycle_authority.create_delivery_initialization(
            repository="SecPal/.github",
            delivery_issue=776,
            pull_request=800,
            initial_head_sha=CANDIDATE,
            validation_receipt_digest=receipt["receipt_digest"],
            final_attestation_digest=attestation["attestation_digest"],
            signer_identity=SIGNER,
            signer=lifecycle_signer,
            initial_head_proof=proof,
        )
        self.assertEqual(initialization["schema_version"], "1.1")
        self.assertEqual(
            lifecycle_authority.initial_state()["unrestricted_review_count"], 0
        )
        self.assertEqual(lifecycle_authority.initial_state()["ready_history"], [])
        observations = [
            {
                "sequence": i,
                "kind": kind,
                "observed_at": f"2026-08-0{i}T00:00:00Z",
                "head_sha": CANDIDATE,
                "reviewed_head_sha": CANDIDATE if kind == "REVIEW_SUBMITTED" else None,
            }
            for i, kind in enumerate(
                (
                    "PR_CREATED_DRAFT",
                    "DRAFT_TO_READY_OBSERVED",
                    "REVIEW_SUBMITTED",
                    "READY_TO_DRAFT_OBSERVED",
                ),
                1,
            )
        ]
        state = lifecycle_authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            ready_transition_count=1,
            ready_history=[
                {
                    "sequence": i,
                    "transition_kind": kind,
                    "observation_digest": fast_path.digest_json(observations[index]),
                }
                for i, kind, index in ((1, "DRAFT_TO_READY", 1), (2, "READY_TO_DRAFT", 3))
            ],
        )
        commit = {
            "oid": CANDIDATE,
            "source": "USER",
            "signer_identity": SIGNER,
            "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
            "github_verification": {"verified": True, "reason": "valid"},
        }
        with mock.patch.object(
            lifecycle_authority,
            "_load_delivery_signature_policy",
            return_value=registry()["signature_policy"],
        ), self.assertRaisesRegex(
            lifecycle_authority.LifecycleAuthorityError,
            "adoption validation evidence does not bind the delivery",
        ):
            lifecycle_authority.authenticate_exact_state_adoption_external_evidence(
                repository="SecPal/.github",
                delivery_issue=776,
                pull_request=800,
                head_sha=CANDIDATE,
                tree_sha=TREE,
                pull_request_state="OPEN",
                commit_signature_evidence=commit,
                validation_evidence=proof,
                observed_pre_enrollment_history=observations,
                intended_state=state,
            )

    def test_generic_merge_cannot_be_substituted_for_verified_initial_head(self) -> None:
        with self.assertRaises(lifecycle_authority.LifecycleAuthorityError):
            lifecycle_authority.create_delivery_initialization(repository="SecPal/.github", delivery_issue=776, pull_request=800, initial_head_sha=CANDIDATE, validation_receipt_digest="1" * 64, final_attestation_digest="2" * 64, signer_identity=SIGNER, signer=lifecycle_signer, initial_head_proof={})
        forged = integration.VerifiedInitialHeadProof(
            integration.INITIAL_HEAD_PROOF_KIND, "SecPal/.github", 776, 800,
            CANDIDATE, "1" * 64, "2" * 64, "3" * 64, object(),
        )
        with self.assertRaises(lifecycle_authority.LifecycleAuthorityError):
            lifecycle_authority.create_delivery_initialization(repository="SecPal/.github", delivery_issue=776, pull_request=800, initial_head_sha=CANDIDATE, validation_receipt_digest="1" * 64, final_attestation_digest="2" * 64, signer_identity=SIGNER, signer=lifecycle_signer, initial_head_proof=forged)

    def test_ordinary_initialization_and_ready_kind_remain_unchanged(self) -> None:
        ordinary = lifecycle_authority.create_delivery_initialization(repository="SecPal/.github", delivery_issue=776, pull_request=800, initial_head_sha=PARENT_1, validation_receipt_digest="1" * 64, final_attestation_digest="2" * 64, signer_identity=SIGNER, signer=lifecycle_signer)
        self.assertEqual(ordinary["schema_version"], "1.0")
        self.assertNotIn("initial_head_proof", ordinary)
        self.assertEqual(fast_path.READY_INTEGRATION_KIND, "TWO_PARENT_READY_INTEGRATION")
        self.assertNotEqual(integration.KIND, fast_path.READY_INTEGRATION_KIND)

    def test_one_shot_execution_observes_creates_and_pushes_once(self) -> None:
        normalized = self.normalized()
        calls = {"observe": 0, "create": 0, "persist": 0, "push": 0, "final": 0}
        order = []

        def observe() -> integration.FrozenObservation:
            calls["observe"] += 1
            return integration.FrozenObservation(
                normalized["draft_pr"], normalized["current_main"],
                normalized["work_graph"], normalized["lifecycle_absence"],
            )

        def create(tree: str, parents: list[str], _trailers: object, signer: str) -> dict[str, object]:
            calls["create"] += 1
            return {"head_sha": CANDIDATE, "tree_sha": tree, "parent_shas": parents, "verified_signer": signer, "signature_format": "ssh"}

        def push(_head: str, _expected_old_head: str) -> bool:
            calls["push"] += 1
            order.append("push")
            return True

        def persist(receipt: object, attestation: object) -> None:
            self.assertIsInstance(receipt, dict)
            self.assertIsInstance(attestation, dict)
            calls["persist"] += 1
            order.append("persist")

        def final() -> str:
            calls["final"] += 1
            return CANDIDATE

        result = integration.execute_once(
            evidence=normalized, registry=registry(),
            accepted_authorization_signers=frozenset({AUTHORIZER}),
            authorization_verifier=lambda *_: True,
            derive_tree=lambda _parents, _tree: (TREE, [], [], False),
            run_registered_validation=lambda tree: tree == TREE,
            observe_frozen_state=observe, create_signed_candidate=create,
            persist_candidate_evidence=persist,
            push_fast_forward=push, observe_final_pr_head=final,
            receipt_id="receipt-001", attestation_id="attestation-001",
        )
        self.assertEqual(result.candidate_head_sha, CANDIDATE)
        self.assertEqual(calls, {"observe": 1, "create": 1, "persist": 1, "push": 1, "final": 1})
        self.assertEqual(order, ["persist", "push"])

    def test_evidence_persistence_failure_blocks_before_push(self) -> None:
        normalized = self.normalized()
        pushed = []

        with self.assertRaises(OSError):
            integration.execute_once(
                evidence=normalized, registry=registry(),
                accepted_authorization_signers=frozenset({AUTHORIZER}),
                authorization_verifier=lambda *_: True,
                derive_tree=lambda _parents, _tree: (TREE, [], [], False),
                run_registered_validation=lambda tree: tree == TREE,
                observe_frozen_state=lambda: integration.FrozenObservation(
                    normalized["draft_pr"], normalized["current_main"],
                    normalized["work_graph"], normalized["lifecycle_absence"],
                ),
                create_signed_candidate=lambda tree, parents, _trailers, signer: {
                    "head_sha": CANDIDATE, "tree_sha": tree,
                    "parent_shas": parents, "verified_signer": signer,
                    "signature_format": "ssh",
                },
                persist_candidate_evidence=lambda *_: (_ for _ in ()).throw(OSError("full")),
                push_fast_forward=lambda *_: pushed.append(True) or True,
                observe_final_pr_head=lambda: CANDIDATE,
                receipt_id="receipt-001", attestation_id="attestation-001",
            )
        self.assertEqual(pushed, [])

    def test_toctou_drift_stops_before_candidate_or_push_without_retry(self) -> None:
        normalized = self.normalized()
        calls = {"observe": 0, "create": 0, "push": 0}

        def observe() -> integration.FrozenObservation:
            calls["observe"] += 1
            moved = copy.deepcopy(normalized["current_main"]); moved["sha"] = "f" * 40
            return integration.FrozenObservation(normalized["draft_pr"], moved, normalized["work_graph"], normalized["lifecycle_absence"])

        def create(*_args: object) -> dict[str, object]:
            calls["create"] += 1
            return {}

        def push(*_args: object) -> bool:
            calls["push"] += 1
            return True

        with self.assertRaises(integration.PreEnrollmentIntegrationError):
            integration.execute_once(
                evidence=normalized, registry=registry(),
                accepted_authorization_signers=frozenset({AUTHORIZER}),
                authorization_verifier=lambda *_: True,
                derive_tree=lambda _parents, _tree: (TREE, [], [], False),
                run_registered_validation=lambda _tree: True,
                observe_frozen_state=observe, create_signed_candidate=create,
                persist_candidate_evidence=lambda *_: None,
                push_fast_forward=push, observe_final_pr_head=lambda: CANDIDATE,
                receipt_id="receipt-001", attestation_id="attestation-001",
            )
        self.assertEqual(calls, {"observe": 1, "create": 0, "push": 0})


class BootstrapAdoptionBridgeTests(TestCase):
    """Real signed evidence replay; process isolation is exercised separately below."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        cls.key = cls.root / "signing-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(cls.key)],
            check=True,
        )
        cls.public = " ".join(cls.key.with_suffix(".pub").read_text().split()[:2])
        cls.git("init", "-q")
        for key, value in (
            ("user.name", "Fixture"),
            ("user.email", SIGNER),
            ("gpg.format", "ssh"),
            ("user.signingkey", str(cls.key)),
        ):
            cls.git("config", key, value)
        cls.git("remote", "add", "origin", "https://github.com/SecPal/.github.git")
        document = json.loads((ROOT / fast_path.DELIVERY_REGISTRY_PATH).read_text())
        entry = next(
            item
            for item in document["repositories"]
            if item["repository"] == "SecPal/.github"
        )
        policy = entry["lifecycle_authority_policy"]
        for identity in (SIGNER, AUTHORIZER):
            policy["signers"].append(
                {
                    "identity": identity,
                    "ssh_public_keys": [cls.public],
                    "openpgp_fingerprints": [],
                }
            )
        policy["transition_signer_identities"].append(AUTHORIZER)
        cls.registry_raw = json.dumps(document)
        cls.schema_raw = (
            ROOT / fast_path.DELIVERY_REGISTRY_SCHEMA_RELATIVE_PATH
        ).read_text()
        for relative, raw in (
            (fast_path.DELIVERY_REGISTRY_PATH, cls.registry_raw),
            (fast_path.DELIVERY_REGISTRY_SCHEMA_RELATIVE_PATH, cls.schema_raw),
        ):
            path = cls.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
            cls.git("add", relative)
        (cls.root / "common.txt").write_text("common\n")
        cls.git("add", "common.txt")
        base = cls.git("commit-tree", cls.git("write-tree"), "-S", "-m", "base")
        (cls.root / "draft.txt").write_text("draft\n")
        cls.git("add", "draft.txt")
        cls.parent1 = cls.git(
            "commit-tree", cls.git("write-tree"), "-p", base, "-S", "-m", "draft"
        )
        cls.git("read-tree", base)
        (cls.root / "main.txt").write_text("main\n")
        cls.git("add", "main.txt")
        cls.parent2 = cls.git(
            "commit-tree", cls.git("write-tree"), "-p", base, "-S", "-m", "main"
        )
        cls.tree, conflicts = actions._mechanical_integration_result(
            cls.root, [cls.parent1, cls.parent2]
        )
        assert conflicts == []
        cls.binding = fast_path._validated_historical_registry_binding(
            registry_raw=cls.registry_raw,
            schema_raw=cls.schema_raw,
            repository="SecPal/.github",
        )
        cls.trust = lifecycle_authority.LifecycleTrustPolicy(
            repository="SecPal/.github",
            accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({AUTHORIZER}),
            authority_signer_identities=frozenset({AUTHORIZER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
            signers={
                identity: lifecycle_authority.TrustedSigner(identity, (cls.public,), ())
                for identity in (SIGNER, AUTHORIZER)
            },
            initialization_anchors=(),
        )
        cls.integration = evidence()
        cls.integration["draft_pr"]["head_sha"] = cls.parent1
        cls.integration["current_main"]["sha"] = cls.parent2
        cls.integration["ordered_parent_shas"] = [cls.parent1, cls.parent2]
        cls.integration["validated_tree_sha"] = cls.tree
        cls.integration["mechanical_merge_tree_sha"] = cls.tree
        cls.integration["validation_execution"] = {
            "registry_digest": fast_path.digest_json(cls.binding),
            "command_set_digest": fast_path.digest_json(cls.binding["validation"]),
        }
        cls.integration["authorization"] = integration.create_authorization(
            authorization_id="generic-bootstrap-bridge",
            repository="SecPal/.github",
            delivery_issue=776,
            pull_request=800,
            draft_head_sha=cls.parent1,
            current_main_sha=cls.parent2,
            expected_signer=SIGNER,
            signer_identity=AUTHORIZER,
            signer=cls.sign,
        )
        cls.integration["authorization_digest"] = cls.integration["authorization"][
            "authorization_digest"
        ]
        cls.receipt = integration.create_validation_receipt(
            evidence=cls.integration,
            registry=cls.binding,
            successful_result=True,
            receipt_id="generic-bootstrap-receipt",
        )
        cls.message = (
            "generic bootstrap\n\nSecPal-Pre-Enrollment-Integration: "
            + fast_path.digest_json(cls.integration)
            + "\nSecPal-Pre-Enrollment-Validation-Receipt: "
            + cls.receipt["receipt_digest"]
        )
        cls.head = cls.git(
            "commit-tree",
            cls.tree,
            "-p",
            cls.parent1,
            "-p",
            cls.parent2,
            "-S",
            "-m",
            cls.message,
        )
        cls.attestation = integration.create_final_attestation(
            evidence=cls.integration,
            registry=cls.binding,
            receipt=cls.receipt,
            candidate_head_sha=cls.head,
            candidate_parent_shas=[cls.parent1, cls.parent2],
            candidate_tree_sha=cls.tree,
            verified_signer=SIGNER,
            signature_format="ssh",
            attestation_id="generic-bootstrap-attestation",
        )

    @classmethod
    def git(cls, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", *arguments], cwd=cls.root, stderr=subprocess.PIPE, text=True
        ).strip()

    @classmethod
    def sign(
        cls, payload: bytes, domain: str, identity: str = AUTHORIZER
    ) -> dict[str, str]:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(cls.key), "-n", domain],
            input=payload,
            capture_output=True,
            check=True,
        )
        return {
            "format": "ssh",
            "signer_identity": identity,
            "value": result.stdout.decode(),
        }

    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.real_isolated_runner = (
            bootstrap_source_admission._run_bootstrap_validation_isolated
        )
        self.real_materializer = (
            bootstrap_source_admission._isolated_bootstrap_validation_repository
        )
        self.patch(
            bootstrap_source_admission,
            "_isolated_bootstrap_validation_repository",
            side_effect=lambda _head=None: nullcontext(self.root),
        )
        # Exercise the child replay directly for artifact/crypto failure isolation.
        # BootstrapIsolationTests exercises the real process/materialization boundary.
        self.patch(fast_path, "CENTRAL_REGISTRY_ROOT", new=self.root)
        self.patch(
            bootstrap_source_admission,
            "_run_bootstrap_validation_isolated",
            side_effect=lambda provenance: fast_path._validation_evidence_binding(
                fast_path._replay_pre_enrollment_validation_unsealed(provenance)
            ),
        )
        self.patch(
            bootstrap_source_admission, "_load_actions_helper", return_value=actions
        )
        self.main_guard = self.patch(
            actions, "_require_accepted_main_bridge_source", return_value=self.parent2
        )
        self.patch(
            lifecycle_authority, "_load_lifecycle_trust_policy", return_value=self.trust
        )
        self.patch(
            lifecycle_authority,
            "_load_delivery_signature_policy",
            return_value=self.binding["signature_policy"],
        )
        self.central = self.patch(
            fast_path, "_central_git_result", side_effect=self.central_read
        )
        self.github = self.patch(
            actions, "_run_bridge_gh", side_effect=self.github_read
        )

    def patch(self, target, name, **kwargs):
        return self.stack.enter_context(mock.patch.object(target, name, **kwargs))

    def central_read(self, arguments, **_kwargs):
        if arguments == ["show", f"{self.parent2}:{fast_path.DELIVERY_REGISTRY_PATH}"]:
            return 0, self.registry_raw
        if arguments == [
            "show",
            f"{self.parent2}:{fast_path.DELIVERY_REGISTRY_SCHEMA_RELATIVE_PATH}",
        ]:
            return 0, self.schema_raw
        raise AssertionError(arguments)

    def github_read(self, arguments):
        head = arguments[3].rsplit("/", 1)[-1]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "sha": head,
                    "verification": {"verified": True, "reason": "valid"},
                }
            ),
        )

    def arguments(self):
        return dict(
            repository="SecPal/.github",
            delivery_issue_number=776,
            pull_request_number=800,
            head_sha=self.head,
            repository_root=self.root,
            integration_evidence=copy.deepcopy(self.integration),
            validation_receipt=copy.deepcopy(self.receipt),
            final_attestation=copy.deepcopy(self.attestation),
        )

    def verify(self, **changes):
        return fast_path.verify_pre_enrollment_validation_evidence(
            **(self.arguments() | changes)
        )

    def test_real_signed_bootstrap_preserves_independent_adoption_history(self) -> None:
        candidate = fast_path._authenticate_pre_enrollment_commit(
            helper=actions,
            repository_root=self.root,
            repository="SecPal/.github",
            head_sha=self.head,
            expected_signer=SIGNER,
            trust=self.trust,
            signature_policy=self.binding["signature_policy"],
        )
        proof = integration.verify_final_attestation(
            evidence=self.integration,
            registry=self.binding,
            receipt=self.receipt,
            attestation=self.attestation,
            verified_candidate=candidate,
            commit_trailers={
                "SecPal-Pre-Enrollment-Integration": fast_path.digest_json(
                    self.integration
                ),
                "SecPal-Pre-Enrollment-Validation-Receipt": self.receipt[
                    "receipt_digest"
                ],
            },
        )
        initialization = lifecycle_authority.create_delivery_initialization(
            repository="SecPal/.github",
            delivery_issue=776,
            pull_request=800,
            initial_head_sha=self.head,
            validation_receipt_digest=self.receipt["receipt_digest"],
            final_attestation_digest=self.attestation["attestation_digest"],
            initial_head_proof=proof,
            signer_identity=SIGNER,
            signer=lambda payload, domain: self.sign(payload, domain, SIGNER),
        )
        self.assertEqual(initialization["schema_version"], "1.1")
        self.assertEqual(
            lifecycle_authority.initial_state()["unrestricted_review_count"], 0
        )
        self.assertEqual(lifecycle_authority.initial_state()["ready_history"], [])
        self.assertFalse(fast_path.is_verified_validation_evidence(proof))
        validation = self.verify()
        self.assertTrue(fast_path.is_verified_validation_evidence(validation))
        self.assertEqual(
            validation.validation_receipt_digest, self.receipt["receipt_digest"]
        )
        self.assertEqual(
            validation.final_attestation_digest, self.attestation["attestation_digest"]
        )
        self.assertNotEqual(
            validation.source_validation_evidence_digest,
            fast_path.digest_json(self.integration),
        )
        observed = [
            {
                "sequence": i,
                "kind": kind,
                "observed_at": f"2026-08-0{i}T00:00:00Z",
                "head_sha": self.parent1,
                "reviewed_head_sha": None,
            }
            for i, kind in enumerate(
                (
                    "PR_CREATED_DRAFT",
                    "DRAFT_TO_READY_OBSERVED",
                    "READY_TO_DRAFT_OBSERVED",
                ),
                1,
            )
        ]
        observed.append(
            {
                "sequence": 4,
                "kind": "HEAD_ADVANCED_OBSERVED",
                "observed_at": "2026-08-04T00:00:00Z",
                "head_sha": self.head,
                "reviewed_head_sha": None,
            }
        )
        state = lifecycle_authority.initial_state()
        state.update(
            unrestricted_review_count=1,
            ready_transition_count=1,
            ready_history=[
                {
                    "sequence": i,
                    "transition_kind": kind,
                    "observation_digest": fast_path.digest_json(observed[i]),
                }
                for i, kind in ((1, "DRAFT_TO_READY"), (2, "READY_TO_DRAFT"))
            ],
        )
        commit = {
            "oid": self.head,
            "source": "USER",
            "signer_identity": SIGNER,
            "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
            "github_verification": {"verified": True, "reason": "valid"},
        }
        arguments = dict(
            repository="SecPal/.github",
            delivery_issue=776,
            pull_request=800,
            head_sha=self.head,
            tree_sha=self.tree,
            pull_request_state="OPEN",
            commit_signature_evidence=commit,
            validation_evidence=validation,
            observed_pre_enrollment_history=observed,
            intended_state=state,
        )
        # No provider review is fabricated to consume the historical budget.
        with self.assertRaisesRegex(
            lifecycle_authority.LifecycleAuthorityError,
            "does not authenticate intended state",
        ):
            lifecycle_authority.authenticate_exact_state_adoption_external_evidence(
                **arguments
            )
        admission = lifecycle_authority.create_pre_enrollment_review_budget_consumption_admission(
            admission_id="generic-consumed-budget",
            repository="SecPal/.github",
            delivery_issue=776,
            pull_request=800,
            head_sha=self.head,
            tree_sha=self.tree,
            pull_request_state="OPEN",
            commit_signature_evidence_digest=fast_path.digest_json(
                fast_path.verify_commit_signatures(
                    [commit], self.binding["signature_policy"]
                )[0]
            ),
            validation_receipt_digest=validation.validation_receipt_digest,
            source_validation_evidence_digest=validation.source_validation_evidence_digest,
            adoption_source_evidence_digest=validation.final_attestation_digest,
            observed_pre_enrollment_history=observed,
            intended_state=state,
            adoption_timestamp="2026-08-05T00:00:00Z",
            signer_identity=SIGNER,
            signer=lambda payload, domain: self.sign(payload, domain, SIGNER),
        )
        external = (
            lifecycle_authority.authenticate_exact_state_adoption_external_evidence(
                **arguments,
                review_budget_consumption_admission=admission,
            )
        )
        self.assertEqual(external.intended_state, state)
        self.assertEqual(list(external.observed_pre_enrollment_history), observed)
        adoption = lifecycle_authority.create_exact_state_adoption_evidence(
            verified_external_evidence=external,
            adoption_timestamp="2026-08-05T00:00:00Z",
        )
        self.assertEqual(adoption["proof_version"], "2.0")
        self.assertEqual(
            external.adoption_source_evidence_digest,
            validation.final_attestation_digest,
        )
        self.assertEqual(self.main_guard.call_args.kwargs, {"expected_main": self.parent2})

    def test_raw_artifacts_and_delivery_identities_are_closed(self) -> None:
        for field, value in (
            ("repository", "Other/repository"),
            ("delivery_issue_number", 777),
            ("pull_request_number", 801),
            ("head_sha", self.parent1),
            ("delivery_issue_number", True),
            ("validation_receipt", {}),
            ("final_attestation", {}),
            ("integration_evidence", {}),
        ):
            with self.subTest(field=field), self.assertRaises(
                (ValueError, fast_path.SecurityBlocker)
            ):
                self.verify(**{field: value})
        for field in (
            "registry",
            "command_set",
            "signature_policy",
            "current_main",
            "initial_head_proof",
        ):
            with self.subTest(field=field), self.assertRaises(TypeError):
                self.verify(**{field: {}})
        for document, fields in {
            "validation_receipt": (
                "receipt_digest",
                "integration_evidence_digest",
                "registry_digest",
                "command_set_digest",
            ),
            "final_attestation": (
                "attestation_digest",
                "validation_receipt_digest",
                "integration_evidence_digest",
                "candidate_tree_sha",
            ),
            "integration_evidence": (
                "schema_version",
                "kind",
                "validated_tree_sha",
                "mechanical_merge_tree_sha",
                "authorization_digest",
            ),
        }.items():
            for field in fields:
                arguments = self.arguments()
                arguments[document][field] = "0" * (40 if "tree" in field else 64)
                with self.subTest(document=document, field=field), self.assertRaises(
                    (ValueError, fast_path.SecurityBlocker)
                ):
                    fast_path.verify_pre_enrollment_validation_evidence(**arguments)

    def test_seals_are_replayed_and_cannot_promote_proofs_or_other_families(
        self,
    ) -> None:
        validation = self.verify()
        for field in (
            "repository",
            "delivery_issue_number",
            "pull_request_number",
            "head_sha",
            "tree_sha",
            "validation_receipt_digest",
            "final_attestation_digest",
            "source_validation_evidence_digest",
            "_verification_seal",
        ):
            forged = replace(
                validation,
                **{field: object() if field == "_verification_seal" else "forged"},
            )
            with self.subTest(field=field):
                self.assertFalse(fast_path.is_verified_validation_evidence(forged))
        provenance = json.loads(validation._verification_seal.provenance_json)
        for field, replacement in (
            ("kind", "ORDINARY"),
            ("kind", "READY_INTEGRATION"),
            ("schema_version", "0.0"),
            ("schema_version", "2.0"),
            ("validation_receipt", {}),
            ("registry", {}),
        ):
            changed = copy.deepcopy(provenance)
            changed[field] = replacement
            seal = fast_path._VerifiedValidationEvidenceSeal(
                fast_path.canonical_json_bytes(changed).decode()
            )
            self.assertFalse(
                fast_path.is_verified_validation_evidence(
                    replace(validation, _verification_seal=seal)
                )
            )
        fabricated = integration.VerifiedInitialHeadProof(
            integration.INITIAL_HEAD_PROOF_KIND,
            "SecPal/.github",
            776,
            800,
            self.head,
            self.receipt["receipt_digest"],
            self.attestation["attestation_digest"],
            fast_path.digest_json(self.integration),
            object(),
        )
        self.assertFalse(fast_path.is_verified_validation_evidence(fabricated))
        self.assertFalse(
            fast_path.is_verified_validation_evidence(
                replace(
                    fabricated, _verification_token=integration._VERIFIED_HEAD_TOKEN
                )
            )
        )
        self.main_guard.side_effect = fast_path.SecurityBlocker(
            "candidate-local verifier"
        )
        self.assertFalse(fast_path.is_verified_validation_evidence(validation))

    def test_ordered_parents_and_signed_trailers_are_reauthenticated(self) -> None:
        for parents in (
            [self.parent2, self.parent1],
            [self.parent1],
            [self.parent1, self.parent2, self.git("rev-parse", self.parent1 + "^")],
            [self.parent1, self.git("rev-parse", self.parent2 + "^")],
        ):
            argv = ["commit-tree", self.tree, "-S", "-m", self.message]
            for parent in parents:
                argv.extend(["-p", parent])
            head = self.git(*argv)
            with self.subTest(parents=parents), self.assertRaises(ValueError):
                self.verify(head_sha=head)
        for message in (
            "missing trailers",
            self.message.replace(self.receipt["receipt_digest"], "0" * 64),
        ):
            head = self.git(
                "commit-tree",
                self.tree,
                "-p",
                self.parent1,
                "-p",
                self.parent2,
                "-S",
                "-m",
                message,
            )
            attestation = copy.deepcopy(self.attestation)
            attestation["candidate_head_sha"] = head
            attestation["attestation_digest"] = fast_path.digest_json(
                {k: v for k, v in attestation.items() if k != "attestation_digest"}
            )
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, "trailers"
            ):
                self.verify(head_sha=head, final_attestation=attestation)

    def test_authorization_signature_registry_and_main_cannot_be_substituted(
        self,
    ) -> None:
        for field, replacement in (
            ("value", "invalid signature"),
            ("signer_identity", "foreign@example.test"),
        ):
            changed = copy.deepcopy(self.integration)
            changed["authorization"]["signature"][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(integration_evidence=changed)
        changed = copy.deepcopy(self.integration)
        changed["validation_execution"]["command_set_digest"] = fast_path.digest_json(
            []
        )
        with self.assertRaisesRegex(ValueError, "command-set"):
            self.verify(integration_evidence=changed)
        self.main_guard.return_value = self.parent1
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "outside accepted protected-main history"
        ):
            self.verify()

    def test_invalid_signature_and_wrong_maintained_signer_fail_closed(self) -> None:
        unsigned = self.git(
            "commit-tree",
            self.tree,
            "-p",
            self.parent1,
            "-p",
            self.parent2,
            "-m",
            self.message,
        )
        with self.assertRaises(fast_path.SecurityBlocker):
            self.verify(head_sha=unsigned)
        self.github.side_effect = lambda arguments: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "sha": self.head,
                    "verification": {"verified": False, "reason": "invalid"},
                }
            ),
        )
        with self.assertRaises(fast_path.SecurityBlocker):
            self.verify()
        self.github.side_effect = self.github_read
        wrong_trust = replace(
            self.trust, signers={AUTHORIZER: self.trust.signers[AUTHORIZER]}
        )
        with mock.patch.object(
            lifecycle_authority,
            "_load_lifecycle_trust_policy",
            return_value=wrong_trust,
        ):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "signer is not maintained"
            ):
                self.verify()

    def test_real_graft_cannot_admit_foreign_evidence_epoch(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        history_root = Path(directory.name)
        actions._run_attestation_git(history_root, ["init", "--quiet"])
        actions._run_attestation_git(
            history_root,
            [
                "fetch",
                "--quiet",
                "--no-tags",
                str(self.root),
                self.parent1,
                self.parent2,
            ],
        )
        self.main_guard.return_value = self.parent1
        (history_root / ".git/info/grafts").write_text(
            f"{self.parent1} {self.parent2}\n"
        )
        observed = actions._run_attestation_git(
            history_root, ["rev-list", "--first-parent", self.parent1]
        ).stdout.splitlines()
        self.assertIn(self.parent2, observed)

        def central(arguments, **kwargs):
            if arguments[0] == "rev-list":
                result = actions._run_attestation_git(history_root, arguments)
                return result.returncode, result.stdout
            return self.central_read(arguments, **kwargs)

        self.central.side_effect = central
        with mock.patch.object(fast_path, "CENTRAL_REGISTRY_ROOT", history_root):
            with self.assertRaisesRegex(
                fast_path.SecurityBlocker, "outside accepted protected-main history"
            ):
                self.verify()

    def test_raw_history_rejects_replacement_refs_missing_objects_and_bounds(
        self,
    ) -> None:
        replacement = self.git(
            "commit-tree", self.tree, "-p", self.parent2, "-S", "-m", "replacement"
        )
        self.git("replace", self.parent1, replacement)
        try:
            # The Complete Validation harness disables replacement objects for
            # all Git calls. Enable them only for this diagnostic comparison;
            # the raw-object verifier below keeps its closed Git environment.
            with mock.patch.dict(os.environ):
                os.environ.pop("GIT_NO_REPLACE_OBJECTS", None)
                self.assertIn(
                    self.parent2,
                    self.git("rev-list", "--first-parent", self.parent1).splitlines(),
                )
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "outside accepted"):
                fast_path._require_pre_enrollment_main_ancestor(
                    self.parent1, self.parent2
                )
        finally:
            self.git("replace", "-d", self.parent1)
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "unavailable"):
            fast_path._require_pre_enrollment_main_ancestor("0" * 40, self.parent2)
        with mock.patch.object(fast_path, "PRE_ENROLLMENT_MAIN_HISTORY_LIMIT", 1):
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "depth/count"):
                fast_path._require_pre_enrollment_main_ancestor(
                    replacement, self.parent2
                )
        with mock.patch.object(fast_path, "_PRE_ENROLLMENT_MAIN_HISTORY_BYTES", 1):
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "byte bound"):
                fast_path._require_pre_enrollment_main_ancestor(
                    self.parent2, self.parent2
                )

    def test_raw_history_rejects_malformed_topology_and_object_identity(self) -> None:
        for headers in (
            f"tree {self.tree}\nparent garbage",
            f"tree {self.tree}\nparent\t{self.parent2}",
            f"tree {self.tree}\nparent {self.parent2}\nparent {self.parent2}",
            f"tree {self.tree}\nauthor x\nparent {self.parent2}",
            f"tree {self.tree}\ntree {self.tree}",
            f"parent {self.parent2}",
        ):
            raw = (headers + "\n\nmalformed\n").encode()
            oid = (
                subprocess.check_output(
                    [
                        "git",
                        "hash-object",
                        "--literally",
                        "-w",
                        "-t",
                        "commit",
                        "--stdin",
                    ],
                    cwd=self.root,
                    input=raw,
                )
                .decode()
                .strip()
            )
            with (
                self.subTest(headers=headers),
                self.assertRaises(fast_path.SecurityBlocker),
            ):
                fast_path._require_pre_enrollment_main_ancestor(oid, oid)
        original = bootstrap_source_admission._git

        def corrupt(root, arguments, **kwargs):
            result = original(root, arguments, **kwargs)
            if arguments[:2] == ["cat-file", "commit"]:
                result.stdout = result.stdout.replace(b"main", b"fake")
            return result

        with mock.patch.object(bootstrap_source_admission, "_git", side_effect=corrupt):
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "identity changed"):
                fast_path._require_pre_enrollment_main_ancestor(
                    self.parent2, self.parent2
                )

    def test_main_advance_preserves_immutable_evidence_epoch(self) -> None:
        original = self.verify()
        new_main = self.git(
            "commit-tree", self.tree, "-p", self.parent2, "-S", "-m", "advanced main"
        )
        self.main_guard.return_value = new_main
        advanced_validation = self.verify()
        self.assertEqual(
            fast_path._validation_evidence_binding(original),
            fast_path._validation_evidence_binding(advanced_validation),
        )
        self.assertTrue(fast_path.is_verified_validation_evidence(original))
        changed = copy.deepcopy(self.integration)
        changed["current_main"]["sha"] = new_main
        changed["ordered_parent_shas"][1] = new_main
        # Even a newly authenticated tip cannot replace the signed evidence epoch.
        with (
            mock.patch.object(
                fast_path, "_central_git_result", return_value=(0, new_main + "\n")
            ),
            mock.patch.object(
                fast_path,
                "_validated_historical_registry_binding",
                return_value=self.binding,
            ),
            self.assertRaisesRegex(ValueError, "authorization parent identity"),
        ):
            self.verify(integration_evidence=changed)

    def test_replay_rechecks_tree_boundary_and_rejects_third_tree_content(self) -> None:
        # Fully self-consistent signed artifacts still cannot authorize a manual
        # clean-path delta. Failure must reach the maintained tree verifier.
        self.git("read-tree", self.tree)
        (self.root / "third-tree.txt").write_text("not supplied by either parent\n")
        self.git("add", "third-tree.txt")
        wrong_tree = self.git("write-tree")
        changed = copy.deepcopy(self.integration)
        changed["validated_tree_sha"] = wrong_tree
        receipt = integration.create_validation_receipt(
            evidence=changed,
            registry=self.binding,
            successful_result=True,
            receipt_id="wrong-tree",
        )
        message = (
            "third tree\n\nSecPal-Pre-Enrollment-Integration: "
            + fast_path.digest_json(changed)
            + "\nSecPal-Pre-Enrollment-Validation-Receipt: "
            + receipt["receipt_digest"]
        )
        head = self.git(
            "commit-tree",
            wrong_tree,
            "-p",
            self.parent1,
            "-p",
            self.parent2,
            "-S",
            "-m",
            message,
        )
        attestation = integration.create_final_attestation(
            evidence=changed,
            registry=self.binding,
            receipt=receipt,
            candidate_head_sha=head,
            candidate_parent_shas=[self.parent1, self.parent2],
            candidate_tree_sha=wrong_tree,
            verified_signer=SIGNER,
            signature_format="ssh",
            attestation_id="wrong-tree",
        )
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "manual conflict-resolution delta"
        ):
            self.verify(
                head_sha=head,
                integration_evidence=changed,
                validation_receipt=receipt,
                final_attestation=attestation,
            )
        validation = self.verify()
        with mock.patch.object(
            actions,
            "_verify_integration_tree_delta",
            side_effect=fast_path.SecurityBlocker("tree changed"),
        ):
            self.assertFalse(fast_path.is_verified_validation_evidence(validation))

    def test_foreign_authorization_and_substituted_registry_are_rejected(self) -> None:
        changed = copy.deepcopy(self.integration)
        changed["authorization"] = integration.create_authorization(
            authorization_id="foreign",
            repository="SecPal/.github",
            delivery_issue=777,
            pull_request=800,
            draft_head_sha=self.parent1,
            current_main_sha=self.parent2,
            expected_signer=SIGNER,
            signer_identity=AUTHORIZER,
            signer=self.sign,
        )
        changed["authorization_digest"] = changed["authorization"][
            "authorization_digest"
        ]
        with self.assertRaisesRegex(ValueError, "authorization delivery identity"):
            self.verify(integration_evidence=changed)
        altered = copy.deepcopy(self.binding)
        altered["validation"] = []
        with mock.patch.object(
            fast_path, "_validated_historical_registry_binding", return_value=altered
        ):
            with self.assertRaisesRegex(ValueError, "command-set identity"):
                self.verify()
        altered = copy.deepcopy(self.binding)
        altered.pop("pre_enrollment_integration_policy")
        with mock.patch.object(
            fast_path, "_validated_historical_registry_binding", return_value=altered
        ):
            with self.assertRaisesRegex(fast_path.SecurityBlocker, "did not support"):
                self.verify()

    def test_real_isolated_child_replays_signed_bootstrap_and_raw_history(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        source = Path(directory.name)
        shutil.copytree(
            ROOT / "scripts",
            source / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(ROOT / "docs/schemas", source / "docs/schemas")
        for relative, raw in (
            (fast_path.DELIVERY_REGISTRY_PATH, self.registry_raw),
            (fast_path.DELIVERY_REGISTRY_SCHEMA_RELATIVE_PATH, self.schema_raw),
            (
                "policies/legacy-enrolled-package-loss.json",
                (ROOT / "policies/legacy-enrolled-package-loss.json").read_text(),
            ),
        ):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
        # Only provider transport is a fixture. All authority, registry, raw
        # history, signature and tree checks execute unmodified in the child.
        helper = source / "scripts/secpal-pr-review-actions.py"
        with helper.open("a") as stream:
            stream.write(
                "\ndef _run_bridge_gh(arguments):\n"
                "    endpoint = arguments[3]\n"
                "    main = _run_attestation_git(REPOSITORY_ROOT, ['rev-parse', 'HEAD']).stdout.strip()\n"
                "    if endpoint.endswith('/branches/main'):\n"
                "        value = {'sha': main, 'protected': True}\n"
                "    elif '/commits/' in endpoint:\n"
                "        value = {'sha': endpoint.rsplit('/', 1)[1], 'verified': True, 'verification': {'verified': True, 'reason': 'valid'}}\n"
                "        value.pop('verified' if '\"verification\":' in arguments[-1] else 'verification')\n"
                "    else:\n"
                "        value = {'full_name': 'SecPal/.github', 'default_branch': 'main'}\n"
                "    return subprocess.CompletedProcess(arguments, 0, json.dumps(value), '')\n"
            )

        def git(*arguments):
            return subprocess.check_output(
                ["git", *arguments], cwd=source, stderr=subprocess.PIPE, text=True
            ).strip()

        git("init", "--quiet")
        git("config", "user.name", "Fixture")
        git("config", "user.email", SIGNER)
        git("fetch", "--quiet", "--no-tags", str(self.root), self.parent2)
        admission = source / "scripts/secpal_pr_review/bootstrap_source_admission.py"
        with admission.open("a") as stream:
            stream.write(
                "\n_fixture_git = _git\n"
                "def _git(root, arguments, **kwargs):\n"
                "    if arguments[:3] == ['fetch', '--quiet', '--no-tags']:\n"
                f"        arguments = [*arguments[:4], {str(self.root)!r}, *arguments[5:]]\n"
                "    result = _fixture_git(root, arguments, **kwargs)\n"
                "    return result\n"
            )
        git("add", "scripts", ".agents", "policies", "docs")
        main_oid = git(
            "commit-tree",
            git("write-tree"),
            "-p",
            self.parent2,
            "-m",
            "accepted tooling",
        )
        git("update-ref", "refs/heads/main", main_oid)
        original_git = bootstrap_source_admission._git

        def transport(root, arguments, **kwargs):
            if arguments == [
                "remote",
                "add",
                "origin",
                bootstrap_source_admission.PROTECTED_MAIN_REMOTE_URL,
            ]:
                arguments = ["remote", "add", "origin", str(source)]
            return original_git(root, arguments, **kwargs)

        # The child transports the exact candidate object from the same fixture
        # remote, without inheriting the supplied candidate checkout's Git config.
        git("fetch", "--quiet", "--no-tags", str(self.root), self.head)
        observation = bootstrap_source_admission.ProtectedMainObservation(
            json.dumps(
                {
                    "data": {
                        "repository": {
                            "nameWithOwner": "SecPal/.github",
                            "defaultBranchRef": {
                                "name": "main",
                                "target": {"oid": main_oid},
                            },
                        }
                    }
                }
            ).encode()
        )
        # Deliberately replace the operational path with a foreign checkout.
        # Its configuration and import tree cannot become replay authority.
        hostile = source / "candidate-context"
        hostile.mkdir()
        subprocess.run(["git", "init", "--quiet", str(hostile)], check=True)
        (hostile / ".git/info/grafts").write_text(f"{self.parent1} {self.parent2}\n")
        (hostile / ".git/info/attributes").write_text("* merge=foreign\n")
        subprocess.run(
            ["git", "-C", str(hostile), "config", "merge.foreign.driver", "false"],
            check=True,
        )
        link = source / "candidate-path"
        link.symlink_to(hostile, target_is_directory=True)
        real_child = bootstrap_source_admission._run_isolated_python

        def checked_child(*args, **kwargs):
            result = real_child(*args, **kwargs)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result

        with (
            mock.patch.object(
                bootstrap_source_admission,
                "_isolated_bootstrap_validation_repository",
                side_effect=self.real_materializer,
            ),
            mock.patch.object(
                bootstrap_source_admission,
                "_run_isolated_python",
                side_effect=checked_child,
            ),
            mock.patch.object(
                bootstrap_source_admission, "_git", side_effect=transport
            ),
            mock.patch.object(
                bootstrap_source_admission,
                "_observe_protected_main",
                return_value=observation,
            ),
            mock.patch.object(
                bootstrap_source_admission,
                "_run_bootstrap_validation_isolated",
                side_effect=self.real_isolated_runner,
            ),
        ):
            validation = self.verify(repository_root=link)
            self.assertTrue(fast_path.is_verified_validation_evidence(validation))
            self.assertEqual(validation.head_sha, self.head)
            hostile.rename(source / "replaced-candidate-context")
            hostile.mkdir()
            self.assertTrue(fast_path.is_verified_validation_evidence(validation))

    def test_current_main_guard_authenticates_actual_candidate_bytes(self) -> None:
        # Exercise the real maintained file check; remote observations alone do
        # not let this unaccepted implementation act as accepted-main authority.
        with self.assertRaises(actions.fast_path.SecurityBlocker):
            actions._require_accepted_main_tooling_blobs(
                ROOT, self.git("rev-parse", self.parent2)
            )


class BootstrapIsolationTests(TestCase):
    """Real materialization and isolated interpreter; only the remote is a fixture.

    The tiny accepted verifier is an import-boundary fixture, not evidence that
    bootstrap cryptography succeeds. The signed-object tests above own replay.
    """

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "accepted"
        self.source.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")
        package = self.source / "scripts/secpal_pr_review"
        package.mkdir(parents=True)
        (package / "bootstrap_source_admission.py").write_text(
            "MAXIMUM_EVIDENCE_BYTES = 65536\n"
        )
        (package / "sibling.py").write_text('IDENTITY = "accepted"\n')
        (package / "fast_path.py").write_text(
            "import json, os, sys\n"
            "from . import sibling\n"
            "def canonical_json_bytes(value):\n"
            " return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\\n').encode()\n"
            "def _replay_pre_enrollment_validation_unsealed(value):\n"
            " assert sibling.IDENTITY == 'accepted'\n"
            " assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode\n"
            " assert all(key not in os.environ for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONUSERBASE', 'VIRTUAL_ENV'))\n"
            " assert 'sitecustomize' not in sys.modules and 'usercustomize' not in sys.modules\n"
            " assert value == {'input': 'closed artifact'}\n"
            " return {'verifier': 'accepted', 'pid': os.getpid()}\n"
            "def _validation_evidence_binding(value):\n"
            " return value\n"
        )
        self.main = self.commit()
        original_git = bootstrap_source_admission._git

        def remote_transport(root, arguments, **kwargs):
            if arguments == [
                "remote",
                "add",
                "origin",
                bootstrap_source_admission.PROTECTED_MAIN_REMOTE_URL,
            ]:
                arguments = ["remote", "add", "origin", str(self.source)]
            return original_git(root, arguments, **kwargs)

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            mock.patch.object(
                bootstrap_source_admission, "_git", side_effect=remote_transport
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                bootstrap_source_admission,
                "_observe_protected_main",
                side_effect=lambda: bootstrap_source_admission.ProtectedMainObservation(
                    json.dumps(
                        {
                            "data": {
                                "repository": {
                                    "nameWithOwner": "SecPal/.github",
                                    "defaultBranchRef": {
                                        "name": "main",
                                        "target": {"oid": self.main},
                                    },
                                }
                            }
                        }
                    ).encode()
                ),
            )
        )

    def git(self, *arguments, input=None):
        return subprocess.check_output(
            ["git", *arguments],
            cwd=self.source,
            input=input,
            stderr=subprocess.PIPE,
            text=True,
        ).strip()

    def commit(self):
        self.git("add", "scripts")
        oid = self.git("commit-tree", self.git("write-tree"), "-m", "accepted fixture")
        self.git("update-ref", "refs/heads/main", oid)
        return oid

    def verify(self):
        result = bootstrap_source_admission._run_bootstrap_validation_isolated(
            {"input": "closed artifact"}
        )
        self.assertEqual(result["verifier"], "accepted")
        self.assertNotEqual(result["pid"], os.getpid())

    def test_parent_module_cache_and_forged_metadata_are_irrelevant(self) -> None:
        expected = str(ROOT / "scripts/secpal_pr_review/fast_path.py")
        for name in (
            "scripts.secpal_pr_review.fast_path",
            "scripts.secpal_pr_review.sibling",
            "secpal_bootstrap_source_accepted_main_actions",
        ):
            for metadata in (
                {},
                {"__file__": expected},
                {"__spec__": SimpleNamespace(origin=expected)},
                {"__file__": expected, "__spec__": SimpleNamespace(origin=expected)},
            ):
                foreign = ModuleType(name)
                foreign.__dict__.update(metadata)
                exec(
                    compile(
                        "raise_if_used = lambda *args: (_ for _ in ()).throw(AssertionError('candidate authority'))",
                        "/candidate-local/verifier.py",
                        "exec",
                    ),
                    foreign.__dict__,
                )
                foreign._require_accepted_main_bridge_source = foreign.raise_if_used
                foreign._replay_pre_enrollment_validation_unsealed = (
                    foreign.raise_if_used
                )
                with (
                    self.subTest(name=name, metadata=tuple(metadata)),
                    mock.patch.dict(sys.modules, {name: foreign}),
                ):
                    self.verify()

    def test_candidate_pythonpath_startup_site_and_sibling_shadowing_are_irrelevant(
        self,
    ) -> None:
        candidate = self.root / "candidate"
        package = candidate / "scripts/secpal_pr_review"
        package.mkdir(parents=True)
        marker = self.root / "injected"
        attack = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nraise AssertionError('candidate code')\n"
        for relative in (
            "sitecustomize.py",
            "usercustomize.py",
            "startup.py",
            "scripts/__init__.py",
            "scripts/secpal_pr_review/fast_path.py",
            "scripts/secpal_pr_review/sibling.py",
        ):
            (candidate / relative).write_text(attack)
        site = (
            candidate
            / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        )
        site.mkdir(parents=True)
        (site / "sitecustomize.py").write_text(attack)
        (site / "inject.pth").write_text("import sitecustomize\n")
        with mock.patch.dict(
            os.environ,
            {
                "PYTHONPATH": str(candidate) + os.pathsep + str(site),
                "PYTHONHOME": str(candidate),
                "PYTHONSTARTUP": str(candidate / "startup.py"),
                "PYTHONUSERBASE": str(candidate),
                "VIRTUAL_ENV": str(candidate),
            },
        ):
            self.verify()
        self.assertFalse(marker.exists())

    def test_materialized_import_symlink_and_bytecode_are_rejected(self) -> None:
        sibling = self.source / "scripts/secpal_pr_review/sibling.py"
        sibling.unlink()
        sibling.symlink_to("/candidate-local/sibling.py")
        self.main = self.commit()
        with self.assertRaisesRegex(
            bootstrap_source_admission.BootstrapSourceAdmissionError, "import source"
        ):
            self.verify()
        sibling.unlink()
        sibling.write_text('IDENTITY = "accepted"\n')
        (sibling.parent / "fast_path.pyc").write_bytes(b"foreign bytecode")
        self.main = self.commit()
        with self.assertRaisesRegex(
            bootstrap_source_admission.BootstrapSourceAdmissionError, "import source"
        ):
            self.verify()


if __name__ == "__main__":
    main()
