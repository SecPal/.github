# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Command surface for inspectable, guarded work-graph replanning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import acceptance_criteria, github, github_replanning, replanning, resolver
from .model import Snapshot

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_MUTATION_FAILED = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secpal-work-graph-replan",
        description=(
            "Compile and apply finite graph-first replanning operations. "
            "Semantics: docs/work-graph-contract.md."
        ),
    )
    parser.add_argument("--gh", default="gh", help="Path to the gh executable")
    parser.add_argument("--timeout", type=float, default=github.DEFAULT_TIMEOUT_SECONDS)
    subcommands = parser.add_subparsers(dest="command", required=True)
    plan = subcommands.add_parser("plan", help="Read live state and emit an exact mutation plan")
    plan.add_argument("request", help="Request JSON path, or - for stdin")
    apply = subcommands.add_parser("apply", help="Apply one previously emitted exact plan")
    apply.add_argument("plan", help="Plan JSON path, or - for stdin")
    apply.add_argument(
        "--apply",
        action="store_true",
        required=True,
        help="Required acknowledgement that native GitHub relationships will change",
    )
    return parser


def _read_json(path: str, stdin) -> dict[str, Any]:
    try:
        text = stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise replanning.PlanError("input is not readable JSON") from exc
    if not isinstance(value, dict):
        raise replanning.PlanError("input must be a JSON object")
    return value


def _normalized_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = json.loads(json.dumps(value))
    request["current_issue"] = github.resolve_reference(str(request.get("current_issue", "")))
    operation = request.get("operation")
    if isinstance(operation, dict) and operation.get("existing_issue") is not None:
        operation["existing_issue"] = github.resolve_reference(str(operation["existing_issue"]))
    return request


def _merge_snapshots(*snapshots: Snapshot) -> Snapshot:
    nodes = {}
    for snapshot in snapshots:
        for key, node in snapshot.nodes.items():
            existing = nodes.get(key)
            if existing is not None and existing != node:
                raise replanning.PlanError("canonical readers returned inconsistent node state")
            nodes[key] = node
    return Snapshot(nodes)


def _load_plan_snapshot(
    adapter: github.GitHubReadAdapter, request: Mapping[str, Any]
) -> tuple[Snapshot, str]:
    current_key = str(request["current_issue"])
    initial, canonical_current = github.load_snapshot(
        adapter, current_key, include_reverse_dependencies=True
    )
    current = initial.require(canonical_current)
    if canonical_current != current_key:
        raise replanning.PlanError("current issue reference is not canonical")
    scope = current.parent or canonical_current
    base, canonical_scope = github.load_snapshot(
        adapter, scope, include_reverse_dependencies=True
    )
    if canonical_scope != scope:
        raise replanning.PlanError("owning scope reference is not canonical")
    snapshots = [base]
    existing = (request.get("operation") or {}).get("existing_issue")
    if existing and base.get(str(existing)) is None:
        external, canonical_external = github.load_snapshot(
            adapter, str(existing), include_reverse_dependencies=True
        )
        if canonical_external != existing:
            raise replanning.PlanError("existing prerequisite reference is not canonical")
        snapshots.append(external)
    return _merge_snapshots(*snapshots), scope


def _validate_new_issue_contracts(request: Mapping[str, Any]) -> None:
    operation = request.get("operation") or {}
    values = []
    if isinstance(operation.get("issue"), Mapping):
        values.append(operation["issue"])
    if isinstance(operation.get("epic"), Mapping):
        values.append(operation["epic"])
    children = operation.get("children")
    if isinstance(children, list):
        values.extend(item for item in children if isinstance(item, Mapping))
    if not values:
        return
    bodies = [str(value.get("body", "")) for value in values]
    structural = acceptance_criteria.parse(bodies)
    if any(not body.has_acceptance_criteria for body in structural):
        raise replanning.PlanError("every created issue must have canonical acceptance criteria")


def _emit(value: Mapping[str, Any], stream) -> None:
    print(json.dumps(value, indent=2, sort_keys=True), file=stream)


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "schema": replanning.SCHEMA,
        "status": "error",
        "error": {"code": code, "message": message},
    }


def main(argv: Sequence[str] | None = None, *, stdin=None, stdout=None, stderr=None) -> int:
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    arguments = _parser().parse_args(argv)
    adapter = github.GitHubReadAdapter(
        gh_executable=arguments.gh,
        timeout=arguments.timeout,
    )
    writer = None
    mutation_completed = False
    try:
        document = _read_json(arguments.request if arguments.command == "plan" else arguments.plan, stdin)
        request = _normalized_request(
            document if arguments.command == "plan" else document.get("request") or {}
        )
        _validate_new_issue_contracts(request)
        actor = adapter.viewer_login()
        snapshot, scope = _load_plan_snapshot(adapter, request)
        current_resolution = resolver.resolve(snapshot, scope)
        if not current_resolution.complete or current_resolution.structurally_malformed:
            raise replanning.PlanError("current canonical graph is incomplete or malformed")
        if arguments.command == "plan":
            plan = replanning.build_plan(snapshot, request, actor=actor)
            _emit(plan.to_dict(), stdout)
            return EXIT_OK

        plan = replanning.rebuild_plan(document, snapshot, actor=actor)
        mutation_adapter = github.GitHubGraphQLAdapter(
            gh_executable=arguments.gh,
            timeout=arguments.timeout,
        )
        writer = github_replanning.GitHubMutationWriter(mutation_adapter)
        aliases = replanning.apply_plan(plan, snapshot, actor=actor, writer=writer)
        mutation_completed = bool(plan.steps)
        post_snapshot, post_scope = _load_plan_snapshot(adapter, request)
        expected_post_scope = (
            aliases[plan.owner[1:]] if plan.owner and plan.owner.startswith("@") else scope
        )
        if post_scope != expected_post_scope:
            raise replanning.PlanError("owning scope changed during mutation")
        replanning.verify_applied(plan, post_snapshot, aliases)
        replanning.verify_unchanged_relationships(plan, snapshot, post_snapshot, aliases)
        resolution = resolver.resolve(post_snapshot, post_scope)
        if not resolution.complete or resolution.structurally_malformed:
            raise replanning.PlanError("resulting canonical graph is incomplete or malformed")
        _emit(
            {
                "schema": replanning.SCHEMA,
                "status": "applied",
                "actor": actor,
                "current_issue": plan.current_issue,
                "created": aliases,
                "validation_findings": [item.as_json() for item in resolution.findings],
            },
            stdout,
        )
        return EXIT_OK
    except (replanning.PlanError, github.GitHubError, acceptance_criteria.MarkdownParserUnavailable) as exc:
        mutation_started = mutation_completed or bool(writer and writer.mutation_index)
        code = "PARTIAL_MUTATION_FAILURE" if mutation_started else "REPLAN_BLOCKED"
        _emit(_error(code, str(exc)), stderr)
        return EXIT_MUTATION_FAILED if mutation_started else EXIT_INVALID
    except github_replanning.MutationError as exc:
        mutation_started = bool(writer and writer.mutation_index)
        code = "PARTIAL_MUTATION_FAILURE" if mutation_started else "REPLAN_BLOCKED"
        _emit(_error(code, str(exc)), stderr)
        return EXIT_MUTATION_FAILED if mutation_started else EXIT_INVALID
