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
import subprocess
import tempfile
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar


FOLLOW_UP_HELPER = Path(__file__).resolve().with_name("follow_up.py")
EVIDENCE_HELPER = Path(__file__).resolve().parents[1] / "secpal-pr-review.py"
EXTERNAL_COMMAND_TIMEOUT_SECONDS = 30


def _load_follow_up_helper() -> Any:
    loaded = sys.modules.get("secpal_pr_review.follow_up")
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).absolute() != FOLLOW_UP_HELPER.absolute()
        ):
            raise RuntimeError("Canonical follow-up module has an unexpected path")
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


def _load_evidence_helper() -> Any:
    module_name = "secpal_pr_review.integration_evidence_helper"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).absolute() != EVIDENCE_HELPER.absolute()
        ):
            raise RuntimeError("Canonical evidence helper has an unexpected path")
    spec = importlib.util.spec_from_file_location(module_name, EVIDENCE_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load evidence helper: {EVIDENCE_HELPER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


OID = re.compile(r"^[0-9a-fA-F]{40,64}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[^\x00-\x20\x7f]+$")
EVIDENCE_TEXT = re.compile(r"^[^\x00-\x1f\x7f]+$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SECRET_VALUE = re.compile(
    r"(?i)(?:github_pat_|gh[opsu]_|-----BEGIN [A-Z ]*PRIVATE KEY-----|authorization\s*:\s*bearer)"
)
VALIDATION_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "repository",
        "default_branch",
        "allowed_base_repositories",
        "reviewer_identities",
        "focused_validation",
        "required_local_validation",
        "final_eligibility_absence_recoveries",
        "signature_policy",
        "lifecycle_authority_policy",
        "pre_enrollment_integration_policy",
        "check_policy",
        "manual_gates",
        "unsupported_operations",
        "maximum_api_calls",
        "maximum_items",
        "maximum_threads",
        "maximum_comments",
        "maximum_reactions",
    }
)
VALIDATION_REGISTRY_PROJECTION_FIELDS = frozenset(
    {
        "repository",
        "default_branch",
        "allowed_base_repositories",
        "focused_validation",
        "required_local_validation",
        "signature_policy",
        "check_policy",
        "manual_gates",
        "maximum_api_calls",
        "maximum_items",
    }
)
SUPPORTED_BATCH_CAPABILITIES = frozenset({"THREAD_RESOLUTION"})
TRANSIENT_PULL_REQUEST_REACTION_CONTENTS = frozenset({"EYES"})
CODEX_PROVIDER_LOGIN = "chatgpt-codex-connector"
GITHUB_CODE_QUALITY_LOGIN = "github-code-quality"
CODEX_REVIEW_SUMMARY_MARKER = "<!-- codex-pull-request-review-summary -->"
CODEX_REVIEW_STATUS = re.compile(
    r"<!--\s*codex-security-review:v1\s+(\{.*?\})\s*-->", re.DOTALL
)
CODEX_CANONICAL_COMPLETED_STATUS = re.compile(
    r'✅ \*\*Completed\*\* <relative-time datetime="'
    r'(?P<datetime>[0-9]{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12][0-9]|3[01])'
    r'|(?:0[469]|11)-(?:0[1-9]|[12][0-9]|30)|02-(?:0[1-9]|1[0-9]|2[0-9]))'
    r'T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]'
    r'(?:\.[0-9]{1,6})?Z)">(?P=datetime)</relative-time>'
)
CODEX_REVIEW_LABELS = {
    "Code Review": frozenset({"**Code Review**", "📝 **Code Review**"}),
    "Security Review": frozenset(
        {"**Security Review**", "🔒 **Security Review**"}
    ),
}
SUCCESSOR_TRANSPORT_ROLES = frozenset(
    {
        "CODEX_SUMMARY_UPDATE",
        "CODEX_REVIEW_REQUEST",
        "CODEX_SECURITY_REVIEW_REQUEST",
        "CODEX_CODE_REVIEW_RESULT",
        "CODEX_SECURITY_REVIEW_RESULT",
        "CODEX_COMPLETION_REACTION",
        "CODEX_REVIEW",
        "GITHUB_CODE_QUALITY_REVIEW",
    }
)
REQUIRED_CODEX_SUCCESSOR_ROLES = frozenset(
    {
        "CODEX_SUMMARY_UPDATE",
        "CODEX_REVIEW_REQUEST",
        "CODEX_SECURITY_REVIEW_REQUEST",
        "CODEX_CODE_REVIEW_RESULT",
        "CODEX_SECURITY_REVIEW_RESULT",
    }
)
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
EXCEPTIONAL_CONTINUATION_KIND = "READY_EXCEPTIONAL_CONTINUATION"
EXCEPTIONAL_CONTINUATION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "authorization_id",
        "repository",
        "delivery_issue_number",
        "pull_request_number",
        "prior_ready_head_sha",
        "prior_ready_tree_sha",
        "continuation_tree_sha",
        "reviewed_state_digest",
        "reviewed_feedback_digest",
        "eligibility_evidence_digest",
        "finding_ids",
        "thread_ids",
        "expected_signer",
        "lifecycle",
    }
)
EXCEPTIONAL_CONTINUATION_REANCHOR_KEYS = EXCEPTIONAL_CONTINUATION_KEYS | {
    "reanchor"
}
EXCEPTIONAL_CONTINUATION_REANCHOR_FIELDS = frozenset(
    {
        "evidence_digest",
        "original_pull_request",
        "replacement_pull_request",
        "rejected_candidate_head_sha",
        "rejected_candidate_tree_sha",
        "rejected_validation_receipt_digest",
        "rejected_final_attestation_digest",
        "rejected_state_digest",
        "replacement_state_digest",
        "material_finding_ids",
        "material_thread_ids",
        "finding_source_digest",
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
READY_INTEGRATION_V12_KEYS = READY_INTEGRATION_KEYS | {"reviewed_head_sha"}

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
READY_INTEGRATION_RECOVERED_PRIOR_AUTHORITY_KEYS = (
    READY_INTEGRATION_PRIOR_AUTHORITY_KEYS | {"recovery_publication"}
)
READY_INTEGRATION_RECOVERY_PUBLICATION_KEYS = frozenset(
    {
        "object_oid", "publication_digest", "authorization_id",
        "authorization_digest", "fresh_validation_receipt_digest",
        "feedback_assessment_digest", "historical_evidence_loss_proof_digest",
        "historical_bytes_reconstructed",
    }
)
READY_INTEGRATION_ADOPTED_PRIOR_AUTHORITY_KEYS = frozenset(
    READY_INTEGRATION_PRIOR_AUTHORITY_KEYS
    | {"source_authority_mode", "source_authority", "historical_companions"}
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


def digest_text(value: str) -> str:
    """Return the exact UTF-8 body digest used by Stable Feedback capture."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_codex_completed_status(value: str) -> bool:
    if value == "**Completed**":
        return True
    match = CODEX_CANONICAL_COMPLETED_STATUS.fullmatch(value)
    if match is None:
        return False
    timestamp = match.group("datetime")
    year = int(timestamp[:4])
    if year == 0:
        return False
    if timestamp[5:10] == "02-29" and not (
        year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    ):
        return False
    return True


def verify_codex_provider_summary(body: Any, *, head_sha: str) -> None:
    """Verify the canonical terminal Code/Security provider summary for a head."""

    head_sha = _require_oid(head_sha, "Codex provider summary head")
    if (
        not isinstance(body, str)
        or CODEX_REVIEW_SUMMARY_MARKER not in body
        or len(body.encode("utf-8")) > 64 * 1024
    ):
        raise SecurityBlocker("Codex review provider status is indeterminate")
    matches = CODEX_REVIEW_STATUS.findall(body)
    if len(matches) != 1:
        raise SecurityBlocker("Codex review provider status is indeterminate")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate provider status key")
            value[key] = item
        return value

    try:
        status = json.loads(matches[0], object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SecurityBlocker("Codex review provider status is indeterminate") from exc
    if not isinstance(status, dict) or not {"headSha", "status"} <= set(status):
        raise SecurityBlocker("Codex review provider status is indeterminate")
    if status.get("headSha") != head_sha:
        raise SecurityBlocker(
            "Codex review provider status is stale for the current head"
        )
    if status.get("status") != "completed":
        raise SecurityBlocker("Codex review provider is not terminal")
    for label in ("Code Review", "Security Review"):
        rows = [line for line in body.splitlines() if f"**{label}**" in line]
        if len(rows) != 1:
            raise SecurityBlocker("Codex review provider status is indeterminate")
        cells = rows[0].split("|")
        if (
            len(cells) != 6
            or cells[0].strip()
            or cells[-1].strip()
            or cells[1].strip() not in CODEX_REVIEW_LABELS[label]
            or not cells[3].strip()
            or not cells[4].strip()
        ):
            raise SecurityBlocker("Codex review provider status is indeterminate")
        if not _is_codex_completed_status(cells[2].strip()):
            raise SecurityBlocker("Codex review provider is not terminal")


def validation_registry_projection(entry: Any) -> dict[str, Any]:
    """Return the one closed registry identity used by validation evidence."""

    if not isinstance(entry, dict):
        raise SecurityBlocker("validation registry entry is malformed")
    missing = sorted(VALIDATION_REGISTRY_PROJECTION_FIELDS - entry.keys())
    unknown = sorted(entry.keys() - VALIDATION_REGISTRY_ENTRY_FIELDS)
    if missing or unknown:
        raise SecurityBlocker(
            "validation registry entry is not a supported closed projection"
        )
    focused_validation = entry["focused_validation"]
    required_validation = entry["required_local_validation"]
    if not isinstance(focused_validation, list) or not isinstance(
        required_validation, list
    ):
        raise SecurityBlocker("validation registry command set is malformed")
    validation = [
        command
        for command in focused_validation
        if isinstance(command, dict)
        and command.get("execution_policy", "always") == "always"
    ]
    if any(not isinstance(command, dict) for command in focused_validation) or any(
        not isinstance(command, dict) for command in required_validation
    ):
        raise SecurityBlocker("validation registry command set is malformed")
    binding = {
        "repository": entry["repository"],
        "default_branch": entry["default_branch"],
        "allowed_base_repositories": copy.deepcopy(
            entry["allowed_base_repositories"]
        ),
        "manual_gates": copy.deepcopy(entry["manual_gates"]),
        "signature_policy": copy.deepcopy(entry["signature_policy"]),
        "check_policy": copy.deepcopy(entry["check_policy"]),
        "limits": {
            key: entry[key] for key in ("maximum_api_calls", "maximum_items")
        },
        "validation": copy.deepcopy(validation + required_validation),
        "focused_only_validation": copy.deepcopy(
            [
                command
                for command in focused_validation
                if command.get("execution_policy") == "focused-only"
            ]
        ),
    }
    if "pre_enrollment_integration_policy" in entry:
        if not isinstance(entry["pre_enrollment_integration_policy"], dict):
            raise SecurityBlocker(
                "pre-enrollment integration registry policy is malformed"
            )
        binding["pre_enrollment_integration_policy"] = copy.deepcopy(
            entry["pre_enrollment_integration_policy"]
        )
    return binding


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

    if not isinstance(value, dict):
        raise SecurityBlocker("Ready integration prior authority is malformed or ambiguous")
    if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
        raise SecurityBlocker("Ready integration prior authority contains secret-like text")
    schema_version = value.get("schema_version")
    keys = set(value)
    authority_mode = (
        "ORDINARY"
        if schema_version == "1.1" and keys == READY_INTEGRATION_PRIOR_AUTHORITY_KEYS
        else "RECOVERED"
        if schema_version == "1.2"
        and keys == READY_INTEGRATION_RECOVERED_PRIOR_AUTHORITY_KEYS
        else "ADOPTED_V3"
        if schema_version == "1.2"
        and keys == READY_INTEGRATION_ADOPTED_PRIOR_AUTHORITY_KEYS
        else None
    )
    if authority_mode is None:
        raise SecurityBlocker("Ready integration prior authority is malformed or ambiguous")
    if schema_version not in {"1.1", "1.2"} or (
        value.get("kind") != READY_INTEGRATION_PRIOR_AUTHORITY_KIND
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
    if authority_mode == "ADOPTED_V3":
        lifecycle_keys |= {
            "ready_transition_count",
            "ready_history",
            "exceptional_recovery_history",
            "exceptional_continuation_history",
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
    if authority_mode == "ADOPTED_V3":
        ready_history = lifecycle.get("ready_history")
        if (
            lifecycle.get("historical_proof_mode") != "exact_state_adoption"
            or isinstance(lifecycle.get("ready_transition_count"), bool)
            or lifecycle.get("ready_transition_count") != 1
            or not isinstance(ready_history, list)
            or len(ready_history) != 1
            or not isinstance(ready_history[0], dict)
            or set(ready_history[0])
            != {"sequence", "transition_kind", "event_authorization_digest"}
            or ready_history[0].get("sequence") != 1
            or ready_history[0].get("transition_kind") != "DRAFT_TO_READY"
            or not _require_digest(
                ready_history[0].get("event_authorization_digest"),
                "Ready integration transition authorization",
            )
            or lifecycle.get("exceptional_recovery_history") != []
            or lifecycle.get("exceptional_continuation_history") != []
            or recoveries != 0
            or continuations != 0
        ):
            raise SecurityBlocker(
                "adopted Ready integration lifecycle authority is invalid"
            )
    publication = value.get("publication")
    if not isinstance(publication, dict) or set(publication) != {
        "object_oid",
        "publication_digest",
    }:
        raise SecurityBlocker("Ready integration lifecycle publication is malformed")
    normalized = {
        "schema_version": schema_version,
        "kind": READY_INTEGRATION_PRIOR_AUTHORITY_KIND,
        "repository": _require_string(value.get("repository"), "prior authority repository"),
        "delivery_issue_number": _require_positive_integer(value.get("delivery_issue_number"), "prior authority delivery issue"),
        "pull_request_number": _require_positive_integer(value.get("pull_request_number"), "prior authority pull request"),
        "prior_delivery_head_sha": _require_oid(value.get("prior_delivery_head_sha"), "prior authority head"),
        "prior_delivery_tree_sha": _require_oid(value.get("prior_delivery_tree_sha"), "prior authority tree"),
        "prior_validation_receipt_digest": _require_digest(value.get("prior_validation_receipt_digest"), "prior validation receipt"),
        "prior_final_attestation_digest": (
            _require_digest(
                value.get("prior_final_attestation_digest"),
                "prior final attestation",
            )
            if authority_mode != "ADOPTED_V3"
            else value.get("prior_final_attestation_digest")
        ),
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
    if authority_mode == "ORDINARY":
        return normalized
    if authority_mode == "RECOVERED":
        recovery = value.get("recovery_publication")
        if (
            not isinstance(recovery, dict)
            or set(recovery) != READY_INTEGRATION_RECOVERY_PUBLICATION_KEYS
            or recovery.get("historical_bytes_reconstructed") is not False
        ):
            raise SecurityBlocker(
                "Ready integration recovered prior authority is malformed"
            )
        normalized["recovery_publication"] = {
            "object_oid": _require_oid(
                recovery.get("object_oid"), "Ready recovery publication object"
            ),
            "publication_digest": _require_digest(
                recovery.get("publication_digest"),
                "Ready recovery publication",
            ),
            "authorization_id": _require_string(
                recovery.get("authorization_id"),
                "Ready recovery authorization identity",
            ),
            "authorization_digest": _require_digest(
                recovery.get("authorization_digest"),
                "Ready recovery authorization",
            ),
            "fresh_validation_receipt_digest": _require_digest(
                recovery.get("fresh_validation_receipt_digest"),
                "Ready recovery fresh validation receipt",
            ),
            "feedback_assessment_digest": _require_digest(
                recovery.get("feedback_assessment_digest"),
                "Ready recovery feedback assessment",
            ),
            "historical_evidence_loss_proof_digest": _require_digest(
                recovery.get("historical_evidence_loss_proof_digest"),
                "Ready recovery historical evidence-loss proof",
            ),
            "historical_bytes_reconstructed": False,
        }
        return normalized
    if normalized["prior_final_attestation_digest"] is not None:
        raise SecurityBlocker(
            "adopted Ready authority cannot claim a historical final attestation"
        )
    if value.get("source_authority_mode") != "EXACT_STATE_ADOPTION_V3":
        raise SecurityBlocker("adopted Ready source authority mode is unsupported")
    companions = value.get("historical_companions")
    expected_companions = {
        "reviewed_state_bytes": "UNAVAILABLE",
        "validation_receipt_bytes": "UNAVAILABLE",
        "final_attestation_bytes": "UNAVAILABLE",
        "historical_bytes_reconstructed": False,
    }
    if companions != expected_companions:
        raise SecurityBlocker("adopted Ready historical companion status is invalid")
    source = value.get("source_authority")
    source_keys = {
        "proof_version",
        "source_parent_sha",
        "source_signer_identity",
        "commit_signature_evidence_digest",
        "historical_receipt_provenance_digest",
        "current_safety_digest",
        "observed_history_digest",
        "intended_state_digest",
        "head_advanced_count",
        "head_advanced_history_digest",
        "loss_admission_id",
        "loss_admission_digest",
        "review_budget_admission_id",
        "review_budget_admission_digest",
        "adoption_proof_digest",
        "adoption_authorization_id",
        "adoption_authorization_digest",
        "enrollment_publication",
        "ready_transition",
    }
    if not isinstance(source, dict) or set(source) != source_keys:
        raise SecurityBlocker("adopted Ready source authority is malformed")
    enrollment = source.get("enrollment_publication")
    if not isinstance(enrollment, dict) or set(enrollment) != {
        "object_oid", "publication_digest"
    }:
        raise SecurityBlocker("adopted Ready enrollment publication is malformed")
    transition = source.get("ready_transition")
    if not isinstance(transition, dict) or set(transition) != {
        "event_id", "event_digest", "predecessor_authority_digest",
        "predecessor_head_sha", "resulting_head_sha",
    }:
        raise SecurityBlocker("adopted Ready transition authority is malformed")
    head_advanced_count = source.get("head_advanced_count")
    if (
        source.get("proof_version") != "3.0"
        or _require_oid(source.get("source_parent_sha"), "adopted source parent")
        == normalized["prior_delivery_head_sha"]
        or not _require_string(
            source.get("source_signer_identity"), "adopted source signer"
        )
        or isinstance(head_advanced_count, bool)
        or not isinstance(head_advanced_count, int)
        or head_advanced_count < 0
    ):
        raise SecurityBlocker("adopted Ready source authority is invalid")
    for field, label in (
        ("commit_signature_evidence_digest", "adopted commit signature evidence"),
        ("historical_receipt_provenance_digest", "historical receipt provenance"),
        ("current_safety_digest", "adopted current safety"),
        ("observed_history_digest", "adopted observed history"),
        ("intended_state_digest", "adopted intended state"),
        ("head_advanced_history_digest", "adopted head history"),
        ("loss_admission_digest", "validation evidence loss admission"),
        ("review_budget_admission_digest", "review budget admission"),
        ("adoption_proof_digest", "exact adoption proof"),
        ("adoption_authorization_digest", "exact adoption authorization"),
    ):
        _require_digest(source.get(field), label)
    for field, label in (
        ("loss_admission_id", "validation evidence loss admission identity"),
        ("review_budget_admission_id", "review budget admission identity"),
        ("adoption_authorization_id", "exact adoption authorization identity"),
    ):
        _require_string(source.get(field), label)
    _require_oid(enrollment.get("object_oid"), "adopted enrollment publication")
    _require_digest(
        enrollment.get("publication_digest"), "adopted enrollment publication"
    )
    _require_string(transition.get("event_id"), "adopted Ready transition")
    for field, label in (
        ("event_digest", "adopted Ready event"),
        ("predecessor_authority_digest", "adopted Ready predecessor"),
    ):
        _require_digest(transition.get(field), label)
    for field in ("predecessor_head_sha", "resulting_head_sha"):
        if _require_oid(transition.get(field), "adopted Ready transition head") != normalized[
            "prior_delivery_head_sha"
        ]:
            raise SecurityBlocker("adopted Ready transition changed the source head")
    normalized.update(
        source_authority_mode="EXACT_STATE_ADOPTION_V3",
        source_authority=copy.deepcopy(source),
        historical_companions=copy.deepcopy(companions),
    )
    return normalized


def normalize_ready_integration_evidence(
    value: Any,
    *,
    repository: str,
    reviewed_state: "StableFeedbackState",
    registry: dict[str, Any],
    validated_tree_sha: str,
) -> dict[str, Any]:
    """Normalize and admit one explicitly authorized Ready-head integration."""

    if not isinstance(value, dict):
        raise SecurityBlocker("Ready integration evidence is malformed or ambiguous")
    if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
        raise SecurityBlocker("Ready integration evidence contains secret-like text")
    schema_version = value.get("schema_version")
    expected_keys = (
        READY_INTEGRATION_V12_KEYS
        if schema_version == "1.2"
        else READY_INTEGRATION_KEYS
    )
    if set(value) != expected_keys:
        raise SecurityBlocker("Ready integration evidence is malformed or ambiguous")
    if schema_version not in {"1.1", "1.2"} or value.get("kind") != READY_INTEGRATION_KIND:
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
    reviewed_head = (
        prior_head
        if schema_version == "1.1"
        else _require_oid(value.get("reviewed_head_sha"), "integration reviewed head")
    )
    if reviewed_head != reviewed_state.head_sha:
        raise SecurityBlocker("integration reviewed head is stale or substituted")
    if (
        (schema_version == "1.1" and prior_head != reviewed_head)
        or (schema_version == "1.2" and prior_head == reviewed_head)
    ):
        raise SecurityBlocker("integration first parent is stale or substituted")
    prior_authority_digest = _require_digest(
        value.get("prior_authority_digest"), "prior Ready authority digest"
    )
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
        "schema_version": schema_version,
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
    if schema_version == "1.2":
        normalized["reviewed_head_sha"] = reviewed_head
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


def _exceptional_history(
    value: Any, kinds: frozenset[str], label: str
) -> list[dict[str, Any]]:
    """Normalize history shape while lifecycle_authority remains semantic owner."""

    if not isinstance(value, list) or not value:
        raise SecurityBlocker(f"{label} history is missing")
    normalized: list[dict[str, Any]] = []
    for sequence, item in enumerate(value, start=1):
        if (
            not isinstance(item, dict)
            or set(item)
            != {"sequence", "transition_kind", "event_authorization_digest"}
            or item.get("sequence") != sequence
            or item.get("transition_kind") not in kinds
        ):
            raise SecurityBlocker(f"{label} history is malformed")
        normalized.append(
            {
                "sequence": sequence,
                "transition_kind": item["transition_kind"],
                "event_authorization_digest": _require_digest(
                    item.get("event_authorization_digest"), f"{label} event"
                ),
            }
        )
    return normalized


def normalize_exceptional_continuation_evidence(
    value: Any,
    *,
    repository: str,
    reviewed_state: "StableFeedbackState",
    validated_tree_sha: str,
    eligibility_evidence: Any,
    reanchor_authority: Any = None,
) -> dict[str, Any]:
    """Normalize one typed source-changing continuation after Recovery."""

    reanchored = (
        isinstance(value, dict)
        and value.get("schema_version") == "1.1"
        and set(value) == EXCEPTIONAL_CONTINUATION_REANCHOR_KEYS
    )
    if not isinstance(value, dict) or (
        not reanchored and set(value) != EXCEPTIONAL_CONTINUATION_KEYS
    ):
        raise SecurityBlocker(
            "exceptional continuation evidence is malformed or ambiguous"
        )
    if any(SECRET_VALUE.search(item) for item in _all_strings(value)):
        raise SecurityBlocker(
            "exceptional continuation evidence contains secret-like text"
        )
    eligibility = normalize_resolution_eligibility_evidence(
        eligibility_evidence,
        repository=repository,
        reviewed_state=reviewed_state,
    )
    eligibility_digest = digest_json(eligibility)
    if (
        value.get("schema_version") != ("1.1" if reanchored else "1.0")
        or value.get("kind") != EXCEPTIONAL_CONTINUATION_KIND
        or value.get("repository") != repository
        or reviewed_state.repository != repository
        or value.get("pull_request_number") != reviewed_state.pull_request_number
        or reviewed_state.pr_state != "OPEN"
        or value.get("prior_ready_head_sha") != reviewed_state.head_sha
        or value.get("reviewed_state_digest") != reviewed_state.state_digest
        or value.get("reviewed_feedback_digest") != reviewed_state.feedback_digest
        or value.get("continuation_tree_sha") != validated_tree_sha
        or value.get("eligibility_evidence_digest") != eligibility_digest
    ):
        raise SecurityBlocker("exceptional continuation identity or evidence is stale")
    reanchor = None
    if reanchored:
        candidate = value.get("reanchor")
        if (
            not isinstance(candidate, dict)
            or set(candidate) != EXCEPTIONAL_CONTINUATION_REANCHOR_FIELDS
            or any(SECRET_VALUE.search(item) for item in _all_strings(candidate))
        ):
            raise SecurityBlocker(
                "exceptional continuation re-anchor binding is malformed"
            )
        reanchor = {
            "evidence_digest": _require_digest(
                candidate.get("evidence_digest"), "Continuation re-anchor evidence"
            ),
            "original_pull_request": _require_positive_integer(
                candidate.get("original_pull_request"), "original pull request"
            ),
            "replacement_pull_request": _require_positive_integer(
                candidate.get("replacement_pull_request"), "replacement pull request"
            ),
            "rejected_candidate_head_sha": _require_oid(
                candidate.get("rejected_candidate_head_sha"),
                "rejected candidate head",
            ),
            "rejected_candidate_tree_sha": _require_oid(
                candidate.get("rejected_candidate_tree_sha"),
                "rejected candidate tree",
            ),
            "rejected_validation_receipt_digest": _require_digest(
                candidate.get("rejected_validation_receipt_digest"),
                "rejected validation receipt",
            ),
            "rejected_final_attestation_digest": _require_digest(
                candidate.get("rejected_final_attestation_digest"),
                "rejected final attestation",
            ),
            "rejected_state_digest": _require_digest(
                candidate.get("rejected_state_digest"),
                "rejected Stable Feedback state",
            ),
            "replacement_state_digest": _require_digest(
                candidate.get("replacement_state_digest"),
                "replacement Stable Feedback state",
            ),
            "material_finding_ids": copy.deepcopy(
                candidate.get("material_finding_ids")
            ),
            "material_thread_ids": copy.deepcopy(
                candidate.get("material_thread_ids")
            ),
            "finding_source_digest": _require_digest(
                candidate.get("finding_source_digest"),
                "rejected finding sources",
            ),
        }
        finding_ids = reanchor["material_finding_ids"]
        diagnostic_thread_ids = reanchor["material_thread_ids"]
        if (
            reanchor["original_pull_request"]
            == reanchor["replacement_pull_request"]
            or reanchor["replacement_pull_request"]
            != reviewed_state.pull_request_number
            or reanchor["replacement_state_digest"] != reviewed_state.state_digest
            or not isinstance(finding_ids, list)
            or not finding_ids
            or len(finding_ids) != len(set(finding_ids))
            or any(
                not isinstance(identity, str) or not IDENTITY.fullmatch(identity)
                for identity in finding_ids
            )
            or not isinstance(diagnostic_thread_ids, list)
            or len(diagnostic_thread_ids) != len(set(diagnostic_thread_ids))
            or any(
                not isinstance(identity, str)
                or not re.fullmatch(r"PRRT_[A-Za-z0-9_-]+", identity)
                for identity in diagnostic_thread_ids
            )
            or eligibility.get("eligible_threads") != []
        ):
            raise SecurityBlocker(
                "exceptional continuation re-anchor identity is invalid or stale"
            )
        if reanchor_authority is not None:
            authority_binding = {
                field: copy.deepcopy(getattr(reanchor_authority, field, None))
                for field in EXCEPTIONAL_CONTINUATION_REANCHOR_FIELDS
            }
            authority_binding["material_finding_ids"] = list(
                authority_binding["material_finding_ids"] or []
            )
            authority_binding["material_thread_ids"] = list(
                authority_binding["material_thread_ids"] or []
            )
            if reanchor != authority_binding:
                raise SecurityBlocker(
                    "exceptional continuation re-anchor authority changed"
                )
        thread_ids = []
    else:
        finding_ids, thread_ids = continuation_material_finding_projection(
            reviewed_state, eligibility
        )
    if value.get("finding_ids") != finding_ids or value.get("thread_ids") != thread_ids:
        raise SecurityBlocker(
            "exceptional continuation findings differ from eligibility authority"
        )
    lifecycle = value.get("lifecycle")
    lifecycle_fields = {
        "unrestricted_reviews",
        "remediation_cycles",
        "cycle_3",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_recovery_count",
        "exceptional_recovery_history",
        "exceptional_continuation_predecessor_count",
        "exceptional_continuation_successor_count",
    }
    if not isinstance(lifecycle, dict) or set(lifecycle) != lifecycle_fields:
        raise SecurityBlocker("exceptional continuation lifecycle is malformed")
    expected_signer = value.get("expected_signer")
    if (
        not isinstance(expected_signer, dict)
        or set(expected_signer) != {"kind", "identity"}
        or expected_signer.get("kind")
        not in {"SSH_PRINCIPAL", "OPENPGP_FINGERPRINT"}
    ):
        raise SecurityBlocker("exceptional continuation signer is malformed")
    signer_identity = _require_string(
        expected_signer.get("identity"), "exceptional continuation signer"
    )
    if expected_signer["kind"] == "OPENPGP_FINGERPRINT" and not re.fullmatch(
        r"[0-9A-F]{40,64}", signer_identity
    ):
        raise SecurityBlocker("exceptional continuation OpenPGP signer is malformed")
    ready_history = _exceptional_history(
        lifecycle.get("ready_history"),
        frozenset({"DRAFT_TO_READY", "READY_TO_DRAFT"}),
        "Ready transition",
    )
    recovery_history = _exceptional_history(
        lifecycle.get("exceptional_recovery_history"),
        frozenset({"EXCEPTIONAL_RECOVERY"}),
        "Exceptional Recovery",
    )
    if (
        lifecycle.get("unrestricted_reviews") != 1
        or lifecycle.get("remediation_cycles") != 2
        or lifecycle.get("cycle_3") is not False
        or lifecycle.get("draft") is not False
        or lifecycle.get("ready") is not True
        or lifecycle.get("ready_transition_count")
        != sum(
            item["transition_kind"] == "DRAFT_TO_READY" for item in ready_history
        )
        or lifecycle.get("exceptional_recovery_count") != 1
        or len(recovery_history) != 1
        or lifecycle.get("exceptional_continuation_predecessor_count") != 0
        or lifecycle.get("exceptional_continuation_successor_count") != 1
    ):
        raise SecurityBlocker(
            "exceptional continuation would alter the finite lifecycle"
        )
    return {
        "schema_version": "1.1" if reanchored else "1.0",
        "kind": EXCEPTIONAL_CONTINUATION_KIND,
        "authorization_id": _require_string(
            value.get("authorization_id"),
            "exceptional continuation authorization",
        ),
        "repository": repository,
        "delivery_issue_number": _require_positive_integer(
            value.get("delivery_issue_number"),
            "exceptional continuation delivery issue",
        ),
        "pull_request_number": reviewed_state.pull_request_number,
        "prior_ready_head_sha": reviewed_state.head_sha,
        "prior_ready_tree_sha": _require_oid(
            value.get("prior_ready_tree_sha"), "prior Ready tree"
        ),
        "continuation_tree_sha": _require_oid(
            validated_tree_sha, "continuation tree"
        ),
        "reviewed_state_digest": reviewed_state.state_digest,
        "reviewed_feedback_digest": reviewed_state.feedback_digest,
        "eligibility_evidence_digest": eligibility_digest,
        "finding_ids": finding_ids,
        "thread_ids": thread_ids,
        "expected_signer": {
            "kind": expected_signer["kind"],
            "identity": signer_identity,
        },
        "lifecycle": {
            **{
                key: copy.deepcopy(lifecycle[key])
                for key in lifecycle_fields
                if key not in {"ready_history", "exceptional_recovery_history"}
            },
            "ready_history": ready_history,
            "exceptional_recovery_history": recovery_history,
        },
        **({"reanchor": reanchor} if reanchor is not None else {}),
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


@dataclass(frozen=True, slots=True)
class _VerifiedSuccessorClassificationSeal:
    provenance_digest: str


@dataclass(frozen=True)
class VerifiedSuccessorClassification:
    """Exact safe successor finding returned by maintained signature verification."""

    repository: str
    delivery_issue_number: int
    pull_request_number: int
    head_sha: str
    finding_id: str
    finding_evidence_digest: str
    thread_id: str | None
    top_level_comment_node_id: str | None
    finding_body_digest: str | None
    reply_count: int
    is_resolved: bool | None
    is_outdated: bool | None
    classification: str
    disposition: str
    technically_blocking: bool
    technical_blockers: tuple[str, ...]
    classification_evidence_digest: str
    source_bindings: tuple[tuple[str, str, str, str | None], ...]
    _verification_seal: object


@dataclass(frozen=True)
class VerifiedRejectedSuccessorFindings:
    """Material findings that made one exact successor unsafe to publish."""

    predecessor_state_digest: str
    rejected_state_digest: str
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    source_bindings: tuple[tuple[str, str, str, str | None], ...]
    classification_evidence_digests: tuple[str, ...]


def _seal_successor_classification(**values: Any) -> VerifiedSuccessorClassification:
    """Internal bridge from the maintained detached-signature verifier."""

    digest = values.get("classification_evidence_digest")
    return VerifiedSuccessorClassification(
        **values,
        _verification_seal=_VerifiedSuccessorClassificationSeal(digest),
    )


@dataclass(frozen=True, slots=True)
class _VerifiedValidationEvidenceSeal:
    """Carry canonical provenance that consumers independently re-verify."""

    provenance_json: str


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
    delivery_issue_number: int | None = None


def _validation_evidence_binding(value: VerifiedValidationEvidence) -> dict[str, Any]:
    return {
        "repository": value.repository,
        "delivery_issue_number": value.delivery_issue_number,
        "pull_request_number": value.pull_request_number,
        "head_sha": value.head_sha,
        "tree_sha": value.tree_sha,
        "validation_receipt_digest": value.validation_receipt_digest,
        "final_attestation_digest": value.final_attestation_digest,
        "source_validation_evidence_digest": value.source_validation_evidence_digest,
    }


@dataclass(frozen=True)
class AuthenticatedIntegrationCommit:
    """Exact commit and actual signer proven by the canonical signature verifier."""

    repository: str
    head_sha: str
    tree_sha: str
    parent_shas: tuple[str, ...]
    signer_kind: str
    signer_identity: str
    signature_fingerprint: str
    signature_classification: str
    signature_policy_digest: str
    authentication_digest: str


def _integration_commit_authentication_binding(
    value: AuthenticatedIntegrationCommit,
) -> dict[str, Any]:
    return {
        "repository": value.repository,
        "head_sha": value.head_sha,
        "tree_sha": value.tree_sha,
        "parent_shas": list(value.parent_shas),
        "signer_kind": value.signer_kind,
        "signer_identity": value.signer_identity,
        "signature_fingerprint": value.signature_fingerprint,
        "signature_classification": value.signature_classification,
        "signature_policy_digest": value.signature_policy_digest,
    }


def _actual_integration_signer(
    verification_output: str, expected_signer: dict[str, str]
) -> tuple[str, str]:
    if not isinstance(verification_output, str) or not isinstance(
        expected_signer, dict
    ):
        raise SecurityBlocker("integration commit signer evidence is malformed")
    kind = expected_signer.get("kind")
    identity = expected_signer.get("identity")
    if kind == "SSH_PRINCIPAL" and isinstance(identity, str):
        matches = re.findall(
            r'(?m)^Good "git" signature for ([^\s]+) with ', verification_output
        )
        actual_identity = matches[0] if len(matches) == 1 else None
    elif kind == "OPENPGP_FINGERPRINT" and isinstance(identity, str):
        status_lines = re.findall(
            r"(?m)^\[GNUPG:\] VALIDSIG ([^\r\n]+)$",
            verification_output.upper(),
        )
        fields = status_lines[0].split() if len(status_lines) == 1 else []
        if len(fields) not in {9, 10}:
            raise SecurityBlocker(
                "integration OpenPGP signer status is malformed or ambiguous"
            )
        signing_fingerprint = fields[0]
        primary_fingerprint = fields[9] if len(fields) == 10 else signing_fingerprint
        if not all(
            re.fullmatch(r"[0-9A-F]{40,64}", fingerprint)
            for fingerprint in {signing_fingerprint, primary_fingerprint}
        ):
            raise SecurityBlocker(
                "integration OpenPGP signer status is malformed or ambiguous"
            )
        actual_identity = primary_fingerprint
        identity = identity.upper()
    else:
        raise SecurityBlocker("integration expected signer is malformed")
    if actual_identity != identity:
        raise SecurityBlocker(
            "integration commit signer does not match the explicitly accepted identity"
        )
    return kind, actual_identity


def _actual_signature_fingerprint(
    verification_output: str, signer_kind: str
) -> str:
    if signer_kind == "SSH_PRINCIPAL":
        matches = re.findall(r"\b(SHA256:[A-Za-z0-9+/=]+)\b", verification_output)
        if len(set(matches)) == 1:
            return matches[0]
    elif signer_kind == "OPENPGP_FINGERPRINT":
        status_lines = re.findall(
            r"(?m)^\[GNUPG:\] VALIDSIG ([^\r\n]+)$",
            verification_output.upper(),
        )
        fields = status_lines[0].split() if len(status_lines) == 1 else []
        if fields and re.fullmatch(r"[0-9A-F]{40,64}", fields[0]):
            return fields[0]
    raise SecurityBlocker("integration commit signature fingerprint is unavailable")


def _run_integration_commit_git(
    repository_root: Path, arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    evidence = _load_evidence_helper()
    try:
        git_executable = evidence.resolve_trusted_executable("git")
        environment = evidence.command_environment("git")
    except evidence.CommandPolicyError as exc:
        raise RecoverableLocalError(
            "integration commit verification is unavailable"
        ) from exc
    try:
        return subprocess.run(
            [git_executable, *arguments],
            cwd=repository_root,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=EXTERNAL_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoverableLocalError(
            "integration commit verification is unavailable"
        ) from exc


def _repository_from_remote(value: str) -> str | None:
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        value.strip(),
    )
    return match.group(1) if match is not None else None


def _commit_topology(commit_object: str) -> tuple[str, tuple[str, ...]]:
    headers = commit_object.split("\n\n", 1)[0].splitlines()
    trees = [line[5:].lower() for line in headers if line.startswith("tree ")]
    parents = tuple(
        line[7:].lower() for line in headers if line.startswith("parent ")
    )
    if (
        len(trees) != 1
        or not OID.fullmatch(trees[0])
        or any(not OID.fullmatch(parent) for parent in parents)
    ):
        raise SecurityBlocker("integration commit topology is malformed")
    return trees[0], parents


def _authenticate_integration_commit(
    *,
    repository_root: Path | str,
    repository: str,
    head_sha: str,
    expected_signer: dict[str, str],
    signature_policy: dict[str, Any],
) -> AuthenticatedIntegrationCommit:
    """Authenticate the signed commit, its topology, signer, and trust context."""

    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise SecurityBlocker("integration commit repository identity is malformed")
    head = _require_oid(head_sha, "integration commit")
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RecoverableLocalError(
            "integration commit repository is unavailable"
        ) from exc
    if not root.is_dir():
        raise RecoverableLocalError("integration commit repository is unavailable")
    origin = _run_integration_commit_git(root, ["remote", "get-url", "origin"])
    if origin.returncode != 0 or _repository_from_remote(origin.stdout) != repository:
        raise SecurityBlocker("integration commit repository identity changed")
    commit_object = _run_integration_commit_git(root, ["cat-file", "commit", head])
    if commit_object.returncode != 0:
        raise SecurityBlocker("integration commit object is unavailable")
    tree_sha, parent_shas = _commit_topology(commit_object.stdout)
    verified_commit = _run_integration_commit_git(
        root, ["verify-commit", "--raw", head]
    )
    evidence = _load_evidence_helper()
    local_signature = evidence.interpret_local_signature(
        verified_commit.returncode,
        f"{verified_commit.stdout}\n{verified_commit.stderr}",
        signature_format_hint=(
            evidence._commit_signature_format(commit_object.stdout)
            if commit_object.returncode == 0
            else "unknown"
        ),
    )
    verified = verify_commit_signatures(
        [
            {
                "oid": head,
                "source": "USER",
                "local_signature": local_signature,
                "github_verification": {
                    "verified": False,
                    "reason": "not_required",
                },
            }
        ],
        {**signature_policy, "require_github_verified": False},
    )
    if len(verified) != 1 or verified[0]["oid"] != head:
        raise SecurityBlocker("integration commit signature identity changed")
    verification_output = f"{verified_commit.stdout}\n{verified_commit.stderr}"
    signer_kind, signer_identity = _actual_integration_signer(
        verification_output, expected_signer
    )
    expected_format = "ssh" if signer_kind == "SSH_PRINCIPAL" else "openpgp"
    if local_signature.get("format") != expected_format:
        raise SecurityBlocker("integration commit signer format does not match policy")
    fields = {
        "repository": repository,
        "head_sha": head,
        "tree_sha": tree_sha,
        "parent_shas": list(parent_shas),
        "signer_kind": signer_kind,
        "signer_identity": signer_identity,
        "signature_fingerprint": _actual_signature_fingerprint(
            verification_output, signer_kind
        ),
        "signature_classification": verified[0]["classification"],
        "signature_policy_digest": digest_json(signature_policy),
    }
    return AuthenticatedIntegrationCommit(
        **{**fields, "parent_shas": parent_shas},
        authentication_digest=digest_json(fields),
    )


def authenticate_integration_commit(
    *,
    repository_root: Path | str,
    repository: str,
    head_sha: str,
    expected_signer: dict[str, str],
    signature_policy: dict[str, Any],
) -> AuthenticatedIntegrationCommit:
    return _authenticate_integration_commit(
        repository_root=repository_root,
        repository=repository,
        head_sha=head_sha,
        expected_signer=expected_signer,
        signature_policy=signature_policy,
    )


def _authenticated_integration_commit_agrees(
    value: Any,
    *,
    repository: str | None = None,
    head_sha: str,
    tree_sha: str | None = None,
    parent_shas: list[str] | tuple[str, ...] | None = None,
    expected_signer: dict[str, str],
    signature_policy: dict[str, Any] | None = None,
) -> bool:
    try:
        if not isinstance(value, AuthenticatedIntegrationCommit):
            return False
        binding = _integration_commit_authentication_binding(value)
        if value.authentication_digest != digest_json(binding):
            return False
        expected_kind = (
            expected_signer.get("kind")
            if isinstance(expected_signer, dict)
            else None
        )
        expected_identity = (
            expected_signer.get("identity")
            if isinstance(expected_signer, dict)
            else None
        )
        if expected_kind == "OPENPGP_FINGERPRINT" and isinstance(
            expected_identity, str
        ):
            expected_identity = expected_identity.upper()
        return (
            value.head_sha == head_sha.lower()
            and value.signer_kind == expected_kind
            and value.signer_identity == expected_identity
            and (repository is None or value.repository == repository)
            and (tree_sha is None or value.tree_sha == tree_sha.lower())
            and (
                parent_shas is None
                or value.parent_shas
                == tuple(parent.lower() for parent in parent_shas)
            )
            and (
                signature_policy is None
                or value.signature_policy_digest == digest_json(signature_policy)
            )
        )
    except (AttributeError, KeyError, SecurityBlocker, TypeError, ValueError):
        return False


def _unregistered_validation_evidence(
    *,
    repository: str,
    pull_request_number: int,
    head_sha: str,
    tree_sha: str,
    validation_receipt_digest: str,
    final_attestation_digest: str,
    source_validation_evidence_digest: str,
    delivery_issue_number: int | None = None,
) -> VerifiedValidationEvidence:
    fields = {
        "repository": repository,
        "delivery_issue_number": delivery_issue_number,
        "pull_request_number": pull_request_number,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "validation_receipt_digest": validation_receipt_digest,
        "final_attestation_digest": final_attestation_digest,
        "source_validation_evidence_digest": source_validation_evidence_digest,
    }
    return VerifiedValidationEvidence(
        repository=repository,
        pull_request_number=pull_request_number,
        head_sha=head_sha,
        tree_sha=tree_sha,
        validation_receipt_digest=validation_receipt_digest,
        final_attestation_digest=final_attestation_digest,
        source_validation_evidence_digest=source_validation_evidence_digest,
        _verification_seal=None,
        delivery_issue_number=delivery_issue_number,
    )


def _seal_validation_evidence(
    value: VerifiedValidationEvidence, provenance: dict[str, Any]
) -> VerifiedValidationEvidence:
    seal = _VerifiedValidationEvidenceSeal(
        canonical_json_bytes(provenance).decode("utf-8")
    )
    return VerifiedValidationEvidence(
        **_validation_evidence_binding(value),
        _verification_seal=seal,
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


def _successor_source_inventory(
    state: StableFeedbackState,
) -> dict[tuple[str, str], tuple[str, str | None, dict[str, Any]]]:
    inventory: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ] = {}

    def add(
        kind: str,
        node_id: str,
        digest: str,
        thread_id: str | None,
        item: dict[str, Any],
    ) -> None:
        key = (kind, node_id)
        if key in inventory:
            raise SecurityBlocker("stable feedback repeats a successor source")
        inventory[key] = (digest, thread_id, item)

    for reaction in state.feedback["pull_request_reactions"]:
        add(
            "PULL_REQUEST_REACTION",
            reaction["mutation_id"],
            digest_json(reaction),
            None,
            reaction,
        )
    for review in state.feedback["reviews"]:
        add("REVIEW", review["node_id"], review["body_digest"], None, review)
        for reaction in review["reactions"]:
            add(
                "REVIEW_REACTION",
                reaction["mutation_id"],
                digest_json(reaction),
                None,
                reaction,
            )
    for comment in state.feedback["conversation_comments"]:
        add(
            "CONVERSATION_COMMENT",
            comment["node_id"],
            comment["body_digest"],
            None,
            comment,
        )
        for reaction in comment["reactions"]:
            add(
                "CONVERSATION_REACTION",
                reaction["mutation_id"],
                digest_json(reaction),
                None,
                reaction,
            )
    for thread in state.feedback["threads"]:
        for comment in thread["comments"]:
            add(
                "THREAD_COMMENT",
                comment["node_id"],
                comment["body_digest"],
                thread["node_id"],
                comment,
            )
            for reaction in comment["reactions"]:
                add(
                    "THREAD_COMMENT_REACTION",
                    reaction["mutation_id"],
                    digest_json(reaction),
                    thread["node_id"],
                    reaction,
                )
    return inventory


def _verify_successor_transport(
    value: Any,
    *,
    reviewed_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    current_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    resulting_head_sha: str,
    rejected_candidate: bool = False,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    if not isinstance(value, list):
        raise SecurityBlocker("successor provider transport evidence is malformed")
    admitted_additions: set[tuple[str, str]] = set()
    admitted_updates: set[tuple[str, str]] = set()
    roles: list[str] = []
    rejected_review_kinds: list[str] = []
    for transport in value:
        if not isinstance(transport, dict) or set(transport) != {
            "role",
            "kind",
            "node_id",
            "body",
        }:
            raise SecurityBlocker(
                "successor provider transport evidence is malformed"
            )
        role = transport.get("role")
        kind = transport.get("kind")
        node_id = transport.get("node_id")
        body = transport.get("body")
        if (
            role not in SUCCESSOR_TRANSPORT_ROLES
            or kind
            not in {"REVIEW", "CONVERSATION_COMMENT", "PULL_REQUEST_REACTION"}
            or not isinstance(node_id, str)
            or not IDENTITY.fullmatch(node_id)
            or (body is not None and not isinstance(body, str))
            or (isinstance(body, str) and len(body.encode("utf-8")) > 64 * 1024)
        ):
            raise SecurityBlocker(
                "successor provider transport evidence is malformed"
            )
        key = (kind, node_id)
        if key in admitted_additions or key in admitted_updates:
            raise SecurityBlocker(
                "successor provider transport evidence is duplicate or ambiguous"
            )
        observed = current_sources.get(key)
        if observed is None or observed[1] is not None:
            raise SecurityBlocker(
                "successor provider transport source is absent or ambiguous"
            )
        source_digest, _thread_id, source = observed
        if body is not None and digest_text(body) != source_digest:
            raise SecurityBlocker("successor provider transport body changed")
        actor = source.get("actor") if isinstance(source, dict) else None
        login = actor.get("login") if isinstance(actor, dict) else None
        if isinstance(login, str):
            login = re.sub(r"\[bot\]$", "", login.strip().lower())
        predecessor = reviewed_sources.get(key)

        if role == "CODEX_SUMMARY_UPDATE":
            if (
                kind != "CONVERSATION_COMMENT"
                or predecessor is None
                or body is None
                or login != CODEX_PROVIDER_LOGIN
            ):
                raise SecurityBlocker("Codex summary update is not authenticated")
            verify_codex_provider_summary(body, head_sha=resulting_head_sha)
            admitted_updates.add(key)
        elif role in {"CODEX_REVIEW_REQUEST", "CODEX_SECURITY_REVIEW_REQUEST"}:
            expected_body = (
                "@codex review"
                if role == "CODEX_REVIEW_REQUEST"
                else "@codex security review"
            )
            if (
                kind != "CONVERSATION_COMMENT"
                or predecessor is not None
                or body != expected_body
                or not isinstance(login, str)
                or login in {CODEX_PROVIDER_LOGIN, GITHUB_CODE_QUALITY_LOGIN}
            ):
                raise SecurityBlocker("Codex review request transport is invalid")
            admitted_additions.add(key)
        elif role in {
            "CODEX_CODE_REVIEW_RESULT",
            "CODEX_SECURITY_REVIEW_RESULT",
        }:
            no_finding_text = (
                "Codex Review: Didn't find any major issues."
                if role == "CODEX_CODE_REVIEW_RESULT"
                else "No security issues were found in this pull request."
            )
            reviewed_commit = f"**Reviewed commit:** `{resulting_head_sha[:10]}`"
            if (
                kind != "CONVERSATION_COMMENT"
                or predecessor is not None
                or body is None
                or no_finding_text not in body
                or reviewed_commit not in body
                or login != CODEX_PROVIDER_LOGIN
            ):
                raise SecurityBlocker("Codex review result transport is invalid")
            admitted_additions.add(key)
        elif role == "CODEX_REVIEW":
            if rejected_candidate:
                reviewed_commit = f"**Reviewed commit:** `{resulting_head_sha[:10]}`"
                review_kind = (
                    "SECURITY_REVIEW"
                    if isinstance(body, str)
                    and body.lstrip().startswith("### 🛡️ Codex Security Review")
                    else "CODE_REVIEW"
                    if isinstance(body, str)
                    and body.lstrip().startswith("### 💡 Codex Review")
                    else None
                )
                if (
                    kind != "REVIEW"
                    or predecessor is not None
                    or review_kind is None
                    or body.count(reviewed_commit) != 1
                    or login != CODEX_PROVIDER_LOGIN
                    or source.get("state") != "COMMENTED"
                    or source.get("commit_oid") != resulting_head_sha
                    or source_digest != digest_text(body)
                ):
                    raise SecurityBlocker(
                        "rejected Codex review transport is not head-bound"
                    )
                rejected_review_kinds.append(review_kind)
            elif (
                kind != "REVIEW"
                or predecessor is not None
                or body is not None
                or login != CODEX_PROVIDER_LOGIN
                or source.get("commit_oid") != resulting_head_sha
                or source_digest != digest_text("")
            ):
                raise SecurityBlocker("Codex review transport is not head-bound")
            admitted_additions.add(key)
        elif role == "CODEX_COMPLETION_REACTION":
            if (
                kind != "PULL_REQUEST_REACTION"
                or predecessor is not None
                or body is not None
                or login != CODEX_PROVIDER_LOGIN
                or source.get("content") != "THUMBS_UP"
            ):
                raise SecurityBlocker(
                    "Codex completion reaction transport is invalid"
                )
            admitted_additions.add(key)
        elif role == "GITHUB_CODE_QUALITY_REVIEW":
            if (
                kind != "REVIEW"
                or predecessor is not None
                or body is not None
                or login != GITHUB_CODE_QUALITY_LOGIN
                or source.get("commit_oid") != resulting_head_sha
                or source_digest != digest_text("")
            ):
                raise SecurityBlocker(
                    "GitHub Code Quality review transport is not head-bound"
                )
            admitted_additions.add(key)
        roles.append(role)

    codex_roles = [role for role in roles if role.startswith("CODEX_")]
    if rejected_candidate or codex_roles:
        required = (
            frozenset(
                {
                    "CODEX_SUMMARY_UPDATE",
                    "CODEX_REVIEW_REQUEST",
                    "CODEX_SECURITY_REVIEW_REQUEST",
                }
            )
            if rejected_candidate
            else REQUIRED_CODEX_SUCCESSOR_ROLES
        )
        rejected_results_complete = (
            roles.count("CODEX_CODE_REVIEW_RESULT")
            + rejected_review_kinds.count("CODE_REVIEW")
            == 1
            and roles.count("CODEX_SECURITY_REVIEW_RESULT")
            + rejected_review_kinds.count("SECURITY_REVIEW")
            == 1
        )
        if (
            not required.issubset(roles)
            or any(roles.count(role) != 1 for role in required)
            or (
                rejected_candidate
                and not rejected_results_complete
            )
        ):
            raise SecurityBlocker(
                "Codex provider acquisition transport is incomplete or ambiguous"
            )
    return admitted_additions, admitted_updates


def _verify_successor_findings(
    value: Any,
    *,
    reviewed_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    current_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    repository: str,
    pull_request_number: int,
    resulting_head_sha: str,
    current_threads: dict[str, dict[str, Any]],
) -> set[tuple[str, str]]:
    """Keep ordinary successor safety fail-closed for every material finding."""

    return _verify_successor_findings_with_policy(
        value,
        reviewed_sources=reviewed_sources,
        current_sources=current_sources,
        repository=repository,
        pull_request_number=pull_request_number,
        resulting_head_sha=resulting_head_sha,
        current_threads=current_threads,
        rejected_candidate=False,
    )


def _verify_rejected_successor_findings(
    value: Any,
    *,
    reviewed_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    current_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    repository: str,
    pull_request_number: int,
    resulting_head_sha: str,
    current_threads: dict[str, dict[str, Any]],
) -> set[tuple[str, str]]:
    """Admit only authenticated material findings for diagnostic re-anchoring."""

    return _verify_successor_findings_with_policy(
        value,
        reviewed_sources=reviewed_sources,
        current_sources=current_sources,
        repository=repository,
        pull_request_number=pull_request_number,
        resulting_head_sha=resulting_head_sha,
        current_threads=current_threads,
        rejected_candidate=True,
    )


def _verify_successor_findings_with_policy(
    value: Any,
    *,
    reviewed_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    current_sources: dict[
        tuple[str, str], tuple[str, str | None, dict[str, Any]]
    ],
    repository: str,
    pull_request_number: int,
    resulting_head_sha: str,
    current_threads: dict[str, dict[str, Any]],
    rejected_candidate: bool,
) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        raise SecurityBlocker("successor finding evidence is malformed")
    admitted: set[tuple[str, str]] = set()
    finding_ids: set[str] = set()
    for finding in value:
        if not isinstance(finding, dict) or set(finding) != {
            "sources",
            "classification_evidence",
        }:
            raise SecurityBlocker("successor finding evidence is malformed")
        verified_classification = finding.get("classification_evidence")
        if (
            not isinstance(verified_classification, VerifiedSuccessorClassification)
            or not isinstance(
                verified_classification._verification_seal,
                _VerifiedSuccessorClassificationSeal,
            )
            or verified_classification._verification_seal.provenance_digest
            != verified_classification.classification_evidence_digest
            or verified_classification.repository != repository
            or verified_classification.pull_request_number != pull_request_number
            or verified_classification.head_sha != resulting_head_sha
        ):
            raise SecurityBlocker(
                "successor finding classification is not authenticated"
            )
        finding_id = _require_string(
            verified_classification.finding_id, "successor finding identity"
        )
        if finding_id in finding_ids:
            raise SecurityBlocker("successor finding identity is repeated")
        finding_ids.add(finding_id)
        classification = verified_classification.classification
        disposition = verified_classification.disposition
        technically_blocking = verified_classification.technically_blocking
        if rejected_candidate:
            if (
                technically_blocking is not True
                or not verified_classification.technical_blockers
                or (classification, disposition)
                != ("IN_CONTRACT_DEFECT", "CANDIDATE_REJECTED_BEFORE_PUBLICATION")
                or not DIGEST.fullmatch(
                    verified_classification.classification_evidence_digest
                )
                or not DIGEST.fullmatch(
                    verified_classification.finding_evidence_digest
                )
            ):
                raise SecurityBlocker(
                    "rejected successor finding is not authenticated material evidence"
                )
        else:
            if technically_blocking is True:
                raise SecurityBlocker(
                    "material successor finding blocks continuation"
                )
            if (
                technically_blocking is not False
                or disposition not in CLASSIFICATION_DISPOSITIONS.get(
                    classification, frozenset()
                )
                or not DIGEST.fullmatch(
                    verified_classification.classification_evidence_digest
                )
                or not DIGEST.fullmatch(
                    verified_classification.finding_evidence_digest
                )
                or verified_classification.technical_blockers
            ):
                raise SecurityBlocker(
                    "successor finding lacks a complete safe classification"
                )
        thread_id = verified_classification.thread_id
        if thread_id is not None and (
            not isinstance(thread_id, str)
            or not re.fullmatch(r"PRRT_[A-Za-z0-9_-]+", thread_id)
        ):
            raise SecurityBlocker("successor finding thread identity is malformed")
        sources = finding.get("sources")
        if not isinstance(sources, list) or not sources:
            raise SecurityBlocker("successor finding sources are missing")
        signed_sources = {
            (kind, node_id): (digest, source_thread_id)
            for kind, node_id, digest, source_thread_id in verified_classification.source_bindings
        }
        if len(signed_sources) != len(verified_classification.source_bindings):
            raise SecurityBlocker("successor signed finding source is repeated")
        for source in sources:
            if not isinstance(source, dict) or set(source) != {
                "kind",
                "node_id",
                "digest",
            }:
                raise SecurityBlocker("successor finding source is malformed")
            key = (source.get("kind"), source.get("node_id"))
            observed = current_sources.get(key)
            signed = signed_sources.get(key)
            if (
                key in admitted
                or key in reviewed_sources
                or observed is None
                or signed is None
                or signed[0] != source.get("digest")
                or observed[:2] != signed
            ):
                raise SecurityBlocker(
                    "successor finding source is stale, repeated, or predecessor-owned"
                )
            admitted.add(key)
        if set(signed_sources) != {
            (source["kind"], source["node_id"]) for source in sources
        }:
            raise SecurityBlocker("successor signed finding sources are incomplete")
        if thread_id is None:
            if (
                verified_classification.top_level_comment_node_id is not None
                or verified_classification.finding_body_digest is not None
                or verified_classification.reply_count != 0
                or verified_classification.is_resolved is not None
                or verified_classification.is_outdated is not None
            ):
                raise SecurityBlocker(
                    "successor source-only classification is malformed"
                )
        else:
            top_level = current_sources.get(
                (
                    "THREAD_COMMENT",
                    verified_classification.top_level_comment_node_id,
                )
            )
            thread = current_threads.get(thread_id)
            if (
                verified_classification.is_resolved is not False
                or top_level is None
                or top_level[:2]
                != (verified_classification.finding_body_digest, thread_id)
                or not isinstance(thread, dict)
                or thread["is_resolved"] != verified_classification.is_resolved
                or thread["is_outdated"] != verified_classification.is_outdated
                or len(thread["comments"]) - 1
                != verified_classification.reply_count
            ):
                raise SecurityBlocker(
                    "successor finding classification does not bind the live finding"
                )
    return admitted


def _verify_predecessor_preservation(
    reviewed: StableFeedbackState,
    current: StableFeedbackState,
    *,
    authorized_thread_ids: set[str],
    admitted_updates: set[tuple[str, str]],
) -> None:
    for category, identity_key in (
        ("pull_request_reactions", "mutation_id"),
        ("reviews", "node_id"),
        ("conversation_comments", "node_id"),
    ):
        predecessor = {item[identity_key]: item for item in reviewed.feedback[category]}
        successor = {item[identity_key]: item for item in current.feedback[category]}
        for node_id, expected in predecessor.items():
            observed = successor.get(node_id)
            key = (
                "PULL_REQUEST_REACTION"
                if category == "pull_request_reactions"
                else "REVIEW"
                if category == "reviews"
                else "CONVERSATION_COMMENT",
                node_id,
            )
            if key in admitted_updates:
                comparable = copy.deepcopy(observed)
                if isinstance(comparable, dict):
                    comparable["body_digest"] = expected["body_digest"]
                    comparable["updated_at"] = expected["updated_at"]
                if comparable != expected:
                    raise SecurityBlocker(
                        "provider summary update altered predecessor authority"
                    )
            elif observed != expected:
                if (
                    category not in {"reviews", "conversation_comments"}
                    or not isinstance(observed, dict)
                ):
                    raise SecurityBlocker(
                        "successor removed or changed predecessor feedback"
                    )
                expected_reactions = {
                    item["mutation_id"]: item for item in expected["reactions"]
                }
                observed_reactions = {
                    item["mutation_id"]: item for item in observed["reactions"]
                }
                if any(
                    observed_reactions.get(reaction_id) != reaction
                    for reaction_id, reaction in expected_reactions.items()
                ):
                    raise SecurityBlocker("successor changed a predecessor reaction")
                comparable = copy.deepcopy(observed)
                comparable["reactions"] = expected["reactions"]
                if comparable != expected:
                    raise SecurityBlocker(
                        "successor removed or changed predecessor feedback"
                    )

    predecessor_threads = {
        item["node_id"]: item for item in reviewed.feedback["threads"]
    }
    successor_threads = {
        item["node_id"]: item for item in current.feedback["threads"]
    }
    for thread_id, expected_thread in predecessor_threads.items():
        observed_thread = successor_threads.get(thread_id)
        if not isinstance(observed_thread, dict):
            raise SecurityBlocker("successor removed a predecessor thread")
        expected_comments = {
            item["node_id"]: item for item in expected_thread["comments"]
        }
        observed_comments = {
            item["node_id"]: item for item in observed_thread["comments"]
        }
        for comment_id, expected_comment in expected_comments.items():
            observed_comment = observed_comments.get(comment_id)
            if not isinstance(observed_comment, dict):
                raise SecurityBlocker("successor removed a predecessor reply")
            expected_reactions = {
                item["mutation_id"]: item for item in expected_comment["reactions"]
            }
            observed_reactions = {
                item["mutation_id"]: item for item in observed_comment["reactions"]
            }
            if any(
                observed_reactions.get(reaction_id) != reaction
                for reaction_id, reaction in expected_reactions.items()
            ):
                raise SecurityBlocker("successor changed a predecessor reaction")
            comparable = copy.deepcopy(observed_comment)
            comparable["reactions"] = expected_comment["reactions"]
            if comparable != expected_comment:
                raise SecurityBlocker("successor changed a predecessor comment")
        is_resolved = observed_thread["is_resolved"]
        if (
            expected_thread["is_resolved"] is False
            and is_resolved is True
            and thread_id in authorized_thread_ids
        ):
            is_resolved = False
        is_outdated = observed_thread["is_outdated"]
        if expected_thread["is_outdated"] is False and is_outdated is True:
            is_outdated = False
        if (
            is_resolved != expected_thread["is_resolved"]
            or is_outdated != expected_thread["is_outdated"]
        ):
            raise SecurityBlocker("successor changed predecessor thread state")


def _verify_authenticated_feedback_growth(
    reviewed: StableFeedbackState,
    current: StableFeedbackState,
    *,
    resulting_head_sha: str,
    authorized_thread_ids: set[str],
    successor_evidence: Any,
    rejected_candidate: bool = False,
) -> None:
    expected_keys = {
        "schema_version",
        "repository",
        "pull_request_number",
        "predecessor_state_digest",
        "resulting_head_sha",
        "resulting_state_digest",
        "provider_transport",
        "successor_findings",
    }
    if (
        not isinstance(successor_evidence, dict)
        or set(successor_evidence) != expected_keys
        or any(SECRET_VALUE.search(item) for item in _all_strings(successor_evidence))
        or successor_evidence.get("schema_version")
        != ("1.1" if rejected_candidate else "1.0")
        or successor_evidence.get("repository") != reviewed.repository
        or successor_evidence.get("pull_request_number")
        != reviewed.pull_request_number
        or successor_evidence.get("predecessor_state_digest")
        != reviewed.state_digest
        or successor_evidence.get("resulting_head_sha") != resulting_head_sha
        or successor_evidence.get("resulting_state_digest") != current.state_digest
    ):
        raise SecurityBlocker("successor safety evidence is invalid or stale")
    reviewed_sources = _successor_source_inventory(reviewed)
    current_sources = _successor_source_inventory(current)
    transport_additions, transport_updates = _verify_successor_transport(
        successor_evidence["provider_transport"],
        reviewed_sources=reviewed_sources,
        current_sources=current_sources,
        resulting_head_sha=resulting_head_sha,
        rejected_candidate=rejected_candidate,
    )
    finding_verifier = (
        _verify_rejected_successor_findings
        if rejected_candidate
        else _verify_successor_findings
    )
    finding_additions = finding_verifier(
        successor_evidence["successor_findings"],
        reviewed_sources=reviewed_sources,
        current_sources=current_sources,
        repository=reviewed.repository,
        pull_request_number=reviewed.pull_request_number,
        resulting_head_sha=resulting_head_sha,
        current_threads={
            item["node_id"]: item for item in current.feedback["threads"]
        },
    )
    if transport_additions & finding_additions:
        raise SecurityBlocker("successor feedback has ambiguous authority")
    expected_additions = set(current_sources) - set(reviewed_sources)
    if expected_additions != transport_additions | finding_additions:
        raise SecurityBlocker(
            "successor feedback contains an unauthenticated addition"
        )
    _verify_predecessor_preservation(
        reviewed,
        current,
        authorized_thread_ids=authorized_thread_ids,
        admitted_updates=transport_updates,
    )

    predecessor_thread_ids = {
        item["node_id"] for item in reviewed.feedback["threads"]
    }
    current_thread_ids = {item["node_id"] for item in current.feedback["threads"]}
    finding_thread_ids = {
        item["classification_evidence"].thread_id
        for item in successor_evidence["successor_findings"]
        if isinstance(item, dict)
        and isinstance(
            item.get("classification_evidence"), VerifiedSuccessorClassification
        )
        and item["classification_evidence"].thread_id is not None
    }
    if current_thread_ids - predecessor_thread_ids != finding_thread_ids - predecessor_thread_ids:
        raise SecurityBlocker(
            "successor thread lacks complete classification authority"
        )


def verify_stable_feedback_successor(
    reviewed: StableFeedbackState,
    current: StableFeedbackState,
    *,
    resulting_head_sha: str,
    authorized_thread_ids: Iterable[str],
    successor_safety_evidence: Any = None,
) -> None:
    """Authenticate predecessor feedback after one exact source-head advance."""

    resulting_head_sha = _require_oid(resulting_head_sha, "resulting feedback head")
    if (
        not isinstance(authorized_thread_ids, (list, tuple))
        or not authorized_thread_ids
        or any(
            not isinstance(item, str)
            or not re.fullmatch(r"PRRT_[A-Za-z0-9_-]+", item)
            for item in authorized_thread_ids
        )
        or len(authorized_thread_ids) != len(set(authorized_thread_ids))
    ):
        raise SecurityBlocker("authorized continuation threads are malformed")
    authorized = set(authorized_thread_ids)
    if (
        not isinstance(reviewed, StableFeedbackState)
        or not isinstance(current, StableFeedbackState)
        or current.repository != reviewed.repository
        or current.pull_request_number != reviewed.pull_request_number
        or current.pr_state != "OPEN"
        or current.head_sha != resulting_head_sha
        or current.base_ref != reviewed.base_ref
        or current.base_sha != reviewed.base_sha
    ):
        raise SecurityBlocker(
            "current stable feedback does not identify the exact source successor"
        )
    normalized = copy.deepcopy(current.feedback)
    reviewed_threads = {
        item["node_id"]: item for item in reviewed.feedback["threads"]
    }
    for thread in normalized["threads"]:
        expected = reviewed_threads.get(thread["node_id"])
        if (
            expected is not None
            and expected["is_resolved"] is False
            and thread["is_resolved"] is True
            and thread["node_id"] in authorized
        ):
            thread["is_resolved"] = False
        if (
            expected is not None
            and expected["is_outdated"] is False
            and thread["is_outdated"] is True
        ):
            thread["is_outdated"] = False
    if digest_json(normalized) == reviewed.feedback_digest:
        return
    if successor_safety_evidence is None:
        raise SecurityBlocker(
            "current stable feedback differs from the reviewed predecessor"
        )
    _verify_authenticated_feedback_growth(
        reviewed,
        current,
        resulting_head_sha=resulting_head_sha,
        authorized_thread_ids=authorized,
        successor_evidence=successor_safety_evidence,
    )


def verify_reanchored_stable_feedback_successor(
    reviewed: StableFeedbackState,
    current: StableFeedbackState,
    *,
    resulting_head_sha: str,
    successor_safety_evidence: Any,
) -> None:
    """Require fresh exact-head providers for a re-anchored corrected successor."""

    resulting_head_sha = _require_oid(resulting_head_sha, "resulting feedback head")
    if (
        not isinstance(reviewed, StableFeedbackState)
        or not isinstance(current, StableFeedbackState)
        or current.repository != reviewed.repository
        or current.pull_request_number != reviewed.pull_request_number
        or reviewed.pr_state != "OPEN"
        or current.pr_state != "OPEN"
        or reviewed.head_sha == current.head_sha
        or current.head_sha != resulting_head_sha
        or current.base_ref != reviewed.base_ref
        or current.base_sha != reviewed.base_sha
        or not isinstance(successor_safety_evidence, dict)
    ):
        raise SecurityBlocker(
            "corrected successor feedback does not preserve replacement identity"
        )
    transport = successor_safety_evidence.get("provider_transport")
    roles = {
        item.get("role")
        for item in transport
        if isinstance(item, dict)
    } if isinstance(transport, list) else set()
    if not REQUIRED_CODEX_SUCCESSOR_ROLES.issubset(roles):
        raise SecurityBlocker(
            "corrected successor exact-head providers are incomplete"
        )
    _verify_authenticated_feedback_growth(
        reviewed,
        current,
        resulting_head_sha=resulting_head_sha,
        authorized_thread_ids=set(),
        successor_evidence=successor_safety_evidence,
    )


def verify_rejected_stable_feedback_successor(
    reviewed: StableFeedbackState,
    rejected: StableFeedbackState,
    *,
    resulting_head_sha: str,
    rejected_successor_evidence: Any,
) -> VerifiedRejectedSuccessorFindings:
    """Authenticate material findings on one immutable unpublished successor."""

    resulting_head_sha = _require_oid(
        resulting_head_sha, "rejected successor feedback head"
    )
    if (
        not isinstance(reviewed, StableFeedbackState)
        or not isinstance(rejected, StableFeedbackState)
        or not isinstance(rejected_successor_evidence, dict)
        or rejected.repository != reviewed.repository
        or rejected.pull_request_number != reviewed.pull_request_number
        or reviewed.pr_state != "OPEN"
        or rejected.pr_state != "OPEN"
        or rejected.head_sha != resulting_head_sha
        or rejected.head_sha == reviewed.head_sha
        or rejected.base_ref != reviewed.base_ref
        or rejected.base_sha != reviewed.base_sha
    ):
        raise SecurityBlocker(
            "rejected stable feedback does not identify the exact successor"
        )
    _verify_authenticated_feedback_growth(
        reviewed,
        rejected,
        resulting_head_sha=resulting_head_sha,
        authorized_thread_ids=set(),
        successor_evidence=rejected_successor_evidence,
        rejected_candidate=True,
    )
    findings = rejected_successor_evidence["successor_findings"]
    classifications = [item["classification_evidence"] for item in findings]
    finding_ids = tuple(sorted(item.finding_id for item in classifications))
    if not finding_ids or len(finding_ids) != len(set(finding_ids)):
        raise SecurityBlocker("rejected successor material findings are missing")
    thread_ids = tuple(
        sorted(
            item.thread_id
            for item in classifications
            if item.thread_id is not None
        )
    )
    source_bindings = tuple(
        sorted(
            source
            for item in classifications
            for source in item.source_bindings
        )
    )
    if len(source_bindings) != len(set(source_bindings)):
        raise SecurityBlocker("rejected successor finding sources are repeated")
    return VerifiedRejectedSuccessorFindings(
        predecessor_state_digest=reviewed.state_digest,
        rejected_state_digest=rejected.state_digest,
        finding_ids=finding_ids,
        thread_ids=thread_ids,
        source_bindings=source_bindings,
        classification_evidence_digests=tuple(
            sorted(item.classification_evidence_digest for item in classifications)
        ),
    )


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


def continuation_material_finding_projection(
    reviewed_state: StableFeedbackState,
    eligibility: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Derive only provider-observed material Continuation finding identities."""

    eligible_threads = eligibility.get("eligible_threads")
    if not isinstance(eligible_threads, list) or not eligible_threads:
        raise SecurityBlocker(
            "exceptional continuation requires material corrected findings"
        )
    reviewed_threads = {
        item["node_id"]: item for item in reviewed_state.feedback["threads"]
    }
    finding_ids: list[str] = []
    thread_ids: list[str] = []
    for item in eligible_threads:
        thread = reviewed_threads.get(item["thread_id"])
        observed_comment_ids = (
            {comment["node_id"] for comment in thread["comments"]}
            if isinstance(thread, dict)
            else set()
        )
        if (
            item["classification"] != "VALID_ACTIONABLE"
            or item["disposition"] != "CORRECTED_AND_VERIFIED"
            or item["follow_up"] is not None
            or not set(item["finding_ids"]).issubset(observed_comment_ids)
        ):
            raise SecurityBlocker(
                "exceptional continuation finding lacks stable feedback authority"
            )
        finding_ids.extend(item["finding_ids"])
        thread_ids.append(item["thread_id"])
    finding_ids.sort()
    thread_ids.sort()
    if len(finding_ids) != len(set(finding_ids)):
        raise SecurityBlocker(
            "exceptional continuation finding identities are repeated"
        )
    return finding_ids, thread_ids


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
    exceptional_continuation_evidence_digest: str | None = None,
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
    if exceptional_continuation_evidence_digest is not None:
        fields["exceptional_continuation_evidence_digest"] = _require_digest(
            exceptional_continuation_evidence_digest,
            "exceptional continuation evidence digest",
        )
    if (
        exceptional_recovery_evidence_digest is not None
        and exceptional_continuation_evidence_digest is not None
    ):
        raise SecurityBlocker(
            "Recovery and Continuation evidence kinds are mutually exclusive"
        )
    return {**fields, "receipt_digest": digest_json(fields)}


def _create_validation_attestation(
    *,
    repository: str,
    head_sha: str,
    receipt_head_sha: str,
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
        head_sha=receipt_head_sha,
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
        exceptional_continuation_evidence_digest=validation_receipt.get(
            "exceptional_continuation_evidence_digest"
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
    if "exceptional_continuation_evidence_digest" in validation_receipt:
        fields["exceptional_continuation_evidence_digest"] = validation_receipt[
            "exceptional_continuation_evidence_digest"
        ]
    return {**fields, "attestation_digest": digest_json(fields)}


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
    """Assemble ordinary validation evidence at the reviewed head."""

    return _create_validation_attestation(
        repository=repository,
        head_sha=head_sha,
        receipt_head_sha=reviewed_state.head_sha,
        registry=registry,
        command_set=command_set,
        successful_result=successful_result,
        reviewed_state=reviewed_state,
        validation_receipt=validation_receipt,
    )


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
    if "exceptional_continuation_evidence_digest" in validation_receipt:
        raise SecurityBlocker(
            "Ready integration cannot be combined with exceptional continuation"
        )

    normalized = normalize_ready_integration_evidence(
        integration_evidence,
        repository=repository,
        reviewed_state=reviewed_state,
        registry=registry,
        validated_tree_sha=validation_receipt.get("validated_tree_sha"),
    )
    ordinary = _create_validation_attestation(
        repository=repository,
        head_sha=head_sha,
        receipt_head_sha=normalized["prior_delivery_head_sha"],
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed_state,
        validation_receipt=validation_receipt,
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
    repository_root: Path | str,
    signature_policy: dict[str, Any],
) -> VerifiedValidationEvidence:
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
    return verify_ready_integration_attestation(
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
        repository_root=repository_root,
        signature_policy=signature_policy,
    )


def _verify_ready_integration_attestation_unsealed(
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
    repository_root: Path | str,
    signature_policy: dict[str, Any],
) -> VerifiedValidationEvidence:
    reviewed_state = _require_reviewed_state_identity(repository, reviewed_state)
    normalized = normalize_ready_integration_evidence(
        integration_evidence,
        repository=repository,
        reviewed_state=reviewed_state,
        registry=registry,
        validated_tree_sha=commit_tree_sha,
    )
    if (
        not isinstance(signature_policy, dict)
        or signature_policy != registry.get("signature_policy")
    ):
        raise SecurityBlocker("integration signature policy context changed")
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
    source_binding = {
        "repository": normalized["repository"],
        "delivery_issue_number": normalized["delivery_issue_number"],
        "pull_request_number": normalized["pull_request_number"],
        "head_sha": head_sha,
        "tree_sha": normalized["validated_tree_sha"],
        "ordered_parent_shas": normalized["ordered_parent_shas"],
        "current_main": normalized["target_base"],
        "validation_receipt_digest": validation_receipt["receipt_digest"],
        "final_attestation_digest": expected["attestation_digest"],
        "integration_evidence": normalized,
        "reviewed_state_digest": reviewed_state.state_digest,
        "reviewed_feedback_digest": reviewed_state.feedback_digest,
        "expected_signer": normalized["expected_signer"],
        "evidence_schema_version": normalized["schema_version"],
        "evidence_kind": normalized["kind"],
        "attestation_schema_version": expected["schema_version"],
        "attestation_kind": expected["kind"],
    }
    authenticated_integration_commit = authenticate_integration_commit(
        repository_root=repository_root,
        repository=repository,
        head_sha=head_sha,
        expected_signer=normalized["expected_signer"],
        signature_policy=signature_policy,
    )
    if not _authenticated_integration_commit_agrees(
        authenticated_integration_commit,
        repository=repository,
        head_sha=head_sha,
        tree_sha=commit_tree_sha,
        parent_shas=commit_parent_shas,
        expected_signer=normalized["expected_signer"],
        signature_policy=signature_policy,
    ):
        raise SecurityBlocker("authenticated integration commit is required")
    return _unregistered_validation_evidence(
        repository=normalized["repository"],
        delivery_issue_number=normalized["delivery_issue_number"],
        pull_request_number=normalized["pull_request_number"],
        head_sha=head_sha,
        tree_sha=normalized["validated_tree_sha"],
        validation_receipt_digest=validation_receipt["receipt_digest"],
        final_attestation_digest=expected["attestation_digest"],
        source_validation_evidence_digest=digest_json(source_binding),
    )


def _verify_validation_attestation_unsealed(
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
    delivery_issue_number: int | None = None,
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
        exceptional_continuation_evidence_digest=attestation.get(
            "exceptional_continuation_evidence_digest"
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
    if delivery_issue_number is not None:
        if (
            not isinstance(delivery_issue_number, int)
            or isinstance(delivery_issue_number, bool)
            or delivery_issue_number <= 0
        ):
            raise SecurityBlocker("delivery issue identity is invalid")
        source_binding["delivery_issue_number"] = delivery_issue_number
    return _unregistered_validation_evidence(
        repository=repository,
        delivery_issue_number=delivery_issue_number,
        pull_request_number=reviewed_pull_request,
        head_sha=head_sha,
        tree_sha=commit_tree_sha,
        validation_receipt_digest=receipt["receipt_digest"],
        final_attestation_digest=expected["attestation_digest"],
        source_validation_evidence_digest=digest_json(source_binding),
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
    repository_root: Path | str,
    signature_policy: dict[str, Any],
) -> VerifiedValidationEvidence:
    result = _verify_ready_integration_attestation_unsealed(
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
        repository_root=repository_root,
        signature_policy=signature_policy,
    )
    provenance = {
        "kind": "READY_INTEGRATION",
        "attestation": copy.deepcopy(attestation),
        "repository": repository,
        "head_sha": head_sha,
        "registry": copy.deepcopy(registry),
        "command_set": copy.deepcopy(command_set),
        "reviewed_state": reviewed_state.to_dict(),
        "validation_receipt": copy.deepcopy(validation_receipt),
        "integration_evidence": copy.deepcopy(integration_evidence),
        "commit_parent_shas": list(commit_parent_shas),
        "commit_tree_sha": commit_tree_sha,
        "commit_validation_receipt_digest": commit_validation_receipt_digest,
        "commit_integration_evidence_digest": commit_integration_evidence_digest,
        "repository_root": str(Path(repository_root).resolve()),
        "signature_policy": copy.deepcopy(signature_policy),
    }
    return _seal_validation_evidence(result, provenance)


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
    delivery_issue_number: int | None = None,
) -> VerifiedValidationEvidence:
    result = _verify_validation_attestation_unsealed(
        attestation,
        repository=repository,
        head_sha=head_sha,
        registry=registry,
        command_set=command_set,
        reviewed_state=reviewed_state,
        commit_parent_sha=commit_parent_sha,
        commit_tree_sha=commit_tree_sha,
        commit_validation_receipt_digest=commit_validation_receipt_digest,
        delivery_issue_number=delivery_issue_number,
    )
    provenance = {
        "kind": "ORDINARY",
        "attestation": copy.deepcopy(attestation),
        "repository": repository,
        "head_sha": head_sha,
        "registry": copy.deepcopy(registry),
        "command_set": copy.deepcopy(command_set),
        "reviewed_state": reviewed_state.to_dict(),
        "commit_parent_sha": commit_parent_sha,
        "commit_tree_sha": commit_tree_sha,
        "commit_validation_receipt_digest": commit_validation_receipt_digest,
        "delivery_issue_number": delivery_issue_number,
    }
    return _seal_validation_evidence(result, provenance)


def is_verified_validation_evidence(value: Any) -> bool:
    """Re-verify canonical provenance instead of trusting caller-held authority."""

    try:
        if not isinstance(value, VerifiedValidationEvidence) or not isinstance(
            value._verification_seal, _VerifiedValidationEvidenceSeal
        ):
            return False
        raw = value._verification_seal.provenance_json
        provenance = json.loads(raw)
        if (
            not isinstance(provenance, dict)
            or canonical_json_bytes(provenance).decode("utf-8") != raw
        ):
            return False
        reviewed_state = StableFeedbackState.from_payload(
            provenance["reviewed_state"]
        )
        kind = provenance.get("kind")
        if kind == "ORDINARY":
            verified = _verify_validation_attestation_unsealed(
                provenance["attestation"],
                repository=provenance["repository"],
                head_sha=provenance["head_sha"],
                registry=provenance["registry"],
                command_set=provenance["command_set"],
                reviewed_state=reviewed_state,
                commit_parent_sha=provenance["commit_parent_sha"],
                commit_tree_sha=provenance["commit_tree_sha"],
                commit_validation_receipt_digest=provenance[
                    "commit_validation_receipt_digest"
                ],
                delivery_issue_number=provenance.get("delivery_issue_number"),
            )
        elif kind == "READY_INTEGRATION":
            verified = _verify_ready_integration_attestation_unsealed(
                provenance["attestation"],
                repository=provenance["repository"],
                head_sha=provenance["head_sha"],
                registry=provenance["registry"],
                command_set=provenance["command_set"],
                reviewed_state=reviewed_state,
                validation_receipt=provenance["validation_receipt"],
                integration_evidence=provenance["integration_evidence"],
                commit_parent_shas=provenance["commit_parent_shas"],
                commit_tree_sha=provenance["commit_tree_sha"],
                commit_validation_receipt_digest=provenance[
                    "commit_validation_receipt_digest"
                ],
                commit_integration_evidence_digest=provenance[
                    "commit_integration_evidence_digest"
                ],
                repository_root=provenance["repository_root"],
                signature_policy=provenance["signature_policy"],
            )
        else:
            return False
        return _validation_evidence_binding(verified) == _validation_evidence_binding(
            value
        )
    except (
        AttributeError,
        KeyError,
        OSError,
        RecoverableLocalError,
        SecurityBlocker,
        TypeError,
        ValueError,
    ):
        return False


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
    *,
    include_resolved: bool = False,
    include_resolved_threads: bool | None = None,
) -> dict[tuple[str, str], tuple[str, str | None]]:
    if include_resolved_threads is not None:
        if include_resolved is not False or not isinstance(
            include_resolved_threads, bool
        ):
            raise SecurityBlocker(
                "resolved-feedback selection is malformed or ambiguous"
            )
        include_resolved = include_resolved_threads
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
        if thread["is_resolved"] is True and not include_resolved:
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


def derive_ready_source_recovery_safety_facts(
    *,
    tooling_authority_main: str,
    repository: str,
    pull_request_number: int,
    head_sha: str,
    tree_sha: str,
    parent_shas: list[str] | tuple[str, ...],
    expected_base_ref: str,
    expected_base_sha: str,
    reviewed_state: StableFeedbackState,
    review_decision: str,
    feedback_findings: Any,
    fresh_validation_receipt: Any,
    registry: dict[str, Any],
    command_set: list[dict[str, Any]],
    approval_required: bool = False,
    current_safety_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive canonical unsigned facts; this result carries no authority."""

    policy_head = _require_oid(tooling_authority_main, "recovery tooling authority")
    reviewed = _require_reviewed_state_identity(repository, reviewed_state)
    pr = _require_positive_integer(
        pull_request_number, "Ready-source recovery pull request"
    )
    head = _require_oid(head_sha, "Ready-source recovery head")
    tree = _require_oid(tree_sha, "Ready-source recovery tree")
    parents = tuple(
        _require_oid(item, "Ready-source recovery parent") for item in parent_shas
    ) if isinstance(parent_shas, (list, tuple)) else ()
    if len(parents) != 1:
        raise SecurityBlocker(
            "Ready-source recovery requires the exact sole-parent delivery topology"
        )
    base_ref = _require_string(
        expected_base_ref, "Ready-source recovery target base"
    )
    base_sha = _require_oid(
        expected_base_sha, "Ready-source recovery target base SHA"
    )
    if (
        reviewed.pull_request_number != pr
        or reviewed.head_sha != head
        or reviewed.base_ref != base_ref
        or reviewed.base_sha != base_sha
        or reviewed.pr_state != "OPEN"
    ):
        raise SecurityBlocker(
            "Ready-source recovery reviewed delivery identity changed"
        )
    if not isinstance(approval_required, bool):
        raise SecurityBlocker(
            "Ready-source recovery approval policy is malformed"
        )
    if (
        review_decision == "REVIEW_REQUIRED"
        or review_decision not in {"NONE", "APPROVED"}
        or (review_decision == "NONE" and approval_required)
    ):
        raise SecurityBlocker(
            "Ready-source recovery has a blocking or ambiguous review decision"
        )
    if not isinstance(feedback_findings, list):
        raise SecurityBlocker("Ready-source recovery feedback assessment is missing")
    expected_sources = _classified_feedback_sources(
        reviewed, include_resolved=True
    )
    review_threads = {
        item["node_id"]
        for item in reviewed.feedback["threads"]
    }
    normalized_findings: list[dict[str, Any]] = []
    classified_sources: set[tuple[str, str]] = set()
    finding_ids: set[str] = set()
    for item in feedback_findings:
        fields = {
            "finding_id", "thread_id", "sources", "classification",
            "disposition", "evidence_digest", "technically_blocking",
        }
        if not isinstance(item, dict) or set(item) != fields:
            raise SecurityBlocker(
                "Ready-source recovery feedback finding is malformed"
            )
        finding_id = _require_string(
            item["finding_id"], "Ready-source recovery finding identity"
        )
        if finding_id in finding_ids:
            raise SecurityBlocker(
                "Ready-source recovery repeats a feedback finding"
            )
        finding_ids.add(finding_id)
        classification = item["classification"]
        disposition = item["disposition"]
        if (
            classification not in CLASSIFICATION_DISPOSITIONS
            or disposition not in CLASSIFICATION_DISPOSITIONS[classification]
            or item["technically_blocking"] is not False
        ):
            raise SecurityBlocker(
                "Ready-source recovery feedback is technically blocking or unclassified"
            )
        thread_id = item["thread_id"]
        if thread_id is not None:
            thread_id = _require_string(
                thread_id, "Ready-source recovery thread identity"
            )
            if thread_id not in review_threads:
                raise SecurityBlocker(
                    "Ready-source recovery finding thread identity changed"
                )
        sources = item["sources"]
        if not isinstance(sources, list) or not sources:
            raise SecurityBlocker(
                "Ready-source recovery finding requires feedback sources"
            )
        normalized_sources: list[dict[str, str]] = []
        for source in sources:
            if not isinstance(source, dict) or set(source) != {
                "kind", "node_id", "digest"
            }:
                raise SecurityBlocker(
                    "Ready-source recovery feedback source is malformed"
                )
            kind = source["kind"]
            node_id = _require_string(
                source["node_id"], "Ready-source recovery feedback source identity"
            )
            digest = _require_digest(
                source["digest"], "Ready-source recovery feedback source"
            )
            key = (kind, node_id)
            if (
                kind not in SOURCE_KINDS
                or key in classified_sources
                or expected_sources.get(key) != (digest, thread_id)
            ):
                raise SecurityBlocker(
                    "Ready-source recovery feedback source identity changed"
                )
            classified_sources.add(key)
            normalized_sources.append(
                {"kind": kind, "node_id": node_id, "digest": digest}
            )
        normalized_findings.append(
            {
                "finding_id": finding_id,
                "thread_id": thread_id,
                "sources": normalized_sources,
                "classification": classification,
                "disposition": disposition,
                "evidence_digest": _require_digest(
                    item["evidence_digest"],
                    "Ready-source recovery finding evidence",
                ),
                "technically_blocking": False,
            }
        )
    if classified_sources != set(expected_sources):
        raise SecurityBlocker(
            "Ready-source recovery feedback coverage is incomplete"
        )
    covered_threads = {
        item["thread_id"] for item in normalized_findings
        if item["thread_id"] is not None
    }
    if covered_threads != review_threads:
        raise SecurityBlocker(
            "Ready-source recovery review-thread inventory is ambiguous"
        )
    limits = registry.get("limits") if isinstance(registry, dict) else None
    maximum_items = (
        limits.get("maximum_items") if isinstance(limits, dict) else None
    )
    source_count = sum(len(item["sources"]) for item in normalized_findings)
    if (
        not isinstance(maximum_items, int)
        or isinstance(maximum_items, bool)
        or maximum_items < 1
        or len(normalized_findings) + source_count > maximum_items
    ):
        raise SecurityBlocker("Ready-source recovery feedback evidence is oversized")
    if not isinstance(fresh_validation_receipt, dict):
        raise SecurityBlocker("Ready-source recovery validation receipt is missing")
    if any(
        field in fresh_validation_receipt
        for field in (
            "eligibility_evidence_digest", "integration_evidence_digest",
            "exceptional_recovery_evidence_digest",
        )
    ):
        raise SecurityBlocker(
            "Ready-source recovery validation receipt claims unrelated authority"
        )
    if current_safety_profile is None:
        schema_version = "1.0"
        validation_execution_origin = "MAINTAINED_REGISTERED_EXECUTION"
    else:
        profile_fields = {
            "schema_version", "policy", "harness", "validation_command_set",
            "validation_command_set_digest", "timeout_seconds",
            "required_invariants", "validation_results",
        }
        harness = current_safety_profile.get("harness") if isinstance(
            current_safety_profile, dict
        ) else None
        commands = current_safety_profile.get("validation_command_set") if isinstance(
            current_safety_profile, dict
        ) else None
        invariants = current_safety_profile.get("required_invariants") if isinstance(
            current_safety_profile, dict
        ) else None
        results = current_safety_profile.get("validation_results") if isinstance(
            current_safety_profile, dict
        ) else None
        if (
            not isinstance(current_safety_profile, dict)
            or set(current_safety_profile) != profile_fields
            or current_safety_profile.get("schema_version") != "1.0"
            or current_safety_profile.get("policy")
            != "READY_SOURCE_RECOVERY_CURRENT_SAFETY"
            or current_safety_profile.get("timeout_seconds") != 120
            or not isinstance(harness, list) or len(harness) != 1
            or set(harness[0]) != {"path", "mode", "blob_oid", "size"}
            or harness[0].get("path")
            != "tests/ready-source-recovery-current-safety.py"
            or harness[0].get("mode") not in {"100644", "100755"}
            or not isinstance(harness[0].get("size"), int)
            or isinstance(harness[0].get("size"), bool)
            or harness[0].get("size") < 1
            or not isinstance(harness[0].get("blob_oid"), str)
            or not OID.fullmatch(harness[0]["blob_oid"])
            or not isinstance(commands, list) or len(commands) != 1
            or commands[0] != {
                "argv": ["python3", harness[0]["path"]],
                "working_directory": ".",
                "purpose": "Validate Ready-source recovery current safety",
            }
            or current_safety_profile.get("validation_command_set_digest")
            != digest_json(commands)
            or not isinstance(invariants, list) or not invariants
            or any(not isinstance(item, str) or not item for item in invariants)
            or invariants != sorted(set(invariants))
            or results != [{
                "command_digest": digest_json(commands[0]),
                "exit_status": 0,
                "successful": True,
            }]
            or registry.get("ready_source_recovery_current_safety")
            != current_safety_profile
            or command_set != commands
        ):
            raise SecurityBlocker(
                "Ready-source recovery current-safety profile is invalid"
            )
        schema_version = "1.1"
        validation_execution_origin = (
            "ACCEPTED_MAIN_EXACT_SOURCE_CURRENT_SAFETY"
        )
    expected_receipt = create_validation_receipt(
        repository=repository,
        head_sha=head,
        validated_tree_sha=tree,
        registry=registry,
        command_set=command_set,
        successful_result=True,
        reviewed_state=reviewed,
        manual_gate_evidence=fresh_validation_receipt.get(
            "manual_gate_evidence"
        ),
    )
    if fresh_validation_receipt != expected_receipt:
        raise SecurityBlocker(
            "Ready-source recovery validation receipt is invalid or stale"
        )
    assessment = {
        "review_decision": review_decision,
        "approval_required": approval_required,
        "findings": normalized_findings,
    }
    facts = {
        "schema_version": schema_version,
        "kind": "SECPAL_READY_SOURCE_RECOVERY_SAFETY_FACTS",
        "tooling_authority_main": policy_head,
        "repository": repository,
        "pull_request_number": pr,
        "head_sha": head,
        "tree_sha": tree,
        "parent_shas": list(parents),
        "expected_base_ref": base_ref,
        "expected_base_sha": base_sha,
        "reviewed_state": reviewed.to_dict(),
        "review_decision": review_decision,
        "approval_required": approval_required,
        "feedback_findings": normalized_findings,
        "policy_binding": copy.deepcopy(registry),
        "command_set": copy.deepcopy(command_set),
        "fresh_validation_receipt": copy.deepcopy(expected_receipt),
        "reviewed_state_digest": reviewed.state_digest,
        "reviewed_feedback_digest": reviewed.feedback_digest,
        "feedback_assessment_digest": digest_json(assessment),
        "fresh_validation_receipt_digest": expected_receipt["receipt_digest"],
        "validation_execution_origin": validation_execution_origin,
    }
    return {**facts, "safety_facts_digest": digest_json(facts)}


def verify_ready_source_recovery_safety_facts(value: Any) -> dict[str, Any]:
    """Recompute complete unsigned facts before an authorization signs them."""

    fields = {
        "schema_version", "kind", "tooling_authority_main", "repository",
        "pull_request_number", "head_sha", "tree_sha", "parent_shas",
        "expected_base_ref", "expected_base_sha", "reviewed_state",
        "review_decision", "approval_required", "feedback_findings",
        "policy_binding", "command_set",
        "fresh_validation_receipt", "reviewed_state_digest",
        "reviewed_feedback_digest", "feedback_assessment_digest",
        "fresh_validation_receipt_digest", "validation_execution_origin",
        "safety_facts_digest",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise SecurityBlocker("Ready-source recovery safety facts are malformed")
    unsigned = {
        key: copy.deepcopy(item) for key, item in value.items()
        if key != "safety_facts_digest"
    }
    if value["safety_facts_digest"] != digest_json(unsigned):
        raise SecurityBlocker("Ready-source recovery safety-facts digest mismatch")
    version = value["schema_version"]
    origins = {
        "1.0": "MAINTAINED_REGISTERED_EXECUTION",
        "1.1": "ACCEPTED_MAIN_EXACT_SOURCE_CURRENT_SAFETY",
    }
    if (
        version not in origins
        or value["kind"] != "SECPAL_READY_SOURCE_RECOVERY_SAFETY_FACTS"
        or value["validation_execution_origin"] != origins[version]
    ):
        raise SecurityBlocker("Ready-source recovery safety-facts type is invalid")
    reviewed = StableFeedbackState.from_payload(value["reviewed_state"])
    derived = derive_ready_source_recovery_safety_facts(
        tooling_authority_main=value["tooling_authority_main"],
        repository=value["repository"],
        pull_request_number=value["pull_request_number"],
        head_sha=value["head_sha"], tree_sha=value["tree_sha"],
        parent_shas=value["parent_shas"],
        expected_base_ref=value["expected_base_ref"],
        expected_base_sha=value["expected_base_sha"],
        reviewed_state=reviewed, review_decision=value["review_decision"],
        approval_required=value["approval_required"],
        feedback_findings=value["feedback_findings"],
        fresh_validation_receipt=value["fresh_validation_receipt"],
        registry=value["policy_binding"], command_set=value["command_set"],
        current_safety_profile=(
            value["policy_binding"].get("ready_source_recovery_current_safety")
            if version == "1.1" and isinstance(value["policy_binding"], dict)
            else None
        ),
    )
    if derived != value:
        raise SecurityBlocker("Ready-source recovery safety facts are inconsistent")
    return derived


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
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
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
