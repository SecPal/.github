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
import hashlib
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
REGISTRY_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / ".agents/skills/secpal-pr-review/references/repositories.schema.json"
)
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OID = re.compile(r"^[0-9a-fA-F]{40}$")
THREAD_ID = re.compile(r"^PRRT_[A-Za-z0-9_-]+$")
GH_GRAPHQL_PREFIX = ("api", "--hostname", "github.com", "graphql")

TARGET_QUERY = """
query($threadId: ID!, $commentsAfter: String) {
  node(id: $threadId) {
    __typename
    ... on PullRequestReviewThread {
      id
      isResolved
      isOutdated
      pullRequest {
        number
        state
        headRefOid
        repository { nameWithOwner }
      }
      comments(first: 100, after: $commentsAfter) {
        nodes {
          id
          body
          replyTo { id }
        }
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
ALLOWED_GRAPHQL_DOCUMENTS = frozenset({TARGET_QUERY, RESOLVE_MUTATION})


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
class ThreadCommentState:
    comment_id: str
    body_digest: str
    reply_to_id: str | None


@dataclass(frozen=True)
class ThreadState:
    thread_id: str
    is_resolved: bool
    is_outdated: bool
    comments: tuple[ThreadCommentState, ...]


@dataclass(frozen=True)
class TargetRead:
    repository: str
    pull_request_number: int
    state: str
    head_sha: str
    thread: ThreadState


@dataclass(frozen=True)
class RepositoryLimits:
    maximum_api_calls: int
    maximum_threads: int
    maximum_comments: int


@dataclass
class InvocationBudget:
    maximum_api_calls: int
    maximum_threads: int
    maximum_comments: int
    api_calls: int = 0
    threads: int = 0
    comments: int = 0

    def consume_api_call(self) -> None:
        if self.api_calls >= self.maximum_api_calls:
            raise ResolutionError("registered API call limit reached")
        self.api_calls += 1

    def consume_thread(self) -> None:
        if self.threads >= self.maximum_threads:
            raise ResolutionError("registered review thread limit reached")
        self.threads += 1

    def consume_comment(self) -> None:
        if self.comments >= self.maximum_comments:
            raise ResolutionError("registered review comment limit reached")
        self.comments += 1

    @property
    def remaining_api_calls(self) -> int:
        return self.maximum_api_calls - self.api_calls

    @property
    def remaining_threads(self) -> int:
        return self.maximum_threads - self.threads

    @property
    def remaining_comments(self) -> int:
        return self.maximum_comments - self.comments


def load_repository_limits(repository: str) -> RepositoryLimits:
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError("repository registry is unavailable or malformed") from exc
    try:
        evidence.validate_against_authoritative_schema(
            registry,
            REGISTRY_SCHEMA_PATH,
            "workflow repository registry",
        )
    except evidence.ContractError as exc:
        raise ResolutionError("repository registry is invalid") from exc
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
    maximum_comments = entry.get("maximum_comments")
    if (
        not isinstance(maximum_api_calls, int)
        or isinstance(maximum_api_calls, bool)
        or maximum_api_calls < 1
        or not isinstance(maximum_threads, int)
        or isinstance(maximum_threads, bool)
        or maximum_threads < 1
        or not isinstance(maximum_comments, int)
        or isinstance(maximum_comments, bool)
        or maximum_comments < 1
    ):
        raise ResolutionError("repository registry limits are malformed")
    return RepositoryLimits(
        maximum_api_calls=maximum_api_calls,
        maximum_threads=maximum_threads,
        maximum_comments=maximum_comments,
    )


def _run_gh(arguments: Sequence[str]) -> dict[str, Any]:
    if tuple(arguments[: len(GH_GRAPHQL_PREFIX)]) != GH_GRAPHQL_PREFIX:
        raise ResolutionError("gh command is outside the allowed GraphQL surface")
    query_documents = [
        argument.removeprefix("query=")
        for argument in arguments[len(GH_GRAPHQL_PREFIX) :]
        if argument.startswith("query=")
    ]
    if (
        len(query_documents) != 1
        or query_documents[0] not in ALLOWED_GRAPHQL_DOCUMENTS
    ):
        raise ResolutionError("query is outside the GraphQL document allowlist")
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
    except OSError as exc:
        raise ResolutionError("gh process launch failed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ResolutionError("gh command timed out") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "gh failed").strip()
        raise ResolutionError(evidence.redact_diagnostic(detail))
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
    budget: InvocationBudget,
) -> dict[str, Any]:
    if query not in ALLOWED_GRAPHQL_DOCUMENTS:
        raise ResolutionError("query is outside the GraphQL document allowlist")
    arguments: list[str] = [
        *GH_GRAPHQL_PREFIX,
        "-f",
        f"query={query}",
    ]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        arguments.extend([flag, f"{key}={value}"])
    budget.consume_api_call()
    payload = runner(arguments)
    if payload.get("errors"):
        raise ResolutionError("GitHub GraphQL request failed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ResolutionError("GitHub GraphQL response has no data")
    return data


def _body_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def read_target_thread(
    repository: str,
    number: int,
    thread_id: str,
    budget: InvocationBudget,
    runner: Callable[[Sequence[str]], dict[str, Any]],
) -> TargetRead:
    comments: dict[str, ThreadCommentState] = {}
    after: str | None = None
    observed_repository: str | None = None
    observed_number: int | None = None
    state: str | None = None
    head_sha: str | None = None
    is_resolved: bool | None = None
    is_outdated: bool | None = None
    seen_cursors: set[str] = set()
    pagination_complete = False

    while budget.remaining_api_calls > 0:
        variables: dict[str, str | int] = {"threadId": thread_id}
        if after is not None:
            variables["commentsAfter"] = after
        data = _graphql(TARGET_QUERY, variables, runner, budget)
        node = data.get("node")
        if not isinstance(node, dict) or node.get("__typename") != (
            "PullRequestReviewThread"
        ):
            raise ResolutionError(
                f"target thread does not belong to the pull request: {thread_id}"
            )
        budget.consume_thread()
        pull_request = node.get("pullRequest")
        if not isinstance(pull_request, dict):
            raise ResolutionError("target thread pull request is missing")
        repository_value = pull_request.get("repository")
        current_repository = (
            repository_value.get("nameWithOwner")
            if isinstance(repository_value, dict)
            else None
        )
        current_number = pull_request.get("number")

        current_state = pull_request.get("state")
        current_head = pull_request.get("headRefOid")
        current_resolved = node.get("isResolved")
        current_outdated = node.get("isOutdated")
        if (
            not isinstance(current_repository, str)
            or not isinstance(current_number, int)
            or isinstance(current_number, bool)
            or not isinstance(current_state, str)
            or not isinstance(current_head, str)
            or node.get("id") != thread_id
            or not isinstance(current_resolved, bool)
            or not isinstance(current_outdated, bool)
        ):
            raise ResolutionError("pull request identity is incomplete")
        if state is None:
            observed_repository = current_repository
            observed_number = current_number
            state = current_state
            head_sha = current_head.lower()
            is_resolved = current_resolved
            is_outdated = current_outdated
        elif (
            observed_repository != current_repository
            or observed_number != current_number
            or state != current_state
            or head_sha != current_head.lower()
            or is_resolved != current_resolved
            or is_outdated != current_outdated
        ):
            raise ResolutionError("target thread changed while reading comments")

        connection = node.get("comments")
        if not isinstance(connection, dict):
            raise ResolutionError("target thread comment connection is missing")
        nodes = connection.get("nodes")
        if not isinstance(nodes, list):
            raise ResolutionError("target thread comment list is malformed")
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            raise ResolutionError("target thread comment pagination is missing")
        has_next_page = page_info.get("hasNextPage")
        if not isinstance(has_next_page, bool):
            raise ResolutionError("target thread comment pagination is malformed")
        for comment in nodes:
            if not isinstance(comment, dict):
                raise ResolutionError("target thread comment entry is malformed")
            comment_id = comment.get("id")
            body = comment.get("body")
            reply_to = comment.get("replyTo")
            reply_to_id = (
                reply_to.get("id") if isinstance(reply_to, dict) else None
            )
            if (
                not isinstance(comment_id, str)
                or not comment_id
                or not isinstance(body, str)
                or (
                    reply_to is not None
                    and (
                        not isinstance(reply_to, dict)
                        or not isinstance(reply_to_id, str)
                        or not reply_to_id
                    )
                )
            ):
                raise ResolutionError("target thread comment identity is incomplete")
            if comment_id in comments:
                raise ResolutionError(
                    f"target thread pagination repeated comment: {comment_id}"
                )
            budget.consume_comment()
            comments[comment_id] = ThreadCommentState(
                comment_id=comment_id,
                body_digest=_body_digest(body),
                reply_to_id=reply_to_id,
            )

        if not has_next_page:
            pagination_complete = True
            break
        end_cursor = page_info.get("endCursor")
        if (
            not isinstance(end_cursor, str)
            or not end_cursor
            or end_cursor in seen_cursors
        ):
            raise ResolutionError("target thread comment pagination did not advance")
        seen_cursors.add(end_cursor)
        after = end_cursor

    if not pagination_complete:
        raise ResolutionError("registered API call limit reached")
    assert (
        observed_repository is not None
        and observed_number is not None
        and state is not None
        and head_sha is not None
        and is_resolved is not None
        and is_outdated is not None
    )
    return TargetRead(
        repository=observed_repository,
        pull_request_number=observed_number,
        state=state,
        head_sha=head_sha,
        thread=ThreadState(
            thread_id=thread_id,
            is_resolved=is_resolved,
            is_outdated=is_outdated,
            comments=tuple(sorted(comments.values(), key=lambda item: item.comment_id)),
        ),
    )


def require_expected_target(
    target: TargetRead,
    repository: str,
    number: int,
    expected_head: str,
) -> None:
    if (
        target.repository != repository
        or target.pull_request_number != number
    ):
        raise ResolutionError(
            f"target thread does not belong to {repository}#{number}"
        )
    if target.state != "OPEN":
        raise ResolutionError(f"pull request is {target.state.lower()}, not open")
    if target.head_sha != expected_head.lower():
        raise ResolutionError(
            f"pull request head changed: expected {expected_head.lower()}, "
            f"observed {target.head_sha}"
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
    budget = InvocationBudget(
        limits.maximum_api_calls,
        limits.maximum_threads,
        limits.maximum_comments,
    )
    initial_targets: dict[str, ThreadState] = {}
    for thread_id in thread_ids:
        target = read_target_thread(
            repository,
            number,
            thread_id,
            budget,
            runner,
        )
        require_expected_target(target, repository, number, expected_head)
        initial_targets[thread_id] = target.thread

    already_resolved = sorted(
        thread_id
        for thread_id in thread_ids
        if initial_targets[thread_id].is_resolved
    )
    pending = [
        thread_id
        for thread_id in thread_ids
        if not initial_targets[thread_id].is_resolved
    ]
    applied: list[str] = []

    if apply:
        minimum_recheck_pages = sum(
            max(1, (len(initial_targets[thread_id].comments) + 99) // 100)
            for thread_id in pending
        )
        minimum_recheck_comments = sum(
            len(initial_targets[thread_id].comments) for thread_id in pending
        )
        if budget.remaining_api_calls < minimum_recheck_pages + len(pending):
            raise ResolutionError(
                "registered API call limit cannot cover all target rechecks and writes"
            )
        if budget.remaining_threads < minimum_recheck_pages:
            raise ResolutionError(
                "registered review thread limit cannot cover all target rechecks"
            )
        if budget.remaining_comments < minimum_recheck_comments:
            raise ResolutionError(
                "registered review comment limit cannot cover all target rechecks"
            )
        for index, thread_id in enumerate(pending):
            phase = "recheck"
            try:
                current = read_target_thread(
                    repository,
                    number,
                    thread_id,
                    budget,
                    runner,
                )
                require_expected_target(
                    current,
                    repository,
                    number,
                    expected_head,
                )
                if current.thread != initial_targets[thread_id]:
                    raise ResolutionError(
                        f"target thread changed before resolution: {thread_id}"
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
                    "head_sha": expected_head.lower(),
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
        "head_sha": expected_head.lower(),
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
