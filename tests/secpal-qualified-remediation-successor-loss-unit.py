# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression coverage for the exact #956/#957 remediation evidence loss."""

from __future__ import annotations

import copy
import json
import unittest

from scripts.secpal_pr_review import qualified_remediation_successor_loss as loss


class QualifiedRemediationSuccessorLossTests(unittest.TestCase):
    def test_accepted_registry_registers_the_exact_admission(self) -> None:
        record = loss.load_accepted_admission("SecPal/.github", 956)
        registry = json.loads(
            (
                loss.ROOT
                / ".agents/skills/secpal-pr-review/references/repositories.json"
            ).read_text(encoding="utf-8")
        )
        entry = next(
            item for item in registry["repositories"]
            if item["repository"] == record["repository"]
        )

        self.assertEqual(
            entry["qualified_remediation_successor_evidence_loss_policy"],
            {
                "path": record["policy_path"],
                "admission_digest": record["admission_digest"],
            },
        )

    def test_exact_admission_binds_only_the_classified_successor(self) -> None:
        record = loss.load_accepted_admission("SecPal/.github", 956)

        self.assertEqual(record["pull_request"], 957)
        self.assertEqual(
            record["successor"]["ordered_parent_shas"],
            [
                "fd6e9ff07552cdbbd15373131a073d6bb5357936",
                "14c5bcf19eaa9e144af5e9afa05f12f2c08648dc",
            ],
        )
        self.assertEqual(len(record["stable_thread_inventory"]), 12)
        self.assertEqual(record["current_material_finding_ids"], [])
        self.assertIsNone(record["historical_integration_evidence_digest"])
        self.assertIsNone(record["historical_validation_receipt_digest"])
        self.assertFalse(record["historical_bytes_reconstructed"])

        for label, mutate in (
            (
                "predecessor",
                lambda value: value["predecessor"].update(
                    publication_oid="a" * 40
                ),
            ),
            (
                "parent order",
                lambda value: value["successor"]["ordered_parent_shas"].reverse(),
            ),
            (
                "qualification",
                lambda value: value["qualification"].update(id="other"),
            ),
            (
                "thread inventory",
                lambda value: value["stable_thread_inventory"].pop(),
            ),
            (
                "fabricated receipt",
                lambda value: value.update(
                    historical_validation_receipt_digest="1" * 64
                ),
            ),
            (
                "cycle reset",
                lambda value: value["resulting_state"].update(
                    remediation_cycle_count=1
                ),
            ),
        ):
            with self.subTest(label=label):
                changed = copy.deepcopy(record)
                mutate(changed)
                with self.assertRaises(loss.QualifiedRemediationSuccessorLossError):
                    loss.verify_admission(changed)

    def test_safety_binding_requires_exact_threads_and_zero_material_findings(self) -> None:
        record = loss.load_accepted_admission("SecPal/.github", 956)
        safety = {
            "repository": record["repository"],
            "pull_request_number": record["pull_request"],
            "head_sha": record["successor"]["head_sha"],
            "tree_sha": record["successor"]["tree_sha"],
            "parent_shas": record["successor"]["ordered_parent_shas"],
            "expected_base_ref": "main",
            "expected_base_sha": record["successor"]["ordered_parent_shas"][1],
            "reviewed_state": {
                "threads": [
                    {
                        "node_id": item["thread_id"],
                        "is_resolved": item["resolved"],
                        "is_outdated": item["outdated"],
                    }
                    for item in record["stable_thread_inventory"]
                ]
            },
            "reviewed_state_digest": record["qualification"][
                "reviewed_state_digest"
            ],
            "reviewed_feedback_digest": record["qualification"][
                "reviewed_feedback_digest"
            ],
            "feedback_findings": [],
        }
        loss.verify_safety_binding(record, safety)

        safety["reviewed_state"]["threads"].pop()
        with self.assertRaises(loss.QualifiedRemediationSuccessorLossError):
            loss.verify_safety_binding(record, safety)

    def test_provider_binding_rejects_other_identity_or_head(self) -> None:
        record = loss.load_accepted_admission("SecPal/.github", 956)
        binding = loss.provider_binding(record)
        self.assertEqual(
            binding.provider_head(
                repository=record["repository"],
                pull_request=record["pull_request"],
                current_head_sha=record["successor"]["head_sha"],
            ),
            record["qualification"]["provider_summary_head_sha"],
        )
        with self.assertRaises(loss.QualifiedRemediationSuccessorLossError):
            binding.provider_head(
                repository=record["repository"],
                pull_request=record["pull_request"] + 1,
                current_head_sha=record["successor"]["head_sha"],
            )


if __name__ == "__main__":
    unittest.main()
