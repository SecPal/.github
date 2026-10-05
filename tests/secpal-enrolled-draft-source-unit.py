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

    def test_expensive_validation_expiry_stops_before_reservation_or_candidate(self):
        expiry = self.arguments.expires_at
        with mock.patch.object(owner.time, "time", return_value=expiry - 1) as clock:
            def validate(*args):
                self.events.append("validate")
                clock.return_value = expiry
                return True
            self.actions._run_registered_validations.side_effect = validate
            with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "stale"):
                owner.prepare(self.actions, self.arguments, kind=owner.SOURCE_KIND)
        self.assertEqual(self.events, ["validate"])
        owner.publication.claim_enrolled_draft_integration.assert_not_called()
        self.actions._create_signed_pre_enrollment_commit.assert_not_called()

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

    def test_expired_consumed_claim_requires_exact_fresh_reacquisition(self):
        # Production ordering: the original claim wins, then authorization
        # expires at the final freshness boundary before any branch dispatch.
        expiry = self.evidence["user_authorization"]["expires_at"]
        with mock.patch.object(owner.time, "time", side_effect=[expiry - 1, expiry]):
            with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "stale"):
                self.advance()
        self.assertTrue(self.claimed)
        self.assertEqual(self.branch, self.evidence["draft_head_sha"])
        self.assertEqual(self.harness.current.lifecycle.head_sha, self.branch)
        owner._push_exact.assert_not_called()
        with self.assertRaises(owner.publication.LifecyclePublicationError):
            self.advance()
        self.arguments.reconcile = True
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.advance()
        owner._push_exact.assert_not_called()
        # The new maintained boundary must admit only this existing package;
        # ordinary retry and read-only reconciliation remain prohibited above.
        with mock.patch.object(owner.time, "time", return_value=expiry + 1):
            install_reacquisition_fixture(self)
            self.assertEqual(owner.reacquire_source_push(self.actions, self.arguments), 0)
        self.assertEqual(self.branch, self.head)
        self.assertEqual(self.harness.transition.transition_kind, "HEAD_ADVANCED")
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

    def test_reacquisition_authenticates_retained_object_without_creating_another(self):
        original = self.package()
        preparation, _ = authorizations(original["evidence"])
        predecessor = fixtures.native.Harness(fixtures.native.Chain()).current
        current = replace(predecessor, lifecycle=replace(predecessor.lifecycle, head_sha=self.parent1))
        path = self.root / "original.json"
        path.write_text(json.dumps(original))
        actions = SimpleNamespace(
            _require_distinct_candidate_repository_root=mock.Mock(),
            _read_pre_enrollment_json=fixtures.draft.actions._read_pre_enrollment_json,
            _run_attestation_git=fixtures.draft.actions._run_attestation_git,
            _commit_trailer_digest=fixtures.draft.actions._commit_trailer_digest,
            _authenticate_protected_bridge_main=mock.Mock(return_value="b" * 40),
            _create_signed_pre_enrollment_commit=mock.Mock(),
            _run_registered_validations=mock.Mock(),
            LiveGitHub=lambda: SimpleNamespace(observe_ready_integration_authority=lambda *_: {"head_sha": self.parent1}),
        )
        arguments = SimpleNamespace(repo=fixtures.native.REPOSITORY, delivery_issue=fixtures.native.ISSUE,
            pr=fixtures.native.PR, repo_root=str(self.root), authorization=str(path))
        before = self.git("count-objects", "-v")
        claims = ({"authorization": preparation, "publication_digest": "1" * 64},
                  {"authorization": original, "publication_digest": "2" * 64})
        with self.policy_context(), mock.patch.object(owner, "_trusted_source", return_value="9" * 40), mock.patch.object(owner, "_entry", return_value=({}, {"validation": []})), mock.patch.object(owner, "_live"), mock.patch.object(owner, "_graph", return_value="d" * 64), mock.patch.object(owner, "_require_unpublished_source_history"), mock.patch.object(owner.publication, "verify_current_lifecycle_authority", return_value=current), mock.patch.object(owner.publication, "verify_enrolled_draft_source_claims", return_value=claims), mock.patch.object(owner.publication, "_run_gh", return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"ref": "refs/heads/delivery", "object": {"type": "commit", "sha": self.parent1}}).encode())):
            _, authenticated, binding = owner._qualify_source_reacquisition(actions, arguments, unused=True)
        self.assertEqual(authenticated, original)
        self.assertEqual(binding["candidate_head_sha"], original["final_attestation"]["candidate_head_sha"])
        self.assertEqual(self.git("count-objects", "-v"), before)
        actions._create_signed_pre_enrollment_commit.assert_not_called()
        actions._run_registered_validations.assert_not_called()

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


def install_reacquisition_fixture(case):
    case.protected_claims = {}
    preparation = {"authorization": case.preparation, "publication_digest": "1" * 64}
    consumed = {"authorization": case.authorization, "publication_digest": "2" * 64}
    for item in (preparation, consumed):
        owner.publication._add_enrolled_draft_claim(case.protected_claims, item)
    binding = {**owner._original_reacquisition_binding(case.authorization),
        "preparation_claim_digest": preparation["publication_digest"],
        "original_push_claim_digest": consumed["publication_digest"],
        "accepted_main_sha": "9" * 40,
        "policy_digest": owner.fast_path.digest_json(owner.REACQUISITION_POLICY),
        "work_graph_digest": case.evidence["work_graph_digest"]}
    now = int(owner.time.time())
    case.reauthorization = fixtures.sign_fields({"schema_version": "1.0",
        "kind": owner.REACQUISITION_KIND, "operation_id": "replacement-001",
        "binding": binding, "issued_at": now, "expires_at": now + 600,
        "signer_identity": fixtures.native.SIGNER}, owner.REACQUISITION_DOMAIN)
    case.arguments.reauthorization = str(Path(case.temporary.name) / "reauthorization.json")
    Path(case.arguments.reauthorization).write_text(json.dumps(case.reauthorization))
    case.actions.LiveGitHub = lambda: SimpleNamespace(observe_ready_integration_authority=lambda *_: {"head_sha": case.branch})
    case.actions._write_fast_report = lambda path, value: Path(path).write_text(json.dumps(value))
    def read(original, *, require_unused_reacquisition=False, required_reacquisition=None):
        if case.harness.current.publication_oid != case.evidence["current_publication_oid"]:
            raise owner.publication.LifecyclePublicationError("CURRENT advanced")
        if original != consumed["authorization"]:
            raise owner.publication.LifecyclePublicationError("original substituted")
        if require_unused_reacquisition and any(v.get("reacquisition_authorization") for v in case.protected_claims.values()):
            raise owner.publication.LifecyclePublicationError("reacquisition already consumed")
        if required_reacquisition is not None:
            owned = case.protected_claims.get(required_reacquisition["authorization_digest"])
            if owned is None or owned.get("reacquisition_authorization") != required_reacquisition:
                raise owner.publication.LifecyclePublicationError("replacement ownership missing")
        return preparation, consumed
    def claim(original, **kwargs):
        case.calls.append("replacement-claim")
        owner.publication._add_enrolled_draft_claim(case.protected_claims,
            {"authorization": original, "reacquisition_authorization": kwargs["reacquisition_authorization"]})
    owner.publication.claim_enrolled_draft_integration.side_effect = claim
    for module, name, kwargs in (
        (owner.publication, "verify_enrolled_draft_source_claims", {"side_effect": read}),
        (owner, "_require_unpublished_source_history", {}),
        (owner.publication, "_run_gh", {"side_effect": lambda *_: SimpleNamespace(returncode=0,
            stdout=json.dumps({"ref": "refs/heads/" + case.evidence["head_ref"],
                "object": {"type": "commit", "sha": case.branch}}).encode())}),
    ):
        patch = mock.patch.object(module, name, **kwargs)
        patch.start()
        case.addCleanup(patch.stop)
    return binding


class SourceReacquisitionExecutionTests(TestCase):
    validation = SourceExecutionTests.validation
    live = SourceExecutionTests.live
    claim = SourceExecutionTests.claim
    read_claim = SourceExecutionTests.read_claim
    push = SourceExecutionTests.push

    def setUp(self):
        SourceExecutionTests.setUp(self)
        self.evidence["user_authorization"] = {"issued_at": 1000, "expires_at": 1600}
        self.preparation, self.authorization = authorizations(self.evidence)
        Path(self.arguments.authorization).write_text(json.dumps(self.authorization))
        owner.fast_path.verify_enrolled_draft_validation_evidence.return_value = self.validation()
        self.claimed = True
        self.binding = install_reacquisition_fixture(self)

    def recover(self):
        return owner.reacquire_source_push(self.actions, self.arguments)

    def test_closed_cli_cannot_request_force_rewrite_or_candidate_creation(self):
        parser = fixtures.draft.actions.build_parser()
        base = ["reacquire-enrolled-draft-source-push", "--repo", fixtures.native.REPOSITORY,
            "--delivery-issue", str(fixtures.native.ISSUE), "--pr", str(fixtures.native.PR),
            "--repo-root", str(ROOT), "--authorization", "original.json", "--reauthorization", "fresh.json"]
        selected = parser.parse_args(base)
        self.assertFalse(selected.apply)
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "requires --apply"):
            owner.reacquire_source_push(self.actions, selected)
        for flag in ("--force", "--rebase", "--amend", "--candidate", "--head-ref", "--reconcile"):
            with self.subTest(flag=flag), self.assertRaises(fixtures.draft.actions.fast_path.RecoverableLocalError):
                parser.parse_args(base + [flag])

    def test_one_existing_candidate_push_then_ordinary_head_advanced(self):
        before = self.harness.current
        self.assertEqual(self.recover(), 0)
        self.assertEqual(self.calls, ["replacement-claim", "push"])
        self.assertEqual(self.harness.current.lifecycle.state, before.lifecycle.state)
        self.assertEqual(self.harness.transition.transition_kind, "HEAD_ADVANCED")
        owner._push_exact.assert_called_once()
        # Subsequent live-candidate invocation uses exact reconciliation only.
        self.assertEqual(self.recover(), 0)
        owner._push_exact.assert_called_once()

    def test_stale_pr_pointer_cannot_substitute_for_exact_branch_ref(self):
        raw = {"ref": "refs/heads/delivery", "object": {"type": "commit", "sha": "f" * 40}}
        with mock.patch.object(owner.publication, "_run_gh", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(raw).encode())):
            with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "branch ref"):
                self.recover()
        owner._push_exact.assert_not_called()

    def test_live_candidate_uses_historical_read_only_reconciliation(self):
        self.branch = self.head
        owner._entry.return_value = ({}, {"validation": ["new policy"]})
        self.assertEqual(self.recover(), 0)
        self.assertEqual(self.calls, [])
        owner._push_exact.assert_not_called()
        owner.publication.claim_enrolled_draft_integration.assert_not_called()

    def test_uncertain_nonpersisted_write_is_terminal_across_operation_ids(self):
        owner._push_exact.side_effect = owner.fast_path.SecurityBlocker("uncertain write")
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "terminal stop"):
            self.recover()
        for operation in ("replacement-001", "replacement-002"):
            altered = {key: val for key, val in self.reauthorization.items() if key not in {"signature", "authorization_digest"}}
            altered["operation_id"] = operation
            Path(self.arguments.reauthorization).write_text(json.dumps(fixtures.sign_fields(altered, owner.REACQUISITION_DOMAIN)))
            with self.assertRaisesRegex(owner.publication.LifecyclePublicationError, "already consumed"):
                self.recover()
        owner._push_exact.assert_called_once()

    def test_uncertain_persisted_write_reconciles_without_retry(self):
        def uncertain(*args):
            self.push(*args)
            raise owner.fast_path.SecurityBlocker("response lost")
        owner._push_exact.side_effect = uncertain
        self.assertEqual(self.recover(), 0)
        self.assertEqual(self.harness.transition.transition_kind, "HEAD_ADVANCED")
        owner._push_exact.assert_called_once()

    def test_fresh_authority_substitution_and_expiry_reject_before_claim(self):
        for key, value in (("candidate_head_sha", "f" * 40),
                           ("validated_tree_sha", "f" * 40),
                           ("draft_head_sha", "f" * 40),
                           ("expected_signer", "other@secpal.app"),
                           ("validation_receipt_digest", "f" * 64),
                           ("final_attestation_digest", "f" * 64),
                           ("repository", "Other/repository"),
                           ("delivery_issue", 987), ("pull_request", 988),
                           ("preparation_claim_digest", "f" * 64),
                           ("original_push_claim_digest", "f" * 64),
                           ("accepted_main_sha", "f" * 40),
                           ("policy_digest", "f" * 64),
                           ("work_graph_digest", "f" * 64)):
            fields = {k: copy.deepcopy(v) for k, v in self.reauthorization.items() if k not in {"signature", "authorization_digest"}}
            fields["binding"][key] = value
            Path(self.arguments.reauthorization).write_text(json.dumps(fixtures.sign_fields(fields, owner.REACQUISITION_DOMAIN)))
            with self.subTest(key=key), self.assertRaises((ValueError, owner.fast_path.SecurityBlocker)):
                self.recover()
        Path(self.arguments.reauthorization).write_text(json.dumps(self.reauthorization))
        with mock.patch.object(owner.time, "time", return_value=self.reauthorization["expires_at"]), self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "stale"):
            self.recover()
        owner.publication.claim_enrolled_draft_integration.assert_not_called()
        owner._push_exact.assert_not_called()

    def test_policy_branch_current_and_delivery_drift_reject(self):
        with mock.patch.object(owner, "_entry", return_value=({}, {"validation": ["changed"]})), self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "incompatible"):
            self.recover()
        self.branch = "e" * 40
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.recover()
        self.branch = self.evidence["draft_head_sha"]
        for key in ("repo", "delivery_issue", "pr"):
            before = getattr(self.arguments, key)
            setattr(self.arguments, key, "Other/repository" if key == "repo" else 999)
            with self.subTest(key=key), self.assertRaises(owner.fast_path.SecurityBlocker):
                self.recover()
            setattr(self.arguments, key, before)
        current = self.harness.current
        self.harness.current = replace(current, publication_oid="e" * 40)
        with self.assertRaises(owner.fast_path.SecurityBlocker):
            self.recover()
        self.harness.current = current
        owner._push_exact.assert_not_called()

    def test_changed_graph_after_claim_cannot_dispatch_or_retry(self):
        original_read = owner._qualify_source_reacquisition
        def qualify(*args, **kwargs):
            if not kwargs["unused"]:
                owner._graph.return_value = "f" * 64
            return original_read(*args, **kwargs)
        with mock.patch.object(owner, "_qualify_source_reacquisition", side_effect=qualify), self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "after claim"):
            self.recover()
        with self.assertRaisesRegex(owner.publication.LifecyclePublicationError, "already consumed"):
            self.recover()
        owner._push_exact.assert_not_called()

    def test_post_claim_expiry_consumes_the_only_replacement(self):
        original_read = owner._qualify_source_reacquisition
        def qualify(*args, **kwargs):
            result = original_read(*args, **kwargs)
            if not kwargs["unused"]:
                self.clock.return_value = self.reauthorization["expires_at"]
            return result
        with mock.patch.object(owner.time, "time", return_value=self.reauthorization["issued_at"]) as self.clock, mock.patch.object(owner, "_qualify_source_reacquisition", side_effect=qualify):
            with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "stale"):
                self.recover()
        with self.assertRaisesRegex(owner.publication.LifecyclePublicationError, "already consumed"):
            self.recover()
        owner._push_exact.assert_not_called()

    def test_read_only_qualification_and_explicit_exact_authorization(self):
        self.arguments.output = str(Path(self.temporary.name) / "qualification.json")
        self.assertEqual(owner.qualify_source_reacquisition(self.actions, self.arguments), 0)
        report = json.loads(Path(self.arguments.output).read_text())
        self.assertEqual(report["binding"], self.binding)
        self.arguments.expected_binding_digest = "f" * 64
        self.arguments.operation_id = "replacement-user"
        self.arguments.expires_at = int(time.time()) + 600
        with self.assertRaisesRegex(owner.fast_path.SecurityBlocker, "explicit user"):
            owner.authorize_source_reacquisition(self.actions, self.arguments)
        self.arguments.expected_binding_digest = report["binding_digest"]
        self.assertEqual(owner.authorize_source_reacquisition(self.actions, self.arguments), 0)
        selected = json.loads(Path(self.arguments.output).read_text())
        self.assertEqual(owner.normalize_reacquisition_authorization(selected, self.authorization), selected)
        owner.publication.claim_enrolled_draft_integration.assert_not_called()
        owner._push_exact.assert_not_called()



class SourceReacquisitionJournalTests(TestCase):
    def test_canonical_replacement_is_one_use_across_fresh_clones_and_ids(self):
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
                preparation, original = authorizations(item)
                with self.assertRaises(owner.publication.LifecyclePublicationError):
                    owner.publication.verify_enrolled_draft_source_claims(original)
                owner.publication.claim_enrolled_draft_integration(preparation, signer_identity=fixtures.native.SIGNER, signer=signer)
                with self.assertRaises(owner.publication.LifecyclePublicationError):
                    owner.publication.verify_enrolled_draft_source_claims(original)
                owner.publication.claim_enrolled_draft_integration(original, signer_identity=fixtures.native.SIGNER, signer=signer)
                reserved, consumed = owner.publication.verify_enrolled_draft_source_claims(original, require_unused_reacquisition=True)
                binding = {**owner._original_reacquisition_binding(original),
                    "preparation_claim_digest": reserved["publication_digest"],
                    "original_push_claim_digest": consumed["publication_digest"],
                    "accepted_main_sha": "9" * 40, "policy_digest": owner.fast_path.digest_json(owner.REACQUISITION_POLICY),
                    "work_graph_digest": "d" * 64}
                fields = {"schema_version": "1.0", "kind": owner.REACQUISITION_KIND,
                    "operation_id": "replacement-001", "binding": binding,
                    "issued_at": int(time.time()), "expires_at": int(time.time()) + 600,
                    "signer_identity": fixtures.native.SIGNER}
                replacement = fixtures.sign_fields(fields, owner.REACQUISITION_DOMAIN)
                for key in ("preparation_claim_digest", "original_push_claim_digest"):
                    changed = {**fields, "binding": {**binding, key: "f" * 64}}
                    with self.subTest(key=key), self.assertRaises(owner.publication.LifecyclePublicationError):
                        owner.publication.claim_enrolled_draft_integration(original, signer_identity=fixtures.native.SIGNER, signer=signer, reacquisition_authorization=fixtures.sign_fields(changed, owner.REACQUISITION_DOMAIN))
                # Persisted but unacknowledged claim grants no ephemeral winner
                # capability. Its canonical record still burns the opportunity.
                real_cas = owner.publication._cas_remote_ref
                def uncertain(*args, **kwargs):
                    real_cas(*args, **kwargs)
                    raise owner.publication.LifecyclePublicationAmbiguousWrite("claim response lost")
                with mock.patch.object(owner.publication, "_cas_remote_ref", side_effect=uncertain), self.assertRaises(owner.publication.LifecyclePublicationAmbiguousWrite):
                    owner.publication.claim_enrolled_draft_integration(original, signer_identity=fixtures.native.SIGNER, signer=signer, reacquisition_authorization=replacement)
                for operation in ("replacement-001", "replacement-another-clone"):
                    other = fixtures.sign_fields({**fields, "operation_id": operation}, owner.REACQUISITION_DOMAIN)
                    with self.subTest(operation=operation), self.assertRaisesRegex(owner.publication.LifecyclePublicationError, "already consumed"):
                        owner.publication.claim_enrolled_draft_integration(original, signer_identity=fixtures.native.SIGNER, signer=signer, reacquisition_authorization=other)
                with self.assertRaisesRegex(owner.publication.LifecyclePublicationError, "already consumed"):
                    owner.publication.verify_enrolled_draft_source_claims(original, require_unused_reacquisition=True)
                after = owner.publication.verify_current_lifecycle_authority(fixtures.native.REPOSITORY, fixtures.native.ISSUE)
                self.assertEqual(after.publication_oid, current.publication_oid)
                self.assertEqual(after.lifecycle.state, current.lifecycle.state)
                tip = subprocess.check_output(["git", "--git-dir", str(remote), "rev-parse", fixtures.native.BRANCH], text=True).strip()
                owner.publication._walk_journal_identity_projection(remote, tip, fixtures.native.BRANCH)
                with self.assertRaises(owner.publication.LifecyclePublicationError):
                    owner.publication.claim_enrolled_draft_integration(original, signer_identity=fixtures.native.SIGNER, signer=signer)

    def test_competing_candidate_or_missing_original_claim_cannot_recover(self):
        preparation, original = authorizations()
        claims = {}
        for authorization in (preparation, original):
            owner.publication._add_enrolled_draft_claim(claims, {"authorization": authorization, "publication_digest": "1" * 64})
        # Untrusted workspace claims cannot nominate a second candidate, even
        # with another operation ID and a correctly signed fresh authorization.
        wrong = copy.deepcopy(original)
        wrong["final_attestation"]["candidate_head_sha"] = "f" * 40
        replacement = {"binding": {}}
        for selected, inventory in ((wrong, claims), (original, {})):
            with self.subTest(selected=selected["final_attestation"]["candidate_head_sha"]), self.assertRaises(owner.publication.LifecyclePublicationError):
                owner.publication._add_enrolled_draft_claim(inventory, {"authorization": selected, "reacquisition_authorization": replacement})


class SourceReacquisitionHistoryTests(TestCase):
    def observation(self):
        return {"data": {"repository": {"nameWithOwner": "SecPal/.github", "pullRequest": {
            "number": fixtures.native.PR, "state": "OPEN", "isDraft": True,
            "headRefName": "delivery", "headRefOid": "a" * 40,
            "timelineItems": {"pageInfo": {"hasNextPage": False}, "nodes": [
                {"__typename": "PullRequestCommit", "id": "COMMIT_PREDECESSOR", "commit": {"oid": "a" * 40}},
            ]}}}}}

    def test_complete_provider_representation_normalizes_and_admits_without_rewrite(self):
        _, original = authorizations()
        raw = self.observation()
        normalized = owner.normalize_source_branch_history(raw)
        self.assertEqual(owner.admit_unpublished_source_history(normalized, original), None)
        with mock.patch.object(owner.publication, "_run_gh", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(raw).encode())) as observed:
            owner._require_unpublished_source_history(original)
        self.assertIn("HEAD_REF_RESTORED_EVENT", observed.call_args.args[0][5])

    def test_exact_ref_rejects_missing_changed_noncommit_or_wrong_ref(self):
        raw = {"ref": "refs/heads/delivery", "object": {"type": "commit", "sha": "a" * 40}}
        owner.admit_exact_source_branch_ref(raw, ref="refs/heads/delivery", head="a" * 40)
        for changed in (None, [], {}, {**raw, "ref": "refs/heads/main"},
                        {**raw, "object": {"type": "tree", "sha": "a" * 40}},
                        {**raw, "object": {"type": "commit", "sha": "f" * 40}}):
            with self.subTest(changed=changed), self.assertRaises(owner.fast_path.SecurityBlocker):
                owner.admit_exact_source_branch_ref(changed, ref="refs/heads/delivery", head="a" * 40)

    def test_incomplete_ambiguous_or_persisted_history_never_proves_absence(self):
        _, original = authorizations()
        for event in ("HeadRefForcePushedEvent", "HeadRefDeletedEvent", "HeadRefRestoredEvent", "PullRequestCommit", "UnknownEvent"):
            raw = self.observation()
            raw["data"]["repository"]["pullRequest"]["timelineItems"]["nodes"].append({"__typename": event, "id": "OTHER", "commit": {"oid": original["final_attestation"]["candidate_head_sha"]}})
            with self.subTest(event=event), self.assertRaises(owner.fast_path.SecurityBlocker):
                owner.admit_unpublished_source_history(owner.normalize_source_branch_history(raw), original)
        for mutation in ("pagination", "errors", "duplicate", "fork", "ready", "other_head"):
            raw = self.observation()
            pull = raw["data"]["repository"]["pullRequest"]
            if mutation == "pagination":
                pull["timelineItems"]["pageInfo"]["hasNextPage"] = True
            elif mutation == "errors":
                raw["errors"] = [{"message": "incomplete"}]
            elif mutation == "duplicate":
                pull["timelineItems"]["nodes"] *= 2
            elif mutation == "fork":
                raw["data"]["repository"]["nameWithOwner"] = "Other/repository"
            elif mutation == "ready":
                pull["isDraft"] = False
            else:
                pull["headRefOid"] = "f" * 40
            with self.subTest(mutation=mutation), self.assertRaises(owner.fast_path.SecurityBlocker):
                owner.admit_unpublished_source_history(owner.normalize_source_branch_history(raw), original)


if __name__ == "__main__":
    main()
