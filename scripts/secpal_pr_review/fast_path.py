#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Small, head-bound fast path for stable PR feedback and batch resolution."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar


OID = re.compile(r"^[0-9a-fA-F]{40,64}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[^\x00-\x20\x7f]+$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SUPPORTED_BATCH_CAPABILITIES = frozenset({"THREAD_RESOLUTION"})
ELIGIBLE_DISPOSITIONS = frozenset({
    "CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX", "DISPROVEN_WITH_EVIDENCE",
    "NON_ACTIONABLE", "DUPLICATE_OF_CANONICAL", "OBSOLETE_ON_CURRENT_HEAD",
    "SUPERSEDED_BY_CANONICAL", "REJECTED_SECURITY_WEAKENING",
})


class SecurityBlocker(RuntimeError):
    """Fail-closed state or identity evidence stopped the batch."""


class RecoverableLocalError(RuntimeError):
    """A correctable local invocation or workspace preparation error."""


class TransientReadFailure(RuntimeError):
    """A GitHub read failed before any mutation had an ambiguous result."""


class MutationFailure(RuntimeError):
    """GitHub definitively rejected one mutation; never retry it automatically."""


class UnknownWriteResult(RuntimeError):
    """A mutation may have applied but its response is not authoritative."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not IDENTITY.fullmatch(value):
        raise SecurityBlocker(f"{label} is missing or unsafe")
    return value


def _require_oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or not OID.fullmatch(value):
        raise SecurityBlocker(f"{label} is not a complete commit OID")
    return value.lower()


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise SecurityBlocker(f"{label} is not a SHA-256 digest")
    return value


def _actor(value: Any, label: str, *, allow_deleted: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SecurityBlocker(f"{label} actor identity is missing")
    actor = {
        "login": value.get("login"),
        "node_id": value.get("node_id"),
        "database_id": value.get("database_id"),
    }
    if allow_deleted and all(actor[key] is None for key in actor):
        return actor
    if not isinstance(actor["login"], str) or not actor["login"]:
        raise SecurityBlocker(f"{label} actor login is missing")
    if not isinstance(actor["node_id"], str) or not actor["node_id"]:
        raise SecurityBlocker(f"{label} actor node identity is missing")
    if not isinstance(actor["database_id"], int) or actor["database_id"] < 1:
        raise SecurityBlocker(f"{label} actor database identity is missing")
    return actor


def _reaction(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SecurityBlocker(f"{label} reaction is malformed")
    return {
        "mutation_id": _require_string(value.get("mutation_id"), f"{label} reaction"),
        "content": _require_string(value.get("content"), f"{label} reaction content"),
        "actor": _actor(value.get("actor"), f"{label} reaction", allow_deleted=True),
    }


def _reactions(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SecurityBlocker(f"{label} reactions are malformed")
    normalized = [_reaction(item, label) for item in value]
    identities = [item["mutation_id"] for item in normalized]
    if len(identities) != len(set(identities)):
        raise SecurityBlocker(f"{label} contains duplicate reaction identities")
    return sorted(normalized, key=lambda item: (item["mutation_id"], item["content"]))


def _feedback_projection(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("feedback") if isinstance(payload.get("feedback"), dict) else payload
    pull_request_reactions = _reactions(
        source.get("pull_request_reactions", []), "pull request"
    )
    reviews_value = source.get("reviews", [])
    comments_value = source.get("conversation_comments", [])
    threads_value = source.get("threads", [])
    if not all(isinstance(value, list) for value in (reviews_value, comments_value, threads_value)):
        raise SecurityBlocker("stable feedback connections are malformed")

    reviews: list[dict[str, Any]] = []
    for item in reviews_value:
        if not isinstance(item, dict):
            raise SecurityBlocker("review feedback is malformed")
        reviews.append(
            {
                "node_id": _require_string(item.get("node_id"), "review identity"),
                "body_digest": _require_digest(item.get("body_digest"), "review body digest"),
                "actor": _actor(item.get("actor"), "review", allow_deleted=True),
                "state": _require_string(item.get("state"), "review state"),
                "commit_oid": (
                    _require_oid(item.get("commit_oid"), "review commit")
                    if item.get("commit_oid") is not None
                    else None
                ),
                "reactions": _reactions(item.get("reactions", []), "review"),
            }
        )

    comments: list[dict[str, Any]] = []
    for item in comments_value:
        if not isinstance(item, dict):
            raise SecurityBlocker("conversation feedback is malformed")
        updated_at = item.get("updated_at")
        if updated_at is not None and not isinstance(updated_at, str):
            raise SecurityBlocker("conversation comment update identity is malformed")
        comments.append(
            {
                "node_id": _require_string(item.get("node_id"), "conversation comment identity"),
                "body_digest": _require_digest(
                    item.get("body_digest"), "conversation comment body digest"
                ),
                "actor": _actor(
                    item.get("actor"), "conversation comment", allow_deleted=True
                ),
                "updated_at": updated_at,
                "reactions": _reactions(item.get("reactions", []), "conversation comment"),
            }
        )

    threads: list[dict[str, Any]] = []
    for thread in threads_value:
        if not isinstance(thread, dict) or not isinstance(thread.get("comments"), list):
            raise SecurityBlocker("review thread feedback is malformed")
        thread_id = _require_string(thread.get("node_id"), "review thread identity")
        if not isinstance(thread.get("is_resolved"), bool) or not isinstance(
            thread.get("is_outdated"), bool
        ):
            raise SecurityBlocker(f"review thread {thread_id} state is incomplete")
        thread_comments: list[dict[str, Any]] = []
        for item in thread["comments"]:
            if not isinstance(item, dict):
                raise SecurityBlocker(f"review thread {thread_id} comment is malformed")
            reply_to_id = item.get("reply_to_id")
            if reply_to_id is not None:
                reply_to_id = _require_string(reply_to_id, "reply parent identity")
            thread_comments.append(
                {
                    "node_id": _require_string(item.get("node_id"), "thread comment identity"),
                    "body_digest": _require_digest(
                        item.get("body_digest"), "thread comment body digest"
                    ),
                    "actor": _actor(
                        item.get("actor"), "thread comment", allow_deleted=True
                    ),
                    "reply_to_id": reply_to_id,
                    "reactions": _reactions(item.get("reactions", []), "thread comment"),
                }
            )
        threads.append(
            {
                "node_id": thread_id,
                "is_resolved": thread["is_resolved"],
                "is_outdated": thread["is_outdated"],
                "comments": sorted(thread_comments, key=lambda item: item["node_id"]),
            }
        )

    projection = {
        "pull_request_reactions": pull_request_reactions,
        "reviews": sorted(reviews, key=lambda item: item["node_id"]),
        "conversation_comments": sorted(comments, key=lambda item: item["node_id"]),
        "threads": sorted(threads, key=lambda item: item["node_id"]),
    }
    for label, items in (
        ("reviews", projection["reviews"]),
        ("conversation comments", projection["conversation_comments"]),
        ("review threads", projection["threads"]),
    ):
        identities = [item["node_id"] for item in items]
        if len(identities) != len(set(identities)):
            raise SecurityBlocker(f"stable feedback contains duplicate {label}")
    return projection


@dataclass
class StableFeedbackState:
    """Canonical review evidence; deliberately excludes checks and mergeability."""

    repository: str
    pull_request_number: int
    head_sha: str
    pr_state: str
    feedback: dict[str, Any]
    feedback_digest: str = field(init=False)
    state_digest: str = field(init=False)

    def __post_init__(self) -> None:
        self.repository = _require_string(self.repository, "repository")
        if not REPOSITORY.fullmatch(self.repository):
            raise SecurityBlocker("repository identity is invalid")
        if not isinstance(self.pull_request_number, int) or self.pull_request_number < 1:
            raise SecurityBlocker("pull request identity is invalid")
        self.head_sha = _require_oid(self.head_sha, "stable feedback head")
        if self.pr_state not in {"OPEN", "CLOSED", "MERGED"}:
            raise SecurityBlocker("pull request state is invalid")
        self.feedback = _feedback_projection(self.feedback)
        self.refresh_digests()

    @classmethod
    def from_payload(cls, payload: Any) -> "StableFeedbackState":
        if not isinstance(payload, dict):
            raise SecurityBlocker("stable feedback payload must be a JSON object")
        return cls(
            repository=payload.get("repository"),
            pull_request_number=payload.get("pull_request_number"),
            head_sha=payload.get("head_sha"),
            pr_state=payload.get("pr_state"),
            feedback=_feedback_projection(payload),
        )

    def refresh_digests(self) -> None:
        self.feedback = _feedback_projection(self.feedback)
        self.feedback_digest = digest_json(self.feedback)
        self.state_digest = digest_json(
            {
                "repository": self.repository,
                "pull_request_number": self.pull_request_number,
                "head_sha": self.head_sha,
                "pr_state": self.pr_state,
                "feedback": self.feedback,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "head_sha": self.head_sha,
            "pr_state": self.pr_state,
            **copy.deepcopy(self.feedback),
            "feedback_digest": self.feedback_digest,
            "state_digest": self.state_digest,
        }


@dataclass
class ReadinessState:
    """Volatile local, remote, CI, mergeability, actor, and signature evidence."""

    repository: str
    pull_request_number: int
    head_sha: str
    base_ref: str
    base_sha: str
    local_head_sha: str
    remote_head_sha: str
    worktree_clean: bool
    pull_request_open: bool
    mergeability: str
    actor: dict[str, Any]
    commits: list[dict[str, Any]]


@dataclass(frozen=True)
class BatchOperation:
    operation_id: str
    kind: str
    thread_id: str
    disposition: str


@dataclass
class BatchRequest:
    schema_version: str
    batch_id: str
    repository: str
    pull_request_number: int
    expected_head_sha: str
    expected_actor: dict[str, Any]
    reviewed_state_digest: str
    reviewed_feedback_digest: str
    operations: list[BatchOperation]
    prior_results: list[dict[str, Any]]

    @classmethod
    def from_dict(cls, value: Any) -> "BatchRequest":
        if not isinstance(value, dict):
            raise SecurityBlocker("batch request must be a JSON object")
        expected_keys = {
            "schema_version",
            "batch_id",
            "repository",
            "pull_request_number",
            "expected_head_sha",
            "expected_actor",
            "reviewed_state_digest",
            "reviewed_feedback_digest",
            "operations",
            "prior_results",
        }
        if set(value) != expected_keys:
            raise SecurityBlocker("batch request contains unsupported capabilities or missing fields")
        if value["schema_version"] != "1.0":
            raise SecurityBlocker("batch request schema version is unsupported")
        operations_value = value["operations"]
        if not isinstance(operations_value, list) or not operations_value:
            raise SecurityBlocker("batch request requires at least one operation")
        operations: list[BatchOperation] = []
        for item in operations_value:
            if not isinstance(item, dict) or set(item) != {
                "operation_id",
                "kind",
                "thread_id",
                "disposition",
            }:
                raise SecurityBlocker("batch operation shape is invalid")
            if item["kind"] not in SUPPORTED_BATCH_CAPABILITIES:
                raise SecurityBlocker(f"unsupported batch capability: {item['kind']}")
            if item["disposition"] not in ELIGIBLE_DISPOSITIONS:
                raise SecurityBlocker("thread disposition is not eligible for resolution")
            operations.append(
                BatchOperation(
                    operation_id=_require_string(item["operation_id"], "operation identity"),
                    kind=item["kind"],
                    thread_id=_require_string(item["thread_id"], "thread identity"),
                    disposition=item["disposition"],
                )
            )
        operation_ids = [item.operation_id for item in operations]
        thread_ids = [item.thread_id for item in operations]
        if len(operation_ids) != len(set(operation_ids)) or len(thread_ids) != len(set(thread_ids)):
            raise SecurityBlocker("batch operation and thread identities must be unique")
        prior_results = value["prior_results"]
        if not isinstance(prior_results, list):
            raise SecurityBlocker("prior operation evidence must be a list")
        for result in prior_results:
            if not isinstance(result, dict) or set(result) != {
                "operation_id",
                "thread_id",
                "authorization_digest",
                "mutation_identity",
                "status",
            }:
                raise SecurityBlocker("prior operation evidence is malformed")
            for key in ("operation_id", "thread_id", "mutation_identity"):
                _require_string(result[key], f"prior result {key}")
            _require_digest(result["authorization_digest"], "prior authorization digest")
            if result["status"] != "APPLIED":
                raise SecurityBlocker("prior operation evidence status is not authoritative")
        pull_request_number = value["pull_request_number"]
        if not isinstance(pull_request_number, int) or isinstance(
            pull_request_number, bool
        ) or pull_request_number < 1:
            raise SecurityBlocker("batch pull request identity is invalid")
        repository = _require_string(value["repository"], "repository")
        if not REPOSITORY.fullmatch(repository):
            raise SecurityBlocker("batch repository identity is invalid")
        return cls(
            schema_version="1.0",
            batch_id=_require_string(value["batch_id"], "batch identity"),
            repository=repository,
            pull_request_number=pull_request_number,
            expected_head_sha=_require_oid(value["expected_head_sha"], "expected head"),
            expected_actor=_actor(value["expected_actor"], "expected writer"),
            reviewed_state_digest=_require_digest(
                value["reviewed_state_digest"], "reviewed state digest"
            ),
            reviewed_feedback_digest=_require_digest(
                value["reviewed_feedback_digest"], "reviewed feedback digest"
            ),
            operations=operations,
            prior_results=copy.deepcopy(prior_results),
        )

    @property
    def authorization_digest(self) -> str:
        return digest_json(
            {
                "schema_version": self.schema_version,
                "batch_id": self.batch_id,
                "repository": self.repository,
                "pull_request_number": self.pull_request_number,
                "expected_head_sha": self.expected_head_sha,
                "expected_actor": self.expected_actor,
                "reviewed_state_digest": self.reviewed_state_digest,
                "reviewed_feedback_digest": self.reviewed_feedback_digest,
                "operations": [
                    {
                        "operation_id": item.operation_id,
                        "kind": item.kind,
                        "thread_id": item.thread_id,
                        "disposition": item.disposition,
                    }
                    for item in self.operations
                ],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "expected_head_sha": self.expected_head_sha,
            "expected_actor": copy.deepcopy(self.expected_actor),
            "reviewed_state_digest": self.reviewed_state_digest,
            "reviewed_feedback_digest": self.reviewed_feedback_digest,
            "operations": [
                {
                    "operation_id": item.operation_id,
                    "kind": item.kind,
                    "thread_id": item.thread_id,
                    "disposition": item.disposition,
                }
                for item in self.operations
            ],
            "prior_results": copy.deepcopy(self.prior_results),
        }


def create_validation_attestation(
    *,
    repository: str,
    head_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    successful_result: bool,
    reviewed_state: StableFeedbackState,
) -> dict[str, Any]:
    fields = {
        "schema_version": "1.0",
        "repository": _require_string(repository, "attestation repository"),
        "head_sha": _require_oid(head_sha, "attestation head"),
        "registry_digest": digest_json(registry),
        "command_set_digest": digest_json(command_set),
        "successful_result": successful_result is True,
        "reviewed_head_sha": reviewed_state.head_sha,
        "reviewed_state_digest": reviewed_state.state_digest,
        "reviewed_feedback_digest": reviewed_state.feedback_digest,
    }
    return {**fields, "attestation_digest": digest_json(fields)}


def verify_validation_attestation(
    attestation: Any,
    *,
    repository: str,
    head_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    reviewed_state: StableFeedbackState,
) -> None:
    expected = create_validation_attestation(
        repository=repository,
        head_sha=head_sha,
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed_state,
    )
    if not isinstance(attestation, dict) or attestation != expected:
        raise SecurityBlocker("validation attestation binding is invalid or stale")
    if attestation["successful_result"] is not True:
        raise SecurityBlocker("complete validation did not succeed")


def verify_commit_signatures(commits: Any) -> list[dict[str, Any]]:
    if not isinstance(commits, list) or not commits:
        raise SecurityBlocker("commit signature evidence is missing")
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict):
            raise SecurityBlocker("commit signature evidence is malformed")
        oid = _require_oid(commit.get("oid"), "commit signature identity")
        if oid in seen:
            raise SecurityBlocker("a commit must be signature-verified at most once")
        seen.add(oid)
        source = commit.get("source")
        local = commit.get("local_signature")
        github = commit.get("github_verification")
        if not isinstance(local, dict) or not isinstance(github, dict):
            raise SecurityBlocker(f"signature evidence is incomplete for {oid}")
        local_unknown = local.get("state") in {"unknown_key", "UNKNOWN_LOCAL_KEY"}
        if source == "USER":
            if not (
                local.get("verified") is True
                and local.get("state") == "valid"
                and local.get("format") == "ssh"
            ):
                raise SecurityBlocker(f"invalid or unsigned user-authored commit: {oid}")
            verified.append(
                {
                    "oid": oid,
                    "classification": "LOCAL_SSH_VERIFIED",
                    "local_classification": "VALID",
                }
            )
        elif source == "GITHUB":
            if not (github.get("verified") is True and github.get("reason") == "valid"):
                raise SecurityBlocker(f"GitHub-generated commit verification is invalid: {oid}")
            verified.append(
                {
                    "oid": oid,
                    "classification": "GITHUB_VERIFIED",
                    "local_classification": "UNKNOWN_LOCAL_KEY" if local_unknown else "NOT_REQUIRED",
                }
            )
        else:
            raise SecurityBlocker(f"commit source is unknown for {oid}")
    return verified


def _verify_readiness(request: BatchRequest, readiness: ReadinessState) -> None:
    if readiness.repository != request.repository or readiness.pull_request_number != request.pull_request_number:
        raise SecurityBlocker("repository or pull request identity mismatch")
    heads = {
        "pull request head": readiness.head_sha,
        "local head": readiness.local_head_sha,
        "remote head": readiness.remote_head_sha,
    }
    for label, observed in heads.items():
        if observed != request.expected_head_sha:
            raise SecurityBlocker(
                f"{label} mismatch: expected {request.expected_head_sha}, observed {observed}"
            )
    if not readiness.worktree_clean:
        raise SecurityBlocker("worktree is not clean")
    if not readiness.pull_request_open:
        raise SecurityBlocker("pull request is not open")
    if not isinstance(readiness.base_ref, str) or not readiness.base_ref:
        raise SecurityBlocker("base branch identity is missing")
    _require_oid(readiness.base_sha, "base SHA")
    if readiness.mergeability in {"CONFLICTING", "UNKNOWN", ""}:
        raise SecurityBlocker(f"pull request mergeability is {readiness.mergeability or 'missing'}")
    if _actor(readiness.actor, "current writer") != request.expected_actor:
        raise SecurityBlocker("authenticated actor identity mismatch")
    verify_commit_signatures(readiness.commits)


def _verify_required_checks(checks: Any) -> None:
    if not isinstance(checks, list) or not checks:
        raise SecurityBlocker("required check evidence is missing")
    required = [item for item in checks if isinstance(item, dict) and item.get("required") is True]
    if not required:
        raise SecurityBlocker("required check evidence is missing")
    names: set[str] = set()
    for check in required:
        name = check.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise SecurityBlocker("required check identity is missing or duplicated")
        names.add(name)
        if check.get("status") != "SUCCESS":
            raise SecurityBlocker(f"required check {name} is {check.get('status', 'missing')}")


T = TypeVar("T")


def _read_with_one_retry(action: Callable[[], T]) -> T:
    try:
        return action()
    except TransientReadFailure:
        return action()


def run_recoverable_local_step(action: Callable[[], T], correct: Callable[[], None]) -> T:
    try:
        return action()
    except RecoverableLocalError:
        correct()
        return action()


def _authorized_prior_results(
    request: BatchRequest,
) -> dict[str, dict[str, Any]]:
    operations = {item.operation_id: item for item in request.operations}
    authorized: dict[str, dict[str, Any]] = {}
    for result in request.prior_results:
        operation = operations.get(result["operation_id"])
        if (
            operation is None
            or result["thread_id"] != operation.thread_id
            or result["mutation_identity"] != operation.thread_id
            or result["authorization_digest"] != request.authorization_digest
            or operation.thread_id in authorized
        ):
            raise SecurityBlocker("prior resolution evidence does not belong to this authorized batch")
        authorized[operation.thread_id] = result
    return authorized


def _compare_feedback(
    request: BatchRequest,
    reviewed: StableFeedbackState,
    current: StableFeedbackState,
    authorized: dict[str, dict[str, Any]],
) -> None:
    if (
        current.repository != request.repository
        or current.pull_request_number != request.pull_request_number
        or current.pr_state != "OPEN"
        or current.head_sha != request.expected_head_sha
    ):
        raise SecurityBlocker("stable feedback repository, PR, state, or head changed")
    if current.feedback_digest == reviewed.feedback_digest:
        return
    normalized = copy.deepcopy(current.feedback)
    reviewed_threads = {item["node_id"]: item for item in reviewed.feedback["threads"]}
    for thread in normalized["threads"]:
        thread_id = thread["node_id"]
        expected = reviewed_threads.get(thread_id)
        if (
            thread_id in authorized
            and expected is not None
            and expected["is_resolved"] is False
            and thread["is_resolved"] is True
        ):
            thread["is_resolved"] = False
    if digest_json(normalized) != reviewed.feedback_digest:
        raise SecurityBlocker("stable feedback changed after review")


def _base_report(request: BatchRequest) -> dict[str, Any]:
    return {
        "status": "BATCH_PENDING",
        "batch_id": request.batch_id,
        "authorization_digest": request.authorization_digest,
        "applied": [],
        "already_resolved": [],
        "blocked": [],
        "failed": [],
        "operation_evidence": copy.deepcopy(request.prior_results),
        "write_retry_performed": False,
        "complete_validation_reruns": 0,
    }


def execute_resolution_batch(
    request: BatchRequest,
    attestation: dict[str, Any],
    reviewed_state: StableFeedbackState,
    registry: dict[str, Any],
    gateway: Any,
) -> dict[str, Any]:
    """Preflight once, compare feedback once, then resolve sequentially without retries."""

    if (
        request.repository != reviewed_state.repository
        or request.pull_request_number != reviewed_state.pull_request_number
    ):
        raise SecurityBlocker(
            "batch request does not bind the supplied reviewed feedback identity"
        )
    if request.reviewed_state_digest != reviewed_state.state_digest or request.reviewed_feedback_digest != reviewed_state.feedback_digest:
        raise SecurityBlocker("batch request does not bind the supplied reviewed feedback")
    readiness = _read_with_one_retry(lambda: gateway.read_preflight(request))
    _verify_readiness(request, readiness)
    command_set = registry.get("validation") if isinstance(registry, dict) else None
    if not isinstance(command_set, list):
        raise SecurityBlocker("validation registry command set is missing")
    verify_validation_attestation(
        attestation,
        repository=request.repository,
        head_sha=request.expected_head_sha,
        registry=registry,
        command_set=command_set,
        reviewed_state=reviewed_state,
    )
    checks = _read_with_one_retry(lambda: gateway.read_required_checks(request))
    _verify_required_checks(checks)
    current = _read_with_one_retry(lambda: gateway.read_stable_feedback(request))
    authorized = _authorized_prior_results(request)
    _compare_feedback(request, reviewed_state, current, authorized)

    current_threads = {item["node_id"]: item for item in current.feedback["threads"]}
    for operation in request.operations:
        thread = current_threads.get(operation.thread_id)
        if thread is None:
            raise SecurityBlocker(f"requested thread is missing: {operation.thread_id}")
        if thread["is_resolved"] and operation.thread_id not in authorized:
            raise SecurityBlocker(f"requested thread was resolved outside this batch: {operation.thread_id}")

    report = _base_report(request)
    for index, operation in enumerate(request.operations):
        try:
            target = _read_with_one_retry(
                lambda operation=operation: gateway.read_thread_target(request, operation)
            )
        except (SecurityBlocker, TransientReadFailure) as exc:
            report["status"] = "BLOCKED_TARGET_READ_FAILED"
            report["failed"].append(
                {
                    "operation_id": operation.operation_id,
                    "thread_id": operation.thread_id,
                    "error": str(exc),
                }
            )
            report["blocked"].extend(
                {
                    "operation_id": item.operation_id,
                    "thread_id": item.thread_id,
                    "reason": "stopped after target read failure",
                }
                for item in request.operations[index + 1 :]
            )
            return report
        if not isinstance(target, dict) or target.get("thread_id") != operation.thread_id:
            blocker = "last-moment mutation target identity changed"
        elif target.get("head_sha") != request.expected_head_sha:
            blocker = "last-moment mutation target head changed"
        elif target.get("is_resolved") is True and operation.thread_id in authorized:
            report["already_resolved"].append(
                {"operation_id": operation.operation_id, "thread_id": operation.thread_id}
            )
            continue
        elif target.get("is_resolved") is not False:
            blocker = "last-moment mutation target state changed"
        else:
            blocker = None
        if blocker is not None:
            report["status"] = "BLOCKED_TARGET_CHANGED"
            report["failed"].append(
                {
                    "operation_id": operation.operation_id,
                    "thread_id": operation.thread_id,
                    "error": blocker,
                }
            )
            report["blocked"].extend(
                {
                    "operation_id": item.operation_id,
                    "thread_id": item.thread_id,
                    "reason": "stopped after target change",
                }
                for item in request.operations[index + 1 :]
            )
            return report
        try:
            result = gateway.resolve_thread(request, operation)
            if (
                not isinstance(result, dict)
                or result.get("thread_id") != operation.thread_id
                or result.get("is_resolved") is not True
            ):
                raise UnknownWriteResult("GitHub returned an unverified resolution result")
        except (MutationFailure, UnknownWriteResult) as exc:
            report["status"] = (
                "BLOCKED_UNKNOWN_WRITE_RESULT"
                if isinstance(exc, UnknownWriteResult)
                else "BLOCKED_MUTATION_FAILED"
            )
            report["failed"].append(
                {
                    "operation_id": operation.operation_id,
                    "thread_id": operation.thread_id,
                    "error": str(exc),
                }
            )
            report["blocked"].extend(
                {
                    "operation_id": item.operation_id,
                    "thread_id": item.thread_id,
                    "reason": "stopped after failed write",
                }
                for item in request.operations[index + 1 :]
            )
            return report
        applied = {"operation_id": operation.operation_id, "thread_id": operation.thread_id}
        report["applied"].append(applied)
        report["operation_evidence"].append(
            {
                **applied,
                "authorization_digest": request.authorization_digest,
                "mutation_identity": operation.thread_id,
                "status": "APPLIED",
            }
        )

    report["status"] = "BATCH_APPLIED" if report["applied"] else "BATCH_ALREADY_APPLIED"
    return report


def atomic_write_json(path: Path, value: Any) -> None:
    target = Path(path)
    parent = target.parent.resolve(strict=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            # fdopen may already have closed the descriptor while propagating the failure.
            pass
        try:
            os.unlink(temporary_name)
        except OSError:
            # Preserve the original write failure when best-effort cleanup also fails.
            pass
        raise
