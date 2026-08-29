#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""#674 assessment with the opt-in #735 hard pull-request boundary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secpal_work_graph import github, pr_advisory, resolver  # noqa: E402
from secpal_work_graph.acceptance_criteria import MarkdownParserUnavailable  # noqa: E402

PR_QUERY = """query AdvisoryPullRequest($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequest(number: $number) {
      number
      url
      body
      additions
      deletions
      changedFiles
      closingIssuesReferences(first: 100) {
        totalCount
        pageInfo { hasNextPage }
        nodes { number repository { nameWithOwner } }
      }
    }
  }
}"""


def _closed_mapping(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{label} contains unknown or missing fields")
    return dict(value)


def _load_assessment(path: str | None) -> tuple:
    if path is None:
        return (), (), (), pr_advisory.ReviewSmells()
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    item = _closed_mapping(
        document,
        {"schema", "observations", "feedback", "lifecycle_claims", "review_smells"},
        "assessment",
    )
    if item["schema"] != pr_advisory.SCHEMA:
        raise ValueError("assessment schema is unsupported")
    observations = tuple(
        pr_advisory.Observation(**_closed_mapping(entry, {"kind", "evidence"}, "observation"))
        for entry in item["observations"]
    )
    feedback = tuple(
        pr_advisory.FeedbackClaim(
            **_closed_mapping(
                entry,
                {
                    "finding_id",
                    "classification",
                    "reported_technically_blocking",
                    "reported_mechanically_blocking",
                },
                "feedback claim",
            )
        )
        for entry in item["feedback"]
    )
    lifecycle = tuple(
        pr_advisory.LifecycleClaim(
            **_closed_mapping(
                entry,
                {"kind", "evidence", "technically_blocking", "mechanically_blocking"},
                "lifecycle claim",
            )
        )
        for entry in item["lifecycle_claims"]
    )
    smells = pr_advisory.ReviewSmells(
        **_closed_mapping(
            item["review_smells"], {"tests", "changed_lines", "mutations"}, "review smells"
        )
    )
    return observations, feedback, lifecycle, smells


def _pull_request(adapter: github.GitHubReadAdapter, repository: str, number: int) -> dict:
    owner, name = repository.split("/", 1)
    response = adapter.query(PR_QUERY, {"owner": owner, "name": name, "number": number})
    if response.errors:
        raise github.GitHubError("pull-request advisory evidence is unreadable")
    repository_payload = (response.data or {}).get("repository")
    pull = (repository_payload or {}).get("pullRequest")
    if not repository_payload or not pull:
        raise github.GitHubError("pull request is missing or inaccessible")
    if repository_payload.get("nameWithOwner") != repository:
        raise github.GitHubError("pull-request repository identity changed")
    connection = pull.get("closingIssuesReferences") or {}
    if connection.get("pageInfo", {}).get("hasNextPage"):
        raise github.GitHubError("closing-issue references exceed the bounded gate input")
    nodes = connection.get("nodes") or []
    if int(connection.get("totalCount", -1)) != len(nodes):
        raise github.GitHubError("closing-issue references are incomplete")
    return pull


def _issue_key(node: Mapping[str, Any]) -> str:
    repository = (node.get("repository") or {}).get("nameWithOwner")
    number = node.get("number")
    if not isinstance(repository, str) or not isinstance(number, int):
        raise github.GitHubError("closing-issue identity is incomplete")
    return f"{repository}#{number}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secpal-pr-advisory")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int, default=os.environ.get("PR_NUMBER"))
    parser.add_argument("--primary-issue", help="Repository-qualified primary issue override.")
    parser.add_argument("--assessment", help="Optional explicit judgment evidence JSON.")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Fail when the maintained #735 hard work-graph rules have findings.",
    )
    parser.add_argument("--gh", default="gh")
    parser.add_argument("--timeout", type=float, default=30)
    return parser


def main(argv=None, *, stdout=None, stderr=None) -> int:
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    arguments = build_parser().parse_args(argv)
    if not arguments.repo or "/" not in arguments.repo or not arguments.pr or arguments.pr < 1:
        print("repository and positive pull-request number are required", file=stderr)
        return 2
    adapter = github.GitHubReadAdapter(
        gh_executable=arguments.gh, timeout=arguments.timeout
    )
    try:
        pull = _pull_request(adapter, arguments.repo, arguments.pr)
        connection = pull["closingIssuesReferences"]
        closing = tuple(_issue_key(node) for node in connection.get("nodes") or [])
        if not closing and not arguments.primary_issue:
            document = {
                "schema": pr_advisory.SCHEMA,
                "semantics": pr_advisory.CONTRACT,
                "pull_request": pull["url"],
                "advisory": True,
                "status": "not_a_delivery_pr",
                "owning_issue": None,
                "graph_state": None,
                "findings": [],
                "review_smells": {
                    "tests": 0,
                    "changed_lines": int(pull.get("additions", 0)) + int(pull.get("deletions", 0)),
                    "mutations": 0,
                },
            }
        else:
            primary = arguments.primary_issue or sorted(closing)[0]
            issue_keys = tuple(dict.fromkeys((primary, *closing)))
            graphs: dict[str, resolver.Resolution] = {}
            for issue in issue_keys:
                snapshot, canonical = github.load_snapshot(adapter, issue)
                if canonical != issue:
                    raise github.GitHubError("closing-issue canonical identity changed")
                graphs[issue] = resolver.resolve(snapshot, canonical)
            observations, feedback, lifecycle, smells = _load_assessment(arguments.assessment)
            if arguments.assessment is None:
                smells = pr_advisory.ReviewSmells(
                    changed_lines=int(pull.get("additions", 0)) + int(pull.get("deletions", 0))
                )
            document = pr_advisory.assess(
                pull_request=pull["url"],
                pull_request_key=f"{arguments.repo}#{arguments.pr}",
                pull_request_body=str(pull.get("body") or ""),
                primary_issue=primary,
                closing_issues=closing,
                graph=graphs[primary],
                closing_graphs=graphs,
                observations=observations,
                feedback=feedback,
                lifecycle_claims=lifecycle,
                smells=smells,
                enforced_primary_override=(
                    arguments.primary_issue if arguments.enforce else None
                ),
            )
    except (OSError, ValueError, github.GitHubError, MarkdownParserUnavailable, json.JSONDecodeError) as error:
        print(f"advisory gate evidence unavailable: {error}", file=stderr)
        return 3

    if arguments.enforce:
        document = pr_advisory.enforced_projection(document)
    hard_findings = pr_advisory.hard_gate_findings(document)
    document["gate_status"] = (
        "blocked" if arguments.enforce and hard_findings else "pass"
    )
    document["enforced"] = arguments.enforce
    document["hard_finding_count"] = len(hard_findings)
    document["hard_finding_codes"] = [finding["code"] for finding in hard_findings]
    document["human_judgment_status"] = (
        "reviewed_evidence_supplied"
        if arguments.assessment is not None
        else "explicit_review_required"
    )
    document["human_judgment_rule"] = "work-graph section 7.2"
    document["human_judgment_finding_codes"] = [
        finding["code"]
        for finding in document["findings"]
        if finding["code"] in pr_advisory.HUMAN_JUDGMENT_CODES
    ]
    print(json.dumps(document, indent=2, sort_keys=True), file=stdout)
    for finding in document["findings"]:
        is_hard = arguments.enforce and finding in hard_findings
        level = "error" if is_hard else "warning"
        title = "SecPal work-graph gate" if is_hard else "SecPal PR advisory"
        message = (
            f"{finding['code']}: {finding['evidence']}; "
            f"{finding['action']} ({finding['rule']})"
        )
        escaped = (
            message.replace("%", "%25")
            .replace("\r", "%0D")
            .replace("\n", "%0A")
        )
        print(f"::{level} title={title}::{escaped}", file=stderr)
    return 1 if arguments.enforce and hard_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
