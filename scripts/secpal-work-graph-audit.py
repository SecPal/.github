#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Read-only advisory audit entrypoint; it never mutates GitHub.

Discovery is deliberately narrow: native containment participants and legacy
epic, relationship-mirror, or task-list signals.  Legacy signals select audit
candidates only; they are never turned into native graph edges.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secpal_work_graph import audit, github
from secpal_work_graph.acceptance_criteria import MarkdownParserUnavailable, parse

QUERY = """query WorkGraphAuditIssues($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $cursor, states: [OPEN, CLOSED], orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        repository { nameWithOwner }
        parent { number repository { nameWithOwner } }
        subIssues(first: 1) { totalCount }
        labels(first: 100) { nodes { name } }
        blockedBy(first: 1) { totalCount }
        blocking(first: 1) { totalCount }
        closedByPullRequestsReferences(first: 100, includeClosedPrs: true) {
          totalCount
          nodes { number repository { nameWithOwner } }
        }
      }
    }
  }
}"""


def _discover(adapter, repository: str):
    owner, name = repository.split("/", 1)
    cursor = None
    rows = []
    while True:
        response = adapter.query(
            QUERY, {"owner": owner, "name": name, "cursor": cursor}
        )
        if response.errors:
            raise github.GitHubError("audit discovery data is unreadable")
        repository_payload = (response.data or {}).get("repository")
        connection = (repository_payload or {}).get("issues")
        if not repository_payload or not connection:
            raise github.GitHubError(
                "audit discovery repository or issues connection is unreadable"
            )
        rows.extend(connection.get("nodes") or [])
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return rows
        cursor = page.get("endCursor")
        if not cursor:
            raise github.GitHubError("issues pagination has no cursor")


def _canonical_repository(rows, requested_repository: str) -> str:
    identities = {
        ((row.get("repository") or {}).get("nameWithOwner")) for row in rows
    }
    if rows and (None in identities or len(identities) != 1):
        raise github.GitHubError("audit discovery repository identity is unreadable")
    return str(next(iter(identities))) if rows else requested_repository


def _closing_pull_requests(row) -> tuple[str, ...]:
    references = []
    for pull in (
        (row.get("closedByPullRequestsReferences") or {}).get("nodes") or []
    ):
        repository = (pull.get("repository") or {}).get("nameWithOwner")
        number = pull.get("number")
        if repository and number is not None:
            references.append(f"{repository}#{int(number)}")
    return tuple(sorted(references))


def _advisory_facts(row, structural, repository: str) -> audit.AdvisoryIssueFacts:
    labels = {
        str(item.get("name", "")).casefold()
        for item in ((row.get("labels") or {}).get("nodes") or [])
    }
    parent = row.get("parent")
    children = int((row.get("subIssues") or {}).get("totalCount") or 0)
    closing_pull_requests = _closing_pull_requests(row)
    native = bool(parent) or bool(children)
    return audit.AdvisoryIssueFacts(
        key=f"{repository}#{int(row['number'])}",
        repository=repository,
        discovery_source=(
            "native" if native or closing_pull_requests else "legacy_candidate"
        ),
        relationship_mirrors=structural.relationship_mirrors,
        has_status_checklist=structural.has_status_checklist,
        legacy_epic_candidate=(
            "epic" in labels
            or str(row.get("title", "")).casefold().startswith("[epic]")
        ),
        native_children_count=children,
        closing_pull_requests=closing_pull_requests,
        blocked_by_count=int((row.get("blockedBy") or {}).get("totalCount") or 0),
        blocking_count=int((row.get("blocking") or {}).get("totalCount") or 0),
    )


def _native_root(row, repository: str) -> str | None:
    parent = row.get("parent")
    children = int((row.get("subIssues") or {}).get("totalCount") or 0)
    blocked_by = int((row.get("blockedBy") or {}).get("totalCount") or 0)
    parent_repository = ((parent or {}).get("repository") or {}).get(
        "nameWithOwner"
    )
    if (
        (not parent and (children or blocked_by))
        or parent_repository not in (None, repository)
    ):
        return f"{repository}#{int(row['number'])}"
    return None


def _audit_repository(adapter, requested_repository: str) -> dict:
    rows = _discover(adapter, requested_repository)
    repository = _canonical_repository(rows, requested_repository)
    structural = parse([row.get("body") for row in rows])
    advisory_facts = [
        _advisory_facts(row, fact, repository)
        for row, fact in zip(rows, structural)
    ]
    findings = [
        finding
        for facts in advisory_facts
        for finding in audit.classify_advisory(facts)
    ]
    native_roots = sorted(
        {
            root
            for row in rows
            if (root := _native_root(row, repository)) is not None
        }
    )
    for native_root in native_roots:
        snapshot, canonical_root = github.load_snapshot(adapter, native_root)
        findings.extend(
            audit.classify_native(
                snapshot,
                canonical_root,
                repository=repository,
            )
        )
    findings = audit.deduplicate_findings(findings)
    return {
        "repository": repository,
        "status": "findings" if findings else "clean",
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secpal-work-graph-audit")
    parser.add_argument("--repo", action="append", dest="repos")
    parser.add_argument("--gh", default="gh")
    parser.add_argument("--timeout", type=float, default=30)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    repositories = tuple(arguments.repos or audit.DEFAULT_REPOSITORIES)
    if any("/" not in repository for repository in repositories):
        return 2
    adapter = github.GitHubReadAdapter(
        gh_executable=arguments.gh, timeout=arguments.timeout
    )
    results = []
    failed = False
    for repository in repositories:
        try:
            results.append(_audit_repository(adapter, repository))
        except (github.GitHubError, MarkdownParserUnavailable) as error:
            failed = True
            results.append(
                {
                    "repository": repository,
                    "status": "unavailable",
                    "findings": [],
                    "error": str(error),
                }
            )
    print(json.dumps(audit.document(results), sort_keys=True, indent=2))
    return 3 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
