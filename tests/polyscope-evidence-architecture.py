#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real gate integration at the shared source/worktree admission boundary."""

import importlib.util
import json
import subprocess
import shutil
from argparse import Namespace
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

    def test_direct_api_operation_requires_dispatch_admission_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("`docs/work-graph-contract.md`\n")
            validator = root / "ai-validator.sh"
            validator.write_text("#!/bin/sh\nexit 0\n")
            validator.chmod(0o755)
            for mode, operation in (("prepare_api_worktree", "prepare_api_worktree"),
                                    ("bootstrap_api_worktree", "bootstrap_api_worktree"),
                                    ("refresh_api_worktree", "refresh_api_worktree"),
                                    ("run_api_worktree", "run_api_worktree_shell_command")):
                arguments = {name: None for name in rollout.INSTRUCTION_DEPENDENT_DIRECT_API_MODES}
                arguments.update({mode: root, "source_repo_path": root, "shell_command": "true", "db_path": root / "db"})
                with self.subTest(mode=mode), mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator), mock.patch.object(rollout, operation, return_value=(True, None)) as external:
                    with self.assertRaises(rollout.CanonicalInstructionValidationError):
                        rollout.dispatch_instruction_dependent_direct_api_mode(Namespace(**arguments))
                    external.assert_not_called()
            (root / ".secpal").mkdir()
            declaration = {
                "schema": "secpal-evidence-architecture/v1", "repository": "SecPal/api",
                "runtime_baseline": {"delegation": "transitive_work_graph", "generic_authorities": ["docs/work-graph-contract.md"]},
                "external_operations": [{"id": "runtime", "reachable": True, "fallible": True, "trusted": True,
                                         "diagnostic_identity": {"id": "runtime.admission", "kind": "semantic"}}],
                "pure_surfaces": [], "invariant_declarations": [],
            }
            (root / ".secpal/evidence-architecture.json").write_text(json.dumps(declaration))
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator), mock.patch.object(rollout, "run_api_worktree_shell_command") as external:
                self.assertEqual(rollout.dispatch_instruction_dependent_direct_api_mode(Namespace(**arguments)), 0)
                external.assert_called_once()
            declaration["external_operations"][0]["diagnostic_identity"] = None
            (root / ".secpal/evidence-architecture.json").write_text(json.dumps(declaration))
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator), mock.patch.object(rollout, "run_api_worktree_shell_command") as external:
                with self.assertRaises(rollout.CanonicalInstructionValidationError):
                    rollout.dispatch_instruction_dependent_direct_api_mode(Namespace(**arguments))
                external.assert_not_called()

    def test_architecture_failure_names_the_correct_diagnostic_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("Missing delegation\n")
            with self.assertRaisesRegex(rollout.CanonicalInstructionValidationError, "Evidence Architecture validation failed"):
                rollout.validate_evidence_architecture_root(root, "example")

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
            active = workspace / "active-edge"
            shutil.copytree(workspace / "edge", active)
            with mock.patch.object(rollout, "CANONICAL_AI_INSTRUCTIONS_VALIDATOR", validator):
                rollout.validate_instruction_root(active, set(), "edge",
                    architecture_arguments=specs["edge"][rollout.EVIDENCE_VALIDATION_ARGUMENTS_SPEC_KEY], active_worktree=True)
                args = Namespace(validate_instruction_worktree=active, instruction_repository_name="edge",
                                 architecture_workspace_root=workspace, architecture_repository=["owner", "edge"])
                self.assertEqual(rollout.dispatch_validation_only_direct_mode(args), 0)
                with mock.patch.object(rollout, "REPO_SETTINGS", {"owner": {}, "edge": {}}):
                    generated = rollout.build_workspace_instruction_validation_command("edge", workspace)
                    self.assertIn("--architecture-workspace-root " + str(workspace), generated)
                    self.assertIn("--architecture-repository owner --architecture-repository edge", generated)
                dispatched = command + ["--managed-worktree", "edge=" + str(active), "--dispatch"]
                result = subprocess.run(dispatched, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1)
                self.assertIn("DISPATCH_DECLARATION_MISSING", result.stdout)
                declaration_path = active / ".secpal/evidence-architecture.json"
                declaration = json.loads(declaration_path.read_text())
                declaration["external_operations"] = [{"id": "runtime", "reachable": True, "fallible": True, "trusted": True,
                                                       "diagnostic_identity": {"id": "runtime.admission", "kind": "semantic"}}]
                declaration_path.write_text(json.dumps(declaration))
                self.assertEqual(subprocess.run(dispatched, capture_output=True, text=True, timeout=30).returncode, 0)
                substituted = command + ["--managed-worktree", "unknown=" + str(active)]
                self.assertEqual(subprocess.run(substituted, capture_output=True, text=True, timeout=30).returncode, 1)
                (active / "pure.py").write_text("def normalize(value):\n    return value\ndef admit(value):\n    return True\n")
                with self.assertRaises(rollout.CanonicalInstructionValidationError):
                    rollout.validate_instruction_root(active, set(), "edge",
                        architecture_arguments=specs["edge"][rollout.EVIDENCE_VALIDATION_ARGUMENTS_SPEC_KEY], active_worktree=True)
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


class NativeApplicationRuntimeTests(unittest.TestCase):
    def arguments(self, root, **changes):
        values={name:None for name in rollout.INSTRUCTION_DEPENDENT_DIRECT_API_MODES}
        values.update(run_api_runtime_worktree=root,source_repo_path=root,
                      runtime_role='scheduler',shell_command=None,db_path=root/'db')
        values.update(changes)
        return Namespace(**values)

    def test_fixed_application_roles_do_not_require_a_qualification_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'AGENTS.md').write_text('`docs/work-graph-contract.md`\n')
            validator=root/'ai-validator.sh';validator.write_text('#!/bin/sh\nexit 0\n');validator.chmod(0o755)
            for role,command in [('scheduler',rollout.API_SCHEDULER_COMMAND),('queue',rollout.API_QUEUE_WORKER_COMMAND),('pail',rollout.API_PAIL_COMMAND)]:
                with self.subTest(role=role),mock.patch.object(rollout,'CANONICAL_AI_INSTRUCTIONS_VALIDATOR',validator),mock.patch.object(rollout,'run_api_worktree_shell_command') as execute:
                    self.assertEqual(rollout.dispatch_instruction_dependent_direct_api_mode(self.arguments(root,runtime_role=role)),0)
                    self.assertEqual(execute.call_args.args,(root,root,command))

    def test_fixed_role_path_rejects_arbitrary_shell_and_unknown_roles(self):
        for changes in [{'runtime_role':'queue; touch /tmp/marker'},{'runtime_role':None},{'shell_command':'touch /tmp/marker'}]:
            with self.subTest(changes=changes),mock.patch.object(rollout,'run_api_worktree_shell_command') as execute:
                with self.assertRaises(SystemExit):
                    rollout.dispatch_instruction_dependent_direct_api_mode(self.arguments(Path('/unused'),**changes))
                execute.assert_not_called()

    def test_fixed_runtime_still_rejects_missing_baseline_or_invalid_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            validator=root/'ai-validator.sh';validator.write_text('#!/bin/sh\nexit 0\n');validator.chmod(0o755)
            for baseline,declaration in [('Missing delegation',None),('`docs/work-graph-contract.md`','{"status":"passed"}')]:
                (root/'AGENTS.md').write_text(baseline+'\n')
                if declaration:
                    (root/'.secpal').mkdir(exist_ok=True);(root/'.secpal/evidence-architecture.json').write_text(declaration)
                with mock.patch.object(rollout,'CANONICAL_AI_INSTRUCTIONS_VALIDATOR',validator),mock.patch.object(rollout,'run_api_worktree_shell_command') as execute:
                    with self.assertRaises(rollout.CanonicalInstructionValidationError):
                        rollout.dispatch_instruction_dependent_direct_api_mode(self.arguments(root))
                    execute.assert_not_called()

    def test_runtime_rendering_cannot_introduce_an_arbitrary_command(self):
        with self.assertRaises(ValueError):
            rollout.build_api_preview_runtime_shell_command('php artisan schedule:work; touch /tmp/marker',Path('/source/api'))


if __name__ == "__main__":
    unittest.main()
