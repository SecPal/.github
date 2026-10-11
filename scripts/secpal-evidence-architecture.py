#!/usr/bin/env -S python3 -I -S
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read-only declared-surface enforcement; never dispatch an external system."""

from __future__ import annotations

import os
import sys

if not sys.flags.isolated or not sys.flags.no_site:
    os.execv(sys.executable, [sys.executable, "-I", "-S", os.path.abspath(__file__), *sys.argv[1:]])

import argparse
import json
import importlib.util
import re
import stat
import subprocess
import tempfile
from pathlib import Path

SCRIPT_ROOT = Path(__file__).absolute().parent
PACKAGE = SCRIPT_ROOT / "secpal_evidence_architecture"
MAX_BYTES = 65_536
DECLARATION = ".secpal/evidence-architecture.json"
PROOFS = ".secpal/evidence-agreement-results.json"


class Unavailable(ValueError):
    """Required bounded repository-local evidence is unavailable."""


def closed_json(text):
    def unique(pairs):
        document = {}
        for key, value in pairs:
            if key in document:
                raise Unavailable()
            document[key] = value
        return document
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Unavailable()))


def read(root: Path, relative: str, *, optional=False):
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise Unavailable()
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise Unavailable()
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            os.close(directory)
            directory = child
        try:
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            if optional:
                return None
            raise
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise Unavailable()
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise Unavailable()
    return content.decode("utf-8")


def owned_package():
    # The executable owns the one import namespace. Isolated execution ignores
    # PYTHONPATH/site hooks, and a regular __init__ prevents namespace merging.
    source_path = Path(__file__).absolute()
    if any(path.is_symlink() for path in (source_path, *source_path.parents)):
        raise Unavailable()
    for filename in ("__init__.py", "governance.py", "execution.py", "markdown_references.mjs"):
        read(SCRIPT_ROOT, "secpal_evidence_architecture/" + filename)
    if any(name == "secpal_evidence_architecture" or name.startswith("secpal_evidence_architecture.")
           for name in sys.modules):
        raise Unavailable()
    # Load only this regular package; never add the scripts directory to the
    # general import path, where untracked files could shadow standard modules.
    # A fresh cache prefix prevents untracked .pyc bytes from replacing source.
    with tempfile.TemporaryDirectory(prefix="secpal-evidence-bytecode-") as cache:
        sys.pycache_prefix = cache
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location(
            "secpal_evidence_architecture", PACKAGE / "__init__.py",
            submodule_search_locations=[str(PACKAGE)],
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        spec.loader.exec_module(package)
        from secpal_evidence_architecture import execution, governance
    for module in (execution, governance):
        if Path(module.__file__).absolute().parent != PACKAGE:
            raise Unavailable()
    return governance, execution


def references(text):
    batch = isinstance(text, list)
    request = json.dumps({"documents" if batch else "markdown": text})
    if len(request.encode()) > 1_048_576:
        raise Unavailable()
    result = subprocess.run(
        ["node", str(PACKAGE / "markdown_references.mjs")],
        input=request, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=30, check=False,
        env={"PATH": os.environ.get("PATH", os.defpath)},
    )
    if result.returncode or len(result.stdout.encode()) > 1_048_576:
        raise Unavailable()
    value = closed_json(result.stdout)
    if not isinstance(value, dict) or set(value) != {"references"}:
        raise Unavailable()
    groups = value["references"] if batch else [value["references"]]
    if (not isinstance(groups, list) or batch and len(groups) != len(text)
            or any(not isinstance(group, list) or len(group) > 500
                   or any(type(item) is not str or len(item) > 4096 for item in group)
                   for group in groups)):
        raise Unavailable()
    return value["references"]


def finding(code, item_index=None):
    result = {"code": code, "rule": "docs/evidence-architecture-contract.md",
            "fact": "Declared architecture evidence failed the named closed boundary",
            "action": "Correct the declaration or its executable evidence before admission or dispatch",
            "mechanically_blocking": True, "technically_blocking": True}
    if item_index is not None:
        result["item_index"] = item_index
    return result


def load_surfaces(scope, execution):
    surfaces = {}
    sources = {}
    snapshots = []
    findings = []
    for source_root, source_document in scope:
        for surface in source_document["pure_surfaces"]:
            reference = surface["source"]
            if not isinstance(reference, str) or reference.count("#") != 1:
                raise Unavailable()
            path, function = reference.split("#")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", function):
                raise Unavailable()
            source = read(source_root, path)
            sources[source_document["repository"] + "/" + path] = source
            if len(sources) > 500 or sum(len(value.encode()) for value in sources.values()) > 1_048_576:
                raise Unavailable()
            snapshots.append((source_root, path, source))
            if surface["id"] in surfaces:
                raise Unavailable()
            try:
                surfaces[surface["id"]] = (surface["responsibility"], execution.pure_expression(source, function))
            except execution.PureSourceError:
                findings.append(finding("PURE_SOURCE_UNPROVEN", len(snapshots) - 1))
    for _, declared in scope:
        for invariant in declared["invariant_declarations"]:
            if invariant["surface"] not in surfaces or surfaces[invariant["surface"]][0] != "admission":
                findings.append(finding("INVARIANT_SURFACE_UNPROVEN"))
    return surfaces, sources, snapshots, findings


def execute_agreements(root, document, governance, execution, scope=None, prepared=None, proof_observation=None):
    scope = scope or [(root, document)]
    surfaces, sources, snapshots, source_findings = prepared or load_surfaces(scope, execution)
    findings = [] if prepared else list(source_findings)
    raw = read(root, PROOFS, optional=True)
    if proof_observation is not None and raw != proof_observation[0]:
        raise Unavailable()
    if raw is None:
        if any(read(source_root, path) != source for source_root, path, source in snapshots):
            raise Unavailable()
        return [], [], findings
    proof_document = closed_json(raw)
    if (not isinstance(proof_document, dict) or set(proof_document) != {"schema", "proofs"}
            or proof_document["schema"] != "secpal-evidence-agreement-execution/v1"
            or not isinstance(proof_document["proofs"], list) or len(proof_document["proofs"]) > 100):
        raise Unavailable()
    results, provenance, seen = [], [], set()
    bindings = {(entry.get("agreement_proof"), entry.get("owner"), entry["id"])
                for _, declared in scope for entry in declared["invariant_declarations"] if entry["role"] == "independent_enforcement"}
    invariant_surfaces = {entry["id"]: entry["surface"] for _, declared in scope for entry in declared["invariant_declarations"]}
    for proof_index, proof in enumerate(proof_document["proofs"]):
        if (not isinstance(proof, dict) or set(proof) != {"id", "owner", "enforcement", "left", "right", "cases"}
                or any(type(proof[key]) is not str for key in ("id", "owner", "enforcement"))
                or proof["id"] in seen):
            raise Unavailable()
        seen.add(proof["id"])
        # A mismatching proof never supplies authority for another enforcement.
        if (proof["id"], proof["owner"], proof["enforcement"]) not in bindings:
            continue
        cases = proof["cases"]
        if (not isinstance(cases, list) or not 2 <= len(cases) <= 100
                or any(not isinstance(case, dict) or set(case) != {"input", "expected"}
                       or type(case["expected"]) is not bool or not execution.bounded_value(case["input"])
                       for case in cases)
                or {case["expected"] for case in cases} != {True, False}):
            raise Unavailable()
        paths = []
        for side in (proof["left"], proof["right"]):
            if not isinstance(side, dict) or set(side) != {"normalization", "admission"}:
                raise Unavailable()
            pipeline = []
            for role in ("normalization", "admission"):
                name = side[role]
                if type(name) is not str or name not in surfaces or surfaces[name][0] != role:
                    raise Unavailable()
                pipeline.append(surfaces[name][1])
            paths.append(pipeline)
        if (proof["left"]["admission"] != invariant_surfaces.get(proof["owner"])
                or proof["right"]["admission"] != invariant_surfaces.get(proof["enforcement"])):
            raise Unavailable()
        passed = True
        for case in cases:
            try:
                for normalize, admit in paths:
                    normalized = normalize(case["input"])
                    if not execution.bounded_value(normalized) or admit(normalized) is not case["expected"]:
                        passed = False
            except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
                passed = False
        if not passed:
            findings.append(finding("AGREEMENT_EXECUTION_FAILED", proof_index))
        results.append(governance.VerifiedAgreementResult(proof["id"], proof["owner"], proof["enforcement"],
                                                          "passed" if passed else "failed"))
        provenance.append({"kind": "fresh_executable_agreement", "source_digest": execution.digest(sources),
                           "reviewed_input_digest": execution.digest(cases), "cases": len(cases)})
    # Bind execution to exactly the bytes read: no persistent status shortcut.
    if any(read(source_root, path) != source for source_root, path, source in snapshots) or read(root, PROOFS) != raw:
        raise Unavailable()
    return results, provenance, findings


def assess_root(root, repository, governance, execution, dispatch=False, defer_execution=False, baseline_observation=None):
    if not root.is_dir():
        raise Unavailable()
    baseline = read(root, "AGENTS.md")
    if baseline_observation is not None and baseline != baseline_observation[0]:
        raise Unavailable()
    raw = read(root, DECLARATION, optional=not dispatch)
    if baseline_observation is not None and raw != baseline_observation[2]:
        raise Unavailable()
    document = closed_json(raw) if raw is not None else None
    if document is not None and (not isinstance(document, dict) or document.get("repository") != repository):
        raise Unavailable()
    declaration = governance.runtime_declaration(document) if document is not None else None
    runtime = governance.assess_runtime_baseline(
        baseline_observation[1] if baseline_observation is not None else references(baseline), declared_mode=declaration["delegation"] if declaration else None,
        declared_authorities=declaration["generic_authorities"] if declaration else None,
    )
    # Shape validation precedes source loading or proof execution.
    initial = governance.assess_declarations([] if document is None else [document], dispatch_requested=dispatch)
    if any(item["code"] == "MALFORMED_DECLARATION" for item in initial["findings"]):
        return initial, [], [], []
    if defer_execution:
        initial["findings"] = runtime["findings"]
        return initial, [] if document is None else [document], [], []
    proofs, provenance, findings = execute_agreements(root, document, governance, execution) if document else ([], [], [])
    report = governance.assess_declarations([] if document is None else [document], proof_results=proofs,
                                           dispatch_requested=dispatch)
    report["findings"] = runtime["findings"] + findings + report["findings"]
    report["runtime_baseline"] = runtime["state"]
    report["agreement_execution"] = provenance
    if read(root, "AGENTS.md") != baseline or read(root, DECLARATION, optional=not dispatch) != raw:
        raise Unavailable()
    return report, [] if document is None else [document], proofs, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--repository")
    parser.add_argument("--managed-workspace-root", type=Path)
    parser.add_argument("--managed-repository", action="append", default=[])
    parser.add_argument("--dispatch", action="store_true", help="Validate dispatch admission; performs no dispatch")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    try:
        governance, execution = owned_package()
        if args.self_check:
            if args.repository_root or args.repository or args.managed_workspace_root or args.managed_repository or args.dispatch:
                raise Unavailable()
            references("`docs/work-graph-contract.md`")
            return 0
        if args.managed_workspace_root:
            if any(path.is_symlink() for path in (args.managed_workspace_root, *args.managed_workspace_root.parents)):
                raise Unavailable()
            names = args.managed_repository
            if (args.repository_root or args.repository or args.dispatch or not names
                    or len(names) > 100 or len(set(names)) != len(names)
                    or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."} for name in names)):
                raise Unavailable()
            documents, proofs, findings, provenance, scope, snapshots = [], [], [], [], [], []
            roots = [args.managed_workspace_root / name for name in names]
            baselines = [read(root, "AGENTS.md") for root in roots]
            reference_groups = references(baselines)
            for name, root, baseline, baseline_references in zip(names, roots, baselines, reference_groups):
                if root.is_symlink():
                    raise Unavailable()
                declaration = read(root, DECLARATION, optional=True)
                report, declared, verified, executed = assess_root(root, "SecPal/" + name, governance, execution, defer_execution=True, baseline_observation=(baseline, baseline_references, declaration))
                documents.extend(declared)
                scope.extend((root, document) for document in declared)
                snapshots.extend([(root, "AGENTS.md", baseline), (root, DECLARATION, declaration)])
                proofs.extend(verified)
                findings.extend(report["findings"])
                provenance.extend(executed)
            prepared = load_surfaces(scope, execution)
            findings.extend(prepared[3])
            snapshots.extend(prepared[2])
            for root, document in scope:
                proof_raw = read(root, PROOFS, optional=True)
                snapshots.append((root, PROOFS, proof_raw))
                verified, executed, source_findings = execute_agreements(root, document, governance, execution, scope, prepared, (proof_raw,))
                proofs.extend(verified)
                provenance.extend(executed)
                findings.extend(source_findings)
            if any(read(root, path, optional=path in {DECLARATION, PROOFS}) != observed
                   for root, path, observed in snapshots):
                raise Unavailable()
            report = governance.assess_declarations(documents, proof_results=proofs)
            report["findings"] = findings + report["findings"]
            report["agreement_execution"] = provenance
        else:
            if not args.repository_root or not args.repository or args.managed_repository:
                raise Unavailable()
            if any(path.is_symlink() for path in (args.repository_root, *args.repository_root.parents)):
                raise Unavailable()
            report, _, _, _ = assess_root(args.repository_root.resolve(strict=True), args.repository,
                                         governance, execution, args.dispatch)
        report["status"] = "blocked" if report["findings"] else "pass"
    except (OSError, ValueError, TypeError, KeyError, RecursionError, ImportError, subprocess.SubprocessError):
        report = {"schema": "secpal-evidence-architecture-assessment/v1", "status": "blocked",
                  "findings": [finding("DECLARATION_EVIDENCE_UNAVAILABLE")],
                  "human_judgment_status": "explicit_review_required", "claims_complete_architecture_judgment": False}
    output = json.dumps(report, indent=2, sort_keys=True)
    if len(output.encode()) > MAX_BYTES:
        output = json.dumps({"status": "blocked", "findings": [finding("ASSESSMENT_BOUND_EXCEEDED")],
                             "human_judgment_status": "explicit_review_required", "claims_complete_architecture_judgment": False})
        print(output)
        return 1
    print(output)
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
