# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact contracts Ready admission, provider binding and safety selection."""

from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests.secpal_actions_fixture import load_actions
actions_owner = load_actions()

from scripts.secpal_pr_review import validation_evidence_loss as loss


ROOT = Path(__file__).resolve().parents[1]
H0 = "5fefdc0d8ed92779bdb74a8efa39baba8fdf331e"
H1 = "f8e229ef68630e4e8363fb1af4137a53a55a304a"
HARNESS = "tests/pre-enrollment-contracts-524-current-safety.py"


class Contracts524AdmissionTests(unittest.TestCase):
    @staticmethod
    def record() -> dict:
        policy = json.loads((ROOT / loss.POLICY_PATH).read_text())
        records = [item for item in policy["admissions"]
                   if (item.get("repository"), item.get("delivery_issue"))
                   == ("SecPal/contracts", 524)]
        if len(records) != 1:
            raise AssertionError("contracts #524 needs one exact admission")
        return records[0]

    def binding(self, summary_digest=None):
        record = self.record()
        if summary_digest is not None:
            record["historical_provider_summary_digest"] = summary_digest
        commits = (
            loss.CommitFacts(H0, "ec724fe0956869ecb57b516818037b0512744fde",
                             ("335a49de7a92710e7afce69de3f96a50810c56e4",),
                             "2026-09-29T21:16:09Z", True),
            loss.CommitFacts(H1, record["tree_sha"], (H0,),
                             "2026-09-30T19:38:07Z", True),
        )
        return loss._historical_provider_binding_for_ready(
            record, commits, "2026-09-29T21:22:56Z")

    def test_exact_current_receipt_and_finite_history(self):
        record = self.record()
        self.assertEqual(record["admission_schema_version"], "1.3")
        self.assertEqual(record["pull_request"], 525)
        self.assertEqual(record["head_sha"], H1)
        self.assertEqual(record["parent_sha"], H0)
        self.assertEqual(record["historical_validation_receipt_digest"],
                         "b34ab1e452e4c82e5cef84ad3e4728b206f392517e5c12de2e03f179bfab32f3")
        self.assertEqual(record["historical_package_status"], "UNAVAILABLE")
        self.assertIsNone(record["historical_final_attestation_digest"])
        self.assertIs(record["historical_bytes_reconstructed"], False)
        state = record["intended_state"]
        self.assertEqual([state[key] for key in (
            "unrestricted_review_count", "remediation_cycle_count",
            "ready_transition_count", "exceptional_recovery_count",
            "exceptional_continuation_count")], [1, 1, 1, 0, 0])
        self.assertIs(state["ready"], True)
        self.assertIs(state["draft"], False)
        self.assertIs(state["cycle_3_absent"], True)
        loss.authority._normalize_observed_pre_enrollment_history(
            record["observed_pre_enrollment_history"], expected_head=H1,
            intended_state=state, review_budget_consumption_admitted=True)

    def test_exact_profile_and_cross_delivery_rejection(self):
        record = self.record()
        with patch.object(loss.exact_source_safety, "build_profile", return_value={}) as build:
            loss._current_safety_profile_for_record("a" * 40, record)
        self.assertEqual(build.call_args.kwargs["harness_paths"], (HARNESS,))
        for field, value in (("repository", "Other/contracts"),
                             ("delivery_issue", 523), ("pull_request", 526),
                             ("current_safety_harness_path", loss.CURRENT_RECEIPT_SAFETY_PATH)):
            with self.subTest(field=field):
                changed = copy.deepcopy(record)
                changed[field] = value
                with patch.object(loss.exact_source_safety, "build_profile", return_value={}):
                    with self.assertRaises(loss.authority.LifecycleAuthorityError):
                        loss._current_safety_profile_for_record("a" * 40, changed)

    def test_real_summary_preserves_h0_and_rejects_bad_rows(self):
        record = self.record()
        binding = self.binding()
        summary = json.loads((ROOT / "tests/fixtures/contracts-525-provider-summary.json").read_text())["body"]
        self.assertEqual(loss.fast_path.digest_text(summary),
                         record["historical_provider_summary_digest"])
        binding.verify_historical_provider_summary(
            body=summary, repository="SecPal/contracts", pull_request=525,
            current_head_sha=H1)
        self.assertEqual(binding.provider_head(
            repository="SecPal/contracts", pull_request=525,
            current_head_sha=H1), H0)
        code = next(line for line in summary.splitlines() if "**Code Review**" in line)
        security = next(line for line in summary.splitlines() if "**Security Review**" in line)
        code_only = summary.replace(security, "")
        self.binding(loss.fast_path.digest_text(code_only)).verify_historical_provider_summary(
            body=code_only, repository="SecPal/contracts",
            pull_request=525, current_head_sha=H1)
        for changed in (summary + "\n" + code, summary + "\n" + security,
                        summary.replace(security, security.replace("5fefdc0", "f8e229e")),
                        summary.replace(code, code.replace("Completed", "Running")),
                        summary.replace(security, security.replace("Completed", "Running"))):
            with self.subTest(summary=changed[-100:]):
                with self.assertRaises(loss.fast_path.SecurityBlocker):
                    self.binding(loss.fast_path.digest_text(changed)).verify_historical_provider_summary(
                        body=changed, repository="SecPal/contracts",
                        pull_request=525, current_head_sha=H1)

    def test_safety_execution_rederives_the_same_contracts_profile(self):
        record = self.record()
        def build(_root, _main, **kwargs):
            return {"policy": kwargs["policy"], "harness_paths": kwargs["harness_paths"]}
        with patch.object(loss.exact_source_safety, "build_profile", side_effect=build), patch.object(
            loss.exact_source_safety, "run_profile"
        ) as run:
            profile = loss._current_safety_profile_for_record("a" * 40, record)
            loss._run_current_safety("a" * 40, ROOT, profile, record=record)
        self.assertEqual(run.call_args.kwargs["expected_profile"], profile)

    def test_real_harness_accepts_h1_and_rejects_h0_before_fifo_read(self):
        spec = importlib.util.spec_from_file_location("contracts_safety", ROOT / HARNESS)
        assert spec is not None and spec.loader is not None
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        # Only dependency installation is isolated; every guard subprocess and
        # filesystem probe executes against the authenticated historical source.
        run = harness._run

        def installed(command, **kwargs):
            if command[0] == "npm":
                return subprocess.CompletedProcess(command, 0)
            return run(command, **kwargs)

        for source, expected in (("h1", 0), ("h0", 1)):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "scripts").mkdir()
                shutil.copyfile(
                    ROOT / f"tests/fixtures/contracts-524-node-toolchain-{source}.txt",
                    root / harness.GUARD)
                dependencies = root / "node_modules"
                dependencies.mkdir()
                (dependencies / "js-yaml").symlink_to(
                    ROOT / "node_modules/js-yaml", target_is_directory=True)
                (root / ".nvmrc").write_text("26\n")
                package = {"engines": {"node": "^26.0.0"}}
                (root / "package.json").write_text(json.dumps(package))
                (root / "package-lock.json").write_text(json.dumps({"packages": {"": package}}))
                workflows = root / ".github/workflows"
                workflows.mkdir(parents=True)
                workflow = "jobs:\n  lint:\n    steps:\n      - uses: actions/setup-node@" + "1" * 40 + "\n        with:\n          node-version: '26'\n"
                for name in ("local-openapi-lint.yml", "local-prettier.yml"):
                    (workflows / name).write_text(workflow)
                output = io.StringIO()
                with patch.object(harness.Path, "cwd", return_value=root), patch.object(
                    harness, "_run", side_effect=installed
                ), contextlib.redirect_stdout(output):
                    self.assertEqual(harness.main([]), expected)
                self.assertEqual(json.loads(output.getvalue()),
                                 harness.INVARIANTS if expected == 0 else ["registered_validation"])
                self.assertFalse(dependencies.exists())


if __name__ == "__main__":
    unittest.main()
