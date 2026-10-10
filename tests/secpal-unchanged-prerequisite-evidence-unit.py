# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Exact detached late-disposition shape and signer regressions."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from tests.secpal_actions_fixture import load_actions
actions_owner = load_actions()

from scripts.secpal_pr_review import late_disposition
from scripts.secpal_pr_review import unchanged_head_prerequisite as prerequisite
from scripts.secpal_pr_review import unchanged_head_prerequisite_evidence as evidence


class ExactEvidenceTests(TestCase):
    def setUp(self) -> None:
        self.case = prerequisite.CASES["deployment-281"]
        self.facts = {"case_id": self.case.case_id, "head": self.case.head}
        self.classification = SimpleNamespace(
            repository=self.case.repository,
            delivery_issue_number=self.case.delivery_issue,
            pull_request_number=self.case.pull_request,
            head_sha=self.case.head,
            signer=evidence.expected_signer(),
            finding_id=evidence.FINDING_PREFIX + self.case.case_id,
            finding_evidence_digest=evidence.facts_digest(self.facts),
            evidence_digest="a" * 64,
            thread=late_disposition.ThreadAuthorization(
                thread_id=self.case.thread_id,
                top_level_comment_node_id=self.case.comment_node,
                top_level_comment_database_id=self.case.comment_id,
                finding_body_digest="b" * 64,
                reply_state_digest="c" * 64,
                reply_count=0,
                is_resolved=False,
                is_outdated=False,
                classification="VALID_ACTIONABLE",
                disposition="CORRECTED_AND_VERIFIED",
                technically_blocking=False,
                classification_evidence_digest="a" * 64,
            ),
        )

    def parse(self, payload):
        canonical = late_disposition.canonical_json_bytes(payload)
        with mock.patch.object(
            late_disposition, "verify_detached_signature", return_value=canonical
        ) as verifier:
            result = evidence.parse_exact_disposition(
                Path("/unused/artifact"), Path("/unused/signature"),
                case=self.case, facts=self.facts,
                classification=self.classification,
            )
        self.assertEqual(
            verifier.call_args.args[2],
            evidence.expected_signer(),
        )
        return result

    def test_exact_shape_reuses_signed_late_disposition(self) -> None:
        payload = evidence.disposition_payload(
            self.case, self.facts, self.classification
        )
        result = self.parse(payload)
        self.assertEqual(payload["schema_version"], "1.8")
        self.assertEqual(payload["authorized_action"], "RESOLVE_EXACT_REVIEW_THREADS")
        self.assertEqual(result.threads, (self.classification.thread,))
        self.assertNotIn("validation_receipt_digest", payload)
        self.assertNotIn("validation_attestation_digest", payload)

    def test_extra_authority_field_rejects(self) -> None:
        payload = evidence.disposition_payload(
            self.case, self.facts, self.classification
        )
        payload["merge_authority"] = True
        with self.assertRaises(late_disposition.LateDispositionError):
            self.parse(payload)

    def test_different_source_digest_rejects(self) -> None:
        payload = evidence.disposition_payload(
            self.case, self.facts, self.classification
        )
        payload["external_prerequisite_evidence_digest"] = "f" * 64
        with self.assertRaises(late_disposition.LateDispositionError):
            self.parse(payload)

    def test_wrong_thread_rejects_before_artifact_creation(self) -> None:
        self.classification.thread = SimpleNamespace(thread_id="PRRT_OTHER")
        with self.assertRaises(prerequisite.PrerequisiteError):
            evidence.disposition_payload(
                self.case, self.facts, self.classification
            )

    def test_wrong_signer_rejects_before_artifact_creation(self) -> None:
        self.classification.signer = late_disposition.SignerIdentity(
            "ssh", "SHA256:other"
        )
        with self.assertRaises(prerequisite.PrerequisiteError):
            evidence.disposition_payload(
                self.case, self.facts, self.classification
            )


if __name__ == "__main__":
    main()
