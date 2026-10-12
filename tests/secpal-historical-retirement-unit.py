# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact historical retirement invariants, starting from native provider data."""

import copy
import json
import subprocess
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from tests.secpal_actions_fixture import load_actions

actions = load_actions()
from scripts.secpal_pr_review import historical_retirement as retirement
from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_publication as publication
from scripts.secpal_pr_review import fast_path

import importlib

fixtures = importlib.import_module("tests.secpal-lifecycle-publication-unit")


def history():
    return json.loads((Path(__file__).parent / "fixtures/historical-retirement-706.json").read_text())


def proof():
    observed = history()
    return {
        "accepted_main": "a" * 40, "history": observed,
        "facts": retirement.normalize_history(observed),
        "source_signature": {"repository": retirement.REPOSITORY, "head_sha": retirement.HEAD, "tree_sha": retirement.TREE, "parent_shas": [retirement.PARENT], "signer_kind": "SSH_PRINCIPAL", "signer_identity": fixtures.SIGNER, "signature_fingerprint": "SHA256:test-fixture", "signature_classification": "USER_SIGNED", "signature_policy_digest": "e" * 64},
        "issue_contract_digest": "b" * 64,
        "work_graph": {"705": {"issue": {"blocked": False, "claims": [{"executor": "aroviqen"}]}}, "1183": {"issue": {"done": True}}},
        "journal_tip": "c" * 40, "absence_digest": fast_path.digest_json({"schema_version": "1.0", "kind": "VERIFIED_PRE_ENROLLMENT_LIFECYCLE_ABSENCE", "repository": retirement.REPOSITORY, "delivery_issue": 705, "publication_branch": fixtures.BRANCH, "observed_tip_oid": "c" * 40, "current_publication": False, "native_genesis": False, "lifecycle_aware_head_advancement": False}),
    }


def authorization():
    fields = {"schema_version": "1.0", "kind": retirement.KIND,
              "domain": retirement.DOMAIN, "authorization_id": "human:retire-706",
              "intent": retirement.INTENT, "issued_at": 1000, "expires_at": 1900,
              "proof": proof(), "signer_identity": fixtures.SIGNER}
    signed = {**fields, "signature": fixtures.signer_for()(fast_path.canonical_json_bytes(fields), retirement.DOMAIN)}
    return {**signed, "authorization_digest": fast_path.digest_json(signed)}


def claim(document=None):
    fields = {"schema_version": "1.0", "kind": retirement.CLAIM_KIND,
              "domain": retirement.CLAIM_DOMAIN, "authorization": document or authorization(),
              "publication_branch": fixtures.BRANCH, "journal_predecessor_oid": "c" * 40,
              "signer_identity": fixtures.SIGNER}
    signed = {**fields, "signature": fixtures.signer_for()(fast_path.canonical_json_bytes(fields), retirement.CLAIM_DOMAIN)}
    return fast_path.canonical_json_bytes({**signed, "publication_digest": fast_path.digest_json(signed)})


class HistoricalRetirementTests(TestCase):
    def test_truthful_direct_ready_history_and_ineligible_successor(self):
        facts = retirement.normalize_history(history())
        self.assertEqual(facts["creation_disposition"], "DRAFT_FIRST_VIOLATION")
        self.assertEqual(facts["actual_ready_transition_count"], 0)
        self.assertEqual(facts["provider_review_object_count"], 2)
        self.assertEqual(facts["security_disposition"], "FAILED_USAGE_LIMIT_NO_SUCCESS")
        self.assertEqual(facts["historical_receipt_disposition"], "ISSUANCE_UNKNOWN")
        decision = retirement.successor_eligibility(facts)
        self.assertFalse(decision["eligible"])
        self.assertFalse(decision["review_authorized"])
        self.assertEqual(decision["maximum_successors"], 1)
        self.assertEqual(decision["blocker"], "NO_AUTHENTICATED_NON_RESETTING_FIRST_READY_AUTHORITY")

    def test_fabricated_draft_event_is_rejected(self):
        value = history()
        value["timeline"][0].append({"event": "convert_to_draft"})
        with self.assertRaises(retirement.RetirementError):
            retirement.normalize_history(value)

    def test_identity_source_signature_and_history_substitutions(self):
        mutations = [
            lambda v: v["pr"].update(repository="SecPal/api"),
            lambda v: v["pr"].update(head_repository="other/.github"),
            lambda v: v["pr"].update(number=707),
            lambda v: v["pr"].update(head_sha="a" * 40),
            lambda v: v["pr"].update(draft=True),
            lambda v: v["pr"].update(merged=True),
            lambda v: v["pr"].update(created_at="2026-08-23T00:00:00Z"),
            lambda v: v["commit"]["commit"]["tree"].update(sha="b" * 40),
            lambda v: v["commit"]["parents"].append({"sha": "c" * 40}),
            lambda v: v["commit"]["parents"][0].update(sha="d" * 40),
            lambda v: v["commit"]["commit"]["verification"].update(verified=False),
            lambda v: v["commit"]["commit"].update(message="SecPal-Validation-Receipt: " + "e" * 64),
            lambda v: v["commits"][0].append(v["commits"][0][0]),
            lambda v: v["reviews"][0].pop(),
            lambda v: v["reviews"][0][0].update(commit_id="e" * 40),
            lambda v: v["reviews"][0][0]["user"].update(login="aroviqen"),
            lambda v: v["comments"][0][-1].update(body="Security passed"),
            lambda v: v["comments"][0].append(v["comments"][0][-1]),
            lambda v: v["timeline"][0].append({"event": "ready_for_review"}),
            lambda v: v["timeline"][0].append({"event": "head_ref_force_pushed"}),
            lambda v: v["timeline"].append([]),
            lambda v: v["threads"]["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"].update(hasNextPage=True),
            lambda v: v["threads"]["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0].update(isResolved=True),
            lambda v: v["threads"]["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["comments"]["pageInfo"].update(hasNextPage=True),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = history()
                mutate(value)
                with self.assertRaises(retirement.RetirementError):
                    retirement.normalize_history(value)

    def test_conservative_accounting_cannot_be_reset_or_counted_as_two_cycles(self):
        facts = retirement.normalize_history(history())
        for count in (0, 2, False, True):
            with self.subTest(count=count), self.assertRaises(retirement.RetirementError):
                retirement.successor_eligibility({**facts, "conservative_reserved_review_count": count})
        with self.assertRaises(retirement.RetirementError):
            retirement.successor_eligibility({**facts, "delivery_issue": 1183})

    def test_normal_draft_first_is_preserved_and_exact_delivery_cannot_reinitialize(self):
        state = authority.initial_state()
        ready = authority.require_forward_transition(state, "DRAFT_TO_READY", "a" * 64)
        self.assertEqual(ready["ready_transition_count"], 1)
        state["unrestricted_review_count"] = 1
        with self.assertRaises(authority.LifecycleAuthorityError):
            authority.require_forward_transition(state, "DRAFT_TO_READY", "a" * 64)
        with self.assertRaises(retirement.RetirementError):
            authority.create_delivery_initialization(repository=retirement.REPOSITORY,
                delivery_issue=705, pull_request=9999, initial_head_sha="a" * 40,
                validation_receipt_digest="b" * 64, final_attestation_digest="c" * 64,
                signer_identity=fixtures.SIGNER, signer=fixtures.signer_for())

    def test_signed_exact_retirement_and_journal_claim(self):
        with patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature):
            document = authorization()
            self.assertEqual(retirement.verify_authorization(document), document)
            verified = retirement.verify_claim(claim(document), branch=fixtures.BRANCH, parent="c" * 40)
            self.assertEqual(verified["authorization"], document)
            with self.assertRaises(retirement.RetirementError):
                retirement.verify_claim(claim(document), branch=fixtures.BRANCH, parent="e" * 40)

    def test_missing_forged_or_expanded_authority_fails_before_mutation(self):
        with patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature):
            for field, replacement in (("intent", "CREATE_SUCCESSOR"), ("signature", {}), ("expires_at", 9000), ("signer_identity", "forged@secpal.app"), ("proof", {})):
                with self.subTest(field=field):
                    document = authorization()
                    document[field] = replacement
                    with self.assertRaises((ValueError, retirement.RetirementError)):
                        retirement.verify_authorization(document)

    def test_readers_agree_on_replay_and_competing_enrollment(self):
        with patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature):
            raw = claim()
            valid = [("d" * 40, raw, "c" * 40)]
            self.assertEqual(retirement.verify_journal_claims(valid, fixtures.BRANCH)["object_oid"], "d" * 40)
            conflicting = fast_path.canonical_json_bytes({"kind": publication.GENESIS_ADMISSION_KIND, "repository": retirement.REPOSITORY, "delivery_issue": 705})
            for extra in (("e" * 40, raw, "d" * 40), ("e" * 40, conflicting, "d" * 40)):
                with self.assertRaises(retirement.RetirementError):
                    retirement.verify_journal_claims(valid + [extra], fixtures.BRANCH)
            for reader in (publication._walk_journal, publication._walk_journal_identity_projection):
                with patch.object(publication, "_read_publication_object", side_effect=lambda root, oid: (raw, None)):
                    with self.assertRaises(retirement.RetirementError):
                        reader(Path("."), "d" * 40, fixtures.BRANCH)

    def test_terminal_write_classification_never_authorizes_retry(self):
        for result in ("SUCCESS", "REJECTED", "AMBIGUOUS"):
            self.assertEqual(retirement.classify_close_result(result, closed_and_preserved=True), "RETIRED_UNMERGED_VERIFIED")
        self.assertEqual(retirement.classify_close_result("REJECTED", closed_and_preserved=False), "REJECTED_ATTEMPT_CONSUMED")
        self.assertEqual(retirement.classify_close_result("AMBIGUOUS", closed_and_preserved=False), "RETIREMENT_INDETERMINATE_OBSERVATION_ONLY")

    def test_definite_http_rejection_and_ambiguous_transport_are_distinct(self):
        for status, expected in ((403, "REJECTED"), (422, "REJECTED"), (503, "AMBIGUOUS")):
            response = subprocess.CompletedProcess([], 1, f"HTTP/2.0 {status}\r\n\r\n{{}}".encode(), b"")
            with patch.object(publication, "_run_gh", return_value=response) as runner:
                self.assertEqual(retirement._close_once(), expected)
                self.assertEqual(runner.call_count, 1)

    def test_malformed_provider_write_and_readback_remain_observation_only(self):
        response = subprocess.CompletedProcess([], 0, b"HTTP/2.0 200\r\n\r\n[]", b"")
        with patch.object(publication, "_run_gh", return_value=response):
            self.assertEqual(retirement._close_once(), "AMBIGUOUS")
        with patch.object(retirement, "_observe_history", return_value={"pr": {}}):
            with self.assertRaises(retirement.RetirementError):
                retirement._read_back(authorization(), "d" * 40)

    def test_incomplete_native_pr_observation_has_a_bounded_failure(self):
        with patch.object(retirement, "_get", return_value={}):
            with self.assertRaises(retirement.RetirementError):
                retirement._observe_history()

    def test_stale_and_expired_authority_never_claims_or_closes(self):
        with patch.object(retirement, "_require_accepted_main"), patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature), patch.object(retirement, "_claim_attempt") as reserve, patch.object(retirement, "_close_once") as close:
            with self.assertRaises(retirement.RetirementError):
                retirement.retire(authorization())
            with patch.object(retirement.time, "time", return_value=1100), patch.object(retirement, "authenticate_case", return_value=retirement.VerifiedHistoricalCase({**proof(), "journal_tip": "e" * 40}, retirement._VERIFIED)):
                with self.assertRaises(retirement.RetirementError):
                    retirement.retire(authorization())
            reserve.assert_not_called()
            close.assert_not_called()

    def test_ambiguous_patch_is_read_back_once_without_retry(self):
        with patch.object(retirement, "_require_accepted_main"), patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature), patch.object(retirement.time, "time", return_value=1100), patch.object(retirement, "authenticate_case", return_value=retirement.VerifiedHistoricalCase(proof(), retirement._VERIFIED)), patch.object(retirement, "_claim_attempt", return_value="e" * 40), patch.object(retirement, "_verify_preclose"), patch.object(retirement, "_close_once", return_value="AMBIGUOUS") as close, patch.object(retirement, "_read_back", return_value=False) as read:
            result = retirement.retire(authorization())
            self.assertEqual(result["status"], "RETIREMENT_INDETERMINATE_OBSERVATION_ONLY")
            close.assert_called_once()
            read.assert_called_once()

    def test_reconciliation_cannot_write_and_requires_signed_claim(self):
        with patch.object(retirement, "_require_accepted_main"), patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature), patch.object(retirement, "_read_back", return_value=True), patch.object(retirement, "_close_once") as close, patch.object(retirement, "_claim_attempt") as reserve:
            result = retirement.reconcile(authorization(), "e" * 40)
            self.assertEqual(result["github_attempts"], 0)
            self.assertFalse(result["successor"]["eligible"])
            close.assert_not_called()
            reserve.assert_not_called()

    def test_candidate_local_authority_never_enters_retirement(self):
        with patch.object(retirement, "_require_accepted_main", side_effect=fast_path.SecurityBlocker("candidate tooling")), patch.object(retirement, "_claim_attempt") as reserve:
            with self.assertRaises(fast_path.SecurityBlocker):
                retirement.retire(authorization())
            reserve.assert_not_called()

    def test_post_claim_race_is_consumed_without_a_close(self):
        with patch.object(retirement, "_require_accepted_main"), patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature), patch.object(retirement.time, "time", return_value=1100), patch.object(retirement, "authenticate_case", return_value=retirement.VerifiedHistoricalCase(proof(), retirement._VERIFIED)), patch.object(retirement, "_claim_attempt", return_value="e" * 40), patch.object(retirement, "_verify_preclose", side_effect=retirement.RetirementError("competing primary")), patch.object(retirement, "_close_once") as close:
            with self.assertRaises(retirement.RetirementAttemptStopped) as caught:
                retirement.retire(authorization())
            self.assertEqual(caught.exception.claim_oid, "e" * 40)
            close.assert_not_called()

    def test_partial_claim_cas_never_closes_even_if_it_might_have_persisted(self):
        with patch.object(retirement, "_require_accepted_main"), patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature), patch.object(retirement.time, "time", return_value=1100), patch.object(retirement, "authenticate_case", return_value=retirement.VerifiedHistoricalCase(proof(), retirement._VERIFIED)), patch.object(retirement, "_claim_attempt", side_effect=retirement.RetirementAttemptStopped("e" * 40, "CLAIM_CAS_AMBIGUOUS")), patch.object(retirement, "_close_once") as close:
            with self.assertRaises(retirement.RetirementAttemptStopped):
                retirement.retire(authorization())
            close.assert_not_called()

    def test_claim_writer_cas_failure_retains_oid_and_performs_no_retry(self):
        from contextlib import nullcontext
        with patch.object(retirement.execution, "_policy_role_signer", return_value=(fixtures.SIGNER, fixtures.signer_for())), patch.object(publication, "_verify_live_protection"), patch.object(publication, "_isolated_repository", return_value=nullcontext((Path("."), {}))), patch.object(publication, "_observe_remote_current_once", return_value="c" * 40), patch.object(publication, "_walk_journal"), patch.object(publication, "_write_publication_object", return_value="e" * 40), patch.object(publication, "_cas_remote_ref", side_effect=publication.LifecyclePublicationAmbiguousWrite("uncertain")) as cas:
            with self.assertRaises(retirement.RetirementAttemptStopped) as caught:
                retirement._claim_attempt(authorization())
            self.assertEqual(caught.exception.claim_oid, "e" * 40)
            cas.assert_called_once()

    def test_preserved_closed_native_history_and_claim_are_read_back(self):
        from contextlib import nullcontext
        observed = history()
        observed["pr"].update(state="closed", closed_at="2026-10-12T12:00:00Z")
        observed["provider_timeline"]["data"]["repository"]["pullRequest"]["state"] = "CLOSED"
        observed["timeline"][0].append({"event": "closed", "actor": {"login": "aroviqen"}})
        doc = authorization()
        doc["proof"]["issue_contract_digest"] = fast_path.digest_json({"number": 705, "body": "same contract"})
        raw = claim(doc)
        graphs = {705: {"issue": {"open": True, "claims": []}}, 676: {"issue": {"blocked_by": ["SecPal/.github#705"]}}}
        with patch.object(retirement, "_observe_history", return_value=observed), patch.object(retirement, "_require_accepted_main", return_value=(actions, "a" * 40)), patch.object(retirement, "_graph", side_effect=lambda a, n: graphs[n]), patch.object(retirement, "_get", return_value={"body": "same contract"}), patch.object(publication, "_verify_live_protection"), patch.object(publication, "_isolated_repository", return_value=nullcontext((Path("."), {}))), patch.object(publication, "_observe_remote_current_once", return_value="e" * 40), patch.object(publication, "_walk_journal"), patch.object(publication, "_read_publication_object", return_value=(raw, "c" * 40)), patch.object(publication, "_run_git", return_value=subprocess.CompletedProcess([], 0)), patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature):
            # Editing an authorization after signing is rejected by real claim
            # verification; re-sign only the hermetic authorized proof here.
            unsigned = {k: v for k, v in doc.items() if k not in {"signature", "authorization_digest"}}
            signed = {**unsigned, "signature": fixtures.signer_for()(fast_path.canonical_json_bytes(unsigned), retirement.DOMAIN)}
            doc = {**signed, "authorization_digest": fast_path.digest_json(signed)}
            with patch.object(publication, "_read_publication_object", return_value=(claim(doc), "c" * 40)):
                self.assertTrue(retirement._read_back(doc, "e" * 40))
                observed["comments"][0][-1]["body"] = "Security passed"
                with self.assertRaises(retirement.RetirementError):
                    retirement._read_back(doc, "e" * 40)

    def test_no_closed_event_can_be_inserted_into_open_history(self):
        observed = history()
        observed["timeline"][0].append({"event": "closed"})
        with self.assertRaises(retirement.RetirementError):
            retirement.normalize_history(observed)

    def test_successful_close_has_only_exact_state_write(self):
        response = subprocess.CompletedProcess([], 0, b'HTTP/2.0 200\n\n{"number":706,"state":"closed","merged":false}', b"")
        with patch.object(publication, "_run_gh", return_value=response) as runner:
            self.assertEqual(retirement._close_once(), "SUCCESS")
            arguments = runner.call_args.args[0]
            self.assertIn("repos/SecPal/.github/pulls/706", arguments)
            self.assertEqual(arguments[-2:], ["-f", "state=closed"])
            self.assertNotIn("ready", arguments)
            self.assertNotIn("review", arguments)

    def test_claim_absence_digest_agrees_with_existing_authority(self):
        from contextlib import nullcontext
        with patch.object(publication, "_verify_live_protection"), patch.object(publication, "_isolated_repository", return_value=nullcontext((Path("."), {}))), patch.object(publication, "_observe_remote_current_once", return_value="c" * 40), patch.object(publication, "_walk_journal_identity_projection", return_value=(set(), set())):
            actual = publication.verify_pre_enrollment_absence(retirement.REPOSITORY, 705)
            self.assertEqual(actual.evidence_digest, proof()["absence_digest"])
        document = authorization()
        document["proof"]["absence_digest"] = "e" * 64
        unsigned = {k: v for k, v in document.items() if k not in {"signature", "authorization_digest"}}
        signed = {**unsigned, "signature": fixtures.signer_for()(fast_path.canonical_json_bytes(unsigned), retirement.DOMAIN)}
        document = {**signed, "authorization_digest": fast_path.digest_json(signed)}
        with patch.object(authority, "_policy_signature_verifier", return_value=fixtures.verify_signature):
            with self.assertRaises(retirement.RetirementError):
                retirement.verify_claim(claim(document), branch=fixtures.BRANCH, parent="c" * 40)

    def test_unverified_or_copied_issuance_proof_cannot_sign(self):
        copied = retirement.VerifiedHistoricalCase(proof(), object())
        with patch.object(retirement.execution, "_policy_role_signer") as signer:
            with self.assertRaises(retirement.RetirementError):
                retirement.issue_authorization(copied, authorization_id="human:retire")
            signer.assert_not_called()

        altered = retirement.VerifiedHistoricalCase({**proof(), "accepted_main": "f" * 40}, retirement._VERIFIED)
        with patch.object(retirement, "authenticate_case", return_value=retirement.VerifiedHistoricalCase(proof(), retirement._VERIFIED)), patch.object(retirement.execution, "_policy_role_signer") as signer:
            with self.assertRaises(retirement.RetirementError):
                retirement.issue_authorization(altered, authorization_id="human:retire")
            signer.assert_not_called()

    def test_hidden_provider_edit_history_and_cross_reader_substitution(self):
        for mutate in (
            lambda p: p["timelineItems"]["pageInfo"].update(hasNextPage=True),
            lambda p: p["timelineItems"]["nodes"][1]["userContentEdits"]["pageInfo"].update(hasNextPage=True),
            lambda p: p["timelineItems"]["nodes"][1].update(updatedAt="2026-08-23T00:00:00Z"),
            lambda p: p["timelineItems"]["nodes"][1].update(body="@codex review"),
            lambda p: p.update(headRefOid="e" * 40),
        ):
            value = history()
            mutate(value["provider_timeline"]["data"]["repository"]["pullRequest"])
            with self.assertRaises((retirement.RetirementError, fast_path.SecurityBlocker)):
                retirement.normalize_history(value)

    def test_real_git_claim_preserves_current_and_blocks_replay_in_both_readers(self):
        fixture = fixtures.LifecyclePublicationTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        _, current = fixture.enroll()
        absence = publication.verify_pre_enrollment_absence(retirement.REPOSITORY, 705)
        document = authorization()
        document["proof"].update(journal_tip=absence.observed_tip_oid, absence_digest=absence.evidence_digest)
        unsigned = {k: v for k, v in document.items() if k not in {"signature", "authorization_digest"}}
        signed = {**unsigned, "signature": fixtures.signer_for()(fast_path.canonical_json_bytes(unsigned), retirement.DOMAIN)}
        document = {**signed, "authorization_digest": fast_path.digest_json(signed)}
        with patch.object(retirement.execution, "_policy_role_signer", return_value=(fixtures.SIGNER, fixtures.signer_for())):
            oid = retirement._claim_attempt(document)
            self.assertEqual(fixture.remote_tip(), oid)
            preserved = publication.verify_current_lifecycle_authority(retirement.REPOSITORY, fixtures.ISSUE)
            self.assertEqual(preserved, current)
            for absence_reader in (publication.verify_pre_enrollment_absence, publication.require_unenrolled_delivery):
                with self.assertRaises(publication.LifecyclePublicationError):
                    absence_reader(retirement.REPOSITORY, 705)
            with self.assertRaises(retirement.RetirementError):
                retirement._claim_attempt(document)
            self.assertEqual(fixture.remote_tip(), oid)


if __name__ == "__main__":
    main()
