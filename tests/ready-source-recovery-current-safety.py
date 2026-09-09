# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Closed source-safety assertions for an immutable historical Ready source."""

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


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "scripts"))
from secpal_pr_review import fast_path, lifecycle_authority as authority

REPOSITORY = "example/project"
HEAD = "a" * 40
TREE = "b" * 40
SIGNER = "fixture@example.invalid"


class ReadySourceRecoveryCurrentSafety(unittest.TestCase):
    """Assertions owned by candidate source rather than the current issuer."""

    def setUp(self):
        actor = {"login": "reviewer", "node_id": "actor", "database_id": 7}

        def comment(identity):
            return {
                "node_id": identity,
                "body_digest": hashlib.sha256(identity.encode()).hexdigest(),
                "actor": actor,
                "reply_to_id": None,
                "reactions": [],
            }

        review = {**comment("review"), "state": "COMMENTED", "commit_oid": HEAD}
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=17,
            head_sha=HEAD,
            base_ref="main",
            base_sha="c" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [review],
                "conversation_comments": [
                    {**comment("conversation"), "updated_at": None}
                ],
                "threads": [
                    {
                        "node_id": "resolved-thread",
                        "is_resolved": True,
                        "is_outdated": False,
                        "comments": [comment("resolved-comment")],
                    },
                    {
                        "node_id": "open-thread",
                        "is_resolved": False,
                        "is_outdated": False,
                        "comments": [comment("open-comment")],
                    },
                ],
            },
        )

    def prior_authority(self):
        return {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_PRIOR_AUTHORITY",
            "repository": REPOSITORY,
            "delivery_issue_number": 16,
            "pull_request_number": 17,
            "prior_delivery_head_sha": HEAD,
            "prior_delivery_tree_sha": TREE,
            "prior_validation_receipt_digest": "d" * 64,
            "prior_final_attestation_digest": "e" * 64,
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": SIGNER},
            "lifecycle": {
                "identity": "fixture-lifecycle",
                "current_authority_digest": "f" * 64,
                "historical_proof_mode": authority.NATIVE_PROOF_MODE,
                "draft": False,
                "ready": True,
                "ready_transition": False,
                "unrestricted_reviews": 1,
                "remediation_cycles": 2,
                "exceptional_recoveries": 0,
                "exceptional_continuations": 0,
                "cycle_3": False,
            },
            "publication": {
                "object_oid": "1" * 40,
                "publication_digest": "2" * 64,
            },
        }

    def validate_state(self, state):
        parameters = inspect.signature(authority._validate_state).parameters
        if "allow_adopted_observations" in parameters:
            return authority._validate_state(
                state, allow_adopted_observations=False,
            )
        return authority._validate_state(state)

    def test_ordinary_prior_ready(self):
        prior = self.prior_authority()
        self.assertEqual(
            fast_path.normalize_ready_integration_prior_authority(prior), prior,
        )

    def test_prior_authority_scope(self):
        for path, value in (
            (("delivery_issue_number",), 0),
            (("prior_delivery_head_sha",), "invalid"),
            (("prior_delivery_tree_sha",), "invalid"),
            (("publication", "object_oid"), "invalid"),
            (("lifecycle", "draft"), True),
            (("lifecycle", "ready"), False),
            (("lifecycle", "unrestricted_reviews"), 0),
        ):
            changed = copy.deepcopy(self.prior_authority())
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_prior_authority(changed)
        changed = self.prior_authority()
        changed["caller_selected_safety"] = True
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.normalize_ready_integration_prior_authority(changed)

    def test_prior_authority_signer(self):
        for signer in (
            {"kind": "CALLER", "identity": SIGNER},
            {"kind": "OPENPGP_FINGERPRINT", "identity": "invalid"},
            {"kind": "SSH_PRINCIPAL", "identity": ""},
        ):
            changed = self.prior_authority()
            changed["expected_signer"] = signer
            with self.subTest(signer=signer), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_ready_integration_prior_authority(changed)

    def test_lifecycle_history(self):
        state = authority.initial_state()
        event = {
            "sequence": 1,
            "transition_kind": "DRAFT_TO_READY",
            "event_authorization_digest": "3" * 64,
        }
        state.update(
            unrestricted_review_count=1,
            remediation_cycle_count=2,
            draft=False,
            ready=True,
            ready_transition_count=1,
            ready_history=[event],
        )
        self.assertEqual(self.validate_state(state), state)
        for key, value in (
            ("cycle_3_absent", False),
            ("unrestricted_review_count", 2),
            ("remediation_cycle_count", 3),
            ("ready_transition_count", 0),
            ("exceptional_recovery_count", 2),
            ("exceptional_continuation_count", 2),
        ):
            with self.subTest(key=key), self.assertRaises(
                authority.LifecycleAuthorityError
            ):
                self.validate_state({**state, key: value})

    def test_stable_feedback_integrity(self):
        restored = fast_path.StableFeedbackState.from_payload(
            self.reviewed.to_dict()
        )
        self.assertEqual(restored.state_digest, self.reviewed.state_digest)
        self.assertTrue(any(
            thread["is_resolved"] for thread in restored.feedback["threads"]
        ))
        duplicate = self.reviewed.to_dict()
        duplicate["reviews"].append(copy.deepcopy(duplicate["reviews"][0]))
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.StableFeedbackState.from_payload(duplicate)
        for field, value in (("head_sha", "invalid"), ("base_sha", "invalid")):
            changed = self.reviewed.to_dict()
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.StableFeedbackState.from_payload(changed)

    def test_candidate_issuer_separation(self):
        spec = importlib.util.spec_from_file_location(
            "ready_source_candidate_actions",
            ROOT / "scripts/secpal-pr-review-actions.py",
        )
        if spec is None or spec.loader is None:
            self.fail("candidate actions module has no executable loader")
        actions = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = actions
        spec.loader.exec_module(actions)
        issuer = getattr(actions, "issue_ready_source_recovery_authorization", None)
        if issuer is None:
            self.assertFalse(
                hasattr(actions, "_run_ready_source_recovery_current_safety")
            )
            return
        parameters = inspect.signature(issuer).parameters
        for forbidden in (
            "registry", "command_set", "safety_facts", "current_lifecycle",
            "_validation_runner", "_issuer_source_verifier",
        ):
            self.assertNotIn(forbidden, parameters)


def main(arguments):
    if arguments:
        raise RuntimeError("Ready-source current safety accepts no caller selection")
    names = unittest.defaultTestLoader.getTestCaseNames(
        ReadySourceRecoveryCurrentSafety
    )
    suite = unittest.TestSuite(
        ReadySourceRecoveryCurrentSafety(name) for name in names
    )
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output).run(suite)
    if not result.wasSuccessful() or result.skipped or result.testsRun != len(names):
        sys.stderr.write(output.getvalue())
        failed = sorted({
            getattr(test, "test_case", test)._testMethodName.removeprefix("test_")
            for test, _ in [
                *result.failures, *result.errors, *result.skipped,
            ]
        })
        print(json.dumps(failed))
        return 1
    print(json.dumps([name.removeprefix("test_") for name in names]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
