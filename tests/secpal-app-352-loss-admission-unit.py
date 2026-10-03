# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin the exact parked secpal.app admission and its current-safety profile."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.secpal_pr_review import validation_evidence_loss as loss


ROOT = Path(__file__).resolve().parents[1]


class SecpalApp352AdmissionTests(unittest.TestCase):
    @staticmethod
    def record() -> dict:
        policy = json.loads((ROOT / loss.POLICY_PATH).read_text(encoding="utf-8"))
        records = [
            item for item in policy["admissions"]
            if (item.get("repository"), item.get("delivery_issue"))
            == ("SecPal/secpal.app", 352)
        ]
        if len(records) != 1:
            raise AssertionError("exact #352 admission must be unique")
        return records[0]

    def test_profile_is_exact_and_uses_600_second_budget(self) -> None:
        record = self.record()
        with patch.object(loss.exact_source_safety, "build_profile", return_value={}) as build:
            profile = loss._current_safety_profile_for_record("a" * 40, record)
        self.assertEqual(build.call_args.kwargs["harness_paths"],
                         (loss.SECPAL_APP_352_CURRENT_SAFETY_PATH,))
        self.assertEqual(build.call_args.kwargs["timeout_seconds"], 600)
        self.assertEqual(profile["registered_candidate_validation"],
                         record["registered_validation_projection"])

    def test_exact_record_preserves_missing_historical_bytes(self) -> None:
        record = self.record()
        self.assertEqual(record["pull_request"], 353)
        self.assertEqual(record["admission_schema_version"], "1.2")
        self.assertEqual(record["historical_package_status"], "UNAVAILABLE")
        self.assertIsNone(record["historical_final_attestation_digest"])
        self.assertIs(record["historical_bytes_reconstructed"], False)
        self.assertNotIn("historical_validation_receipt_digest", record)
        self.assertEqual(record["intended_state"]["unrestricted_review_count"], 1)
        self.assertEqual(record["intended_state"]["remediation_cycle_count"], 2)
        self.assertEqual(record["intended_state"]["ready_transition_count"], 1)
        self.assertEqual(record["current_safety_harness_path"],
                         loss.SECPAL_APP_352_CURRENT_SAFETY_PATH)
        self.assertEqual(tuple(item["path"] for item in
                               record["registered_validation_projection"]["files"]),
                         loss.SECPAL_APP_352_REGISTERED_VALIDATION_PATHS)

    def test_scope_and_projected_test_drift_reject(self) -> None:
        record = self.record()
        for field, value in (
            ("repository", "Other/app"),
            ("delivery_issue", 351),
            ("pull_request", 354),
            ("current_safety_harness_path", "tests/candidate.py"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(record)
                changed[field] = value
                with patch.object(loss.exact_source_safety, "build_profile", return_value={}):
                    with self.assertRaises(loss.authority.LifecycleAuthorityError):
                        loss._current_safety_profile_for_record("a" * 40, changed)
        changed = copy.deepcopy(record)
        changed["registered_validation_projection"]["files"][0]["path"] = (
            "tests/candidate-selected.mjs"
        )
        with patch.object(loss.exact_source_safety, "build_profile", return_value={}):
            with self.assertRaises(loss.authority.LifecycleAuthorityError):
                loss._zero_receipt_current_safety_profile("a" * 40, changed)

    def test_harness_runs_registered_commands_and_rejects_failure(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "secpal_app_352_safety", ROOT / loss.SECPAL_APP_352_CURRENT_SAFETY_PATH
        )
        assert spec is not None and spec.loader is not None
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".nvmrc", ".npmrc", "CHANGELOG.md"):
                (root / name).write_text("26\n" if name == ".nvmrc" else
                                         "engine-strict=true\n")
            (root / "package.json").write_text('{"engines":{"node":"^26.10.0"}}')
            (root / "package-lock.json").write_text("{}")
            (root / "tests").mkdir()
            (root / "tests/workflow-action-pins.test.mjs").write_text("test")
            seen = []

            def run(command, **_kwargs):
                seen.append(tuple(command))
                return SimpleNamespace(returncode=0)

            with patch.object(harness.Path, "cwd", return_value=root), patch.object(
                harness.subprocess, "run", side_effect=run
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(harness.main([]), 0)
            self.assertEqual(seen[2:], list(harness.COMMANDS))

            def fail(command, **_kwargs):
                return SimpleNamespace(returncode=1 if tuple(command) == harness.COMMANDS[3] else 0)

            with patch.object(harness.Path, "cwd", return_value=root), patch.object(
                harness.subprocess, "run", side_effect=fail
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(harness.main([]), 1)


if __name__ == "__main__":
    unittest.main()
