# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hermetic regressions for authenticated pre-enrollment Draft integration."""

from __future__ import annotations

import importlib.util
import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
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


class DeploymentIntegrationPolicyTests(TestCase):
    repository = "SecPal/deployment"
    delivery_issue = 81
    pull_request = 286

    def setUp(self) -> None:
        self.registry = actions.load_registry()
        self.entry = actions.select_repository(self.registry, self.repository)
        self.arguments = SimpleNamespace(
            apply=True, receipt_output="unused-receipt",
            attestation_output="unused-attestation", commit_subject="test admission",
            repo_root=str(ROOT), repo=self.repository, registry=None,
            evidence="unused-evidence", pr=self.pull_request, delivery_issue=self.delivery_issue,
            authorization_id="exact-policy-001", expected_signer=SIGNER,
        )

    def test_policy_and_maintained_projections_agree(self) -> None:
        expected = registry()["pre_enrollment_integration_policy"]
        self.assertEqual(self.entry["pre_enrollment_integration_policy"], expected)
        resolver_spec = importlib.util.spec_from_file_location(
            "integration_policy_resolver", ROOT / "scripts/secpal-resolve-fixed-threads.py"
        )
        assert resolver_spec is not None and resolver_spec.loader is not None
        resolver = importlib.util.module_from_spec(resolver_spec)
        sys.modules[resolver_spec.name] = resolver
        resolver_spec.loader.exec_module(resolver)
        binding = fast_path.validation_registry_projection(self.entry)
        self.assertEqual(binding["pre_enrollment_integration_policy"], expected)
        self.assertEqual(actions._fast_registry_binding(self.entry), binding)
        self.assertEqual(resolver._validation_registry_binding(self.entry), binding)
        self.assertIn("BRANCH_WRITE", self.entry["unsupported_operations"])
        admitted = {
            entry["repository"] for entry in self.registry["repositories"]
            if "pre_enrollment_integration_policy" in entry
        }
        self.assertEqual(admitted, {"SecPal/.github", "SecPal/api", "SecPal/contracts", "SecPal/android", "SecPal/secpal.app", "SecPal/deployment"})
        self.assertEqual(
            actions.select_repository(self.registry, "SecPal/.github")[
                "pre_enrollment_integration_policy"
            ], expected,
        )

    def selected_evidence(self) -> dict:
        binding = actions._fast_registry_binding(self.entry)
        selected = evidence()
        selected.update(repository=self.repository, delivery_issue=self.delivery_issue, pull_request=self.pull_request)
        authorization = integration.create_authorization(
            authorization_id=self.arguments.authorization_id,
            repository=self.repository, delivery_issue=self.delivery_issue, pull_request=self.pull_request,
            draft_head_sha=PARENT_1, current_main_sha=PARENT_2,
            expected_signer=SIGNER, signer_identity=AUTHORIZER, signer=fake_signer,
        )
        selected.update(
            authorization=authorization,
            authorization_digest=authorization["authorization_digest"],
            validation_execution={
                "registry_digest": fast_path.digest_json(binding),
                "command_set_digest": fast_path.digest_json(binding["validation"]),
            },
        )
        return selected

    def test_executor_admits_exact_repository_selection_before_tree_validation(self) -> None:
        with (
            mock.patch.object(actions, "_attestation_local_state", return_value=(PARENT_1, "")),
            mock.patch.object(actions, "_read_pre_enrollment_json", return_value=self.selected_evidence()) as read,
            mock.patch.object(actions, "_staged_tree", return_value="f" * 40) as tree,
            mock.patch.object(actions, "_create_signed_pre_enrollment_commit") as candidate,
            mock.patch.object(actions, "_push_pre_enrollment_commit") as push,
            self.assertRaisesRegex(actions.fast_path.SecurityBlocker, "staged tree is not the exact authorized integration tree"),
        ):
            actions._command_integrate_pre_enrollment_draft(self.arguments)
        read.assert_called_once()
        tree.assert_called_once()
        candidate.assert_not_called()
        push.assert_not_called()

    def test_missing_or_substituted_policy_fails_before_evidence_or_mutation(self) -> None:
        mutations = [
            ("missing", None), ("malformed", []),
            *[(field, {**registry()["pre_enrollment_integration_policy"], field: value})
              for field, value in (
                  ("schema_version", "2.0"), ("force_push", True),
                  ("automatic_retry", True), ("maximum_candidates", 2),
                  ("maximum_pushes", 2), ("merge_pull_request", True),
                  ("command", "push"), ("topology_kind", "TWO_PARENT_READY_INTEGRATION"),
                  ("allowed_mutation", "BRANCH_WRITE"), ("caller_branch", "arbitrary"),
              )],
        ]
        for name, policy in mutations:
            with self.subTest(policy=name):
                fixture = copy.deepcopy(self.registry)
                entry = next(item for item in fixture["repositories"] if item["repository"] == self.arguments.repo)
                if policy is None:
                    entry.pop("pre_enrollment_integration_policy", None)
                else:
                    entry["pre_enrollment_integration_policy"] = policy
                with (
                    mock.patch.object(actions, "load_registry", return_value=fixture),
                    mock.patch.object(actions, "_attestation_local_state", return_value=(PARENT_1, "")),
                    mock.patch.object(actions, "_read_pre_enrollment_json") as read,
                    mock.patch.object(actions, "_create_signed_pre_enrollment_commit") as candidate,
                    mock.patch.object(actions, "_push_pre_enrollment_commit") as push,
                    mock.patch.object(actions, "_load_lifecycle_publication_helpers") as lifecycle,
                    mock.patch.object(actions, "_verify_pre_enrollment_external_authority") as provider,
                    self.assertRaises((actions.RegistryError, actions.fast_path.SecurityBlocker)),
                ):
                    actions._command_integrate_pre_enrollment_draft(self.arguments)
                read.assert_not_called()
                candidate.assert_not_called()
                push.assert_not_called()
                lifecycle.assert_not_called()
                provider.assert_not_called()
        with self.assertRaisesRegex(actions.RegistryError, "unsupported repository"):
            actions.select_repository(self.registry, "Other/deployment")


class SecpalAppIntegrationPolicyTests(DeploymentIntegrationPolicyTests):
    repository = "SecPal/secpal.app"
    delivery_issue = 332
    pull_request = 333

    def test_policy_on_another_repository_does_not_admit_target(self) -> None:
        fixture = copy.deepcopy(self.registry)
        for entry in fixture["repositories"]:
            if entry["repository"] == self.repository:
                entry.pop("pre_enrollment_integration_policy", None)
            if entry["repository"] == "SecPal/.github":
                entry["pre_enrollment_integration_policy"] = copy.deepcopy(
                    registry()["pre_enrollment_integration_policy"]
                )
        with (
            mock.patch.object(actions, "load_registry", return_value=fixture),
            mock.patch.object(actions, "_attestation_local_state", return_value=(PARENT_1, "")),
            mock.patch.object(actions, "_read_pre_enrollment_json") as read,
            mock.patch.object(actions, "_create_signed_pre_enrollment_commit") as candidate,
            mock.patch.object(actions, "_push_pre_enrollment_commit") as push,
            self.assertRaisesRegex(actions.fast_path.SecurityBlocker, "repository has no closed pre-enrollment integration policy"),
        ):
            actions._command_integrate_pre_enrollment_draft(self.arguments)
        read.assert_not_called()
        candidate.assert_not_called()
        push.assert_not_called()

    def test_caller_evidence_cannot_substitute_repository_or_policy(self) -> None:
        selected = self.selected_evidence()
        for mutation in (
            {"repository": "SecPal/.github"},
            {"pre_enrollment_integration_policy": registry()["pre_enrollment_integration_policy"]},
        ):
            with self.subTest(mutation=mutation):
                substituted = {**selected, **mutation}
                with (
                    mock.patch.object(actions, "_attestation_local_state", return_value=(PARENT_1, "")),
                    mock.patch.object(actions, "_read_pre_enrollment_json", return_value=substituted),
                    mock.patch.object(actions, "_staged_tree") as tree,
                    mock.patch.object(actions, "_create_signed_pre_enrollment_commit") as candidate,
                    mock.patch.object(actions, "_push_pre_enrollment_commit") as push,
                    self.assertRaises(actions.fast_path.SecurityBlocker),
                ):
                    actions._command_integrate_pre_enrollment_draft(self.arguments)
                tree.assert_not_called()
                candidate.assert_not_called()
                push.assert_not_called()


class ApiIntegrationPolicyTests(SecpalAppIntegrationPolicyTests):
    repository = "SecPal/api"
    delivery_issue = 900001
    pull_request = 900002


class ContractsIntegrationPolicyTests(SecpalAppIntegrationPolicyTests):
    repository = "SecPal/contracts"
    delivery_issue = 900001
    pull_request = 900002


class AndroidIntegrationPolicyTests(SecpalAppIntegrationPolicyTests):
    repository = "SecPal/android"
    delivery_issue = 900001
    pull_request = 900002


class PreEnrollmentIntegrationBoundaryTests(TestCase):
    def test_deleted_fork_repository_normalizes_to_ineligible_facts(self) -> None:
        runner = mock.Mock()
        runner.run.return_value = {"data": {"repository": {
            "nameWithOwner": "SecPal/.github", "defaultBranchRef": {"name": "main", "target": {"oid": PARENT_2}},
            "pullRequest": {
                "number": 900002, "state": "OPEN", "isDraft": True, "headRefName": "delivery", "headRefOid": PARENT_1,
                "baseRefName": "main", "baseRepository": {"nameWithOwner": "SecPal/.github"}, "headRepository": None,
                "closingIssuesReferences": {"nodes": [{"repository": {"nameWithOwner": "SecPal/.github"}, "number": 900001, "state": "OPEN"}], "pageInfo": {"hasNextPage": False}},
            },
        }}}
        github = actions.LiveGitHub(runner)
        graph = {"issue": {"claims": [{"pull_request": "SecPal/.github#900002"}],
                           "leaf": True, "blocked": False, "ready": True}}
        publication = SimpleNamespace(verify_pre_enrollment_absence=lambda *_: SimpleNamespace(evidence_digest="4" * 64))
        with (
            mock.patch.object(actions, "_observe_pre_enrollment_work_graph", return_value=graph),
            mock.patch.object(actions, "_authenticate_protected_bridge_main", return_value=PARENT_2),
            mock.patch.object(actions, "LiveGitHub", return_value=github),
            self.assertRaisesRegex(actions.fast_path.SecurityBlocker, "Draft PR observation"),
        ):
            actions._observe_pre_enrollment_state(ROOT, "SecPal/.github", 900001, 900002, registry(), publication)
        # Preserve the existing Ready family's rejection, rather than letting
        # nullable-repository normalization accidentally admit its missing head.
        runner.run.return_value["data"]["repository"]["pullRequest"]["isDraft"] = False
        with mock.patch.object(actions, "LiveGitHub", return_value=github), self.assertRaises(
            (actions.MutationBlocked, actions.MutationFailure, AttributeError, TypeError)
        ):
            actions._observe_ready_integration_authority_once("SecPal/.github", 900002)

    def test_graph_observation_cannot_load_caller_python_or_node_code(self) -> None:
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/untrusted", "NODE_OPTIONS": "--require=/untrusted.js"}), mock.patch.object(actions.subprocess, "run") as run:
            actions._run_pre_enrollment_work_graph(ROOT, ["graph.py", "validate-issue", "SecPal/.github#900001"])
        self.assertIn("-I", run.call_args.args[0])
        self.assertNotIn("NODE_OPTIONS", run.call_args.kwargs["env"])
        self.assertNotIn("PYTHONPATH", run.call_args.kwargs["env"])

    def test_production_preparation_accepts_only_target_selectors(self) -> None:
        arguments = actions.build_parser().parse_args([
            "prepare-pre-enrollment-draft-integration", "--repo", "SecPal/.github",
            "--delivery-issue", "900001", "--pr", "900002", "--repo-root", str(ROOT),
            "--authorization-id", "integration-001", "--output", "integration.json",
        ])
        self.assertEqual(arguments.authorization_id, "integration-001")
        self.assertFalse(hasattr(arguments, "registry"))
        self.assertFalse(hasattr(arguments, "expected_signer"))
        self.assertFalse(hasattr(arguments, "evidence"))

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
            "accepted_formats": ["ssh"],
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


class ProductionPreparationTests(TestCase):
    """Real Git derivation; provider fixtures prove behavior, not live authority."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="secpal-producer-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "candidate"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", "https://github.com/SecPal/.github.git")
        (self.root / "shared").write_text("base\n")
        self.commit()
        self.git("checkout", "-q", "-b", "delivery")
        (self.root / "draft").write_text("draft\n")
        self.commit()
        self.head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        (self.root / "main").write_text("main\n")
        self.commit()
        self.main_head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "delivery")
        self.arguments = SimpleNamespace(
            repo="SecPal/.github", delivery_issue=900001, pr=900002,
            repo_root=str(self.root), authorization_id="integration-001",
            output=str(Path(self.directory.name) / "integration.json"),
        )
        self.live = {
            "repository": self.arguments.repo, "pull_request_number": self.arguments.pr,
            "state": "OPEN", "draft": True, "head_ref": "delivery", "head_sha": self.head,
            "base_repository": self.arguments.repo, "head_repository": self.arguments.repo,
            "base_ref": "main", "base_sha": self.main_head,
            "closing_issues_complete": True,
            "closing_issues": [{"repository": self.arguments.repo,
                                "number": self.arguments.delivery_issue, "state": "OPEN"}],
        }
        self.graph = {"complete": True, "findings": [], "issue": {
            "key": f"{self.arguments.repo}#{self.arguments.delivery_issue}",
            "leaf": True, "ready": True, "blocked": False, "malformed": False,
            "reasons": [], "claims": [{"pull_request": f"{self.arguments.repo}#{self.arguments.pr}"}],
        }}
        self.helpers = actions._load_enrolled_draft_integration_helper()
        self.policy = SimpleNamespace(transition_signer_identities=frozenset({AUTHORIZER}))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target, name, kwargs in (
            (actions, "_require_accepted_main_bridge_source", {"return_value": actions._run_attestation_git(ROOT, ["rev-parse", "HEAD"]).stdout.strip()}),
            (actions, "_load_enrolled_draft_integration_helper", {"return_value": self.helpers}),
            (actions, "_load_lifecycle_publication_helpers", {"return_value": (self.helpers.authority, self.helpers.publication)}),
            (actions, "_authenticate_protected_bridge_main", {"return_value": self.main_head}),
            (actions.LiveGitHub, "observe_ready_integration_authority", {"side_effect": lambda *_: copy.deepcopy(self.live)}),
            (actions, "_run_pre_enrollment_work_graph", {"side_effect": lambda *_: SimpleNamespace(returncode=0, stdout=json.dumps(self.graph))}),
            (self.helpers.publication, "verify_pre_enrollment_absence", {"return_value": SimpleNamespace(evidence_digest="4" * 64)}),
            (self.helpers.authority, "_load_lifecycle_trust_policy", {"return_value": self.policy}),
            (self.helpers.execution, "_policy_role_signer", {"return_value": (AUTHORIZER, fake_signer)}),
            (self.helpers.authority, "_policy_signature_verifier", {"return_value": lambda *_: True}),
            (self.helpers.authority, "_verify_signature", {"side_effect": self.verify_signature}),
        ):
            self.stack.enter_context(mock.patch.object(target, name, **kwargs))

    def git(self, *argv: str) -> str:
        return subprocess.run(["git", *argv], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self) -> None:
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    @staticmethod
    def verify_signature(payload, signature, signer, domain, *_):
        if signature != fake_signer(payload, domain) or signer != AUTHORIZER:
            raise actions.fast_path.SecurityBlocker("authorization mismatch")
        return True

    def prepare(self) -> dict:
        actions._command_prepare_pre_enrollment_draft_integration(self.arguments)
        return integration.loads_closed_json(Path(self.arguments.output).read_bytes())

    def test_produces_admitted_package_without_caller_authored_facts_or_mutation(self) -> None:
        before = self.git("status", "--porcelain=v2")
        with mock.patch.object(actions, "_push_pre_enrollment_commit") as push:
            package = self.prepare()
        binding = actions._fast_registry_binding(actions.select_repository(actions.load_registry(), self.arguments.repo))
        self.assertEqual(integration.normalize_evidence(package, registry=binding), package)
        actions._verify_pre_enrollment_external_authority(package, self.root)
        tree, conflicts = actions._mechanical_integration_result(self.root, [self.head, self.main_head])
        integration.verify_combined_tree(package, mechanical_tree_sha=tree,
                                         conflict_paths=conflicts, observed_delta=[], retained_conflict_markers=False)
        self.assertEqual(package["validated_tree_sha"], tree)
        self.assertEqual(package["ordered_parent_shas"], [self.head, self.main_head])
        self.assertEqual(self.git("rev-parse", "HEAD"), self.head)
        self.assertEqual(self.git("status", "--porcelain=v2"), before)
        push.assert_not_called()

    def test_observation_rejects_wrong_delivery_state_graph_or_absence(self) -> None:
        base_live, base_graph = copy.deepcopy(self.live), copy.deepcopy(self.graph)
        cases = [
            ("live", key, value) for key, value in (
                ("repository", "Other/repo"), ("head_repository", "Other/repo"),
                ("base_repository", "Other/repo"), ("pull_request_number", 900003),
                ("state", "CLOSED"), ("draft", False), ("head_sha", "a" * 40),
                ("base_ref", "release"), ("base_sha", "b" * 40),
                ("closing_issues_complete", False), ("closing_issues", []),
                ("head_ref", "bad ref"),
            )
        ] + [("issue", key, value) for key, value in (
            ("key", "SecPal/.github#900003"), ("ready", False), ("blocked", True),
            ("malformed", True), ("leaf", False), ("reasons", ["unsatisfied_dependency"]),
            ("claims", []), ("claims", [{"pull_request": "SecPal/.github#900003"}]),
        )] + [("graph", "complete", False)]
        for kind, key, value in cases:
            with self.subTest(kind=kind, key=key, value=value):
                self.live, self.graph = copy.deepcopy(base_live), copy.deepcopy(base_graph)
                target = self.live if kind == "live" else self.graph["issue"] if kind == "issue" else self.graph
                target[key] = value
                with self.assertRaises((actions.fast_path.SecurityBlocker, integration.PreEnrollmentIntegrationError,
                                        actions.pre_enrollment.PreEnrollmentIntegrationError)):
                    self.prepare()
                self.assertFalse(Path(self.arguments.output).exists())
        self.live, self.graph = base_live, base_graph
        for reason in ("CURRENT exists", "native genesis exists", "HEAD_ADVANCED exists"):
            with self.subTest(reason=reason), mock.patch.object(
                self.helpers.publication, "verify_pre_enrollment_absence",
                side_effect=self.helpers.publication.LifecyclePublicationError(reason),
            ), self.assertRaises(actions.fast_path.SecurityBlocker):
                self.prepare()

    def test_independent_admission_rejects_forged_package_fields(self) -> None:
        package = self.prepare()
        cases = [
            ("draft_pr", "observation_digest", "5" * 64),
            ("current_main", "observation_digest", "5" * 64),
            ("work_graph", "evidence_digest", "5" * 64),
            ("lifecycle_absence", "evidence_digest", "5" * 64),
            ("validation_execution", "registry_digest", "5" * 64),
            ("validation_execution", "command_set_digest", "5" * 64),
            ("authorization", "authorization_id", "other-operation"),
            (None, "expected_signer", "substituted@example.invalid"),
        ]
        for section, key, value in cases:
            with self.subTest(section=section, key=key):
                forged = copy.deepcopy(package)
                (forged[section] if section else forged)[key] = value
                with self.assertRaises((actions.fast_path.SecurityBlocker, actions.pre_enrollment.PreEnrollmentIntegrationError)):
                    actions._verify_pre_enrollment_external_authority(forged, self.root)

    def test_drift_between_observation_and_admission_leaves_no_package(self) -> None:
        drifted = {**self.live, "head_sha": "a" * 40}
        with mock.patch.object(actions.LiveGitHub, "observe_ready_integration_authority",
                               side_effect=[self.live, drifted]), self.assertRaises(actions.pre_enrollment.PreEnrollmentIntegrationError):
            self.prepare()
        self.assertFalse(Path(self.arguments.output).exists())

    def test_independent_lifecycle_drift_is_a_bounded_cli_failure(self) -> None:
        class IndependentlyLoadedPublicationError(ValueError):
            pass

        publication = SimpleNamespace(
            LifecyclePublicationError=IndependentlyLoadedPublicationError,
            verify_pre_enrollment_absence=mock.Mock(side_effect=IndependentlyLoadedPublicationError("CURRENT appeared")),
        )
        with mock.patch.object(actions, "_load_lifecycle_publication_helpers", return_value=(self.helpers.authority, publication)), self.assertRaisesRegex(actions.fast_path.SecurityBlocker, "lifecycle absence"):
            self.prepare()
        self.assertFalse(Path(self.arguments.output).exists())

    def test_real_conflict_resolution_is_derived_and_bounded(self) -> None:
        self.git("checkout", "-q", "main")
        (self.root / "shared").write_text("main conflict\n")
        self.commit()
        self.main_head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "delivery")
        (self.root / "shared").write_text("draft conflict\n")
        self.commit()
        self.head = self.git("rev-parse", "HEAD")
        self.live.update(head_sha=self.head, base_sha=self.main_head)
        with mock.patch.object(actions, "_authenticate_protected_bridge_main", return_value=self.main_head):
            result = subprocess.run(["git", "merge", "--no-commit", self.main_head], cwd=self.root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                self.prepare()
            (self.root / "shared").write_text("resolved\n")
            self.git("add", "shared")
            package = self.prepare()
            self.assertEqual(package["mechanical_conflict_paths"], ["shared"])
            self.assertEqual([item["path"] for item in package["manual_conflict_resolution_delta"]], ["shared"])
            Path(self.arguments.output).unlink()
            (self.root / "unrelated").write_text("unrelated edit\n")
            self.git("add", "unrelated")
            with self.assertRaises(actions.pre_enrollment.PreEnrollmentIntegrationError):
                self.prepare()
            self.assertFalse(Path(self.arguments.output).exists())

    def test_package_composes_with_existing_executor_receipt_and_head_proof(self) -> None:
        package = self.prepare()
        binding = actions._fast_registry_binding(actions.select_repository(actions.load_registry(), self.arguments.repo))
        current = actions.pre_enrollment
        tree, conflicts = actions._mechanical_integration_result(self.root, package["ordered_parent_shas"])
        result = current.execute_once(
            evidence=package, registry=binding, accepted_authorization_signers=frozenset({AUTHORIZER}),
            authorization_verifier=lambda payload, signature, signer, domain: self.verify_signature(payload, signature, signer, domain),
            derive_tree=lambda *_: (tree, conflicts, [], False), run_registered_validation=lambda *_: True,
            observe_frozen_state=lambda: actions._observe_pre_enrollment_state(
                self.root, self.arguments.repo, self.arguments.delivery_issue, self.arguments.pr, binding, self.helpers.publication),
            create_signed_candidate=lambda tree, parents, trailers, signer: {
                "head_sha": CANDIDATE, "tree_sha": tree, "parent_shas": parents,
                "verified_signer": signer, "signature_format": "ssh"},
            persist_candidate_evidence=lambda *_: None, push_fast_forward=lambda *_: True,
            observe_final_pr_head=lambda: CANDIDATE, receipt_id="producer-receipt", attestation_id="producer-attestation",
        )
        self.assertTrue(current.is_verified_initial_head_proof(result.initial_head_proof))
        self.assertEqual(result.validation_receipt["integration_evidence_digest"], fast_path.digest_json(package))
        self.assertEqual(result.final_attestation["ordered_parent_shas"], [self.head, self.main_head])

    def test_output_cannot_overwrite_inputs_evidence_or_git_refs(self) -> None:
        for output in (self.root / "shared", self.root / ".git" / "refs" / "heads" / "new",
                       ROOT / "scripts" / "secpal-pr-review-actions.py"):
            with self.subTest(output=output), self.assertRaises(actions.fast_path.SecurityBlocker):
                self.arguments.output = str(output)
                self.prepare()
        self.arguments.output = str(Path(self.directory.name) / "existing.json")
        Path(self.arguments.output).write_text("retained evidence\n")
        with self.assertRaises(actions.fast_path.SecurityBlocker):
            self.prepare()
        self.assertEqual(Path(self.arguments.output).read_text(), "retained evidence\n")




if __name__ == "__main__":
    main()
