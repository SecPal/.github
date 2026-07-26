#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Resolve explicitly named, already-fixed pull-request review threads.

This command deliberately separates thread resolution from merge readiness.
It verifies the pull request, expected head, and exact target thread identities,
then resolves each still-open target once. It does not inspect CI, reactions,
unrelated feedback, signatures, local validation receipts, or mergeability.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Sequence

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OID = re.compile(r"^[0-9a-fA-F]{40}$")
THREAD_ID = re.compile(r"^PRRT_[A-Za-z0-9_-]+$")

READ_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      state
      headRefOid
      reviewThreads(first: 100, after: $after) {
        nodes { id isResolved }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""


class ResolutionError(RuntimeError):
    """The requested bounded resolution cannot be proven safe."""


@dataclass(frozen=True)
class ThreadState:
    thread_id: str
    is_resolved: bool


@dataclass(frozen=True)
class PullRequestState:
    state: str
    head_sha: str
    threads: dict[str, ThreadState]


def _run_gh(arguments: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ["gh", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "gh failed").strip()
        raise ResolutionError(detail)
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ResolutionError("gh returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ResolutionError("gh returned an unexpected response")
    return value


def _graphql(
    query: str,
    variables: dict[str, str | int],
    runner: Callable[[Sequence[str]], dict[str, Any]] = _run_gh,
) -> dict[str, Any]:
    arguments: list[str] = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        arguments.extend([flag, f"{key}={value}"])
    payload = runner(arguments)
    if payload.get("errors"):
        raise ResolutionError("GitHub GraphQL request failed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ResolutionError("GitHub GraphQL response has no data")
    return data


def read_pull_request(
    repository: str,
    number: int,
    required_thread_ids: set[str],
    runner: Callable[[Sequence[str]], dict[str, Any]] = _run_gh,
) -> PullRequestState:
    owner, name = repository.split("/", 1)
    threads: dict[str, ThreadState] = {}
    after: str | None = None
    state: str | None = None
    head_sha: str | None = None

    while True:
        variables: dict[str, str | int] = {
            "owner": owner,
            "name": name,
            "number": number,
        }
        if after is not None:
            variables["after"] = after
        data = _graphql(READ_QUERY, variables, runner)
        repository_value = data.get("repository")
        pull_request = (
            repository_value.get("pullRequest")
            if isinstance(repository_value, dict)
            else None
        )
        if not isinstance(pull_request, dict):
            raise ResolutionError("pull request was not found")

        current_state = pull_request.get("state")
        current_head = pull_request.get("headRefOid")
        if not isinstance(current_state, str) or not isinstance(current_head, str):
            raise ResolutionError("pull request identity is incomplete")
        if state is None:
            state = current_state
            head_sha = current_head.lower()
        elif state != current_state or head_sha != current_head.lower():
            raise ResolutionError("pull request changed while reading target threads")

        connection = pull_request.get("reviewThreads")
        if not isinstance(connection, dict):
            raise ResolutionError("review thread connection is missing")
        nodes = connection.get("nodes")
        if not isinstance(nodes, list):
            raise ResolutionError("review thread list is malformed")
        for node in nodes:
            if not isinstance(node, dict):
                raise ResolutionError("review thread entry is malformed")
            thread_id = node.get("id")
            is_resolved = node.get("isResolved")
            if not isinstance(thread_id, str) or not isinstance(is_resolved, bool):
                raise ResolutionError("review thread identity is incomplete")
            threads[thread_id] = ThreadState(thread_id, is_resolved)

        if required_thread_ids.issubset(threads):
            break
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            raise ResolutionError("review thread pagination is missing")
        if not page_info.get("hasNextPage"):
            break
        end_cursor = page_info.get("endCursor")
        if (
            not isinstance(end_cursor, str)
            or not end_cursor
            or end_cursor == after
        ):
            raise ResolutionError("review thread pagination did not advance")
        after = end_cursor

    assert state is not None and head_sha is not None
    missing = sorted(required_thread_ids.difference(threads))
    if missing:
        raise ResolutionError(
            f"target threads do not belong to the pull request: {', '.join(missing)}"
        )
    return PullRequestState(state=state, head_sha=head_sha, threads=threads)


def resolve_threads(
    repository: str,
    number: int,
    expected_head: str,
    thread_ids: list[str],
    *,
    apply: bool,
    runner: Callable[[Sequence[str]], dict[str, Any]] = _run_gh,
) -> dict[str, Any]:
    requested = set(thread_ids)
    pull_request = read_pull_request(repository, number, requested, runner)
    if pull_request.state != "OPEN":
        raise ResolutionError(f"pull request is {pull_request.state.lower()}, not open")
    if pull_request.head_sha != expected_head.lower():
        raise ResolutionError(
            f"pull request head changed: expected {expected_head.lower()}, "
            f"observed {pull_request.head_sha}"
        )

    already_resolved = sorted(
        thread_id
        for thread_id in thread_ids
        if pull_request.threads[thread_id].is_resolved
    )
    pending = [
        thread_id
        for thread_id in thread_ids
        if not pull_request.threads[thread_id].is_resolved
    ]
    applied: list[str] = []

    if apply:
        for thread_id in pending:
            data = _graphql(RESOLVE_MUTATION, {"threadId": thread_id}, runner)
            mutation = data.get("resolveReviewThread")
            thread = mutation.get("thread") if isinstance(mutation, dict) else None
            if not isinstance(thread, dict):
                raise ResolutionError(
                    f"GitHub did not confirm resolution for {thread_id}"
                )
            if thread.get("id") != thread_id or thread.get("isResolved") is not True:
                raise ResolutionError(
                    f"GitHub returned an invalid resolution result for {thread_id}"
                )
            applied.append(thread_id)

    return {
        "repository": repository,
        "pull_request_number": number,
        "head_sha": pull_request.head_sha,
        "mode": "apply" if apply else "dry-run",
        "already_resolved": already_resolved,
        "pending": pending if not apply else [],
        "resolved": applied,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--thread-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args(argv)
    if not REPOSITORY.fullmatch(arguments.repo):
        parser.error("--repo must use owner/name format")
    if arguments.pr < 1:
        parser.error("--pr must be positive")
    if not OID.fullmatch(arguments.expected_head):
        parser.error("--expected-head must be a full 40-character commit OID")
    if len(arguments.thread_id) != len(set(arguments.thread_id)):
        parser.error("--thread-id values must be unique")
    invalid = [
        value for value in arguments.thread_id if not THREAD_ID.fullmatch(value)
    ]
    if invalid:
        parser.error("--thread-id must be a GitHub review-thread node ID")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = resolve_threads(
            arguments.repo,
            arguments.pr,
            arguments.expected_head,
            arguments.thread_id,
            apply=arguments.apply,
        )
    except (ResolutionError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
