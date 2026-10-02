# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""One exact late thread write, no generic fallback or retry."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


RESOLVER_PATH = Path(__file__).resolve().parents[1] / "scripts/secpal-resolve-fixed-threads.py"
SPEC = importlib.util.spec_from_file_location("exact_prerequisite_resolver_test", RESOLVER_PATH)
assert SPEC is not None and SPEC.loader is not None
RESOLVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RESOLVER
SPEC.loader.exec_module(RESOLVER)


class ExactResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = RESOLVER.exact_prerequisite.CASES["deployment-281"]
        self.body_digest = hashlib.sha256(
            self.case.comment_body.encode("utf-8")
        ).hexdigest()
        self.thread = RESOLVER.ThreadState(
            self.case.thread_id, False, False,
            (RESOLVER.ThreadCommentState(
                self.case.comment_node, self.case.comment_id,
                self.body_digest, None,
            ),),
        )
        self.target = RESOLVER.TargetRead(
            self.case.repository, self.case.pull_request, "OPEN",
            self.case.head, 1, self.thread,
        )
        self.facts = {"case_id": self.case.case_id, "head": self.case.head}
        self.authorization = RESOLVER.late_disposition.ThreadAuthorization(
            thread_id=self.case.thread_id,
            top_level_comment_node_id=self.case.comment_node,
            top_level_comment_database_id=self.case.comment_id,
            finding_body_digest=self.body_digest,
            reply_state_digest=RESOLVER._reply_state_digest(self.thread)[0],
            reply_count=0,
            is_resolved=False,
            is_outdated=False,
            classification="VALID_ACTIONABLE",
            disposition="CORRECTED_AND_VERIFIED",
            technically_blocking=False,
            classification_evidence_digest="a" * 64,
        )
        self.classification = SimpleNamespace(
            canonical_payload=b"",
            thread=self.authorization,
        )
        self.classification.canonical_payload = (
            RESOLVER.late_disposition.canonical_json_bytes(
                RESOLVER.exact_prerequisite_evidence.classification_payload(
                    self.case, self.target, self.facts
                )
            )
        )
        self.disposition = RESOLVER.late_disposition.LateDispositionEvidence(
            artifact_digest="b" * 64,
            canonical_payload=b"{}",
            delivery_issue_number=self.case.delivery_issue,
            signer=RESOLVER.exact_prerequisite_evidence.expected_signer(),
            threads=(self.authorization,),
        )

    def run_exact(self, *, auth_side_effect=None, response=None):
        authentication = (
            mock.Mock(side_effect=auth_side_effect)
            if auth_side_effect is not None
            else mock.Mock(return_value=self.facts)
        )
        with (
            mock.patch.object(RESOLVER, "read_stable_target_thread",
                              return_value=self.target) as read,
            mock.patch.object(RESOLVER, "_authenticate_exact_prerequisite",
                              authentication),
            mock.patch.object(
                RESOLVER.late_disposition,
                "parse_classification_artifact",
                return_value=self.classification,
            ),
            mock.patch.object(
                RESOLVER.exact_prerequisite_evidence,
                "parse_exact_disposition",
                return_value=self.disposition,
            ),
            mock.patch.object(
                RESOLVER, "_graphql",
                return_value=response if response is not None else {
                    "resolveReviewThread": {
                        "thread": {"id": self.case.thread_id,
                                   "isResolved": True}
                    }
                },
            ) as write,
        ):
            result = RESOLVER.resolve_exact_prerequisite_late_thread(
                self.case.case_id,
                classification_path=Path("/unused/classification"),
                classification_signature_path=Path("/unused/classification.sig"),
                disposition_path=Path("/unused/disposition"),
                disposition_signature_path=Path("/unused/disposition.sig"),
                apply=True,
            )
        return result, read.call_count, authentication.call_count, write.call_count

    def test_exact_proven_thread_is_mutated_once(self) -> None:
        result, reads, proofs, writes = self.run_exact()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resolved"], [self.case.thread_id])
        self.assertEqual((reads, proofs, writes), (3, 3, 1))
        self.assertEqual(result["lifecycle_consumption"]["delivery_commits"], 0)

    def test_prerequisite_drift_prevents_write(self) -> None:
        with self.assertRaises(RESOLVER.ResolutionError):
            self.run_exact(auth_side_effect=[self.facts, {"case_id": "changed"}])

    def test_uncertain_write_is_not_retried(self) -> None:
        result, _reads, _proofs, writes = self.run_exact(response={})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"][0]["write_result"], "unknown")
        self.assertEqual(writes, 1)

    def test_unregistered_case_has_no_write(self) -> None:
        with self.assertRaises(RESOLVER.ResolutionError):
            RESOLVER.resolve_exact_prerequisite_late_thread(
                "unrelated-999",
                classification_path=Path("/unused/a"),
                classification_signature_path=Path("/unused/b"),
                disposition_path=Path("/unused/c"),
                disposition_signature_path=Path("/unused/d"),
                apply=True,
            )


if __name__ == "__main__":
    unittest.main()
