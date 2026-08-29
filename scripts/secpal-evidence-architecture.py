#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Validate explicit evidence architecture before delivery or dispatch."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from secpal_evidence_architecture import governance


MAX_INPUT_BYTES = 65_536
DEFAULT_DECLARATION = ".secpal/evidence-architecture.json"
REFERENCE_PARSER = (
    Path(__file__).resolve().parent
    / "secpal_evidence_architecture"
    / "markdown_references.mjs"
)
_MANAGED_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class EvidenceUnavailable(RuntimeError):
    """Required closed local evidence cannot be read completely."""


def _root(value: str) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, ValueError) as error:
        raise EvidenceUnavailable("repository root is unavailable") from error
    if not root.is_dir():
        raise EvidenceUnavailable("repository root is not a directory")
    return root


def _inside(root: Path, relative: str, label: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or any(
        part in {"", ".", ".."} for part in relative_path.parts
    ):
        raise EvidenceUnavailable(f"{label} path is not a closed repository-relative path")
    candidate = root / relative_path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise EvidenceUnavailable(f"{label} path escapes the repository root") from error
    cursor = root
    for part in relative_path.parts:
        cursor /= part
        if cursor.is_symlink():
            raise EvidenceUnavailable(f"{label} path contains a symbolic link")
    return candidate


def _read_text(path: Path, label: str, *, required: bool) -> str | None:
    if not path.exists() and not required:
        return None
    try:
        if not path.is_file() or path.is_symlink():
            raise EvidenceUnavailable(f"{label} is not a repository-local regular file")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise EvidenceUnavailable(f"{label} exceeds the bounded input limit")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise EvidenceUnavailable(f"{label} is unavailable or malformed") from error


def _json_document(path: Path, label: str, *, required: bool) -> Any:
    text = _read_text(path, label, required=required)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise EvidenceUnavailable(f"{label} is unavailable or malformed") from error


def _references(markdown: str) -> tuple[str, ...]:
    try:
        completed = subprocess.run(
            ["node", str(REFERENCE_PARSER)],
            input=json.dumps({"markdown": markdown}),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceUnavailable("maintained Markdown reference parser is unavailable") from error
    if completed.returncode != 0:
        raise EvidenceUnavailable("maintained Markdown reference parser failed")
    try:
        document = json.loads(completed.stdout)
        if (
            not isinstance(document, dict)
            or set(document) != {"references"}
            or not isinstance(document["references"], list)
            or len(document["references"]) > governance.MAX_ITEMS
            or any(not isinstance(item, str) for item in document["references"])
        ):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise EvidenceUnavailable("maintained Markdown reference evidence is malformed") from None
    return tuple(document["references"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secpal-evidence-architecture")
    parser.add_argument("--repository-root")
    parser.add_argument("--repository")
    parser.add_argument("--managed-workspace-root")
    parser.add_argument("--managed-repository", action="append", default=[])
    parser.add_argument("--baseline", default="AGENTS.md")
    parser.add_argument("--declaration", default=DEFAULT_DECLARATION)
    parser.add_argument("--proof-results")
    parser.add_argument(
        "--declared-delegation",
        choices=("direct", "transitive_work_graph"),
    )
    parser.add_argument("--dispatch", action="store_true")
    return parser


def _single_assessment(arguments: argparse.Namespace) -> dict[str, Any]:
    if (
        not arguments.repository_root
        or not arguments.repository
        or arguments.managed_workspace_root
        or arguments.managed_repository
    ):
        raise EvidenceUnavailable("single-repository mode requires one root and repository")
    root = _root(arguments.repository_root)
    baseline_path = _inside(root, arguments.baseline, "runtime baseline")
    baseline = _read_text(baseline_path, "runtime baseline", required=True)
    assert baseline is not None
    references = _references(baseline)

    declaration_path = _inside(root, arguments.declaration, "declaration")
    declaration = _json_document(
        declaration_path, "evidence architecture declaration", required=arguments.dispatch
    )
    if declaration is not None and (
        not isinstance(declaration, dict)
        or declaration.get("repository") != arguments.repository
    ):
        raise EvidenceUnavailable(
            "declaration repository identity does not match the trusted caller"
        )
    declared_runtime = (
        governance.runtime_declaration(declaration)
        if declaration is not None
        else None
    )
    if (
        declared_runtime is not None
        and arguments.declared_delegation is not None
        and declared_runtime["delegation"] != arguments.declared_delegation
    ):
        raise EvidenceUnavailable("runtime delegation inputs contradict each other")
    runtime = governance.assess_runtime_baseline(
        references,
        declared_mode=(
            declared_runtime["delegation"]
            if declared_runtime is not None
            else arguments.declared_delegation
        ),
        declared_authorities=(
            declared_runtime["generic_authorities"]
            if declared_runtime is not None
            else None
        ),
    )
    proofs = None
    if arguments.proof_results:
        proof_path = _inside(root, arguments.proof_results, "agreement results")
        proofs = _json_document(proof_path, "agreement results", required=True)
    assessment = governance.assess_declarations(
        [] if declaration is None else [declaration],
        proof_results=proofs,
        dispatch_requested=arguments.dispatch,
    )
    assessment["runtime_baseline"] = runtime
    assessment["findings"] = [*runtime["findings"], *assessment["findings"]]
    assessment["status"] = "blocked" if assessment["findings"] else "pass"
    return assessment


def _managed_assessment(arguments: argparse.Namespace) -> dict[str, Any]:
    if (
        not arguments.managed_workspace_root
        or arguments.repository_root
        or arguments.repository
        or arguments.dispatch
        or arguments.proof_results
        or arguments.declared_delegation
        or arguments.baseline != "AGENTS.md"
        or arguments.declaration != DEFAULT_DECLARATION
    ):
        raise EvidenceUnavailable("managed mode has incompatible single-repository options")
    names = arguments.managed_repository
    if (
        not names
        or len(names) > governance.MAX_DOCUMENTS
        or len(set(names)) != len(names)
        or any(not _MANAGED_NAME.fullmatch(name) for name in names)
    ):
        raise EvidenceUnavailable("managed repository identities are unavailable or malformed")

    workspace = _root(arguments.managed_workspace_root)
    declarations: list[Any] = []
    combined_results: dict[str, Any] = {
        "schema": governance.PROOF_SCHEMA,
        "results": [],
    }
    runtime_baselines: dict[str, Any] = {}
    for name in names:
        root = _inside(workspace, name, "managed repository")
        if not root.is_dir():
            raise EvidenceUnavailable("managed repository root is unavailable")
        repository = f"SecPal/{name}"
        baseline = _read_text(root / "AGENTS.md", "runtime baseline", required=True)
        assert baseline is not None
        references = _references(baseline)

        declaration_path = _inside(root, DEFAULT_DECLARATION, "declaration")
        declaration = _json_document(
            declaration_path, "evidence architecture declaration", required=False
        )
        if declaration is None:
            runtime_baselines[repository] = governance.assess_runtime_baseline(
                references
            )
            continue
        if (
            not isinstance(declaration, dict)
            or declaration.get("repository") != repository
        ):
            raise EvidenceUnavailable(
                "declaration repository identity does not match the managed repository"
            )
        declared_runtime = governance.runtime_declaration(declaration)
        runtime_baselines[repository] = governance.assess_runtime_baseline(
            references,
            declared_mode=declared_runtime["delegation"],
            declared_authorities=declared_runtime["generic_authorities"],
        )
        declarations.append(declaration)
        result_path = _inside(
            root,
            ".secpal/evidence-agreement-results.json",
            "agreement results",
        )
        results = _json_document(result_path, "agreement results", required=False)
        if results is not None:
            if not isinstance(results, dict) or not isinstance(results.get("results"), list):
                raise EvidenceUnavailable("agreement results are unavailable or malformed")
            if results.get("schema") != governance.PROOF_SCHEMA:
                raise EvidenceUnavailable("agreement result schema is unsupported")
            combined_results["results"].extend(results["results"])

    assessment = governance.assess_declarations(
        declarations,
        proof_results=combined_results,
    )
    runtime_findings = [
        finding
        for result in runtime_baselines.values()
        for finding in result["findings"]
    ]
    assessment["runtime_baselines"] = runtime_baselines
    assessment["findings"] = [*runtime_findings, *assessment["findings"]]
    assessment["status"] = "blocked" if assessment["findings"] else "pass"
    return assessment


def unavailable_report(message: str, *, dispatch_requested: bool) -> dict[str, Any]:
    fact = "Required architecture evidence is unavailable; raw input was not retained"
    return {
        "schema": "secpal-evidence-architecture-assessment/v1",
        "semantics": governance.CONTRACT,
        "status": "blocked",
        "dispatch_requested": dispatch_requested,
        "runtime_baseline": {"state": "UNAVAILABLE", "findings": []},
        "findings": [
            {
                "code": "DECLARATION_EVIDENCE_UNAVAILABLE",
                "rule": "evidence architecture sections 1, 2, and 4",
                "fact": fact,
                "action": "Restore complete bounded declaration and baseline evidence.",
                "technically_blocking": True,
                "mechanically_blocking": True,
            }
        ],
        "human_judgment_status": "explicit_review_required",
        "claims_complete_architecture_judgment": False,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        assessment = (
            _managed_assessment(arguments)
            if arguments.managed_workspace_root
            else _single_assessment(arguments)
        )
    except (EvidenceUnavailable, OSError, TypeError, ValueError) as error:
        assessment = unavailable_report(str(error), dispatch_requested=arguments.dispatch)

    print(json.dumps(assessment, indent=2, sort_keys=True))
    for finding in assessment["findings"]:
        message = f"{finding['code']}: {finding['fact']} ({finding['rule']})"
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=SecPal evidence architecture gate::{escaped}", file=sys.stderr)
    return 1 if assessment["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
