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
EVIDENCE_TEXT = re.compile(r"^[^\x00-\x1f\x7f]+$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SECRET_VALUE = re.compile(
    r"(?i)(?:github_pat_|gh[opsu]_|-----BEGIN [A-Z ]*PRIVATE KEY-----|authorization\s*:\s*bearer)"
)
SUPPORTED_BATCH_CAPABILITIES = frozenset({"THREAD_RESOLUTION"})
SOURCE_KINDS = frozenset(
    {
        "PULL_REQUEST_REACTION",
        "REVIEW",
        "REVIEW_REACTION",
        "CONVERSATION_COMMENT",
        "CONVERSATION_REACTION",
        "THREAD_COMMENT",
        "THREAD_COMMENT_REACTION",
    }
)
THREAD_SOURCE_KINDS = frozenset({"THREAD_COMMENT", "THREAD_COMMENT_REACTION"})
CLASSIFICATION_DISPOSITIONS = {
    "VALID_ACTIONABLE": frozenset({"CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX"}),
    "INVALID_FALSE_OR_MISLEADING": frozenset({"DISPROVEN_WITH_EVIDENCE"}),
    "INFORMATIONAL": frozenset({"NON_ACTIONABLE"}),
    "DUPLICATE": frozenset({"DUPLICATE_OF_CANONICAL"}),
    "OUTDATED_BUT_STILL_VALID": frozenset(
        {"CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX"}
    ),
    "OUTDATED_AND_OBSOLETE": frozenset({"OBSOLETE_ON_CURRENT_HEAD"}),
    "ALREADY_FIXED_ON_SNAPSHOT_HEAD": frozenset({"PROVEN_EXISTING_FIX"}),
    "SUPERSEDED": frozenset({"SUPERSEDED_BY_CANONICAL"}),
    "SECURITY_WEAKENING_SUGGESTION": frozenset({"REJECTED_SECURITY_WEAKENING"}),
}
FIXED_DISPOSITIONS = frozenset({"CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX"})
MERGE_STATE_POLICY = {
    "DIRTY": "block",
    "UNKNOWN": "block",
    "BLOCKED": "block",
    "BEHIND": "strict_base",
    "DRAFT": "block",
    "UNSTABLE": "required_checks",
    "HAS_HOOKS": "allow",
    "CLEAN": "allow",
}
RESOLUTION_MERGE_STATE_POLICY = {
    **MERGE_STATE_POLICY,
    "BLOCKED": "required_checks",
}


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


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            item
            for key, nested in value.items()
            for item in (*_all_strings(key), *_all_strings(nested))
        ]
    if isinstance(value, list):
        return [item for nested in value for item in _all_strings(nested)]
    return []


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
    base_ref: str
    base_sha: str
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
        self.base_ref = _require_string(self.base_ref, "stable feedback base")
        self.base_sha = _require_oid(self.base_sha, "stable feedback base SHA")
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
            base_ref=payload.get("base_ref"),
            base_sha=payload.get("base_sha"),
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
                "base_ref": self.base_ref,
                "base_sha": self.base_sha,
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
            "base_ref": self.base_ref,
            "base_sha": self.base_sha,
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
    base_repository: str
    local_head_sha: str
    remote_head_sha: str
    head_parent_sha: str
    head_tree_sha: str
    validation_receipt_digest: str | None
    worktree_clean: bool
    pull_request_open: bool
    mergeability: str
    merge_state_status: str
    actor: dict[str, Any]
    commits: list[dict[str, Any]]


@dataclass(frozen=True)
class BatchSource:
    kind: str
    node_id: str
    digest: str


@dataclass(frozen=True)
class BatchFinding:
    finding_id: str
    thread_id: str | None
    sources: tuple[BatchSource, ...]
    source_subitem_id: str | None
    classification: str
    disposition: str
    evidence_digest: str
    test_evidence_digest: str | None
    commit_sha: str | None
    canonical_finding_id: str | None


@dataclass(frozen=True)
class BatchOperation:
    operation_id: str
    kind: str
    thread_id: str
    finding_ids: tuple[str, ...]


def _batch_finding_dict(item: BatchFinding) -> dict[str, Any]:
    return {
        "finding_id": item.finding_id,
        "thread_id": item.thread_id,
        "sources": [
            {
                "kind": source.kind,
                "node_id": source.node_id,
                "digest": source.digest,
            }
            for source in item.sources
        ],
        "source_subitem_id": item.source_subitem_id,
        "classification": item.classification,
        "disposition": item.disposition,
        "evidence_digest": item.evidence_digest,
        "test_evidence_digest": item.test_evidence_digest,
        "commit_sha": item.commit_sha,
        "canonical_finding_id": item.canonical_finding_id,
    }


@dataclass
class BatchRequest:
    schema_version: str
    batch_id: str
    repository: str
    pull_request_number: int
    expected_head_sha: str
    expected_base_ref: str
    expected_base_sha: str
    expected_actor: dict[str, Any]
    reviewed_state_digest: str
    reviewed_feedback_digest: str
    findings: list[BatchFinding]
    operations: list[BatchOperation]

    @classmethod
    def from_dict(cls, value: Any) -> "BatchRequest":
        if not isinstance(value, dict):
            raise SecurityBlocker("batch request must be a JSON object")
        if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
            raise SecurityBlocker("batch request contains a secret-like value")
        if "prior_results" in value:
            raise SecurityBlocker(
                "caller-authored prior resolution evidence is not accepted"
            )
        expected_keys = {
            "schema_version",
            "batch_id",
            "repository",
            "pull_request_number",
            "expected_head_sha",
            "expected_base_ref",
            "expected_base_sha",
            "expected_actor",
            "reviewed_state_digest",
            "reviewed_feedback_digest",
            "findings",
            "operations",
        }
        if set(value) != expected_keys:
            raise SecurityBlocker("batch request contains unsupported capabilities or missing fields")
        if value["schema_version"] != "1.2":
            raise SecurityBlocker("batch request schema version is unsupported")
        findings_value = value["findings"]
        if not isinstance(findings_value, list) or not findings_value:
            raise SecurityBlocker("batch request requires classified findings")
        findings: list[BatchFinding] = []
        for item in findings_value:
            expected_finding_keys = {
                "finding_id",
                "thread_id",
                "sources",
                "source_subitem_id",
                "classification",
                "disposition",
                "evidence_digest",
                "test_evidence_digest",
                "commit_sha",
                "canonical_finding_id",
            }
            if not isinstance(item, dict) or set(item) != expected_finding_keys:
                raise SecurityBlocker("batch finding shape is invalid")
            classification = item["classification"]
            disposition = item["disposition"]
            if (
                classification not in CLASSIFICATION_DISPOSITIONS
                or disposition not in CLASSIFICATION_DISPOSITIONS[classification]
            ):
                raise SecurityBlocker(
                    "batch finding classification and disposition are incompatible"
                )
            source_value = item["sources"]
            if not isinstance(source_value, list) or not source_value:
                raise SecurityBlocker("batch finding requires feedback sources")
            sources: list[BatchSource] = []
            for source in source_value:
                if not isinstance(source, dict) or set(source) != {
                    "kind",
                    "node_id",
                    "digest",
                }:
                    raise SecurityBlocker("batch finding feedback source is malformed")
                if source["kind"] not in SOURCE_KINDS:
                    raise SecurityBlocker("batch finding feedback source kind is unsupported")
                sources.append(
                    BatchSource(
                        kind=source["kind"],
                        node_id=_require_string(
                            source["node_id"], "feedback source identity"
                        ),
                        digest=_require_digest(
                            source["digest"], "feedback source digest"
                        ),
                    )
                )
            source_ids = [(source.kind, source.node_id) for source in sources]
            if len(source_ids) != len(set(source_ids)):
                raise SecurityBlocker("batch finding repeats a feedback source")
            thread_id = item["thread_id"]
            if thread_id is not None:
                thread_id = _require_string(
                    thread_id, "finding thread identity"
                )
            if any(source.kind in THREAD_SOURCE_KINDS for source in sources) != (
                thread_id is not None
            ):
                raise SecurityBlocker(
                    "thread feedback sources and finding thread identity are inconsistent"
                )
            source_subitem_id = item["source_subitem_id"]
            if source_subitem_id is not None:
                source_subitem_id = _require_string(
                    source_subitem_id, "source sub-item identity"
                )
            test_evidence_digest = item["test_evidence_digest"]
            commit_sha = item["commit_sha"]
            if test_evidence_digest is not None:
                test_evidence_digest = _require_digest(
                    test_evidence_digest, "test evidence digest"
                )
            if commit_sha is not None:
                commit_sha = _require_oid(commit_sha, "finding commit")
            if disposition in FIXED_DISPOSITIONS and (
                test_evidence_digest is None or commit_sha is None
            ):
                raise SecurityBlocker(
                    "fixed batch findings require test evidence and a commit"
                )
            if disposition not in FIXED_DISPOSITIONS and (
                test_evidence_digest is not None or commit_sha is not None
            ):
                raise SecurityBlocker(
                    "non-fixed batch findings cannot carry fix-only evidence"
                )
            canonical_finding_id = item["canonical_finding_id"]
            if canonical_finding_id is not None:
                canonical_finding_id = _require_string(
                    canonical_finding_id, "canonical finding identity"
                )
            findings.append(
                BatchFinding(
                    finding_id=_require_string(item["finding_id"], "finding identity"),
                    thread_id=thread_id,
                    sources=tuple(sources),
                    source_subitem_id=source_subitem_id,
                    classification=classification,
                    disposition=disposition,
                    evidence_digest=_require_digest(
                        item["evidence_digest"], "finding evidence digest"
                    ),
                    test_evidence_digest=test_evidence_digest,
                    commit_sha=commit_sha,
                    canonical_finding_id=canonical_finding_id,
                )
            )
        finding_ids = [item.finding_id for item in findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise SecurityBlocker("batch finding identities must be unique")
        findings_by_id = {item.finding_id: item for item in findings}
        for finding in findings:
            canonical = finding.canonical_finding_id
            if finding.classification in {"DUPLICATE", "SUPERSEDED"}:
                if (
                    canonical is None
                    or canonical == finding.finding_id
                    or canonical not in findings_by_id
                ):
                    raise SecurityBlocker(
                        "duplicate or superseded finding lacks a canonical finding"
                    )
            elif canonical is not None:
                raise SecurityBlocker(
                    "only duplicate or superseded findings may name a canonical finding"
                )
        for finding in findings:
            visited = {finding.finding_id}
            current = finding
            while current.canonical_finding_id is not None:
                canonical_id = current.canonical_finding_id
                if canonical_id in visited:
                    raise SecurityBlocker("canonical batch findings contain a cycle")
                visited.add(canonical_id)
                current = findings_by_id[canonical_id]
        operations_value = value["operations"]
        if not isinstance(operations_value, list) or not operations_value:
            raise SecurityBlocker("batch request requires at least one operation")
        operations: list[BatchOperation] = []
        for item in operations_value:
            if not isinstance(item, dict) or set(item) != {
                "operation_id",
                "kind",
                "thread_id",
                "finding_ids",
            }:
                raise SecurityBlocker("batch operation shape is invalid")
            if item["kind"] not in SUPPORTED_BATCH_CAPABILITIES:
                raise SecurityBlocker(f"unsupported batch capability: {item['kind']}")
            operation_finding_ids = item["finding_ids"]
            if (
                not isinstance(operation_finding_ids, list)
                or not operation_finding_ids
            ):
                raise SecurityBlocker("batch operation requires classified findings")
            normalized_finding_ids = tuple(
                _require_string(finding_id, "operation finding identity")
                for finding_id in operation_finding_ids
            )
            if len(normalized_finding_ids) != len(set(normalized_finding_ids)):
                raise SecurityBlocker("batch operation repeats a classified finding")
            operations.append(
                BatchOperation(
                    operation_id=_require_string(item["operation_id"], "operation identity"),
                    kind=item["kind"],
                    thread_id=_require_string(item["thread_id"], "thread identity"),
                    finding_ids=normalized_finding_ids,
                )
            )
        operation_ids = [item.operation_id for item in operations]
        thread_ids = [item.thread_id for item in operations]
        if len(operation_ids) != len(set(operation_ids)) or len(thread_ids) != len(set(thread_ids)):
            raise SecurityBlocker("batch operation and thread identities must be unique")
        linked_findings: list[str] = []
        for operation in operations:
            for finding_id in operation.finding_ids:
                finding = findings_by_id.get(finding_id)
                if finding is None or finding.thread_id != operation.thread_id:
                    raise SecurityBlocker(
                        "batch operation does not bind a finding from its thread"
                    )
                linked_findings.append(finding_id)
        threaded_finding_ids = {
            finding.finding_id for finding in findings if finding.thread_id is not None
        }
        if len(linked_findings) != len(set(linked_findings)) or set(
            linked_findings
        ) != threaded_finding_ids:
            raise SecurityBlocker(
                "every threaded finding must belong to exactly one batch operation"
            )
        pull_request_number = value["pull_request_number"]
        if not isinstance(pull_request_number, int) or isinstance(
            pull_request_number, bool
        ) or pull_request_number < 1:
            raise SecurityBlocker("batch pull request identity is invalid")
        repository = _require_string(value["repository"], "repository")
        if not REPOSITORY.fullmatch(repository):
            raise SecurityBlocker("batch repository identity is invalid")
        return cls(
            schema_version="1.2",
            batch_id=_require_string(value["batch_id"], "batch identity"),
            repository=repository,
            pull_request_number=pull_request_number,
            expected_head_sha=_require_oid(value["expected_head_sha"], "expected head"),
            expected_base_ref=_require_string(value["expected_base_ref"], "expected base"),
            expected_base_sha=_require_oid(value["expected_base_sha"], "expected base SHA"),
            expected_actor=_actor(value["expected_actor"], "expected writer"),
            reviewed_state_digest=_require_digest(
                value["reviewed_state_digest"], "reviewed state digest"
            ),
            reviewed_feedback_digest=_require_digest(
                value["reviewed_feedback_digest"], "reviewed feedback digest"
            ),
            findings=findings,
            operations=operations,
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
                "expected_base_ref": self.expected_base_ref,
                "expected_base_sha": self.expected_base_sha,
                "expected_actor": self.expected_actor,
                "reviewed_state_digest": self.reviewed_state_digest,
                "reviewed_feedback_digest": self.reviewed_feedback_digest,
                "findings": [_batch_finding_dict(item) for item in self.findings],
                "operations": [
                    {
                        "operation_id": item.operation_id,
                        "kind": item.kind,
                        "thread_id": item.thread_id,
                        "finding_ids": list(item.finding_ids),
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
            "expected_base_ref": self.expected_base_ref,
            "expected_base_sha": self.expected_base_sha,
            "expected_actor": copy.deepcopy(self.expected_actor),
            "reviewed_state_digest": self.reviewed_state_digest,
            "reviewed_feedback_digest": self.reviewed_feedback_digest,
            "findings": [_batch_finding_dict(item) for item in self.findings],
            "operations": [
                {
                    "operation_id": item.operation_id,
                    "kind": item.kind,
                    "thread_id": item.thread_id,
                    "finding_ids": list(item.finding_ids),
                }
                for item in self.operations
            ],
        }


def validate_manual_gate_evidence(
    value: Any,
    registered_gates: Any,
) -> list[dict[str, Any]]:
    if not isinstance(registered_gates, list) or any(
        not isinstance(gate, str) or not gate for gate in registered_gates
    ):
        raise SecurityBlocker("registered manual gates are malformed")
    if not isinstance(value, list) or len(value) != len(registered_gates):
        raise SecurityBlocker("manual-gate evidence is incomplete")
    normalized: list[dict[str, Any]] = []
    for index, gate in enumerate(registered_gates):
        item = value[index]
        if not isinstance(item, dict) or set(item) != {
            "gate",
            "satisfied",
            "evidence",
        }:
            raise SecurityBlocker("manual-gate evidence shape is invalid")
        evidence_text = item.get("evidence")
        if (
            item.get("gate") != gate
            or item.get("satisfied") is not True
            or not isinstance(evidence_text, str)
            or not EVIDENCE_TEXT.fullmatch(evidence_text)
        ):
            raise SecurityBlocker("manual-gate evidence is not satisfied")
        if SECRET_VALUE.search(evidence_text):
            raise SecurityBlocker("manual-gate evidence contains a secret-like value")
        normalized.append(
            {"gate": gate, "satisfied": True, "evidence": evidence_text}
        )
    return normalized


def create_validation_receipt(
    *,
    repository: str,
    head_sha: str,
    validated_tree_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    successful_result: bool,
    reviewed_state: StableFeedbackState,
    manual_gate_evidence: Any,
) -> dict[str, Any]:
    gates = registry.get("manual_gates") if isinstance(registry, dict) else None
    normalized_gates = validate_manual_gate_evidence(manual_gate_evidence, gates)
    fields = {
        "schema_version": "1.0",
        "kind": "VALIDATION_RECEIPT",
        "repository": _require_string(repository, "receipt repository"),
        "head_sha": _require_oid(head_sha, "receipt head"),
        "validated_tree_sha": _require_oid(
            validated_tree_sha, "validated tree"
        ),
        "registry_digest": digest_json(registry),
        "command_set_digest": digest_json(command_set),
        "successful_result": successful_result is True,
        "reviewed_state_digest": reviewed_state.state_digest,
        "reviewed_feedback_digest": reviewed_state.feedback_digest,
        "manual_gate_evidence": normalized_gates,
    }
    return {**fields, "receipt_digest": digest_json(fields)}


def create_validation_attestation(
    *,
    repository: str,
    head_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    successful_result: bool,
    reviewed_state: StableFeedbackState,
    validation_receipt: Any,
) -> dict[str, Any]:
    if not isinstance(validation_receipt, dict):
        raise SecurityBlocker("validation receipt is missing")
    expected_receipt = create_validation_receipt(
        repository=repository,
        head_sha=reviewed_state.head_sha,
        validated_tree_sha=validation_receipt.get("validated_tree_sha"),
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed_state,
        manual_gate_evidence=validation_receipt.get("manual_gate_evidence"),
    )
    if validation_receipt != expected_receipt:
        raise SecurityBlocker("validation receipt is invalid or stale")
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
        "validated_tree_sha": validation_receipt["validated_tree_sha"],
        "validation_receipt_digest": validation_receipt["receipt_digest"],
        "manual_gate_evidence": copy.deepcopy(
            validation_receipt["manual_gate_evidence"]
        ),
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
    commit_parent_sha: str,
    commit_tree_sha: str,
    commit_validation_receipt_digest: str | None,
) -> None:
    if (
        _require_oid(commit_parent_sha, "validated commit parent")
        != reviewed_state.head_sha
    ):
        raise SecurityBlocker("validated commit parent does not match reviewed head")
    if not isinstance(attestation, dict):
        raise SecurityBlocker("validation attestation is missing")
    receipt = create_validation_receipt(
        repository=repository,
        head_sha=reviewed_state.head_sha,
        validated_tree_sha=commit_tree_sha,
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed_state,
        manual_gate_evidence=attestation.get("manual_gate_evidence"),
    )
    if (
        commit_validation_receipt_digest != receipt["receipt_digest"]
        or attestation.get("validation_receipt_digest") != receipt["receipt_digest"]
    ):
        raise SecurityBlocker(
            "signed commit does not bind the validation receipt"
        )
    expected = create_validation_attestation(
        repository=repository,
        head_sha=head_sha,
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed_state,
        validation_receipt=receipt,
    )
    if not isinstance(attestation, dict) or attestation != expected:
        raise SecurityBlocker("validation attestation binding is invalid or stale")
    if attestation["successful_result"] is not True:
        raise SecurityBlocker("complete validation did not succeed")


def verify_commit_signatures(
    commits: Any,
    signature_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(commits, list) or not commits:
        raise SecurityBlocker("commit signature evidence is missing")
    policy = signature_policy or {"accepted_formats": ["ssh", "openpgp"]}
    accepted_formats = policy.get("accepted_formats") if isinstance(policy, dict) else None
    if (
        not isinstance(accepted_formats, list)
        or not accepted_formats
        or any(item not in {"ssh", "openpgp"} for item in accepted_formats)
    ):
        raise SecurityBlocker("configured signature formats are missing or unsafe")
    accepted = frozenset(accepted_formats)
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
                and local.get("format") in accepted
            ):
                raise SecurityBlocker(f"invalid or unsigned user-authored commit: {oid}")
            signature_format = local["format"]
            verified.append(
                {
                    "oid": oid,
                    "classification": f"LOCAL_{signature_format.upper()}_VERIFIED",
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


def _classified_feedback_sources(
    reviewed_state: StableFeedbackState,
) -> dict[tuple[str, str], tuple[str, str | None]]:
    expected: dict[tuple[str, str], tuple[str, str | None]] = {}

    def add(kind: str, node_id: str, source_digest: str, thread_id: str | None) -> None:
        key = (kind, node_id)
        if key in expected:
            raise SecurityBlocker("stable feedback repeats a classification source")
        expected[key] = (source_digest, thread_id)

    for reaction in reviewed_state.feedback["pull_request_reactions"]:
        add(
            "PULL_REQUEST_REACTION",
            reaction["mutation_id"],
            digest_json(reaction),
            None,
        )
    for review in reviewed_state.feedback["reviews"]:
        add("REVIEW", review["node_id"], review["body_digest"], None)
        for reaction in review["reactions"]:
            add(
                "REVIEW_REACTION",
                reaction["mutation_id"],
                digest_json(reaction),
                None,
            )
    for comment in reviewed_state.feedback["conversation_comments"]:
        add(
            "CONVERSATION_COMMENT",
            comment["node_id"],
            comment["body_digest"],
            None,
        )
        for reaction in comment["reactions"]:
            add(
                "CONVERSATION_REACTION",
                reaction["mutation_id"],
                digest_json(reaction),
                None,
            )
    for thread in reviewed_state.feedback["threads"]:
        if thread["is_resolved"] is True:
            continue
        for comment in thread["comments"]:
            add(
                "THREAD_COMMENT",
                comment["node_id"],
                comment["body_digest"],
                thread["node_id"],
            )
            for reaction in comment["reactions"]:
                add(
                    "THREAD_COMMENT_REACTION",
                    reaction["mutation_id"],
                    digest_json(reaction),
                    thread["node_id"],
                )
    return expected


def _verify_classified_findings(
    request: BatchRequest,
    reviewed_state: StableFeedbackState,
    registry: dict[str, Any],
) -> None:
    limits = registry.get("limits") if isinstance(registry, dict) else None
    maximum_items = limits.get("maximum_items") if isinstance(limits, dict) else None
    if not isinstance(maximum_items, int) or maximum_items < 1:
        raise SecurityBlocker("batch item limit is missing")
    source_count = sum(len(finding.sources) for finding in request.findings)
    if len(request.findings) + len(request.operations) + source_count > maximum_items:
        raise SecurityBlocker("classified batch exceeds the registered item limit")
    unresolved_threads = {
        item["node_id"]: item
        for item in reviewed_state.feedback["threads"]
        if item["is_resolved"] is False
    }
    operation_threads = {item.thread_id for item in request.operations}
    if operation_threads != set(unresolved_threads):
        raise SecurityBlocker(
            "batch operations must cover every unresolved reviewed thread"
        )
    expected_sources = _classified_feedback_sources(reviewed_state)
    classified_sources: dict[tuple[str, str], list[str | None]] = {}
    for finding in request.findings:
        if finding.thread_id is not None and finding.thread_id not in unresolved_threads:
            raise SecurityBlocker(
                "classified finding does not belong to an unresolved reviewed thread"
            )
        for source in finding.sources:
            key = (source.kind, source.node_id)
            expected = expected_sources.get(key)
            if expected != (source.digest, finding.thread_id):
                raise SecurityBlocker(
                    "classified finding source does not match reviewed feedback"
                )
            classified_sources.setdefault(key, []).append(
                finding.source_subitem_id
            )
    if set(classified_sources) != set(expected_sources):
        raise SecurityBlocker(
            "classified finding coverage is incomplete for stable feedback"
        )
    for subitem_ids in classified_sources.values():
        if len(subitem_ids) > 1 and (
            any(item is None for item in subitem_ids)
            or len(subitem_ids) != len(set(subitem_ids))
        ):
            raise SecurityBlocker(
                "compound source findings require unique sub-item identities"
            )


def _verify_finding_commits(
    request: BatchRequest,
    readiness: ReadinessState,
) -> None:
    commit_oids = {
        item.get("oid") for item in readiness.commits if isinstance(item, dict)
    }
    for finding in request.findings:
        if (
            finding.disposition == "CORRECTED_AND_VERIFIED"
            and finding.commit_sha != request.expected_head_sha
        ):
            raise SecurityBlocker(
                "corrected batch finding does not bind the remediation head"
            )
        if (
            finding.disposition in FIXED_DISPOSITIONS
            and finding.commit_sha not in commit_oids
        ):
            raise SecurityBlocker(
                "fixed batch finding commit is not present in the reviewed PR"
            )


def _verify_finding_test_evidence(
    request: BatchRequest,
    attestation: dict[str, Any],
) -> None:
    receipt_digest = attestation.get("validation_receipt_digest")
    if not isinstance(receipt_digest, str) or not DIGEST.fullmatch(receipt_digest):
        raise SecurityBlocker("validation receipt evidence is missing")
    for finding in request.findings:
        if (
            finding.disposition in FIXED_DISPOSITIONS
            and finding.test_evidence_digest != receipt_digest
        ):
            raise SecurityBlocker(
                "fixed finding test evidence does not bind the validation receipt"
            )


def _verify_readiness(
    request: BatchRequest,
    readiness: ReadinessState,
    registry: dict[str, Any],
) -> None:
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
    if readiness.base_ref != request.expected_base_ref:
        raise SecurityBlocker("pull request base branch changed after review")
    if _require_oid(readiness.base_sha, "base SHA") != request.expected_base_sha:
        raise SecurityBlocker("pull request base SHA changed after review")
    default_branch = registry.get("default_branch")
    allowed_base_repositories = registry.get("allowed_base_repositories")
    if not isinstance(default_branch, str) or not default_branch:
        raise SecurityBlocker("registered default branch is missing")
    if request.expected_base_ref != default_branch:
        raise SecurityBlocker("pull request does not target the registered default branch")
    if (
        not isinstance(allowed_base_repositories, list)
        or readiness.base_repository not in allowed_base_repositories
    ):
        raise SecurityBlocker("pull request base repository is outside the registered boundary")
    if readiness.mergeability != "MERGEABLE":
        raise SecurityBlocker(f"pull request mergeability is {readiness.mergeability or 'missing'}")
    merge_disposition = RESOLUTION_MERGE_STATE_POLICY.get(
        readiness.merge_state_status
    )
    if merge_disposition is None or merge_disposition == "block":
        raise SecurityBlocker(
            "pull request merge state is "
            f"{readiness.merge_state_status or 'missing'}"
        )
    if _actor(readiness.actor, "current writer") != request.expected_actor:
        raise SecurityBlocker("authenticated actor identity mismatch")
    verify_commit_signatures(readiness.commits, registry.get("signature_policy"))


def _verify_strict_merge_state(
    readiness: ReadinessState,
    check_evidence: dict[str, Any],
) -> None:
    strict_base_required = check_evidence.get("strict_base_required")
    if not isinstance(strict_base_required, bool):
        raise SecurityBlocker("strict required-check evidence is missing")
    if readiness.merge_state_status == "BEHIND" and strict_base_required:
        raise SecurityBlocker(
            "pull request is behind the base required by strict checks"
        )


def _verify_required_checks(
    checks: Any,
    required_specs: Any,
    policy: Any,
) -> None:
    if not isinstance(checks, list):
        raise SecurityBlocker("required check evidence is malformed")
    if not isinstance(required_specs, list):
        raise SecurityBlocker("configured required check evidence is missing")
    if not required_specs:
        return
    if not checks:
        raise SecurityBlocker("required check evidence is missing")
    skipped_policy = policy.get("expected_skipped") if isinstance(policy, dict) else None
    if skipped_policy not in {"allow", "block"}:
        raise SecurityBlocker("required check skipped policy is invalid")

    for spec in required_specs:
        if not isinstance(spec, dict):
            raise SecurityBlocker("configured required check identity is malformed")
        name = spec.get("context")
        integration_id = spec.get("integration_id")
        if not isinstance(name, str) or not name:
            raise SecurityBlocker("configured required check identity is malformed")
        matching = [
            item
            for item in checks
            if isinstance(item, dict)
            and item.get("name") == name
            and item.get("is_effective", True) is True
            and (
                integration_id is None
                or item.get("application", {}).get("database_id") == integration_id
            )
        ]
        if not matching:
            raise SecurityBlocker(f"required check {name} is missing")
        for check in matching:
            status = str(check.get("status") or "").upper()
            conclusion = str(check.get("conclusion") or "").upper()
            accepted_conclusion = conclusion in {"SUCCESS", "NEUTRAL"} or (
                conclusion == "SKIPPED" and skipped_policy == "allow"
            )
            stable_id = str(check.get("stable_id") or "")
            successful = (
                status == "COMPLETED" and accepted_conclusion
                if stable_id.startswith("check_run:")
                else accepted_conclusion
            )
            if not successful:
                raise SecurityBlocker(
                    f"required check {name} is {conclusion or status or 'missing'}"
                )


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


def _compare_feedback(
    request: BatchRequest,
    reviewed: StableFeedbackState,
    current: StableFeedbackState,
) -> None:
    if (
        current.repository != request.repository
        or current.pull_request_number != request.pull_request_number
        or current.pr_state != "OPEN"
        or current.head_sha != request.expected_head_sha
        or current.base_ref != request.expected_base_ref
        or current.base_sha != request.expected_base_sha
    ):
        raise SecurityBlocker(
            "stable feedback repository, PR, state, head, or base changed"
        )
    if current.feedback_digest == reviewed.feedback_digest:
        return
    normalized = copy.deepcopy(current.feedback)
    reviewed_threads = {item["node_id"]: item for item in reviewed.feedback["threads"]}
    for thread in normalized["threads"]:
        expected = reviewed_threads.get(thread["node_id"])
        if (
            request.expected_head_sha != reviewed.head_sha
            and expected is not None
            and expected["is_outdated"] is False
            and thread["is_outdated"] is True
        ):
            thread["is_outdated"] = False
    if digest_json(normalized) != reviewed.feedback_digest:
        raise SecurityBlocker("stable feedback changed after review")


def _base_report(request: BatchRequest) -> dict[str, Any]:
    return {
        "status": "BATCH_PENDING",
        "batch_id": request.batch_id,
        "authorization_digest": request.authorization_digest,
        "applied": [],
        "blocked": [],
        "failed": [],
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
    if reviewed_state.pr_state != "OPEN":
        raise SecurityBlocker("reviewed pull request state is not open")
    if request.reviewed_state_digest != reviewed_state.state_digest or request.reviewed_feedback_digest != reviewed_state.feedback_digest:
        raise SecurityBlocker("batch request does not bind the supplied reviewed feedback")
    if (
        request.expected_base_ref != reviewed_state.base_ref
        or request.expected_base_sha != reviewed_state.base_sha
    ):
        raise SecurityBlocker("batch request does not bind the reviewed base")
    default_branch = registry.get("default_branch") if isinstance(registry, dict) else None
    if request.expected_base_ref != default_branch:
        raise SecurityBlocker("reviewed pull request does not target the registered default branch")
    _verify_classified_findings(request, reviewed_state, registry)
    check_policy = registry.get("check_policy") if isinstance(registry, dict) else None
    readiness = _read_with_one_retry(lambda: gateway.read_preflight(request))
    _verify_readiness(request, readiness, registry)
    _verify_finding_commits(request, readiness)
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
        commit_parent_sha=readiness.head_parent_sha,
        commit_tree_sha=readiness.head_tree_sha,
        commit_validation_receipt_digest=readiness.validation_receipt_digest,
    )
    _verify_finding_test_evidence(request, attestation)
    check_evidence = _read_with_one_retry(
        lambda: gateway.read_required_checks(request, registry)
    )
    if not isinstance(check_evidence, dict):
        raise SecurityBlocker("required check evidence is malformed")
    _verify_required_checks(
        check_evidence.get("checks"),
        check_evidence.get("required_specs"),
        check_policy,
    )
    _verify_strict_merge_state(readiness, check_evidence)
    current = _read_with_one_retry(lambda: gateway.read_stable_feedback(request))
    _compare_feedback(request, reviewed_state, current)

    current_threads = {item["node_id"]: item for item in current.feedback["threads"]}
    for operation in request.operations:
        thread = current_threads.get(operation.thread_id)
        if thread is None:
            raise SecurityBlocker(f"requested thread is missing: {operation.thread_id}")
        if thread["is_resolved"]:
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
        observed_thread = target.get("thread") if isinstance(target, dict) else None
        expected_thread = current_threads.get(operation.thread_id)
        if not isinstance(target, dict) or target.get("thread_id") != operation.thread_id:
            blocker = "last-moment mutation target identity changed"
        elif target.get("head_sha") != request.expected_head_sha:
            blocker = "last-moment mutation target head changed"
        elif target.get("pr_state") != "OPEN":
            blocker = "last-moment pull request state changed"
        elif (
            target.get("base_ref") != request.expected_base_ref
            or target.get("base_sha") != request.expected_base_sha
        ):
            blocker = "last-moment pull request base changed"
        elif target.get("mergeability") != "MERGEABLE":
            blocker = "last-moment pull request mergeability changed"
        elif target.get("merge_state_status") != readiness.merge_state_status:
            blocker = "last-moment pull request merge state changed"
        elif RESOLUTION_MERGE_STATE_POLICY.get(
            target.get("merge_state_status")
        ) in {
            None,
            "block",
        }:
            blocker = "last-moment pull request merge state changed"
        elif (
            target.get("merge_state_status") == "BEHIND"
            and check_evidence["strict_base_required"] is True
        ):
            blocker = "last-moment pull request is behind the strict base"
        elif not isinstance(observed_thread, dict) or expected_thread is None:
            blocker = "last-moment mutation target feedback is incomplete"
        else:
            try:
                normalized_thread = _feedback_projection(
                    {"threads": [observed_thread]}
                )["threads"][0]
            except SecurityBlocker:
                blocker = "last-moment mutation target feedback is incomplete"
            else:
                comparable_thread = copy.deepcopy(normalized_thread)
                if (
                    request.expected_head_sha != reviewed_state.head_sha
                    and comparable_thread["is_outdated"] is True
                    and expected_thread["is_outdated"] is False
                ):
                    comparable_thread["is_outdated"] = False
                blocker = (
                    None
                    if comparable_thread == expected_thread
                    else "last-moment mutation target feedback changed"
                )
        if blocker is None and target.get("is_resolved") is not False:
            blocker = "last-moment mutation target state changed"
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

    report["status"] = "BATCH_APPLIED"
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
