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
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_HELPER = REPOSITORY_ROOT / "scripts/secpal-pr-review.py"
REGISTRY_PATH = (
    REPOSITORY_ROOT
    / ".agents/skills/secpal-pr-review/references/repositories.json"
)
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


def _load_evidence_helper() -> Any:
    module_name = "secpal_pr_review_evidence_shared"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).resolve() != EVIDENCE_HELPER.resolve()
        ):
            raise RuntimeError("accepted evidence helper has an unexpected path")
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, EVIDENCE_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load accepted evidence helper: {EVIDENCE_HELPER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(spec.name) is module:
            sys.modules.pop(spec.name, None)
        raise
    return module


evidence = _load_evidence_helper()


@dataclass(frozen=True)
class ThreadState:
    thread_id: str
    is_resolved: bool


@dataclass(frozen=True)
class PullRequestState:
    state: str
    head_sha: str
    threads: dict[str, ThreadState]


@dataclass(frozen=True)
class RepositoryLimits:
    maximum_api_calls: int
    maximum_threads: int


@dataclass
class ApiBudget:
    maximum_api_calls: int
    calls: int = 0

    def consume(self) -> None:
        if self.calls >= self.maximum_api_calls:
            raise ResolutionError("registered API call limit reached")
        self.calls += 1

    @property
    def remaining(self) -> int:
        return self.maximum_api_calls - self.calls


def load_repository_limits(repository: str) -> RepositoryLimits:
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError("repository registry is unavailable or malformed") from exc
    repositories = registry.get("repositories") if isinstance(registry, dict) else None
    if not isinstance(repositories, list):
        raise ResolutionError("repository registry is malformed")
    matches = [
        entry
        for entry in repositories
        if isinstance(entry, dict) and entry.get("repository") == repository
    ]
    if len(matches) != 1:
        raise ResolutionError(f"unsupported repository: {repository}")
    entry = matches[0]
    maximum_api_calls = entry.get("maximum_api_calls")
    maximum_threads = entry.get("maximum_threads")
    if (
        not isinstance(maximum_api_calls, int)
        or isinstance(maximum_api_calls, bool)
        or maximum_api_calls < 1
        or not isinstance(maximum_threads, int)
        or isinstance(maximum_threads, bool)
        or maximum_threads < 1
    ):
        raise ResolutionError("repository registry limits are malformed")
    return RepositoryLimits(
        maximum_api_calls=maximum_api_calls,
        maximum_threads=maximum_threads,
    )


def _run_gh(arguments: Sequence[str]) -> dict[str, Any]:
    try:
        executable = evidence.resolve_trusted_executable("gh")
        completed = subprocess.run(
            [executable, *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=evidence.command_environment("gh"),
            timeout=30,
        )
    except evidence.CommandPolicyError as exc:
        raise ResolutionError("trusted GitHub CLI is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise ResolutionError("gh command timed out") from exc
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
    runner: Callable[[Sequence[str]], dict[str, Any]],
    budget: ApiBudget,
) -> dict[str, Any]:
    arguments: list[str] = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        arguments.extend([flag, f"{key}={value}"])
    budget.consume()
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
    limits: RepositoryLimits,
    budget: ApiBudget,
    runner: Callable[[Sequence[str]], dict[str, Any]],
) -> PullRequestState:
    owner, name = repository.split("/", 1)
    threads: dict[str, ThreadState] = {}
    after: str | None = None
    state: str | None = None
    head_sha: str | None = None
    thread_count = 0
    pagination_complete = False

    while budget.remaining > 0:
        variables: dict[str, str | int] = {
            "owner": owner,
            "name": name,
            "number": number,
        }
        if after is not None:
            variables["after"] = after
        data = _graphql(READ_QUERY, variables, runner, budget)
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
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            raise ResolutionError("review thread pagination is missing")
        has_next_page = page_info.get("hasNextPage")
        if not isinstance(has_next_page, bool):
            raise ResolutionError("review thread pagination is malformed")
        for node in nodes:
            if not isinstance(node, dict):
                raise ResolutionError("review thread entry is malformed")
            thread_id = node.get("id")
            is_resolved = node.get("isResolved")
            if not isinstance(thread_id, str) or not isinstance(is_resolved, bool):
                raise ResolutionError("review thread identity is incomplete")
            if thread_id in threads:
                raise ResolutionError(
                    f"review thread pagination repeated thread: {thread_id}"
                )
            thread_count += 1
            if thread_count > limits.maximum_threads:
                raise ResolutionError("registered review thread limit reached")
            threads[thread_id] = ThreadState(thread_id, is_resolved)

        if required_thread_ids.issubset(threads):
            pagination_complete = True
            break
        if not has_next_page:
            pagination_complete = True
            break
        if thread_count >= limits.maximum_threads:
            raise ResolutionError("registered review thread limit reached")
        end_cursor = page_info.get("endCursor")
        if (
            not isinstance(end_cursor, str)
            or not end_cursor
            or end_cursor == after
        ):
            raise ResolutionError("review thread pagination did not advance")
        after = end_cursor

    if not pagination_complete:
        raise ResolutionError("registered API call limit reached")
    assert state is not None and head_sha is not None
    missing = sorted(required_thread_ids.difference(threads))
    if missing:
        raise ResolutionError(
            f"target threads do not belong to the pull request: {', '.join(missing)}"
        )
    return PullRequestState(state=state, head_sha=head_sha, threads=threads)


def require_expected_pull_request(
    pull_request: PullRequestState,
    expected_head: str,
) -> None:
    if pull_request.state != "OPEN":
        raise ResolutionError(f"pull request is {pull_request.state.lower()}, not open")
    if pull_request.head_sha != expected_head.lower():
        raise ResolutionError(
            f"pull request head changed: expected {expected_head.lower()}, "
            f"observed {pull_request.head_sha}"
        )


def validate_request(
    repository: str,
    number: int,
    expected_head: str,
    thread_ids: list[str],
    apply: bool,
) -> None:
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise ResolutionError("repository must use owner/name format")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ResolutionError("pull request number must be positive")
    if not isinstance(expected_head, str) or not OID.fullmatch(expected_head):
        raise ResolutionError("expected head must be a full 40-character commit OID")
    if not isinstance(thread_ids, list) or not thread_ids:
        raise ResolutionError("at least one thread ID is required")
    if any(not isinstance(value, str) for value in thread_ids):
        raise ResolutionError("thread IDs must be GitHub review-thread node IDs")
    if len(thread_ids) != len(set(thread_ids)):
        raise ResolutionError("thread IDs must be unique")
    if any(not THREAD_ID.fullmatch(value) for value in thread_ids):
        raise ResolutionError("thread IDs must be GitHub review-thread node IDs")
    if not isinstance(apply, bool):
        raise ResolutionError("apply must be boolean")


def resolve_threads(
    repository: str,
    number: int,
    expected_head: str,
    thread_ids: list[str],
    *,
    apply: bool,
    runner: Callable[[Sequence[str]], dict[str, Any]] = _run_gh,
) -> dict[str, Any]:
    validate_request(repository, number, expected_head, thread_ids, apply)
    limits = load_repository_limits(repository)
    budget = ApiBudget(limits.maximum_api_calls)
    requested = set(thread_ids)
    pull_request = read_pull_request(
        repository,
        number,
        requested,
        limits,
        budget,
        runner,
    )
    require_expected_pull_request(pull_request, expected_head)

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
        if budget.remaining < len(pending) * 2:
            raise ResolutionError(
                "registered API call limit cannot cover all target rechecks and writes"
            )
        for index, thread_id in enumerate(pending):
            phase = "recheck"
            try:
                current = read_pull_request(
                    repository,
                    number,
                    {thread_id},
                    limits,
                    budget,
                    runner,
                )
                require_expected_pull_request(current, expected_head)
                if current.threads[thread_id].is_resolved:
                    raise ResolutionError(
                        "target thread changed before resolution: "
                        f"{thread_id} is resolved"
                    )
                phase = "mutation"
                data = _graphql(
                    RESOLVE_MUTATION,
                    {"threadId": thread_id},
                    runner,
                    budget,
                )
                mutation = data.get("resolveReviewThread")
                thread = (
                    mutation.get("thread") if isinstance(mutation, dict) else None
                )
                if not isinstance(thread, dict):
                    raise ResolutionError(
                        f"GitHub did not confirm resolution for {thread_id}"
                    )
                if (
                    thread.get("id") != thread_id
                    or thread.get("isResolved") is not True
                ):
                    raise ResolutionError(
                        "GitHub returned an invalid resolution result for "
                        f"{thread_id}"
                    )
            except ResolutionError as exc:
                return {
                    "repository": repository,
                    "pull_request_number": number,
                    "head_sha": pull_request.head_sha,
                    "mode": "apply",
                    "status": "failed",
                    "already_resolved": already_resolved,
                    "pending": [],
                    "resolved": applied,
                    "failed": [
                        {
                            "thread_id": thread_id,
                            "phase": phase,
                            "write_result": (
                                "unknown"
                                if phase == "mutation"
                                else "not_attempted"
                            ),
                            "error": str(exc),
                        }
                    ],
                    "unattempted": pending[index + 1 :],
                }
            applied.append(thread_id)

    return {
        "repository": repository,
        "pull_request_number": number,
        "head_sha": pull_request.head_sha,
        "mode": "apply" if apply else "dry-run",
        "status": "success",
        "already_resolved": already_resolved,
        "pending": pending if not apply else [],
        "resolved": applied,
        "failed": [],
        "unattempted": [],
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--thread-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        validate_request(
            arguments.repo,
            arguments.pr,
            arguments.expected_head,
            arguments.thread_id,
            arguments.apply,
        )
    except ResolutionError as exc:
        parser.error(str(exc))
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
    except ResolutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
