#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real gate integration at the shared source/worktree admission boundary."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import unittest.mock as mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("architecture_rollout", ROOT / "scripts/polyscope-rollout.py")
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


class PolyscopeArchitectureTests(unittest.TestCase):
    def test_managed_scope_cannot_substitute_another_worktree_or_self_check(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "actual"
            other = workspace / "other"
            root.mkdir()
            other.mkdir()
            (root / "AGENTS.md").write_text("Missing delegation\n")
            (other / "AGENTS.md").write_text("`docs/work-graph-contract.md`\n")
            for arguments in (
                ["--self-check"],
                ["--managed-workspace-root", str(workspace), "--managed-repository", "other"],
            ):
                with self.subTest(arguments=arguments), self.assertRaises(rollout.CanonicalInstructionValidationError):
                    rollout.validate_evidence_architecture_root(root, "actual", arguments)

    def test_symlink_worktree_cannot_hide_its_actual_admission_root(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "actual"
            root.mkdir()
            (root / "AGENTS.md").write_text("`docs/work-graph-contract.md`\n")
            (root / ".secpal").mkdir()
            (root / ".secpal/evidence-architecture.json").write_text('{"status":"passed"}')
            alias = workspace / "alias"
            alias.symlink_to(root, target_is_directory=True)
            validator = workspace / "ai-validator.sh"
            validator.write_text("#!/bin/sh\nexit 0\n")
            validator.chmod(0o755)
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator):
                with self.assertRaises(rollout.CanonicalInstructionValidationError) as caught:
                    rollout.validate_instruction_root(alias, set(), "actual")
                self.assertIn(str(root), str(caught.exception))

    def test_cached_worktree_must_revalidate_changed_managed_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Runtime\n\n`docs/work-graph-contract.md`\n")
            validator = root / "ai-validator.sh"
            validator.write_text("#!/bin/sh\nexit 0\n")
            validator.chmod(0o755)
            cache = set()
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator):
                rollout.validate_instruction_root(root, cache, "example")
                (root / ".secpal").mkdir()
                (root / ".secpal/evidence-architecture.json").write_text('{"status":"passed"}')
                with self.assertRaises(rollout.CanonicalInstructionValidationError):
                    rollout.validate_instruction_root(root, cache, "example")

    def test_worktree_dispatch_is_rejected_before_runtime_operation_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Runtime\n\nMissing delegation\n")
            marker = root / "executed"
            validator = root / "ai-validator.sh"
            validator.write_text("#!/bin/sh\nexit 0\n")
            validator.chmod(0o755)
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator):
                with self.assertRaises(rollout.CanonicalInstructionValidationError):
                    rollout.validate_instruction_root(root, set(), "example")
                    marker.write_text("external operation invoked")
            self.assertFalse(marker.exists())

    def test_declared_opaque_operation_blocks_real_worktree_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Runtime\n\n`docs/work-graph-contract.md`\n")
            (root / ".secpal").mkdir()
            (root / ".secpal/evidence-architecture.json").write_text(json.dumps({
                "schema": "secpal-evidence-architecture/v1", "repository": "SecPal/example",
                "runtime_baseline": {"delegation": "transitive_work_graph", "generic_authorities": ["docs/work-graph-contract.md"]},
                "external_operations": [{"id": "inspect", "reachable": True, "fallible": True,
                                         "trusted": True, "diagnostic_identity": None}],
                "pure_surfaces": [], "invariant_declarations": [],
            }))
            validator = root / "ai-validator.sh"
            validator.write_text("#!/bin/sh\nexit 0\n")
            validator.chmod(0o755)
            marker = root / "external-operation"
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator):
                with self.assertRaises(rollout.CanonicalInstructionValidationError):
                    rollout.validate_instruction_root(root, set(), "example")
                    marker.write_text("invoked")
            self.assertFalse(marker.exists())

    def test_managed_cross_repository_agreement_executes_both_actual_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for name in ("owner", "edge"):
                root = workspace / name
                (root / ".secpal").mkdir(parents=True)
                (root / "AGENTS.md").write_text("`docs/work-graph-contract.md`\n")
                (root / "pure.py").write_text(
                    "def normalize(value):\n    return value.removeprefix('sha256:')\n"
                    "def admit(value):\n    return len(value) == 64\n"
                )
                invariant = {"id": name, "invariant": "digest.length", "role": "owner", "surface": name + ".admit"}
                if name == "edge":
                    invariant.update(role="independent_enforcement", owner="owner", derivation="reviewed-cases", agreement_proof="proof")
                (root / ".secpal/evidence-architecture.json").write_text(json.dumps({
                    "schema": "secpal-evidence-architecture/v1", "repository": "SecPal/" + name,
                    "runtime_baseline": {"delegation": "transitive_work_graph", "generic_authorities": ["docs/work-graph-contract.md"]},
                    "external_operations": [],
                    "pure_surfaces": [
                        {"id": name + ".normalize", "responsibility": "normalization", "capabilities": ["deterministic_compute"], "source": "pure.py#normalize"},
                        {"id": name + ".admit", "responsibility": "admission", "capabilities": ["deterministic_compute"], "source": "pure.py#admit"},
                    ], "invariant_declarations": [invariant],
                }))
            (workspace / "edge/.secpal/evidence-agreement-results.json").write_text(json.dumps({
                "schema": "secpal-evidence-agreement-execution/v1", "proofs": [{
                    "id": "proof", "owner": "owner", "enforcement": "edge",
                    "left": {"normalization": "owner.normalize", "admission": "owner.admit"},
                    "right": {"normalization": "edge.normalize", "admission": "edge.admit"},
                    "cases": [{"input": "sha256:" + "a" * 64, "expected": True}, {"input": "sha256:bad", "expected": False}],
                }],
            }))
            command = ["python3", "-I", str(ROOT / "scripts/secpal-evidence-architecture.py"),
                       "--managed-workspace-root", str(workspace), "--managed-repository", "owner", "--managed-repository", "edge"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout)
            validator = workspace / "ai-validator.sh"
            validator.write_text("#!/bin/sh\nexit 0\n")
            validator.chmod(0o755)
            specs = {name: {"path": workspace / name, "repository_name": name} for name in ("owner", "edge")}
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator):
                rollout.validate_repo_instruction_files(specs, set())
            (workspace / "owner/pure.py").write_text("def normalize(value):\n    return value\ndef admit(value):\n    return True\n")
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn("AGREEMENT_EXECUTION_FAILED", result.stdout)

    def test_managed_bundle_rejects_owners_duplicated_across_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for name in ("one", "two"):
                root = workspace / name
                (root / ".secpal").mkdir(parents=True)
                (root / "AGENTS.md").write_text("`docs/work-graph-contract.md`\n")
                (root / "pure.py").write_text("def admit(value):\n    return True\n")
                (root / ".secpal/evidence-architecture.json").write_text(json.dumps({
                    "schema": "secpal-evidence-architecture/v1", "repository": "SecPal/" + name,
                    "runtime_baseline": {"delegation": "transitive_work_graph", "generic_authorities": ["docs/work-graph-contract.md"]},
                    "external_operations": [],
                    "pure_surfaces": [{"id": name + ".admit", "responsibility": "admission", "capabilities": ["deterministic_compute"], "source": "pure.py#admit"}],
                    "invariant_declarations": [{"id": name + ".owner", "invariant": "shared", "role": "owner", "surface": name + ".admit"}],
                }))
            result = subprocess.run(["python3", "-I", str(ROOT / "scripts/secpal-evidence-architecture.py"),
                                     "--managed-workspace-root", str(workspace), "--managed-repository", "one",
                                     "--managed-repository", "two"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn("DUPLICATE_INVARIANT_OWNER", result.stdout)

    def test_invariant_identity_collision_cannot_substitute_another_owners_source(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for name, length, invariant, role in (
                ("owner", 64, "digest.length", "owner"),
                ("other", 3, "other.length", "owner"),
                ("edge", 3, "digest.length", "independent_enforcement"),
            ):
                root = workspace / name
                (root / ".secpal").mkdir(parents=True)
                (root / "AGENTS.md").write_text("`docs/work-graph-contract.md`\n")
                (root / "pure.py").write_text(f"def normalize(value):\n    return value\ndef admit(value):\n    return len(value) == {length}\n")
                entry = {"id": "canonical" if role == "owner" else "edge", "invariant": invariant,
                         "role": role, "surface": name + ".admit"}
                if role == "independent_enforcement":
                    entry.update(owner="canonical", derivation="reviewed-values", agreement_proof="proof")
                (root / ".secpal/evidence-architecture.json").write_text(json.dumps({
                    "schema": "secpal-evidence-architecture/v1", "repository": "SecPal/" + name,
                    "runtime_baseline": {"delegation": "transitive_work_graph", "generic_authorities": ["docs/work-graph-contract.md"]},
                    "external_operations": [], "pure_surfaces": [
                        {"id": name + "." + function, "responsibility": responsibility,
                         "capabilities": ["deterministic_compute"], "source": "pure.py#" + function}
                        for function, responsibility in (("normalize", "normalization"), ("admit", "admission"))
                    ], "invariant_declarations": [entry],
                }))
            (workspace / "edge/.secpal/evidence-agreement-results.json").write_text(json.dumps({
                "schema": "secpal-evidence-agreement-execution/v1", "proofs": [{
                    "id": "proof", "owner": "canonical", "enforcement": "edge",
                    "left": {"normalization": "other.normalize", "admission": "other.admit"},
                    "right": {"normalization": "edge.normalize", "admission": "edge.admit"},
                    "cases": [{"input": "abc", "expected": True}, {"input": "bad-length", "expected": False}],
                }],
            }))
            result = subprocess.run(["python3", "-I", str(ROOT / "scripts/secpal-evidence-architecture.py"),
                                     "--managed-workspace-root", str(workspace),
                                     "--managed-repository", "owner", "--managed-repository", "other",
                                     "--managed-repository", "edge"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("DUPLICATE_INVARIANT_IDENTITY", result.stdout)


if __name__ == "__main__":
    unittest.main()
