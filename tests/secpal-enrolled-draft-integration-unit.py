# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Enrolled initial Draft integration authority and execution regressions."""

from __future__ import annotations

import copy
from contextlib import ExitStack
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


draft = load_fixture("enrolled_draft_fixture", "tests/secpal-pre-enrollment-integration-unit.py")
lifecycle = load_fixture("enrolled_lifecycle_fixture", "tests/secpal-lifecycle-authority-unit.py")
ready = load_fixture("enrolled_ready_fixture", "tests/secpal-pr-review-actions-unit.py")
native = load_fixture("enrolled_native_fixture", "tests/secpal-lifecycle-execution-contract-unit.py")
from scripts.secpal_pr_review import enrolled_draft_integration as enrolled


def fixture_evidence():
    current = native.Harness(native.Chain()).current
    return {
        "schema_version": "1.0", "kind": enrolled.KIND,
        **enrolled.current_binding(current),
        "current_main": {"ref": "main", "sha": "b" * 40},
        "ordered_parent_shas": [current.lifecycle.head_sha, "b" * 40],
        "validated_tree_sha": "c" * 40,
        "tree_evidence": {
            "mechanical_merge_tree_sha": "c" * 40, "mechanical_conflict_paths": [],
            "manual_conflict_resolution_delta": [], "path_classifications": [],
        },
        "head_ref": "delivery", "work_graph_digest": "d" * 64,
        "registry_digest": enrolled.fast_path.digest_json({"validation": []}),
        "command_set_digest": enrolled.fast_path.digest_json([]),
        "expected_signer": native.SIGNER,
        "manual_gate_evidence": [],
    }


def sign_fields(fields, domain):
    signed = {**fields, "signature": native.signer_for()(enrolled.fast_path.canonical_json_bytes(fields), domain)}
    return {**signed, "authorization_digest": enrolled.fast_path.digest_json(signed)}


def fixture_authorizations(evidence=None):
    evidence = fixture_evidence() if evidence is None else evidence
    receipt = enrolled.fast_path.create_enrolled_draft_validation_receipt(evidence)
    common = {"schema_version": "1.0", "authorization_id": "integration-001", "evidence": evidence,
              "validation_receipt": receipt, "signer_identity": native.SIGNER}
    preparation = sign_fields({**common, "kind": enrolled.PREPARATION_AUTHORIZATION_KIND}, enrolled.PREPARATION_AUTHORIZATION_DOMAIN)
    attestation = enrolled.fast_path.create_enrolled_draft_final_attestation(
        evidence, receipt, candidate_head_sha="6" * 40, signature_fingerprint="SHA256:AAAA",
    )
    authorization = sign_fields({**common, "kind": enrolled.AUTHORIZATION_KIND,
                                 "final_attestation": attestation,
                                 "preparation_authorization_digest": preparation["authorization_digest"]}, enrolled.AUTHORIZATION_DOMAIN)
    return preparation, authorization


def signature_context():
    stack = ExitStack()
    stack.enter_context(mock.patch.object(enrolled.authority, "_load_lifecycle_trust_policy", side_effect=lambda repository: replace(native.policy_for(), repository=repository)))
    stack.enter_context(mock.patch.object(enrolled.authority, "_policy_signature_verifier", return_value=native.verify_signature))
    return stack


class MaintainedGapTests(TestCase):
    def test_head_advanced_preserves_initial_draft_state(self):
        chain = lifecycle.genesis_chain()
        before = chain.verify()
        chain.append("HEAD_ADVANCED", head=lifecycle.HEADS[1])
        after = chain.verify()
        self.assertEqual(after.lifecycle_id, before.lifecycle_id)
        self.assertEqual(after.pull_request, before.pull_request)
        self.assertEqual(after.state, before.state)
        self.assertNotEqual(after.head_sha, before.head_sha)

    def test_pre_enrollment_rejects_current_and_native_genesis(self):
        for field in ("current_publication", "native_genesis"):
            evidence = draft.evidence()
            evidence["lifecycle_absence"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(
                draft.integration.PreEnrollmentIntegrationError, "lifecycle-aware"
            ):
                draft.integration.normalize_evidence(evidence, registry=draft.registry())

    def test_ready_integration_requires_authenticated_ready_state(self):
        evidence = ready.ready_integration_prior_authority(ready.fast_feedback())
        evidence["lifecycle"].update(draft=True, ready=False)
        with self.assertRaises(ready.fast_path.SecurityBlocker):
            ready.fast_path.normalize_ready_integration_prior_authority(evidence)

    def test_production_executor_is_selectable(self):
        arguments = draft.actions.build_parser().parse_args([
            "integrate-enrolled-draft", "--repo", "SecPal/deployment",
            "--pr", "286", "--delivery-issue", "81",
            "--authorization", "authorization.json",
            "--apply",
        ])
        self.assertEqual(arguments.command, "integrate-enrolled-draft")

    def test_isolated_production_cli_loads_and_rejects_missing_apply(self):
        result = subprocess.run([
            sys.executable, "-I", str(ROOT / "scripts/secpal-pr-review-actions.py"),
            "integrate-enrolled-draft", "--repo", "SecPal/deployment", "--pr", "286",
            "--delivery-issue", "81", "--authorization", "not-read.json",
        ], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 3, result.stderr)
        report = json.loads(result.stderr)
        self.assertEqual(report["status"], "BLOCKED_SECURITY")
        self.assertIn("requires --apply", report["blocker"])


class EnrolledDraftAuthorityTests(TestCase):
    def test_work_graph_transport_failure_is_controlled(self):
        actions = SimpleNamespace(REPOSITORY_ROOT=ROOT,
            _run_pre_enrollment_work_graph=mock.Mock(side_effect=subprocess.TimeoutExpired("python", 1)))
        with self.assertRaises(enrolled.fast_path.RecoverableLocalError):
            enrolled._graph(actions, native.REPOSITORY, native.ISSUE)

    def test_signed_package_and_separate_preparation_authority(self):
        preparation, authorization = fixture_authorizations()
        with signature_context():
            self.assertEqual(enrolled.normalize_authorization(authorization), authorization)
            self.assertEqual(enrolled.normalize_authorization(preparation, allow_preparation=True), preparation)
            with self.assertRaises((ValueError, enrolled.fast_path.SecurityBlocker)):
                enrolled.normalize_authorization(preparation)

    def test_all_initial_state_counters_histories_and_proof_mode_are_closed(self):
        current = native.Harness(native.Chain()).current
        for key, value in (
            ("draft", False), ("ready", True), ("unrestricted_review_count", 1),
            ("remediation_cycle_count", 1), ("ready_transition_count", 1),
            ("ready_history", [{"transition_kind": "READY_TO_DRAFT"}]),
            ("exceptional_recovery_count", 1), ("exceptional_recovery_history", [{}]),
            ("exceptional_continuation_count", 1), ("exceptional_continuation_history", [{}]),
            ("cycle_3_absent", False), ("unrestricted_review_count", False),
        ):
            state = {**current.lifecycle.state, key: value}
            mutated = replace(current, lifecycle=replace(current.lifecycle, state=state))
            with self.subTest(key=key, value=value), self.assertRaises(enrolled.fast_path.SecurityBlocker):
                enrolled.require_initial_native_draft(mutated)
        with self.assertRaises(enrolled.fast_path.SecurityBlocker):
            enrolled.require_initial_native_draft(replace(current, lifecycle=replace(current.lifecycle, historical_proof_mode="EXACT_STATE_ADOPTION")))

    def test_stale_current_wrong_issue_pr_repository_and_root_are_rejected(self):
        current = native.Harness(native.Chain()).current
        evidence = fixture_evidence()
        for key, value in (("repository", "Other/repository"), ("delivery_issue", 81),
                           ("pull_request", 286), ("lifecycle_id", "another-root"),
                           ("current_publication_oid", "9" * 40),
                           ("current_publication_digest", "9" * 64),
                           ("predecessor_authority_digest", "9" * 64),
                           ("draft_head_sha", "9" * 40)):
            selected = {**evidence, key: value}
            with self.subTest(key=key), self.assertRaises(enrolled.fast_path.SecurityBlocker):
                enrolled.require_predecessor(current, selected)

    def test_zero_counters_do_not_admit_historical_corrections_or_replacement_pr(self):
        current = native.Harness(native.Chain()).current
        original = json.loads(current.serialized_lifecycle_evidence)
        for mutation in ("review", "rebound"):
            bundle = copy.deepcopy(original)
            if mutation == "review":
                bundle["transition_authorizations"].append({"transition_kind": "INVALID_REVIEW_CONSUMPTION_CORRECTED"})
            else:
                bundle["delivery_initialization"]["pull_request"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(enrolled.fast_path.SecurityBlocker):
                enrolled.require_initial_native_draft(replace(current, serialized_lifecycle_evidence=json.dumps(bundle).encode()))

    def test_wrong_family_unknown_fields_parent_order_and_parent_count(self):
        base = fixture_evidence()
        for update in ({"kind": "PRE_ENROLLMENT_DRAFT_INTEGRATION"},
                       {"kind": "TWO_PARENT_READY_INTEGRATION"},
                       {"transition_kind": "DRAFT_TO_READY"},
                       {"ordered_parent_shas": list(reversed(base["ordered_parent_shas"]))},
                       {"ordered_parent_shas": base["ordered_parent_shas"] + ["9" * 40]},
                       {"ordered_parent_shas": base["ordered_parent_shas"][:1]},
                       {"current_main": {"ref": "main", "sha": "9" * 40}}):
            with self.subTest(update=update), self.assertRaises((ValueError, enrolled.fast_path.SecurityBlocker)):
                enrolled.normalize_evidence({**base, **update})

    def test_signed_authorization_binds_receipt_tree_and_signer(self):
        _, original = fixture_authorizations()
        mutations = (
            lambda item: item["evidence"].update(validated_tree_sha="9" * 40),
            lambda item: item["validation_receipt"].update(successful_result=False),
            lambda item: item["final_attestation"].update(candidate_tree_sha="9" * 40),
            lambda item: item.update(signer_identity="substitute@secpal.app"),
            lambda item: item.update(transition_kind="DRAFT_TO_READY"),
        )
        with signature_context():
            for mutate in mutations:
                candidate = copy.deepcopy(original)
                mutate(candidate)
                candidate = sign_fields({key: value for key, value in candidate.items() if key not in {"signature", "authorization_digest"}}, enrolled.AUTHORIZATION_DOMAIN)
                with self.subTest(mutation=mutate), self.assertRaises((ValueError, enrolled.fast_path.SecurityBlocker)):
                    enrolled.normalize_authorization(candidate)
            candidate = copy.deepcopy(original)
            candidate["signature"]["value"] = "0" * 64
            candidate["authorization_digest"] = enrolled.fast_path.digest_json({key: value for key, value in candidate.items() if key != "authorization_digest"})
            with self.assertRaises(enrolled.authority.LifecycleAuthorityError):
                enrolled.normalize_authorization(candidate)

    def test_documented_enrolled_draft_registrations_match_registry(self):
        documentation = (ROOT / "scripts/README.md").read_text()
        paragraph = documentation.split(
            "The central `enrolled_draft_integration_policy`", 1
        )[1].split("Historical pre-enrollment absence", 1)[0]
        documented = set(re.findall(r"`(SecPal/[^`]+)`", paragraph))
        registered = {
            entry["repository"] for entry in draft.actions.load_registry()["repositories"]
            if "enrolled_draft_integration_policy" in entry
        }
        self.assertEqual(documented, registered)

    def test_registry_only_registers_closed_operation_for_delivery_repositories(self):
        registry = draft.actions.load_registry()
        admitted = {entry["repository"] for entry in registry["repositories"] if "enrolled_draft_integration_policy" in entry}
        self.assertEqual(admitted, {"SecPal/.github", "SecPal/api", "SecPal/frontend", "SecPal/contracts", "SecPal/android", "SecPal/secpal.app", "SecPal/deployment"})
        for repository in admitted:
            entry = draft.actions.select_repository(registry, repository)
            self.assertEqual(entry["enrolled_draft_integration_policy"], enrolled.POLICY)
            self.assertIn("BRANCH_WRITE", entry["unsupported_operations"])
        for key, value in (("force_push", True), ("maximum_candidates", 2),
                           ("maximum_pushes", 2), ("automatic_retry", True),
                           ("merge_pull_request", True), ("command", "push")):
            modified = copy.deepcopy(registry)
            modified["repositories"][0]["enrolled_draft_integration_policy"][key] = value
            with self.subTest(key=key), self.assertRaises(draft.actions.RegistryError):
                draft.actions.validate_registry(modified)


class FrontendEnrolledDraftPolicyTests(TestCase):
    repository = "SecPal/frontend"

    def setUp(self):
        self.registry = draft.actions.load_registry()
        self.entry = draft.actions.select_repository(self.registry, self.repository)

    def test_exact_policy_and_maintained_projections_agree(self):
        self.assertEqual(self.entry["enrolled_draft_integration_policy"], enrolled.POLICY)
        self.assertIn("lifecycle_authority_policy", self.entry)
        # A separate CLI first-load test must not execute inside the owned harness.
        code = f"""
import importlib.util, json, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'scripts'))
spec = importlib.util.spec_from_file_location('isolated_policy_resolver', root / 'scripts/secpal-resolve-fixed-threads.py')
resolver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = resolver
spec.loader.exec_module(resolver)
print(json.dumps(resolver._validation_registry_binding({self.entry!r})))
"""
        result = subprocess.run([sys.executable, "-I", "-c", code],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        resolver_binding = json.loads(result.stdout)
        binding = enrolled.fast_path.validation_registry_projection(self.entry)
        self.assertEqual(binding, draft.actions._fast_registry_binding(self.entry))
        self.assertEqual(binding, resolver_binding)
        self.assertEqual(enrolled._entry(draft.actions, self.repository), (self.entry, binding))
        self.assertIn("BRANCH_WRITE", self.entry["unsupported_operations"])
        with self.assertRaises(draft.actions.RegistryError):
            draft.actions.select_repository(self.registry, "Other/frontend")

    def dispatch(self, fixture, *, admitted):
        class Selected(Exception):
            pass
        arguments = SimpleNamespace(apply=True, repo=self.repository, repo_root=str(ROOT))
        for command in (enrolled.prepare, enrolled.integrate):
            with (
                self.subTest(command=command.__name__),
                mock.patch.object(enrolled, "_trusted_source", return_value="b" * 40),
                mock.patch.object(draft.actions, "load_registry", return_value=fixture),
                mock.patch.object(draft.actions, "_require_distinct_candidate_repository_root", side_effect=Selected) as selected,
                mock.patch.object(draft.actions, "_create_signed_pre_enrollment_commit") as candidate,
                mock.patch.object(draft.actions, "_read_pre_enrollment_json") as read,
                mock.patch.object(enrolled.publication, "verify_current_lifecycle_authority") as current,
                mock.patch.object(enrolled.publication, "claim_enrolled_draft_integration") as claim,
                mock.patch.object(enrolled, "_push_exact") as push,
                self.assertRaises(Selected if admitted else (draft.actions.RegistryError, enrolled.fast_path.SecurityBlocker)),
            ):
                command(draft.actions, arguments)
            self.assertEqual(selected.call_count, int(admitted))
            candidate.assert_not_called()
            read.assert_not_called()
            current.assert_not_called()
            claim.assert_not_called()
            push.assert_not_called()

    def test_executor_selects_target_before_mutation(self):
        self.dispatch(self.registry, admitted=True)

    def test_missing_target_policy_is_not_supplied_by_other_repositories(self):
        fixture = copy.deepcopy(self.registry)
        next(entry for entry in fixture["repositories"] if entry["repository"] == self.repository).pop("enrolled_draft_integration_policy", None)
        self.assertEqual(draft.actions.select_repository(fixture, "SecPal/.github")["enrolled_draft_integration_policy"], enrolled.POLICY)
        self.dispatch(fixture, admitted=False)

    def test_malformed_and_widened_policy_reject_in_schema_and_executor(self):
        mutations = (
            ("schema_version", "2.0"), ("command", "push"),
            ("topology_kind", "ARBITRARY_MERGE"), ("allowed_mutation", "BRANCH_WRITE"),
            ("maximum_candidates", 2), ("maximum_pushes", 2),
            ("force_push", True), ("automatic_retry", True),
            ("merge_pull_request", True), ("caller_policy", True),
        )
        for key, value in mutations:
            fixture = copy.deepcopy(self.registry)
            target = next(entry for entry in fixture["repositories"] if entry["repository"] == self.repository)
            target["enrolled_draft_integration_policy"] = {**enrolled.POLICY, key: value}
            with self.subTest(key=key), self.assertRaises(draft.actions.RegistryError):
                draft.actions.validate_registry(fixture)
            self.dispatch(fixture, admitted=False)


class ApiEnrolledDraftPolicyTests(FrontendEnrolledDraftPolicyTests):
    repository = "SecPal/api"


class ContractsEnrolledDraftPolicyTests(FrontendEnrolledDraftPolicyTests):
    repository = "SecPal/contracts"


class SecpalAppEnrolledDraftPolicyTests(FrontendEnrolledDraftPolicyTests):
    repository = "SecPal/secpal.app"


class AndroidEnrolledDraftPolicyTests(FrontendEnrolledDraftPolicyTests):
    repository = "SecPal/android"


class EnrolledDraftJournalTests(TestCase):
    def test_real_journal_claims_preserve_current_and_native_root(self):
        publication = enrolled.publication
        with tempfile.TemporaryDirectory() as temporary:
            remote = Path(temporary) / "journal.git"
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            policy = replace(native.policy_for(), publication_remote_url=str(remote),
                             genesis_admission_signer_identities=frozenset({native.SIGNER}))
            with signature_context(), mock.patch.object(enrolled.authority, "_load_lifecycle_trust_policy", return_value=policy), mock.patch.object(publication, "_verify_live_protection"):
                chain = native.Chain()
                publication.admit_native_genesis(chain.raw(), signer_identity=native.SIGNER, signer=native.signer_for())
                current = publication.enroll_existing_lifecycle(chain.raw(), signer_identity=native.SIGNER, signer=native.signer_for())
                evidence = {**fixture_evidence(), **enrolled.current_binding(current)}
                preparation, authorization = fixture_authorizations(evidence)
                publication.claim_enrolled_draft_integration(preparation, signer_identity=native.SIGNER, signer=native.signer_for())
                publication.claim_enrolled_draft_integration(authorization, signer_identity=native.SIGNER, signer=native.signer_for())
                publication.verify_enrolled_draft_integration_claim(authorization)
                selected = publication.verify_current_lifecycle_authority(native.REPOSITORY, native.ISSUE)
                self.assertEqual(selected.publication_oid, current.publication_oid)
                self.assertEqual(selected.lifecycle.state, current.lifecycle.state)
                with self.assertRaisesRegex(publication.LifecyclePublicationError, "already claimed"):
                    publication.claim_enrolled_draft_integration(authorization, signer_identity=native.SIGNER, signer=native.signer_for())
                with self.assertRaises(publication.LifecyclePublicationError):
                    publication.admit_native_genesis(chain.raw(), signer_identity=native.SIGNER, signer=native.signer_for())
                tip = subprocess.check_output(["git", "--git-dir", str(remote), "rev-parse", native.BRANCH], text=True).strip()
                projected, admissions = publication._walk_journal_identity_projection(remote, tip, native.BRANCH)
                self.assertIn((native.REPOSITORY, native.ISSUE), projected)
                self.assertEqual(len(admissions), 1)

    def test_preparation_reserves_one_candidate_and_push_claim_is_one_use(self):
        preparation, authorization = fixture_authorizations()
        claims = {}
        publication = enrolled.publication
        publication._add_enrolled_draft_claim(claims, {"authorization": preparation})
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "already claimed"):
            publication._add_enrolled_draft_claim(claims, {"authorization": preparation})
        changed = {**preparation, "authorization_id": "another-id", "authorization_digest": "9" * 64}
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "already claimed"):
            publication._add_enrolled_draft_claim(claims, {"authorization": changed})
        publication._add_enrolled_draft_claim(claims, {"authorization": authorization})
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "already claimed"):
            publication._add_enrolled_draft_claim(claims, {"authorization": authorization})

    def test_second_candidate_or_wrong_preparation_cannot_acquire_push_authority(self):
        preparation, authorization = fixture_authorizations()
        publication = enrolled.publication
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "no protected"):
            publication._add_enrolled_draft_claim({}, {"authorization": authorization})
        claims = {preparation["authorization_digest"]: {"authorization": preparation}}
        changed = copy.deepcopy(authorization)
        changed["evidence"]["head_ref"] = "substituted"
        with self.assertRaisesRegex(publication.LifecyclePublicationError, "differs from preparation"):
            publication._add_enrolled_draft_claim(claims, {"authorization": changed})
        publication._add_enrolled_draft_claim(claims, {"authorization": authorization})
        changed = copy.deepcopy(authorization)
        changed["authorization_id"] = "another-id"
        changed["final_attestation"]["candidate_head_sha"] = "9" * 40
        with self.assertRaises(publication.LifecyclePublicationError):
            publication._add_enrolled_draft_claim(claims, {"authorization": changed})

    def test_journal_envelope_verifies_roles_current_parent_and_authorization(self):
        preparation, _ = fixture_authorizations()
        current = native.Harness(native.Chain()).current
        lifecycle = current.lifecycle
        document = {
            "repository": lifecycle.repository, "delivery_issue": lifecycle.delivery_issue,
            "pull_request": lifecycle.pull_request, "lifecycle_id": lifecycle.lifecycle_id,
            "initialization_evidence_digest": lifecycle.initialization_evidence_digest,
            "publication_digest": current.publication_digest, "terminal_authority_digest": lifecycle.authority_digest,
            "head_sha": lifecycle.head_sha, "historical_proof_mode": lifecycle.historical_proof_mode,
            "journal_predecessor_oid": "0" * 40, "predecessor_publication_oid": None,
            "lifecycle_evidence": json.loads(current.serialized_lifecycle_evidence),
        }
        fields = {
            "schema_version": "1.0", "kind": enrolled.publication.ENROLLED_DRAFT_CLAIM_KIND,
            "domain": enrolled.publication.ENROLLED_DRAFT_CLAIM_DOMAIN,
            "authorization": preparation, "publication_branch": native.BRANCH,
            "journal_predecessor_oid": "3" * 40, "signer_identity": native.SIGNER,
        }
        def serialize(value):
            signed = {**value, "signature": native.signer_for()(enrolled.fast_path.canonical_json_bytes(value), enrolled.publication.ENROLLED_DRAFT_CLAIM_DOMAIN)}
            return enrolled.fast_path.canonical_json_bytes({**signed, "publication_digest": enrolled.fast_path.digest_json(signed)})
        with signature_context():
            verified = enrolled.publication._verify_enrolled_draft_claim_document(serialize(fields), expected_branch=native.BRANCH, parent="3" * 40, previous=(current.publication_oid, document, lifecycle))
            self.assertEqual(verified["authorization"], preparation)
            for key, value in (("publication_branch", "refs/heads/main"),
                               ("journal_predecessor_oid", "9" * 40),
                               ("signer_identity", "substitute@secpal.app")):
                with self.subTest(key=key), self.assertRaises((ValueError, enrolled.fast_path.SecurityBlocker)):
                    enrolled.publication._verify_enrolled_draft_claim_document(serialize({**fields, key: value}), expected_branch=native.BRANCH, parent="3" * 40, previous=(current.publication_oid, document, lifecycle))


class EnrolledDraftPushTests(TestCase):
    def test_substituted_pushurl_stops_before_dispatch(self):
        fake = SimpleNamespace(_run_attestation_git=mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="https://github.com/Other/repository.git\n")), _push_pre_enrollment_commit=mock.Mock())
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "destination"):
            enrolled._push_exact(fake, ROOT, fixture_evidence(), "6" * 40)
        fake._push_pre_enrollment_commit.assert_not_called()

    def test_exact_push_hook_rejects_branch_head_and_multiple_refs(self):
        evidence = fixture_evidence()
        head = "6" * 40
        fake = SimpleNamespace(_run_attestation_git=mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="https://github.com/SecPal/.github.git\n")))
        fake.evidence = draft.actions.evidence
        old_run = fake._run_attestation_git
        fake._run_attestation_git = lambda root, argv, **kwargs: SimpleNamespace(returncode=0, stdout=b"PACK") if argv[0] == "pack-objects" else old_run(root, argv, **kwargs)
        def push(root, argv, **kwargs):
            if argv[0] == "init":
                return SimpleNamespace(returncode=0, stdout=b"")
            if argv[0] == "index-pack":
                return SimpleNamespace(returncode=0, stdout=b"")
            if argv[0] == "cat-file":
                return SimpleNamespace(returncode=0, stdout=(f"tree {evidence['validated_tree_sha']}\nparent {evidence['draft_head_sha']}\nparent {evidence['current_main']['sha']}\n\nfixture\n").encode())
            self.assertNotEqual(root, ROOT)
            self.assertNotIn("origin", argv)
            self.assertNotIn("--force", argv)
            self.assertNotIn("--force-with-lease", argv)
            hook = Path(argv[1].split("=", 1)[1]) / "pre-push"
            expected = f"{head} {head} refs/heads/delivery {evidence['draft_head_sha']}\n"
            self.assertEqual(subprocess.run([str(hook)], input=expected, text=True).returncode, 0)
            for row in (expected.replace("delivery", "substituted"),
                        expected.replace(evidence["draft_head_sha"], "9" * 40),
                        expected + expected, expected.replace(head, "9" * 40)):
                self.assertNotEqual(subprocess.run([str(hook)], input=row, text=True).returncode, 0)
            return SimpleNamespace(returncode=0)
        with signature_context(), mock.patch.object(enrolled.publication, "_github_token", return_value="fixture-nonsecret"), mock.patch.object(enrolled.publication, "_run_git", side_effect=push):
            enrolled._push_exact(fake, ROOT, evidence, head)


class EnrolledDraftPreparationTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.current = native.Harness(native.Chain()).current
        self.evidence = fixture_evidence()
        self.events = []
        self.claims = {}
        gates = Path(self.temporary.name) / "gates.json"
        gates.write_text("[]")
        self.arguments = SimpleNamespace(apply=True, repo=native.REPOSITORY, pr=native.PR,
            delivery_issue=native.ISSUE, repo_root=str(ROOT), authorization_id="prepare-001",
            manual_gate_evidence=str(gates), operation_directory=str(Path(self.temporary.name) / "operation"))
        self.actions = SimpleNamespace(
            evidence=draft.actions.evidence,
            _read_pre_enrollment_json=draft.actions._read_pre_enrollment_json,
            _require_distinct_candidate_repository_root=mock.Mock(),
            _authenticate_protected_bridge_main=mock.Mock(return_value="b" * 40),
            _attestation_local_state=mock.Mock(return_value=("a" * 40, "")),
            _staged_tree=mock.Mock(return_value="c" * 40),
            _run_attestation_git=mock.Mock(return_value=SimpleNamespace(returncode=1)),
            _run_registered_validations=mock.Mock(side_effect=lambda *_: self.events.append("validate") or True),
            _create_signed_pre_enrollment_commit=mock.Mock(side_effect=lambda *_: self.events.append("candidate") or SimpleNamespace(returncode=0, stdout="6" * 40)),
            _write_fast_report=lambda path, value: Path(path).write_text(json.dumps(value)),
        )
        stack = signature_context()
        self.addCleanup(stack.close)
        for owner, name, kwargs in (
            (enrolled, "_trusted_source", {"return_value": "9" * 40}),
            (enrolled, "_entry", {"return_value": ({}, {"validation": [], "manual_gates": [], "default_branch": "main"})}),
            (enrolled, "_graph", {"return_value": "d" * 64}),
            (enrolled, "_live", {"return_value": "delivery"}),
            (enrolled, "_commit", {"return_value": SimpleNamespace(signature_fingerprint="SHA256:AAAA")}),
            (enrolled.fast_path, "derive_ready_integration_tree_evidence", {"return_value": self.evidence["tree_evidence"]}),
            (enrolled.execution, "_production_signing_authorities", {"side_effect": native.fixture_signing_authorities}),
            (enrolled.publication, "verify_current_lifecycle_authority", {"return_value": self.current}),
            (enrolled.publication, "claim_enrolled_draft_integration", {"side_effect": self.claim}),
        ):
            stack.enter_context(mock.patch.object(owner, name, **kwargs))

    def claim(self, authorization, **kwargs):
        self.events.append("reserve")
        enrolled.publication._add_enrolled_draft_claim(self.claims, {"authorization": authorization})

    def test_validation_and_protected_reservation_precede_exact_single_candidate(self):
        self.assertEqual(enrolled.prepare(self.actions, self.arguments), 0)
        self.assertEqual(self.events, ["validate", "reserve", "candidate"])
        candidate = self.actions._create_signed_pre_enrollment_commit.call_args.args
        self.assertEqual(candidate[1], ["commit-tree", "-S", "c" * 40, "-p", "a" * 40, "-p", "b" * 40])
        authorization = json.loads((Path(self.arguments.operation_directory) / "authorization.json").read_text())
        self.assertEqual(enrolled.normalize_authorization(authorization), authorization)

    def test_other_directory_or_authorization_cannot_create_second_candidate(self):
        enrolled.prepare(self.actions, self.arguments)
        self.arguments.operation_directory = str(Path(self.temporary.name) / "another-operation")
        self.arguments.authorization_id = "prepare-002"
        with self.assertRaisesRegex(enrolled.publication.LifecyclePublicationError, "already claimed"):
            enrolled.prepare(self.actions, self.arguments)
        self.actions._create_signed_pre_enrollment_commit.assert_called_once()

    def test_validation_failure_never_reserves_or_creates(self):
        self.actions._run_registered_validations.side_effect = None
        self.actions._run_registered_validations.return_value = False
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "Complete Validation"):
            enrolled.prepare(self.actions, self.arguments)
        self.assertFalse(self.claims)
        self.actions._create_signed_pre_enrollment_commit.assert_not_called()

    def test_candidate_creation_failure_is_controlled_after_one_reservation(self):
        for failure in (OSError("unavailable"), subprocess.TimeoutExpired("git", 1),
                        draft.actions.evidence.CommandPolicyError("unavailable")):
            with self.subTest(failure=type(failure).__name__):
                self.claims.clear()
                self.arguments.operation_directory = str(Path(self.temporary.name) / type(failure).__name__)
                self.actions._create_signed_pre_enrollment_commit.reset_mock()
                self.actions._create_signed_pre_enrollment_commit.side_effect = failure
                with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "no retry"):
                    enrolled.prepare(self.actions, self.arguments)
                self.assertTrue(self.claims)
                self.actions._create_signed_pre_enrollment_commit.assert_called_once()

    def test_missing_manual_gates_is_a_recoverable_input_failure(self):
        self.arguments.manual_gate_evidence = str(Path(self.temporary.name) / "missing.json")
        with self.assertRaises((enrolled.fast_path.RecoverableLocalError, draft.actions.fast_path.RecoverableLocalError)):
            enrolled.prepare(self.actions, self.arguments)
        self.assertFalse(self.claims)

    def test_main_ancestry_already_present_never_creates_candidate(self):
        self.actions._run_attestation_git.return_value.returncode = 0
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "unnecessary"):
            enrolled.prepare(self.actions, self.arguments)
        self.actions._run_registered_validations.assert_not_called()
        self.actions._create_signed_pre_enrollment_commit.assert_not_called()


class EnrolledDraftRealGitTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                            "GIT_CONFIG_NOSYSTEM": "1"}
        self.git("init", "-q")
        self.git("config", "user.name", "Integration fixture")
        self.git("config", "user.email", native.SIGNER)
        self.git("remote", "add", "origin", "https://github.com/SecPal/.github.git")
        key = self.root / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True, capture_output=True)
        self.public_key = key.with_suffix(".pub").read_text().strip()
        allowed = self.root / "allowed-signers"
        allowed.write_text(native.SIGNER + " " + self.public_key + "\n")
        self.git("config", "gpg.format", "ssh")
        self.git("config", "user.signingkey", str(key))
        self.git("config", "gpg.ssh.allowedSignersFile", str(allowed))
        self.git("config", "commit.gpgsign", "true")
        (self.root / "source.txt").write_text("accepted base\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")
        (self.root / "delivery.txt").write_text("delivery source\n")
        self.git("add", "delivery.txt")
        self.git("commit", "-qm", "delivery")
        self.parent1 = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "--detach", self.base)
        (self.root / "source.txt").write_text("accepted current main\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "main")
        self.parent2 = self.git("rev-parse", "HEAD")
        self.tree = self.git("merge-tree", "--write-tree", self.parent1, self.parent2)

    def git(self, *arguments, input=None):
        return subprocess.check_output(["git", *arguments], cwd=self.root, env=self.environment, input=None if input is None else input.encode()).decode().strip()

    def package(self, *, tree=None):
        tree = self.tree if tree is None else tree
        evidence = fixture_evidence()
        evidence.update(draft_head_sha=self.parent1, current_main={"ref": "main", "sha": self.parent2},
            ordered_parent_shas=[self.parent1, self.parent2], validated_tree_sha=tree,
            tree_evidence=enrolled.fast_path.derive_ready_integration_tree_evidence(self.root, [self.parent1, self.parent2], tree, schema_version="1.0", kind=enrolled.KIND))
        receipt = enrolled.fast_path.create_enrolled_draft_validation_receipt(evidence)
        message = "Integrate fixture\n\n" + "".join(f"{name}: {value}\n" for name, value in zip(enrolled.TRAILERS, (enrolled.fast_path.digest_json(evidence), receipt["receipt_digest"])))
        head = self.git("commit-tree", "-S", tree, "-p", self.parent1, "-p", self.parent2, input=message)
        preparation, authorization = fixture_authorizations(evidence)
        authorization["final_attestation"] = enrolled.fast_path.create_enrolled_draft_final_attestation(evidence, receipt, candidate_head_sha=head, signature_fingerprint=enrolled.execution._ssh_public_key_fingerprint(self.public_key))
        authorization = sign_fields({key: value for key, value in authorization.items() if key not in {"signature", "authorization_digest"}}, enrolled.AUTHORIZATION_DOMAIN)
        return authorization

    def policy_context(self):
        stack = signature_context()
        policy = native.policy_for()
        policy = replace(policy, signers={native.SIGNER: enrolled.authority.TrustedSigner(native.SIGNER, (self.public_key,), ())})
        stack.enter_context(mock.patch.object(enrolled.authority, "_load_lifecycle_trust_policy", return_value=policy))
        return stack

    def test_real_signed_candidate_validation_provenance_is_reverified(self):
        with self.policy_context():
            authorization = self.package()
            verified = enrolled.fast_path.verify_enrolled_draft_validation_evidence(authorization, repository_root=self.root)
            self.assertTrue(enrolled.fast_path.is_verified_validation_evidence(verified))
            self.assertEqual(verified.tree_sha, self.tree)
            self.assertFalse(enrolled.fast_path.is_verified_validation_evidence(replace(verified, tree_sha="9" * 40)))

    def test_candidate_local_merge_driver_cannot_change_tree_authority(self):
        self.git("checkout", "-q", "--detach", self.parent1)
        (self.root / "source.txt").write_text("delivery conflict\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "delivery conflict")
        parent1 = self.git("rev-parse", "HEAD")
        mechanical = subprocess.run(["git", "merge-tree", "--write-tree", parent1, self.parent2], cwd=self.root, env=self.environment, capture_output=True, text=True).stdout.splitlines()[0]
        self.git("read-tree", mechanical)
        blob = self.git("rev-parse", self.parent2 + ":source.txt")
        self.git("update-index", "--cacheinfo", "100644", blob, "source.txt")
        resolved = self.git("write-tree")
        expected = enrolled.fast_path.derive_ready_integration_tree_evidence(self.root, [parent1, self.parent2], resolved, schema_version="1.0", kind=enrolled.KIND)
        attributes = self.root / "local-attributes"
        attributes.write_text("source.txt merge=evil\n")
        marker = self.root / "driver-ran"
        self.git("config", "core.attributesFile", str(attributes))
        self.git("config", "merge.evil.driver", f'printf injected > %A; touch "{marker}"')
        observed = enrolled.fast_path.derive_ready_integration_tree_evidence(self.root, [parent1, self.parent2], resolved, schema_version="1.0", kind=enrolled.KIND)
        self.assertFalse(marker.exists(), "candidate-local external merge driver ran")
        self.assertEqual(observed, expected)

    def test_preparation_ignores_candidate_local_signing_program(self):
        marker = self.root / "signing-program-ran"
        evil = self.root / "evil-signer"
        trusted = enrolled.execution.late_disposition._trusted_executable("ssh-keygen")
        evil.write_text(f'#!/bin/sh\ntouch "{marker}"\nexec "{trusted}" "$@"\n')
        evil.chmod(0o700)
        self.git("config", "gpg.ssh.program", str(evil))
        current = native.Harness(native.Chain()).current
        current = replace(current, lifecycle=replace(current.lifecycle, head_sha=self.parent1))
        gates = self.root / "gates.json"
        gates.write_text("[]")
        arguments = SimpleNamespace(apply=True, repo=native.REPOSITORY, pr=native.PR,
            delivery_issue=native.ISSUE, repo_root=str(self.root), authorization_id="real-preparation",
            manual_gate_evidence=str(gates), operation_directory=str(self.root / "operation"))
        actions = SimpleNamespace(evidence=draft.actions.evidence,
            _require_distinct_candidate_repository_root=mock.Mock(),
            _read_pre_enrollment_json=draft.actions._read_pre_enrollment_json,
            _run_attestation_git=draft.actions._run_attestation_git,
            _attestation_local_state=mock.Mock(return_value=(self.parent1, "")),
            _staged_tree=mock.Mock(return_value=self.tree),
            _run_registered_validations=mock.Mock(return_value=True),
            _authenticate_protected_bridge_main=mock.Mock(return_value=self.parent2),
            _create_signed_pre_enrollment_commit=draft.actions._create_signed_pre_enrollment_commit,
            _write_fast_report=lambda path, value: Path(path).write_text(json.dumps(value)))
        with self.policy_context(), ExitStack() as stack:
            for owner, name, kwargs in (
                (enrolled, "_trusted_source", {"return_value": "9" * 40}),
                (enrolled, "_entry", {"return_value": ({}, {"validation": [], "manual_gates": [], "default_branch": "main"})}),
                (enrolled, "_graph", {"return_value": "d" * 64}),
                (enrolled, "_live", {"return_value": "delivery"}),
                (enrolled.execution, "_production_signing_authorities", {"side_effect": native.fixture_signing_authorities}),
                (enrolled.execution.late_disposition, "read_role_signing_configuration", {"return_value": ("ssh", str(self.root / "key"))}),
                (enrolled.publication, "verify_current_lifecycle_authority", {"return_value": current}),
                (enrolled.publication, "claim_enrolled_draft_integration", {}),
            ):
                stack.enter_context(mock.patch.object(owner, name, **kwargs))
            enrolled.prepare(actions, arguments)
        self.assertFalse(marker.exists(), "candidate-local signing executable ran")
        authorization = json.loads((self.root / "operation/authorization.json").read_bytes())
        with self.policy_context():
            self.assertEqual(enrolled._commit(actions, self.root, authorization["evidence"], authorization["final_attestation"]["candidate_head_sha"]).signature_fingerprint,
                             enrolled.execution._ssh_public_key_fingerprint(self.public_key))

    def test_unrelated_manual_delta_and_hidden_candidate_source_are_rejected(self):
        self.git("read-tree", self.tree)
        (self.root / "hidden_candidate_only.py").write_text("unexpected = True\n")
        self.git("add", "hidden_candidate_only.py")
        tree = self.git("write-tree")
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "preservation"):
            enrolled.fast_path.derive_ready_integration_tree_evidence(self.root, [self.parent1, self.parent2], tree, schema_version="1.0", kind=enrolled.KIND)

    def test_two_stage_url_rewrite_cannot_redirect_isolated_push(self):
        with self.policy_context():
            authorization = self.package()
            evidence = authorization["evidence"]
            head = authorization["final_attestation"]["candidate_head_sha"]
            destination = self.root / "authorized.git"
            evil = self.root / "evil.git"
            for target in (destination, evil):
                subprocess.run(["git", "init", "-q", "--bare", str(target)], check=True, capture_output=True, env=self.environment)
                self.git("push", "-q", str(target), self.parent1 + ":refs/heads/delivery")
            canonical = "https://github.com/SecPal/.github.git"
            self.git("remote", "set-url", "origin", "seed/repo")
            self.git("config", "url." + canonical + ".insteadOf", "seed/repo")
            self.git("config", "url." + canonical + ".pushInsteadOf", "seed/repo")
            self.git("config", "url." + str(evil) + ".pushInsteadOf", canonical)
            self.assertEqual(self.git("remote", "get-url", "origin"), canonical)
            self.assertEqual(self.git("remote", "get-url", "--push", "origin"), canonical)
            original = enrolled.publication._run_git
            pushes = []
            def isolated_run(root, argv, **kwargs):
                if "push" in argv:
                    self.assertNotEqual(root, self.root)
                    self.assertEqual(argv[-2], canonical)
                    self.assertEqual(original(root, ["config", "--get-regexp", "^url\\."]).returncode, 1)
                    pushes.append(argv)
                    argv = [*argv[:-2], str(destination), argv[-1]]
                return original(root, argv, **kwargs)
            with mock.patch.object(enrolled.publication, "_github_token", return_value="fixture-nonsecret"), mock.patch.object(enrolled.publication, "_run_git", side_effect=isolated_run):
                enrolled._push_exact(draft.actions, self.root, evidence, head)
            self.assertEqual(len(pushes), 1)
            self.assertEqual(subprocess.check_output(["git", "--git-dir", str(destination), "rev-parse", "refs/heads/delivery"], env=self.environment).decode().strip(), head)
            self.assertEqual(subprocess.check_output(["git", "--git-dir", str(evil), "rev-parse", "refs/heads/delivery"], env=self.environment).decode().strip(), self.parent1)

    def test_conflicts_bind_every_path_and_reject_retained_markers(self):
        self.git("checkout", "-q", "--detach", self.parent1)
        (self.root / "source.txt").write_text("delivery conflict\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "delivery conflict")
        parent1 = self.git("rev-parse", "HEAD")
        result = subprocess.run(["git", "merge-tree", "--write-tree", parent1, self.parent2], cwd=self.root, env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        mechanical = result.stdout.splitlines()[0]
        with self.assertRaises(enrolled.fast_path.SecurityBlocker):
            enrolled.fast_path.derive_ready_integration_tree_evidence(self.root, [parent1, self.parent2], mechanical, schema_version="1.0", kind=enrolled.KIND)
        # parent2 lacks the unrelated delivery file, so restore that exact
        # mechanical state. Only source.txt may be resolved.
        self.git("read-tree", mechanical)
        blob = self.git("rev-parse", self.parent2 + ":source.txt")
        self.git("update-index", "--cacheinfo", "100644", blob, "source.txt")
        resolved = self.git("write-tree")
        evidence = enrolled.fast_path.derive_ready_integration_tree_evidence(self.root, [parent1, self.parent2], resolved, schema_version="1.0", kind=enrolled.KIND)
        self.assertEqual(evidence["mechanical_conflict_paths"], ["source.txt"])
        self.assertEqual(evidence["path_classifications"], [{"path": "source.txt", "classification": "CONFLICT_RESOLUTION"}])


class EnrolledDraftExecutionTests(TestCase):
    def setUp(self):
        self.harness = native.Harness(native.Chain())
        self.evidence = fixture_evidence()
        self.preparation, self.authorization = fixture_authorizations(self.evidence)
        self.head = self.authorization["final_attestation"]["candidate_head_sha"]
        self.branch = self.evidence["draft_head_sha"]
        self.claimed = False
        self.calls = []
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        auth_path = Path(self.temporary.name) / "authorization.json"
        auth_path.write_text(json.dumps(self.authorization))
        self.arguments = SimpleNamespace(apply=True, reconcile=False, repo=native.REPOSITORY,
                                         delivery_issue=native.ISSUE, pr=native.PR,
                                         repo_root=str(ROOT), authorization=str(auth_path))
        self.actions = SimpleNamespace(_require_distinct_candidate_repository_root=mock.Mock(),
                                       _read_pre_enrollment_json=draft.actions._read_pre_enrollment_json,
                                       _authenticate_protected_bridge_main=mock.Mock(return_value="b" * 40))
        stack = signature_context()
        self.addCleanup(stack.close)
        for owner, name, kwargs in (
            (enrolled, "_trusted_source", {"return_value": "9" * 40}),
            (enrolled, "_entry", {"return_value": ({}, {"validation": []})}),
            (enrolled, "_verify_candidate_package", {"return_value": self.head}),
            (enrolled, "_graph", {"return_value": self.evidence["work_graph_digest"]}),
            (enrolled, "_live", {"side_effect": self.live}),
            (enrolled, "_push_exact", {"side_effect": self.push}),
            (enrolled.execution, "_production_signing_authorities", {"side_effect": native.fixture_signing_authorities}),
            (enrolled.execution, "_verify_live_github_commit_signature", {}),
            (enrolled.publication, "verify_current_lifecycle_authority", {"side_effect": lambda *args: self.harness.current}),
            (enrolled.publication, "claim_enrolled_draft_integration", {"side_effect": self.claim}),
            (enrolled.publication, "verify_enrolled_draft_integration_claim", {"side_effect": self.read_claim}),
            (enrolled.publication, "advance_current_terminal", {"side_effect": self.harness.publisher}),
            (enrolled.publication, "_verify_historical_lifecycle_transition", {"side_effect": lambda *args, **kwargs: self.harness.transition}),
            (enrolled.fast_path, "verify_enrolled_draft_validation_evidence", {"return_value": self.validation()}),
            (enrolled.fast_path, "is_verified_validation_evidence", {"return_value": True}),
            (enrolled.authority, "is_verified_validation_evidence", {"return_value": True}),
        ):
            stack.enter_context(mock.patch.object(owner, name, **kwargs))

    def validation(self):
        return enrolled.fast_path._unregistered_validation_evidence(repository=native.REPOSITORY,
            delivery_issue_number=native.ISSUE, pull_request_number=native.PR,
            head_sha=self.head, tree_sha=self.evidence["validated_tree_sha"],
            validation_receipt_digest=self.authorization["validation_receipt"]["receipt_digest"],
            final_attestation_digest=self.authorization["final_attestation"]["attestation_digest"],
            source_validation_evidence_digest=enrolled.fast_path.digest_json(self.evidence))

    def live(self, _actions, _repository, _issue, _pr, expected, _main, _ref=None):
        if self.branch != expected:
            raise enrolled.fast_path.SecurityBlocker("PR-head drift")

    def claim(self, *_args, **_kwargs):
        self.calls.append("claim")
        if self.claimed:
            raise enrolled.publication.LifecyclePublicationError("already claimed")
        self.claimed = True

    def read_claim(self, *_args):
        if not self.claimed:
            raise enrolled.publication.LifecyclePublicationError("missing claim")

    def push(self, *_args):
        self.calls.append("push")
        self.branch = self.head

    def test_success_only_head_advanced_and_draft_counters_are_preserved(self):
        before = self.harness.current
        self.assertEqual(enrolled.integrate(self.actions, self.arguments), 0)
        self.assertEqual(self.calls, ["claim", "push"])
        after = self.harness.current
        self.assertEqual(after.lifecycle.state, before.lifecycle.state)
        self.assertEqual(after.lifecycle.lifecycle_id, before.lifecycle.lifecycle_id)
        self.assertEqual(after.lifecycle.pull_request, before.lifecycle.pull_request)
        self.assertEqual(after.lifecycle.head_sha, self.head)
        self.assertEqual(self.harness.transition.transition_kind, "HEAD_ADVANCED")
        self.assertEqual(len(self.harness.publication_writes), 1)

    def test_missing_authorization_is_a_recoverable_input_failure(self):
        self.arguments.authorization = str(Path(self.temporary.name) / "missing.json")
        with self.assertRaises((enrolled.fast_path.RecoverableLocalError, draft.actions.fast_path.RecoverableLocalError)):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls, [])

    def test_graph_drift_during_claim_consumes_claim_without_push(self):
        enrolled._graph.side_effect = [self.evidence["work_graph_digest"], "e" * 64]
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "work graph"):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls, ["claim"])
        self.assertFalse(self.harness.publication_writes)

    def test_head_drift_during_successor_prevents_publication(self):
        original = enrolled._successor
        def drift(*args):
            result = original(*args)
            self.branch = "9" * 40
            return result
        with mock.patch.object(enrolled, "_successor", side_effect=drift):
            with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "PR-head drift"):
                enrolled.integrate(self.actions, self.arguments)
        self.assertFalse(self.harness.publication_writes)
        self.assertEqual(self.calls, ["claim", "push"])

    def test_head_drift_during_publication_cannot_report_success(self):
        original = self.harness.publisher
        def drift(*args, **kwargs):
            result = original(*args, **kwargs)
            self.branch = "9" * 40
            return result
        enrolled.publication.advance_current_terminal.side_effect = drift
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "PR-head drift"):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(len(self.harness.publication_writes), 1)

    def test_completed_reconciliation_rechecks_live_head_after_journal_verification(self):
        enrolled.integrate(self.actions, self.arguments)
        self.arguments.reconcile = True
        original = enrolled._require_exact_published
        def drift(*args):
            original(*args)
            self.branch = "9" * 40
        with mock.patch.object(enrolled, "_require_exact_published", side_effect=drift):
            with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "PR-head drift"):
                enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls, ["claim", "push"])

    def test_push_then_missing_publication_reconciles_without_second_push(self):
        self.harness.publication_mode = "AMBIGUOUS_PREDECESSOR"
        with self.assertRaises(enrolled.publication.LifecyclePublicationAmbiguousWrite):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(self.branch, self.head)
        self.assertEqual(self.harness.current.lifecycle.head_sha, self.evidence["draft_head_sha"])
        self.arguments.reconcile = True
        self.harness.publication_mode = "SUCCESS"
        self.assertEqual(enrolled.integrate(self.actions, self.arguments), 0)
        self.assertEqual(self.calls.count("push"), 1)
        self.assertEqual(self.calls.count("claim"), 1)
        self.assertEqual(self.harness.current.lifecycle.head_sha, self.head)

    def test_uncertain_successful_publication_reconciles_read_only(self):
        self.harness.publication_mode = "AMBIGUOUS_TARGET"
        with self.assertRaises(enrolled.publication.LifecyclePublicationAmbiguousWrite):
            enrolled.integrate(self.actions, self.arguments)
        count = len(self.harness.publication_writes)
        self.arguments.reconcile = True
        self.assertEqual(enrolled.integrate(self.actions, self.arguments), 0)
        self.assertEqual(len(self.harness.publication_writes), count)
        self.assertEqual(self.calls.count("push"), 1)

    def test_exact_reconciliation_survives_later_validation_policy_change(self):
        self.harness.publication_mode = "AMBIGUOUS_PREDECESSOR"
        with self.assertRaises(enrolled.publication.LifecyclePublicationAmbiguousWrite):
            enrolled.integrate(self.actions, self.arguments)
        enrolled._entry.return_value = ({}, {"validation": [{"command": "new-check"}]})
        self.arguments.reconcile = True
        self.harness.publication_mode = "SUCCESS"
        self.assertEqual(enrolled.integrate(self.actions, self.arguments), 0)
        self.assertEqual(self.calls, ["claim", "push"])
        self.assertEqual(self.harness.current.lifecycle.head_sha, self.head)

    def test_changed_validation_policy_blocks_initial_push(self):
        enrolled._entry.return_value = ({}, {"validation": [{"command": "new-check"}]})
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "validation policy changed"):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls, [])

    def test_claim_before_push_crash_cannot_retry_or_reconcile_an_unpushed_head(self):
        enrolled._push_exact.side_effect = RuntimeError("crash before dispatch")
        with self.assertRaises(RuntimeError):
            enrolled.integrate(self.actions, self.arguments)
        with self.assertRaises(enrolled.publication.LifecyclePublicationError):
            enrolled.integrate(self.actions, self.arguments)
        self.arguments.reconcile = True
        with self.assertRaises(enrolled.fast_path.SecurityBlocker):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(enrolled._push_exact.call_count, 1)
        self.assertFalse(self.harness.publication_writes)

    def test_head_drift_stale_main_and_wrong_selection_stop_before_claim(self):
        for mutation in ("head", "main", "pr", "issue", "repository"):
            with self.subTest(mutation=mutation):
                arguments = copy.copy(self.arguments)
                if mutation == "head":
                    self.branch = "9" * 40
                elif mutation == "main":
                    self.actions._authenticate_protected_bridge_main.return_value = "9" * 40
                elif mutation == "pr":
                    arguments.pr += 1
                elif mutation == "issue":
                    arguments.delivery_issue += 1
                else:
                    arguments.repo = "Other/repository"
                with self.assertRaises((ValueError, enrolled.fast_path.SecurityBlocker)):
                    enrolled.integrate(self.actions, arguments)
                self.branch = self.evidence["draft_head_sha"]
                self.actions._authenticate_protected_bridge_main.return_value = "b" * 40
        self.assertEqual(self.calls, [])

    def test_publication_of_different_head_is_rejected(self):
        def wrong(raw, **kwargs):
            result = self.harness.publisher(raw, **kwargs)
            self.harness.current = replace(result, lifecycle=replace(result.lifecycle, head_sha="9" * 40))
            return result
        enrolled.publication.advance_current_terminal.side_effect = wrong
        with self.assertRaisesRegex(enrolled.fast_path.SecurityBlocker, "another integration"):
            enrolled.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls.count("push"), 1)


if __name__ == "__main__":
    main()
