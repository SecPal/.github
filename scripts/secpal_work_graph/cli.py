# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Deterministic rendering and command surface of the work-graph resolver.

Every command derives its result from one resolved model, so the JSON and the
human-readable rendering can never disagree. Semantics:
docs/work-graph-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping, Sequence

from . import github, resolver
from .acceptance_criteria import MarkdownParserUnavailable
from .model import Snapshot

SCHEMA = "secpal-work-graph/v1"
CONTRACT = "docs/work-graph-contract.md"

EXIT_OK = 0
EXIT_REPORTED = 1
EXIT_USAGE = 2
EXIT_GITHUB = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secpal-work-graph",
        description=(
            "Read-only resolution of the GitHub-native SecPal work graph. "
            f"Semantics: {CONTRACT}."
        ),
    )
    parser.add_argument("--repo", help="Default owner/repo for bare issue numbers.")
    parser.add_argument(
        "--format", choices=("json", "text"), default="json", help="Output format (default: json)."
    )
    parser.add_argument("--gh", default="gh", help="Path to the gh executable.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=github.DEFAULT_TIMEOUT_SECONDS,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=github.DEFAULT_MAX_NODES,
        help="Maximum number of issues read in one invocation.",
    )

    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("show", "Print the normalized graph for a scope root."),
        ("validate", "Report machine-derivable structural findings for a scope root."),
        ("ready", "List every READY delivery leaf under a scope root."),
    ):
        subparser = commands.add_parser(name, help=help_text)
        subparser.add_argument("root", help="Scope root as owner/repo#number, #number, or issue URL.")

    next_parser = commands.add_parser("next", help="Select the next leaf for one executor.")
    next_parser.add_argument("root", help="Scope root as owner/repo#number, #number, or issue URL.")
    next_parser.add_argument(
        "--executor",
        help=(
            "Executor identity for claim filtering. Defaults to the authenticated "
            "gh identity, which resolves the invocation-context input."
        ),
    )

    issue_parser = commands.add_parser(
        "validate-issue", help="Explain the resolved state of a single issue."
    )
    issue_parser.add_argument("issue", help="Issue as owner/repo#number, #number, or issue URL.")
    return parser


def _claim_json(claims) -> list[dict[str, str]]:
    return [
        {"executor": claim.executor, "pull_request": claim.pull_request, "url": claim.url}
        for claim in claims
    ]


def _node_json(resolution: resolver.Resolution, key: str) -> dict[str, Any]:
    node = resolution.snapshot.nodes[key]
    state = resolution.states[key]
    return {
        "key": key,
        "repository": node.repository,
        "number": node.number,
        "title": node.title,
        "url": node.url,
        "state": node.state,
        "state_reason": node.state_reason,
        "parent": node.parent,
        "parent_observable": node.parent_observable,
        "children": list(node.children),
        "blocked_by": list(node.blocked_by),
        "priority_labels": list(node.priority_labels),
        "priority_labels_observable": node.priority_labels_observable,
        "has_acceptance_criteria": node.has_acceptance_criteria,
        "path": list(state.path),
        "depth": state.depth,
        "leaf": state.leaf,
        "open": state.open,
        "done": state.done,
        "blocked": state.blocked,
        "ready": state.ready,
        "active": state.active,
        "malformed": state.malformed,
        "reasons": list(state.reasons),
        "priority_rank": state.priority_rank,
        "claims": _claim_json(state.claims),
    }


def _envelope(command: str, resolution: resolver.Resolution) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "semantics": CONTRACT,
        "command": command,
        "status": "resolved",
        "scope_root": resolution.scope_root,
        "complete": resolution.complete,
        "findings": [finding.as_json() for finding in resolution.findings],
    }


def _not_ready_leaves(resolution: resolver.Resolution) -> list[dict[str, Any]]:
    return [
        {"key": state.key, "reasons": list(state.reasons)}
        for state in resolution.resolved_states()
        if state.leaf and state.open and not state.ready
    ]


def build_document(command: str, resolution: resolver.Resolution, *, executor: str | None) -> dict[str, Any]:
    """Derive one command's machine output from the resolved model."""
    document = _envelope(command, resolution)

    if command == "show":
        document["ancestors"] = [
            {
                "key": key,
                "state": resolution.snapshot.require(key).state,
                "resolved": resolution.snapshot.require(key).resolved,
            }
            for key in resolution.ancestors
        ]
        document["nodes"] = [_node_json(resolution, state.key) for state in resolution.resolved_states()]
    elif command == "validate":
        document["finding_count"] = len(resolution.findings)
    elif command == "ready":
        document["ready"] = [_node_json(resolution, key) for key in resolution.ready_leaves()]
        document["not_ready_leaves"] = _not_ready_leaves(resolution)
    elif command == "next":
        result = resolution.select_next(executor or "")
        document["executor"] = executor
        document["selected"] = _node_json(resolution, result.selected) if result.selected else None
        document["no_selection_reason"] = result.no_selection_reason
        document["incomplete_reason"] = result.incomplete_reason
        document["candidates"] = list(result.candidates)
        document["ready"] = list(resolution.ready_leaves())
        if result.incomplete_reason is not None:
            # Not a canonical no-selection result: the declared inputs were not
            # fully observable, so no canonical `NEXT` exists for this scope.
            document["status"] = "incomplete_inputs"
        if result.no_selection_reason == resolver.NO_READY_LEAF:
            document["not_ready_leaves"] = _not_ready_leaves(resolution)
    elif command == "validate-issue":
        key = resolution.scope_root
        document["issue"] = _node_json(resolution, key)
        document["findings"] = [
            finding.as_json() for finding in resolution.findings if finding.node == key
        ]
    return document


def _render_text(document: Mapping[str, Any]) -> str:
    lines = [f"{document['command']} {document['scope_root']}  (semantics: {CONTRACT})"]
    command = document["command"]

    if command == "show":
        for ancestor in document["ancestors"]:
            lines.append(f"  ancestor {ancestor['key']} [{ancestor['state']}]")
        for node in document["nodes"]:
            marker = "READY" if node["ready"] else ",".join(node["reasons"]) or node["state"]
            path = ".".join(str(position) for position in node["path"]) or "-"
            lines.append(f"  {path:<10} {node['key']:<28} {marker}")
    elif command == "ready":
        for node in document["ready"]:
            lines.append(f"  READY {node['key']} {node['title']}")
        for entry in document["not_ready_leaves"]:
            lines.append(f"  ---   {entry['key']} {','.join(entry['reasons'])}")
    elif command == "next":
        if document["selected"]:
            lines.append(f"  NEXT {document['selected']['key']} {document['selected']['title']}")
        elif document["incomplete_reason"]:
            lines.append(f"  no canonical NEXT: {document['incomplete_reason']}")
        else:
            lines.append(f"  no selection: {document['no_selection_reason']}")
        for entry in document.get("not_ready_leaves", []):
            lines.append(f"  ---  {entry['key']} {','.join(entry['reasons'])}")
    elif command == "validate-issue":
        issue = document["issue"]
        predicates = [name for name in ("open", "done", "blocked", "ready", "active", "malformed") if issue[name]]
        lines.append(f"  {issue['key']} {' '.join(predicates) or 'none'}")
        if issue["reasons"]:
            lines.append(f"  not ready: {', '.join(issue['reasons'])}")

    if document["findings"]:
        lines.append("  findings:")
        for finding in document["findings"]:
            detail = f" ({finding['detail']})" if finding["detail"] else ""
            lines.append(f"    {finding['code']} {finding['node']}{detail}")
    elif command == "validate":
        lines.append("  no structural findings")
    if not document["complete"]:
        lines.append("  incomplete: required graph data could not be resolved")
    return "\n".join(lines)


def _emit(document: Mapping[str, Any], output_format: str, stream) -> None:
    if output_format == "json":
        print(json.dumps(document, indent=2, sort_keys=True), file=stream)
    else:
        print(_render_text(document), file=stream)


def _failure(command: str, code: str, message: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "semantics": CONTRACT,
        "command": command,
        "status": "error",
        "error": {"code": code, "message": message},
    }


def _exit_code(command: str, document: Mapping[str, Any]) -> int:
    if command == "validate":
        return EXIT_REPORTED if document["findings"] else EXIT_OK
    if command == "validate-issue":
        return EXIT_OK if document["issue"]["ready"] else EXIT_REPORTED
    if command == "next":
        # Both canonical no-selection reasons are ordinary answers; incomplete
        # inputs are not.
        return EXIT_REPORTED if document["incomplete_reason"] else EXIT_OK
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, stdout=None, stderr=None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    arguments = parser.parse_args(argv)
    command = arguments.command
    reference = getattr(arguments, "root", None) or arguments.issue

    try:
        scope_root = github.resolve_reference(reference, default_repository=arguments.repo)
    except ValueError as error:
        _emit(_failure(command, "invalid_reference", str(error)), arguments.format, stderr)
        return EXIT_USAGE

    adapter = github.GitHubReadAdapter(
        gh_executable=arguments.gh, timeout=arguments.timeout, max_nodes=arguments.max_nodes
    )
    try:
        executor = getattr(arguments, "executor", None)
        if command == "next" and not executor:
            executor = adapter.viewer_login()
        snapshot: Snapshot = github.load_snapshot(adapter, scope_root)
    except github.GitHubError as error:
        _emit(_failure(command, "github_unavailable", str(error)), arguments.format, stderr)
        return EXIT_GITHUB
    except MarkdownParserUnavailable as error:
        _emit(_failure(command, "markdown_parser_unavailable", str(error)), arguments.format, stderr)
        return EXIT_GITHUB

    try:
        resolution = resolver.resolve(snapshot, scope_root)
    except resolver.ScopeRootUnresolved as error:
        _emit(_failure(command, "unresolved_scope_root", str(error)), arguments.format, stderr)
        return EXIT_GITHUB

    document = build_document(command, resolution, executor=executor)
    _emit(document, arguments.format, stdout)
    return _exit_code(command, document)
