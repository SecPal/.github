# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed evidence for one authenticated pre-enrollment Draft integration.

This module owns the authority boundary that is deliberately absent from the
Ready lifecycle.  Git mechanics stay shared with the maintained review action;
this module closes and authenticates their inputs and outputs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import stat
import re
from typing import Any, Callable, Mapping, NamedTuple

from .fast_path import canonical_json_bytes, digest_json


SCHEMA_VERSION = "1.1"
HISTORICAL_SCHEMA_VERSION = "1.0"
KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION"
DOMAIN = "secpal.pre-enrollment-draft-integration/v1.1"
AUTHORIZATION_KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION_AUTHORIZATION"
AUTHORIZATION_DOMAIN = "secpal.pre-enrollment-draft-integration-authorization/v1.1"
RECEIPT_KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION_VALIDATION_RECEIPT"
RECEIPT_DOMAIN = "secpal.pre-enrollment-draft-integration-validation-receipt/v1.1"
ATTESTATION_KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION_FINAL_ATTESTATION"
ATTESTATION_DOMAIN = "secpal.pre-enrollment-draft-integration-final-attestation/v1.1"
INITIAL_HEAD_PROOF_KIND = "AUTHENTICATED_PRE_ENROLLMENT_DRAFT_INTEGRATION_HEAD"

_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_HISTORICAL_IDENTITY = re.compile(r"[^\x00-\x20\x7f]+")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,254}")
_PATH = re.compile(r"[^\x00-\x1f\x7f]+")

# Derived closed-schema envelopes, including UTF-8 JSON escaping and final LF.
# IDs reuse the lifecycle identity grammar; paths/counts reuse the maintained
# 1024-byte/32-path correction profile. Signatures use the lifecycle 16-KiB cap.
ARTIFACT_BYTE_LIMITS = {
    "authorization": 99948,
    "integration": 240076,
    "receipt": 1141,
    "attestation": 140731,
}
BRIDGE_ARTIFACT_BYTES = 381948
ARTIFACT_FILES = {
    "integration": "integration-evidence.json",
    "receipt": "validation-receipt.json",
    "attestation": "final-attestation.json",
}


class PreEnrollmentIntegrationError(ValueError):
    """The requested integration is stale, ambiguous, or unauthorized."""


def require_current_policy(binding: Mapping[str, Any]) -> None:
    policy = binding.get("pre_enrollment_integration_policy")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "command": "integrate-pre-enrollment-draft",
        "topology_kind": KIND,
        "allowed_mutation": "NON_FORCE_PUSH_EXACT_PR_BRANCH",
        "maximum_candidates": 1, "maximum_pushes": 1,
        "force_push": False, "automatic_retry": False, "merge_pull_request": False,
    }
    if (binding.get("repository") != "SecPal/.github"
            or binding.get("default_branch") != "main"
            or not isinstance(policy, dict)
            or set(policy) != set(expected) | {"historical_sources"}
            or any(policy[key] != value for key, value in expected.items())
            or not isinstance(policy["historical_sources"], list)):
        raise PreEnrollmentIntegrationError("EVIDENCE_TIME_POLICY_REJECTED")


def _domain(current: str, legacy: bool) -> str:
    return current.removesuffix(".1") if legacy else current


def _bounded_text(value: Any, maximum: int) -> None:
    if not isinstance(value, str) or len(value) > maximum:
        raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED") from exc
    if size > maximum:
        raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")


def _bounded_result(value: dict[str, Any], kind: str) -> dict[str, Any]:
    if len(canonical_json_bytes(value)) > ARTIFACT_BYTE_LIMITS[kind]:
        raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
    return value


def _check_json_depth(raw: bytes, maximum: int) -> None:
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > maximum:
                raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
        elif char in (93, 125):
            depth -= 1


def loads_artifact(raw: bytes, kind: str) -> dict[str, Any]:
    """Read current finite canonical bytes; this never selects legacy authority."""
    if kind not in ARTIFACT_BYTE_LIMITS or not isinstance(raw, bytes):
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED")
    if len(raw) > ARTIFACT_BYTE_LIMITS[kind]:
        raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
    _check_json_depth(raw, 3 if kind in {"integration", "attestation"} else 2)
    try:
        value = loads_closed_json(raw)
        if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
            raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED") from exc
    if value.get("schema_version") != SCHEMA_VERSION:
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED")
    return value


def read_artifact(path: Path, kind: str) -> dict[str, Any]:
    """Read current producer input with the same bound as its output."""
    if kind not in ARTIFACT_BYTE_LIMITS:
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED")
    return loads_artifact(_read_artifact_file(path, ARTIFACT_BYTE_LIMITS[kind]), kind)


def _read_artifact_file(path: Path, limit: int) -> bytes:
    """Bound the same regular descriptor before/after reading; never follow links."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if (
            identity(before) != identity(after)
            or identity(after) != identity(os.stat(path, follow_symlinks=False))
            or remaining == 0
        ):
            raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _historical_source(policy: Mapping[str, Any], *, repository: str,
                       delivery_issue: int, pull_request: int, head_sha: str) -> dict[str, Any] | None:
    """Select from independently authenticated current policy, never input flags.

    The admitted bridge owns policy authentication before calling this private
    projection. This helper and its caller-held result confer no authority.
    """
    rows = policy.get("historical_sources", [])
    if not isinstance(rows, list):
        raise PreEnrollmentIntegrationError("EVIDENCE_TIME_POLICY_REJECTED")
    matches = [row for row in rows if isinstance(row, dict) and row.get("head_sha") == head_sha]
    if not matches:
        return None
    if len(matches) != 1:
        raise PreEnrollmentIntegrationError("EVIDENCE_TIME_POLICY_REJECTED")
    selected = matches[0]
    if any(selected.get(key) != expected for key, expected in {
        "repository": repository, "delivery_issue": delivery_issue,
        "pull_request": pull_request, "head_sha": head_sha,
    }.items()):
        raise PreEnrollmentIntegrationError("ARTIFACT_BINDING_REJECTED")
    return selected


def _read_bridge_artifacts(directory: Path, historical: Mapping[str, Any] | None) -> dict[str, Any]:
    """Read only the three fixed data files from an outer-controlled directory."""
    if directory.is_symlink() or not directory.is_dir():
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED")
    original_root = directory.stat()
    result = {}
    limits = None if historical is None else historical.get("artifact_sizes")
    if historical is not None and limits is None:
        raise PreEnrollmentIntegrationError("HISTORICAL_EVIDENCE_UNAVAILABLE")
    for kind, filename in ARTIFACT_FILES.items():
        limit = ARTIFACT_BYTE_LIMITS[kind] if limits is None else limits[kind]["wire_bytes"]
        raw = _read_artifact_file(directory / filename, limit)
        if historical is None:
            value = loads_artifact(raw, kind)
        else:
            _check_json_depth(raw, 3 if kind != "receipt" else 2)
            value = loads_closed_json(raw)
            if (
                not isinstance(value, dict)
                or value.get("schema_version") != HISTORICAL_SCHEMA_VERSION
                or len(canonical_json_bytes(value)) != limits[kind]["canonical_bytes"]
            ):
                raise PreEnrollmentIntegrationError("ARTIFACT_BINDING_REJECTED")
        result[kind] = value
    final_root = directory.stat()
    if directory.is_symlink() or (original_root.st_dev, original_root.st_ino) != (final_root.st_dev, final_root.st_ino):
        raise PreEnrollmentIntegrationError("INPUT_SCHEMA_REJECTED")
    if historical is not None:
        _require_historical_artifacts(result, historical)
    return result


def _require_historical_artifacts(artifacts: Mapping[str, Any], historical: Mapping[str, Any]) -> None:
    if (
        digest_json(artifacts["integration"]) != historical["integration_evidence_digest"]
        or artifacts["receipt"].get("receipt_digest") != historical["validation_receipt_digest"]
        or artifacts["attestation"].get("attestation_digest") != historical["final_attestation_digest"]
        or artifacts["attestation"].get("candidate_tree_sha") != historical["tree_sha"]
    ):
        raise PreEnrollmentIntegrationError("ARTIFACT_BINDING_REJECTED")
    # Receipt/attestation digest fields are re-derived by their original verifier,
    # not mistaken for whole-document byte hashes here.


_VERIFIED_HEAD_TOKEN = object()
_VERIFIED_CANDIDATE_TOKEN = object()


def loads_closed_json(raw: bytes | str) -> Any:
    """Load JSON while rejecting duplicate keys and non-finite constants."""

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PreEnrollmentIntegrationError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise PreEnrollmentIntegrationError(f"non-finite JSON value is forbidden: {value}")

    try:
        return json.loads(
            raw, object_pairs_hook=closed_object, parse_constant=reject_constant
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PreEnrollmentIntegrationError(
            "pre-enrollment evidence JSON is malformed"
        ) from exc


@dataclass(frozen=True)
class VerifiedInitialHeadProof:
    """Opaque handoff accepted by lifecycle initialization after full verification."""

    kind: str
    repository: str
    delivery_issue: int
    pull_request: int
    initial_head_sha: str
    validation_receipt_digest: str
    final_attestation_digest: str
    integration_evidence_digest: str
    _verification_token: object = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "repository": self.repository,
            "delivery_issue": self.delivery_issue,
            "pull_request": self.pull_request,
            "initial_head_sha": self.initial_head_sha,
            "validation_receipt_digest": self.validation_receipt_digest,
            "final_attestation_digest": self.final_attestation_digest,
            "integration_evidence_digest": self.integration_evidence_digest,
        }


def is_verified_initial_head_proof(value: Any) -> bool:
    return (
        isinstance(value, VerifiedInitialHeadProof)
        and value._verification_token is _VERIFIED_HEAD_TOKEN
    )


class FrozenObservation(NamedTuple):
    draft_pr: Mapping[str, Any]
    current_main: Mapping[str, Any]
    work_graph: Mapping[str, Any]
    lifecycle_absence: Mapping[str, Any]


@dataclass(frozen=True)
class ExecutionResult:
    """Closed result of the one-shot mutation boundary."""

    candidate_head_sha: str
    validation_receipt: dict[str, Any]
    final_attestation: dict[str, Any]
    initial_head_proof: VerifiedInitialHeadProof


AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version", "kind", "domain", "authorization_id", "repository",
        "delivery_issue", "pull_request", "draft_head_sha", "current_main_sha",
        "expected_signer", "signer_identity", "signature", "authorization_digest",
    }
)


@dataclass(frozen=True)
class VerifiedCandidateCommit:
    """Opaque commit facts emitted only after the maintained Git verifier runs."""

    head_sha: str
    tree_sha: str
    parent_shas: tuple[str, str]
    verified_signer: str
    signature_format: str
    _verification_token: object = field(repr=False, compare=False)


def _seal_verified_candidate_commit(value: Mapping[str, Any]) -> VerifiedCandidateCommit:
    """Seal the closed result of the admitted source's concrete commit verifier."""

    if set(value) != {
        "head_sha", "tree_sha", "parent_shas", "verified_signer", "signature_format"
    }:
        raise PreEnrollmentIntegrationError("verified candidate evidence is ambiguous")
    parents = value["parent_shas"]
    if not isinstance(parents, (list, tuple)) or len(parents) != 2:
        raise PreEnrollmentIntegrationError("verified candidate parent topology is invalid")
    signature_format = value["signature_format"]
    if signature_format not in {"ssh", "openpgp"}:
        raise PreEnrollmentIntegrationError("verified candidate signature is invalid")
    return VerifiedCandidateCommit(
        _oid(value["head_sha"], "verified candidate head"),
        _oid(value["tree_sha"], "verified candidate tree"),
        (_oid(parents[0], "verified candidate parent"), _oid(parents[1], "verified candidate parent")),
        _identity(value["verified_signer"], "verified candidate signer"),
        signature_format,
        _VERIFIED_CANDIDATE_TOKEN,
    )
SIGNATURE_FIELDS = frozenset({"format", "signer_identity", "value"})
EVIDENCE_FIELDS = frozenset(
    {
        "schema_version", "kind", "domain", "repository", "delivery_issue",
        "pull_request", "authorization", "authorization_digest", "draft_pr",
        "current_main", "ordered_parent_shas", "validated_tree_sha",
        "mechanical_merge_tree_sha", "mechanical_conflict_paths",
        "manual_conflict_resolution_delta", "work_graph", "lifecycle_absence",
        "validation_execution", "expected_signer",
    }
)
DELTA_FIELDS = frozenset({"path", "status", "old_mode", "new_mode", "old_oid", "new_oid"})


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise PreEnrollmentIntegrationError(f"{label} schema is not closed")
    return value


def _oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _OID.fullmatch(value):
        raise PreEnrollmentIntegrationError(f"{label} is not a complete object identity")
    return value.lower()


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise PreEnrollmentIntegrationError(f"{label} is not a SHA-256 digest")
    return value


def _positive(value: Any, label: str, *, legacy: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or (not legacy and value > 2147483647):
        raise PreEnrollmentIntegrationError(f"{label} must be a positive integer")
    return value


def _identity(value: Any, label: str, *, legacy: bool = False) -> str:
    if not legacy:
        _bounded_text(value, 255)
    if not isinstance(value, str) or not (_HISTORICAL_IDENTITY if legacy else _IDENTITY).fullmatch(value):
        raise PreEnrollmentIntegrationError(f"{label} is invalid")
    return value


def _repository(value: Any, *, legacy: bool = False) -> str:
    if not isinstance(value, str) or (not legacy and value != "SecPal/.github") or not _REPOSITORY.fullmatch(value):
        raise PreEnrollmentIntegrationError("repository identity is invalid")
    return value


def _signature(value: Any, signer: str, *, legacy: bool = False) -> dict[str, str]:
    item = _closed(value, SIGNATURE_FIELDS, "authorization signature")
    if item["format"] not in {"ssh", "openpgp"}:
        raise PreEnrollmentIntegrationError("authorization signature format is unsupported")
    if item["signer_identity"] != signer or not isinstance(item["value"], str) or not item["value"]:
        raise PreEnrollmentIntegrationError("authorization signature identity is inconsistent")
    if not legacy:
        _bounded_text(item["value"], 16384)
    return copy.deepcopy(item)


def _normalize_authorization(value: Any, *, legacy: bool) -> dict[str, Any]:
    item = _closed(value, AUTHORIZATION_FIELDS, "pre-enrollment authorization")
    if item["schema_version"] != (HISTORICAL_SCHEMA_VERSION if legacy else SCHEMA_VERSION) or item["kind"] != AUTHORIZATION_KIND or item["domain"] != _domain(AUTHORIZATION_DOMAIN, legacy):
        raise PreEnrollmentIntegrationError("pre-enrollment authorization kind is unsupported")
    signer = _identity(item["signer_identity"], "authorization signer", legacy=legacy)
    fields = {
        "schema_version": (HISTORICAL_SCHEMA_VERSION if legacy else SCHEMA_VERSION),
        "kind": AUTHORIZATION_KIND,
        "domain": _domain(AUTHORIZATION_DOMAIN, legacy),
        "authorization_id": _identity(item["authorization_id"], "authorization identity", legacy=legacy),
        "repository": _repository(item["repository"], legacy=legacy),
        "delivery_issue": _positive(item["delivery_issue"], "delivery issue", legacy=legacy),
        "pull_request": _positive(item["pull_request"], "pull request", legacy=legacy),
        "draft_head_sha": _oid(item["draft_head_sha"], "authorized Draft head"),
        "current_main_sha": _oid(item["current_main_sha"], "authorized current main"),
        "expected_signer": _identity(item["expected_signer"], "candidate signer", legacy=legacy),
        "signer_identity": signer,
    }
    signed = {**fields, "signature": _signature(item["signature"], signer, legacy=legacy)}
    if _digest(item["authorization_digest"], "authorization digest") != digest_json(signed):
        raise PreEnrollmentIntegrationError("authorization digest mismatch")
    return {**signed, "authorization_digest": digest_json(signed)}


def create_authorization(
    *, authorization_id: str, repository: str, delivery_issue: int,
    pull_request: int, draft_head_sha: str, current_main_sha: str,
    expected_signer: str, signer_identity: str,
    signer: Callable[[bytes, str], Mapping[str, str]],
) -> dict[str, Any]:
    """Create the exact signed, one-shot selection for this closed operation."""

    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": AUTHORIZATION_KIND,
        "domain": AUTHORIZATION_DOMAIN,
        "authorization_id": _identity(authorization_id, "authorization identity"),
        "repository": _repository(repository),
        "delivery_issue": _positive(delivery_issue, "delivery issue"),
        "pull_request": _positive(pull_request, "pull request"),
        "draft_head_sha": _oid(draft_head_sha, "authorized Draft head"),
        "current_main_sha": _oid(current_main_sha, "authorized current main"),
        "expected_signer": _identity(expected_signer, "candidate signer"),
        "signer_identity": _identity(signer_identity, "authorization signer"),
    }
    signature = _signature(
        dict(signer(canonical_json_bytes(fields), AUTHORIZATION_DOMAIN)),
        fields["signer_identity"],
    )
    signed = {**fields, "signature": signature}
    return _bounded_result({**signed, "authorization_digest": digest_json(signed)}, "authorization")


def _verify_authorization(
    authorization: Mapping[str, Any], *, accepted_signers: frozenset[str],
    verifier: Callable[[bytes, Mapping[str, str], str, str], bool],
    legacy: bool,
) -> dict[str, Any]:
    normalized = _normalize_authorization(authorization, legacy=legacy)
    signer = normalized["signer_identity"]
    if signer not in accepted_signers or not verifier(
        canonical_json_bytes({k: copy.deepcopy(v) for k, v in normalized.items() if k not in {"signature", "authorization_digest"}}),
        normalized["signature"], signer, _domain(AUTHORIZATION_DOMAIN, legacy),
    ):
        raise PreEnrollmentIntegrationError("pre-enrollment authorization signature is not trusted")
    return normalized


def _paths(value: Any, *, legacy: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise PreEnrollmentIntegrationError("conflict paths are malformed")
    if not legacy and len(value) > 32:
        raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
    result = []
    for path in value:
        if not legacy:
            _bounded_text(path, 1024)
        if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or any(p in {"", ".", ".."} for p in path.split("/")) or not _PATH.fullmatch(path):
            raise PreEnrollmentIntegrationError("conflict path is unsafe")
        result.append(path)
    if result != sorted(set(result)):
        raise PreEnrollmentIntegrationError("conflict paths are not canonical")
    return result


def _delta(value: Any, *, legacy: bool = False) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PreEnrollmentIntegrationError("conflict-resolution delta is malformed")
    if not legacy and len(value) > 32:
        raise PreEnrollmentIntegrationError("RESOURCE_CONTRACT_REJECTED")
    result = []
    for raw in value:
        item = _closed(raw, DELTA_FIELDS, "conflict-resolution delta")
        path = _paths([item["path"]], legacy=legacy)[0]
        allowed_modes = {"000000", "100644", "100755", "120000", "160000"}
        if (
            item["status"] not in {"A", "D", "M", "T"}
            or item["old_mode"] not in allowed_modes
            or item["new_mode"] not in allowed_modes
            or (item["status"] == "A" and item["old_mode"] != "000000")
            or (item["status"] == "D" and item["new_mode"] != "000000")
        ):
            raise PreEnrollmentIntegrationError("conflict-resolution status is invalid")
        result.append({**copy.deepcopy(item), "path": path, "old_oid": _oid(item["old_oid"], "old conflict object"), "new_oid": _oid(item["new_oid"], "new conflict object")})
    if [i["path"] for i in result] != sorted({i["path"] for i in result}):
        raise PreEnrollmentIntegrationError("conflict-resolution delta is not canonical")
    return result


def _normalize_evidence(value: Any, *, registry: Mapping[str, Any], legacy: bool) -> dict[str, Any]:
    item = _closed(value, EVIDENCE_FIELDS, "pre-enrollment integration evidence")
    if item["schema_version"] != (HISTORICAL_SCHEMA_VERSION if legacy else SCHEMA_VERSION) or item["kind"] != KIND or item["domain"] != _domain(DOMAIN, legacy):
        raise PreEnrollmentIntegrationError("pre-enrollment topology kind is unsupported")
    if not legacy:
        require_current_policy(registry)
    repository = _repository(item["repository"], legacy=legacy)
    if repository != registry.get("repository"):
        raise PreEnrollmentIntegrationError("repository is not registered")
    issue = _positive(item["delivery_issue"], "delivery issue", legacy=legacy)
    pr = _positive(item["pull_request"], "pull request", legacy=legacy)
    authorization = _normalize_authorization(item["authorization"], legacy=legacy)
    if item["authorization_digest"] != authorization["authorization_digest"] or (authorization["repository"], authorization["delivery_issue"], authorization["pull_request"]) != (repository, issue, pr):
        raise PreEnrollmentIntegrationError("authorization delivery identity changed")
    draft = _closed(item["draft_pr"], frozenset({"state", "draft", "head_sha", "observation_digest"}), "Draft PR identity")
    current = _closed(item["current_main"], frozenset({"ref", "sha", "observation_digest"}), "current-main identity")
    draft_head = _oid(draft["head_sha"], "Draft PR head")
    main_head = _oid(current["sha"], "current-main head")
    if draft["state"] != "OPEN" or draft["draft"] is not True:
        raise PreEnrollmentIntegrationError("delivery PR is not an open Draft")
    if current["ref"] != registry.get("default_branch"):
        raise PreEnrollmentIntegrationError("current-main ref is not the registered default branch")
    parents = item["ordered_parent_shas"]
    if not isinstance(parents, list) or len(parents) != 2 or [_oid(p, "integration parent") for p in parents] != [draft_head, main_head] or draft_head == main_head:
        raise PreEnrollmentIntegrationError("pre-enrollment integration requires exact ordered Draft/current-main parents")
    if authorization["draft_head_sha"] != draft_head or authorization["current_main_sha"] != main_head:
        raise PreEnrollmentIntegrationError("authorization parent identity changed")
    conflicts = _paths(item["mechanical_conflict_paths"], legacy=legacy)
    delta = _delta(item["manual_conflict_resolution_delta"], legacy=legacy)
    if (not conflicts and delta) or (conflicts and [d["path"] for d in delta] != conflicts):
        raise PreEnrollmentIntegrationError("conflict resolution is omitted, extra, or outside the authenticated boundary")
    graph = _closed(item["work_graph"], frozenset({"leaf", "hard_dependencies_satisfied", "ready", "evidence_digest"}), "work-graph evidence")
    if graph["leaf"] is not True or graph["hard_dependencies_satisfied"] is not True or graph["ready"] is not True:
        raise PreEnrollmentIntegrationError("delivery work graph does not permit execution")
    lifecycle = _closed(item["lifecycle_absence"], frozenset({"current_publication", "native_genesis", "lifecycle_aware_head_advancement", "evidence_digest"}), "lifecycle-absence evidence")
    if any(lifecycle[k] is not False for k in ("current_publication", "native_genesis", "lifecycle_aware_head_advancement")):
        raise PreEnrollmentIntegrationError("delivery already requires lifecycle-aware continuation")
    execution = _closed(item["validation_execution"], frozenset({"registry_digest", "command_set_digest"}), "validation execution")
    expected_execution = {"registry_digest": digest_json(registry), "command_set_digest": digest_json(registry.get("validation", []))}
    if execution != expected_execution:
        raise PreEnrollmentIntegrationError("validation command-set identity is stale")
    signer = _identity(item["expected_signer"], "expected candidate signer", legacy=legacy)
    if signer != authorization["expected_signer"]:
        raise PreEnrollmentIntegrationError("candidate signer differs from authorization")
    validated_tree = _oid(item["validated_tree_sha"], "validated tree")
    mechanical_tree = _oid(item["mechanical_merge_tree_sha"], "mechanical merge tree")
    for field, label in ((draft["observation_digest"], "Draft observation"), (current["observation_digest"], "current-main observation"), (graph["evidence_digest"], "work-graph evidence"), (lifecycle["evidence_digest"], "lifecycle-absence evidence")):
        _digest(field, label)
    normalized = copy.deepcopy(item)
    normalized.update(authorization=authorization, draft_pr={**draft, "head_sha": draft_head}, current_main={**current, "sha": main_head}, ordered_parent_shas=[draft_head, main_head], mechanical_conflict_paths=conflicts, manual_conflict_resolution_delta=delta, validated_tree_sha=validated_tree, mechanical_merge_tree_sha=mechanical_tree)
    return normalized


def verify_fresh_state(evidence: Mapping[str, Any], *, live_pr: Mapping[str, Any], live_main: Mapping[str, Any], work_graph: Mapping[str, Any], lifecycle_absence: Mapping[str, Any]) -> None:
    if dict(live_pr) != evidence["draft_pr"]:
        raise PreEnrollmentIntegrationError("Draft PR state or head drifted before write")
    if dict(live_main) != evidence["current_main"]:
        raise PreEnrollmentIntegrationError("registered current main drifted before write")
    if dict(work_graph) != evidence["work_graph"]:
        raise PreEnrollmentIntegrationError("work-graph authority drifted before write")
    if dict(lifecycle_absence) != evidence["lifecycle_absence"]:
        raise PreEnrollmentIntegrationError("lifecycle absence changed before write")


def verify_combined_tree(evidence: Mapping[str, Any], *, mechanical_tree_sha: str, conflict_paths: list[str], observed_delta: list[dict[str, str]], retained_conflict_markers: bool) -> None:
    if _oid(mechanical_tree_sha, "observed mechanical tree") != evidence["mechanical_merge_tree_sha"] or _paths(conflict_paths) != evidence["mechanical_conflict_paths"] or _delta(observed_delta) != evidence["manual_conflict_resolution_delta"]:
        raise PreEnrollmentIntegrationError("combined-tree or conflict evidence mismatch")
    if retained_conflict_markers:
        raise PreEnrollmentIntegrationError("resolved tree retains conflict markers")
    if not conflict_paths and evidence["validated_tree_sha"] != evidence["mechanical_merge_tree_sha"]:
        raise PreEnrollmentIntegrationError("clean merge tree contains a manual delta")


def _reconstruct_receipt(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], successful_result: bool, receipt_id: str, legacy: bool) -> dict[str, Any]:
    _identity(receipt_id, "receipt identity", legacy=legacy)
    normalized = _normalize_evidence(evidence, registry=registry, legacy=legacy)
    fields = {
        "schema_version": (HISTORICAL_SCHEMA_VERSION if legacy else SCHEMA_VERSION), "kind": RECEIPT_KIND, "domain": _domain(RECEIPT_DOMAIN, legacy),
        "receipt_id": _identity(receipt_id, "receipt identity", legacy=legacy), "repository": normalized["repository"],
        "delivery_issue": normalized["delivery_issue"], "pull_request": normalized["pull_request"],
        "ordered_parent_shas": copy.deepcopy(normalized["ordered_parent_shas"]),
        "validated_tree_sha": normalized["validated_tree_sha"], "integration_evidence_digest": digest_json(normalized),
        "registry_digest": digest_json(registry), "command_set_digest": digest_json(registry.get("validation", [])),
        "successful_result": successful_result is True,
    }
    if not fields["successful_result"]:
        raise PreEnrollmentIntegrationError("failed validation cannot produce a receipt")
    return {**fields, "receipt_digest": digest_json(fields)}


def _reconstruct_attestation(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], receipt: Mapping[str, Any], candidate_head_sha: str, candidate_parent_shas: list[str], candidate_tree_sha: str, verified_signer: str, signature_format: str, attestation_id: str, legacy: bool) -> dict[str, Any]:
    _identity(attestation_id, "attestation identity", legacy=legacy)
    normalized = _normalize_evidence(evidence, registry=registry, legacy=legacy)
    expected_receipt = _reconstruct_receipt(evidence=normalized, registry=registry, successful_result=True, receipt_id=receipt.get("receipt_id"), legacy=legacy)
    if dict(receipt) != expected_receipt:
        raise PreEnrollmentIntegrationError("validation receipt is stale or belongs to another candidate")
    if candidate_parent_shas != normalized["ordered_parent_shas"] or _oid(candidate_tree_sha, "candidate tree") != normalized["validated_tree_sha"]:
        raise PreEnrollmentIntegrationError("signed candidate topology differs from validated evidence")
    if verified_signer != normalized["expected_signer"] or signature_format not in {"ssh", "openpgp"}:
        raise PreEnrollmentIntegrationError("candidate is unsigned or signed by the wrong identity")
    fields = {
        "schema_version": (HISTORICAL_SCHEMA_VERSION if legacy else SCHEMA_VERSION), "kind": ATTESTATION_KIND, "domain": _domain(ATTESTATION_DOMAIN, legacy),
        "attestation_id": _identity(attestation_id, "attestation identity", legacy=legacy), "repository": normalized["repository"],
        "delivery_issue": normalized["delivery_issue"], "pull_request": normalized["pull_request"],
        "candidate_head_sha": _oid(candidate_head_sha, "candidate head"), "candidate_tree_sha": normalized["validated_tree_sha"],
        "ordered_parent_shas": copy.deepcopy(normalized["ordered_parent_shas"]), "current_main": copy.deepcopy(normalized["current_main"]),
        "initial_draft_pr": copy.deepcopy(normalized["draft_pr"]), "conflict_paths": copy.deepcopy(normalized["mechanical_conflict_paths"]),
        "conflict_resolution_delta": copy.deepcopy(normalized["manual_conflict_resolution_delta"]), "expected_signer": normalized["expected_signer"],
        "verified_signature": {"format": signature_format, "signer_identity": verified_signer, "valid": True},
        "authorization_digest": normalized["authorization_digest"], "integration_evidence_digest": digest_json(normalized),
        "validation_receipt_digest": receipt["receipt_digest"], "receipt_id": receipt["receipt_id"],
    }
    return {**fields, "attestation_digest": digest_json(fields)}


def _verify_final_attestation(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], receipt: Mapping[str, Any], attestation: Mapping[str, Any], commit_trailers: Mapping[str, str], verified_candidate: VerifiedCandidateCommit, legacy: bool) -> VerifiedInitialHeadProof:
    if (
        not isinstance(verified_candidate, VerifiedCandidateCommit)
        or verified_candidate._verification_token is not _VERIFIED_CANDIDATE_TOKEN
    ):
        raise PreEnrollmentIntegrationError(
            "initial-head proof requires independently verified commit evidence"
        )
    expected = _reconstruct_attestation(
        legacy=legacy,
        evidence=evidence, registry=registry, receipt=receipt,
        candidate_head_sha=verified_candidate.head_sha,
        candidate_parent_shas=list(verified_candidate.parent_shas),
        candidate_tree_sha=verified_candidate.tree_sha,
        verified_signer=verified_candidate.verified_signer,
        signature_format=verified_candidate.signature_format,
        attestation_id=attestation.get("attestation_id"),
    )
    if dict(attestation) != expected:
        raise PreEnrollmentIntegrationError("final attestation is stale, replayed, or ambiguous")
    if dict(commit_trailers) != {"SecPal-Pre-Enrollment-Integration": expected["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": expected["validation_receipt_digest"]}:
        raise PreEnrollmentIntegrationError("signed candidate trailers do not bind typed evidence")
    return VerifiedInitialHeadProof(INITIAL_HEAD_PROOF_KIND, expected["repository"], expected["delivery_issue"], expected["pull_request"], expected["candidate_head_sha"], expected["validation_receipt_digest"], expected["attestation_digest"], expected["integration_evidence_digest"], _VERIFIED_HEAD_TOKEN)


def normalize_authorization(value: Any) -> dict[str, Any]:
    return _bounded_result(_normalize_authorization(value, legacy=False), "authorization")


def normalize_evidence(value: Any, *, registry: Mapping[str, Any]) -> dict[str, Any]:
    return _bounded_result(_normalize_evidence(value, registry=registry, legacy=False), "integration")


def verify_authorization(authorization: Mapping[str, Any], *, accepted_signers: frozenset[str], verifier: Callable[[bytes, Mapping[str, str], str, str], bool]) -> dict[str, Any]:
    return _verify_authorization(authorization, accepted_signers=accepted_signers, verifier=verifier, legacy=False)


def create_validation_receipt(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], successful_result: bool, receipt_id: str) -> dict[str, Any]:
    return _bounded_result(_reconstruct_receipt(evidence=evidence, registry=registry, successful_result=successful_result, receipt_id=receipt_id, legacy=False), "receipt")


def create_final_attestation(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], receipt: Mapping[str, Any], candidate_head_sha: str, candidate_parent_shas: list[str], candidate_tree_sha: str, verified_signer: str, signature_format: str, attestation_id: str) -> dict[str, Any]:
    return _bounded_result(_reconstruct_attestation(evidence=evidence, registry=registry, receipt=receipt, candidate_head_sha=candidate_head_sha, candidate_parent_shas=candidate_parent_shas, candidate_tree_sha=candidate_tree_sha, verified_signer=verified_signer, signature_format=signature_format, attestation_id=attestation_id, legacy=False), "attestation")


def verify_final_attestation(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], receipt: Mapping[str, Any], attestation: Mapping[str, Any], commit_trailers: Mapping[str, str], verified_candidate: VerifiedCandidateCommit) -> VerifiedInitialHeadProof:
    return _verify_final_attestation(evidence=evidence, registry=registry, receipt=receipt, attestation=attestation, commit_trailers=commit_trailers, verified_candidate=verified_candidate, legacy=False)


def execute_once(
    *, evidence: Mapping[str, Any], registry: Mapping[str, Any],
    accepted_authorization_signers: frozenset[str],
    authorization_verifier: Callable[[bytes, Mapping[str, str], str, str], bool],
    derive_tree: Callable[[list[str], str], tuple[str, list[str], list[dict[str, str]], bool]],
    run_registered_validation: Callable[[str], bool],
    observe_frozen_state: Callable[[], FrozenObservation],
    create_signed_candidate: Callable[[str, list[str], Mapping[str, str], str], Mapping[str, Any]],
    persist_candidate_evidence: Callable[[Mapping[str, Any], Mapping[str, Any]], None],
    push_fast_forward: Callable[[str, str], bool],
    observe_final_pr_head: Callable[[], str],
    receipt_id: str, attestation_id: str,
) -> ExecutionResult:
    """Execute at most one candidate and push, with no retry or merge side effect.

    Concrete Git/GitHub adapters remain outside this authority function.  The
    function's closed callback surface is intentionally narrower than a generic
    Git transaction or push API.
    """

    normalized = normalize_evidence(evidence, registry=registry)
    verify_authorization(
        normalized["authorization"],
        accepted_signers=accepted_authorization_signers,
        verifier=authorization_verifier,
    )
    mechanical_tree, conflict_paths, delta, markers = derive_tree(
        normalized["ordered_parent_shas"], normalized["validated_tree_sha"]
    )
    verify_combined_tree(
        normalized,
        mechanical_tree_sha=mechanical_tree,
        conflict_paths=conflict_paths,
        observed_delta=delta,
        retained_conflict_markers=markers,
    )
    if not run_registered_validation(normalized["validated_tree_sha"]):
        raise PreEnrollmentIntegrationError("complete registered validation failed")

    # This is the sole final current-state observation.  Any drift stops the
    # invocation; no candidate exists yet and no automatic retry is permitted.
    observed = observe_frozen_state()
    verify_fresh_state(
        normalized,
        live_pr=observed.draft_pr,
        live_main=observed.current_main,
        work_graph=observed.work_graph,
        lifecycle_absence=observed.lifecycle_absence,
    )
    receipt = create_validation_receipt(
        evidence=normalized,
        registry=registry,
        successful_result=True,
        receipt_id=receipt_id,
    )
    trailers = {
        "SecPal-Pre-Enrollment-Integration": digest_json(normalized),
        "SecPal-Pre-Enrollment-Validation-Receipt": receipt["receipt_digest"],
    }
    candidate = dict(
        create_signed_candidate(
            normalized["validated_tree_sha"],
            normalized["ordered_parent_shas"],
            trailers,
            normalized["expected_signer"],
        )
    )
    required_candidate_fields = {
        "head_sha", "tree_sha", "parent_shas", "verified_signer", "signature_format"
    }
    if set(candidate) != required_candidate_fields:
        raise PreEnrollmentIntegrationError("signed candidate evidence is ambiguous")
    attestation = create_final_attestation(
        evidence=normalized,
        registry=registry,
        receipt=receipt,
        candidate_head_sha=candidate["head_sha"],
        candidate_parent_shas=candidate["parent_shas"],
        candidate_tree_sha=candidate["tree_sha"],
        verified_signer=candidate["verified_signer"],
        signature_format=candidate["signature_format"],
        attestation_id=attestation_id,
    )
    verified_candidate = _seal_verified_candidate_commit(candidate)
    proof = verify_final_attestation(
        evidence=normalized,
        registry=registry,
        receipt=receipt,
        attestation=attestation,
        commit_trailers=trailers,
        verified_candidate=verified_candidate,
    )
    persist_candidate_evidence(receipt, attestation)
    if not push_fast_forward(proof.initial_head_sha, normalized["draft_pr"]["head_sha"]):
        raise PreEnrollmentIntegrationError(
            "authorized non-force push failed or has an unknown result"
        )
    if _oid(observe_final_pr_head(), "final PR head") != proof.initial_head_sha:
        raise PreEnrollmentIntegrationError("final PR head equality was not proven")
    return ExecutionResult(proof.initial_head_sha, receipt, attestation, proof)
