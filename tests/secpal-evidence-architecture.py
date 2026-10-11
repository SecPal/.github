#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Execute the real declared-surface gate, including hostile local evidence."""

from __future__ import annotations

import json
import importlib.util
import os
import py_compile
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/secpal-evidence-architecture.py"


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".secpal").mkdir()
        (self.root / "AGENTS.md").write_text(
            "# Runtime\n\nDelegate to `docs/work-graph-contract.md`.\n"
        )
        self.source = (
            "def normalize(value):\n"
            "    return value.lower().removeprefix('sha256:')\n\n"
            "def admit(value):\n"
            "    return len(value) == 64\n"
        )
        (self.root / "pure.py").write_text(self.source)
        self.document = {
            "schema": "secpal-evidence-architecture/v1",
            "repository": "SecPal/example",
            "runtime_baseline": {
                "delegation": "transitive_work_graph",
                "generic_authorities": ["docs/work-graph-contract.md"],
            },
            "external_operations": [{
                "id": "inspect-host", "reachable": True, "fallible": True,
                "trusted": True,
                "diagnostic_identity": {"id": "host.inspect", "kind": "semantic"},
            }],
            "pure_surfaces": [
                {"id": "normalize", "responsibility": "normalization",
                 "capabilities": ["deterministic_compute"], "source": "pure.py#normalize"},
                {"id": "admit", "responsibility": "admission",
                 "capabilities": ["deterministic_compute"], "source": "pure.py#admit"},
            ],
            "invariant_declarations": [{"id": "owner", "invariant": "digest", "role": "owner", "surface": "admit"}],
        }

    def run_gate(self, *arguments, env=None):
        (self.root / ".secpal/evidence-architecture.json").write_text(json.dumps(self.document))
        return subprocess.run(
            [sys.executable, "-I", str(CLI), "--repository-root", str(self.root),
             "--repository", "SecPal/example", *arguments],
            capture_output=True, text=True, timeout=30, env=env,
        )

    def blocked(self, code, *arguments):
        result = self.run_gate(*arguments)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn(code, [item["code"] for item in report["findings"]])
        self.assertFalse(report["claims_complete_architecture_judgment"])
        return result

    def agreement(self):
        self.document["invariant_declarations"].append({
            "id": "edge", "invariant": "digest", "role": "independent_enforcement",
            "surface": "edge-admit", "owner": "owner", "derivation": "reviewed-digest-cases", "agreement_proof": "agreement",
        })
        (self.root / "edge.py").write_text(self.source)
        self.document["pure_surfaces"].extend([
            {"id": "edge-normalize", "responsibility": "normalization", "capabilities": ["deterministic_compute"], "source": "edge.py#normalize"},
            {"id": "edge-admit", "responsibility": "admission", "capabilities": ["deterministic_compute"], "source": "edge.py#admit"},
        ])
        proof = {
            "schema": "secpal-evidence-agreement-execution/v1",
            "proofs": [{
                "id": "agreement", "owner": "owner", "enforcement": "edge",
                "left": {"normalization": "normalize", "admission": "admit"},
                "right": {"normalization": "edge-normalize", "admission": "edge-admit"},
                "cases": [{"input": "sha256:" + "A" * 64, "expected": True},
                          {"input": "sha256:bad", "expected": False}],
            }],
        }
        path = self.root / ".secpal/evidence-agreement-results.json"
        path.write_text(json.dumps(proof))
        return proof, path

    def test_declared_pure_positive_and_dispatch(self):
        result = self.run_gate("--dispatch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")

    def test_supported_expression_semantics_match_actual_python_functions(self):
        spec = importlib.util.spec_from_file_location("pure_subset", ROOT / "scripts/secpal_evidence_architecture/execution.py")
        execution = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(execution)
        expressions = ["value.lower().removeprefix('sha256:')", "value.upper().strip()",
                       "value.removesuffix(':end')", "value.startswith('sha256:') and len(value) == 71",
                       "value.endswith(':end') or not value", "0 < len(value) < 72",
                       "True if 'sha256:' in value else False", "'bad' not in value"]
        values = ["sha256:" + "a" * 64, "sha256:bad", " prefix:end ", ""]
        for expression in expressions:
            source = f"def transform(value):\n    return {expression}\n"
            actual = {}
            # This is a trusted authored fixture, independently exercised by the
            # Python runtime to check the interpreter's compatibility promise.
            exec(source, {"__builtins__": {"len": len}}, actual)
            guarded = execution.pure_expression(source, "transform")
            for value in values:
                self.assertEqual(guarded(value), actual["transform"](value))

    def test_each_opaque_failure_boundary_blocks_before_dispatch(self):
        for diagnostic in (None, {"id": "bootstrap", "kind": "phase"},
                           {"id": "x" * 500, "kind": "semantic"},
                           {"id": "secret=value\n", "kind": "semantic"},
                           {"id": "inspect", "kind": "semantic", "stderr": "credential"}):
            with self.subTest(diagnostic=diagnostic):
                self.document["external_operations"][0]["diagnostic_identity"] = diagnostic
                result = self.run_gate("--dispatch")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("credential", result.stdout + result.stderr)

    def test_empty_dispatch_inventory_blocks(self):
        self.document["external_operations"] = []
        self.blocked("DISPATCH_DECLARATION_MISSING", "--dispatch")

    def test_self_check_cannot_replace_dispatch_admission(self):
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE", "--dispatch", "--self-check")

    def test_declared_owner_must_name_an_actual_admission_surface(self):
        self.document["invariant_declarations"][0]["surface"] = "missing"
        self.blocked("INVARIANT_SURFACE_UNPROVEN")

    def test_forbidden_declared_capabilities(self):
        for capability in ("process", "filesystem", "network", "clock", "mutable_external_state"):
            with self.subTest(capability=capability):
                self.document["pure_surfaces"][0]["capabilities"] = [capability]
                self.blocked("PURE_SURFACE_FORBIDDEN_CAPABILITY")

    def test_source_mutation_cannot_lie_about_capabilities(self):
        for body in ("open('/etc/passwd').read()", "__import__('os').environ",
                     "__import__('subprocess').run(['true'])", "__import__('time').time()",
                     "__import__('socket').socket()", "value.__class__", "eval(value)"):
            with self.subTest(body=body):
                (self.root / "pure.py").write_text(f"def normalize(value):\n    return {body}\n")
                self.blocked("PURE_SOURCE_UNPROVEN")

    def test_baseline_reference_must_be_operative(self):
        for reference in ("", "<!-- `docs/work-graph-contract.md` -->", "> `docs/work-graph-contract.md`",
                          "```\ndocs/work-graph-contract.md\n```"):
            with self.subTest(reference=reference):
                (self.root / "AGENTS.md").write_text("# Runtime\n\n" + reference + "\n")
                self.blocked("MISSING_RUNTIME_BASELINE_DELEGATION")

    def test_managed_parser_batch_preserves_each_document_boundary(self):
        result = subprocess.run(["node", str(ROOT / "scripts/secpal_evidence_architecture/markdown_references.mjs")],
                                input=json.dumps({"documents": ["`docs/work-graph-contract.md`",
                                                               "<!-- `docs/work-graph-contract.md` -->",
                                                               "> `docs/work-graph-contract.md`"]}),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"references": [["docs/work-graph-contract.md"], [], []]})

    def test_contradictory_declared_authority(self):
        self.document["runtime_baseline"]["generic_authorities"] = ["local-contract.md"]
        self.blocked("CONTRADICTORY_RUNTIME_BASELINE_DELEGATION")

    def test_duplicate_owner(self):
        self.document["invariant_declarations"].append({"id": "other", "invariant": "digest", "role": "owner", "surface": "admit"})
        self.blocked("DUPLICATE_INVARIANT_OWNER")

    def test_executed_realistic_agreement_has_source_and_input_provenance(self):
        self.agreement()
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)["agreement_execution"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["cases"], 2)
        self.assertEqual(len(evidence[0]["source_digest"]), 64)
        self.assertNotIn("sha256:" + "A" * 64, result.stdout)

    def test_forged_status_and_missing_execution_provenance_fail(self):
        proof, path = self.agreement()
        for value in ({"id": "agreement", "kind": "executable", "status": "passed"},
                      {"payload": {"results": [{"status": "passed"}]}, "signature": "fake"},
                      {"schema": proof["schema"], "proofs": []}):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                self.assertEqual(self.run_gate().returncode, 1)

    def test_changed_source_and_cases_are_reexecuted(self):
        proof, path = self.agreement()
        (self.root / "pure.py").write_text(self.source.replace("len(value) == 64", "True"))
        self.blocked("AGREEMENT_EXECUTION_FAILED")
        (self.root / "pure.py").write_text(self.source)
        proof["proofs"][0]["cases"][1]["input"] = "sha256:" + "B" * 64
        path.write_text(json.dumps(proof))
        self.blocked("AGREEMENT_EXECUTION_FAILED")

    def test_missing_or_wrong_owner_and_proof_fail(self):
        self.agreement()
        for key in ("owner", "derivation", "agreement_proof"):
            saved = self.document["invariant_declarations"][1][key]
            self.document["invariant_declarations"][1][key] = None
            self.blocked("INDEPENDENT_ENFORCEMENT_UNPROVEN")
            self.document["invariant_declarations"][1][key] = saved

    def test_proof_cannot_substitute_owner_implementation(self):
        proof, path = self.agreement()
        proof["proofs"][0]["right"]["admission"] = "admit"
        path.write_text(json.dumps(proof))
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE")

    def test_only_accepting_cases_do_not_prove_agreement(self):
        proof, path = self.agreement()
        proof["proofs"][0]["cases"] = [{"input": "sha256:" + "A" * 64, "expected": True}] * 2
        path.write_text(json.dumps(proof))
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE")

    def test_missing_declared_pure_source_fails(self):
        (self.root / "pure.py").unlink()
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE")

    def test_duplicate_json_fields_are_not_silent_policy_overrides(self):
        path = self.root / ".secpal/evidence-agreement-results.json"
        self.agreement()
        path.write_text('{"schema":"forged","schema":"secpal-evidence-agreement-execution/v1","proofs":[]}')
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE")

    def test_symlinks_and_parent_traversal_fail_closed(self):
        target = self.root / "outside.json"
        target.write_text(json.dumps(self.document))
        path = self.root / ".secpal/evidence-architecture.json"
        path.symlink_to(target)
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE")
        path.unlink()
        self.document["pure_surfaces"][0]["source"] = "../pure.py#normalize"
        self.blocked("DECLARATION_EVIDENCE_UNAVAILABLE")

    def test_pythonpath_cannot_replace_the_owned_module(self):
        attack = self.root / "attack"
        attack.mkdir()
        (attack / "secpal_evidence_architecture.py").write_text("raise RuntimeError('attacker-loaded')\n")
        result = self.run_gate(env={**os.environ, "PYTHONPATH": str(attack)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("attacker-loaded", result.stderr)

    def test_shared_diagnostic_identity_cannot_hide_two_trusted_operations(self):
        duplicate = json.loads(json.dumps(self.document["external_operations"][0]))
        duplicate["id"] = "collect-host"
        self.document["external_operations"].append(duplicate)
        self.blocked("OPAQUE_TRUSTED_FAILURE_BOUNDARY", "--dispatch")
        duplicate["reachable"] = False
        self.assertEqual(self.run_gate("--dispatch").returncode, 0)

    def test_builtin_shadowing_cannot_hide_a_reachable_filesystem_capability(self):
        marker = self.root / "side-effect"
        source = self.source + f"\ndef len(value):\n    __import__('pathlib').Path({str(marker)!r}).write_text('invoked')\n    return 64\n"
        (self.root / "pure.py").write_text(source)
        result = self.run_gate()
        namespace = {}
        exec(compile(source, "reviewed-pure-fixture", "exec", dont_inherit=True), namespace)
        self.assertTrue(namespace["admit"]("bad"))
        self.assertTrue(marker.exists())
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("PURE_SOURCE_UNPROVEN", result.stdout)

    def test_evaluated_function_metadata_cannot_change_the_execution_namespace(self):
        marker = self.root / "annotation-effect"
        for argument in ("*args", "**kwargs", "value, /", "*, value"):
            with self.subTest(argument=argument):
                parameter = argument.replace("value", f"value: __import__('pathlib').Path({str(marker)!r}).write_text('invoked')")
                if argument in ("*args", "**kwargs"):
                    parameter += f": __import__('pathlib').Path({str(marker)!r}).write_text('invoked')"
                source = self.source + f"\ndef helper({parameter}):\n    return None\n"
                (self.root / "pure.py").write_text(source)
                result = self.run_gate()
                namespace = {}
                exec(compile(source, "reviewed-pure-fixture", "exec", dont_inherit=True), namespace)
                self.assertTrue(marker.exists())
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("PURE_SOURCE_UNPROVEN", result.stdout)
                marker.unlink()

    def test_builtin_namespace_rebinding_cannot_forge_python_semantics(self):
        source = "def __builtins__(value):\n    return value\n\n" + self.source
        (self.root / "pure.py").write_text(source)
        result = self.run_gate()
        namespace = {}
        exec(compile(source, "reviewed-pure-fixture", "exec", dont_inherit=True), namespace)
        with self.assertRaises(TypeError):
            namespace["admit"]("a" * 64)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("PURE_SOURCE_UNPROVEN", result.stdout)

    def test_executable_is_isolated_before_python_startup_hooks(self):
        attack = self.root / "startup"
        attack.mkdir()
        marker = self.root / "hook-executed"
        (attack / "sitecustomize.py").write_text(f"open({str(marker)!r}, 'w').write('executed')\n")
        result = subprocess.run([str(CLI), "--repository-root", str(self.root),
                                 "--repository", "SecPal/example"], capture_output=True,
                                text=True, timeout=30, env={**os.environ, "PYTHONPATH": str(attack)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_node_preload_cannot_forge_canonical_parser_evidence(self):
        (self.root / "AGENTS.md").write_text("# Runtime\n\nMissing delegation\n")
        attack = self.root / "preload.cjs"
        attack.write_text('process.stdout.write(JSON.stringify({references:["docs/work-graph-contract.md"]})); process.exit(0);\n')
        result = self.run_gate(env={**os.environ, "NODE_OPTIONS": "--require=" + str(attack)})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("MISSING_RUNTIME_BASELINE_DELEGATION", result.stdout)

    def test_untracked_bytecode_cannot_replace_verified_package_source(self):
        (self.root / "AGENTS.md").write_text("# Runtime\n\nMissing delegation\n")
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            package = bundle / "scripts/secpal_evidence_architecture"
            shutil.copytree(ROOT / "scripts/secpal_evidence_architecture", package)
            shutil.copy2(CLI, bundle / "scripts" / CLI.name)
            (bundle / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
            source = package / "governance.py"
            forged = bundle / "forged.py"
            forged.write_text(source.read_text() + '\nassess_runtime_baseline = lambda *a, **k: {"state":"forged", "findings":[]}\n')
            cache = package / "__pycache__" / ("governance." + sys.implementation.cache_tag + ".pyc")
            cache.parent.mkdir(exist_ok=True)
            py_compile.compile(str(forged), cfile=str(cache), doraise=True)
            content = cache.read_bytes()
            cache.write_bytes(content[:8] + struct.pack("<II", int(source.stat().st_mtime), source.stat().st_size) + content[16:])
            (self.root / ".secpal/evidence-architecture.json").write_text(json.dumps(self.document))
            result = subprocess.run([sys.executable, "-I", str(bundle / "scripts" / CLI.name),
                                     "--repository-root", str(self.root), "--repository", "SecPal/example"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("MISSING_RUNTIME_BASELINE_DELEGATION", result.stdout)

    def test_missing_parser_and_package_fail_before_activation(self):
        with tempfile.TemporaryDirectory() as bundle:
            scripts = Path(bundle) / "scripts"
            shutil.copytree(ROOT / "scripts/secpal_evidence_architecture", scripts / "secpal_evidence_architecture")
            shutil.copy2(CLI, scripts / CLI.name)
            (Path(bundle) / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
            command = [sys.executable, "-I", str(scripts / CLI.name), "--self-check"]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            for removal in ("markdown_references.mjs", "__init__.py"):
                path = scripts / "secpal_evidence_architecture" / removal
                saved = path.read_bytes()
                path.unlink()
                result = subprocess.run([sys.executable, "-I", str(scripts / CLI.name), "--self-check"], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                path.write_bytes(saved)
            (Path(bundle) / "node_modules").unlink()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_parser_cannot_fall_back_to_an_ancestor_dependency_installation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            scripts = Path(directory) / "scripts"
            shutil.copytree(ROOT / "scripts/secpal_evidence_architecture", scripts / "secpal_evidence_architecture")
            shutil.copy2(CLI, scripts / CLI.name)
            result = subprocess.run([sys.executable, "-I", str(scripts / CLI.name), "--self-check"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_managed_assessment_binds_the_declaration_bytes_it_actually_validated(self):
        self.document["repository"] = "SecPal/" + self.root.name
        (self.root / ".secpal/evidence-architecture.json").write_text(json.dumps(self.document))
        # A real file mutation immediately after the real assessment models a
        # concurrent writer; neither observation nor admission is mocked.
        script = f"""
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location('gate', {str(CLI)!r})
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
actual_assess = gate.assess_root
def changed_after_assessment(*args, **kwargs):
    result = actual_assess(*args, **kwargs)
    path = pathlib.Path({str(self.root / '.secpal/evidence-architecture.json')!r})
    document = json.loads(path.read_text())
    document['external_operations'][0]['diagnostic_identity'] = None
    path.write_text(json.dumps(document))
    return result
gate.assess_root = changed_after_assessment
sys.argv = ['gate', '--managed-workspace-root', {str(self.root.parent)!r}, '--managed-repository', {self.root.name!r}]
raise SystemExit(gate.main())
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-c", script], capture_output=True, text=True, timeout=30)
        # Managed identity is the temporary repository's actual basename.
        document = json.loads((self.root / ".secpal/evidence-architecture.json").read_text())
        self.assertEqual(document["external_operations"][0]["diagnostic_identity"], None)
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_symlink_executable_cannot_select_another_package_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / "scripts"
            shutil.copytree(ROOT / "scripts/secpal_evidence_architecture", scripts / "secpal_evidence_architecture")
            (scripts / CLI.name).symlink_to(CLI)
            (Path(directory) / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
            result = subprocess.run([sys.executable, "-I", str(scripts / CLI.name), "--self-check"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
