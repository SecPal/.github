#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Structural invariants for canonical evidence-architecture governance."""

from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
class EvidenceArchitectureGovernanceTests(unittest.TestCase):
    def gate_workflow(self) -> dict:
        result = subprocess.run(
            ["node", "--input-type=module", "-e",
             "import fs from 'node:fs'; import * as yaml from 'js-yaml'; " +
             "process.stdout.write(JSON.stringify(yaml.load(fs.readFileSync('.github/workflows/quality.yml','utf8'))));"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)

    def assert_active_gate(self, workflow: dict) -> None:
        jobs = [job for job in workflow["jobs"].values() if job.get("name") == "Evidence Architecture PR Gate"]
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertNotIn("if", job)
        self.assertNotIn("continue-on-error", job)
        self.assertNotIn("permissions", job)
        self.assertLessEqual(job["timeout-minutes"], 10)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        steps = job["steps"]
        command = next(step for step in steps if "secpal-evidence-architecture.py" in step.get("run", ""))
        self.assertEqual(command["run"], "python3 -I scripts/secpal-evidence-architecture.py --repository-root . --repository SecPal/.github")
        for step in steps:
            self.assertNotIn("if", step)
            self.assertNotIn("continue-on-error", step)
        for suite in ("secpal-evidence-architecture", "polyscope-evidence-architecture", "evidence-architecture-governance"):
            self.assertTrue(any(f"python3 tests/{suite}.py" in step.get("run", "") for step in steps))

    def test_distinct_gate_is_unconditional_and_runs_real_enforcement(self) -> None:
        self.assert_active_gate(self.gate_workflow())

    def test_disabled_skipped_or_disconnected_gate_mutations_are_rejected(self) -> None:
        workflow = self.gate_workflow()
        for mutation in ("job_skip", "step_skip", "soft_failure", "disconnect"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(workflow)
                job = changed["jobs"]["evidence-architecture"]
                if mutation == "job_skip":
                    job["if"] = "false"
                elif mutation == "step_skip":
                    job["steps"][-1]["if"] = "false"
                elif mutation == "soft_failure":
                    job["continue-on-error"] = True
                else:
                    job["steps"][-1]["run"] = "true"
                with self.assertRaises(AssertionError):
                    self.assert_active_gate(changed)


if __name__ == "__main__":
    unittest.main()
