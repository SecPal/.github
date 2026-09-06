# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hermetic regressions for authenticated pre-enrollment Draft integration."""

from __future__ import annotations

import importlib.util
import copy
from pathlib import Path
import sys
from unittest import TestCase, main, mock

from scripts.secpal_pr_review import fast_path
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


def registry() -> dict[str, object]:
    return {
        "repository": "SecPal/.github",
        "default_branch": "main",
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
        proof = integration.verify_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, attestation=attestation, commit_trailers={"SecPal-Pre-Enrollment-Integration": attestation["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"]})
        self.assertEqual(proof.initial_head_sha, CANDIDATE)
        for mutation in ("receipt", "attestation", "cross-issue", "cross-pr"):
            bad_receipt = copy.deepcopy(receipt); bad_attestation = copy.deepcopy(attestation); bad_evidence = copy.deepcopy(normalized)
            if mutation == "receipt": bad_receipt["receipt_id"] = "stale"
            elif mutation == "attestation": bad_attestation["attestation_id"] = "stale"
            elif mutation == "cross-issue": bad_evidence["delivery_issue"] = 777
            else: bad_evidence["pull_request"] = 801
            with self.assertRaises(integration.PreEnrollmentIntegrationError):
                integration.verify_final_attestation(evidence=bad_evidence, registry=registry(), receipt=bad_receipt, attestation=bad_attestation, commit_trailers={})

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
        proof = integration.verify_final_attestation(evidence=normalized, registry=registry(), receipt=receipt, attestation=attestation, commit_trailers={"SecPal-Pre-Enrollment-Integration": attestation["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"]})
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
        calls = {"observe": 0, "create": 0, "push": 0, "final": 0}

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
            return True

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
            push_fast_forward=push, observe_final_pr_head=final,
            receipt_id="receipt-001", attestation_id="attestation-001",
        )
        self.assertEqual(result.candidate_head_sha, CANDIDATE)
        self.assertEqual(calls, {"observe": 1, "create": 1, "push": 1, "final": 1})

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
                push_fast_forward=push, observe_final_pr_head=lambda: CANDIDATE,
                receipt_id="receipt-001", attestation_id="attestation-001",
            )
        self.assertEqual(calls, {"observe": 1, "create": 0, "push": 0})


if __name__ == "__main__":
    main()
