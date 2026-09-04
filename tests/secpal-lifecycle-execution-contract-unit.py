#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for authenticated Ready/Draft execution.

The cases map the issue #810 evidence plan as follows:
1-9 execution/order/convergence and both ambiguity boundaries; 10-17 stale,
substituted, reverse-partial, and replay authority; 18-20 Ready/Draft history;
21-23 authority-kind separation; 24-27 cross-context replay; 28-31 signer,
schema, transition, and duplicate publication; 32 and 38 structural bounds;
33-37 are exercised by the unchanged registered lifecycle, review-authority,
and Ready-integration suites in addition to the focused characterization here.
"""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import inspect
from pathlib import Path
import sys
from typing import Any
from unittest import TestCase, main, mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import lifecycle_execution as execution
from scripts.secpal_pr_review import lifecycle_orchestration as orchestration
from scripts.secpal_pr_review import lifecycle_publication as publication


REPOSITORY = "SecPal/.github"
ISSUE = 810
PR = 811
HEAD = "a" * 40
SIGNER = "aroviqen@secpal.app"
BRANCH = "refs/heads/secpal-lifecycle-publications"
SECRET = b"lifecycle-execution-fixture"


def signer_for(identity: str = SIGNER) -> authority.Signer:
    def sign(payload: bytes, domain: str) -> dict[str, str]:
        value = hashlib.sha256(
            SECRET + identity.encode() + domain.encode() + payload
        ).hexdigest()
        return {"format": "ssh", "signer_identity": identity, "value": value}

    return sign


def verify_signature(
    payload: bytes,
    signature: dict[str, Any],
    expected_signer: str,
    domain: str,
) -> authority.VerifiedSignature:
    expected = signer_for(expected_signer)(payload, domain)
    if signature != expected:
        raise ValueError("invalid fixture signature")
    return authority.VerifiedSignature(expected_signer, signature["format"])


def policy_for(signers: frozenset[str] = frozenset({SIGNER})) -> authority.LifecycleTrustPolicy:
    trusted = {
        identity: authority.TrustedSigner(identity, ("ssh-ed25519 AAAA",), ())
        for identity in signers
    }
    return authority.LifecycleTrustPolicy(
        repository=REPOSITORY,
        accepted_formats=frozenset({"ssh"}),
        transition_signer_identities=signers,
        authority_signer_identities=frozenset({SIGNER}),
        signers=trusted,
        initialization_anchors=(),
        publication_signer_identities=frozenset({SIGNER}),
        publication_branch=BRANCH,
        publication_remote_url=f"https://github.com/{REPOSITORY}.git",
        publication_ruleset_id=1,
        publication_required_rules=frozenset({"deletion", "non_fast_forward"}),
    )


class Chain:
    def __init__(self) -> None:
        self.initialization = authority.create_delivery_initialization(
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            pull_request=PR,
            initial_head_sha=HEAD,
            validation_receipt_digest="1" * 64,
            final_attestation_digest="2" * 64,
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        self.lifecycle_id = authority.delivery_initialization_lifecycle_id(
            self.initialization["initialization_digest"]
        )
        self.events: list[dict[str, Any]] = []
        self.authorities: list[dict[str, Any]] = []
        self.head = HEAD
        self.append("INITIALIZED_DRAFT")
        self.append("UNRESTRICTED_REVIEW_CONSUMED")

    def append(self, transition: str, *, head: str | None = None) -> None:
        predecessor = self.authorities[-1] if self.authorities else None
        resulting_head = self.head if head is None else head
        event = authority.create_transition_authorization(
            event_id=(
                f"genesis:{self.initialization['initialization_digest']}"
                if predecessor is None
                else f"fixture-event-{len(self.events) + 1}"
            ),
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle_id=self.lifecycle_id,
            pull_request=PR,
            predecessor_authority_digest=(
                None if predecessor is None else predecessor["authority_digest"]
            ),
            predecessor_head_sha=None if predecessor is None else self.head,
            resulting_head_sha=resulting_head,
            transition_kind=transition,
            replacement_pull_request=None,
            initialization_evidence_digest=self.initialization["initialization_digest"],
            signer_identity=SIGNER,
            signer=signer_for(),
        )
        snapshot = authority.issue_lifecycle_authority(
            predecessor_chain=self.authorities,
            transition_authorizations=self.events,
            authorization=event,
            signer_identity=SIGNER,
            authority_signer=signer_for(),
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=verify_signature,
        )
        self.events.append(event)
        self.authorities.append(snapshot)
        self.head = resulting_head

    def raw(self) -> bytes:
        return authority.serialize_lifecycle_evidence(
            delivery_initialization=self.initialization,
            transition_authorizations=self.events,
            authority_chain=self.authorities,
        )

    def verified(self) -> authority.VerifiedLifecycleAuthority:
        return authority._verify_lifecycle_authority_objects(
            self.authorities,
            self.events,
            accepted_event_signers=frozenset({SIGNER}),
            accepted_authority_signers=frozenset({SIGNER}),
            signature_verifier=verify_signature,
        )


def fixture_signing_authorities(*_args: Any) -> execution.SigningAuthorities:
    signer = signer_for()
    return execution.SigningAuthorities(
        SIGNER, signer, SIGNER, signer, SIGNER, signer
    )


class Harness:
    def __init__(self, chain: Chain, *, github_draft: bool | None = None) -> None:
        self.chain = chain
        self.predecessor = publication.VerifiedLifecyclePublication(
            "3" * 40,
            "4" * 64,
            BRANCH,
            "0" * 40,
            None,
            chain.verified(),
            chain.raw(),
        )
        self.current = self.predecessor
        self.target: publication.VerifiedLifecyclePublication | None = None
        self.transition: publication.VerifiedLifecyclePublicationTransition | None = None
        self.github = execution.LivePullRequest(
            REPOSITORY,
            PR,
            "OPEN",
            chain.verified().head_sha,
            chain.verified().state["draft"] if github_draft is None else github_draft,
        )
        self.github_mode = "SUCCESS"
        self.publication_mode = "SUCCESS"
        self.github_writes: list[tuple[str, int, str]] = []
        self.publication_writes: list[bytes] = []
        self.events: list[str] = []
        self.current_reads = 0
        self.github_reads = 0
        self.current_drift_at: dict[int, publication.VerifiedLifecyclePublication] = {}
        self.github_drift_at: dict[int, execution.LivePullRequest] = {}

    def current_reader(self, repository: str, issue: int):
        self.current_reads += 1
        self.events.append("read-current")
        if (repository, issue) != (REPOSITORY, ISSUE):
            raise AssertionError("unexpected CURRENT selector")
        if self.current_reads in self.current_drift_at:
            self.current = self.current_drift_at[self.current_reads]
        return copy.deepcopy(self.current)

    def github_reader(self, repository: str, pull_request: int):
        self.github_reads += 1
        self.events.append("read-github")
        if (repository, pull_request) != (REPOSITORY, PR):
            raise AssertionError("unexpected GitHub selector")
        if self.github_reads in self.github_drift_at:
            self.github = self.github_drift_at[self.github_reads]
        return copy.deepcopy(self.github)

    def github_writer(self, repository: str, pull_request: int, operation: str):
        self.events.append("write-github")
        self.github_writes.append((repository, pull_request, operation))
        if self.github_mode in {"SUCCESS", "AMBIGUOUS_TARGET"}:
            self.github = copy.deepcopy(self.github)
            object.__setattr__(
                self.github, "draft", operation == "READY_TO_DRAFT"
            )
        return "SUCCESS" if self.github_mode == "SUCCESS" else "AMBIGUOUS"

    def _candidate(self, raw: bytes) -> tuple[authority.VerifiedLifecycleAuthority, dict[str, Any]]:
        parsed = authority._load_canonical_json(raw, "fixture successor")
        successor = authority._verify_lifecycle_authority_for_journal(
            raw, admitted_initialization=parsed["delivery_initialization"]
        )
        return successor, parsed["transition_authorizations"][-1]

    def publisher(self, raw: bytes, **_kwargs: Any):
        self.events.append("write-publication")
        self.publication_writes.append(raw)
        successor, event = self._candidate(raw)
        target = publication.VerifiedLifecyclePublication(
            "5" * 40,
            "6" * 64,
            BRANCH,
            self.predecessor.publication_oid,
            self.predecessor.publication_oid,
            successor,
            raw,
        )
        transition = publication.VerifiedLifecyclePublicationTransition(
            predecessor=self.predecessor,
            successor=target,
            event_id=event["event_id"],
            event_digest=event["event_digest"],
            transition_kind=event["transition_kind"],
            event_signer_identity=event["signer_identity"],
            pull_request=event["pull_request"],
            predecessor_authority_digest=event["predecessor_authority_digest"],
            predecessor_head_sha=event["predecessor_head_sha"],
            resulting_head_sha=event["resulting_head_sha"],
            initialization_evidence_digest=event[
                "initialization_evidence_digest"
            ],
        )
        if self.publication_mode in {"SUCCESS", "AMBIGUOUS_TARGET"}:
            self.target = target
            self.transition = transition
            self.current = target
        if self.publication_mode == "SUCCESS":
            return target
        raise publication.LifecyclePublicationError("ambiguous fixture publication")

    def historical_reader(self, repository: str, issue: int, predecessor_oid: str):
        if (repository, issue, predecessor_oid) != (
            REPOSITORY,
            ISSUE,
            self.predecessor.publication_oid,
        ) or self.transition is None:
            raise publication.LifecyclePublicationError("no exact successor")
        return copy.deepcopy(self.transition)

    def execute(self, authorization: bytes) -> execution.LifecycleExecutionResult:
        return execution._execute_lifecycle_transition(
            REPOSITORY,
            ISSUE,
            authorization,
            current_reader=self.current_reader,
            historical_reader=self.historical_reader,
            github_reader=self.github_reader,
            github_writer=self.github_writer,
            publisher=self.publisher,
            signing_authority_provider=fixture_signing_authorities,
        )


def authorization_for(
    harness: Harness,
    operation: str,
    *,
    authorization_id: str | None = None,
    publication_oid: str | None = None,
    publication_digest: str | None = None,
    lifecycle: authority.VerifiedLifecycleAuthority | None = None,
    delivery_issue: int = ISSUE,
    signer_identity: str = SIGNER,
) -> bytes:
    selected = lifecycle or harness.predecessor.lifecycle
    return orchestration.create_user_authorization(
        authorization_id=authorization_id or f"fixture-{operation.lower()}",
        repository=REPOSITORY,
        delivery_issue=delivery_issue,
        lifecycle=selected,
        publication_oid=publication_oid or harness.predecessor.publication_oid,
        publication_digest=publication_digest or harness.predecessor.publication_digest,
        operation=operation,
        reason=f"Authorize exact {operation} fixture",
        scope={"pull_request": selected.pull_request, "head_sha": selected.head_sha},
        signer_identity=signer_identity,
        signer=signer_for(signer_identity),
    )


class LifecycleExecutionTests(TestCase):
    def setUp(self) -> None:
        self.policy = policy_for()
        self.policy_patch = mock.patch.object(
            authority, "_load_lifecycle_trust_policy", return_value=self.policy
        )
        self.verifier_patch = mock.patch.object(
            authority,
            "_policy_signature_verifier",
            return_value=verify_signature,
        )
        self.policy_patch.start()
        self.verifier_patch.start()
        self.addCleanup(self.policy_patch.stop)
        self.addCleanup(self.verifier_patch.stop)

    def draft_harness(self) -> Harness:
        return Harness(Chain())

    def ready_harness(self) -> Harness:
        chain = Chain()
        chain.append("DRAFT_TO_READY")
        return Harness(chain)

    def test_cases_1_2_3_normal_success_orders_and_converges(self) -> None:
        harness = self.draft_harness()
        result = harness.execute(authorization_for(harness, "DRAFT_TO_READY"))
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.observed_case, "NOT_STARTED")
        self.assertEqual((result.github_write_attempts, result.publication_write_attempts), (1, 1))
        self.assertFalse(harness.github.draft)
        self.assertTrue(harness.current.lifecycle.state["ready"])
        self.assertLess(harness.events.index("write-github"), harness.events.index("write-publication"))

    def test_case_4_publication_interruption_resumes_without_github_replay(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")
        harness.github = copy.deepcopy(harness.github)
        object.__setattr__(harness.github, "draft", False)
        first = harness.execute(auth)
        self.assertEqual(first.status, "COMPLETE")
        self.assertEqual(first.github_write_attempts, 0)
        self.assertEqual(len(harness.github_writes), 0)

    def test_signing_failure_after_github_write_resumes_without_github_replay(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")

        with self.assertRaisesRegex(RuntimeError, "signing unavailable"):
            execution._execute_lifecycle_transition(
                REPOSITORY,
                ISSUE,
                auth,
                current_reader=harness.current_reader,
                historical_reader=harness.historical_reader,
                github_reader=harness.github_reader,
                github_writer=harness.github_writer,
                publisher=harness.publisher,
                signing_authority_provider=lambda *_args: (_ for _ in ()).throw(
                    RuntimeError("signing unavailable")
                ),
            )

        self.assertFalse(harness.github.draft)
        self.assertEqual(harness.current, harness.predecessor)
        self.assertEqual(len(harness.github_writes), 1)
        self.assertEqual(len(harness.publication_writes), 0)

        result = harness.execute(auth)

        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(len(harness.github_writes), 1)
        self.assertEqual(len(harness.publication_writes), 1)

    def test_case_5_completed_replay_is_zero_write_idempotent(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")
        harness.execute(auth)
        before_count = harness.current.lifecycle.state["ready_transition_count"]
        second = harness.execute(auth)
        self.assertEqual(second.status, "COMPLETE")
        self.assertEqual((second.github_write_attempts, second.publication_write_attempts), (0, 0))
        self.assertEqual(len(harness.github_writes), 1)
        self.assertEqual(len(harness.publication_writes), 1)
        self.assertEqual(harness.current.lifecycle.state["ready_transition_count"], before_count)

    def test_cases_6_7_ambiguous_github_is_read_back_once_and_never_retried(self) -> None:
        target = self.draft_harness()
        target.github_mode = "AMBIGUOUS_TARGET"
        result = target.execute(authorization_for(target, "DRAFT_TO_READY"))
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(len(target.github_writes), 1)

        predecessor = self.draft_harness()
        predecessor.github_mode = "AMBIGUOUS_PREDECESSOR"
        result = predecessor.execute(authorization_for(predecessor, "DRAFT_TO_READY"))
        self.assertEqual(result.status, "GITHUB_MUTATION_INCOMPLETE")
        self.assertEqual(len(predecessor.github_writes), 1)
        self.assertEqual(len(predecessor.publication_writes), 0)

    def test_cases_8_9_ambiguous_publication_classifies_successor_or_predecessor(self) -> None:
        successor = self.draft_harness()
        successor.github = copy.deepcopy(successor.github)
        object.__setattr__(successor.github, "draft", False)
        successor.publication_mode = "AMBIGUOUS_TARGET"
        result = successor.execute(authorization_for(successor, "DRAFT_TO_READY"))
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(len(successor.publication_writes), 1)

        predecessor = self.draft_harness()
        predecessor.github = copy.deepcopy(predecessor.github)
        object.__setattr__(predecessor.github, "draft", False)
        predecessor.publication_mode = "AMBIGUOUS_PREDECESSOR"
        result = predecessor.execute(authorization_for(predecessor, "DRAFT_TO_READY"))
        self.assertEqual(result.status, "PUBLICATION_PENDING")
        self.assertEqual(len(predecessor.publication_writes), 1)
        self.assertEqual(len(predecessor.github_writes), 0)

    def test_cases_10_14_partial_state_rejects_wrong_or_stale_authority(self) -> None:
        cases = []
        for field in ("publication_oid", "publication_digest"):
            harness = self.draft_harness()
            harness.github = copy.deepcopy(harness.github)
            object.__setattr__(harness.github, "draft", False)
            kwargs = {field: ("9" * 40 if field.endswith("oid") else "9" * 64)}
            cases.append((harness, authorization_for(harness, "DRAFT_TO_READY", **kwargs)))
        for mutation in (
            "head_sha", "pull_request", "lifecycle_id", "authority_digest"
        ):
            harness = self.draft_harness()
            harness.github = copy.deepcopy(harness.github)
            object.__setattr__(harness.github, "draft", False)
            stale = copy.deepcopy(harness.predecessor.lifecycle)
            object.__setattr__(stale, mutation, {
                "head_sha": "b" * 40,
                "pull_request": PR + 1,
                "lifecycle_id": "lifecycle:" + "9" * 64,
                "authority_digest": "9" * 64,
            }[mutation])
            cases.append((harness, authorization_for(harness, "DRAFT_TO_READY", lifecycle=stale)))
        for harness, auth in cases:
            with self.subTest(auth=hashlib.sha256(auth).hexdigest()), self.assertRaises(execution.LifecycleExecutionError):
                harness.execute(auth)
            self.assertEqual((len(harness.github_writes), len(harness.publication_writes)), (0, 0))

    def test_case_15_unsafe_reverse_partial_fails_closed(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")
        harness.github = copy.deepcopy(harness.github)
        object.__setattr__(harness.github, "draft", False)
        harness.execute(auth)
        object.__setattr__(harness.github, "draft", True)
        with self.assertRaisesRegex(execution.LifecycleExecutionError, "unsafe"):
            harness.execute(auth)
        self.assertEqual(len(harness.github_writes), 0)

    def test_cases_16_17_completed_authority_cannot_select_later_or_unrelated_ready(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")
        harness.execute(auth)
        unrelated = copy.deepcopy(harness.current)
        object.__setattr__(unrelated, "publication_oid", "7" * 40)
        harness.current = unrelated
        with self.assertRaises(execution.LifecycleExecutionError):
            harness.execute(auth)

        unrelated_ready = self.ready_harness()
        stale_draft = self.draft_harness()
        unrelated_ready.current = unrelated_ready.predecessor
        unrelated_ready.github = copy.deepcopy(unrelated_ready.github)
        object.__setattr__(unrelated_ready.github, "draft", False)
        with self.assertRaises(execution.LifecycleExecutionError):
            unrelated_ready.execute(authorization_for(stale_draft, "DRAFT_TO_READY"))

    def test_cases_18_19_ready_to_draft_requires_separate_authority_and_preserves_history(self) -> None:
        harness = self.ready_harness()
        before = copy.deepcopy(harness.current.lifecycle.state)
        wrong = authorization_for(harness, "DRAFT_TO_READY")
        with self.assertRaises(execution.LifecycleExecutionError):
            harness.execute(wrong)
        result = harness.execute(authorization_for(harness, "READY_TO_DRAFT"))
        self.assertEqual(result.status, "COMPLETE")
        after = harness.current.lifecycle.state
        self.assertTrue(after["draft"])
        self.assertFalse(after["ready"])
        for field in (
            "unrestricted_review_count", "remediation_cycle_count",
            "ready_transition_count", "exceptional_recovery_count",
            "exceptional_recovery_history", "exceptional_continuation_count",
            "exceptional_continuation_history", "cycle_3_absent",
        ):
            self.assertEqual(after[field], before[field])
        self.assertEqual(len(after["ready_history"]), len(before["ready_history"]) + 1)

    def test_adopted_ready_history_uses_adoption_aware_successor_derivation(self) -> None:
        lifecycle = self.ready_harness().predecessor.lifecycle
        observed = {
            "sequence": 1,
            "kind": "DRAFT_TO_READY_OBSERVED",
            "observed_at": "2026-08-02T00:00:00Z",
            "head_sha": lifecycle.head_sha,
            "reviewed_head_sha": None,
        }
        state = copy.deepcopy(lifecycle.state)
        state["ready_history"] = [
            {
                "sequence": 1,
                "transition_kind": "DRAFT_TO_READY",
                "observation_digest": authority.digest_json(observed),
            }
        ]
        adopted = replace(
            lifecycle,
            state=state,
            historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
        )

        successor = execution._derive_transition_state(
            adopted, "READY_TO_DRAFT", "f" * 64
        )

        self.assertTrue(successor["draft"])
        self.assertFalse(successor["ready"])
        self.assertEqual(successor["ready_history"][:-1], state["ready_history"])

    def test_case_20_later_ready_preserves_exhausted_counters_and_history(self) -> None:
        chain = Chain()
        chain.append("REMEDIATION_COMPLETED", head="b" * 40)
        chain.append("REMEDIATION_COMPLETED", head="c" * 40)
        chain.append("DRAFT_TO_READY")
        chain.append("READY_TO_DRAFT")
        harness = Harness(chain)
        before = copy.deepcopy(harness.current.lifecycle.state)
        harness.execute(authorization_for(harness, "DRAFT_TO_READY"))
        after = harness.current.lifecycle.state
        self.assertEqual(after["remediation_cycle_count"], 2)
        self.assertEqual(after["ready_transition_count"], 2)
        self.assertEqual(after["ready_history"][:-1], before["ready_history"])

    def test_cases_21_23_non_ready_authorities_cannot_invoke_executor(self) -> None:
        for operation in (
            "REVIEW_EVENT_OBSERVED", "CI_OBSERVED", "REMEDIATION_COMPLETED",
            "EXCEPTIONAL_RECOVERY",
        ):
            harness = self.draft_harness()
            with self.subTest(operation=operation), self.assertRaises(execution.LifecycleExecutionError):
                harness.execute(authorization_for(harness, operation))
            self.assertEqual((len(harness.github_writes), len(harness.publication_writes)), (0, 0))

    def test_cases_24_27_cross_context_replay_fails_before_write(self) -> None:
        source = self.draft_harness()
        auth = authorization_for(source, "DRAFT_TO_READY")
        with self.assertRaises(execution.LifecycleExecutionError):
            execution._execute_lifecycle_transition(
                "Other/repo", ISSUE, auth,
                current_reader=source.current_reader,
                historical_reader=source.historical_reader,
                github_reader=source.github_reader,
                github_writer=source.github_writer,
                publisher=source.publisher,
                signing_authority_provider=fixture_signing_authorities,
            )
        for altered_issue in (ISSUE + 1,):
            with self.assertRaises(execution.LifecycleExecutionError):
                execution._execute_lifecycle_transition(
                    REPOSITORY, altered_issue, auth,
                    current_reader=source.current_reader,
                    historical_reader=source.historical_reader,
                    github_reader=source.github_reader,
                    github_writer=source.github_writer,
                    publisher=source.publisher,
                    signing_authority_provider=fixture_signing_authorities,
                )
        for field, value in (("pull_request", PR + 1), ("head_sha", "b" * 40)):
            harness = self.draft_harness()
            stale = copy.deepcopy(harness.predecessor.lifecycle)
            object.__setattr__(stale, field, value)
            with self.assertRaises(execution.LifecycleExecutionError):
                harness.execute(authorization_for(harness, "DRAFT_TO_READY", lifecycle=stale))
        self.assertEqual(len(source.github_writes), 0)

    def test_cases_28_30_wrong_signer_malformed_and_unknown_transition_fail(self) -> None:
        harness = self.draft_harness()
        with self.assertRaises(execution.LifecycleExecutionError):
            harness.execute(authorization_for(harness, "DRAFT_TO_READY", signer_identity="other@secpal.app"))
        for malformed in (b"{}", b'{"unknown":true}', b"not-json"):
            with self.subTest(malformed=malformed), self.assertRaises(execution.LifecycleExecutionError):
                harness.execute(malformed)
        with self.assertRaises(execution.LifecycleExecutionError):
            harness.execute(authorization_for(harness, "UNKNOWN_TRANSITION"))
        self.assertEqual((len(harness.github_writes), len(harness.publication_writes)), (0, 0))

    def test_signed_authorization_and_published_transition_substitution_fail(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")
        parsed = authority.loads_closed_json(auth)
        for field, value in (
            ("reason", "Substituted reason"),
            ("scope", {"pull_request": PR, "head_sha": "b" * 40}),
            ("operation", "READY_TO_DRAFT"),
            ("signer_identity", "other@secpal.app"),
        ):
            changed = copy.deepcopy(parsed)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(execution.LifecycleExecutionError):
                harness.execute(authority.canonical_json_bytes(changed))
        self.assertEqual((len(harness.github_writes), len(harness.publication_writes)), (0, 0))

        harness.execute(auth)
        assert harness.transition is not None
        substituted = copy.deepcopy(harness.transition)
        object.__setattr__(substituted, "transition_kind", "READY_TO_DRAFT")
        harness.transition = substituted
        with self.assertRaises(execution.LifecycleExecutionError):
            harness.execute(auth)
        self.assertEqual(len(harness.publication_writes), 1)

    def test_case_31_duplicate_ready_publication_is_never_attempted(self) -> None:
        harness = self.draft_harness()
        auth = authorization_for(harness, "DRAFT_TO_READY")
        harness.execute(auth)
        harness.execute(auth)
        self.assertEqual(len(harness.publication_writes), 1)

    def test_cases_32_38_executor_has_no_store_second_machine_journal_or_hosted_ci(self) -> None:
        source = inspect.getsource(execution)
        self.assertNotIn("sqlite", source.lower())
        self.assertNotIn("poll", source.lower())
        self.assertNotIn("sleep", source.lower())
        self.assertNotIn("checkrun", source.lower())
        self.assertIs(execution.authority.derive_state, authority.derive_state)
        self.assertIs(
            execution.publication.advance_current_terminal,
            publication.advance_current_terminal,
        )
        self.assertEqual(execution.SUPPORTED_OPERATIONS, {"DRAFT_TO_READY", "READY_TO_DRAFT"})

    def test_classifier_covers_exact_closed_cases_for_both_operations(self) -> None:
        expected = {
            (True, "PREDECESSOR", "DRAFT_TO_READY"): "NOT_STARTED",
            (False, "PREDECESSOR", "DRAFT_TO_READY"): "GITHUB_APPLIED_PUBLICATION_PENDING",
            (False, "TARGET", "DRAFT_TO_READY"): "COMPLETE",
            (True, "TARGET", "DRAFT_TO_READY"): "UNSAFE_REVERSE_PARTIAL",
            (False, "PREDECESSOR", "READY_TO_DRAFT"): "NOT_STARTED",
            (True, "PREDECESSOR", "READY_TO_DRAFT"): "GITHUB_APPLIED_PUBLICATION_PENDING",
            (True, "TARGET", "READY_TO_DRAFT"): "COMPLETE",
            (False, "TARGET", "READY_TO_DRAFT"): "UNSAFE_REVERSE_PARTIAL",
        }
        for arguments, result in expected.items():
            self.assertEqual(
                execution.classify_observed_state(
                    github_draft=arguments[0],
                    current_position=arguments[1],
                    operation=arguments[2],
                ),
                result,
            )
        with self.assertRaises(execution.LifecycleExecutionError):
            execution.classify_observed_state(
                github_draft=True, current_position="OTHER", operation="DRAFT_TO_READY"
            )

    def test_toctou_drift_immediately_before_writes_causes_zero_writes(self) -> None:
        current_drift = self.draft_harness()
        changed = copy.deepcopy(current_drift.predecessor)
        object.__setattr__(changed, "publication_oid", "9" * 40)
        current_drift.current_drift_at[2] = changed
        with self.assertRaises(execution.LifecycleExecutionError):
            current_drift.execute(authorization_for(current_drift, "DRAFT_TO_READY"))
        self.assertEqual(len(current_drift.github_writes), 0)

        github_drift = self.draft_harness()
        github_drift.github_drift_at[2] = execution.LivePullRequest(
            REPOSITORY, PR, "OPEN", "b" * 40, True
        )
        with self.assertRaises(execution.LifecycleExecutionError):
            github_drift.execute(authorization_for(github_drift, "DRAFT_TO_READY"))
        self.assertEqual(len(github_drift.github_writes), 0)

        publication_current_drift = self.draft_harness()
        object.__setattr__(publication_current_drift.github, "draft", False)
        changed = copy.deepcopy(publication_current_drift.predecessor)
        object.__setattr__(changed, "publication_oid", "9" * 40)
        publication_current_drift.current_drift_at[3] = changed
        with self.assertRaises(execution.LifecycleExecutionError):
            publication_current_drift.execute(
                authorization_for(publication_current_drift, "DRAFT_TO_READY")
            )
        self.assertEqual(len(publication_current_drift.publication_writes), 0)

        publication_github_drift = self.draft_harness()
        object.__setattr__(publication_github_drift.github, "draft", False)
        publication_github_drift.github_drift_at[3] = execution.LivePullRequest(
            REPOSITORY, PR, "OPEN", HEAD, True
        )
        with self.assertRaises(execution.LifecycleExecutionError):
            publication_github_drift.execute(
                authorization_for(publication_github_drift, "DRAFT_TO_READY")
            )
        self.assertEqual(len(publication_github_drift.publication_writes), 0)

    def test_command_boundary_is_exact_noninteractive_and_has_no_caller_executable(self) -> None:
        calls = []

        def run(arguments: list[str]):
            calls.append(arguments)
            return type("Result", (), {"returncode": 0})()

        with mock.patch.object(publication, "_run_gh", side_effect=run):
            self.assertEqual(execution._write_live_github(REPOSITORY, PR, "DRAFT_TO_READY"), "SUCCESS")
            self.assertEqual(execution._write_live_github(REPOSITORY, PR, "READY_TO_DRAFT"), "SUCCESS")
        self.assertEqual(calls, [
            ["pr", "ready", str(PR), "--repo", REPOSITORY],
            ["pr", "ready", str(PR), "--repo", REPOSITORY, "--undo"],
        ])
        self.assertEqual(
            list(inspect.signature(execution.execute_lifecycle_transition).parameters),
            ["repository", "delivery_issue", "serialized_authorization"],
        )


if __name__ == "__main__":
    main()
