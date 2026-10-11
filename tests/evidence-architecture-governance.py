#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Structural invariants for canonical evidence-architecture governance."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK_GRAPH_PATH = "docs/work-graph-contract.md"
EVIDENCE_PATH = "docs/evidence-architecture-contract.md"


def validate_binding(work_graph: str, evidence: str, agents: str) -> None:
    """Require one canonical companion and an unbroken runtime delegation."""

    if EVIDENCE_PATH not in work_graph:
        raise AssertionError(
            "the work-graph contract must normatively incorporate the evidence contract"
        )
    if "normatively incorporates" not in work_graph:
        raise AssertionError(
            "the work-graph contract must identify the companion as normative"
        )
    for path in (WORK_GRAPH_PATH, EVIDENCE_PATH):
        if path not in agents:
            raise AssertionError(f"the root runtime baseline must reference {path}")
    for reference in (
        "#63",
        "#64",
        "#66",
        "#67",
        "#68",
        "#72",
        "#73",
        "#74",
        "#117",
        "#118",
        "#119",
        "#120",
        "#121",
        "#122",
        "#145",
        "#146",
        "#147",
        "#148",
        "#149",
        "#150",
        "33021568439",
    ):
        if re.search(rf"(?<![0-9]){re.escape(reference)}(?![0-9])", evidence) is None:
            raise AssertionError(
                f"the historical source record must retain {reference}"
            )


class EvidenceArchitectureGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_graph = (ROOT / WORK_GRAPH_PATH).read_text(encoding="utf-8")
        self.evidence = (ROOT / EVIDENCE_PATH).read_text(encoding="utf-8")
        self.agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    def test_canonical_runtime_binding_is_complete(self) -> None:
        validate_binding(self.work_graph, self.evidence, self.agents)

    def test_missing_work_graph_delegation_is_rejected(self) -> None:
        mutated = self.work_graph.replace(EVIDENCE_PATH, "")
        with self.assertRaisesRegex(AssertionError, "normatively incorporate"):
            validate_binding(mutated, self.evidence, self.agents)

    def test_missing_runtime_baseline_reference_is_rejected(self) -> None:
        mutated = self.agents.replace(EVIDENCE_PATH, "")
        with self.assertRaisesRegex(AssertionError, "root runtime baseline"):
            validate_binding(self.work_graph, self.evidence, mutated)

    def test_renumbered_historical_reference_is_rejected(self) -> None:
        mutated = self.evidence.replace("#64", "#640")
        with self.assertRaisesRegex(AssertionError, "retain #64"):
            validate_binding(self.work_graph, mutated, self.agents)

    def test_current_rocky_correction_is_distinguished_from_history(self) -> None:
        normalized_evidence = " ".join(self.evidence.split())
        for statement in (
            "current #117 now requires explicit observation, normalization, admission, and assembly ownership",
            "current corrective prerequisite #150 blocks further #118 real-provider qualification",
            "#120, #121, and #122 remain scoped to #119 workload evidence",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, normalized_evidence)

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
