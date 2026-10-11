# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact protected authority for deployment #119 / PR #250."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.secpal_actions_fixture import load_actions
actions_owner = load_actions()

from scripts.secpal_pr_review import validation_evidence_loss as loss


ROOT = Path(__file__).resolve().parents[1]
HEAD = "be8d579f2ad96d8e94599c818de37e53fb3b2b3f"
TREE = "bbb1cd0bfe0a7286bdf75a2bfeb80d5815a2b2b6"
PARENT = "7e7a6e316007de919166c2d296e6918cfd353063"


class Deployment119AdmissionTests(unittest.TestCase):
    def test_workload_schema_cannot_claim_pg16_or_production(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "deployment_119_safety",
            ROOT / "tests/pre-enrollment-deployment-119-current-safety.py",
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        schema = {
            "$defs": {
                "workloadEvidence": {
                    "additionalProperties": False,
                    "required": ["claim_scope", "database_scope"],
                    "properties": {
                        "claim_scope": {
                            "const": "disposable-rootless-application-integration"
                        },
                        "database_scope": {
                            "const": "disposable-postgresql-18-fixture"
                        },
                    },
                },
            },
        }
        self.assertTrue(harness._closed_scope_schema(schema))
        for field, value in (
            ("claim_scope", "production-application"),
            ("database_scope", "production-postgresql-16-container"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(schema)
                changed["$defs"]["workloadEvidence"]["properties"][field][
                    "const"
                ] = value
                self.assertFalse(harness._closed_scope_schema(changed))
        changed = copy.deepcopy(schema)
        changed["$defs"]["workloadEvidence"]["additionalProperties"] = True
        self.assertFalse(harness._closed_scope_schema(changed))

    @staticmethod
    def record() -> dict:
        policy = json.loads((ROOT / loss.POLICY_PATH).read_text(encoding="utf-8"))
        matches = [
            item for item in policy["admissions"]
            if item.get("repository") == "SecPal/deployment"
            and item.get("delivery_issue") == 119
        ]
        if len(matches) != 1:
            raise AssertionError("no unique exact accepted #119 authority")
        return matches[0]

    def test_zero_receipt_profile_selects_only_protected_workload_harness(self) -> None:
        record = {
            "admission_schema_version": "1.2",
            "repository": "SecPal/deployment",
            "delivery_issue": 119,
            "pull_request": 250,
            "head_sha": HEAD,
            "tree_sha": TREE,
            "current_safety_harness_path": (
                "tests/pre-enrollment-deployment-119-current-safety.py"
            ),
        }
        with patch.object(loss.exact_source_safety, "build_profile") as build:
            loss._current_safety_profile_for_record("a" * 40, record)
        self.assertEqual(
            build.call_args.kwargs["harness_paths"],
            (record["current_safety_harness_path"],),
        )

    def test_exact_zero_receipt_record_has_workload_safety_authority(self) -> None:
        policy = json.loads(
            (ROOT / loss.POLICY_PATH).read_text(encoding="utf-8")
        )
        records = [
            item for item in policy["admissions"]
            if item.get("repository") == "SecPal/deployment"
            and item.get("delivery_issue") == 119
        ]
        self.assertEqual(len(records), 1, "no exact accepted #119 authority")
        record = records[0]
        self.assertEqual(record["pull_request"], 250)
        self.assertEqual(record["admission_schema_version"], "1.2")
        self.assertEqual(record["head_sha"], HEAD)
        self.assertEqual(record["tree_sha"], TREE)
        self.assertEqual(record["parent_sha"], PARENT)
        self.assertNotIn("historical_validation_receipt_digest", record)
        self.assertEqual(record["historical_package_status"], "UNAVAILABLE")
        self.assertIsNone(record["historical_final_attestation_digest"])
        self.assertIs(record["historical_bytes_reconstructed"], False)
        self.assertNotEqual(
            record["current_safety_harness_path"],
            loss.REGISTERED_CURRENT_SAFETY_PATH,
            "production-host safety cannot certify #119 workload",
        )
        self.assertNotEqual(
            record["current_safety_harness_path"],
            loss.NO_RECEIPT_CURRENT_SAFETY_PATH,
            "#711 scanner safety cannot certify #119 workload",
        )
        self.assertTrue(
            (ROOT / record["current_safety_harness_path"]).is_file()
        )
        self.assertEqual(record["intended_state"]["unrestricted_review_count"], 1)
        self.assertEqual(record["intended_state"]["remediation_cycle_count"], 1)
        self.assertEqual(record["intended_state"]["ready_transition_count"], 1)
        self.assertTrue(record["intended_state"]["cycle_3_absent"])
        self.assertEqual(
            [item["kind"] for item in record["observed_pre_enrollment_history"]],
            ["PR_CREATED_DRAFT", "DRAFT_TO_READY_OBSERVED",
             "REMEDIATION_HEAD_OBSERVED"],
        )
        loss.authority._normalize_observed_pre_enrollment_history(
            record["observed_pre_enrollment_history"],
            expected_head=HEAD,
            intended_state=record["intended_state"],
            review_budget_consumption_admitted=True,
        )
        self.assertEqual(len(loss._decisions(record["technical_decisions"])), 7)
        self.assertEqual(
            sum(item["disposition"] == "CORRECTED_AND_VERIFIED"
                for item in record["technical_decisions"]),
            4,
        )

    def test_cross_delivery_or_candidate_harness_selection_fails_closed(self) -> None:
        record = self.record()
        changes = (
            ("repository", "Other/deployment"),
            ("delivery_issue", 118),
            ("pull_request", 249),
            ("current_safety_harness_path", "tests/candidate-safety.py"),
        )
        for field, value in changes:
            with self.subTest(field=field):
                changed = copy.deepcopy(record)
                changed[field] = value
                with patch.object(loss.exact_source_safety, "build_profile"):
                    with self.assertRaises(loss.authority.LifecycleAuthorityError):
                        loss._current_safety_profile_for_record("a" * 40, changed)

    def test_projection_rejects_wrong_source_and_unregistered_test(self) -> None:
        record = self.record()
        for field, value in (
            ("head_sha", "a" * 40),
            ("tree_sha", "b" * 40),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(record)
                changed["registered_validation_projection"][field] = value
                with patch.object(loss.exact_source_safety, "build_profile", return_value={}):
                    with self.assertRaises(loss.authority.LifecycleAuthorityError):
                        loss._zero_receipt_current_safety_profile("a" * 40, changed)
        changed = copy.deepcopy(record)
        changed["registered_validation_projection"]["files"][0]["path"] = (
            "tests/candidate-selected.py"
        )
        with patch.object(loss.exact_source_safety, "build_profile", return_value={}):
            with self.assertRaises(loss.authority.LifecycleAuthorityError):
                loss._zero_receipt_current_safety_profile("a" * 40, changed)


if __name__ == "__main__":
    unittest.main()
