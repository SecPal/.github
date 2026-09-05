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
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar


FOLLOW_UP_HELPER = Path(__file__).resolve().with_name("follow_up.py")


def _load_follow_up_helper() -> Any:
    loaded = sys.modules.get("secpal_pr_review.follow_up")
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if not isinstance(loaded_path, str) or Path(loaded_path).resolve() != FOLLOW_UP_HELPER:
            raise RuntimeError("Canonical follow-up module has an unexpected path")
        return loaded
    spec = importlib.util.spec_from_file_location("secpal_pr_review.follow_up", FOLLOW_UP_HELPER)
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


OID = re.compile(r"^[0-9a-fA-F]{40,64}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[^\x00-\x20\x7f]+$")
EVIDENCE_TEXT = re.compile(r"^[^\x00-\x1f\x7f]+$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SECRET_VALUE = re.compile(
    r"(?i)(?:github_pat_|gh[opsu]_|-----BEGIN [A-Z ]*PRIVATE KEY-----|authorization\s*:\s*bearer)"
)
SUPPORTED_BATCH_CAPABILITIES = frozenset({"THREAD_RESOLUTION"})
TRANSIENT_PULL_REQUEST_REACTION_CONTENTS = frozenset({"EYES"})
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
    "OUTSIDE_PR_SCOPE": frozenset({"TRACKED_AS_FOLLOW_UP"}),
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
READY_INTEGRATION_KIND = "TWO_PARENT_READY_INTEGRATION"
READY_INTEGRATION_PRIOR_AUTHORITY_KIND = "READY_INTEGRATION_PRIOR_AUTHORITY"
EXCEPTIONAL_RECOVERY_KIND = "READY_EXCEPTIONAL_RECOVERY"
EXCEPTIONAL_RECOVERY_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "authorization_id",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "prior_ready_head_sha",
        "prior_ready_tree_sha",
        "recovery_tree_sha",
        "reviewed_state_digest",
        "reviewed_feedback_digest",
        "eligibility_evidence_digest",
        "finding_ids",
        "thread_ids",
        "lifecycle",
    }
)
READY_INTEGRATION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "authorization_id",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "prior_delivery_head_sha",
        "prior_authority_digest",
        "prior_authority_tag_object_sha",
        "target_base",
        "ordered_parent_shas",
        "validated_tree_sha",
        "mechanical_merge_tree_sha",
        "mechanical_conflict_paths",
        "manual_conflict_resolution_delta",
        "reviewed_state_digest",
        "reviewed_feedback_digest",
        "validation_execution",
        "expected_signer",
        "eligibility",
    }
)

READY_INTEGRATION_PRIOR_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "prior_delivery_head_sha",
        "prior_delivery_tree_sha",
        "prior_validation_receipt_digest",
        "prior_final_attestation_digest",
        "expected_signer",
        "lifecycle",
        "publication",
    }
)


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


def _require_positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SecurityBlocker(f"{label} is not a positive integer")
    return value


def _ready_integration_delta(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SecurityBlocker("integration conflict-resolution delta is malformed")
    normalized: list[dict[str, str]] = []
    expected_keys = {"path", "status", "old_mode", "new_mode", "old_oid", "new_oid"}
    allowed_modes = {"000000", "100644", "100755", "120000", "160000"}
    for item in value:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise SecurityBlocker("integration conflict-resolution delta is malformed")
        path = item.get("path")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or not EVIDENCE_TEXT.fullmatch(path)
        ):
            raise SecurityBlocker("integration conflict-resolution path is unsafe")
        status = item.get("status")
        old_mode = item.get("old_mode")
        new_mode = item.get("new_mode")
        if (
            status not in {"A", "D", "M", "T"}
            or old_mode not in allowed_modes
            or new_mode not in allowed_modes
            or (status == "A" and old_mode != "000000")
            or (status == "D" and new_mode != "000000")
        ):
            raise SecurityBlocker("integration conflict-resolution operation is invalid")
        normalized.append(
            {
                "path": path,
                "status": status,
                "old_mode": old_mode,
                "new_mode": new_mode,
                "old_oid": _require_oid(item.get("old_oid"), "integration old object"),
                "new_oid": _require_oid(item.get("new_oid"), "integration new object"),
            }
        )
    if normalized != sorted(normalized, key=lambda item: item["path"]):
        raise SecurityBlocker("integration conflict-resolution delta is not canonical")
    paths = [item["path"] for item in normalized]
    if len(paths) != len(set(paths)):
        raise SecurityBlocker("integration conflict-resolution delta repeats a path")
    return normalized


def _ready_integration_conflict_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SecurityBlocker("integration mechanical conflict paths are malformed")
    normalized: list[str] = []
    for path in value:
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or not EVIDENCE_TEXT.fullmatch(path)
        ):
            raise SecurityBlocker("integration mechanical conflict path is unsafe")
        normalized.append(path)
    if normalized != sorted(normalized) or len(normalized) != len(set(normalized)):
        raise SecurityBlocker(
            "integration mechanical conflict paths are not canonical"
        )
    return normalized


def normalize_ready_integration_prior_authority(value: Any) -> dict[str, Any]:
    """Normalize the separately signed authority for the prior Ready head."""

    if not isinstance(value, dict) or set(value) != READY_INTEGRATION_PRIOR_AUTHORITY_KEYS:
        raise SecurityBlocker("Ready integration prior authority is malformed or ambiguous")
    if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
        raise SecurityBlocker("Ready integration prior authority contains secret-like text")
    if (
        value.get("schema_version") != "1.1"
        or value.get("kind") != READY_INTEGRATION_PRIOR_AUTHORITY_KIND
    ):
        raise SecurityBlocker("Ready integration prior authority kind or version is unsupported")
    signer = value.get("expected_signer")
    if not isinstance(signer, dict) or set(signer) != {"kind", "identity"}:
        raise SecurityBlocker("Ready integration prior signer is malformed")
    signer_kind = signer.get("kind")
    signer_identity = _require_string(signer.get("identity"), "Ready integration prior signer")
    if signer_kind == "SSH_PRINCIPAL":
        pass
    elif signer_kind == "OPENPGP_FINGERPRINT":
        if not re.fullmatch(r"[0-9A-F]{40,64}", signer_identity):
            raise SecurityBlocker("Ready integration prior OpenPGP signer is malformed")
    else:
        raise SecurityBlocker("Ready integration prior signer kind is unsupported")
    lifecycle = value.get("lifecycle")
    lifecycle_keys = {
        "identity",
        "current_authority_digest",
        "historical_proof_mode",
        "draft",
        "ready",
        "ready_transition",
        "unrestricted_reviews",
        "remediation_cycles",
        "exceptional_recoveries",
        "exceptional_continuations",
        "cycle_3",
    }
    if not isinstance(lifecycle, dict) or set(lifecycle) != lifecycle_keys:
        raise SecurityBlocker("Ready integration prior lifecycle authority is malformed")
    reviews = lifecycle.get("unrestricted_reviews")
    cycles = lifecycle.get("remediation_cycles")
    recoveries = lifecycle.get("exceptional_recoveries")
    continuations = lifecycle.get("exceptional_continuations")
    if (
        not _require_string(lifecycle.get("identity"), "Ready integration lifecycle identity")
        or not _require_digest(
            lifecycle.get("current_authority_digest"),
            "Ready integration current lifecycle authority",
        )
        or lifecycle.get("historical_proof_mode")
        not in {
            "native_lifecycle",
            "legacy_migration_checkpoint",
            "exact_state_adoption",
        }
        or lifecycle.get("draft") is not False
        or lifecycle.get("ready") is not True
        or lifecycle.get("ready_transition") is not False
        or lifecycle.get("cycle_3") is not False
        or isinstance(reviews, bool)
        or reviews != 1
        or isinstance(cycles, bool)
        or not isinstance(cycles, int)
        or not 0 <= cycles <= 2
        or isinstance(recoveries, bool)
        or not isinstance(recoveries, int)
        or not 0 <= recoveries <= 1
        or isinstance(continuations, bool)
        or not isinstance(continuations, int)
        or not 0 <= continuations <= 1
    ):
        raise SecurityBlocker("Ready integration prior lifecycle authority is invalid")
    publication = value.get("publication")
    if not isinstance(publication, dict) or set(publication) != {
        "object_oid",
        "publication_digest",
    }:
        raise SecurityBlocker("Ready integration lifecycle publication is malformed")
    return {
        "schema_version": "1.1",
        "kind": READY_INTEGRATION_PRIOR_AUTHORITY_KIND,
        "repository": _require_string(value.get("repository"), "prior authority repository"),
        "delivery_issue_number": _require_positive_integer(value.get("delivery_issue_number"), "prior authority delivery issue"),
        "pull_request_number": _require_positive_integer(value.get("pull_request_number"), "prior authority pull request"),
        "prior_delivery_head_sha": _require_oid(value.get("prior_delivery_head_sha"), "prior authority head"),
        "prior_delivery_tree_sha": _require_oid(value.get("prior_delivery_tree_sha"), "prior authority tree"),
        "prior_validation_receipt_digest": _require_digest(value.get("prior_validation_receipt_digest"), "prior validation receipt"),
        "prior_final_attestation_digest": _require_digest(value.get("prior_final_attestation_digest"), "prior final attestation"),
        "expected_signer": {"kind": signer_kind, "identity": signer_identity},
        "lifecycle": copy.deepcopy(lifecycle),
        "publication": {
            "object_oid": _require_oid(
                publication.get("object_oid"),
                "Ready integration lifecycle publication object",
            ),
            "publication_digest": _require_digest(
                publication.get("publication_digest"),
                "Ready integration lifecycle publication digest",
            ),
        },
    }


def normalize_ready_integration_evidence(
    value: Any,
    *,
    repository: str,
    reviewed_state: "StableFeedbackState",
    registry: dict[str, Any],
    validated_tree_sha: str,
) -> dict[str, Any]:
    """Normalize and admit one explicitly authorized Ready-head integration."""

    if not isinstance(value, dict) or set(value) != READY_INTEGRATION_KEYS:
        raise SecurityBlocker("Ready integration evidence is malformed or ambiguous")
    if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
        raise SecurityBlocker("Ready integration evidence contains secret-like text")
    if value.get("schema_version") != "1.1" or value.get("kind") != READY_INTEGRATION_KIND:
        raise SecurityBlocker("Ready integration topology kind or version is unsupported")
    normalized_repository = _require_string(value.get("repository"), "integration repository")
    if normalized_repository != repository or reviewed_state.repository != repository:
        raise SecurityBlocker("integration repository binding changed")
    pull_request_number = _require_positive_integer(
        value.get("pull_request_number"), "integration pull request"
    )
    if pull_request_number != reviewed_state.pull_request_number:
        raise SecurityBlocker("integration pull-request binding changed")
    delivery_issue_number = _require_positive_integer(
        value.get("delivery_issue_number"), "integration delivery issue"
    )
    authorization_id = _require_string(
        value.get("authorization_id"), "integration authorization identity"
    )
    prior_head = _require_oid(
        value.get("prior_delivery_head_sha"), "prior delivery head"
    )
    prior_authority_digest = _require_digest(
        value.get("prior_authority_digest"), "prior Ready authority digest"
    )
    if prior_head != reviewed_state.head_sha:
        raise SecurityBlocker("integration first parent is stale or substituted")
    target_base = value.get("target_base")
    if not isinstance(target_base, dict) or set(target_base) != {
        "ref",
        "authorized_sha",
        "observed_sha",
    }:
        raise SecurityBlocker("integration target-base evidence is malformed")
    target_ref = _require_string(target_base.get("ref"), "integration target-base ref")
    authorized_base = _require_oid(
        target_base.get("authorized_sha"), "authorized target-base head"
    )
    observed_base = _require_oid(
        target_base.get("observed_sha"), "observed target-base head"
    )
    if (
        target_ref != registry.get("default_branch")
        or target_ref != reviewed_state.base_ref
        or observed_base != authorized_base
    ):
        raise SecurityBlocker("integration target-base identity or bound ref drifted")
    parents = value.get("ordered_parent_shas")
    if not isinstance(parents, list) or len(parents) != 2:
        raise SecurityBlocker("Ready integration requires exactly two ordered parents")
    normalized_parents = [
        _require_oid(parent, "integration parent") for parent in parents
    ]
    if normalized_parents != [prior_head, authorized_base] or prior_head == authorized_base:
        raise SecurityBlocker("integration ordered parents are invalid")
    validated_tree = _require_oid(
        value.get("validated_tree_sha"), "integration validated tree"
    )
    if validated_tree != _require_oid(validated_tree_sha, "observed validated tree"):
        raise SecurityBlocker("integration validated tree changed")
    mechanical_tree = _require_oid(
        value.get("mechanical_merge_tree_sha"), "mechanical merge tree"
    )
    reviewed_state_digest = _require_digest(
        value.get("reviewed_state_digest"), "integration reviewed-state digest"
    )
    reviewed_feedback_digest = _require_digest(
        value.get("reviewed_feedback_digest"), "integration stable-feedback digest"
    )
    if (
        reviewed_state.pr_state != "OPEN"
        or reviewed_state_digest != reviewed_state.state_digest
        or reviewed_feedback_digest != reviewed_state.feedback_digest
    ):
        raise SecurityBlocker("integration stable-feedback evidence is stale")
    validation_execution = value.get("validation_execution")
    if not isinstance(validation_execution, dict) or set(validation_execution) != {
        "registry_digest",
        "command_set_digest",
    }:
        raise SecurityBlocker("integration validation execution is malformed")
    expected_execution = {
        "registry_digest": digest_json(registry),
        "command_set_digest": digest_json(registry.get("validation")),
    }
    normalized_execution = {
        "registry_digest": _require_digest(
            validation_execution.get("registry_digest"), "integration registry digest"
        ),
        "command_set_digest": _require_digest(
            validation_execution.get("command_set_digest"),
            "integration command-set digest",
        ),
    }
    if normalized_execution != expected_execution:
        raise SecurityBlocker("integration validation execution is stale or substituted")
    signer = value.get("expected_signer")
    if not isinstance(signer, dict) or set(signer) != {"kind", "identity"}:
        raise SecurityBlocker("integration signer evidence is malformed")
    signer_kind = signer.get("kind")
    signer_identity = _require_string(signer.get("identity"), "integration signer identity")
    if signer_kind == "SSH_PRINCIPAL":
        if not IDENTITY.fullmatch(signer_identity):
            raise SecurityBlocker("integration SSH signer identity is malformed")
    elif signer_kind == "OPENPGP_FINGERPRINT":
        if not re.fullmatch(r"[0-9A-F]{40,64}", signer_identity):
            raise SecurityBlocker("integration OpenPGP signer identity is malformed")
    else:
        raise SecurityBlocker("integration signer kind is unsupported")
    eligibility = value.get("eligibility")
    eligibility_keys = {
        "eligible",
        "lifecycle_identity",
        "draft_before",
        "draft_after",
        "ready_before",
        "ready_after",
        "ready_transition",
        "review_requested",
        "unrestricted_reviews_before",
        "unrestricted_reviews_after",
        "remediation_cycles_before",
        "remediation_cycles_after",
        "exceptional_recoveries_before",
        "exceptional_recoveries_after",
        "exceptional_continuations_before",
        "exceptional_continuations_after",
        "cycle_3",
    }
    if not isinstance(eligibility, dict) or set(eligibility) != eligibility_keys:
        raise SecurityBlocker("integration eligibility evidence is malformed")
    before_reviews = eligibility.get("unrestricted_reviews_before")
    after_reviews = eligibility.get("unrestricted_reviews_after")
    before_cycles = eligibility.get("remediation_cycles_before")
    after_cycles = eligibility.get("remediation_cycles_after")
    before_recoveries = eligibility.get("exceptional_recoveries_before")
    after_recoveries = eligibility.get("exceptional_recoveries_after")
    before_continuations = eligibility.get("exceptional_continuations_before")
    after_continuations = eligibility.get("exceptional_continuations_after")
    if (
        eligibility.get("eligible") is not True
        or not _require_string(
            eligibility.get("lifecycle_identity"),
            "integration lifecycle identity",
        )
        or eligibility.get("draft_before") is not False
        or eligibility.get("draft_after") is not False
        or eligibility.get("ready_before") is not True
        or eligibility.get("ready_after") is not True
        or eligibility.get("ready_transition") is not False
        or eligibility.get("review_requested") is not False
        or eligibility.get("cycle_3") is not False
        or isinstance(before_reviews, bool)
        or not isinstance(before_reviews, int)
        or before_reviews != 1
        or after_reviews != before_reviews
        or isinstance(before_cycles, bool)
        or not isinstance(before_cycles, int)
        or not 0 <= before_cycles <= 2
        or after_cycles != before_cycles
        or isinstance(before_recoveries, bool)
        or not isinstance(before_recoveries, int)
        or not 0 <= before_recoveries <= 1
        or isinstance(after_recoveries, bool)
        or not isinstance(after_recoveries, int)
        or after_recoveries != before_recoveries
        or isinstance(before_continuations, bool)
        or not isinstance(before_continuations, int)
        or not 0 <= before_continuations <= 1
        or isinstance(after_continuations, bool)
        or not isinstance(after_continuations, int)
        or after_continuations != before_continuations
    ):
        raise SecurityBlocker("integration eligibility or lifecycle continuity is invalid")
    normalized = {
        "schema_version": "1.1",
        "kind": READY_INTEGRATION_KIND,
        "authorization_id": authorization_id,
        "repository": normalized_repository,
        "delivery_issue_number": delivery_issue_number,
        "pull_request_number": pull_request_number,
        "prior_delivery_head_sha": prior_head,
        "prior_authority_digest": prior_authority_digest,
        "prior_authority_tag_object_sha": _require_oid(
            value.get("prior_authority_tag_object_sha"),
            "prior authority tag object",
        ),
        "target_base": {
            "ref": target_ref,
            "authorized_sha": authorized_base,
            "observed_sha": observed_base,
        },
        "ordered_parent_shas": normalized_parents,
        "validated_tree_sha": validated_tree,
        "mechanical_merge_tree_sha": mechanical_tree,
        "mechanical_conflict_paths": _ready_integration_conflict_paths(
            value.get("mechanical_conflict_paths")
        ),
        "manual_conflict_resolution_delta": _ready_integration_delta(
            value.get("manual_conflict_resolution_delta")
        ),
        "reviewed_state_digest": reviewed_state_digest,
        "reviewed_feedback_digest": reviewed_feedback_digest,
        "validation_execution": normalized_execution,
        "expected_signer": {
            "kind": signer_kind,
            "identity": signer_identity,
        },
        "eligibility": copy.deepcopy(eligibility),
    }
    return normalized


def normalize_exceptional_recovery_evidence(
    value: Any,
    *,
    repository: str,
    reviewed_state: "StableFeedbackState",
    validated_tree_sha: str,
    eligibility_evidence_digest: str,
) -> dict[str, Any]:
    """Normalize one explicitly user-authorized Ready-head recovery."""

    if not isinstance(value, dict) or set(value) != EXCEPTIONAL_RECOVERY_KEYS:
        raise SecurityBlocker("exceptional recovery evidence is malformed or ambiguous")
    if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
        raise SecurityBlocker("exceptional recovery evidence contains secret-like text")
    if (
        value.get("schema_version") != "1.0"
        or value.get("kind") != EXCEPTIONAL_RECOVERY_KIND
        or value.get("repository") != repository
        or reviewed_state.repository != repository
        or value.get("pull_request_number") != reviewed_state.pull_request_number
        or reviewed_state.pr_state != "OPEN"
        or value.get("prior_ready_head_sha") != reviewed_state.head_sha
        or value.get("reviewed_state_digest") != reviewed_state.state_digest
        or value.get("reviewed_feedback_digest") != reviewed_state.feedback_digest
        or value.get("recovery_tree_sha") != validated_tree_sha
        or value.get("eligibility_evidence_digest") != eligibility_evidence_digest
    ):
        raise SecurityBlocker("exceptional recovery identity or evidence is stale")
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, dict) or set(lifecycle) != {
        "unrestricted_reviews",
        "remediation_cycles",
        "cycle_3",
        "draft",
        "ready",
        "ready_transition",
        "exceptional_recovery_count",
    }:
        raise SecurityBlocker("exceptional recovery lifecycle is malformed")
    if lifecycle != {
        "unrestricted_reviews": 1,
        "remediation_cycles": 2,
        "cycle_3": False,
        "draft": False,
        "ready": True,
        "ready_transition": False,
        "exceptional_recovery_count": 1,
    }:
        raise SecurityBlocker("exceptional recovery would alter the finite lifecycle")
    finding_ids = value.get("finding_ids")
    thread_ids = value.get("thread_ids")
    if (
        not isinstance(finding_ids, list)
        or not finding_ids
        or any(not isinstance(item, str) or not IDENTITY.fullmatch(item) for item in finding_ids)
        or finding_ids != sorted(finding_ids)
        or len(finding_ids) != len(set(finding_ids))
        or not isinstance(thread_ids, list)
        or not thread_ids
        or any(
            not isinstance(item, str)
            or not re.fullmatch(r"PRRT_[A-Za-z0-9_-]+", item)
            for item in thread_ids
        )
        or thread_ids != sorted(thread_ids)
        or len(thread_ids) != len(set(thread_ids))
    ):
        raise SecurityBlocker("exceptional recovery finding identities are malformed")
    reviewed_threads = {
        item.get("node_id"): item
        for item in reviewed_state.feedback.get("threads", [])
        if isinstance(item, dict)
    }
    if (
        len(finding_ids) != len(thread_ids)
        or any(
            thread_id not in reviewed_threads
            or reviewed_threads[thread_id].get("is_resolved") is not False
            for thread_id in thread_ids
        )
    ):
        raise SecurityBlocker(
            "exceptional recovery threads are absent or not unresolved"
        )
    return {
        "schema_version": "1.0",
        "kind": EXCEPTIONAL_RECOVERY_KIND,
        "authorization_id": _require_string(
            value.get("authorization_id"), "exceptional recovery authorization"
        ),
        "repository": repository,
        "delivery_issue_number": _require_positive_integer(
            value.get("delivery_issue_number"), "exceptional recovery delivery issue"
        ),
        "pull_request_number": reviewed_state.pull_request_number,
        "prior_ready_head_sha": reviewed_state.head_sha,
        "prior_ready_tree_sha": _require_oid(
            value.get("prior_ready_tree_sha"), "prior Ready tree"
        ),
        "recovery_tree_sha": _require_oid(validated_tree_sha, "recovery tree"),
        "reviewed_state_digest": reviewed_state.state_digest,
        "reviewed_feedback_digest": reviewed_state.feedback_digest,
        "eligibility_evidence_digest": _require_digest(
            eligibility_evidence_digest, "exceptional recovery eligibility"
        ),
        "finding_ids": copy.deepcopy(finding_ids),
        "thread_ids": copy.deepcopy(thread_ids),
        "lifecycle": copy.deepcopy(lifecycle),
    }


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
    pull_request_reactions = [
        reaction
        for reaction in _reactions(
            source.get("pull_request_reactions", []), "pull request"
        )
        if reaction["content"] not in TRANSIENT_PULL_REQUEST_REACTION_CONTENTS
    ]
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
        comment_identities = [item["node_id"] for item in thread_comments]
        if len(comment_identities) != len(set(comment_identities)):
            raise SecurityBlocker(
                f"review thread {thread_id} contains duplicate comment identities"
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
    comment_identities = [
        item["node_id"] for item in projection["conversation_comments"]
    ] + [
        item["node_id"]
        for thread in projection["threads"]
        for item in thread["comments"]
    ]
    if len(comment_identities) != len(set(comment_identities)):
        raise SecurityBlocker("stable feedback contains duplicate comment identities")
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
        self.pull_request_number = _require_positive_integer(
            self.pull_request_number, "pull request identity"
        )
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


_VERIFIED_VALIDATION_EVIDENCE = object()


@dataclass(frozen=True)
class VerifiedValidationEvidence:
    """Canonical source evidence exposed only after full attestation verification."""

    repository: str
    pull_request_number: int
    head_sha: str
    tree_sha: str
    validation_receipt_digest: str
    final_attestation_digest: str
    source_validation_evidence_digest: str
    _verification_seal: object


def is_verified_validation_evidence(value: Any) -> bool:
    """Reject caller-constructed validation summaries at trust boundaries."""

    return (
        isinstance(value, VerifiedValidationEvidence)
        and value._verification_seal is _VERIFIED_VALIDATION_EVIDENCE
    )


def _require_reviewed_state_identity(
    repository: Any, reviewed_state: Any
) -> StableFeedbackState:
    """Require one canonical reviewed state for the exact repository."""

    repository = _require_string(repository, "reviewed repository")
    if not REPOSITORY.fullmatch(repository):
        raise SecurityBlocker("reviewed repository identity is malformed")
    if not isinstance(reviewed_state, StableFeedbackState):
        raise SecurityBlocker("reviewed state is not canonical")
    if reviewed_state.repository != repository:
        raise SecurityBlocker("reviewed repository identity changed")
    return reviewed_state


def verify_reviewed_state_evidence(value: Any) -> StableFeedbackState:
    """Verify one complete closed reviewed-state document."""

    if not isinstance(value, dict):
        raise SecurityBlocker("reviewed-state evidence is malformed")
    reviewed = StableFeedbackState.from_payload(value)
    if value != reviewed.to_dict():
        raise SecurityBlocker("reviewed-state evidence is invalid or stale")
    return reviewed


def normalize_resolution_eligibility_evidence(
    value: Any,
    *,
    repository: str,
    reviewed_state: StableFeedbackState,
) -> dict[str, Any]:
    """Normalize the existing closed resolution-eligibility evidence."""

    expected_keys = {
        "schema_version",
        "repository",
        "pull_request_number",
        "reviewed_head_sha",
        "reviewed_state_digest",
        "eligible_threads",
    }
    threads = value.get("eligible_threads") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("schema_version") != "1.1"
        or value.get("repository") != repository
        or reviewed_state.repository != repository
        or value.get("pull_request_number") != reviewed_state.pull_request_number
        or isinstance(value.get("pull_request_number"), bool)
        or value.get("reviewed_head_sha") != reviewed_state.head_sha
        or value.get("reviewed_state_digest") != reviewed_state.state_digest
        or not isinstance(threads, list)
    ):
        raise SecurityBlocker(
            "resolution eligibility evidence is invalid or stale"
        )
    reviewed_threads = {
        item.get("node_id"): item
        for item in reviewed_state.feedback.get("threads", [])
        if isinstance(item, dict)
    }
    observed_thread_ids: list[str] = []
    for item in threads:
        if not isinstance(item, dict) or set(item) != {
            "thread_id",
            "classification",
            "disposition",
            "finding_ids",
            "evidence_digest",
            "follow_up",
        }:
            raise SecurityBlocker(
                "resolution eligibility evidence thread is malformed"
            )
        thread_id = item.get("thread_id")
        classification = item.get("classification")
        disposition = item.get("disposition")
        finding_ids = item.get("finding_ids")
        reviewed_thread = reviewed_threads.get(thread_id)
        if (
            not isinstance(thread_id, str)
            or not re.fullmatch(r"PRRT_[A-Za-z0-9_-]+", thread_id)
            or not isinstance(classification, str)
            or disposition
            not in CLASSIFICATION_DISPOSITIONS.get(
                classification, frozenset()
            )
            or not isinstance(finding_ids, list)
            or not finding_ids
            or any(
                not isinstance(finding_id, str)
                or not IDENTITY.fullmatch(finding_id)
                or SECRET_VALUE.search(finding_id)
                for finding_id in finding_ids
            )
            or len(finding_ids) != len(set(finding_ids))
            or not isinstance(item.get("evidence_digest"), str)
            or not DIGEST.fullmatch(item["evidence_digest"])
            or not isinstance(reviewed_thread, dict)
            or reviewed_thread.get("is_resolved") is not False
        ):
            raise SecurityBlocker(
                "resolution eligibility evidence thread is ineligible"
            )
        if disposition == "TRACKED_AS_FOLLOW_UP":
            try:
                follow_up.parse_follow_up(item.get("follow_up"))
            except follow_up.FollowUpError as exc:
                raise SecurityBlocker(str(exc)) from exc
        elif item.get("follow_up") is not None:
            raise SecurityBlocker(
                "only tracked out-of-scope eligibility may carry follow-up identity"
            )
        observed_thread_ids.append(thread_id)
    if len(observed_thread_ids) != len(set(observed_thread_ids)):
        raise SecurityBlocker(
            "resolution eligibility evidence contains duplicate threads"
        )
    return copy.deepcopy(value)


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
    follow_up: Any | None


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
        "follow_up": item.follow_up.to_dict() if item.follow_up is not None else None,
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
        if value["schema_version"] != "1.3":
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
                "follow_up",
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
            follow_up_identity = None
            if disposition == "TRACKED_AS_FOLLOW_UP":
                try:
                    follow_up_identity = follow_up.parse_follow_up(item["follow_up"])
                except follow_up.FollowUpError as exc:
                    raise SecurityBlocker(str(exc)) from exc
            elif item["follow_up"] is not None:
                raise SecurityBlocker(
                    "only tracked out-of-scope findings may carry follow-up identity"
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
                    follow_up=follow_up_identity,
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
            schema_version="1.3",
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
    eligibility_evidence_digest: str | None = None,
    integration_evidence_digest: str | None = None,
    exceptional_recovery_evidence_digest: str | None = None,
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
    if eligibility_evidence_digest is not None:
        if (
            not isinstance(eligibility_evidence_digest, str)
            or not DIGEST.fullmatch(eligibility_evidence_digest)
        ):
            raise SecurityBlocker("eligibility evidence digest is malformed")
        fields["eligibility_evidence_digest"] = eligibility_evidence_digest
    if integration_evidence_digest is not None:
        fields["integration_evidence_digest"] = _require_digest(
            integration_evidence_digest, "integration evidence digest"
        )
    if exceptional_recovery_evidence_digest is not None:
        fields["exceptional_recovery_evidence_digest"] = _require_digest(
            exceptional_recovery_evidence_digest,
            "exceptional recovery evidence digest",
        )
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
        eligibility_evidence_digest=validation_receipt.get(
            "eligibility_evidence_digest"
        ),
        integration_evidence_digest=validation_receipt.get(
            "integration_evidence_digest"
        ),
        exceptional_recovery_evidence_digest=validation_receipt.get(
            "exceptional_recovery_evidence_digest"
        ),
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
    if "eligibility_evidence_digest" in validation_receipt:
        fields["eligibility_evidence_digest"] = validation_receipt[
            "eligibility_evidence_digest"
        ]
    if "integration_evidence_digest" in validation_receipt:
        fields["integration_evidence_digest"] = validation_receipt[
            "integration_evidence_digest"
        ]
    if "exceptional_recovery_evidence_digest" in validation_receipt:
        fields["exceptional_recovery_evidence_digest"] = validation_receipt[
            "exceptional_recovery_evidence_digest"
        ]
    return {**fields, "attestation_digest": digest_json(fields)}


def create_ready_integration_attestation(
    *,
    repository: str,
    head_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    reviewed_state: StableFeedbackState,
    validation_receipt: Any,
    integration_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Assemble final evidence for the one bounded Ready integration topology."""

    if "exceptional_recovery_evidence_digest" in validation_receipt:
        raise SecurityBlocker(
            "Ready integration cannot be combined with exceptional recovery"
        )

    ordinary = create_validation_attestation(
        repository=repository,
        head_sha=head_sha,
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed_state,
        validation_receipt=validation_receipt,
    )
    normalized = normalize_ready_integration_evidence(
        integration_evidence,
        repository=repository,
        reviewed_state=reviewed_state,
        registry=registry,
        validated_tree_sha=validation_receipt.get("validated_tree_sha"),
    )
    if validation_receipt.get("integration_evidence_digest") != digest_json(normalized):
        raise SecurityBlocker("validation receipt does not bind the Ready integration evidence")
    eligibility_digest = ordinary.get("eligibility_evidence_digest")
    eligibility_bound = eligibility_digest is not None
    fields = {
        "schema_version": "1.2" if eligibility_bound else "1.1",
        "kind": (
            "ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION"
            if eligibility_bound
            else "READY_INTEGRATION_VALIDATION_ATTESTATION"
        ),
        "repository": normalized["repository"],
        "delivery_issue_number": normalized["delivery_issue_number"],
        "pull_request_number": normalized["pull_request_number"],
        "head_sha": _require_oid(head_sha, "integration attestation head"),
        "topology_kind": normalized["kind"],
        "authorization_id": normalized["authorization_id"],
        "prior_authority_digest": normalized["prior_authority_digest"],
        "prior_authority_tag_object_sha": normalized[
            "prior_authority_tag_object_sha"
        ],
        "ordered_parent_shas": copy.deepcopy(normalized["ordered_parent_shas"]),
        "validated_tree_sha": normalized["validated_tree_sha"],
        "mechanical_merge_tree_sha": normalized["mechanical_merge_tree_sha"],
        "mechanical_conflict_paths": copy.deepcopy(
            normalized["mechanical_conflict_paths"]
        ),
        "manual_conflict_resolution_delta": copy.deepcopy(
            normalized["manual_conflict_resolution_delta"]
        ),
        "validation_receipt_digest": ordinary["validation_receipt_digest"],
        "integration_evidence_digest": digest_json(normalized),
        "registry_digest": ordinary["registry_digest"],
        "command_set_digest": ordinary["command_set_digest"],
        "reviewed_head_sha": ordinary["reviewed_head_sha"],
        "reviewed_state_digest": ordinary["reviewed_state_digest"],
        "reviewed_feedback_digest": ordinary["reviewed_feedback_digest"],
        "expected_signer": copy.deepcopy(normalized["expected_signer"]),
        "eligibility": copy.deepcopy(normalized["eligibility"]),
        "successful_result": True,
    }
    if eligibility_bound:
        fields["manual_gate_evidence"] = copy.deepcopy(
            ordinary["manual_gate_evidence"]
        )
        fields["eligibility_evidence_digest"] = eligibility_digest
    return {**fields, "attestation_digest": digest_json(fields)}


def verify_eligibility_bound_ready_integration_attestation(
    attestation: Any,
    *,
    repository: str,
    head_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    reviewed_state: StableFeedbackState,
    validation_receipt: dict[str, Any],
    integration_evidence: dict[str, Any],
    commit_parent_shas: list[str],
    commit_tree_sha: str,
    commit_validation_receipt_digest: str | None,
    commit_integration_evidence_digest: str | None,
) -> None:
    """Verify the closed integration-resolution attestation kind."""

    if (
        not isinstance(attestation, dict)
        or attestation.get("schema_version") != "1.2"
        or attestation.get("kind")
        != "ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION"
        or not isinstance(attestation.get("eligibility_evidence_digest"), str)
        or not DIGEST.fullmatch(attestation["eligibility_evidence_digest"])
    ):
        raise SecurityBlocker(
            "eligibility-bound Ready integration attestation is required"
        )
    if (
        validation_receipt.get("eligibility_evidence_digest")
        != attestation["eligibility_evidence_digest"]
    ):
        raise SecurityBlocker(
            "Ready integration receipt and attestation eligibility differ"
        )
    verify_ready_integration_attestation(
        attestation,
        repository=repository,
        head_sha=head_sha,
        registry=registry,
        command_set=command_set,
        reviewed_state=reviewed_state,
        validation_receipt=validation_receipt,
        integration_evidence=integration_evidence,
        commit_parent_shas=commit_parent_shas,
        commit_tree_sha=commit_tree_sha,
        commit_validation_receipt_digest=commit_validation_receipt_digest,
        commit_integration_evidence_digest=commit_integration_evidence_digest,
    )


def verify_ready_integration_attestation(
    attestation: Any,
    *,
    repository: str,
    head_sha: str,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    reviewed_state: StableFeedbackState,
    validation_receipt: dict[str, Any],
    integration_evidence: dict[str, Any],
    commit_parent_shas: list[str],
    commit_tree_sha: str,
    commit_validation_receipt_digest: str | None,
    commit_integration_evidence_digest: str | None,
) -> None:
    normalized = normalize_ready_integration_evidence(
        integration_evidence,
        repository=repository,
        reviewed_state=reviewed_state,
        registry=registry,
        validated_tree_sha=commit_tree_sha,
    )
    if commit_parent_shas != normalized["ordered_parent_shas"]:
        raise SecurityBlocker("integration attestation ordered parents changed")
    if (
        commit_validation_receipt_digest != validation_receipt.get("receipt_digest")
        or commit_integration_evidence_digest != digest_json(normalized)
    ):
        raise SecurityBlocker("integration commit evidence trailers changed")
    expected = create_ready_integration_attestation(
        repository=repository,
        head_sha=head_sha,
        registry=registry,
        command_set=command_set,
        reviewed_state=reviewed_state,
        validation_receipt=validation_receipt,
        integration_evidence=normalized,
    )
    if not isinstance(attestation, dict) or attestation != expected:
        raise SecurityBlocker("Ready integration attestation is invalid or stale")


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
) -> VerifiedValidationEvidence:
    reviewed_state = _require_reviewed_state_identity(repository, reviewed_state)
    reviewed_pull_request = reviewed_state.pull_request_number
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
        eligibility_evidence_digest=attestation.get(
            "eligibility_evidence_digest"
        ),
        exceptional_recovery_evidence_digest=attestation.get(
            "exceptional_recovery_evidence_digest"
        ),
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
    source_binding = {
        "repository": repository,
        "pull_request_number": reviewed_pull_request,
        "head_sha": head_sha,
        "tree_sha": commit_tree_sha,
        "validation_receipt_digest": receipt["receipt_digest"],
        "final_attestation_digest": expected["attestation_digest"],
        "reviewed_state_digest": reviewed_state.state_digest,
        "reviewed_feedback_digest": reviewed_state.feedback_digest,
    }
    return VerifiedValidationEvidence(
        repository=repository,
        pull_request_number=reviewed_pull_request,
        head_sha=head_sha,
        tree_sha=commit_tree_sha,
        validation_receipt_digest=receipt["receipt_digest"],
        final_attestation_digest=expected["attestation_digest"],
        source_validation_evidence_digest=digest_json(source_binding),
        _verification_seal=_VERIFIED_VALIDATION_EVIDENCE,
    )


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
            if policy.get("require_github_verified") is True and not (
                github.get("verified") is True and github.get("reason") == "valid"
            ):
                raise SecurityBlocker(
                    f"GitHub verification rejected user-authored commit: {oid}"
                )
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


def _verify_policy_evidence(check_evidence: Any, policy: Any) -> None:
    """Require independently typed ruleset and classic-protection evidence."""

    if not isinstance(check_evidence, dict) or not isinstance(policy, dict):
        raise SecurityBlocker("required policy evidence is malformed")
    rulesets = check_evidence.get("ruleset_evidence")
    classic = check_evidence.get("classic_branch_protection_evidence")
    if rulesets is classic:
        raise SecurityBlocker("ruleset and classic branch-protection evidence are ambiguous")
    if policy.get("require_ruleset_evidence") is True and not isinstance(rulesets, list):
        raise SecurityBlocker("independent ruleset evidence is missing")
    if policy.get("require_branch_protection_evidence") is True and not isinstance(classic, dict):
        raise SecurityBlocker("complete classic branch-protection evidence is missing")


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
    if any(
        finding.disposition == "TRACKED_AS_FOLLOW_UP"
        for finding in request.findings
    ):
        raise SecurityBlocker(
            "tracked follow-up resolution requires the authenticated simple resolver"
        )
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
    _verify_policy_evidence(check_evidence, check_policy)
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
