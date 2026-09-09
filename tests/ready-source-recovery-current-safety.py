# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Closed current-policy assertions against exact historical Ready source."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "scripts"))
from secpal_pr_review import fast_path, lifecycle_authority as authority, lifecycle_publication

REPOSITORY = "example/project"
SIGNER = "fixture@example.invalid"
HEAD = "a" * 40
TREE = "b" * 40


def sign(payload, domain):
    return {
        "format": "ssh", "signer_identity": SIGNER,
        "value": hashlib.sha256(domain.encode() + payload).hexdigest(),
    }


def verify_signature(payload, signature, expected_signer, domain):
    if expected_signer != SIGNER or signature != sign(payload, domain):
        raise ValueError("invalid fixture signature")
    return authority.VerifiedSignature(expected_signer, signature["format"])


class ReadySourceRecoveryCurrentSafety(unittest.TestCase):
    """Assertions derived only from #827's Ready-source recovery boundary."""

    def setUp(self):
        self.registry = {
            "manual_gates": [], "validation": [], "limits": {"maximum_items": 10000},
        }
        actor = {"login": "reviewer", "node_id": "actor", "database_id": 7}

        def comment(identity, reply=None):
            return {
                "node_id": identity,
                "body_digest": hashlib.sha256(identity.encode()).hexdigest(),
                "actor": actor, "reply_to_id": reply, "reactions": [],
            }

        def reaction(identity):
            return {"mutation_id": identity, "content": "THUMBS_UP", "actor": actor}

        reviewed_comment, reply, outdated = comment("comment"), comment("reply", "comment"), comment("old")
        review = {**comment("review"), "state": "COMMENTED", "commit_oid": HEAD}
        conversation = {**comment("conversation"), "updated_at": None}
        pr_reaction, review_reaction, conversation_reaction, thread_reaction = (
            reaction(identity) for identity in (
                "pr-reaction", "review-reaction", "conversation-reaction", "thread-reaction",
            )
        )
        review["reactions"] = [review_reaction]
        conversation["reactions"] = [conversation_reaction]
        reviewed_comment["reactions"] = [thread_reaction]
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY, pull_request_number=17, head_sha=HEAD,
            base_ref="main", base_sha="c" * 40, pr_state="OPEN",
            feedback={
                "pull_request_reactions": [pr_reaction], "reviews": [review],
                "conversation_comments": [conversation],
                "threads": [
                    {"node_id": "thread", "is_resolved": True, "is_outdated": False,
                     "comments": [reviewed_comment, reply]},
                    {"node_id": "outdated", "is_resolved": False, "is_outdated": True,
                     "comments": [outdated]},
                ],
            },
        )
        sources = [
            (kind, item["node_id"], item["body_digest"], thread)
            for kind, item, thread in (
                ("REVIEW", review, None), ("CONVERSATION_COMMENT", conversation, None),
                ("THREAD_COMMENT", reviewed_comment, "thread"),
                ("THREAD_COMMENT", reply, "thread"),
                ("THREAD_COMMENT", outdated, "outdated"),
            )
        ]
        sources += [
            (kind, item["mutation_id"], authority.digest_json(item), thread)
            for kind, item, thread in (
                ("PULL_REQUEST_REACTION", pr_reaction, None),
                ("REVIEW_REACTION", review_reaction, None),
                ("CONVERSATION_REACTION", conversation_reaction, None),
                ("THREAD_COMMENT_REACTION", thread_reaction, "thread"),
            )
        ]
        self.findings = [
            {
                "finding_id": identity, "thread_id": thread,
                "sources": [{"kind": kind, "node_id": identity, "digest": digest}],
                "classification": "INFORMATIONAL", "disposition": "NON_ACTIONABLE",
                "evidence_digest": "e" * 64, "technically_blocking": False,
            }
            for kind, identity, digest, thread in sources
        ]
        self.receipt = fast_path.create_validation_receipt(
            repository=REPOSITORY, head_sha=HEAD, validated_tree_sha=TREE,
            registry=self.registry, command_set=[], successful_result=True,
            reviewed_state=self.reviewed, manual_gate_evidence=[],
        )
        state = authority.initial_state()
        state.update(
            unrestricted_review_count=1, remediation_cycle_count=2,
            draft=False, ready=True, ready_transition_count=1,
            ready_history=[{"sequence": 1, "transition_kind": "DRAFT_TO_READY",
                            "observation_digest": "f" * 64}],
        )
        self.current = authority.VerifiedLifecycleAuthority(
            authority_digest="1" * 64, repository=REPOSITORY, delivery_issue=16,
            lifecycle_id="fixture-lifecycle", initialization_evidence_digest="2" * 64,
            pull_request=17, head_sha=HEAD, state=state,
            authority_signer_identity=SIGNER,
            historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
        )
        trust = authority.LifecycleTrustPolicy(
            repository=REPOSITORY, accepted_formats=frozenset({"ssh"}),
            transition_signer_identities=frozenset({SIGNER}),
            authority_signer_identities=frozenset({SIGNER}),
            signers={SIGNER: authority.TrustedSigner(SIGNER, ("fixture-key",), ())},
            initialization_anchors=(),
        )
        for name, value in (
            ("_load_lifecycle_trust_policy", trust),
            ("_policy_signature_verifier", verify_signature),
            ("_load_delivery_signature_policy",
             {"accepted_formats": ["ssh"], "require_github_verified": True}),
        ):
            patcher = patch.object(authority, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def safety(self, **changes):
        fields = dict(
            tooling_authority_main="9" * 40, repository=REPOSITORY,
            pull_request_number=17, head_sha=HEAD, tree_sha=TREE,
            parent_shas=["8" * 40], expected_base_ref="main", expected_base_sha="c" * 40,
            reviewed_state=self.reviewed, review_decision="APPROVED",
            feedback_findings=self.findings, fresh_validation_receipt=self.receipt,
            registry=self.registry, command_set=[],
        )
        fields.update(changes)
        return fast_path.derive_ready_source_recovery_safety_facts(**fields)

    def authorization(self):
        return authority._sign_ready_source_recovery_authorization(
            current_lifecycle=self.current, current_publication_oid="3" * 40,
            current_publication_digest="4" * 64, recovery_safety_facts=self.safety(),
            commit_signature_evidence={
                "oid": HEAD, "source": "USER", "signer_identity": SIGNER,
                "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
                "github_verification": {"verified": True, "reason": "valid"},
            },
            historical_validation_receipt_digest="5" * 64,
            historical_final_attestation_digest="6" * 64,
            historical_evidence_loss_proof_digest="7" * 64,
            authorization_id="fixture-recovery", bounded_uses=1,
            expected_commit_signer={"kind": "SSH_PRINCIPAL", "identity": SIGNER},
            signer_identity=SIGNER, signer=sign,
        )

    def verify(self, document):
        return authority.verify_ready_source_recovery_authorization(
            document, current_lifecycle=self.current,
            current_publication_oid="3" * 40, current_publication_digest="4" * 64,
        )

    def test_historical_bytes_unavailable(self):
        document = self.authorization()
        self.verify(document)
        self.assertEqual(
            document["historical_evidence_status"],
            "PROVEN_PRE_PERSISTENCE_PACKAGE_UNAVAILABLE",
        )
        self.assertIs(document["historical_bytes_reconstructed"], False)

    def test_signed_authority_required(self):
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.verify(self.safety())
        document = self.authorization()
        del document["signature"]
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.verify(document)

    def test_complete_feedback(self):
        self.safety()
        with self.assertRaises(fast_path.SecurityBlocker):
            self.safety(feedback_findings=self.findings[:-1])

    def test_resolved_feedback(self):
        self.assertTrue(next(
            item for item in self.reviewed.feedback["threads"]
            if item["node_id"] == "thread"
        )["is_resolved"])
        with self.assertRaises(fast_path.SecurityBlocker):
            self.safety(feedback_findings=[])

    def test_context_binding(self):
        document = self.authorization()
        self.verify(document)
        for field, value in (
            ("repository", "other/project"), ("pull_request", 19),
            ("head_sha", "e" * 40), ("tree_sha", "e" * 40), ("bounded_uses", 2),
        ):
            changed = copy.deepcopy(document)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(authority.LifecycleAuthorityError):
                self.verify(changed)

    def test_wrong_signer(self):
        document = self.authorization()
        document["signer_identity"] = "wrong@example.invalid"
        with self.assertRaises(authority.LifecycleAuthorityError):
            self.verify(document)

    def test_source_history(self):
        authority._ready_source_recovery_state(
            self.current.state, historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
        )
        for key, value in (
            ("cycle_3_absent", False), ("remediation_cycle_count", 3),
            ("unrestricted_review_count", 0), ("ready", False), ("draft", True),
        ):
            with self.subTest(key=key), self.assertRaises(authority.LifecycleAuthorityError):
                authority._ready_source_recovery_state(
                    {**self.current.state, key: value},
                    historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
                )

    def test_candidate_local_issuer_rejected(self):
        spec = importlib.util.spec_from_file_location(
            "ready_source_current_safety_actions", ROOT / "scripts/secpal-pr-review-actions.py",
        )
        actions = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = actions
        spec.loader.exec_module(actions)
        parameters = inspect.signature(actions.issue_ready_source_recovery_authorization).parameters
        for forbidden in (
            "registry", "command_set", "safety_facts", "current_lifecycle",
            "_validation_runner", "_issuer_source_verifier",
        ):
            self.assertNotIn(forbidden, parameters)
        with patch.object(actions, "_attestation_local_state", return_value=(HEAD, "")):
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                actions._verify_recovery_issuer_source("f" * 40)

    def test_ordinary_prior_ready(self):
        prior = {
            "schema_version": "1.1", "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
            "repository": REPOSITORY, "delivery_issue_number": 16,
            "pull_request_number": 17, "prior_delivery_head_sha": HEAD,
            "prior_delivery_tree_sha": TREE, "prior_validation_receipt_digest": "5" * 64,
            "prior_final_attestation_digest": "6" * 64,
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
            "lifecycle": {
                "identity": "fixture-lifecycle", "current_authority_digest": "1" * 64,
                "historical_proof_mode": authority.EXACT_ADOPTION_PROOF_MODE,
                "draft": False, "ready": True, "ready_transition": False,
                "unrestricted_reviews": 1, "remediation_cycles": 2,
                "exceptional_recoveries": 0, "exceptional_continuations": 0,
                "cycle_3": False,
            },
            "publication": {"object_oid": "3" * 40, "publication_digest": "4" * 64},
        }
        self.assertEqual(fast_path.normalize_ready_integration_prior_authority(prior), prior)


def main(arguments):
    if arguments:
        raise RuntimeError("Ready-source current safety accepts no caller selection")
    names = unittest.defaultTestLoader.getTestCaseNames(ReadySourceRecoveryCurrentSafety)
    suite = unittest.TestSuite(ReadySourceRecoveryCurrentSafety(name) for name in names)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output).run(suite)
    if not result.wasSuccessful() or result.skipped or result.testsRun != len(names):
        sys.stderr.write(output.getvalue())
        failed = sorted({
            getattr(test, "test_case", test)._testMethodName.removeprefix("test_")
            for test, _ in [*result.failures, *result.errors, *result.skipped]
        })
        print(json.dumps(failed))
        return 1
    print(json.dumps([name.removeprefix("test_") for name in names]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
