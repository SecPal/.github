#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Resolve explicitly named, already-fixed pull-request review threads.

This command deliberately separates thread resolution from merge readiness.
It verifies the pull request, expected head, caller-captured reviewed-state
digest, successful validation evidence for the fix commit, exact target thread
identities, and the target state captured when feedback was reviewed, then
resolves each still-open target once. It does not inspect CI, reactions,
unrelated feedback, mergeability, or any broader readiness state.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import operator
import os
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
FOLLOW_UP_HELPER = REPOSITORY_ROOT / "scripts/secpal_pr_review/follow_up.py"
LATE_DISPOSITION_HELPER = (
    REPOSITORY_ROOT / "scripts/secpal_pr_review/late_disposition.py"
)
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OID = re.compile(r"^[0-9a-fA-F]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
THREAD_ID = re.compile(r"^PRRT_[A-Za-z0-9_-]+$")
EVIDENCE_TEXT = re.compile(r"^[^\x00-\x1f\x7f]+$")
SECRET_VALUE = re.compile(
    r"(?i)(?:github_pat_|gh[opsu]_|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"authorization\s*:\s*bearer)"
)
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
          databaseId
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
FIXED_THREAD_RESOLUTION_CONTRACT = {
    "resolver": "scripts/secpal-resolve-fixed-threads.py",
    "required_bindings": [
        "repository",
        "pull_request_number",
        "repository_root",
        "expected_head",
        "reviewed_state_digest",
        "validation_evidence",
        "eligibility_evidence",
        "thread_ids",
    ],
    "allowed_github_operations": [
        "READ_NAMED_REVIEW_THREAD",
        "READ_AUTHENTICATED_FOLLOW_UP_WORK_GRAPH",
        "RESOLVE_NAMED_REVIEW_THREAD",
    ],
    "prohibited_hosted_reads": [
        "GITHUB_ACTIONS",
        "CODEQL",
        "CHECK_SUITES",
        "COMMIT_STATUSES",
        "REQUIRED_CHECKS",
        "MERGEABILITY",
        "BRANCH_PROTECTION",
        "MERGE_READINESS",
    ],
    "prohibited_mutations": [
        "REVIEW_REQUEST",
        "READY_TRANSITION",
        "MERGE",
        "LABEL",
        "GENERIC_COMMENT",
    ],
    "readiness_authorization": "SEPARATE_EXPLICIT_WORKFLOW",
}
ELIGIBLE_DISPOSITIONS = {
    "VALID_ACTIONABLE": frozenset(
        {"CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX"}
    ),
    "INVALID_FALSE_OR_MISLEADING": frozenset({"DISPROVEN_WITH_EVIDENCE"}),
    "INFORMATIONAL": frozenset({"NON_ACTIONABLE"}),
    "DUPLICATE": frozenset({"DUPLICATE_OF_CANONICAL"}),
    "OUTDATED_BUT_STILL_VALID": frozenset(
        {"CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX"}
    ),
    "OUTDATED_AND_OBSOLETE": frozenset({"OBSOLETE_ON_CURRENT_HEAD"}),
    "ALREADY_FIXED_ON_SNAPSHOT_HEAD": frozenset({"PROVEN_EXISTING_FIX"}),
    "SUPERSEDED": frozenset({"SUPERSEDED_BY_CANONICAL"}),
    "SECURITY_WEAKENING_SUGGESTION": frozenset(
        {"REJECTED_SECURITY_WEAKENING"}
    ),
    "OUTSIDE_PR_SCOPE": frozenset({"TRACKED_AS_FOLLOW_UP"}),
}


class ResolutionError(RuntimeError):
    """The requested bounded resolution cannot be proven safe."""


def _load_evidence_helper() -> Any:
    loaded = sys.modules.get("secpal_pr_review_evidence_shared")
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).resolve() != EVIDENCE_HELPER.resolve()
        ):
            raise RuntimeError("accepted evidence helper has an unexpected path")
        return loaded
    spec = importlib.util.spec_from_file_location(
        "secpal_pr_review_evidence_shared",
        EVIDENCE_HELPER,
    )
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


def _load_follow_up_helper() -> Any:
    loaded = sys.modules.get("secpal_pr_review.follow_up")
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).resolve() != FOLLOW_UP_HELPER.resolve()
        ):
            raise RuntimeError("Canonical follow-up module has an unexpected path")
        return loaded
    spec = importlib.util.spec_from_file_location(
        "secpal_pr_review.follow_up", FOLLOW_UP_HELPER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load follow-up helper: {FOLLOW_UP_HELPER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


follow_up = _load_follow_up_helper()
FollowUpIdentity = follow_up.FollowUpIdentity
LiveFollowUpState = follow_up.LiveFollowUpState


def _load_late_disposition_helper() -> Any:
    loaded = sys.modules.get("secpal_pr_review.late_disposition")
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).resolve() != LATE_DISPOSITION_HELPER.resolve()
        ):
            raise RuntimeError("Late-disposition module has an unexpected path")
        return loaded
    spec = importlib.util.spec_from_file_location(
        "secpal_pr_review.late_disposition", LATE_DISPOSITION_HELPER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load late-disposition helper: {LATE_DISPOSITION_HELPER}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


late_disposition = _load_late_disposition_helper()


def _resolve_trusted_markdown_node() -> str:
    """Resolve Node only for the maintained Markdown parser bridge."""

    for directory in evidence.TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / "node"
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    raise ResolutionError("trusted Markdown parser is unavailable")


def _markdown_parser_environment() -> dict[str, str]:
    """Return an explicit non-inheriting Markdown parser environment."""

    return {"PATH": evidence.TRUSTED_COMMAND_PATH}


def _read_authenticated_follow_up(
    identity: FollowUpIdentity,
    budget: InvocationBudget,
) -> LiveFollowUpState:
    try:
        executable = evidence.resolve_trusted_executable("gh")
    except evidence.CommandPolicyError as exc:
        raise ResolutionError("trusted GitHub CLI is unavailable") from exc
    node_executable = _resolve_trusted_markdown_node()
    parser_environment = _markdown_parser_environment()
    try:
        return follow_up.read_live_follow_up(
            identity,
            gh_executable=executable,
            environment=evidence.command_environment("gh"),
            node_executable=node_executable,
            parser_environment=parser_environment,
            query_consumer=_consume_api_call,
            query_context=budget,
        )
    except follow_up.FollowUpError as exc:
        raise ResolutionError(str(exc)) from exc


@dataclass(frozen=True)
class ThreadCommentState:
    comment_id: str
    database_id: int | None
    body_digest: str
    reply_to_id: str | None


@dataclass(frozen=True)
class ThreadState:
    thread_id: str
    is_resolved: bool
    is_outdated: bool
    comments: tuple[ThreadCommentState, ...]


@dataclass(frozen=True)
class ExpectedThreadState:
    thread_id: str
    is_resolved: bool
    is_outdated: bool
    comments: tuple[ThreadCommentState, ...]


@dataclass(frozen=True)
class ReviewedState:
    head_sha: str
    state_digest: str
    feedback_digest: str
    targets: dict[str, ExpectedThreadState]


@dataclass(frozen=True)
class ValidationEvidence:
    kind: str
    evidence_digest: str
    validated_tree_sha: str
    validation_receipt_digest: str
    eligibility_evidence_digest: str


@dataclass(frozen=True)
class EligibilityEvidence:
    evidence_digest: str
    canonical_payload: bytes


@dataclass(frozen=True)
class TargetRead:
    repository: str
    pull_request_number: int
    state: str
    head_sha: str
    api_pages: int
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


def _consume_api_call(budget: InvocationBudget) -> None:
    if budget.api_calls >= budget.maximum_api_calls:
        raise ResolutionError("registered API call limit reached")
    budget.api_calls += 1


def _consume_thread(budget: InvocationBudget) -> None:
    if budget.threads >= budget.maximum_threads:
        raise ResolutionError("registered review thread limit reached")
    budget.threads += 1


def _consume_comment(budget: InvocationBudget) -> None:
    if budget.comments >= budget.maximum_comments:
        raise ResolutionError("registered review comment limit reached")
    budget.comments += 1


def _load_repository_entry(repository: str) -> dict[str, Any]:
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
    if registry.get("fixed_thread_resolution") != (
        FIXED_THREAD_RESOLUTION_CONTRACT
    ):
        raise ResolutionError("fixed-thread resolution registry contract is invalid")
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
    return matches[0]


def load_repository_limits(repository: str) -> RepositoryLimits:
    entry = _load_repository_entry(repository)
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


def _validation_registry_binding(entry: dict[str, Any]) -> dict[str, Any]:
    focused_validation = entry["focused_validation"]
    validation = [
        command
        for command in focused_validation
        if command.get("execution_policy", "always") == "always"
    ] + list(entry["required_local_validation"])
    return {
        "repository": entry["repository"],
        "default_branch": entry["default_branch"],
        "allowed_base_repositories": entry["allowed_base_repositories"],
        "manual_gates": entry["manual_gates"],
        "signature_policy": entry["signature_policy"],
        "check_policy": entry["check_policy"],
        "limits": {
            key: entry[key] for key in ("maximum_api_calls", "maximum_items")
        },
        "validation": validation,
        "focused_only_validation": [
            command
            for command in focused_validation
            if command.get("execution_policy") == "focused-only"
        ],
    }


def _validate_manual_gate_evidence(
    value: Any,
    registered_gates: Any,
) -> list[dict[str, Any]]:
    if not isinstance(registered_gates, list) or any(
        not isinstance(gate, str) or not gate for gate in registered_gates
    ):
        raise ResolutionError("registered manual gates are malformed")
    if not isinstance(value, list) or len(value) != len(registered_gates):
        raise ResolutionError("validation evidence is invalid or stale")
    normalized: list[dict[str, Any]] = []
    for index, gate in enumerate(registered_gates):
        item = value[index]
        evidence_text = item.get("evidence") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) != {"gate", "satisfied", "evidence"}
            or item.get("gate") != gate
            or item.get("satisfied") is not True
            or not isinstance(evidence_text, str)
            or not EVIDENCE_TEXT.fullmatch(evidence_text)
            or SECRET_VALUE.search(evidence_text)
        ):
            raise ResolutionError("validation evidence is invalid or stale")
        normalized.append(
            {"gate": gate, "satisfied": True, "evidence": evidence_text}
        )
    return normalized


def _expected_validation_receipt(
    repository: str,
    reviewed: ReviewedState,
    validated_tree_sha: Any,
    manual_gate_evidence: Any,
    eligibility_evidence_digest: Any,
    registry_binding: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(validated_tree_sha, str) or not OID.fullmatch(
        validated_tree_sha
    ):
        raise ResolutionError("validation evidence is invalid or stale")
    if (
        not isinstance(eligibility_evidence_digest, str)
        or not DIGEST.fullmatch(eligibility_evidence_digest)
    ):
        raise ResolutionError("validation evidence is invalid or stale")
    fields = {
        "schema_version": "1.0",
        "kind": "VALIDATION_RECEIPT",
        "repository": repository,
        "head_sha": reviewed.head_sha,
        "validated_tree_sha": validated_tree_sha.lower(),
        "registry_digest": _digest_json(registry_binding),
        "command_set_digest": _digest_json(registry_binding["validation"]),
        "successful_result": True,
        "reviewed_state_digest": reviewed.state_digest,
        "reviewed_feedback_digest": reviewed.feedback_digest,
        "manual_gate_evidence": _validate_manual_gate_evidence(
            manual_gate_evidence,
            registry_binding["manual_gates"],
        ),
        "eligibility_evidence_digest": eligibility_evidence_digest,
    }
    return {**fields, "receipt_digest": _digest_json(fields)}


def _expected_validation_attestation(
    repository: str,
    expected_head: str,
    reviewed: ReviewedState,
    payload: dict[str, Any],
    registry_binding: dict[str, Any],
) -> dict[str, Any]:
    receipt = _expected_validation_receipt(
        repository,
        reviewed,
        payload.get("validated_tree_sha"),
        payload.get("manual_gate_evidence"),
        payload.get("eligibility_evidence_digest"),
        registry_binding,
    )
    fields = {
        "schema_version": "1.0",
        "repository": repository,
        "head_sha": expected_head.lower(),
        "registry_digest": receipt["registry_digest"],
        "command_set_digest": receipt["command_set_digest"],
        "successful_result": True,
        "reviewed_head_sha": reviewed.head_sha,
        "reviewed_state_digest": reviewed.state_digest,
        "reviewed_feedback_digest": reviewed.feedback_digest,
        "validated_tree_sha": receipt["validated_tree_sha"],
        "validation_receipt_digest": receipt["receipt_digest"],
        "manual_gate_evidence": receipt["manual_gate_evidence"],
        "eligibility_evidence_digest": receipt[
            "eligibility_evidence_digest"
        ],
    }
    return {**fields, "attestation_digest": _digest_json(fields)}


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


def _run_git(
    repository_root: Path,
    arguments: Sequence[str],
    *,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        executable = evidence.resolve_trusted_executable("git")
        completed = subprocess.run(
            [executable, *arguments],
            cwd=repository_root,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=evidence.command_environment("git"),
            timeout=30,
        )
    except evidence.CommandPolicyError as exc:
        raise ResolutionError("trusted Git executable is unavailable") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResolutionError("local Git command is unavailable") from exc
    if completed.returncode != 0 and not allow_failure:
        raise ResolutionError(
            evidence.redact_diagnostic(
                completed.stderr or "local Git command failed"
            )
        )
    return completed


def _remote_repository(value: str) -> str:
    normalized = value.strip()
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        normalized,
    )
    if match is None:
        raise ResolutionError("local origin repository identity is unsupported")
    return match.group(1)


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
    _consume_api_call(budget)
    payload = runner(arguments)
    if payload.get("errors"):
        raise ResolutionError("GitHub GraphQL request failed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ResolutionError("GitHub GraphQL response has no data")
    return data


def _body_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _reject_nonfinite_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def load_reviewed_state(
    path: Path,
    repository: str,
    number: int,
    expected_state_digest: str,
    thread_ids: tuple[str, ...],
) -> ReviewedState:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (OSError, ValueError) as exc:
        raise ResolutionError(
            "reviewed feedback state is unavailable or malformed"
        ) from exc
    expected_keys = {
        "schema_version",
        "repository",
        "pull_request_number",
        "head_sha",
        "base_ref",
        "base_sha",
        "pr_state",
        "pull_request_reactions",
        "reviews",
        "conversation_comments",
        "threads",
        "feedback_digest",
        "state_digest",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ResolutionError("reviewed feedback state has an unsupported shape")
    if (
        payload.get("schema_version") != "1.0"
        or payload.get("repository") != repository
        or not isinstance(payload.get("pull_request_number"), int)
        or isinstance(payload.get("pull_request_number"), bool)
        or payload.get("pull_request_number") != number
        or not isinstance(payload.get("head_sha"), str)
        or not OID.fullmatch(payload["head_sha"])
        or not isinstance(payload.get("base_ref"), str)
        or not payload["base_ref"]
        or not isinstance(payload.get("base_sha"), str)
        or not OID.fullmatch(payload["base_sha"])
        or payload.get("pr_state") != "OPEN"
    ):
        raise ResolutionError("reviewed feedback state identity does not match the request")
    feedback = {
        "pull_request_reactions": payload.get("pull_request_reactions"),
        "reviews": payload.get("reviews"),
        "conversation_comments": payload.get("conversation_comments"),
        "threads": payload.get("threads"),
    }
    if any(not isinstance(value, list) for value in feedback.values()):
        raise ResolutionError("reviewed feedback state is malformed")
    feedback_digest = payload.get("feedback_digest")
    state_digest = payload.get("state_digest")
    if (
        not isinstance(feedback_digest, str)
        or not DIGEST.fullmatch(feedback_digest)
        or feedback_digest != _digest_json(feedback)
        or not isinstance(state_digest, str)
        or not DIGEST.fullmatch(state_digest)
        or state_digest
        != _digest_json(
            {
                "repository": payload.get("repository"),
                "pull_request_number": payload.get("pull_request_number"),
                "head_sha": payload.get("head_sha"),
                "base_ref": payload.get("base_ref"),
                "base_sha": payload.get("base_sha"),
                "pr_state": payload.get("pr_state"),
                "feedback": feedback,
            }
        )
    ):
        raise ResolutionError("reviewed feedback state digest is invalid")
    if (
        not isinstance(expected_state_digest, str)
        or not DIGEST.fullmatch(expected_state_digest)
        or state_digest != expected_state_digest
    ):
        raise ResolutionError(
            "reviewed feedback state does not match the captured digest"
        )

    threads = payload["threads"]
    indexed_threads: dict[str, dict[str, Any]] = {}
    for thread in threads:
        if (
            not isinstance(thread, dict)
            or set(thread) != {
                "node_id",
                "is_resolved",
                "is_outdated",
                "comments",
            }
            or not isinstance(thread.get("node_id"), str)
            or not THREAD_ID.fullmatch(thread["node_id"])
            or not isinstance(thread.get("is_resolved"), bool)
            or not isinstance(thread.get("is_outdated"), bool)
            or not isinstance(thread.get("comments"), list)
            or thread["node_id"] in indexed_threads
        ):
            raise ResolutionError("reviewed feedback thread state is malformed")
        indexed_threads[thread["node_id"]] = thread

    expected_targets: dict[str, ExpectedThreadState] = {}
    for thread_id in thread_ids:
        thread = indexed_threads.get(thread_id)
        if thread is None:
            raise ResolutionError(
                f"target thread is absent from reviewed feedback: {thread_id}"
            )
        comments: dict[str, ThreadCommentState] = {}
        for comment in thread["comments"]:
            if not isinstance(comment, dict):
                raise ResolutionError("reviewed target comment state is malformed")
            comment_id = comment.get("node_id")
            body_digest = comment.get("body_digest")
            reply_to_id = comment.get("reply_to_id")
            if (
                not isinstance(comment_id, str)
                or not comment_id
                or not isinstance(body_digest, str)
                or not DIGEST.fullmatch(body_digest)
                or (
                    reply_to_id is not None
                    and (not isinstance(reply_to_id, str) or not reply_to_id)
                )
                or comment_id in comments
            ):
                raise ResolutionError("reviewed target comment state is malformed")
            comments[comment_id] = ThreadCommentState(
                comment_id=comment_id,
                database_id=None,
                body_digest=body_digest,
                reply_to_id=reply_to_id,
            )
        expected_targets[thread_id] = ExpectedThreadState(
            thread_id=thread_id,
            is_resolved=thread["is_resolved"],
            is_outdated=thread["is_outdated"],
            comments=tuple(
                sorted(comments.values(), key=operator.attrgetter("comment_id"))
            ),
        )
    return ReviewedState(
        head_sha=payload["head_sha"].lower(),
        state_digest=state_digest,
        feedback_digest=feedback_digest,
        targets=expected_targets,
    )


def load_validation_evidence(
    path: Path,
    repository: str,
    expected_head: str,
    reviewed: ReviewedState,
) -> ValidationEvidence:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (OSError, ValueError) as exc:
        raise ResolutionError(
            "validation evidence is unavailable or malformed"
        ) from exc
    registry_binding = _validation_registry_binding(
        _load_repository_entry(repository)
    )
    if isinstance(payload, dict) and payload.get("kind") == "VALIDATION_RECEIPT":
        raise ResolutionError(
            "validation evidence requires an authenticated fix-commit "
            "attestation"
        )
    if not isinstance(payload, dict):
        raise ResolutionError("validation evidence is unavailable or malformed")
    expected_attestation = _expected_validation_attestation(
        repository,
        expected_head,
        reviewed,
        payload,
        registry_binding,
    )
    if payload != expected_attestation:
        if payload.get("head_sha") != expected_head.lower():
            raise ResolutionError(
                "validation evidence does not match the fix commit"
            )
        raise ResolutionError("validation evidence is invalid or stale")
    return ValidationEvidence(
        kind="attestation",
        evidence_digest=payload["attestation_digest"],
        validated_tree_sha=payload["validated_tree_sha"],
        validation_receipt_digest=payload["validation_receipt_digest"],
        eligibility_evidence_digest=payload[
            "eligibility_evidence_digest"
        ],
    )


def verify_local_fix_commit(
    repository_root: Path,
    repository: str,
    expected_head: str,
    reviewed: ReviewedState,
    validation: ValidationEvidence,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    require_signer_identity: bool = False,
) -> Any:
    effective_runner = _run_git if runner is None else runner
    if (
        not isinstance(validation, ValidationEvidence)
        or validation.kind != "attestation"
        or not isinstance(validation.evidence_digest, str)
        or not DIGEST.fullmatch(validation.evidence_digest)
        or not isinstance(validation.validated_tree_sha, str)
        or not OID.fullmatch(validation.validated_tree_sha)
        or not isinstance(validation.validation_receipt_digest, str)
        or not DIGEST.fullmatch(validation.validation_receipt_digest)
        or not isinstance(validation.eligibility_evidence_digest, str)
        or not DIGEST.fullmatch(validation.eligibility_evidence_digest)
    ):
        raise ResolutionError("validation evidence binding is invalid or stale")
    try:
        root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ResolutionError("local repository root is unavailable") from exc
    if not root.is_dir():
        raise ResolutionError("local repository root is unavailable")
    origin = effective_runner(root, ("remote", "get-url", "origin")).stdout.strip()
    if _remote_repository(origin) != repository:
        raise ResolutionError("local origin repository identity mismatch")
    local_head = effective_runner(root, ("rev-parse", "HEAD")).stdout.strip().lower()
    if local_head != expected_head.lower():
        raise ResolutionError(
            f"local head mismatch: expected {expected_head.lower()}, "
            f"observed {local_head or 'missing'}"
        )
    commit_tree = effective_runner(
        root,
        ("rev-parse", f"{expected_head.lower()}^{{tree}}"),
    ).stdout.strip().lower()
    if (
        not OID.fullmatch(commit_tree)
        or commit_tree != validation.validated_tree_sha
    ):
        raise ResolutionError("validated tree does not match the fix commit tree")
    ancestry = effective_runner(
        root,
        ("rev-list", "--parents", "-n", "1", expected_head.lower()),
    ).stdout.split()
    if ancestry != [expected_head.lower(), reviewed.head_sha]:
        raise ResolutionError(
            "validated fix commit parent does not match reviewed head"
        )
    trailer_output = effective_runner(
        root,
        (
            "show",
            "-s",
            "--format=%(trailers:key=SecPal-Validation-Receipt,"
            "valueonly,separator=%x00)",
            expected_head.lower(),
        ),
    ).stdout
    trailers = [
        value.strip()
        for value in trailer_output.rstrip("\n").split("\x00")
        if value.strip()
    ]
    if trailers != [validation.validation_receipt_digest]:
        raise ResolutionError(
            "fix commit validation-receipt trailer does not match evidence"
        )
    commit_object = effective_runner(
        root,
        ("cat-file", "commit", expected_head.lower()),
        allow_failure=True,
    )
    verified = effective_runner(
        root,
        ("verify-commit", "--raw", expected_head.lower()),
        allow_failure=True,
    )
    local_signature = evidence.interpret_local_signature(
        verified.returncode,
        f"{verified.stdout}\n{verified.stderr}",
        signature_format_hint=(
            evidence._commit_signature_format(commit_object.stdout)
            if commit_object.returncode == 0
            else "unknown"
        ),
    )
    signature_policy = _load_repository_entry(repository)["signature_policy"]
    accepted_formats = signature_policy.get("accepted_formats")
    if (
        signature_policy.get("require_local_verified") is not True
        or local_signature.get("state") != "valid"
        or local_signature.get("verified") is not True
        or not isinstance(accepted_formats, list)
        or local_signature.get("format") not in accepted_formats
    ):
        raise ResolutionError("fix commit local signature is not verified")
    try:
        return late_disposition.signer_from_git_verification(
            local_signature["format"],
            f"{verified.stdout}\n{verified.stderr}",
        )
    except late_disposition.LateDispositionError as exc:
        if require_signer_identity:
            raise ResolutionError(str(exc)) from exc
        return None


def verify_live_follow_up(
    identity: FollowUpIdentity,
    budget: InvocationBudget | None = None,
    *,
    state_reader: Callable[[FollowUpIdentity], LiveFollowUpState] | None = None,
) -> LiveFollowUpState:
    if state_reader is None:
        if not isinstance(budget, InvocationBudget):
            raise ResolutionError("shared invocation budget is required")
    try:
        if state_reader is None:
            state = _read_authenticated_follow_up(identity, budget)
            return follow_up.verify_live_follow_up(identity, state=state)
        return follow_up.verify_live_follow_up(identity, state_reader=state_reader)
    except follow_up.FollowUpError as exc:
        raise ResolutionError(str(exc)) from exc


def _reject_duplicate_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _tracked_follow_ups_from_payload(
    canonical_payload: bytes,
    *,
    repository: str,
    number: int,
    reviewed_state_digest: str,
    thread_ids: tuple[str, ...],
    reviewed_head_sha: str | None = None,
) -> dict[str, FollowUpIdentity]:
    try:
        payload = json.loads(
            canonical_payload,
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_reject_duplicate_json_object,
        )
    except (TypeError, ValueError) as exc:
        raise ResolutionError("eligibility evidence payload is malformed") from exc
    expected_keys = {
        "schema_version",
        "repository",
        "pull_request_number",
        "reviewed_head_sha",
        "reviewed_state_digest",
        "eligible_threads",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ResolutionError("eligibility evidence is unavailable or malformed")
    schema_version = payload.get("schema_version")
    threads = payload.get("eligible_threads")
    observed_head = payload.get("reviewed_head_sha")
    if (
        schema_version not in ("1.0", "1.1")
        or payload.get("repository") != repository
        or payload.get("pull_request_number") != number
        or isinstance(payload.get("pull_request_number"), bool)
        or not isinstance(observed_head, str)
        or not OID.fullmatch(observed_head)
        or (
            reviewed_head_sha is not None
            and observed_head != reviewed_head_sha.lower()
        )
        or payload.get("reviewed_state_digest") != reviewed_state_digest
        or not isinstance(threads, list)
    ):
        raise ResolutionError("eligibility evidence binding is invalid or stale")
    tracked: dict[str, FollowUpIdentity] = {}
    observed_thread_ids: list[str] = []
    for item in threads:
        expected_thread_keys = {
            "thread_id",
            "classification",
            "disposition",
            "finding_ids",
            "evidence_digest",
        }
        if schema_version == "1.1":
            expected_thread_keys.add("follow_up")
        if not isinstance(item, dict) or set(item) != expected_thread_keys:
            raise ResolutionError("eligibility evidence thread is malformed")
        thread_id = item.get("thread_id")
        classification = item.get("classification")
        disposition = item.get("disposition")
        finding_ids = item.get("finding_ids")
        if (
            not isinstance(thread_id, str)
            or not THREAD_ID.fullmatch(thread_id)
            or not isinstance(classification, str)
            or disposition not in ELIGIBLE_DISPOSITIONS.get(
                classification,
                frozenset(),
            )
            or (
                schema_version == "1.0"
                and disposition == "TRACKED_AS_FOLLOW_UP"
            )
            or not isinstance(finding_ids, list)
            or not finding_ids
            or any(
                not isinstance(finding_id, str) or not finding_id
                for finding_id in finding_ids
            )
            or len(finding_ids) != len(set(finding_ids))
            or not isinstance(item.get("evidence_digest"), str)
            or not DIGEST.fullmatch(item["evidence_digest"])
        ):
            raise ResolutionError("eligibility evidence thread is ineligible")
        if disposition == "TRACKED_AS_FOLLOW_UP":
            try:
                tracked[thread_id] = follow_up.parse_follow_up(
                    item.get("follow_up")
                )
            except follow_up.FollowUpError as exc:
                raise ResolutionError(str(exc)) from exc
        elif schema_version == "1.1" and item.get("follow_up") is not None:
            raise ResolutionError(
                "only tracked out-of-scope eligibility may carry follow-up identity"
            )
        observed_thread_ids.append(thread_id)
    if tuple(observed_thread_ids) != thread_ids:
        raise ResolutionError(
            "eligibility evidence must cover requested threads exactly"
        )
    return tracked


def load_eligibility_evidence(
    path: Path,
    repository: str,
    number: int,
    reviewed_head_sha: str,
    reviewed_state_digest: str,
    thread_ids: tuple[str, ...],
    *,
    authenticated_evidence_digest: str,
) -> EligibilityEvidence:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_reject_duplicate_json_object,
        )
    except (OSError, ValueError) as exc:
        raise ResolutionError(
            "eligibility evidence is unavailable or malformed"
        ) from exc
    observed_evidence_digest = _digest_json(payload)
    if (
        not isinstance(authenticated_evidence_digest, str)
        or not DIGEST.fullmatch(authenticated_evidence_digest)
        or observed_evidence_digest != authenticated_evidence_digest
    ):
        raise ResolutionError("eligibility evidence is not authenticated")
    canonical_payload = _canonical_json_bytes(payload)
    _tracked_follow_ups_from_payload(
        canonical_payload,
        repository=repository,
        number=number,
        reviewed_head_sha=reviewed_head_sha,
        reviewed_state_digest=reviewed_state_digest,
        thread_ids=thread_ids,
    )
    return EligibilityEvidence(
        observed_evidence_digest,
        canonical_payload,
    )


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
    api_pages = 0

    for _page in range(budget.maximum_api_calls - budget.api_calls):
        variables: dict[str, str | int] = {"threadId": thread_id}
        if after is not None:
            variables["commentsAfter"] = after
        data = _graphql(TARGET_QUERY, variables, runner, budget)
        api_pages += 1
        node = data.get("node")
        if not isinstance(node, dict) or node.get("__typename") != (
            "PullRequestReviewThread"
        ):
            raise ResolutionError(
                f"target thread does not belong to the pull request: {thread_id}"
            )
        _consume_thread(budget)
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
            database_id = comment.get("databaseId")
            body = comment.get("body")
            reply_to = comment.get("replyTo")
            reply_to_id = (
                reply_to.get("id") if isinstance(reply_to, dict) else None
            )
            if (
                not isinstance(comment_id, str)
                or not comment_id
                or not isinstance(database_id, int)
                or isinstance(database_id, bool)
                or database_id < 1
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
            _consume_comment(budget)
            comments[comment_id] = ThreadCommentState(
                comment_id=comment_id,
                database_id=database_id,
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
        api_pages=api_pages,
        thread=ThreadState(
            thread_id=thread_id,
            is_resolved=is_resolved,
            is_outdated=is_outdated,
            comments=tuple(
                sorted(comments.values(), key=operator.attrgetter("comment_id"))
            ),
        ),
    )


def read_stable_target_thread(
    repository: str,
    number: int,
    thread_id: str,
    budget: InvocationBudget,
    runner: Callable[[Sequence[str]], dict[str, Any]],
) -> TargetRead:
    first = read_target_thread(repository, number, thread_id, budget, runner)
    second = read_target_thread(repository, number, thread_id, budget, runner)
    if first != second:
        raise ResolutionError(
            f"target thread changed while rechecking comments: {thread_id}"
        )
    return second


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
    thread_ids: tuple[str, ...],
    apply: bool,
) -> None:
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise ResolutionError("repository must use owner/name format")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ResolutionError("pull request number must be positive")
    if not isinstance(expected_head, str) or not OID.fullmatch(expected_head):
        raise ResolutionError("expected head must be a full 40-character commit OID")
    if type(thread_ids) is not tuple:
        raise ResolutionError("thread IDs must be supplied as an immutable tuple")
    if not thread_ids:
        raise ResolutionError("at least one thread ID is required")
    if any(not isinstance(value, str) for value in thread_ids):
        raise ResolutionError("thread IDs must be GitHub review-thread node IDs")
    if len(thread_ids) != len(set(thread_ids)):
        raise ResolutionError("thread IDs must be unique")
    if any(not THREAD_ID.fullmatch(value) for value in thread_ids):
        raise ResolutionError("thread IDs must be GitHub review-thread node IDs")
    if not isinstance(apply, bool):
        raise ResolutionError("apply must be boolean")


def validate_expected_targets(
    thread_ids: tuple[str, ...],
    expected_targets: dict[str, ExpectedThreadState] | None,
) -> dict[str, ExpectedThreadState]:
    if (
        not isinstance(expected_targets, dict)
        or set(expected_targets) != set(thread_ids)
    ):
        raise ResolutionError(
            "reviewed target state must cover every requested thread exactly"
        )
    for thread_id, target in expected_targets.items():
        if (
            not isinstance(target, ExpectedThreadState)
            or target.thread_id != thread_id
            or not isinstance(target.is_resolved, bool)
            or not isinstance(target.is_outdated, bool)
            or tuple(
                sorted(target.comments, key=operator.attrgetter("comment_id"))
            )
            != target.comments
            or len({item.comment_id for item in target.comments})
            != len(target.comments)
        ):
            raise ResolutionError("reviewed target state is malformed")
        for comment in target.comments:
            if (
                not isinstance(comment, ThreadCommentState)
                or not isinstance(comment.comment_id, str)
                or not comment.comment_id
                or comment.database_id is not None
                or not isinstance(comment.body_digest, str)
                or not DIGEST.fullmatch(comment.body_digest)
                or (
                    comment.reply_to_id is not None
                    and (
                        not isinstance(comment.reply_to_id, str)
                        or not comment.reply_to_id
                    )
                )
            ):
                raise ResolutionError("reviewed target comment state is malformed")
    return expected_targets


def _matches_reviewed_target(
    current: ThreadState,
    reviewed: ExpectedThreadState,
) -> bool:
    return (
        current.thread_id == reviewed.thread_id
        and current.is_resolved == reviewed.is_resolved
        and tuple(
            (item.comment_id, item.body_digest, item.reply_to_id)
            for item in current.comments
        )
        == tuple(
            (item.comment_id, item.body_digest, item.reply_to_id)
            for item in reviewed.comments
        )
    )


def _reply_state_digest(thread: ThreadState) -> tuple[str, int]:
    replies = [
        {
            "node_id": item.comment_id,
            "database_id": item.database_id,
            "body_digest": item.body_digest,
            "reply_to_id": item.reply_to_id,
        }
        for item in thread.comments
        if item.reply_to_id is not None
    ]
    return _digest_json(replies), len(replies)


def _matches_late_authorization(
    thread: ThreadState,
    authorization: Any,
) -> bool:
    top_level = [item for item in thread.comments if item.reply_to_id is None]
    reply_digest, reply_count = _reply_state_digest(thread)
    return (
        len(top_level) == 1
        and thread.thread_id == authorization.thread_id
        and thread.is_resolved == authorization.is_resolved
        and thread.is_outdated == authorization.is_outdated
        and top_level[0].comment_id
        == authorization.top_level_comment_node_id
        and top_level[0].database_id
        == authorization.top_level_comment_database_id
        and top_level[0].body_digest == authorization.finding_body_digest
        and reply_digest == authorization.reply_state_digest
        and reply_count == authorization.reply_count
    )


def _load_late_classification_evidence(
    path: Path,
) -> tuple[dict[str, Any], ...]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 64 * 1024:
            raise ValueError("invalid size")
        payload = json.loads(
            raw,
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_reject_duplicate_json_object,
        )
    except (OSError, ValueError) as exc:
        raise ResolutionError(
            "late classification evidence is unavailable or malformed"
        ) from exc
    if raw != _canonical_json_bytes(payload):
        raise ResolutionError("late classification evidence is not canonical")
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "threads"}
        or payload.get("schema_version") != "1.0"
        or not isinstance(payload.get("threads"), list)
        or len(payload["threads"]) != 1
    ):
        raise ResolutionError("late classification evidence shape is unsupported")
    decisions: list[dict[str, Any]] = []
    for item in payload["threads"]:
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "thread_id",
                "classification",
                "disposition",
                "technically_blocking",
                "classification_evidence_digest",
            }
            or not isinstance(item.get("thread_id"), str)
            or not THREAD_ID.fullmatch(item["thread_id"])
            or item.get("classification") != "INVALID_FALSE_OR_MISLEADING"
            or item.get("disposition")
            not in ELIGIBLE_DISPOSITIONS["INVALID_FALSE_OR_MISLEADING"]
            or item.get("technically_blocking") is not False
            or not isinstance(item.get("classification_evidence_digest"), str)
            or not DIGEST.fullmatch(item["classification_evidence_digest"])
        ):
            raise ResolutionError("late classification is not resolution-eligible")
        decisions.append(item)
    identities = [item["thread_id"] for item in decisions]
    if len(identities) != len(set(identities)):
        raise ResolutionError("late classification contains duplicate threads")
    return tuple(decisions)


def create_late_disposition_artifact(
    repository: str,
    delivery_issue_number: int,
    number: int,
    expected_head: str,
    *,
    repository_root: Path | str,
    final_reviewed_state_path: Path | str,
    expected_final_reviewed_state_digest: str,
    final_validation_evidence_path: Path | str,
    classification_evidence_path: Path | str,
    output_path: Path | str,
    signature_output_path: Path | str,
) -> dict[str, Any]:
    if not REPOSITORY.fullmatch(repository):
        raise ResolutionError("repository must use owner/name format")
    if (
        not isinstance(delivery_issue_number, int)
        or isinstance(delivery_issue_number, bool)
        or delivery_issue_number < 1
        or not isinstance(number, int)
        or isinstance(number, bool)
        or number < 1
        or not isinstance(expected_head, str)
        or not OID.fullmatch(expected_head)
        or not isinstance(expected_final_reviewed_state_digest, str)
        or not DIGEST.fullmatch(expected_final_reviewed_state_digest)
    ):
        raise ResolutionError("late-disposition delivery identity is malformed")
    decisions = _load_late_classification_evidence(
        Path(classification_evidence_path)
    )
    thread_ids = tuple(item["thread_id"] for item in decisions)
    final_reviewed = load_reviewed_state(
        Path(final_reviewed_state_path),
        repository,
        number,
        expected_final_reviewed_state_digest,
        (),
    )
    validation = load_validation_evidence(
        Path(final_validation_evidence_path),
        repository,
        expected_head,
        final_reviewed,
    )
    root = Path(repository_root)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_output = Path(output_path).resolve()
        resolved_signature_output = Path(signature_output_path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ResolutionError("late-disposition output location is unavailable") from exc
    if (
        resolved_output == resolved_root
        or resolved_root in resolved_output.parents
        or resolved_signature_output == resolved_root
        or resolved_root in resolved_signature_output.parents
    ):
        raise ResolutionError(
            "late-disposition evidence must be stored outside the delivery repository"
        )
    signer = verify_local_fix_commit(
        root,
        repository,
        expected_head,
        final_reviewed,
        validation,
        require_signer_identity=True,
    )
    limits = load_repository_limits(repository)
    budget = InvocationBudget(
        limits.maximum_api_calls,
        limits.maximum_threads,
        limits.maximum_comments,
    )
    authorizations: list[dict[str, Any]] = []
    for decision in decisions:
        thread_id = decision["thread_id"]
        target = read_stable_target_thread(
            repository, number, thread_id, budget, _run_gh
        )
        require_expected_target(target, repository, number, expected_head)
        top_level = [
            item for item in target.thread.comments if item.reply_to_id is None
        ]
        if len(top_level) != 1 or target.thread.is_resolved:
            raise ResolutionError(
                f"late target must be one unresolved source conversation: {thread_id}"
            )
        reply_digest, reply_count = _reply_state_digest(target.thread)
        authorizations.append(
            {
                "thread_id": thread_id,
                "top_level_comment_node_id": top_level[0].comment_id,
                "top_level_comment_database_id": top_level[0].database_id,
                "finding_body_digest": top_level[0].body_digest,
                "reply_state_digest": reply_digest,
                "reply_count": reply_count,
                "is_resolved": False,
                "is_outdated": target.thread.is_outdated,
                "classification": decision["classification"],
                "disposition": decision["disposition"],
                "technically_blocking": False,
                "classification_evidence_digest": decision[
                    "classification_evidence_digest"
                ],
                "authorized_action": "RESOLVE_REVIEW_THREAD",
            }
        )
    artifact = {
        "schema_version": late_disposition.SCHEMA_VERSION,
        "kind": late_disposition.KIND,
        "repository": repository,
        "delivery_issue_number": delivery_issue_number,
        "pull_request_number": number,
        "head_sha": expected_head.lower(),
        "validated_tree_sha": validation.validated_tree_sha,
        "validation_receipt_digest": validation.validation_receipt_digest,
        "validation_attestation_digest": validation.evidence_digest,
        "final_eligibility_evidence_digest": (
            validation.eligibility_evidence_digest
        ),
        "delivery_signer": {
            "format": signer.signature_format,
            "fingerprint": signer.fingerprint,
        },
        "authorized_action": "RESOLVE_EXACT_REVIEW_THREADS",
        "threads": authorizations,
    }
    try:
        configured_format, signing_key = (
            late_disposition.read_signing_configuration()
        )
    except late_disposition.LateDispositionError as exc:
        raise ResolutionError(str(exc)) from exc
    if configured_format != signer.signature_format or not signing_key:
        raise ResolutionError(
            "OS-account signing configuration does not match final delivery signer"
        )
    if signer.signature_format == "ssh":
        key_path = Path(signing_key)
        if not key_path.is_absolute():
            raise ResolutionError("SSH signing key must use an absolute path")
        try:
            resolved_key = key_path.resolve(strict=True)
            account_home = late_disposition.os_account_home()
            key_stat = resolved_key.stat()
        except (OSError, RuntimeError) as exc:
            raise ResolutionError("SSH signing key is unavailable") from exc
        if (
            resolved_key == resolved_root
            or resolved_root in resolved_key.parents
            or not (
                resolved_key == account_home
                or account_home in resolved_key.parents
            )
            or key_stat.st_uid != os.getuid()
            or key_stat.st_mode & 0o022
        ):
            raise ResolutionError("SSH signing key is not OS-account controlled")
    try:
        late_disposition.sign_artifact(
            artifact,
            Path(output_path),
            Path(signature_output_path),
            signer=signer,
            signing_key=signing_key,
        )
    except late_disposition.LateDispositionError as exc:
        raise ResolutionError(str(exc)) from exc
    artifact_digest = hashlib.sha256(
        late_disposition.canonical_json_bytes(artifact)
    ).hexdigest()
    return {
        "status": "LATE_DISPOSITION_AUTHENTICATED",
        "repository": repository,
        "delivery_issue_number": delivery_issue_number,
        "pull_request_number": number,
        "head_sha": expected_head.lower(),
        "artifact_digest": artifact_digest,
        "signature_format": signer.signature_format,
        "signer_fingerprint": signer.fingerprint,
        "thread_ids": list(thread_ids),
        "authorized_action": "RESOLVE_EXACT_REVIEW_THREADS",
        "delivery_tree_changed": False,
        "lifecycle_consumption": {
            "unrestricted_reviews": 0,
            "remediation_cycles": 0,
            "delivery_commits": 0,
            "pushes": 0,
            "ready_transitions": 0,
        },
    }


def resolve_late_disposition_threads(
    repository: str,
    delivery_issue_number: int,
    number: int,
    expected_head: str,
    thread_ids: tuple[str, ...],
    *,
    apply: bool,
    repository_root: Path | str,
    final_reviewed_state_path: Path | str,
    expected_final_reviewed_state_digest: str,
    final_validation_evidence_path: Path | str,
    late_disposition_evidence_path: Path | str,
    late_disposition_signature_path: Path | str,
) -> dict[str, Any]:
    """Resolve only exact late threads authenticated independently of Git history."""

    validate_request(repository, number, expected_head, thread_ids, apply)
    if len(thread_ids) != 1:
        raise ResolutionError(
            "late disposition authorizes exactly one review thread"
        )
    if (
        not isinstance(delivery_issue_number, int)
        or isinstance(delivery_issue_number, bool)
        or delivery_issue_number < 1
    ):
        raise ResolutionError("delivery issue number must be positive")
    if (
        not isinstance(expected_final_reviewed_state_digest, str)
        or not DIGEST.fullmatch(expected_final_reviewed_state_digest)
    ):
        raise ResolutionError("final reviewed-state digest is required")
    final_reviewed = load_reviewed_state(
        Path(final_reviewed_state_path),
        repository,
        number,
        expected_final_reviewed_state_digest,
        (),
    )
    validation = load_validation_evidence(
        Path(final_validation_evidence_path),
        repository,
        expected_head,
        final_reviewed,
    )
    signer = verify_local_fix_commit(
        Path(repository_root),
        repository,
        expected_head,
        final_reviewed,
        validation,
        require_signer_identity=True,
    )
    try:
        authorization = late_disposition.parse_artifact(
            Path(late_disposition_evidence_path),
            Path(late_disposition_signature_path),
            expected_signer=signer,
            repository=repository,
            delivery_issue_number=delivery_issue_number,
            pull_request_number=number,
            head_sha=expected_head,
            validated_tree_sha=validation.validated_tree_sha,
            validation_receipt_digest=validation.validation_receipt_digest,
            validation_attestation_digest=validation.evidence_digest,
            final_eligibility_evidence_digest=(
                validation.eligibility_evidence_digest
            ),
            thread_ids=thread_ids,
            allowed_dispositions=ELIGIBLE_DISPOSITIONS,
        )
    except late_disposition.LateDispositionError as exc:
        raise ResolutionError(str(exc)) from exc

    limits = load_repository_limits(repository)
    budget = InvocationBudget(
        limits.maximum_api_calls,
        limits.maximum_threads,
        limits.maximum_comments,
    )
    expected = {item.thread_id: item for item in authorization.threads}
    initial_targets: dict[str, TargetRead] = {}
    for thread_id in thread_ids:
        target = read_target_thread(repository, number, thread_id, budget, _run_gh)
        require_expected_target(target, repository, number, expected_head)
        if not _matches_late_authorization(target.thread, expected[thread_id]):
            raise ResolutionError(
                f"target thread differs from authenticated late disposition: {thread_id}"
            )
        initial_targets[thread_id] = target

    pending = list(thread_ids)
    applied: list[str] = []
    already_resolved: list[str] = []
    if apply:
        minimum_pages = sum(item.api_pages * 4 for item in initial_targets.values())
        minimum_comments = sum(
            len(item.thread.comments) * 4 for item in initial_targets.values()
        )
        if budget.maximum_api_calls - budget.api_calls < minimum_pages + len(thread_ids):
            raise ResolutionError(
                "registered API call limit cannot cover all target rechecks and writes"
            )
        if budget.maximum_threads - budget.threads < minimum_pages:
            raise ResolutionError(
                "registered review thread limit cannot cover all target rechecks"
            )
        if budget.maximum_comments - budget.comments < minimum_comments:
            raise ResolutionError(
                "registered review comment limit cannot cover all target rechecks"
            )
        for thread_id in thread_ids:
            preflight = read_stable_target_thread(
                repository, number, thread_id, budget, _run_gh
            )
            require_expected_target(preflight, repository, number, expected_head)
            if (
                preflight.thread != initial_targets[thread_id].thread
                or not _matches_late_authorization(
                    preflight.thread, expected[thread_id]
                )
            ):
                raise ResolutionError(
                    f"target thread changed during late-disposition preflight: {thread_id}"
                )
        for index, thread_id in enumerate(thread_ids):
            phase = "recheck"
            try:
                current = read_stable_target_thread(
                    repository, number, thread_id, budget, _run_gh
                )
                require_expected_target(current, repository, number, expected_head)
                if (
                    current.thread != initial_targets[thread_id].thread
                    or not _matches_late_authorization(
                        current.thread, expected[thread_id]
                    )
                ):
                    raise ResolutionError(
                        f"target thread changed before resolution: {thread_id}"
                    )
                phase = "mutation"
                data = _graphql(
                    RESOLVE_MUTATION,
                    {"threadId": thread_id},
                    _run_gh,
                    budget,
                )
                mutation = data.get("resolveReviewThread")
                result = mutation.get("thread") if isinstance(mutation, dict) else None
                if (
                    not isinstance(result, dict)
                    or result.get("id") != thread_id
                    or result.get("isResolved") is not True
                ):
                    raise ResolutionError(
                        f"GitHub did not confirm resolution for {thread_id}"
                    )
            except ResolutionError as exc:
                return {
                    "repository": repository,
                    "delivery_issue_number": delivery_issue_number,
                    "pull_request_number": number,
                    "head_sha": expected_head.lower(),
                    "validation_evidence_digest": validation.evidence_digest,
                    "late_disposition_evidence_digest": authorization.artifact_digest,
                    "eligibility_path": "authenticated_late_disposition",
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
                                "unknown" if phase == "mutation" else "not_attempted"
                            ),
                            "error": str(exc),
                        }
                    ],
                    "unattempted": list(thread_ids[index + 1 :]),
                }
            applied.append(thread_id)

    return {
        "repository": repository,
        "delivery_issue_number": delivery_issue_number,
        "pull_request_number": number,
        "head_sha": expected_head.lower(),
        "validation_evidence_digest": validation.evidence_digest,
        "late_disposition_evidence_digest": authorization.artifact_digest,
        "eligibility_path": "authenticated_late_disposition",
        "mode": "apply" if apply else "dry-run",
        "status": "success",
        "already_resolved": already_resolved,
        "pending": pending if not apply else [],
        "resolved": applied,
        "failed": [],
        "unattempted": [],
        "lifecycle_consumption": {
            "unrestricted_reviews": 0,
            "remediation_cycles": 0,
            "delivery_commits": 0,
            "pushes": 0,
            "ready_transitions": 0,
        },
    }


def resolve_threads(
    repository: str,
    number: int,
    expected_head: str,
    thread_ids: tuple[str, ...],
    *,
    apply: bool,
    repository_root: Path | str | None = None,
    reviewed_state_path: Path | str | None = None,
    expected_reviewed_state_digest: str | None = None,
    validation_evidence_path: Path | str | None = None,
    eligibility_evidence_path: Path | str | None = None,
    **caller_constructed_authorization: Any,
) -> dict[str, Any]:
    """Resolve threads only after proving the complete local evidence chain."""
    validate_request(repository, number, expected_head, thread_ids, apply)
    if caller_constructed_authorization:
        raise ResolutionError(
            "authenticated mutation boundary rejects caller-constructed evidence"
        )
    if (
        repository_root is None
        or reviewed_state_path is None
        or validation_evidence_path is None
        or eligibility_evidence_path is None
        or not isinstance(expected_reviewed_state_digest, str)
        or not DIGEST.fullmatch(expected_reviewed_state_digest)
    ):
        raise ResolutionError(
            "authenticated mutation boundary requires canonical evidence inputs"
        )
    reviewed = load_reviewed_state(
        Path(reviewed_state_path),
        repository,
        number,
        expected_reviewed_state_digest,
        thread_ids,
    )
    validation = load_validation_evidence(
        Path(validation_evidence_path),
        repository,
        expected_head,
        reviewed,
    )
    verify_local_fix_commit(
        Path(repository_root),
        repository,
        expected_head,
        reviewed,
        validation,
    )
    eligibility = load_eligibility_evidence(
        Path(eligibility_evidence_path),
        repository,
        number,
        reviewed.head_sha,
        reviewed.state_digest,
        thread_ids,
        authenticated_evidence_digest=validation.eligibility_evidence_digest,
    )
    expected_targets = reviewed.targets
    reviewed_state_digest = reviewed.state_digest
    validation_evidence_digest = validation.evidence_digest
    eligibility_evidence_digest = eligibility.evidence_digest
    eligibility_evidence: EligibilityEvidence | None = eligibility
    follow_up_verifier = verify_live_follow_up
    runner = _run_gh
    if (
        not isinstance(reviewed_state_digest, str)
        or not DIGEST.fullmatch(reviewed_state_digest)
    ):
        raise ResolutionError("reviewed state digest is required")
    if (
        not isinstance(validation_evidence_digest, str)
        or not DIGEST.fullmatch(validation_evidence_digest)
    ):
        raise ResolutionError("validation evidence digest is required")
    if (
        not isinstance(eligibility_evidence_digest, str)
        or not DIGEST.fullmatch(eligibility_evidence_digest)
    ):
        raise ResolutionError("eligibility evidence digest is required")
    reviewed_targets = validate_expected_targets(thread_ids, expected_targets)
    tracked: dict[str, FollowUpIdentity] = {}
    if apply and eligibility_evidence is None:
        raise ResolutionError(
            "authenticated canonical eligibility evidence is required for apply"
        )
    if eligibility_evidence is not None:
        if (
            not isinstance(eligibility_evidence, EligibilityEvidence)
            or eligibility_evidence.evidence_digest != eligibility_evidence_digest
            or not isinstance(eligibility_evidence.canonical_payload, bytes)
            or hashlib.sha256(eligibility_evidence.canonical_payload).hexdigest()
            != eligibility_evidence_digest
        ):
            raise ResolutionError("tracked follow-up evidence is not authenticated")
        tracked = _tracked_follow_ups_from_payload(
            eligibility_evidence.canonical_payload,
            repository=repository,
            number=number,
            reviewed_state_digest=reviewed_state_digest,
            thread_ids=thread_ids,
        )
    limits = load_repository_limits(repository)
    budget = InvocationBudget(
        limits.maximum_api_calls,
        limits.maximum_threads,
        limits.maximum_comments,
    )
    initial_targets: dict[str, TargetRead] = {}
    for thread_id in thread_ids:
        target = read_target_thread(
            repository,
            number,
            thread_id,
            budget,
            runner,
        )
        require_expected_target(target, repository, number, expected_head)
        reviewed_target = reviewed_targets[thread_id]
        if not _matches_reviewed_target(target.thread, reviewed_target):
            raise ResolutionError(
                f"target thread differs from reviewed feedback: {thread_id}"
            )
        initial_targets[thread_id] = target

    already_resolved: list[str] = []
    pending = [
        thread_id
        for thread_id in thread_ids
        if not initial_targets[thread_id].thread.is_resolved
    ]
    applied: list[str] = []

    if apply:
        minimum_recheck_pages = sum(
            initial_targets[thread_id].api_pages * 2
            for thread_id in thread_ids
        )
        minimum_recheck_comments = sum(
            len(initial_targets[thread_id].thread.comments) * 2
            for thread_id in thread_ids
        )
        if (
            budget.maximum_api_calls - budget.api_calls
            < minimum_recheck_pages + len(pending)
        ):
            raise ResolutionError(
                "registered API call limit cannot cover all target rechecks and writes"
            )
        if budget.maximum_threads - budget.threads < minimum_recheck_pages:
            raise ResolutionError(
                "registered review thread limit cannot cover all target rechecks"
            )
        if budget.maximum_comments - budget.comments < minimum_recheck_comments:
            raise ResolutionError(
                "registered review comment limit cannot cover all target rechecks"
            )
        for index, thread_id in enumerate(thread_ids):
            phase = "follow-up" if thread_id in tracked else "recheck"
            try:
                if (
                    not initial_targets[thread_id].thread.is_resolved
                    and thread_id in tracked
                ):
                    follow_up_verifier(tracked[thread_id], budget)
                phase = "recheck"
                remaining_thread_ids = thread_ids[index:]
                required_recheck_pages = sum(
                    initial_targets[remaining_thread_id].api_pages * 2
                    for remaining_thread_id in remaining_thread_ids
                )
                required_recheck_comments = sum(
                    len(initial_targets[remaining_thread_id].thread.comments) * 2
                    for remaining_thread_id in remaining_thread_ids
                )
                required_mutations = sum(
                    not initial_targets[remaining_thread_id].thread.is_resolved
                    for remaining_thread_id in remaining_thread_ids
                )
                required_follow_up_reads = sum(
                    remaining_thread_id != thread_id
                    and not initial_targets[remaining_thread_id].thread.is_resolved
                    and remaining_thread_id in tracked
                    for remaining_thread_id in remaining_thread_ids
                )
                if (
                    budget.maximum_api_calls - budget.api_calls
                    < required_recheck_pages
                    + required_mutations
                    + required_follow_up_reads
                ):
                    raise ResolutionError(
                        "registered API call limit cannot cover the remaining "
                        "follow-up reads, target rechecks, and writes"
                    )
                if (
                    budget.maximum_threads - budget.threads
                    < required_recheck_pages
                ):
                    raise ResolutionError(
                        "registered review thread limit cannot cover the remaining "
                        "target rechecks"
                    )
                if (
                    budget.maximum_comments - budget.comments
                    < required_recheck_comments
                ):
                    raise ResolutionError(
                        "registered review comment limit cannot cover the remaining "
                        "target rechecks"
                    )
                current = read_stable_target_thread(
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
                if current.thread != initial_targets[thread_id].thread:
                    raise ResolutionError(
                        f"target thread changed before resolution: {thread_id}"
                    )
                if initial_targets[thread_id].thread.is_resolved:
                    already_resolved.append(thread_id)
                    continue
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
                    "reviewed_state_digest": reviewed_state_digest,
                    "validation_evidence_digest": validation_evidence_digest,
                    "eligibility_evidence_digest": eligibility_evidence_digest,
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
                    "unattempted": list(thread_ids[index + 1 :]),
                }
            applied.append(thread_id)
    else:
        already_resolved = sorted(
            thread_id
            for thread_id in thread_ids
            if initial_targets[thread_id].thread.is_resolved
        )

    return {
        "repository": repository,
        "pull_request_number": number,
        "head_sha": expected_head.lower(),
        "reviewed_state_digest": reviewed_state_digest,
        "validation_evidence_digest": validation_evidence_digest,
        "eligibility_evidence_digest": eligibility_evidence_digest,
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
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--reviewed-state", required=True)
    parser.add_argument("--expected-reviewed-state-digest", required=True)
    parser.add_argument("--validation-evidence", required=True)
    parser.add_argument("--eligibility-evidence")
    parser.add_argument("--delivery-issue", type=int)
    parser.add_argument("--late-disposition-evidence")
    parser.add_argument("--late-disposition-signature")
    parser.add_argument("--thread-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args(argv)
    arguments.thread_id = tuple(arguments.thread_id)
    try:
        validate_request(
            arguments.repo,
            arguments.pr,
            arguments.expected_head,
            arguments.thread_id,
            arguments.apply,
        )
        if not DIGEST.fullmatch(arguments.expected_reviewed_state_digest):
            raise ResolutionError(
                "expected reviewed state digest must be a SHA-256 digest"
            )
        late_values = (
            arguments.delivery_issue,
            arguments.late_disposition_evidence,
            arguments.late_disposition_signature,
        )
        if any(value is not None for value in late_values):
            if not all(value is not None for value in late_values):
                raise ResolutionError(
                    "late disposition requires delivery issue, artifact, and signature"
                )
            if arguments.eligibility_evidence is not None:
                raise ResolutionError(
                    "commit-bound and late-disposition eligibility are mutually exclusive"
                )
        elif arguments.eligibility_evidence is None:
            raise ResolutionError(
                "commit-bound resolution requires eligibility evidence"
            )
    except ResolutionError as exc:
        parser.error(str(exc))
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if arguments.late_disposition_evidence is not None:
            result = resolve_late_disposition_threads(
                arguments.repo,
                arguments.delivery_issue,
                arguments.pr,
                arguments.expected_head,
                arguments.thread_id,
                apply=arguments.apply,
                repository_root=arguments.repo_root,
                final_reviewed_state_path=arguments.reviewed_state,
                expected_final_reviewed_state_digest=(
                    arguments.expected_reviewed_state_digest
                ),
                final_validation_evidence_path=arguments.validation_evidence,
                late_disposition_evidence_path=(
                    arguments.late_disposition_evidence
                ),
                late_disposition_signature_path=(
                    arguments.late_disposition_signature
                ),
            )
        else:
            result = resolve_threads(
                arguments.repo,
                arguments.pr,
                arguments.expected_head,
                arguments.thread_id,
                apply=arguments.apply,
                repository_root=arguments.repo_root,
                reviewed_state_path=arguments.reviewed_state,
                expected_reviewed_state_digest=(
                    arguments.expected_reviewed_state_digest
                ),
                validation_evidence_path=arguments.validation_evidence,
                eligibility_evidence_path=arguments.eligibility_evidence,
            )
    except ResolutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
