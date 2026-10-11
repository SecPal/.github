# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ordinary enrolled initial-Draft source authority regressions."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import json
import tempfile
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_enrolled_fixtures", ROOT / "tests/secpal-enrolled-draft-integration-unit.py")
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)
owner = fixtures.enrolled


def evidence():
    item = fixtures.fixture_evidence()
    item.pop("current_main")
    item.pop("tree_evidence")
    item.update(kind="ENROLLED_DRAFT_SOURCE_ADVANCEMENT",
                ordered_parent_shas=[item["draft_head_sha"]],
                user_authorization={"issued_at": 1000, "expires_at": 1600})
    return item


class SourceAdmissionTests(TestCase):
    def test_source_accepts_one_parent_and_no_current_main(self):
        item = evidence()
        self.assertEqual(owner.normalize_evidence(item), item)

    def test_source_never_admits_integration_or_unbounded_authority(self):
        for update in ({"ordered_parent_shas": ["1" * 40, "2" * 40]},
                       {"ordered_parent_shas": []},
                       {"ordered_parent_shas": ["9" * 40]},
                       {"current_main": {"ref": "main", "sha": "2" * 40}},
                       {"head_ref": "main"},
                       {"head_ref": "refs/heads/main"},
                       {"user_authorization": {"issued_at": 1000, "expires_at": 1000}},
                       {"user_authorization": {"issued_at": 1000, "expires_at": 100000}},
                       {"allowed_mutation": "BRANCH_WRITE"}):
            with self.subTest(update=update), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                owner.normalize_evidence({**evidence(), **copy.deepcopy(update)})

    def test_registry_selects_only_central_and_deployment_source_capability(self):
        registry = fixtures.draft.actions.load_registry()
        admitted = {entry["repository"] for entry in registry["repositories"] if "enrolled_draft_source_advancement_policy" in entry}
        self.assertEqual(admitted, {"SecPal/.github", "SecPal/deployment"})
        for repository in admitted:
            entry, binding = owner._entry(fixtures.draft.actions, repository, owner.SOURCE_KIND)
            self.assertEqual(binding["enrolled_draft_source_advancement_policy"], owner.SOURCE_POLICY)
            self.assertIn("BRANCH_WRITE", entry["unsupported_operations"])
        for repository in ("SecPal/frontend", "Other/deployment"):
            with self.subTest(repository=repository), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                owner._entry(fixtures.draft.actions, repository, owner.SOURCE_KIND)


def authorizations(item=None, *, candidate="6" * 40, authorization_id="source-001", fingerprint="SHA256:AAAA"):
    item = evidence() if item is None else item
    receipt = owner.fast_path.create_enrolled_draft_validation_receipt(item)
    common = {"schema_version": "1.0", "authorization_id": authorization_id,
              "evidence": item, "validation_receipt": receipt,
              "signer_identity": fixtures.native.SIGNER}
    preparation = fixtures.sign_fields({**common, "kind": owner.authorization_kind(owner.SOURCE_KIND, preparation=True)}, owner.authorization_domain(owner.SOURCE_KIND, preparation=True))
    final = owner.fast_path.create_enrolled_draft_final_attestation(item, receipt, candidate_head_sha=candidate, signature_fingerprint=fingerprint)
    authorized = fixtures.sign_fields({**common, "kind": owner.authorization_kind(owner.SOURCE_KIND),
        "final_attestation": final, "preparation_authorization_digest": preparation["authorization_digest"]}, owner.authorization_domain(owner.SOURCE_KIND))
    return preparation, authorized


class SourceAuthorizationTests(TestCase):
    def test_source_registry_rejects_widening_and_missing_policy(self):
        registry = fixtures.draft.actions.load_registry()
        for key, value in (("force_push", True), ("maximum_candidates", 2),
                           ("maximum_pushes", 2), ("automatic_retry", True),
                           ("merge_pull_request", True), ("allowed_mutation", "BRANCH_WRITE"),
                           ("maximum_authorization_age_seconds", 901)):
            modified = copy.deepcopy(registry)
            modified["repositories"][0]["enrolled_draft_source_advancement_policy"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                fixtures.draft.actions.validate_registry(modified)
        modified = copy.deepcopy(registry)
        modified["repositories"][0].pop("enrolled_draft_source_advancement_policy")
        with mock.patch.object(fixtures.draft.actions, "load_registry", return_value=modified), self.assertRaises(owner.fast_path.SecurityBlocker):
            owner._entry(fixtures.draft.actions, "SecPal/.github", owner.SOURCE_KIND)

    def test_isolated_source_cli_selects_owner_and_requires_apply(self):
        import subprocess
        result = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/secpal-pr-review-actions.py"),
            "advance-enrolled-draft-source", "--repo", "SecPal/.github", "--delivery-issue", "123",
            "--pr", "124", "--authorization", "not-read.json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        report = json.loads(result.stderr)
        self.assertEqual(report["status"], "BLOCKED_SECURITY")
        self.assertIn("requires --apply", report["blocker"])
    def test_signed_package_and_receipt_bind_every_source_boundary(self):
        _, original = authorizations()
        with fixtures.signature_context():
            self.assertEqual(owner.normalize_authorization(original), original)
            for path, value in (
                (("evidence", "repository"), "Other/repository"),
                (("evidence", "delivery_issue"), 100),
                (("evidence", "pull_request"), 200),
                (("evidence", "draft_head_sha"), "9" * 40),
                (("evidence", "validated_tree_sha"), "9" * 40),
                (("evidence", "registry_digest"), "9" * 64),
                (("evidence", "command_set_digest"), "9" * 64),
                (("validation_receipt", "successful_result"), False),
                (("final_attestation", "candidate_tree_sha"), "9" * 40),
                (("signer_identity",), "Other/signer"),
                (("evidence", "user_authorization", "expires_at"), 1601),
            ):
                item = copy.deepcopy(original)
                parent = item
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                resigned = fixtures.sign_fields({key: val for key, val in item.items() if key not in {"signature", "authorization_digest"}}, owner.authorization_domain(owner.SOURCE_KIND))
                with self.subTest(path=path), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                    owner.normalize_authorization(resigned)
            item = copy.deepcopy(original)
            item["signature"]["value"] = "0" * 64
            item["authorization_digest"] = owner.fast_path.digest_json({key: value for key, value in item.items() if key != "authorization_digest"})
            with self.assertRaises(ValueError):
                owner.normalize_authorization(item)

    def test_temporal_admission_and_reconciliation_are_distinct(self):
        for now, accepted in ((999, False), (1000, True), (1599, True), (1600, False)):
            with self.subTest(now=now), mock.patch.object(owner.time, "time", return_value=now):
                if accepted:
                    owner.require_fresh_source_authorization(evidence())
                else:
                    with self.assertRaises(owner.fast_path.SecurityBlocker):
                        owner.require_fresh_source_authorization(evidence())

    def test_shared_claims_exclude_cross_operation_candidates_and_reuse(self):
        source, final = authorizations()
        integration, _ = fixtures.fixture_authorizations()
        claims = {}
        owner.publication._add_enrolled_draft_claim(claims, {"authorization": source})
        for value in (source, integration):
            with self.assertRaises(owner.publication.LifecyclePublicationError):
                owner.publication._add_enrolled_draft_claim(claims, {"authorization": value})
        owner.publication._add_enrolled_draft_claim(claims, {"authorization": final})
        with self.assertRaises(owner.publication.LifecyclePublicationError):
            owner.publication._add_enrolled_draft_claim(claims, {"authorization": final})

    def test_initial_guard_rejects_counters_histories_corrections_and_replacement(self):
        fixtures.EnrolledDraftAuthorityTests.test_all_initial_state_counters_histories_and_proof_mode_are_closed(self)
        fixtures.EnrolledDraftAuthorityTests.test_zero_counters_do_not_admit_historical_corrections_or_replacement_pr(self)
        fixtures.EnrolledDraftAuthorityTests.test_stale_current_wrong_issue_pr_repository_and_root_are_rejected(self)

    def test_source_cli_requires_exact_user_bounds(self):
        for command in ("prepare-enrolled-draft-source", "advance-enrolled-draft-source"):
            args = [command, "--repo", "SecPal/.github", "--delivery-issue", "123", "--pr", "124"]
            if command.startswith("prepare-"):
                args.extend(["--operation-directory", "new", "--authorization-id", "source-001",
                             "--manual-gate-evidence", "gates.json", "--expected-predecessor", "a" * 40,
                             "--authorized-tree", "c" * 40, "--expected-signer", fixtures.native.SIGNER,
                             "--expires-at", "1600"])
            else:
                args.extend(["--authorization", "authorization.json"])
            parsed = fixtures.draft.actions.build_parser().parse_args(args)
            self.assertEqual(parsed.command, command)


class SourcePreparationTests(TestCase):
    claim = fixtures.EnrolledDraftPreparationTests.claim

    def setUp(self):
        fixtures.EnrolledDraftPreparationTests.setUp(self)
        self.arguments.expected_predecessor = "a" * 40
        self.arguments.authorized_tree = "c" * 40
        self.arguments.expected_signer = fixtures.native.SIGNER
        self.arguments.expires_at = int(time.time()) + 600
        self.actions._run_attestation_git.return_value = SimpleNamespace(returncode=0, stdout="a" * 40)

    def test_registered_validation_reservation_and_one_single_parent_commit(self):
        self.assertEqual(owner.prepare(self.actions, self.arguments, kind=owner.SOURCE_KIND), 0)
        self.assertEqual(self.events, ["validate", "reserve", "candidate"])
        args = self.actions._create_signed_pre_enrollment_commit.call_args.args
        self.assertEqual(args[1], ["commit-tree", "-S", "c" * 40, "-p", "a" * 40])
        self.assertIn("SecPal-Validation-Receipt: ", args[2])
        owner.fast_path.derive_ready_integration_tree_evidence.assert_not_called()
        value = json.loads((Path(self.arguments.operation_directory) / "authorization.json").read_text())
        self.assertEqual(value["evidence"]["kind"], owner.SOURCE_KIND)
        self.assertNotIn("current_main", value["evidence"])
        self.arguments.operation_directory = str(Path(self.temporary.name) / "second-operation")
        self.arguments.authorization_id = "another-source-id"
        with self.assertRaises(owner.publication.LifecyclePublicationError):
            owner.prepare(self.actions, self.arguments, kind=owner.SOURCE_KIND)
        self.actions._create_signed_pre_enrollment_commit.assert_called_once()

    def test_wrong_tree_predecessor_signer_or_expiry_never_reserves(self):
        for name, wrong in (("authorized_tree", "9" * 40), ("expected_predecessor", "9" * 40),
                            ("expected_signer", "other@secpal.app"), ("expires_at", 1)):
            old = getattr(self.arguments, name)
            setattr(self.arguments, name, wrong)
            with self.subTest(name=name), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                owner.prepare(self.actions, self.arguments, kind=owner.SOURCE_KIND)
            setattr(self.arguments, name, old)
        self.assertEqual(self.events, [])

    def test_failed_validation_and_changed_staged_tree_never_create(self):
        self.actions._run_registered_validations.side_effect = None
        self.actions._run_registered_validations.return_value = False
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            owner.prepare(self.actions, self.arguments, kind=owner.SOURCE_KIND)
        self.assertEqual(self.events, [])
        self.arguments.operation_directory = str(Path(self.temporary.name) / "changed")
        self.actions._run_registered_validations.return_value = True
        self.actions._staged_tree.side_effect = ["c" * 40, "9" * 40]
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            owner.prepare(self.actions, self.arguments, kind=owner.SOURCE_KIND)
        self.actions._create_signed_pre_enrollment_commit.assert_not_called()


class SourceExecutionTests(TestCase):
    validation = fixtures.EnrolledDraftExecutionTests.validation
    live = fixtures.EnrolledDraftExecutionTests.live
    claim = fixtures.EnrolledDraftExecutionTests.claim
    read_claim = fixtures.EnrolledDraftExecutionTests.read_claim
    push = fixtures.EnrolledDraftExecutionTests.push

    def setUp(self):
        fixtures.EnrolledDraftExecutionTests.setUp(self)
        self.evidence = evidence()
        self.evidence["user_authorization"] = {"issued_at": int(time.time()), "expires_at": int(time.time()) + 600}
        self.preparation, self.authorization = authorizations(self.evidence)
        Path(self.arguments.authorization).write_text(json.dumps(self.authorization))
        owner.fast_path.verify_enrolled_draft_validation_evidence.return_value = self.validation()

    def advance(self):
        return owner.integrate(self.actions, self.arguments, kind=owner.SOURCE_KIND)

    def test_positive_publication_preserves_every_lifecycle_fact(self):
        before = self.harness.current
        self.assertEqual(self.advance(), 0)
        self.assertEqual(self.calls, ["claim", "push"])
        self.assertEqual(self.harness.current.lifecycle.state, before.lifecycle.state)
        self.assertEqual(self.harness.current.lifecycle.lifecycle_id, before.lifecycle.lifecycle_id)
        self.assertEqual(self.harness.current.lifecycle.head_sha, self.head)
        self.assertEqual(self.harness.transition.transition_kind, "HEAD_ADVANCED")

    def test_separate_fresh_authority_advances_another_direct_child(self):
        self.advance()
        self.evidence.update(owner.current_binding(self.harness.current))
        self.evidence["ordered_parent_shas"] = [self.head]
        self.evidence["validated_tree_sha"] = "7" * 40
        self.head = "8" * 40
        self.preparation, self.authorization = authorizations(self.evidence, candidate=self.head, authorization_id="source-002")
        self.claimed = False
        owner._verify_candidate_package.return_value = self.head
        Path(self.arguments.authorization).write_text(json.dumps(self.authorization))
        owner.fast_path.verify_enrolled_draft_validation_evidence.return_value = self.validation()
        self.assertEqual(self.advance(), 0)
        self.assertEqual(self.calls, ["claim", "push", "claim", "push"])
        self.assertEqual(self.harness.current.lifecycle.head_sha, self.head)

    def test_uncertain_push_or_publication_never_retries(self):
        self.harness.publication_mode = "AMBIGUOUS_PREDECESSOR"
        with self.assertRaises(owner.publication.LifecyclePublicationAmbiguousWrite):
            self.advance()
        self.assertEqual(self.calls, ["claim", "push"])
        self.arguments.reconcile = True
        self.harness.publication_mode = "SUCCESS"
        with mock.patch.object(owner.time, "time", return_value=999999999999):
            self.assertEqual(self.advance(), 0)
        self.assertEqual(self.calls, ["claim", "push"])
        self.assertEqual(self.advance(), 0)
        self.assertEqual(self.calls, ["claim", "push"])

    def test_claimed_but_unpushed_candidate_cannot_retry_or_reconcile(self):
        owner._push_exact.side_effect = RuntimeError("uncertain push")
        with self.assertRaises(RuntimeError):
            self.advance()
        with self.assertRaises(owner.publication.LifecyclePublicationError):
            self.advance()
        self.arguments.reconcile = True
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.advance()
        self.assertEqual(self.calls, ["claim", "claim"])
        self.assertEqual(owner._push_exact.call_count, 1)

    def test_main_can_advance_without_becoming_a_parent(self):
        self.actions._authenticate_protected_bridge_main.return_value = "9" * 40
        self.assertEqual(self.advance(), 0)
        self.assertEqual(self.evidence["ordered_parent_shas"], ["a" * 40])

    def test_wrong_selection_policy_graph_or_expiration_stops_before_push(self):
        for attribute, value in (("repo", "Other/repository"), ("delivery_issue", 100), ("pr", 200)):
            old = getattr(self.arguments, attribute)
            setattr(self.arguments, attribute, value)
            with self.subTest(attribute=attribute), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                self.advance()
            setattr(self.arguments, attribute, old)
        owner._entry.return_value = ({}, {"validation": ["substituted"]})
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.advance()
        owner._entry.return_value = ({}, {"validation": []})
        owner._graph.return_value = "9" * 64
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.advance()
        owner._graph.return_value = self.evidence["work_graph_digest"]
        with mock.patch.object(owner.time, "time", return_value=999999999999), self.assertRaises(owner.fast_path.SecurityBlocker):
            self.advance()
        self.assertEqual(self.calls, [])

    def test_publication_substitution_cannot_report_success(self):
        original = self.harness.publisher
        def substitute(raw, **kwargs):
            result = original(raw, **kwargs)
            self.harness.current = replace(result, lifecycle=replace(result.lifecycle, head_sha="9" * 40))
            return result
        owner.publication.advance_current_terminal.side_effect = substitute
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.advance()


class IntegrationPreparationMainTests(TestCase):
    claim = fixtures.EnrolledDraftPreparationTests.claim

    def setUp(self):
        fixtures.EnrolledDraftPreparationTests.setUp(self)

    def test_main_race_after_validation_stops_before_candidate_reservation(self):
        calls = []
        def live(_actions, _repo, _issue, _pr, _head, main_sha, _ref=None):
            calls.append(main_sha)
            if len(calls) > 1 and main_sha != "9" * 40:
                raise owner.fast_path.SecurityBlocker("protected-main drift")
            return "delivery"
        owner._live.side_effect = live
        self.actions._authenticate_protected_bridge_main.side_effect = ["b" * 40, "b" * 40, "9" * 40]
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "protected-main drift"):
            owner.prepare(self.actions, self.arguments)
        self.assertEqual(self.events, ["validate"])
        self.assertFalse(self.claims)
        self.actions._create_signed_pre_enrollment_commit.assert_not_called()


class MainSeparationTests(TestCase):
    validation = fixtures.EnrolledDraftExecutionTests.validation
    claim = fixtures.EnrolledDraftExecutionTests.claim
    read_claim = fixtures.EnrolledDraftExecutionTests.read_claim
    push = fixtures.EnrolledDraftExecutionTests.push

    def setUp(self):
        fixtures.EnrolledDraftExecutionTests.setUp(self)
        self.observed_main = self.evidence["current_main"]["sha"]

    def live(self, actions, repository, issue, pr, head, main_sha, ref=None):
        fixtures.EnrolledDraftExecutionTests.live(self, actions, repository, issue, pr, head, main_sha, ref)
        if main_sha != self.observed_main:
            raise owner.fast_path.SecurityBlocker("protected-main drift")

    def advance_main(self):
        self.observed_main = "9" * 40
        self.actions._authenticate_protected_bridge_main.return_value = self.observed_main

    def test_integration_rejects_main_advancement_after_push(self):
        def push_and_advance(*args):
            self.push(*args)
            self.advance_main()
        owner._push_exact.side_effect = push_and_advance
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "protected-main drift"):
            owner.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls, ["claim", "push"])
        self.assertFalse(self.harness.publication_writes)

    def test_missing_integration_publication_cannot_reconcile_stale_main(self):
        self.harness.publication_mode = "AMBIGUOUS_PREDECESSOR"
        with self.assertRaises(owner.publication.LifecyclePublicationAmbiguousWrite):
            owner.integrate(self.actions, self.arguments)
        self.arguments.reconcile = True
        self.harness.publication_mode = "SUCCESS"
        self.advance_main()
        writes = len(self.harness.publication_writes)
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "protected-main drift"):
            owner.integrate(self.actions, self.arguments)
        self.assertEqual(len(self.harness.publication_writes), writes)
        self.assertEqual(self.calls, ["claim", "push"])

    def test_completed_integration_reconciliation_rejects_stale_main(self):
        owner.integrate(self.actions, self.arguments)
        self.arguments.reconcile = True
        self.advance_main()
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "protected-main drift"):
            owner.integrate(self.actions, self.arguments)
        self.assertEqual(self.calls, ["claim", "push"])
        self.assertEqual(len(self.harness.publication_writes), 1)

    def test_integration_rechecks_authorized_main_before_publication(self):
        original = owner._successor
        def advance_during_successor(*args):
            result = original(*args)
            self.advance_main()
            return result
        with mock.patch.object(owner, "_successor", side_effect=advance_during_successor):
            with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "protected-main drift"):
                owner.integrate(self.actions, self.arguments)
        self.assertFalse(self.harness.publication_writes)

    def test_integration_rechecks_authorized_main_after_publication(self):
        original = self.harness.publisher
        def advance_during_publication(*args, **kwargs):
            result = original(*args, **kwargs)
            self.advance_main()
            return result
        owner.publication.advance_current_terminal.side_effect = advance_during_publication
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "protected-main drift"):
            owner.integrate(self.actions, self.arguments)
        self.assertEqual(len(self.harness.publication_writes), 1)

    def test_source_advancement_allows_independent_main_advancement_after_push(self):
        self.evidence = evidence()
        self.evidence["user_authorization"] = {"issued_at": int(time.time()), "expires_at": int(time.time()) + 600}
        self.preparation, self.authorization = authorizations(self.evidence)
        Path(self.arguments.authorization).write_text(json.dumps(self.authorization))
        owner.fast_path.verify_enrolled_draft_validation_evidence.return_value = self.validation()
        def push_and_advance(*args):
            self.push(*args)
            self.advance_main()
        owner._push_exact.side_effect = push_and_advance
        self.assertEqual(owner.integrate(self.actions, self.arguments, kind=owner.SOURCE_KIND), 0)
        self.assertEqual(self.calls, ["claim", "push"])
        self.assertEqual(self.evidence["ordered_parent_shas"], ["a" * 40])


class SourceRealGitTests(TestCase):
    git = fixtures.EnrolledDraftRealGitTests.git
    policy_context = fixtures.EnrolledDraftRealGitTests.policy_context

    def setUp(self):
        fixtures.EnrolledDraftRealGitTests.setUp(self)

    def package(self, *, parents=None, signed=True, trailers=None):
        item = evidence()
        item.update(draft_head_sha=self.parent1, ordered_parent_shas=[self.parent1], validated_tree_sha=self.tree)
        preparation, authorization = authorizations(item)
        receipt = authorization["validation_receipt"]
        lines = list(zip(owner.validation_trailers(item), (owner.fast_path.digest_json(item), receipt["receipt_digest"]))) if trailers is None else trailers
        message = "source fixture\n\n" + "".join(f"{name}: {value}\n" for name, value in lines)
        args = ["commit-tree"] + (["-S"] if signed else []) + [self.tree]
        for parent in ([self.parent1] if parents is None else parents):
            args.extend(["-p", parent])
        head = self.git(*args, input=message)
        authorization["final_attestation"] = owner.fast_path.create_enrolled_draft_final_attestation(item, receipt, candidate_head_sha=head, signature_fingerprint=owner.execution._ssh_public_key_fingerprint(self.public_key))
        return fixtures.sign_fields({key: val for key, val in authorization.items() if key not in {"signature", "authorization_digest"}}, owner.authorization_domain(owner.SOURCE_KIND))

    def test_real_signed_single_parent_and_sealed_attestation(self):
        with self.policy_context():
            package = self.package()
            verified = owner.fast_path.verify_enrolled_draft_validation_evidence(package, repository_root=self.root)
            self.assertTrue(owner.fast_path.is_verified_validation_evidence(verified))
            self.assertFalse(owner.fast_path.is_verified_validation_evidence(replace(verified, tree_sha="9" * 40)))
            candidate = package["final_attestation"]["candidate_head_sha"]
            self.assertEqual(self.git("rev-list", "--parents", "-n", "1", candidate).split(), [candidate, self.parent1])

    def test_merge_rewrite_unsigned_and_missing_duplicate_or_wrong_receipt(self):
        good = self.package()
        item = good["evidence"]
        lines = list(zip(owner.validation_trailers(item), (owner.fast_path.digest_json(item), good["validation_receipt"]["receipt_digest"])))
        with self.policy_context():
            for update in ({"parents": [self.parent1, self.parent2]}, {"parents": [self.base]},
                           {"signed": False}, {"trailers": lines[:1]},
                           {"trailers": lines + [lines[-1]]},
                           {"trailers": lines + [(lines[-1][0], "malformed")]},
                           {"trailers": [lines[0], (lines[-1][0], "9" * 64)]}):
                with self.subTest(update=update), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                    owner.fast_path.verify_enrolled_draft_validation_evidence(self.package(**update), repository_root=self.root)

    def test_wrong_signer_cannot_supply_source_attestation(self):
        package = self.package()
        with self.policy_context(), mock.patch.object(owner.fast_path, "authenticate_integration_commit", return_value=SimpleNamespace(tree_sha=self.tree, parent_shas=(self.parent1,), signature_fingerprint="SHA256:BBBB")):
            with self.assertRaises(owner.fast_path.SecurityBlocker):
                owner.fast_path.verify_enrolled_draft_validation_evidence(package, repository_root=self.root)


class SourceLiveBoundaryTests(TestCase):
    def test_exact_primary_pr_and_every_live_identity_boundary(self):
        live = {"repository": "SecPal/.github", "head_repository": "SecPal/.github",
            "base_repository": "SecPal/.github", "pull_request_number": fixtures.native.PR,
            "state": "OPEN", "draft": True, "head_sha": "a" * 40,
            "base_ref": "main", "base_sha": "b" * 40,
            "closing_issues_complete": True,
            "closing_issues": [{"repository": "SecPal/.github", "number": fixtures.native.ISSUE, "state": "OPEN"}],
            "head_ref": "delivery"}
        actions = SimpleNamespace(LiveGitHub=lambda: SimpleNamespace(observe_ready_integration_authority=lambda *_: live),
            REPOSITORY_ROOT=ROOT, _run_attestation_git=mock.Mock(return_value=SimpleNamespace(returncode=0)))
        graph = {"issue": {"claims": [{"pull_request": f"SecPal/.github#{fixtures.native.PR}"}]}}
        with mock.patch.object(owner, "_work_graph", return_value=graph):
            self.assertEqual(owner._live(actions, "SecPal/.github", fixtures.native.ISSUE, fixtures.native.PR, "a" * 40, "b" * 40, "delivery"), "delivery")
            for key, value in (("repository", "Other/repository"), ("head_repository", "Fork/repository"),
                               ("base_repository", "Other/repository"), ("pull_request_number", 1),
                               ("state", "CLOSED"), ("draft", False), ("head_sha", "9" * 40),
                               ("base_ref", "development"), ("closing_issues_complete", False),
                               ("closing_issues", []), ("head_ref", "main"), ("head_ref", "other")):
                old = live[key]
                live[key] = value
                with self.subTest(key=key), self.assertRaises(owner.fast_path.SecurityBlocker):
                    owner._live(actions, "SecPal/.github", fixtures.native.ISSUE, fixtures.native.PR, "a" * 40, "b" * 40, "delivery")
                live[key] = old
            graph["issue"]["claims"].append({"pull_request": "SecPal/.github#100"})
            with self.assertRaises(owner.fast_path.SecurityBlocker):
                owner._live(actions, "SecPal/.github", fixtures.native.ISSUE, fixtures.native.PR, "a" * 40, "b" * 40)

    def test_source_transport_binds_sole_parent_and_one_exact_non_force_ref(self):
        item = evidence()
        head = "6" * 40
        actions = SimpleNamespace(_run_attestation_git=lambda root, args, **kwargs: SimpleNamespace(returncode=0, stdout=b"PACK" if args[0] == "pack-objects" else "https://github.com/SecPal/.github.git\n"))
        def transport(root, args, **kwargs):
            if args[0] in {"init", "index-pack"}:
                return SimpleNamespace(returncode=0, stdout=b"")
            if args[0] == "cat-file":
                return SimpleNamespace(returncode=0, stdout=(f"tree {item['validated_tree_sha']}\nparent {item['draft_head_sha']}\n\nsource\n").encode())
            self.assertNotEqual(root, ROOT)
            self.assertEqual(args[-2:], ["https://github.com/SecPal/.github.git", f"{head}:refs/heads/delivery"])
            self.assertNotIn("--force", args)
            self.assertNotIn("--force-with-lease", args)
            hook = Path(args[1].split("=", 1)[1]) / "pre-push"
            import subprocess
            row = f"{head} {head} refs/heads/delivery {item['draft_head_sha']}\n"
            self.assertEqual(subprocess.run([str(hook)], input=row, text=True).returncode, 0)
            for invalid in (row + row, row.replace("delivery", "main"), row.replace("delivery", "other"),
                            row.replace(item['draft_head_sha'], "9" * 40), row.replace(head, "9" * 40)):
                self.assertNotEqual(subprocess.run([str(hook)], input=invalid, text=True).returncode, 0)
            return SimpleNamespace(returncode=0)
        with fixtures.signature_context(), mock.patch.object(owner.publication, "_github_token", return_value="fixture-nonsecret"), mock.patch.object(owner.publication, "_run_git", side_effect=transport):
            owner._push_exact(actions, ROOT, item, head)


class SourceJournalTests(TestCase):
    def test_real_protected_journal_admits_source_claim_and_rejects_replay(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temporary:
            remote = Path(temporary) / "journal.git"
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            policy = replace(fixtures.native.policy_for(), publication_remote_url=str(remote), genesis_admission_signer_identities=frozenset({fixtures.native.SIGNER}))
            with fixtures.signature_context(), mock.patch.object(owner.authority, "_load_lifecycle_trust_policy", return_value=policy), mock.patch.object(owner.publication, "_verify_live_protection"):
                chain = fixtures.native.Chain()
                signer = fixtures.native.signer_for()
                owner.publication.admit_native_genesis(chain.raw(), signer_identity=fixtures.native.SIGNER, signer=signer)
                current = owner.publication.enroll_existing_lifecycle(chain.raw(), signer_identity=fixtures.native.SIGNER, signer=signer)
                item = {**evidence(), **owner.current_binding(current)}
                item["ordered_parent_shas"] = [current.lifecycle.head_sha]
                preparation, final = authorizations(item)
                for selected in (preparation, final):
                    owner.publication.claim_enrolled_draft_integration(selected, signer_identity=fixtures.native.SIGNER, signer=signer)
                owner.publication.verify_enrolled_draft_integration_claim(final)
                after = owner.publication.verify_current_lifecycle_authority(fixtures.native.REPOSITORY, fixtures.native.ISSUE)
                self.assertEqual(after.publication_oid, current.publication_oid)
                self.assertEqual(after.lifecycle.state, current.lifecycle.state)
                with self.assertRaises(owner.publication.LifecyclePublicationError):
                    owner.publication.claim_enrolled_draft_integration(final, signer_identity=fixtures.native.SIGNER, signer=signer)


if __name__ == "__main__":
    main()
