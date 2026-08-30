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
import re
from typing import Any, Callable, Mapping, NamedTuple

from .fast_path import canonical_json_bytes, digest_json


SCHEMA_VERSION = "1.0"
KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION"
DOMAIN = "secpal.pre-enrollment-draft-integration/v1"
AUTHORIZATION_KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION_AUTHORIZATION"
AUTHORIZATION_DOMAIN = "secpal.pre-enrollment-draft-integration-authorization/v1"
RECEIPT_KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION_VALIDATION_RECEIPT"
RECEIPT_DOMAIN = "secpal.pre-enrollment-draft-integration-validation-receipt/v1"
ATTESTATION_KIND = "PRE_ENROLLMENT_DRAFT_INTEGRATION_FINAL_ATTESTATION"
ATTESTATION_DOMAIN = "secpal.pre-enrollment-draft-integration-final-attestation/v1"
INITIAL_HEAD_PROOF_KIND = "AUTHENTICATED_PRE_ENROLLMENT_DRAFT_INTEGRATION_HEAD"

_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_IDENTITY = re.compile(r"[^\x00-\x20\x7f]+")
_PATH = re.compile(r"[^\x00-\x1f\x7f]+")


class PreEnrollmentIntegrationError(ValueError):
    """The requested integration is stale, ambiguous, or unauthorized."""


_VERIFIED_HEAD_TOKEN = object()


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


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PreEnrollmentIntegrationError(f"{label} must be a positive integer")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise PreEnrollmentIntegrationError(f"{label} is invalid")
    return value


def _repository(value: Any) -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise PreEnrollmentIntegrationError("repository identity is invalid")
    return value


def _signature(value: Any, signer: str) -> dict[str, str]:
    item = _closed(value, SIGNATURE_FIELDS, "authorization signature")
    if item["format"] not in {"ssh", "openpgp"}:
        raise PreEnrollmentIntegrationError("authorization signature format is unsupported")
    if item["signer_identity"] != signer or not isinstance(item["value"], str) or not item["value"]:
        raise PreEnrollmentIntegrationError("authorization signature identity is inconsistent")
    return copy.deepcopy(item)


def normalize_authorization(value: Any) -> dict[str, Any]:
    item = _closed(value, AUTHORIZATION_FIELDS, "pre-enrollment authorization")
    if item["schema_version"] != SCHEMA_VERSION or item["kind"] != AUTHORIZATION_KIND or item["domain"] != AUTHORIZATION_DOMAIN:
        raise PreEnrollmentIntegrationError("pre-enrollment authorization kind is unsupported")
    signer = _identity(item["signer_identity"], "authorization signer")
    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": AUTHORIZATION_KIND,
        "domain": AUTHORIZATION_DOMAIN,
        "authorization_id": _identity(item["authorization_id"], "authorization identity"),
        "repository": _repository(item["repository"]),
        "delivery_issue": _positive(item["delivery_issue"], "delivery issue"),
        "pull_request": _positive(item["pull_request"], "pull request"),
        "draft_head_sha": _oid(item["draft_head_sha"], "authorized Draft head"),
        "current_main_sha": _oid(item["current_main_sha"], "authorized current main"),
        "expected_signer": _identity(item["expected_signer"], "candidate signer"),
        "signer_identity": signer,
    }
    signed = {**fields, "signature": _signature(item["signature"], signer)}
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
    return {**signed, "authorization_digest": digest_json(signed)}


def verify_authorization(
    authorization: Mapping[str, Any], *, accepted_signers: frozenset[str],
    verifier: Callable[[bytes, Mapping[str, str], str, str], bool],
) -> dict[str, Any]:
    normalized = normalize_authorization(authorization)
    signer = normalized["signer_identity"]
    if signer not in accepted_signers or not verifier(
        canonical_json_bytes({k: copy.deepcopy(v) for k, v in normalized.items() if k not in {"signature", "authorization_digest"}}),
        normalized["signature"], signer, AUTHORIZATION_DOMAIN,
    ):
        raise PreEnrollmentIntegrationError("pre-enrollment authorization signature is not trusted")
    return normalized


def _paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise PreEnrollmentIntegrationError("conflict paths are malformed")
    result = []
    for path in value:
        if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or any(p in {"", ".", ".."} for p in path.split("/")) or not _PATH.fullmatch(path):
            raise PreEnrollmentIntegrationError("conflict path is unsafe")
        result.append(path)
    if result != sorted(set(result)):
        raise PreEnrollmentIntegrationError("conflict paths are not canonical")
    return result


def _delta(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PreEnrollmentIntegrationError("conflict-resolution delta is malformed")
    result = []
    for raw in value:
        item = _closed(raw, DELTA_FIELDS, "conflict-resolution delta")
        path = _paths([item["path"]])[0]
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


def normalize_evidence(value: Any, *, registry: Mapping[str, Any]) -> dict[str, Any]:
    item = _closed(value, EVIDENCE_FIELDS, "pre-enrollment integration evidence")
    if item["schema_version"] != SCHEMA_VERSION or item["kind"] != KIND or item["domain"] != DOMAIN:
        raise PreEnrollmentIntegrationError("pre-enrollment topology kind is unsupported")
    repository = _repository(item["repository"])
    if repository != registry.get("repository"):
        raise PreEnrollmentIntegrationError("repository is not registered")
    issue = _positive(item["delivery_issue"], "delivery issue")
    pr = _positive(item["pull_request"], "pull request")
    authorization = normalize_authorization(item["authorization"])
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
    conflicts = _paths(item["mechanical_conflict_paths"])
    delta = _delta(item["manual_conflict_resolution_delta"])
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
    signer = _identity(item["expected_signer"], "expected candidate signer")
    if signer != authorization["expected_signer"]:
        raise PreEnrollmentIntegrationError("candidate signer differs from authorization")
    normalized = copy.deepcopy(item)
    normalized.update(authorization=authorization, draft_pr={**draft, "head_sha": draft_head}, current_main={**current, "sha": main_head}, ordered_parent_shas=[draft_head, main_head], mechanical_conflict_paths=conflicts, manual_conflict_resolution_delta=delta, validated_tree_sha=_oid(item["validated_tree_sha"], "validated tree"), mechanical_merge_tree_sha=_oid(item["mechanical_merge_tree_sha"], "mechanical merge tree"))
    for field, label in ((draft["observation_digest"], "Draft observation"), (current["observation_digest"], "current-main observation"), (graph["evidence_digest"], "work-graph evidence"), (lifecycle["evidence_digest"], "lifecycle-absence evidence")):
        _digest(field, label)
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


def create_validation_receipt(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], successful_result: bool, receipt_id: str) -> dict[str, Any]:
    normalized = normalize_evidence(evidence, registry=registry)
    fields = {
        "schema_version": SCHEMA_VERSION, "kind": RECEIPT_KIND, "domain": RECEIPT_DOMAIN,
        "receipt_id": _identity(receipt_id, "receipt identity"), "repository": normalized["repository"],
        "delivery_issue": normalized["delivery_issue"], "pull_request": normalized["pull_request"],
        "ordered_parent_shas": copy.deepcopy(normalized["ordered_parent_shas"]),
        "validated_tree_sha": normalized["validated_tree_sha"], "integration_evidence_digest": digest_json(normalized),
        "registry_digest": digest_json(registry), "command_set_digest": digest_json(registry.get("validation", [])),
        "successful_result": successful_result is True,
    }
    if not fields["successful_result"]:
        raise PreEnrollmentIntegrationError("failed validation cannot produce a receipt")
    return {**fields, "receipt_digest": digest_json(fields)}


def create_final_attestation(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], receipt: Mapping[str, Any], candidate_head_sha: str, candidate_parent_shas: list[str], candidate_tree_sha: str, verified_signer: str, signature_format: str, attestation_id: str) -> dict[str, Any]:
    normalized = normalize_evidence(evidence, registry=registry)
    expected_receipt = create_validation_receipt(evidence=normalized, registry=registry, successful_result=True, receipt_id=receipt.get("receipt_id"))
    if dict(receipt) != expected_receipt:
        raise PreEnrollmentIntegrationError("validation receipt is stale or belongs to another candidate")
    if candidate_parent_shas != normalized["ordered_parent_shas"] or _oid(candidate_tree_sha, "candidate tree") != normalized["validated_tree_sha"]:
        raise PreEnrollmentIntegrationError("signed candidate topology differs from validated evidence")
    if verified_signer != normalized["expected_signer"] or signature_format not in {"ssh", "openpgp"}:
        raise PreEnrollmentIntegrationError("candidate is unsigned or signed by the wrong identity")
    fields = {
        "schema_version": SCHEMA_VERSION, "kind": ATTESTATION_KIND, "domain": ATTESTATION_DOMAIN,
        "attestation_id": _identity(attestation_id, "attestation identity"), "repository": normalized["repository"],
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


def verify_final_attestation(*, evidence: Mapping[str, Any], registry: Mapping[str, Any], receipt: Mapping[str, Any], attestation: Mapping[str, Any], commit_trailers: Mapping[str, str]) -> VerifiedInitialHeadProof:
    expected = create_final_attestation(
        evidence=evidence, registry=registry, receipt=receipt,
        candidate_head_sha=attestation.get("candidate_head_sha"), candidate_parent_shas=attestation.get("ordered_parent_shas"),
        candidate_tree_sha=attestation.get("candidate_tree_sha"), verified_signer=attestation.get("verified_signature", {}).get("signer_identity"),
        signature_format=attestation.get("verified_signature", {}).get("format"), attestation_id=attestation.get("attestation_id"),
    )
    if dict(attestation) != expected:
        raise PreEnrollmentIntegrationError("final attestation is stale, replayed, or ambiguous")
    if dict(commit_trailers) != {"SecPal-Pre-Enrollment-Integration": expected["integration_evidence_digest"], "SecPal-Pre-Enrollment-Validation-Receipt": expected["validation_receipt_digest"]}:
        raise PreEnrollmentIntegrationError("signed candidate trailers do not bind typed evidence")
    return VerifiedInitialHeadProof(INITIAL_HEAD_PROOF_KIND, expected["repository"], expected["delivery_issue"], expected["pull_request"], expected["candidate_head_sha"], expected["validation_receipt_digest"], expected["attestation_digest"], expected["integration_evidence_digest"], _VERIFIED_HEAD_TOKEN)


def execute_once(
    *, evidence: Mapping[str, Any], registry: Mapping[str, Any],
    accepted_authorization_signers: frozenset[str],
    authorization_verifier: Callable[[bytes, Mapping[str, str], str, str], bool],
    derive_tree: Callable[[list[str], str], tuple[str, list[str], list[dict[str, str]], bool]],
    run_registered_validation: Callable[[str], bool],
    observe_frozen_state: Callable[[], FrozenObservation],
    create_signed_candidate: Callable[[str, list[str], Mapping[str, str], str], Mapping[str, Any]],
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
    proof = verify_final_attestation(
        evidence=normalized,
        registry=registry,
        receipt=receipt,
        attestation=attestation,
        commit_trailers=trailers,
    )
    if not push_fast_forward(proof.initial_head_sha, normalized["draft_pr"]["head_sha"]):
        raise PreEnrollmentIntegrationError(
            "authorized non-force push failed or has an unknown result"
        )
    if _oid(observe_final_pr_head(), "final PR head") != proof.initial_head_sha:
        raise PreEnrollmentIntegrationError("final PR head equality was not proven")
    return ExecutionResult(proof.initial_head_sha, receipt, attestation, proof)
