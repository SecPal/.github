# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed, append-only authority for the finite delivery lifecycle.

This module owns lifecycle state derivation, not lifecycle orchestration.  Its
public verifier loads signer roles and credentials from the installed maintained
registry, consumes canonical serialized evidence, and performs SSH/OpenPGP
verification without accepting consumer-selected trust inputs.
"""

from __future__ import annotations

import base64
import binascii
import copy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .fast_path import (
    SecurityBlocker,
    VerifiedValidationEvidence,
    canonical_json_bytes,
    digest_json,
    is_verified_validation_evidence,
    verify_commit_signatures,
)


SCHEMA_VERSION = "1.0"
AUTHORITY_KIND = "SECPAL_DELIVERY_LIFECYCLE_AUTHORITY"
AUTHORITY_DOMAIN = "secpal.delivery-lifecycle-authority/v1"
EVENT_KIND = "SECPAL_DELIVERY_LIFECYCLE_TRANSITION_AUTHORIZATION"
EVENT_DOMAIN = "secpal.delivery-lifecycle-transition-authorization/v1"
INITIALIZATION_KIND = "SECPAL_DELIVERY_LIFECYCLE_INITIALIZATION"
INITIALIZATION_DOMAIN = "secpal.delivery-lifecycle-initialization/v1"
BUNDLE_KIND = "SECPAL_DELIVERY_LIFECYCLE_EVIDENCE"
BUNDLE_DOMAIN = "secpal.delivery-lifecycle-evidence/v1"
LEGACY_ADOPTION_KIND = "SECPAL_LEGACY_LIFECYCLE_ADOPTION_CHECKPOINT"
LEGACY_ADOPTION_DOMAIN = "secpal.legacy-lifecycle-adoption-checkpoint/v1"
LEGACY_PROOF_MODE = "legacy_migration_checkpoint"
EXACT_ADOPTION_PROOF_KIND = "SECPAL_EXACT_STATE_ADOPTION_PROOF"
EXACT_ADOPTION_PROOF_DOMAIN = "secpal.exact-state-adoption-proof/v1"
EXACT_ADOPTION_AUTHORIZATION_KIND = "SECPAL_EXACT_STATE_ADOPTION_AUTHORIZATION"
EXACT_ADOPTION_AUTHORIZATION_DOMAIN = "secpal.exact-state-adoption-authorization/v1"
EXACT_ADOPTION_EVIDENCE_KIND = "SECPAL_EXACT_STATE_ADOPTION_EVIDENCE"
EXACT_ADOPTION_EVIDENCE_DOMAIN = "secpal.exact-state-adoption-evidence/v1"
EXACT_ADOPTION_PROOF_MODE = "exact_state_adoption"
NATIVE_PROOF_MODE = "native_lifecycle"
PUBLICATION_EVIDENCE_KIND = "SECPAL_PUBLISHED_LIFECYCLE_EVIDENCE"
PUBLICATION_EVIDENCE_DOMAIN = "secpal.published-lifecycle-evidence/v1"

MAX_UNRESTRICTED_REVIEWS = 1
MAX_REMEDIATION_CYCLES = 2
MAX_EXCEPTIONAL_RECOVERIES = 1
MAX_EXCEPTIONAL_CONTINUATIONS = 1

TRANSITIONS = frozenset(
    {
        "INITIALIZED_DRAFT",
        "UNRESTRICTED_REVIEW_CONSUMED",
        "REMEDIATION_COMPLETED",
        "DRAFT_TO_READY",
        "READY_TO_DRAFT",
        "HEAD_ADVANCED",
        "EXCEPTIONAL_RECOVERY",
        "EXCEPTIONAL_CONTINUATION",
        "PR_REBOUND",
        "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
    }
)

_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,254}")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

Signature = Mapping[str, Any]
Signer = Callable[[bytes, str], Signature]
SignatureVerifier = Callable[
    [bytes, Mapping[str, Any], str, str], "VerifiedSignature"
]


class LifecycleAuthorityError(ValueError):
    """Lifecycle authority is incomplete, stale, ambiguous, or unauthorized."""


@dataclass(frozen=True)
class VerifiedSignature:
    """Normalized result returned by a trusted SSH/OpenPGP verification adapter."""

    signer_identity: str
    signature_format: str


@dataclass(frozen=True)
class ExpectedLifecycle:
    """Identity and optional state constraints requested by a consumer."""

    repository: str
    delivery_issue: int
    lifecycle_id: str
    pull_request: int
    head_sha: str
    unrestricted_review_count: int | None = None
    remediation_cycle_count: int | None = None
    ready: bool | None = None
    ready_transition_count: int | None = None
    exceptional_recovery_count: int | None = None
    exceptional_continuation_count: int | None = None


@dataclass(frozen=True)
class VerifiedLifecycleAuthority:
    """Normalized authority returned only after the full chain is verified."""

    authority_digest: str
    repository: str
    delivery_issue: int
    lifecycle_id: str
    initialization_evidence_digest: str
    pull_request: int
    head_sha: str
    state: dict[str, Any]
    authority_signer_identity: str
    historical_proof_mode: str = NATIVE_PROOF_MODE
    legacy_adoption_checkpoint_digest: str | None = None
    tree_sha: str | None = None
    validation_receipt_digest: str | None = None
    source_validation_evidence_digest: str | None = None
    adoption_source_evidence_digest: str | None = None


_VERIFIED_EXACT_ADOPTION_EVIDENCE = object()


@dataclass(frozen=True)
class VerifiedExactStateAdoptionExternalEvidence:
    """Verifier-derived delivery facts accepted by exact adoption assembly."""

    repository: str
    delivery_issue: int
    pull_request: int
    head_sha: str
    tree_sha: str
    pull_request_state: str
    commit_signature_evidence_digest: str
    validation_receipt_digest: str
    source_validation_evidence_digest: str
    adoption_source_evidence_digest: str
    observed_pre_enrollment_history: tuple[dict[str, Any], ...]
    intended_state: dict[str, Any]
    supporting_evidence_digests: tuple[str, ...]
    _verification_seal: object


@dataclass(frozen=True)
class TrustedSigner:
    """One signer credential loaded from the maintained repository registry."""

    identity: str
    ssh_public_keys: tuple[str, ...]
    openpgp_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class InitializationAnchor:
    """One registry-authenticated initialization and its current trusted tip."""

    delivery_issue: int
    pull_request: int
    initial_head_sha: str
    initialization_digest: str
    current_pull_request: int
    current_head_sha: str
    current_authority_digest: str


@dataclass(frozen=True)
class BootstrapGenesisRepair:
    """One maintained, one-time repair allowance for pre-admission publication."""

    repair_issue: int
    delivery_issue: int
    pull_request: int
    initial_head_sha: str
    initialization_digest: str
    validation_receipt_digest: str
    final_attestation_digest: str
    enrollment_publication_oid: str
    enrollment_publication_digest: str


@dataclass(frozen=True)
class BootstrapSourceAdmissionPolicy:
    """One exact implementation source admitted by accepted-main policy."""

    schema_version: str
    kind: str
    subtype: str
    repository: str
    delivery_issue: int
    pull_request: int
    source_head_sha: str
    source_tree_sha: str
    source_parent_sha: str
    validation_receipt_digest: str
    final_attestation_digest: str
    source_signer_identity: str
    implementation_path: str
    entrypoint: str
    purpose: str
    source_pr_state: str
    source_pr_draft: bool
    source_base_ref: str
    admission_digest: str


@dataclass(frozen=True)
class HistoricalCompatibilityPublication:
    """One exact pre-admission native enrollment allowed by maintained policy."""

    repository: str
    delivery_issue: int
    pull_request: int
    initial_head_sha: str
    initialization_digest: str
    enrollment_publication_oid: str
    enrollment_publication_digest: str
    historical_proof_mode: str


@dataclass(frozen=True)
class LifecycleTrustPolicy:
    """Installed trust policy; never accepted as lifecycle evidence input."""

    repository: str
    accepted_formats: frozenset[str]
    transition_signer_identities: frozenset[str]
    authority_signer_identities: frozenset[str]
    signers: Mapping[str, TrustedSigner]
    initialization_anchors: tuple[InitializationAnchor, ...]
    publication_signer_identities: frozenset[str] = frozenset()
    genesis_admission_signer_identities: frozenset[str] = frozenset()
    legacy_adoption_signer_identities: frozenset[str] = frozenset()
    publication_branch: str = "refs/heads/secpal-lifecycle-publications"
    publication_remote_url: str = ""
    publication_ruleset_id: int = 0
    publication_required_rules: frozenset[str] = frozenset()
    bootstrap_genesis_repairs: tuple[BootstrapGenesisRepair, ...] = ()
    bootstrap_source_admissions: tuple[BootstrapSourceAdmissionPolicy, ...] = ()
    historical_compatibility_publications: tuple[
        HistoricalCompatibilityPublication, ...
    ] = ()


EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "event_id",
        "repository",
        "delivery_issue",
        "lifecycle_id",
        "pull_request",
        "predecessor_authority_digest",
        "predecessor_head_sha",
        "resulting_head_sha",
        "transition_kind",
        "replacement_pull_request",
        "initialization_evidence_digest",
        "signer_identity",
        "signature",
        "event_digest",
    }
)
AUTHORITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "repository",
        "delivery_issue",
        "lifecycle_id",
        "pull_request",
        "head_sha",
        "predecessor_head_sha",
        "predecessor_authority_digest",
        "transition_kind",
        "event_authorization_digest",
        "initialization_evidence_digest",
        "state_before",
        "state_after",
        "signer_identity",
        "signature",
        "authority_digest",
    }
)
CURRENT_HEAD_EVIDENCE_FIELDS = frozenset(
    {
        "head_sha",
        "tree_sha",
        "validation_receipt_digest",
        "source_validation_evidence_digest",
        "final_attestation_digest",
    }
)
SIGNATURE_FIELDS = frozenset({"format", "signer_identity", "value"})
STATE_FIELDS = frozenset(
    {
        "unrestricted_review_count",
        "remediation_cycle_count",
        "cycle_3_absent",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_recovery_count",
        "exceptional_recovery_history",
        "exceptional_continuation_count",
        "exceptional_continuation_history",
    }
)
HISTORY_FIELDS = frozenset(
    {"sequence", "transition_kind", "event_authorization_digest"}
)
ADOPTED_HISTORY_FIELDS = frozenset(
    {"sequence", "transition_kind", "observation_digest"}
)
INITIALIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "repository",
        "delivery_issue",
        "pull_request",
        "initial_head_sha",
        "validation_receipt_digest",
        "final_attestation_digest",
        "signer_identity",
        "signature",
        "initialization_digest",
    }
)
BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "delivery_initialization",
        "transition_authorizations",
        "authority_chain",
    }
)
LEGACY_ADOPTION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "historical_proof_mode",
        "repository",
        "delivery_issue",
        "lifecycle_id",
        "current_pull_request",
        "current_head_sha",
        "initial_delivery_identity",
        "state",
        "pr_replacement_history_summary",
        "migration_reason",
        "authorization_identity",
        "checkpoint_event_id",
        "checkpoint_timestamp",
        "supporting_evidence_digests",
        "lifecycle_evidence_digest",
        "terminal_authority_digest",
        "signer_identity",
        "signature",
        "checkpoint_digest",
    }
)
OBSERVED_HISTORY_FIELDS = frozenset(
    {"sequence", "kind", "observed_at", "head_sha", "reviewed_head_sha"}
)
EXACT_ADOPTION_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version", "kind", "domain", "proof_version", "repository",
        "delivery_issue", "pull_request", "head_sha", "tree_sha",
        "pull_request_state", "commit_signature_status",
        "commit_signature_evidence_digest", "validation_receipt_digest",
        "source_validation_evidence_digest", "adoption_source_evidence_digest",
        "observed_pre_enrollment_history", "observed_history_digest",
        "intended_state", "intended_state_digest", "adoption_timestamp",
        "supporting_evidence_digests", "ordinary_lifecycle_events",
        "head_advanced_count", "head_advanced_history_digest",
        "adoption_evidence_digest",
    }
)
EXACT_ADOPTION_AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version", "kind", "domain", "proof_version", "repository",
        "delivery_issue", "pull_request", "head_sha", "tree_sha",
        "adoption_evidence_digest", "intended_state_digest",
        "authorization_id", "bounded_uses", "signer_identity", "signature",
        "authorization_digest",
    }
)
EXACT_ADOPTION_PROOF_FIELDS = frozenset(
    (EXACT_ADOPTION_EVIDENCE_FIELDS - {"kind", "domain"})
    | {
        "kind", "domain", "historical_proof_mode", "lifecycle_id",
        "authorization", "authorization_digest", "signer_identity", "signature",
        "proof_digest",
    }
)
EXACT_ADOPTION_PUBLICATION_FIELDS = frozenset(
    {
        "schema_version", "kind", "domain", "enrollment_mode",
        "exact_state_adoption_proof", "transition_authorizations",
        "authority_chain",
    }
)
PUBLICATION_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "enrollment_mode",
        "lifecycle_evidence",
        "legacy_adoption_checkpoint",
    }
)

_TRUST_REGISTRY = (
    Path(__file__).resolve().parents[2]
    / ".agents/skills/secpal-pr-review/references/repositories.json"
)
_EVIDENCE_HELPER = Path(__file__).resolve().parents[1] / "secpal-pr-review.py"


def loads_closed_json(raw: bytes | str) -> Any:
    """Parse JSON while rejecting duplicate object keys before normalization."""

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise LifecycleAuthorityError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise LifecycleAuthorityError(f"non-finite JSON value is forbidden: {value}")

    try:
        return json.loads(
            raw,
            object_pairs_hook=closed_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LifecycleAuthorityError("lifecycle authority JSON is malformed") from exc


def _load_canonical_json(raw: bytes | str, label: str) -> Any:
    parsed = loads_closed_json(raw)
    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    if encoded != canonical_json_bytes(parsed):
        raise LifecycleAuthorityError(f"{label} is not canonical JSON")
    return parsed


def _require_closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise LifecycleAuthorityError(f"{label} schema is not closed")
    return value


def _require_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise LifecycleAuthorityError(f"{label} is invalid")
    return value


def _require_repository(value: Any) -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise LifecycleAuthorityError("repository identity is invalid")
    return value


def _require_oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _OID.fullmatch(value):
        raise LifecycleAuthorityError(f"{label} is not a canonical commit OID")
    return value


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise LifecycleAuthorityError(f"{label} is not a canonical SHA-256 digest")
    return value


def _require_transition_kind(value: Any, *, allow_genesis: bool = True) -> str:
    permitted = TRANSITIONS if allow_genesis else TRANSITIONS - {"INITIALIZED_DRAFT"}
    if not isinstance(value, str) or value not in permitted:
        raise LifecycleAuthorityError("unknown lifecycle transition")
    return value


def _require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LifecycleAuthorityError(f"{label} must be a positive integer")
    return value


def _require_counter(value: Any, label: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > maximum
    ):
        raise LifecycleAuthorityError(f"{label} is outside its finite budget")
    return value


def _unsigned(value: Mapping[str, Any], digest_field: str, signature_field: str) -> dict[str, Any]:
    return {
        key: copy.deepcopy(item)
        for key, item in value.items()
        if key not in {digest_field, signature_field}
    }


def _normalize_signature(value: Any, expected_signer: str) -> dict[str, str]:
    signature = _require_closed(value, SIGNATURE_FIELDS, "signature")
    signature_format = signature["format"]
    if signature_format not in {"ssh", "openpgp"}:
        raise LifecycleAuthorityError("signature format is not accepted")
    signer_identity = _require_identity(signature["signer_identity"], "signature signer")
    if signer_identity != expected_signer:
        raise LifecycleAuthorityError("signature signer identity is inconsistent")
    encoded = signature["value"]
    if not isinstance(encoded, str) or not encoded or len(encoded) > 16384:
        raise LifecycleAuthorityError("signature value is malformed")
    return {
        "format": signature_format,
        "signer_identity": signer_identity,
        "value": encoded,
    }


def _verify_signature(
    payload: bytes,
    signature: Any,
    expected_signer: str,
    domain: str,
    accepted_signers: frozenset[str],
    verifier: SignatureVerifier,
) -> dict[str, str]:
    normalized = _normalize_signature(signature, expected_signer)
    if expected_signer not in accepted_signers:
        raise LifecycleAuthorityError("authority signer is not independently accepted")
    try:
        verified = verifier(payload, normalized, expected_signer, domain)
    except Exception as exc:
        raise LifecycleAuthorityError("authority signature verification failed") from exc
    if not isinstance(verified, VerifiedSignature):
        raise LifecycleAuthorityError("signature verifier returned ambiguous evidence")
    if (
        verified.signer_identity != expected_signer
        or verified.signature_format != normalized["format"]
    ):
        raise LifecycleAuthorityError("verified signer or signature format is wrong")
    return normalized


def delivery_initialization_lifecycle_id(initialization_digest: str) -> str:
    """Derive the sole persistent lifecycle identity for one initialization."""

    return f"lifecycle:{_require_digest(initialization_digest, 'initialization digest')}"


def create_delivery_initialization(
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    initial_head_sha: str,
    validation_receipt_digest: str,
    final_attestation_digest: str,
    signer_identity: str,
    signer: Signer,
) -> dict[str, Any]:
    """Create signed ordinary-delivery initialization evidence."""

    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": INITIALIZATION_KIND,
        "domain": INITIALIZATION_DOMAIN,
        "repository": _require_repository(repository),
        "delivery_issue": _require_positive_int(delivery_issue, "delivery issue"),
        "pull_request": _require_positive_int(pull_request, "pull request"),
        "initial_head_sha": _require_oid(initial_head_sha, "initial head"),
        "validation_receipt_digest": _require_digest(
            validation_receipt_digest, "validation receipt"
        ),
        "final_attestation_digest": _require_digest(
            final_attestation_digest, "final attestation"
        ),
        "signer_identity": _require_identity(signer_identity, "initialization signer"),
    }
    signature = _normalize_signature(
        signer(canonical_json_bytes(fields), INITIALIZATION_DOMAIN), signer_identity
    )
    signed = {**fields, "signature": signature}
    return {**signed, "initialization_digest": digest_json(signed)}


def _verify_delivery_initialization(
    value: Any,
    *,
    policy: LifecycleTrustPolicy,
    signature_verifier: SignatureVerifier,
    require_maintained_anchor: bool = True,
) -> dict[str, Any]:
    initialization = _require_closed(
        value, INITIALIZATION_FIELDS, "delivery initialization"
    )
    if initialization["schema_version"] != SCHEMA_VERSION:
        raise LifecycleAuthorityError("unknown delivery-initialization version")
    if (
        initialization["kind"] != INITIALIZATION_KIND
        or initialization["domain"] != INITIALIZATION_DOMAIN
    ):
        raise LifecycleAuthorityError("unknown delivery-initialization kind or domain")
    repository = _require_repository(initialization["repository"])
    if repository != policy.repository:
        raise LifecycleAuthorityError("initialization repository is not trusted")
    issue = _require_positive_int(initialization["delivery_issue"], "delivery issue")
    pull_request = _require_positive_int(initialization["pull_request"], "pull request")
    head = _require_oid(initialization["initial_head_sha"], "initial head")
    _require_digest(initialization["validation_receipt_digest"], "validation receipt")
    _require_digest(initialization["final_attestation_digest"], "final attestation")
    signer = _require_identity(initialization["signer_identity"], "initialization signer")
    signed = {
        key: copy.deepcopy(item)
        for key, item in initialization.items()
        if key != "initialization_digest"
    }
    digest = _require_digest(initialization["initialization_digest"], "initialization digest")
    if digest != digest_json(signed):
        raise LifecycleAuthorityError("delivery-initialization digest mismatch")
    _verify_signature(
        canonical_json_bytes(
            _unsigned(initialization, "initialization_digest", "signature")
        ),
        initialization["signature"],
        signer,
        INITIALIZATION_DOMAIN,
        policy.transition_signer_identities,
        signature_verifier,
    )
    if require_maintained_anchor:
        matching = [
            anchor
            for anchor in policy.initialization_anchors
            if (
                anchor.delivery_issue == issue
                and anchor.pull_request == pull_request
                and anchor.initial_head_sha == head
            )
        ]
        if len(matching) != 1 or matching[0].initialization_digest != digest:
            raise LifecycleAuthorityError(
                "delivery initialization is not the unique maintained trust anchor"
            )
    return copy.deepcopy(initialization)


def _load_lifecycle_trust_policy(repository: str) -> LifecycleTrustPolicy:
    """Load lifecycle trust only from the installed maintained registry."""

    try:
        registry = loads_closed_json(_TRUST_REGISTRY.read_bytes())
    except OSError as exc:
        raise LifecycleAuthorityError("maintained lifecycle trust registry is unavailable") from exc
    if not isinstance(registry, dict) or registry.get("schema_version") != "1.0":
        raise LifecycleAuthorityError("maintained lifecycle trust registry is invalid")
    entries = registry.get("repositories")
    if not isinstance(entries, list):
        raise LifecycleAuthorityError("maintained repository registry is malformed")
    matches = [
        item
        for item in entries
        if isinstance(item, dict) and item.get("repository") == repository
    ]
    if len(matches) != 1:
        raise LifecycleAuthorityError("repository has no unique maintained trust policy")
    raw = matches[0].get("lifecycle_authority_policy")
    fields = frozenset(
        {
            "schema_version",
            "accepted_formats",
            "signers",
            "transition_signer_identities",
            "authority_signer_identities",
            "publication_signer_identities",
            "genesis_admission_signer_identities",
            "legacy_adoption_signer_identities",
            "publication_branch",
            "publication_remote_url",
            "publication_ruleset_id",
            "publication_required_rules",
            "bootstrap_genesis_repairs",
            "bootstrap_source_admissions",
            "historical_compatibility_publications",
            "delivery_initializations",
        }
    )
    policy = _require_closed(raw, fields, "lifecycle trust policy")
    if policy["schema_version"] != SCHEMA_VERSION:
        raise LifecycleAuthorityError("unknown lifecycle trust-policy version")
    formats = policy["accepted_formats"]
    if (
        not isinstance(formats, list)
        or not formats
        or len(formats) != len(set(formats))
        or any(item not in {"ssh", "openpgp"} for item in formats)
    ):
        raise LifecycleAuthorityError("lifecycle signature-format policy is invalid")
    signers: dict[str, TrustedSigner] = {}
    signer_fields = frozenset(
        {"identity", "ssh_public_keys", "openpgp_fingerprints"}
    )
    if not isinstance(policy["signers"], list):
        raise LifecycleAuthorityError("lifecycle signer policy is invalid")
    for value in policy["signers"]:
        item = _require_closed(value, signer_fields, "trusted lifecycle signer")
        identity = _require_identity(item["identity"], "trusted signer")
        ssh_keys = item["ssh_public_keys"]
        fingerprints = item["openpgp_fingerprints"]
        if (
            identity in signers
            or not isinstance(ssh_keys, list)
            or not isinstance(fingerprints, list)
            or len(ssh_keys) != len(set(ssh_keys))
            or len(fingerprints) != len(set(fingerprints))
            or any(
                not isinstance(key, str)
                or not re.fullmatch(r"ssh-(?:ed25519|rsa) [A-Za-z0-9+/=]+", key)
                for key in ssh_keys
            )
            or any(
                not isinstance(fingerprint, str)
                or not re.fullmatch(r"[0-9A-F]{40,64}", fingerprint)
                for fingerprint in fingerprints
            )
            or (not ssh_keys and not fingerprints)
        ):
            raise LifecycleAuthorityError("trusted lifecycle signer credentials are invalid")
        signers[identity] = TrustedSigner(
            identity, tuple(ssh_keys), tuple(fingerprints)
        )

    def role_identities(key: str) -> frozenset[str]:
        values = policy[key]
        if (
            not isinstance(values, list)
            or not values
            or len(values) != len(set(values))
            or any(value not in signers for value in values)
        ):
            raise LifecycleAuthorityError(f"{key} is not a closed trusted signer role")
        return frozenset(values)

    transition_signers = role_identities("transition_signer_identities")
    authority_signers = role_identities("authority_signer_identities")
    publication_signers = role_identities("publication_signer_identities")
    genesis_admission_signers = role_identities(
        "genesis_admission_signer_identities"
    )
    legacy_adoption_signers = role_identities("legacy_adoption_signer_identities")

    def credential_identities(identity: str) -> frozenset[tuple[str, bytes]]:
        signer = signers[identity]
        credentials: set[tuple[str, bytes]] = set()
        for public_key in signer.ssh_public_keys:
            algorithm, encoded = public_key.split(" ", 1)
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise LifecycleAuthorityError(
                    "trusted lifecycle signer credentials are invalid"
                ) from exc
            if base64.b64encode(decoded).decode("ascii") != encoded:
                raise LifecycleAuthorityError(
                    "trusted lifecycle signer credentials are not canonical"
                )
            credentials.add((f"ssh:{algorithm}", decoded))
        credentials.update(
            ("openpgp", bytes.fromhex(fingerprint))
            for fingerprint in signer.openpgp_fingerprints
        )
        return frozenset(credentials)

    legacy_credentials: dict[tuple[str, bytes], str] = {}
    for identity in legacy_adoption_signers:
        for credential in credential_identities(identity):
            if credential in legacy_credentials:
                raise LifecycleAuthorityError(
                    "legacy-adoption signer credentials are ambiguous"
                )
            legacy_credentials[credential] = identity
    routine_signers = (
        transition_signers
        | authority_signers
        | publication_signers
        | genesis_admission_signers
    )
    if legacy_adoption_signers & routine_signers:
        raise LifecycleAuthorityError(
            "legacy-adoption authority must use a distinct signer identity"
        )
    for identity in set(signers) - legacy_adoption_signers:
        if set(credential_identities(identity)) & set(legacy_credentials):
            raise LifecycleAuthorityError(
                "legacy-adoption authority must use a cryptographically distinct credential"
            )

    anchors: list[InitializationAnchor] = []
    anchor_fields = frozenset(
        {
            "delivery_issue",
            "pull_request",
            "initial_head_sha",
            "initialization_digest",
            "current_pull_request",
            "current_head_sha",
            "current_authority_digest",
        }
    )
    if not isinstance(policy["delivery_initializations"], list):
        raise LifecycleAuthorityError("delivery initialization policy is invalid")
    seen_delivery_issues: set[int] = set()
    seen_digests: set[str] = set()
    for value in policy["delivery_initializations"]:
        item = _require_closed(value, anchor_fields, "delivery initialization anchor")
        issue = _require_positive_int(item["delivery_issue"], "anchored delivery issue")
        pull_request = _require_positive_int(item["pull_request"], "anchored pull request")
        head = _require_oid(item["initial_head_sha"], "anchored initial head")
        digest = _require_digest(item["initialization_digest"], "anchored initialization")
        current_pull_request = _require_positive_int(
            item["current_pull_request"], "current anchored pull request"
        )
        current_head = _require_oid(item["current_head_sha"], "current anchored head")
        current_authority = _require_digest(
            item["current_authority_digest"], "current terminal authority"
        )
        if issue in seen_delivery_issues or digest in seen_digests:
            raise LifecycleAuthorityError("delivery initialization anchors are ambiguous")
        seen_delivery_issues.add(issue)
        seen_digests.add(digest)
        anchors.append(
            InitializationAnchor(
                issue,
                pull_request,
                head,
                digest,
                current_pull_request,
                current_head,
                current_authority,
            )
        )
    publication_branch = policy["publication_branch"]
    if (
        publication_branch != "refs/heads/secpal-lifecycle-publications"
    ):
        raise LifecycleAuthorityError("lifecycle publication branch is invalid")
    publication_remote = policy["publication_remote_url"]
    if (
        not isinstance(publication_remote, str)
        or not re.fullmatch(
            r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git",
            publication_remote,
        )
    ):
        raise LifecycleAuthorityError("lifecycle publication remote is invalid")
    if publication_remote != f"https://github.com/{repository}.git":
        raise LifecycleAuthorityError("lifecycle publication remote does not match repository")
    ruleset_id = _require_positive_int(
        policy["publication_ruleset_id"], "publication ruleset"
    )
    required_rules = policy["publication_required_rules"]
    if (
        not isinstance(required_rules, list)
        or set(required_rules) != {"deletion", "non_fast_forward"}
        or len(required_rules) != 2
    ):
        raise LifecycleAuthorityError("lifecycle publication protection policy is invalid")
    repair_fields = frozenset(
        {
            "repair_issue",
            "delivery_issue",
            "pull_request",
            "initial_head_sha",
            "initialization_digest",
            "validation_receipt_digest",
            "final_attestation_digest",
            "enrollment_publication_oid",
            "enrollment_publication_digest",
        }
    )
    raw_repairs = policy["bootstrap_genesis_repairs"]
    if not isinstance(raw_repairs, list):
        raise LifecycleAuthorityError("bootstrap genesis-repair policy is invalid")
    repairs: list[BootstrapGenesisRepair] = []
    repair_issues: set[int] = set()
    repaired_deliveries: set[int] = set()
    for value in raw_repairs:
        item = _require_closed(value, repair_fields, "bootstrap genesis repair")
        repair_issue = _require_positive_int(item["repair_issue"], "repair issue")
        delivery_issue = _require_positive_int(
            item["delivery_issue"], "repaired delivery issue"
        )
        if repair_issue in repair_issues or delivery_issue in repaired_deliveries:
            raise LifecycleAuthorityError("bootstrap genesis repairs are ambiguous")
        repair_issues.add(repair_issue)
        repaired_deliveries.add(delivery_issue)
        repairs.append(
            BootstrapGenesisRepair(
                repair_issue=repair_issue,
                delivery_issue=delivery_issue,
                pull_request=_require_positive_int(
                    item["pull_request"], "repaired pull request"
                ),
                initial_head_sha=_require_oid(
                    item["initial_head_sha"], "repaired initial head"
                ),
                initialization_digest=_require_digest(
                    item["initialization_digest"], "repaired initialization"
                ),
                validation_receipt_digest=_require_digest(
                    item["validation_receipt_digest"], "repaired validation receipt"
                ),
                final_attestation_digest=_require_digest(
                    item["final_attestation_digest"], "repaired final attestation"
                ),
                enrollment_publication_oid=_require_oid(
                    item["enrollment_publication_oid"], "repaired enrollment publication"
                ),
                enrollment_publication_digest=_require_digest(
                    item["enrollment_publication_digest"],
                    "repaired enrollment publication digest",
                ),
            )
        )
    source_fields = frozenset(
        {
            "schema_version", "kind", "subtype", "repository",
            "delivery_issue", "pull_request", "source_head_sha",
            "source_tree_sha", "source_parent_sha",
            "validation_receipt_digest", "final_attestation_digest",
            "source_signer_identity", "implementation_path", "entrypoint",
            "purpose", "source_pr_state", "source_pr_draft", "source_base_ref",
            "admission_digest",
        }
    )
    raw_sources = policy["bootstrap_source_admissions"]
    if not isinstance(raw_sources, list):
        raise LifecycleAuthorityError("bootstrap source-admission policy is invalid")
    source_admissions: list[BootstrapSourceAdmissionPolicy] = []
    source_identities: set[tuple[int, int, str]] = set()
    source_digests: set[str] = set()
    for value in raw_sources:
        item = _require_closed(value, source_fields, "bootstrap source admission")
        unsigned = {key: copy.deepcopy(item[key]) for key in source_fields - {"admission_digest"}}
        repository_identity = _require_repository(item["repository"])
        delivery_issue = _require_positive_int(item["delivery_issue"], "source delivery issue")
        pull_request = _require_positive_int(item["pull_request"], "source pull request")
        head = _require_oid(item["source_head_sha"], "source head")
        identity = (delivery_issue, pull_request, item["purpose"])
        admission_digest = _require_digest(item["admission_digest"], "source admission")
        if (
            item["schema_version"] != SCHEMA_VERSION
            or item["kind"] != "BOOTSTRAP_SOURCE_ADMISSION"
            or item["subtype"] != "FIRST_READY_EXECUTOR_BOOTSTRAP_SOURCE"
            or repository_identity != repository
            or item["source_signer_identity"] not in signers
            or item["implementation_path"]
            != "scripts/secpal_pr_review/lifecycle_execution.py"
            or item["entrypoint"] != "execute_lifecycle_transition"
            or item["purpose"] != "FIRST_READY_EXECUTOR_BOOTSTRAP"
            or item["source_pr_state"] != "OPEN"
            or item["source_pr_draft"] is not True
            or item["source_base_ref"] != "main"
            or admission_digest != digest_json(unsigned)
            or identity in source_identities
            or admission_digest in source_digests
        ):
            raise LifecycleAuthorityError(
                "bootstrap source admissions are ambiguous or mismatched"
            )
        source_identities.add(identity)
        source_digests.add(admission_digest)
        source_admissions.append(
            BootstrapSourceAdmissionPolicy(
                schema_version=item["schema_version"],
                kind=item["kind"],
                subtype=item["subtype"],
                repository=repository_identity,
                delivery_issue=delivery_issue,
                pull_request=pull_request,
                source_head_sha=head,
                source_tree_sha=_require_oid(item["source_tree_sha"], "source tree"),
                source_parent_sha=_require_oid(item["source_parent_sha"], "source parent"),
                validation_receipt_digest=_require_digest(
                    item["validation_receipt_digest"], "source validation receipt"
                ),
                final_attestation_digest=_require_digest(
                    item["final_attestation_digest"], "source final attestation"
                ),
                source_signer_identity=item["source_signer_identity"],
                implementation_path=item["implementation_path"],
                entrypoint=item["entrypoint"],
                purpose=item["purpose"],
                source_pr_state=item["source_pr_state"],
                source_pr_draft=item["source_pr_draft"],
                source_base_ref=item["source_base_ref"],
                admission_digest=admission_digest,
            )
        )
    compatibility_fields = frozenset(
        {
            "repository",
            "delivery_issue",
            "pull_request",
            "initial_head_sha",
            "initialization_digest",
            "enrollment_publication_oid",
            "enrollment_publication_digest",
            "historical_proof_mode",
        }
    )
    raw_compatibility = policy["historical_compatibility_publications"]
    if not isinstance(raw_compatibility, list):
        raise LifecycleAuthorityError(
            "historical compatibility-publication policy is invalid"
        )
    compatibility_publications: list[HistoricalCompatibilityPublication] = []
    compatibility_initializations: set[tuple[int, str]] = set()
    compatibility_oids: set[str] = set()
    compatibility_digests: set[str] = set()
    for value in raw_compatibility:
        item = _require_closed(
            value,
            compatibility_fields,
            "historical compatibility publication",
        )
        compatibility_repository = _require_repository(item["repository"])
        compatibility_issue = _require_positive_int(
            item["delivery_issue"], "historical compatibility delivery issue"
        )
        compatibility_pr = _require_positive_int(
            item["pull_request"], "historical compatibility pull request"
        )
        compatibility_head = _require_oid(
            item["initial_head_sha"], "historical compatibility initial head"
        )
        compatibility_initialization = _require_digest(
            item["initialization_digest"],
            "historical compatibility initialization",
        )
        compatibility_oid = _require_oid(
            item["enrollment_publication_oid"],
            "historical compatibility enrollment publication",
        )
        compatibility_digest = _require_digest(
            item["enrollment_publication_digest"],
            "historical compatibility enrollment publication digest",
        )
        initialization_key = (
            compatibility_issue,
            compatibility_initialization,
        )
        matching_anchors = [
            anchor
            for anchor in anchors
            if (
                anchor.delivery_issue == compatibility_issue
                and anchor.pull_request == compatibility_pr
                and anchor.initial_head_sha == compatibility_head
                and anchor.initialization_digest == compatibility_initialization
            )
        ]
        if (
            compatibility_repository != repository
            or item["historical_proof_mode"] != NATIVE_PROOF_MODE
            or len(matching_anchors) != 1
            or initialization_key in compatibility_initializations
            or compatibility_oid in compatibility_oids
            or compatibility_digest in compatibility_digests
        ):
            raise LifecycleAuthorityError(
                "historical compatibility publications are ambiguous or mismatched"
            )
        compatibility_initializations.add(initialization_key)
        compatibility_oids.add(compatibility_oid)
        compatibility_digests.add(compatibility_digest)
        compatibility_publications.append(
            HistoricalCompatibilityPublication(
                repository=compatibility_repository,
                delivery_issue=compatibility_issue,
                pull_request=compatibility_pr,
                initial_head_sha=compatibility_head,
                initialization_digest=compatibility_initialization,
                enrollment_publication_oid=compatibility_oid,
                enrollment_publication_digest=compatibility_digest,
                historical_proof_mode=item["historical_proof_mode"],
            )
        )
    return LifecycleTrustPolicy(
        repository=repository,
        accepted_formats=frozenset(formats),
        transition_signer_identities=transition_signers,
        authority_signer_identities=authority_signers,
        publication_signer_identities=publication_signers,
        genesis_admission_signer_identities=genesis_admission_signers,
        legacy_adoption_signer_identities=legacy_adoption_signers,
        publication_branch=publication_branch,
        publication_remote_url=publication_remote,
        publication_ruleset_id=ruleset_id,
        publication_required_rules=frozenset(required_rules),
        bootstrap_genesis_repairs=tuple(repairs),
        bootstrap_source_admissions=tuple(source_admissions),
        historical_compatibility_publications=tuple(
            compatibility_publications
        ),
        signers=signers,
        initialization_anchors=tuple(anchors),
    )


def _load_delivery_signature_policy(repository: str) -> dict[str, Any]:
    """Load commit-signature policy from the same maintained registry."""

    try:
        registry = loads_closed_json(_TRUST_REGISTRY.read_bytes())
    except OSError as exc:
        raise LifecycleAuthorityError(
            "maintained delivery signature policy is unavailable"
        ) from exc
    entries = registry.get("repositories") if isinstance(registry, dict) else None
    matches = [
        item for item in entries
        if isinstance(item, dict) and item.get("repository") == repository
    ] if isinstance(entries, list) else []
    if len(matches) != 1 or not isinstance(
        matches[0].get("signature_policy"), dict
    ):
        raise LifecycleAuthorityError(
            "repository has no unique maintained delivery signature policy"
        )
    return copy.deepcopy(matches[0]["signature_policy"])


@cache
def _load_trusted_command_helper() -> Any:
    """Load the maintained external-command trust boundary by exact path."""

    module_name = "secpal_lifecycle_trusted_commands"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        loaded_path = getattr(loaded, "__file__", None)
        if (
            not isinstance(loaded_path, str)
            or Path(loaded_path).resolve() != _EVIDENCE_HELPER.resolve()
        ):
            raise LifecycleAuthorityError(
                "maintained command trust helper has an unexpected path"
            )
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, _EVIDENCE_HELPER)
    if spec is None or spec.loader is None:
        raise LifecycleAuthorityError("maintained command trust helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        raise LifecycleAuthorityError(
            "maintained command trust helper could not be loaded"
        ) from exc
    return module


def _trusted_signature_command(name: str) -> tuple[str, dict[str, str]]:
    helper = _load_trusted_command_helper()
    if name not in {"gpg", "ssh-keygen"}:
        raise LifecycleAuthorityError("signature verifier executable is not allowlisted")
    for directory in helper.TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / name
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved), helper.command_environment(name)
    raise LifecycleAuthorityError(f"maintained {name} signature verifier is unavailable")


def _verify_ssh_signature(
    payload: bytes,
    signature_value: str,
    signer: TrustedSigner,
    domain: str,
) -> None:
    if not signer.ssh_public_keys:
        raise LifecycleAuthorityError("trusted signer has no SSH credential")
    executable, environment = _trusted_signature_command("ssh-keygen")
    with tempfile.TemporaryDirectory(prefix="secpal-lifecycle-ssh-") as directory:
        root = Path(directory)
        allowed = root / "allowed_signers"
        signature = root / "signature"
        allowed.write_text(
            "".join(
                f"{signer.identity} {public_key}\n"
                for public_key in signer.ssh_public_keys
            ),
            encoding="utf-8",
        )
        signature.write_text(signature_value, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    executable,
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed),
                    "-I",
                    signer.identity,
                    "-n",
                    domain,
                    "-s",
                    str(signature),
                ],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=15,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LifecycleAuthorityError("SSH signature verifier is unavailable") from exc
        if result.returncode != 0:
            raise LifecycleAuthorityError("SSH lifecycle signature is invalid")


def _verify_openpgp_signature(
    payload: bytes,
    signature_value: str,
    signer: TrustedSigner,
) -> None:
    if not signer.openpgp_fingerprints:
        raise LifecycleAuthorityError("trusted signer has no OpenPGP credential")
    executable, environment = _trusted_signature_command("gpg")
    with tempfile.TemporaryDirectory(prefix="secpal-lifecycle-openpgp-") as directory:
        root = Path(directory)
        payload_file = root / "payload"
        signature_file = root / "signature.asc"
        payload_file.write_bytes(payload)
        signature_file.write_text(signature_value, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    executable,
                    "--batch",
                    "--status-fd",
                    "1",
                    "--verify",
                    str(signature_file),
                    str(payload_file),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=15,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LifecycleAuthorityError("OpenPGP signature verifier is unavailable") from exc
        valid_fingerprints: set[str] = set()
        for line in result.stdout.splitlines():
            if line.startswith("[GNUPG:] VALIDSIG "):
                fields = line.split()
                if len(fields) >= 3:
                    valid_fingerprints.add(fields[2])
                if len(fields) >= 12:
                    valid_fingerprints.add(fields[-1])
        if result.returncode != 0 or not valid_fingerprints.intersection(
            signer.openpgp_fingerprints
        ):
            raise LifecycleAuthorityError("OpenPGP lifecycle signature is invalid")


def _policy_signature_verifier(policy: LifecycleTrustPolicy) -> SignatureVerifier:
    def verify(
        payload: bytes,
        signature: Mapping[str, Any],
        expected_signer: str,
        domain: str,
    ) -> VerifiedSignature:
        credential = policy.signers.get(expected_signer)
        signature_format = signature["format"]
        if credential is None or signature_format not in policy.accepted_formats:
            raise LifecycleAuthorityError("lifecycle signer or format is not trusted")
        if signature_format == "ssh":
            _verify_ssh_signature(payload, signature["value"], credential, domain)
        elif signature_format == "openpgp":
            _verify_openpgp_signature(payload, signature["value"], credential)
        else:
            raise LifecycleAuthorityError("lifecycle signature format is unknown")
        return VerifiedSignature(expected_signer, signature_format)

    return verify


def initial_state() -> dict[str, Any]:
    return {
        "unrestricted_review_count": 0,
        "remediation_cycle_count": 0,
        "cycle_3_absent": True,
        "draft": True,
        "ready": False,
        "ready_transition_count": 0,
        "ready_history": [],
        "exceptional_recovery_count": 0,
        "exceptional_recovery_history": [],
        "exceptional_continuation_count": 0,
        "exceptional_continuation_history": [],
    }


def _history_entry(transition: str, event_digest: str, sequence: int) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "transition_kind": transition,
        "event_authorization_digest": event_digest,
    }


def _validate_history(
    value: Any,
    label: str,
    allowed: frozenset[str],
    *,
    allow_adopted_observations: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LifecycleAuthorityError(f"{label} must be a list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        if isinstance(item, Mapping) and set(item) == HISTORY_FIELDS:
            entry = _require_closed(item, HISTORY_FIELDS, f"{label} entry")
            provenance_field = "event_authorization_digest"
        elif (
            allow_adopted_observations
            and isinstance(item, Mapping)
            and set(item) == ADOPTED_HISTORY_FIELDS
        ):
            entry = _require_closed(
                item, ADOPTED_HISTORY_FIELDS, f"{label} adopted entry"
            )
            provenance_field = "observation_digest"
        else:
            raise LifecycleAuthorityError(
                f"{label} entry contains unknown or missing fields"
            )
        if entry["sequence"] != index or isinstance(entry["sequence"], bool):
            raise LifecycleAuthorityError(f"{label} sequence is not canonical")
        if entry["transition_kind"] not in allowed:
            raise LifecycleAuthorityError(f"{label} transition is invalid")
        normalized.append({
            "sequence": index,
            "transition_kind": entry["transition_kind"],
            provenance_field: _require_digest(
                entry[provenance_field], f"{label} provenance digest"
            ),
        })
    return normalized


def _validate_state(
    value: Any, *, allow_adopted_observations: bool = False
) -> dict[str, Any]:
    state = _require_closed(value, STATE_FIELDS, "lifecycle state")
    review = _require_counter(
        state["unrestricted_review_count"],
        "unrestricted-review count",
        MAX_UNRESTRICTED_REVIEWS,
    )
    remediation = _require_counter(
        state["remediation_cycle_count"],
        "remediation-cycle count",
        MAX_REMEDIATION_CYCLES,
    )
    recovery = _require_counter(
        state["exceptional_recovery_count"],
        "exceptional-recovery count",
        MAX_EXCEPTIONAL_RECOVERIES,
    )
    continuation = _require_counter(
        state["exceptional_continuation_count"],
        "exceptional-continuation count",
        MAX_EXCEPTIONAL_CONTINUATIONS,
    )
    if state["cycle_3_absent"] is not True:
        raise LifecycleAuthorityError("Cycle 3 must be explicitly absent")
    if not isinstance(state["draft"], bool) or not isinstance(state["ready"], bool):
        raise LifecycleAuthorityError("Draft and Ready state must be booleans")
    if state["draft"] == state["ready"]:
        raise LifecycleAuthorityError("Draft and Ready state are inconsistent")
    ready_history = _validate_history(
        state["ready_history"],
        "Ready history",
        frozenset({"DRAFT_TO_READY", "READY_TO_DRAFT"}),
        allow_adopted_observations=allow_adopted_observations,
    )
    ready_count = _require_counter(
        state["ready_transition_count"],
        "Ready-transition count",
        len(ready_history),
    )
    if ready_count != sum(
        item["transition_kind"] == "DRAFT_TO_READY" for item in ready_history
    ):
        raise LifecycleAuthorityError("Ready-transition count does not match history")
    recovery_history = _validate_history(
        state["exceptional_recovery_history"],
        "exceptional-recovery history",
        frozenset({"EXCEPTIONAL_RECOVERY"}),
        allow_adopted_observations=allow_adopted_observations,
    )
    continuation_history = _validate_history(
        state["exceptional_continuation_history"],
        "exceptional-continuation history",
        frozenset({"EXCEPTIONAL_CONTINUATION"}),
        allow_adopted_observations=allow_adopted_observations,
    )
    if recovery != len(recovery_history) or continuation != len(continuation_history):
        raise LifecycleAuthorityError("exceptional lifecycle counts do not match history")
    return {
        "unrestricted_review_count": review,
        "remediation_cycle_count": remediation,
        "cycle_3_absent": True,
        "draft": state["draft"],
        "ready": state["ready"],
        "ready_transition_count": ready_count,
        "ready_history": ready_history,
        "exceptional_recovery_count": recovery,
        "exceptional_recovery_history": recovery_history,
        "exceptional_continuation_count": continuation,
        "exceptional_continuation_history": continuation_history,
    }


def _derive_state(
    predecessor_state: Mapping[str, Any],
    transition_kind: str,
    event_authorization_digest: str,
    *,
    allow_adopted_observations: bool,
) -> dict[str, Any]:
    transition_kind = _require_transition_kind(transition_kind, allow_genesis=False)
    state = copy.deepcopy(_validate_state(
        dict(predecessor_state),
        allow_adopted_observations=allow_adopted_observations,
    ))
    digest = _require_digest(
        event_authorization_digest, "transition authorization digest"
    )
    if transition_kind == "UNRESTRICTED_REVIEW_CONSUMED":
        if state["unrestricted_review_count"] >= MAX_UNRESTRICTED_REVIEWS:
            raise LifecycleAuthorityError("unrestricted-review budget is exhausted")
        state["unrestricted_review_count"] += 1
    elif transition_kind == "REMEDIATION_COMPLETED":
        if state["unrestricted_review_count"] != MAX_UNRESTRICTED_REVIEWS:
            raise LifecycleAuthorityError("remediation requires the unrestricted review")
        if state["remediation_cycle_count"] >= MAX_REMEDIATION_CYCLES:
            raise LifecycleAuthorityError("remediation budget is exhausted; Cycle 3 is forbidden")
        state["remediation_cycle_count"] += 1
    elif transition_kind == "DRAFT_TO_READY":
        if state["ready"] or state["unrestricted_review_count"] != MAX_UNRESTRICTED_REVIEWS:
            raise LifecycleAuthorityError("Draft-to-Ready transition is not permitted")
        state["draft"] = False
        state["ready"] = True
        state["ready_transition_count"] += 1
        state["ready_history"].append(
            _history_entry(transition_kind, digest, len(state["ready_history"]) + 1)
        )
    elif transition_kind == "READY_TO_DRAFT":
        if not state["ready"]:
            raise LifecycleAuthorityError("Ready-to-Draft transition is not permitted")
        state["draft"] = True
        state["ready"] = False
        state["ready_history"].append(
            _history_entry(transition_kind, digest, len(state["ready_history"]) + 1)
        )
    elif transition_kind == "EXCEPTIONAL_RECOVERY":
        if state["exceptional_recovery_count"] >= MAX_EXCEPTIONAL_RECOVERIES:
            raise LifecycleAuthorityError("exceptional recovery cannot be replayed")
        state["exceptional_recovery_count"] += 1
        state["exceptional_recovery_history"].append(
            _history_entry(
                transition_kind, digest, len(state["exceptional_recovery_history"]) + 1
            )
        )
    elif transition_kind == "EXCEPTIONAL_CONTINUATION":
        if state["exceptional_continuation_count"] >= MAX_EXCEPTIONAL_CONTINUATIONS:
            raise LifecycleAuthorityError("exceptional continuation cannot be replayed")
        state["exceptional_continuation_count"] += 1
        state["exceptional_continuation_history"].append(
            _history_entry(
                transition_kind,
                digest,
                len(state["exceptional_continuation_history"]) + 1,
            )
        )
    elif transition_kind == "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED":
        # Persist one exact authorization without manufacturing a review or
        # remediation counter and without creating another lifecycle cycle.
        pass
    return _validate_state(
        state, allow_adopted_observations=allow_adopted_observations
    )


def derive_state(
    predecessor_state: Mapping[str, Any],
    transition_kind: str,
    event_authorization_digest: str,
    **caller_assertions: Any,
) -> dict[str, Any]:
    """Derive the sole permitted next state; caller-supplied results are refused."""

    if caller_assertions:
        raise LifecycleAuthorityError(
            "caller-supplied resulting lifecycle state is forbidden"
        )
    return _derive_state(
        predecessor_state,
        transition_kind,
        event_authorization_digest,
        allow_adopted_observations=False,
    )


def create_transition_authorization(
    *,
    event_id: str,
    repository: str,
    delivery_issue: int,
    lifecycle_id: str,
    pull_request: int,
    predecessor_authority_digest: str | None,
    predecessor_head_sha: str | None,
    resulting_head_sha: str,
    transition_kind: str,
    replacement_pull_request: int | None,
    initialization_evidence_digest: str,
    signer_identity: str,
    signer: Signer,
) -> dict[str, Any]:
    """Create independently signed authorization for one exact transition."""

    transition_kind = _require_transition_kind(transition_kind)
    fields: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "domain": EVENT_DOMAIN,
        "event_id": _require_identity(event_id, "event identity"),
        "repository": _require_repository(repository),
        "delivery_issue": _require_positive_int(delivery_issue, "delivery issue"),
        "lifecycle_id": _require_identity(lifecycle_id, "lifecycle identity"),
        "pull_request": _require_positive_int(pull_request, "pull request"),
        "predecessor_authority_digest": predecessor_authority_digest,
        "predecessor_head_sha": predecessor_head_sha,
        "resulting_head_sha": _require_oid(resulting_head_sha, "resulting head"),
        "transition_kind": transition_kind,
        "replacement_pull_request": replacement_pull_request,
        "initialization_evidence_digest": _require_digest(
            initialization_evidence_digest, "initialization evidence"
        ),
        "signer_identity": _require_identity(signer_identity, "event signer"),
    }
    _validate_event_semantics(fields)
    signature = _normalize_signature(
        signer(canonical_json_bytes(fields), EVENT_DOMAIN), fields["signer_identity"]
    )
    signed = {**fields, "signature": signature}
    return {**signed, "event_digest": digest_json(signed)}


def _validate_event_semantics(event: Mapping[str, Any]) -> None:
    transition = event["transition_kind"]
    predecessor_digest = event["predecessor_authority_digest"]
    predecessor_head = event["predecessor_head_sha"]
    replacement = event["replacement_pull_request"]
    initialization_digest = _require_digest(
        event["initialization_evidence_digest"], "initialization evidence"
    )
    if transition == "INITIALIZED_DRAFT":
        if predecessor_digest is not None or predecessor_head is not None or replacement is not None:
            raise LifecycleAuthorityError("genesis cannot claim a predecessor or replacement")
        if event["lifecycle_id"] != delivery_initialization_lifecycle_id(
            initialization_digest
        ):
            raise LifecycleAuthorityError(
                "genesis lifecycle identity is not derived from initialization"
            )
        if event["event_id"] != f"genesis:{initialization_digest}":
            raise LifecycleAuthorityError(
                "genesis event identity is not canonical for initialization"
            )
    else:
        _require_digest(predecessor_digest, "predecessor authority digest")
        _require_oid(predecessor_head, "predecessor head")
    if transition == "PR_REBOUND":
        replacement_value = _require_positive_int(replacement, "replacement pull request")
        if replacement_value == event["pull_request"]:
            raise LifecycleAuthorityError("replacement pull request must change")
    elif replacement is not None:
        raise LifecycleAuthorityError("only PR rebinding may name a replacement pull request")
    if transition in {
        "INITIALIZED_DRAFT",
        "UNRESTRICTED_REVIEW_CONSUMED",
        "DRAFT_TO_READY",
        "READY_TO_DRAFT",
        "PR_REBOUND",
        "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
    } and predecessor_head is not None and event["resulting_head_sha"] != predecessor_head:
        raise LifecycleAuthorityError("selected transition cannot advance the delivery head")
    if transition in {"HEAD_ADVANCED", "REMEDIATION_COMPLETED"} and (
        event["resulting_head_sha"] == predecessor_head
    ):
        raise LifecycleAuthorityError("selected transition requires a new delivery head")


def _verify_transition_authorization(
    value: Any,
    *,
    accepted_signers: frozenset[str],
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    event = _require_closed(value, EVENT_FIELDS, "transition authorization")
    if event["schema_version"] != SCHEMA_VERSION:
        raise LifecycleAuthorityError("unknown transition-authorization version")
    if event["kind"] != EVENT_KIND or event["domain"] != EVENT_DOMAIN:
        raise LifecycleAuthorityError("unknown transition-authorization kind or domain")
    _require_transition_kind(event["transition_kind"])
    _require_identity(event["event_id"], "event identity")
    _require_repository(event["repository"])
    _require_positive_int(event["delivery_issue"], "delivery issue")
    _require_identity(event["lifecycle_id"], "lifecycle identity")
    _require_positive_int(event["pull_request"], "pull request")
    _require_oid(event["resulting_head_sha"], "resulting head")
    _require_digest(event["initialization_evidence_digest"], "initialization evidence")
    signer_identity = _require_identity(event["signer_identity"], "event signer")
    _validate_event_semantics(event)
    signed = {key: copy.deepcopy(item) for key, item in event.items() if key != "event_digest"}
    if _require_digest(event["event_digest"], "event digest") != digest_json(signed):
        raise LifecycleAuthorityError("transition-authorization digest mismatch")
    unsigned = _unsigned(event, "event_digest", "signature")
    _verify_signature(
        canonical_json_bytes(unsigned),
        event["signature"],
        signer_identity,
        EVENT_DOMAIN,
        accepted_signers,
        signature_verifier,
    )
    return copy.deepcopy(event)


def _authority_unsigned_fields(
    *, event: Mapping[str, Any], predecessor: Mapping[str, Any] | None, state: Mapping[str, Any]
) -> dict[str, Any]:
    transition = event["transition_kind"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": AUTHORITY_KIND,
        "domain": AUTHORITY_DOMAIN,
        "repository": event["repository"],
        "delivery_issue": event["delivery_issue"],
        "lifecycle_id": event["lifecycle_id"],
        "pull_request": (
            event["replacement_pull_request"]
            if transition == "PR_REBOUND"
            else event["pull_request"]
        ),
        "head_sha": event["resulting_head_sha"],
        "predecessor_head_sha": event["predecessor_head_sha"],
        "predecessor_authority_digest": event["predecessor_authority_digest"],
        "transition_kind": transition,
        "event_authorization_digest": event["event_digest"],
        "initialization_evidence_digest": event["initialization_evidence_digest"],
        "state_before": None if predecessor is None else copy.deepcopy(predecessor["state_after"]),
        "state_after": copy.deepcopy(state),
    }


def issue_lifecycle_authority(
    *,
    predecessor_chain: Sequence[Mapping[str, Any]],
    transition_authorizations: Sequence[Mapping[str, Any]],
    authorization: Mapping[str, Any],
    signer_identity: str,
    authority_signer: Signer,
    accepted_event_signers: frozenset[str],
    accepted_authority_signers: frozenset[str],
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    """Verify predecessor/event authority, derive state, and sign one snapshot."""

    event = _verify_transition_authorization(
        authorization,
        accepted_signers=accepted_event_signers,
        signature_verifier=signature_verifier,
    )
    predecessor: Mapping[str, Any] | None = None
    if event["transition_kind"] == "INITIALIZED_DRAFT":
        if predecessor_chain or transition_authorizations:
            raise LifecycleAuthorityError("genesis must be the sole chain root")
        state = initial_state()
    else:
        if not predecessor_chain:
            raise LifecycleAuthorityError("non-genesis authority requires its predecessor chain")
        verified = _verify_lifecycle_authority_objects(
            predecessor_chain,
            transition_authorizations,
            accepted_event_signers=accepted_event_signers,
            accepted_authority_signers=accepted_authority_signers,
            signature_verifier=signature_verifier,
        )
        predecessor = predecessor_chain[-1]
        if (
            event["repository"] != verified.repository
            or event["delivery_issue"] != verified.delivery_issue
            or event["lifecycle_id"] != verified.lifecycle_id
            or event["pull_request"] != verified.pull_request
            or event["predecessor_head_sha"] != verified.head_sha
            or event["predecessor_authority_digest"] != verified.authority_digest
            or event["initialization_evidence_digest"]
            != predecessor_chain[-1]["initialization_evidence_digest"]
        ):
            raise LifecycleAuthorityError("transition authorization does not continue exact predecessor")
        state = derive_state(
            verified.state, event["transition_kind"], event["event_digest"]
        )
    fields = _authority_unsigned_fields(event=event, predecessor=predecessor, state=state)
    fields["signer_identity"] = _require_identity(signer_identity, "authority signer")
    if fields["signer_identity"] not in accepted_authority_signers:
        raise LifecycleAuthorityError("authority signer is not independently accepted")
    signature = _normalize_signature(
        authority_signer(canonical_json_bytes(fields), AUTHORITY_DOMAIN),
        fields["signer_identity"],
    )
    signed = {**fields, "signature": signature}
    return {**signed, "authority_digest": digest_json(signed)}


def _verify_authority_shape(
    value: Any,
    *,
    accepted_signers: frozenset[str],
    signature_verifier: SignatureVerifier,
    allow_adopted_observations: bool = False,
) -> dict[str, Any]:
    fields = set(value) if isinstance(value, Mapping) else set()
    has_current_evidence = fields == AUTHORITY_FIELDS | {"current_head_evidence"}
    if has_current_evidence and not allow_adopted_observations:
        raise LifecycleAuthorityError(
            "ordinary lifecycle authority cannot carry adopted current evidence"
        )
    authority = _require_closed(
        value,
        AUTHORITY_FIELDS | ({"current_head_evidence"} if has_current_evidence else set()),
        "lifecycle authority",
    )
    if authority["schema_version"] != SCHEMA_VERSION:
        raise LifecycleAuthorityError("unknown lifecycle-authority version")
    if authority["kind"] != AUTHORITY_KIND or authority["domain"] != AUTHORITY_DOMAIN:
        raise LifecycleAuthorityError("unknown lifecycle-authority kind or domain")
    _require_repository(authority["repository"])
    _require_positive_int(authority["delivery_issue"], "delivery issue")
    _require_identity(authority["lifecycle_id"], "lifecycle identity")
    _require_positive_int(authority["pull_request"], "pull request")
    _require_oid(authority["head_sha"], "authority head")
    _require_transition_kind(authority["transition_kind"])
    _require_digest(authority["event_authorization_digest"], "event authorization digest")
    _require_digest(
        authority["initialization_evidence_digest"], "initialization evidence"
    )
    if authority["predecessor_authority_digest"] is not None:
        _require_digest(authority["predecessor_authority_digest"], "predecessor digest")
    if authority["predecessor_head_sha"] is not None:
        _require_oid(authority["predecessor_head_sha"], "predecessor head")
    if authority["state_before"] is not None:
        _validate_state(
            authority["state_before"],
            allow_adopted_observations=allow_adopted_observations,
        )
    _validate_state(
        authority["state_after"],
        allow_adopted_observations=allow_adopted_observations,
    )
    if has_current_evidence:
        current = _require_closed(
            authority["current_head_evidence"],
            CURRENT_HEAD_EVIDENCE_FIELDS,
            "adopted current-head evidence",
        )
        if current["head_sha"] != authority["head_sha"]:
            raise LifecycleAuthorityError(
                "adopted current-head evidence does not bind authority head"
            )
        _require_oid(current["tree_sha"], "adopted current tree")
        for field in (
            "validation_receipt_digest",
            "source_validation_evidence_digest",
            "final_attestation_digest",
        ):
            _require_digest(current[field], f"adopted current {field}")
    signer = _require_identity(authority["signer_identity"], "authority signer")
    signed = {
        key: copy.deepcopy(item) for key, item in authority.items() if key != "authority_digest"
    }
    if _require_digest(authority["authority_digest"], "authority digest") != digest_json(signed):
        raise LifecycleAuthorityError("lifecycle-authority digest mismatch")
    unsigned = _unsigned(authority, "authority_digest", "signature")
    _verify_signature(
        canonical_json_bytes(unsigned),
        authority["signature"],
        signer,
        AUTHORITY_DOMAIN,
        accepted_signers,
        signature_verifier,
    )
    return copy.deepcopy(authority)


def _verify_lifecycle_authority_objects(
    authority_chain: Sequence[Mapping[str, Any]],
    transition_authorizations: Sequence[Mapping[str, Any]],
    *,
    accepted_event_signers: frozenset[str],
    accepted_authority_signers: frozenset[str],
    signature_verifier: SignatureVerifier,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify parsed objects with an already authenticated internal trust context."""

    if not authority_chain or len(authority_chain) != len(transition_authorizations):
        raise LifecycleAuthorityError("complete authority and event chains are required")
    events: list[dict[str, Any]] = []
    event_digests: set[str] = set()
    event_ids: set[str] = set()
    for value in transition_authorizations:
        event = _verify_transition_authorization(
            value,
            accepted_signers=accepted_event_signers,
            signature_verifier=signature_verifier,
        )
        if event["event_digest"] in event_digests or event["event_id"] in event_ids:
            raise LifecycleAuthorityError("transition authorization was replayed")
        event_digests.add(event["event_digest"])
        event_ids.add(event["event_id"])
        events.append(event)

    previous: dict[str, Any] | None = None
    current_state: dict[str, Any] | None = None
    verified_authority: dict[str, Any] | None = None
    for index, raw in enumerate(authority_chain):
        item = _verify_authority_shape(
            raw,
            accepted_signers=accepted_authority_signers,
            signature_verifier=signature_verifier,
        )
        event = events[index]
        if item["event_authorization_digest"] != event["event_digest"]:
            raise LifecycleAuthorityError("authority does not bind its exact event authorization")
        if index == 0:
            if item["transition_kind"] != "INITIALIZED_DRAFT":
                raise LifecycleAuthorityError("authority chain is truncated before typed genesis")
            if item["predecessor_authority_digest"] is not None or item["state_before"] is not None:
                raise LifecycleAuthorityError("genesis authority claims a predecessor")
            if item["lifecycle_id"] != delivery_initialization_lifecycle_id(
                item["initialization_evidence_digest"]
            ):
                raise LifecycleAuthorityError("genesis lifecycle identity is not anchored")
            derived = initial_state()
        else:
            if previous is None or current_state is None:
                raise LifecycleAuthorityError("authority predecessor is unavailable")
            if (
                item["predecessor_authority_digest"] != previous["authority_digest"]
                or item["predecessor_head_sha"] != previous["head_sha"]
                or item["repository"] != previous["repository"]
                or item["delivery_issue"] != previous["delivery_issue"]
                or item["lifecycle_id"] != previous["lifecycle_id"]
                or item["initialization_evidence_digest"]
                != previous["initialization_evidence_digest"]
                or item["state_before"] != current_state
            ):
                raise LifecycleAuthorityError("authority predecessor continuity is invalid")
            expected_event_pr = previous["pull_request"]
            if event["pull_request"] != expected_event_pr:
                raise LifecycleAuthorityError("transition event was replayed across pull requests")
            derived = derive_state(
                current_state, item["transition_kind"], item["event_authorization_digest"]
            )
        if (
            event["repository"] != item["repository"]
            or event["delivery_issue"] != item["delivery_issue"]
            or event["lifecycle_id"] != item["lifecycle_id"]
            or event["resulting_head_sha"] != item["head_sha"]
            or event["predecessor_authority_digest"] != item["predecessor_authority_digest"]
            or event["predecessor_head_sha"] != item["predecessor_head_sha"]
            or event["transition_kind"] != item["transition_kind"]
            or event["initialization_evidence_digest"]
            != item["initialization_evidence_digest"]
            or item["state_after"] != derived
        ):
            raise LifecycleAuthorityError("authority state or event binding was not derived")
        resulting_pr = (
            event["replacement_pull_request"]
            if event["transition_kind"] == "PR_REBOUND"
            else event["pull_request"]
        )
        if item["pull_request"] != resulting_pr:
            raise LifecycleAuthorityError("authority pull-request continuity is invalid")
        previous = item
        current_state = derived
        verified_authority = item

    if verified_authority is None or current_state is None:
        raise LifecycleAuthorityError("lifecycle authority is missing")
    result = VerifiedLifecycleAuthority(
        authority_digest=verified_authority["authority_digest"],
        repository=verified_authority["repository"],
        delivery_issue=verified_authority["delivery_issue"],
        lifecycle_id=verified_authority["lifecycle_id"],
        initialization_evidence_digest=verified_authority[
            "initialization_evidence_digest"
        ],
        pull_request=verified_authority["pull_request"],
        head_sha=verified_authority["head_sha"],
        state=copy.deepcopy(current_state),
        authority_signer_identity=verified_authority["signer_identity"],
    )
    if expected is not None:
        _compare_expected(result, expected)
    return result


def serialize_lifecycle_evidence(
    *,
    delivery_initialization: Mapping[str, Any],
    transition_authorizations: Sequence[Mapping[str, Any]],
    authority_chain: Sequence[Mapping[str, Any]],
) -> bytes:
    """Serialize one complete lifecycle chain for the maintained public verifier."""

    return canonical_json_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": BUNDLE_KIND,
            "domain": BUNDLE_DOMAIN,
            "delivery_initialization": copy.deepcopy(delivery_initialization),
            "transition_authorizations": copy.deepcopy(list(transition_authorizations)),
            "authority_chain": copy.deepcopy(list(authority_chain)),
        }
    )


def _verify_lifecycle_bundle_from_initialization(
    bundle: Any,
    initialization: Mapping[str, Any],
    policy: LifecycleTrustPolicy,
    signature_verifier: SignatureVerifier,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify one complete #750 chain after its root boundary is authenticated."""

    bundle = _require_closed(bundle, BUNDLE_FIELDS, "lifecycle evidence")
    if bundle["schema_version"] != SCHEMA_VERSION:
        raise LifecycleAuthorityError("unknown lifecycle-evidence version")
    if bundle["kind"] != BUNDLE_KIND or bundle["domain"] != BUNDLE_DOMAIN:
        raise LifecycleAuthorityError("unknown lifecycle-evidence kind or domain")
    authorities = bundle["authority_chain"]
    events = bundle["transition_authorizations"]
    if not isinstance(authorities, list) or not isinstance(events, list):
        raise LifecycleAuthorityError("complete lifecycle evidence chains are required")
    result = _verify_lifecycle_authority_objects(
        authorities,
        events,
        accepted_event_signers=policy.transition_signer_identities,
        accepted_authority_signers=policy.authority_signer_identities,
        signature_verifier=signature_verifier,
        expected=expected,
    )
    first_event = events[0]
    first_authority = authorities[0]
    digest = initialization["initialization_digest"]
    if (
        first_event["initialization_evidence_digest"] != digest
        or first_authority["initialization_evidence_digest"] != digest
        or first_event["repository"] != initialization["repository"]
        or first_event["delivery_issue"] != initialization["delivery_issue"]
        or first_event["pull_request"] != initialization["pull_request"]
        or first_event["resulting_head_sha"] != initialization["initial_head_sha"]
        or result.lifecycle_id != delivery_initialization_lifecycle_id(digest)
    ):
        raise LifecycleAuthorityError(
            "genesis does not bind the authenticated delivery initialization"
        )
    return result


def _verify_unanchored_lifecycle_bundle(
    bundle: Any,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify #750 derivation without treating it as an enrollment trust root."""

    bundle = _require_closed(bundle, BUNDLE_FIELDS, "lifecycle evidence")
    initialization_value = bundle["delivery_initialization"]
    if not isinstance(initialization_value, dict):
        raise LifecycleAuthorityError("delivery initialization is malformed")
    repository = _require_repository(initialization_value.get("repository"))
    policy = _load_lifecycle_trust_policy(repository)
    signature_verifier = _policy_signature_verifier(policy)
    initialization = _verify_delivery_initialization(
        initialization_value,
        policy=policy,
        signature_verifier=signature_verifier,
        require_maintained_anchor=False,
    )
    return _verify_lifecycle_bundle_from_initialization(
        bundle, initialization, policy, signature_verifier, expected
    )


def verify_native_lifecycle_for_genesis_admission(
    serialized_evidence: bytes | str,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify native derivation without allowing it to admit its own genesis."""

    if not isinstance(serialized_evidence, (bytes, str)):
        raise LifecycleAuthorityError(
            "native genesis admission requires canonical serialized lifecycle evidence"
        )
    bundle = _require_closed(
        _load_canonical_json(serialized_evidence, "native lifecycle evidence"),
        BUNDLE_FIELDS,
        "lifecycle evidence",
    )
    return _verify_unanchored_lifecycle_bundle(bundle, expected)


def _verify_native_lifecycle_bundle_for_journal(
    bundle: Any,
    expected: ExpectedLifecycle | None = None,
    admitted_initialization: Mapping[str, Any] | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify an adopted native chain without selecting CURRENT from static tip state."""

    bundle = _require_closed(bundle, BUNDLE_FIELDS, "lifecycle evidence")
    initialization_value = bundle["delivery_initialization"]
    if not isinstance(initialization_value, dict):
        raise LifecycleAuthorityError("delivery initialization is malformed")
    repository = _require_repository(initialization_value.get("repository"))
    policy = _load_lifecycle_trust_policy(repository)
    signature_verifier = _policy_signature_verifier(policy)
    if admitted_initialization is None:
        raise LifecycleAuthorityError("native genesis is not independently admitted")
    initialization = _verify_delivery_initialization(
        admitted_initialization,
        policy=policy,
        signature_verifier=signature_verifier,
        require_maintained_anchor=False,
    )
    if initialization != initialization_value:
        raise LifecycleAuthorityError(
            "native genesis admission does not match lifecycle initialization"
        )
    return _verify_lifecycle_bundle_from_initialization(
        bundle, initialization, policy, signature_verifier, expected
    )


def _legacy_checkpoint_state(value: Any) -> dict[str, Any]:
    state = copy.deepcopy(_require_closed(value, STATE_FIELDS, "legacy checkpoint state"))
    _validate_state(state)
    return state


def _parse_adoption_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ):
        raise LifecycleAuthorityError(f"{label} is invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise LifecycleAuthorityError(f"{label} is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise LifecycleAuthorityError(f"{label} is not canonical UTC")
    return parsed


def _require_adoption_timestamp(value: Any, label: str) -> str:
    _parse_adoption_timestamp(value, label)
    return value


def _normalize_observed_pre_enrollment_history(
    value: Any, *, expected_head: str, intended_state: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Normalize factual observations without recasting them as lifecycle events."""

    if not isinstance(value, list) or not value:
        raise LifecycleAuthorityError("observed pre-enrollment history is required")
    allowed = frozenset(
        {
            "PR_CREATED_DRAFT", "DRAFT_TO_READY_OBSERVED",
            "READY_TO_DRAFT_OBSERVED", "REVIEW_SUBMITTED",
            "REMEDIATION_HEAD_OBSERVED", "EXCEPTIONAL_RECOVERY_OBSERVED",
            "EXCEPTIONAL_CONTINUATION_OBSERVED", "HEAD_ADVANCED_OBSERVED",
        }
    )
    normalized: list[dict[str, Any]] = []
    previous_instant: datetime | None = None
    effective_head: str | None = None
    observed_heads: set[str] = set()
    head_changing_observations = frozenset(
        {
            "REMEDIATION_HEAD_OBSERVED",
            "EXCEPTIONAL_RECOVERY_OBSERVED",
            "EXCEPTIONAL_CONTINUATION_OBSERVED",
            "HEAD_ADVANCED_OBSERVED",
        }
    )
    for sequence, raw in enumerate(value, 1):
        item = _require_closed(
            raw, OBSERVED_HISTORY_FIELDS, "observed pre-enrollment history entry"
        )
        kind = item["kind"]
        timestamp = _require_adoption_timestamp(item["observed_at"], "observation time")
        instant = _parse_adoption_timestamp(timestamp, "observation time")
        head = _require_oid(item["head_sha"], "observed head")
        reviewed_head = item["reviewed_head_sha"]
        if (
            item["sequence"] != sequence
            or isinstance(item["sequence"], bool)
            or kind not in allowed
            or (previous_instant is not None and instant < previous_instant)
            or (kind == "REVIEW_SUBMITTED") != (reviewed_head is not None)
        ):
            raise LifecycleAuthorityError(
                "observed pre-enrollment chronology is not canonical"
            )
        if reviewed_head is not None:
            reviewed_head = _require_oid(reviewed_head, "observed reviewed head")
        if kind == "REMEDIATION_HEAD_OBSERVED" and (
            head == effective_head or head in observed_heads
        ):
            raise LifecycleAuthorityError(
                "remediation observation must advance the delivery head"
            )
        if effective_head is None or kind in head_changing_observations:
            effective_head = head
        observed_heads.add(head)
        normalized.append(
            {
                "sequence": sequence,
                "kind": kind,
                "observed_at": timestamp,
                "head_sha": head,
                "reviewed_head_sha": reviewed_head,
            }
        )
        previous_instant = instant
    state = _validate_state(
        dict(intended_state), allow_adopted_observations=True
    )
    kinds = [item["kind"] for item in normalized]
    if kinds[0] != "PR_CREATED_DRAFT" or normalized[-1]["head_sha"] != expected_head:
        raise LifecycleAuthorityError(
            "observed pre-enrollment history does not bind the delivery boundary"
        )
    draft = True
    ready_transitions = 0
    for kind in kinds[1:]:
        if kind == "DRAFT_TO_READY_OBSERVED":
            if not draft:
                raise LifecycleAuthorityError("observed Ready chronology contains hidden churn")
            draft = False
            ready_transitions += 1
        elif kind == "READY_TO_DRAFT_OBSERVED":
            if draft:
                raise LifecycleAuthorityError("observed Draft chronology contains hidden churn")
            draft = True
    if (
        kinds.count("PR_CREATED_DRAFT") != 1
        or kinds.count("REVIEW_SUBMITTED") != state["unrestricted_review_count"]
        or kinds.count("REMEDIATION_HEAD_OBSERVED")
        != state["remediation_cycle_count"]
        or kinds.count("EXCEPTIONAL_RECOVERY_OBSERVED")
        != state["exceptional_recovery_count"]
        or kinds.count("EXCEPTIONAL_CONTINUATION_OBSERVED")
        != state["exceptional_continuation_count"]
        or ready_transitions != state["ready_transition_count"]
        or draft != state["draft"]
        or (not draft) != state["ready"]
    ):
        raise LifecycleAuthorityError(
            "observed pre-enrollment history does not authenticate intended state"
        )
    history_provenance = {
        "ready_history": [
            {
                "sequence": sequence,
                "transition_kind": (
                    "DRAFT_TO_READY"
                    if item["kind"] == "DRAFT_TO_READY_OBSERVED"
                    else "READY_TO_DRAFT"
                ),
                "observation_digest": digest_json(item),
            }
            for sequence, item in enumerate(
                (
                    entry for entry in normalized
                    if entry["kind"] in {
                        "DRAFT_TO_READY_OBSERVED", "READY_TO_DRAFT_OBSERVED"
                    }
                ),
                1,
            )
        ],
        "exceptional_recovery_history": [
            {
                "sequence": sequence,
                "transition_kind": "EXCEPTIONAL_RECOVERY",
                "observation_digest": digest_json(item),
            }
            for sequence, item in enumerate(
                (
                    entry for entry in normalized
                    if entry["kind"] == "EXCEPTIONAL_RECOVERY_OBSERVED"
                ),
                1,
            )
        ],
        "exceptional_continuation_history": [
            {
                "sequence": sequence,
                "transition_kind": "EXCEPTIONAL_CONTINUATION",
                "observation_digest": digest_json(item),
            }
            for sequence, item in enumerate(
                (
                    entry for entry in normalized
                    if entry["kind"] == "EXCEPTIONAL_CONTINUATION_OBSERVED"
                ),
                1,
            )
        ],
    }
    for field, expected_history in history_provenance.items():
        if state[field] != expected_history:
            raise LifecycleAuthorityError(
                "adopted history cannot claim ordinary authorization provenance"
            )
    return normalized


def authenticate_exact_state_adoption_external_evidence(
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    head_sha: str,
    tree_sha: str,
    pull_request_state: str,
    commit_signature_evidence: Mapping[str, Any],
    validation_evidence: VerifiedValidationEvidence,
    observed_pre_enrollment_history: Sequence[Mapping[str, Any]],
    intended_state: Mapping[str, Any],
) -> VerifiedExactStateAdoptionExternalEvidence:
    """Authenticate external artifacts before any adoption proof is assembled."""

    repository = _require_repository(repository)
    issue = _require_positive_int(delivery_issue, "adopted delivery issue")
    pr = _require_positive_int(pull_request, "adopted pull request")
    head = _require_oid(head_sha, "adopted head")
    tree = _require_oid(tree_sha, "adopted tree")
    if pull_request_state != "OPEN":
        raise LifecycleAuthorityError("adoption requires an open delivery")
    if not is_verified_validation_evidence(validation_evidence) or (
        validation_evidence.repository != repository
        or validation_evidence.pull_request_number != pr
        or validation_evidence.head_sha != head
        or validation_evidence.tree_sha != tree
    ):
        raise LifecycleAuthorityError(
            "adoption validation evidence does not bind the delivery"
        )
    commit = copy.deepcopy(dict(commit_signature_evidence))
    try:
        verified_commits = verify_commit_signatures(
            [commit], _load_delivery_signature_policy(repository)
        )
    except SecurityBlocker as exc:
        raise LifecycleAuthorityError(
            "adoption commit signature evidence is invalid"
        ) from exc
    if len(verified_commits) != 1 or verified_commits[0]["oid"] != head:
        raise LifecycleAuthorityError(
            "adoption commit signature evidence changed identity"
        )
    signature_evidence_digest = digest_json(verified_commits[0])
    state = _validate_state(
        dict(intended_state), allow_adopted_observations=True
    )
    history = _normalize_observed_pre_enrollment_history(
        list(observed_pre_enrollment_history),
        expected_head=head,
        intended_state=state,
    )
    supporting_digests = tuple(sorted({
        validation_evidence.validation_receipt_digest,
        validation_evidence.source_validation_evidence_digest,
        validation_evidence.final_attestation_digest,
        signature_evidence_digest,
        digest_json(history),
    }))
    return VerifiedExactStateAdoptionExternalEvidence(
        repository=repository,
        delivery_issue=issue,
        pull_request=pr,
        head_sha=head,
        tree_sha=tree,
        pull_request_state=pull_request_state,
        commit_signature_evidence_digest=signature_evidence_digest,
        validation_receipt_digest=validation_evidence.validation_receipt_digest,
        source_validation_evidence_digest=(
            validation_evidence.source_validation_evidence_digest
        ),
        adoption_source_evidence_digest=validation_evidence.final_attestation_digest,
        observed_pre_enrollment_history=tuple(copy.deepcopy(history)),
        intended_state=copy.deepcopy(state),
        supporting_evidence_digests=supporting_digests,
        _verification_seal=_VERIFIED_EXACT_ADOPTION_EVIDENCE,
    )


def _assemble_exact_state_adoption_evidence(
    *, repository: str, delivery_issue: int, pull_request: int, head_sha: str,
    tree_sha: str, pull_request_state: str, commit_signature_evidence_digest: str,
    validation_receipt_digest: str, source_validation_evidence_digest: str,
    adoption_source_evidence_digest: str,
    observed_pre_enrollment_history: Sequence[Mapping[str, Any]],
    intended_state: Mapping[str, Any], adoption_timestamp: str,
    supporting_evidence_digests: Sequence[str],
) -> dict[str, Any]:
    """Assemble canonical proof fields from already authenticated evidence."""

    repository = _require_repository(repository)
    issue = _require_positive_int(delivery_issue, "adopted delivery issue")
    pr = _require_positive_int(pull_request, "adopted pull request")
    head = _require_oid(head_sha, "adopted head")
    tree = _require_oid(tree_sha, "adopted tree")
    if pull_request_state != "OPEN":
        raise LifecycleAuthorityError("adoption requires an open signed delivery")
    state = _validate_state(
        dict(intended_state), allow_adopted_observations=True
    )
    history = _normalize_observed_pre_enrollment_history(
        list(observed_pre_enrollment_history), expected_head=head, intended_state=state
    )
    timestamp = _require_adoption_timestamp(adoption_timestamp, "adoption timestamp")
    observation_instant = _parse_adoption_timestamp(
        history[-1]["observed_at"], "observation time"
    )
    if _parse_adoption_timestamp(timestamp, "adoption timestamp") < observation_instant:
        raise LifecycleAuthorityError("adoption cannot be backdated before observation")
    supporting = list(supporting_evidence_digests)
    if not supporting or len(supporting) != len(set(supporting)):
        raise LifecycleAuthorityError("adoption supporting evidence is ambiguous")
    for digest in supporting:
        _require_digest(digest, "adoption supporting evidence")
    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXACT_ADOPTION_EVIDENCE_KIND,
        "domain": EXACT_ADOPTION_EVIDENCE_DOMAIN,
        "proof_version": SCHEMA_VERSION,
        "repository": repository,
        "delivery_issue": issue,
        "pull_request": pr,
        "head_sha": head,
        "tree_sha": tree,
        "pull_request_state": pull_request_state,
        "commit_signature_status": "VERIFIED",
        "commit_signature_evidence_digest": _require_digest(
            commit_signature_evidence_digest, "commit signature evidence"
        ),
        "validation_receipt_digest": _require_digest(
            validation_receipt_digest, "adoption validation receipt"
        ),
        "source_validation_evidence_digest": _require_digest(
            source_validation_evidence_digest, "source validation evidence"
        ),
        "adoption_source_evidence_digest": _require_digest(
            adoption_source_evidence_digest, "adoption-time source evidence"
        ),
        "observed_pre_enrollment_history": history,
        "observed_history_digest": digest_json(history),
        "intended_state": copy.deepcopy(state),
        "intended_state_digest": digest_json(state),
        "adoption_timestamp": timestamp,
        "supporting_evidence_digests": supporting,
        "ordinary_lifecycle_events": [],
        "head_advanced_count": sum(
            item["kind"] == "HEAD_ADVANCED_OBSERVED" for item in history
        ),
        "head_advanced_history_digest": digest_json(
            [item for item in history if item["kind"] == "HEAD_ADVANCED_OBSERVED"]
        ),
    }
    return {**fields, "adoption_evidence_digest": digest_json(fields)}


def create_exact_state_adoption_evidence(
    *, verified_external_evidence: VerifiedExactStateAdoptionExternalEvidence,
    adoption_timestamp: str,
) -> dict[str, Any]:
    """Create canonical facts for one exact pre-enrollment adoption boundary."""

    evidence = verified_external_evidence
    if (
        not isinstance(evidence, VerifiedExactStateAdoptionExternalEvidence)
        or evidence._verification_seal is not _VERIFIED_EXACT_ADOPTION_EVIDENCE
    ):
        raise LifecycleAuthorityError(
            "exact adoption requires verifier-derived external evidence"
        )
    return _assemble_exact_state_adoption_evidence(
        repository=evidence.repository,
        delivery_issue=evidence.delivery_issue,
        pull_request=evidence.pull_request,
        head_sha=evidence.head_sha,
        tree_sha=evidence.tree_sha,
        pull_request_state=evidence.pull_request_state,
        commit_signature_evidence_digest=(
            evidence.commit_signature_evidence_digest
        ),
        validation_receipt_digest=evidence.validation_receipt_digest,
        source_validation_evidence_digest=evidence.source_validation_evidence_digest,
        adoption_source_evidence_digest=evidence.adoption_source_evidence_digest,
        observed_pre_enrollment_history=evidence.observed_pre_enrollment_history,
        intended_state=evidence.intended_state,
        adoption_timestamp=adoption_timestamp,
        supporting_evidence_digests=evidence.supporting_evidence_digests,
    )


def _verify_exact_state_adoption_evidence(value: Any) -> dict[str, Any]:
    evidence = _require_closed(
        value, EXACT_ADOPTION_EVIDENCE_FIELDS, "exact-state adoption evidence"
    )
    if (
        evidence["schema_version"] != SCHEMA_VERSION
        or evidence["proof_version"] != SCHEMA_VERSION
        or evidence["kind"] != EXACT_ADOPTION_EVIDENCE_KIND
        or evidence["domain"] != EXACT_ADOPTION_EVIDENCE_DOMAIN
        or evidence["ordinary_lifecycle_events"] != []
        or evidence["commit_signature_status"] != "VERIFIED"
    ):
        raise LifecycleAuthorityError("exact-state adoption evidence semantics are unknown")
    rebuilt = _assemble_exact_state_adoption_evidence(
        repository=evidence["repository"], delivery_issue=evidence["delivery_issue"],
        pull_request=evidence["pull_request"], head_sha=evidence["head_sha"],
        tree_sha=evidence["tree_sha"], pull_request_state=evidence["pull_request_state"],
        commit_signature_evidence_digest=evidence[
            "commit_signature_evidence_digest"
        ],
        validation_receipt_digest=evidence["validation_receipt_digest"],
        source_validation_evidence_digest=evidence["source_validation_evidence_digest"],
        adoption_source_evidence_digest=evidence["adoption_source_evidence_digest"],
        observed_pre_enrollment_history=evidence["observed_pre_enrollment_history"],
        intended_state=evidence["intended_state"],
        adoption_timestamp=evidence["adoption_timestamp"],
        supporting_evidence_digests=evidence["supporting_evidence_digests"],
    )
    if rebuilt != evidence:
        raise LifecycleAuthorityError("exact-state adoption evidence binding changed")
    return rebuilt


def create_exact_state_adoption_authorization(
    *, adoption_evidence: Mapping[str, Any], authorization_id: str,
    bounded_uses: int, signer_identity: str, signer: Signer,
) -> dict[str, Any]:
    """Sign one exact-scope, one-use authorization independently of the proof."""

    evidence = _verify_exact_state_adoption_evidence(adoption_evidence)
    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXACT_ADOPTION_AUTHORIZATION_KIND,
        "domain": EXACT_ADOPTION_AUTHORIZATION_DOMAIN,
        "proof_version": SCHEMA_VERSION,
        "repository": evidence["repository"],
        "delivery_issue": evidence["delivery_issue"],
        "pull_request": evidence["pull_request"],
        "head_sha": evidence["head_sha"],
        "tree_sha": evidence["tree_sha"],
        "adoption_evidence_digest": evidence["adoption_evidence_digest"],
        "intended_state_digest": evidence["intended_state_digest"],
        "authorization_id": _require_identity(authorization_id, "adoption authorization"),
        "bounded_uses": bounded_uses,
        "signer_identity": _require_identity(signer_identity, "adoption authorization signer"),
    }
    if bounded_uses != 1 or isinstance(bounded_uses, bool):
        raise LifecycleAuthorityError("exact-state adoption authorization must have one use")
    signature = _normalize_signature(
        signer(canonical_json_bytes(fields), EXACT_ADOPTION_AUTHORIZATION_DOMAIN),
        fields["signer_identity"],
    )
    signed = {**fields, "signature": signature}
    return {**signed, "authorization_digest": digest_json(signed)}


def create_exact_state_adoption_proof(
    *, adoption_evidence: Mapping[str, Any], authorization: Mapping[str, Any],
    signer_identity: str, signer: Signer,
) -> dict[str, Any]:
    """Create the signed adoption genesis; no ordinary history is synthesized."""

    evidence = _verify_exact_state_adoption_evidence(adoption_evidence)
    authorization_item = copy.deepcopy(dict(authorization))
    fields = {
        **{key: copy.deepcopy(value) for key, value in evidence.items()
           if key not in {"kind", "domain"}},
        "kind": EXACT_ADOPTION_PROOF_KIND,
        "domain": EXACT_ADOPTION_PROOF_DOMAIN,
        "historical_proof_mode": EXACT_ADOPTION_PROOF_MODE,
        "lifecycle_id": f"lifecycle-adoption:{evidence['adoption_evidence_digest']}",
        "authorization": authorization_item,
        "authorization_digest": authorization_item.get("authorization_digest"),
        "signer_identity": _require_identity(signer_identity, "exact adoption signer"),
    }
    signature = _normalize_signature(
        signer(canonical_json_bytes(fields), EXACT_ADOPTION_PROOF_DOMAIN),
        fields["signer_identity"],
    )
    signed = {**fields, "signature": signature}
    return {**signed, "proof_digest": digest_json(signed)}


def verify_exact_state_adoption_proof(
    proof_value: Any, expected: ExpectedLifecycle | None = None
) -> VerifiedLifecycleAuthority:
    """Authenticate one exact adopted baseline using maintained adoption trust."""

    proof = _require_closed(
        proof_value, EXACT_ADOPTION_PROOF_FIELDS, "exact-state adoption proof"
    )
    if (
        proof["schema_version"] != SCHEMA_VERSION
        or proof["proof_version"] != SCHEMA_VERSION
        or proof["kind"] != EXACT_ADOPTION_PROOF_KIND
        or proof["domain"] != EXACT_ADOPTION_PROOF_DOMAIN
        or proof["historical_proof_mode"] != EXACT_ADOPTION_PROOF_MODE
    ):
        raise LifecycleAuthorityError("exact-state adoption proof semantics are unknown")
    evidence = _verify_exact_state_adoption_evidence(
        {
            **{key: copy.deepcopy(proof[key]) for key in EXACT_ADOPTION_EVIDENCE_FIELDS},
            "kind": EXACT_ADOPTION_EVIDENCE_KIND,
            "domain": EXACT_ADOPTION_EVIDENCE_DOMAIN,
        }
    )
    expected_lifecycle = f"lifecycle-adoption:{evidence['adoption_evidence_digest']}"
    if proof["lifecycle_id"] != expected_lifecycle:
        raise LifecycleAuthorityError("exact-state adoption lifecycle identity changed")
    repository = evidence["repository"]
    policy = _load_lifecycle_trust_policy(repository)
    verifier = _policy_signature_verifier(policy)
    authorization = _require_closed(
        proof["authorization"], EXACT_ADOPTION_AUTHORIZATION_FIELDS,
        "exact-state adoption authorization",
    )
    if (
        authorization["schema_version"] != SCHEMA_VERSION
        or authorization["proof_version"] != SCHEMA_VERSION
        or authorization["kind"] != EXACT_ADOPTION_AUTHORIZATION_KIND
        or authorization["domain"] != EXACT_ADOPTION_AUTHORIZATION_DOMAIN
        or authorization["bounded_uses"] != 1
        or isinstance(authorization["bounded_uses"], bool)
        or any(
            authorization[field] != evidence[field]
            for field in (
                "repository", "delivery_issue", "pull_request", "head_sha",
                "tree_sha", "adoption_evidence_digest", "intended_state_digest",
            )
        )
    ):
        raise LifecycleAuthorityError("exact-state adoption authorization scope changed")
    authorization_signer = _require_identity(
        authorization["signer_identity"], "adoption authorization signer"
    )
    authorization_signed = {
        key: copy.deepcopy(value) for key, value in authorization.items()
        if key != "authorization_digest"
    }
    authorization_digest = _require_digest(
        authorization["authorization_digest"], "adoption authorization"
    )
    if (
        authorization_digest != digest_json(authorization_signed)
        or proof["authorization_digest"] != authorization_digest
    ):
        raise LifecycleAuthorityError("exact-state adoption authorization digest mismatch")
    _verify_signature(
        canonical_json_bytes(
            _unsigned(authorization, "authorization_digest", "signature")
        ),
        authorization["signature"], authorization_signer,
        EXACT_ADOPTION_AUTHORIZATION_DOMAIN,
        policy.legacy_adoption_signer_identities, verifier,
    )
    proof_signer = _require_identity(proof["signer_identity"], "exact adoption signer")
    proof_signed = {
        key: copy.deepcopy(value) for key, value in proof.items()
        if key != "proof_digest"
    }
    proof_digest = _require_digest(proof["proof_digest"], "exact adoption proof")
    if proof_digest != digest_json(proof_signed):
        raise LifecycleAuthorityError("exact-state adoption proof digest mismatch")
    _verify_signature(
        canonical_json_bytes(_unsigned(proof, "proof_digest", "signature")),
        proof["signature"], proof_signer, EXACT_ADOPTION_PROOF_DOMAIN,
        policy.legacy_adoption_signer_identities, verifier,
    )
    result = VerifiedLifecycleAuthority(
        authority_digest=proof_digest,
        repository=repository,
        delivery_issue=evidence["delivery_issue"],
        lifecycle_id=expected_lifecycle,
        initialization_evidence_digest=evidence["adoption_evidence_digest"],
        pull_request=evidence["pull_request"],
        head_sha=evidence["head_sha"],
        state=copy.deepcopy(evidence["intended_state"]),
        authority_signer_identity=proof_signer,
        historical_proof_mode=EXACT_ADOPTION_PROOF_MODE,
        legacy_adoption_checkpoint_digest=proof_digest,
        tree_sha=evidence["tree_sha"],
        validation_receipt_digest=evidence["validation_receipt_digest"],
        source_validation_evidence_digest=evidence[
            "source_validation_evidence_digest"
        ],
        adoption_source_evidence_digest=evidence[
            "adoption_source_evidence_digest"
        ],
    )
    if expected is not None:
        _compare_expected(result, expected)
    return result


def serialize_exact_state_adoption_evidence(
    *, exact_state_adoption_proof: Mapping[str, Any],
    transition_authorizations: Sequence[Mapping[str, Any]] = (),
    authority_chain: Sequence[Mapping[str, Any]] = (),
) -> bytes:
    """Serialize one adopted genesis and its ordinary post-adoption successors."""

    return canonical_json_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": EXACT_ADOPTION_EVIDENCE_KIND,
            "domain": EXACT_ADOPTION_EVIDENCE_DOMAIN,
            "enrollment_mode": "EXACT_STATE_ADOPTION",
            "exact_state_adoption_proof": copy.deepcopy(
                dict(exact_state_adoption_proof)
            ),
            "transition_authorizations": copy.deepcopy(
                list(transition_authorizations)
            ),
            "authority_chain": copy.deepcopy(list(authority_chain)),
        }
    )


def _verify_exact_state_adoption_bundle(
    value: Any, expected: ExpectedLifecycle | None = None
) -> VerifiedLifecycleAuthority:
    bundle = _require_closed(
        value, EXACT_ADOPTION_PUBLICATION_FIELDS, "exact-state adoption lifecycle evidence"
    )
    if (
        bundle["schema_version"] != SCHEMA_VERSION
        or bundle["kind"] != EXACT_ADOPTION_EVIDENCE_KIND
        or bundle["domain"] != EXACT_ADOPTION_EVIDENCE_DOMAIN
        or bundle["enrollment_mode"] != "EXACT_STATE_ADOPTION"
    ):
        raise LifecycleAuthorityError("exact-state adoption lifecycle semantics are unknown")
    result = verify_exact_state_adoption_proof(
        bundle["exact_state_adoption_proof"]
    )
    events_raw = bundle["transition_authorizations"]
    authorities_raw = bundle["authority_chain"]
    if (
        not isinstance(events_raw, list)
        or not isinstance(authorities_raw, list)
        or len(events_raw) != len(authorities_raw)
    ):
        raise LifecycleAuthorityError("exact-state adoption successor chain is incomplete")
    policy = _load_lifecycle_trust_policy(result.repository)
    verifier = _policy_signature_verifier(policy)
    event_ids: set[str] = set()
    event_digests: set[str] = set()
    previous_digest = result.authority_digest
    previous_head = result.head_sha
    previous_pr = result.pull_request
    state = copy.deepcopy(result.state)
    last_signer = result.authority_signer_identity
    current_tree = result.tree_sha
    current_receipt = result.validation_receipt_digest
    current_source = result.source_validation_evidence_digest
    current_attestation = result.adoption_source_evidence_digest
    for raw_event, raw_authority in zip(events_raw, authorities_raw):
        event = _verify_transition_authorization(
            raw_event,
            accepted_signers=policy.transition_signer_identities,
            signature_verifier=verifier,
        )
        snapshot = _verify_authority_shape(
            raw_authority,
            accepted_signers=policy.authority_signer_identities,
            signature_verifier=verifier,
            allow_adopted_observations=True,
        )
        if (
            event["event_id"] in event_ids
            or event["event_digest"] in event_digests
            or event["transition_kind"] == "INITIALIZED_DRAFT"
            or event["repository"] != result.repository
            or event["delivery_issue"] != result.delivery_issue
            or event["lifecycle_id"] != result.lifecycle_id
            or event["pull_request"] != previous_pr
            or event["predecessor_authority_digest"] != previous_digest
            or event["predecessor_head_sha"] != previous_head
            or event["initialization_evidence_digest"]
            != result.initialization_evidence_digest
        ):
            raise LifecycleAuthorityError(
                "exact-state adoption successor authorization is not continuous"
            )
        derived = _derive_state(
            state,
            event["transition_kind"],
            event["event_digest"],
            allow_adopted_observations=True,
        )
        resulting_pr = (
            event["replacement_pull_request"]
            if event["transition_kind"] == "PR_REBOUND"
            else event["pull_request"]
        )
        if (
            snapshot["repository"] != result.repository
            or snapshot["delivery_issue"] != result.delivery_issue
            or snapshot["lifecycle_id"] != result.lifecycle_id
            or snapshot["pull_request"] != resulting_pr
            or snapshot["head_sha"] != event["resulting_head_sha"]
            or snapshot["predecessor_authority_digest"] != previous_digest
            or snapshot["predecessor_head_sha"] != previous_head
            or snapshot["transition_kind"] != event["transition_kind"]
            or snapshot["event_authorization_digest"] != event["event_digest"]
            or snapshot["initialization_evidence_digest"]
            != result.initialization_evidence_digest
            or snapshot["state_before"] != state
            or snapshot["state_after"] != derived
        ):
            raise LifecycleAuthorityError(
                "exact-state adoption successor authority is not derived"
            )
        head_changed = event["resulting_head_sha"] != previous_head
        delivery_identity_changed = head_changed or resulting_pr != previous_pr
        current_evidence = snapshot.get("current_head_evidence")
        if delivery_identity_changed != (current_evidence is not None):
            raise LifecycleAuthorityError(
                "exact-state adoption successor current evidence is incomplete"
            )
        if current_evidence is not None:
            current_tree = current_evidence["tree_sha"]
            current_receipt = current_evidence["validation_receipt_digest"]
            current_source = current_evidence["source_validation_evidence_digest"]
            current_attestation = current_evidence["final_attestation_digest"]
        event_ids.add(event["event_id"])
        event_digests.add(event["event_digest"])
        previous_digest = snapshot["authority_digest"]
        previous_head = snapshot["head_sha"]
        previous_pr = snapshot["pull_request"]
        state = derived
        last_signer = snapshot["signer_identity"]
    verified = replace(
        result,
        authority_digest=previous_digest,
        pull_request=previous_pr,
        head_sha=previous_head,
        state=copy.deepcopy(state),
        authority_signer_identity=last_signer,
        tree_sha=current_tree,
        validation_receipt_digest=current_receipt,
        source_validation_evidence_digest=current_source,
        adoption_source_evidence_digest=current_attestation,
    )
    if expected is not None:
        _compare_expected(verified, expected)
    return verified


def issue_exact_state_adoption_successor_authority(
    *, serialized_adoption_evidence: bytes | str,
    authorization: Mapping[str, Any], signer_identity: str,
    authority_signer: Signer,
    current_head_evidence: VerifiedValidationEvidence | None = None,
) -> dict[str, Any]:
    """Issue one ordinary successor from the authenticated adopted predecessor."""

    bundle = _require_closed(
        _load_canonical_json(
            serialized_adoption_evidence, "exact-state adoption lifecycle evidence"
        ),
        EXACT_ADOPTION_PUBLICATION_FIELDS,
        "exact-state adoption lifecycle evidence",
    )
    predecessor = _verify_exact_state_adoption_bundle(bundle)
    policy = _load_lifecycle_trust_policy(predecessor.repository)
    verifier = _policy_signature_verifier(policy)
    event = _verify_transition_authorization(
        authorization,
        accepted_signers=policy.transition_signer_identities,
        signature_verifier=verifier,
    )
    if (
        event["transition_kind"] == "INITIALIZED_DRAFT"
        or event["repository"] != predecessor.repository
        or event["delivery_issue"] != predecessor.delivery_issue
        or event["lifecycle_id"] != predecessor.lifecycle_id
        or event["pull_request"] != predecessor.pull_request
        or event["predecessor_authority_digest"] != predecessor.authority_digest
        or event["predecessor_head_sha"] != predecessor.head_sha
        or event["initialization_evidence_digest"]
        != predecessor.initialization_evidence_digest
    ):
        raise LifecycleAuthorityError(
            "transition authorization does not continue adopted predecessor"
        )
    state = _derive_state(
        predecessor.state,
        event["transition_kind"],
        event["event_digest"],
        allow_adopted_observations=True,
    )
    fields = _authority_unsigned_fields(
        event=event, predecessor={"state_after": predecessor.state}, state=state
    )
    head_changed = event["resulting_head_sha"] != predecessor.head_sha
    resulting_pr = (
        event["replacement_pull_request"]
        if event["transition_kind"] == "PR_REBOUND"
        else predecessor.pull_request
    )
    delivery_identity_changed = (
        head_changed or resulting_pr != predecessor.pull_request
    )
    if delivery_identity_changed:
        if (
            not is_verified_validation_evidence(current_head_evidence)
            or current_head_evidence.repository != predecessor.repository
            or current_head_evidence.pull_request_number != resulting_pr
            or current_head_evidence.head_sha != event["resulting_head_sha"]
        ):
            raise LifecycleAuthorityError(
                "delivery-identity-changing adopted successor requires verified current evidence"
            )
        fields["current_head_evidence"] = {
            "head_sha": current_head_evidence.head_sha,
            "tree_sha": current_head_evidence.tree_sha,
            "validation_receipt_digest": (
                current_head_evidence.validation_receipt_digest
            ),
            "source_validation_evidence_digest": (
                current_head_evidence.source_validation_evidence_digest
            ),
            "final_attestation_digest": (
                current_head_evidence.final_attestation_digest
            ),
        }
    elif current_head_evidence is not None:
        raise LifecycleAuthorityError(
            "unchanged adopted successor cannot replace current evidence"
        )
    fields["signer_identity"] = _require_identity(
        signer_identity, "authority signer"
    )
    if fields["signer_identity"] not in policy.authority_signer_identities:
        raise LifecycleAuthorityError("authority signer is not independently accepted")
    signature = _normalize_signature(
        authority_signer(canonical_json_bytes(fields), AUTHORITY_DOMAIN),
        fields["signer_identity"],
    )
    signed = {**fields, "signature": signature}
    return {**signed, "authority_digest": digest_json(signed)}


def create_legacy_adoption_checkpoint(
    serialized_lifecycle_evidence: bytes | str,
    *,
    migration_reason: str,
    authorization_identity: str,
    checkpoint_event_id: str,
    checkpoint_timestamp: str,
    supporting_evidence_digests: Sequence[str],
    pr_replacement_history_summary: Sequence[Mapping[str, Any]],
    signer_identity: str,
    signer: Signer,
) -> dict[str, Any]:
    """Create the one explicit trust root for a genuinely pre-#750 lifecycle."""

    bundle = _require_closed(
        _load_canonical_json(serialized_lifecycle_evidence, "lifecycle evidence"),
        BUNDLE_FIELDS,
        "lifecycle evidence",
    )
    verified = _verify_unanchored_lifecycle_bundle(bundle)
    initialization = bundle["delivery_initialization"]
    if not isinstance(migration_reason, str) or not migration_reason.strip() or len(migration_reason) > 512:
        raise LifecycleAuthorityError("legacy migration reason is invalid")
    authorization = _require_identity(authorization_identity, "legacy authorization")
    event_id = _require_identity(checkpoint_event_id, "legacy checkpoint event")
    if not isinstance(checkpoint_timestamp, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        checkpoint_timestamp,
    ):
        raise LifecycleAuthorityError("legacy checkpoint timestamp is invalid")
    evidence_digests = list(supporting_evidence_digests)
    if len(evidence_digests) != len(set(evidence_digests)):
        raise LifecycleAuthorityError("legacy supporting evidence is ambiguous")
    for digest in evidence_digests:
        _require_digest(digest, "legacy supporting evidence")
    replacement_summary: list[dict[str, Any]] = []
    for value in pr_replacement_history_summary:
        item = _require_closed(
            value,
            frozenset({"from_pull_request", "to_pull_request", "event_digest"}),
            "legacy PR replacement summary",
        )
        replacement_summary.append(
            {
                "from_pull_request": _require_positive_int(
                    item["from_pull_request"], "legacy predecessor PR"
                ),
                "to_pull_request": _require_positive_int(
                    item["to_pull_request"], "legacy replacement PR"
                ),
                "event_digest": _require_digest(
                    item["event_digest"], "legacy PR replacement event"
                ),
            }
        )
    if len({item["event_digest"] for item in replacement_summary}) != len(replacement_summary):
        raise LifecycleAuthorityError("legacy PR replacement history is ambiguous")
    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": LEGACY_ADOPTION_KIND,
        "domain": LEGACY_ADOPTION_DOMAIN,
        "historical_proof_mode": LEGACY_PROOF_MODE,
        "repository": verified.repository,
        "delivery_issue": verified.delivery_issue,
        "lifecycle_id": verified.lifecycle_id,
        "current_pull_request": verified.pull_request,
        "current_head_sha": verified.head_sha,
        "initial_delivery_identity": {
            "pull_request": initialization["pull_request"],
            "head_sha": initialization["initial_head_sha"],
        },
        "state": copy.deepcopy(verified.state),
        "pr_replacement_history_summary": replacement_summary,
        "migration_reason": migration_reason.strip(),
        "authorization_identity": authorization,
        "checkpoint_event_id": event_id,
        "checkpoint_timestamp": checkpoint_timestamp,
        "supporting_evidence_digests": evidence_digests,
        "lifecycle_evidence_digest": hashlib.sha256(
            canonical_json_bytes(bundle)
        ).hexdigest(),
        "terminal_authority_digest": verified.authority_digest,
        "signer_identity": _require_identity(signer_identity, "legacy adoption signer"),
    }
    signature = _normalize_signature(
        signer(canonical_json_bytes(fields), LEGACY_ADOPTION_DOMAIN), signer_identity
    )
    signed = {**fields, "signature": signature}
    return {**signed, "checkpoint_digest": digest_json(signed)}


def serialize_publication_lifecycle_evidence(
    *,
    lifecycle_evidence: bytes | str,
    legacy_adoption_checkpoint: Mapping[str, Any] | None = None,
) -> bytes:
    """Serialize a closed native or one-time legacy publication enrollment."""

    bundle = _require_closed(
        _load_canonical_json(lifecycle_evidence, "lifecycle evidence"),
        BUNDLE_FIELDS,
        "lifecycle evidence",
    )
    mode = "LEGACY_ADOPTION_CHECKPOINT" if legacy_adoption_checkpoint is not None else "NATIVE_LIFECYCLE"
    return canonical_json_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": PUBLICATION_EVIDENCE_KIND,
            "domain": PUBLICATION_EVIDENCE_DOMAIN,
            "enrollment_mode": mode,
            "lifecycle_evidence": copy.deepcopy(bundle),
            "legacy_adoption_checkpoint": (
                None if legacy_adoption_checkpoint is None else copy.deepcopy(dict(legacy_adoption_checkpoint))
            ),
        }
    )


def _verify_legacy_adoption_checkpoint(
    checkpoint_value: Any,
    bundle: Mapping[str, Any],
    full_result: VerifiedLifecycleAuthority,
    policy: LifecycleTrustPolicy,
) -> VerifiedLifecycleAuthority:
    checkpoint = _require_closed(
        checkpoint_value, LEGACY_ADOPTION_FIELDS, "legacy adoption checkpoint"
    )
    if (
        checkpoint["schema_version"] != SCHEMA_VERSION
        or checkpoint["kind"] != LEGACY_ADOPTION_KIND
        or checkpoint["domain"] != LEGACY_ADOPTION_DOMAIN
        or checkpoint["historical_proof_mode"] != LEGACY_PROOF_MODE
    ):
        raise LifecycleAuthorityError("legacy adoption checkpoint semantics are invalid")
    repository = _require_repository(checkpoint["repository"])
    issue = _require_positive_int(checkpoint["delivery_issue"], "legacy delivery issue")
    if any(anchor.delivery_issue == issue for anchor in policy.initialization_anchors):
        raise LifecycleAuthorityError(
            "a natively anchored lifecycle cannot use legacy adoption"
        )
    lifecycle_id = _require_identity(checkpoint["lifecycle_id"], "legacy lifecycle")
    current_pr = _require_positive_int(checkpoint["current_pull_request"], "legacy current PR")
    current_head = _require_oid(checkpoint["current_head_sha"], "legacy current head")
    initial = _require_closed(
        checkpoint["initial_delivery_identity"],
        frozenset({"pull_request", "head_sha"}),
        "legacy initial delivery identity",
    )
    initial_pr = _require_positive_int(initial["pull_request"], "legacy initial PR")
    initial_head = _require_oid(initial["head_sha"], "legacy initial head")
    state = _legacy_checkpoint_state(checkpoint["state"])
    if state["cycle_3_absent"] is not True:
        raise LifecycleAuthorityError("legacy checkpoint cannot represent Cycle 3")
    reason = checkpoint["migration_reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
        raise LifecycleAuthorityError("legacy migration reason is invalid")
    _require_identity(checkpoint["authorization_identity"], "legacy authorization")
    _require_identity(checkpoint["checkpoint_event_id"], "legacy checkpoint event")
    if not isinstance(checkpoint["checkpoint_timestamp"], str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        checkpoint["checkpoint_timestamp"],
    ):
        raise LifecycleAuthorityError("legacy checkpoint timestamp is invalid")
    supporting = checkpoint["supporting_evidence_digests"]
    if not isinstance(supporting, list) or len(supporting) != len(set(supporting)):
        raise LifecycleAuthorityError("legacy supporting evidence is ambiguous")
    for digest in supporting:
        _require_digest(digest, "legacy supporting evidence")
    replacements = checkpoint["pr_replacement_history_summary"]
    if not isinstance(replacements, list):
        raise LifecycleAuthorityError("legacy PR replacement history is malformed")
    replacement_digests: set[str] = set()
    for value in replacements:
        item = _require_closed(
            value,
            frozenset({"from_pull_request", "to_pull_request", "event_digest"}),
            "legacy PR replacement summary",
        )
        _require_positive_int(item["from_pull_request"], "legacy predecessor PR")
        _require_positive_int(item["to_pull_request"], "legacy replacement PR")
        digest = _require_digest(item["event_digest"], "legacy PR replacement event")
        if digest in replacement_digests:
            raise LifecycleAuthorityError("legacy PR replacement history is ambiguous")
        replacement_digests.add(digest)
    checkpoint_terminal = _require_digest(
        checkpoint["terminal_authority_digest"], "legacy checkpoint terminal"
    )
    authorities = bundle["authority_chain"]
    matches = [index for index, item in enumerate(authorities) if isinstance(item, dict) and item.get("authority_digest") == checkpoint_terminal]
    if len(matches) != 1:
        raise LifecycleAuthorityError("legacy checkpoint terminal is not a unique chain prefix")
    boundary = matches[0] + 1
    prefix = {
        **copy.deepcopy(dict(bundle)),
        "transition_authorizations": copy.deepcopy(bundle["transition_authorizations"][:boundary]),
        "authority_chain": copy.deepcopy(authorities[:boundary]),
    }
    prefix_result = _verify_unanchored_lifecycle_bundle(prefix)
    initialization = bundle["delivery_initialization"]
    expected_replacements = [
        {
            "from_pull_request": event["pull_request"],
            "to_pull_request": event["replacement_pull_request"],
            "event_digest": event["event_digest"],
        }
        for event in prefix["transition_authorizations"]
        if event["transition_kind"] == "PR_REBOUND"
    ]
    if (
        checkpoint["lifecycle_evidence_digest"] != hashlib.sha256(canonical_json_bytes(prefix)).hexdigest()
        or repository != prefix_result.repository
        or issue != prefix_result.delivery_issue
        or lifecycle_id != prefix_result.lifecycle_id
        or current_pr != prefix_result.pull_request
        or current_head != prefix_result.head_sha
        or state != prefix_result.state
        or initial_pr != initialization["pull_request"]
        or initial_head != initialization["initial_head_sha"]
        or replacements != expected_replacements
        or full_result.repository != repository
        or full_result.delivery_issue != issue
        or full_result.lifecycle_id != lifecycle_id
    ):
        raise LifecycleAuthorityError("legacy checkpoint does not bind its exact lifecycle boundary")
    signer_identity = _require_identity(checkpoint["signer_identity"], "legacy adoption signer")
    signed = {key: copy.deepcopy(item) for key, item in checkpoint.items() if key != "checkpoint_digest"}
    digest = _require_digest(checkpoint["checkpoint_digest"], "legacy checkpoint")
    if digest != digest_json(signed):
        raise LifecycleAuthorityError("legacy adoption checkpoint digest mismatch")
    _verify_signature(
        canonical_json_bytes(_unsigned(checkpoint, "checkpoint_digest", "signature")),
        checkpoint["signature"],
        signer_identity,
        LEGACY_ADOPTION_DOMAIN,
        policy.legacy_adoption_signer_identities,
        _policy_signature_verifier(policy),
    )
    return replace(
        full_result,
        historical_proof_mode=LEGACY_PROOF_MODE,
        legacy_adoption_checkpoint_digest=digest,
    )


def _require_exact_legacy_checkpoint_terminal(
    checkpoint: Mapping[str, Any],
    bundle: Mapping[str, Any],
    result: VerifiedLifecycleAuthority,
) -> None:
    """Require an enrollment root to stop exactly at its migration checkpoint."""

    authorities = bundle.get("authority_chain")
    events = bundle.get("transition_authorizations")
    checkpoint_terminal = checkpoint.get("terminal_authority_digest")
    if (
        result.historical_proof_mode != LEGACY_PROOF_MODE
        or result.legacy_adoption_checkpoint_digest is None
        or not isinstance(authorities, list)
        or not isinstance(events, list)
        or not authorities
        or len(authorities) != len(events)
        or checkpoint_terminal != result.authority_digest
        or not isinstance(authorities[-1], dict)
        or authorities[-1].get("authority_digest") != checkpoint_terminal
    ):
        raise LifecycleAuthorityError(
            "legacy enrollment must end at the exact migration checkpoint terminal"
        )


def verify_lifecycle_authority_for_publication(
    serialized_evidence: bytes | str,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify native #750 evidence or one explicit legacy migration checkpoint."""

    if not isinstance(serialized_evidence, (bytes, str)):
        raise LifecycleAuthorityError(
            "publication enrollment requires canonical serialized lifecycle evidence"
        )
    parsed = _load_canonical_json(serialized_evidence, "published lifecycle evidence")
    if isinstance(parsed, dict) and set(parsed) == EXACT_ADOPTION_PUBLICATION_FIELDS:
        if parsed.get("transition_authorizations") != [] or parsed.get("authority_chain") != []:
            raise LifecycleAuthorityError(
                "exact-state adoption enrollment must begin at its proof baseline"
            )
        return _verify_exact_state_adoption_bundle(parsed, expected)
    if isinstance(parsed, dict) and set(parsed) == PUBLICATION_EVIDENCE_FIELDS:
        wrapper = _require_closed(parsed, PUBLICATION_EVIDENCE_FIELDS, "published lifecycle evidence")
        if (
            wrapper["schema_version"] != SCHEMA_VERSION
            or wrapper["kind"] != PUBLICATION_EVIDENCE_KIND
            or wrapper["domain"] != PUBLICATION_EVIDENCE_DOMAIN
        ):
            raise LifecycleAuthorityError("unknown published lifecycle-evidence semantics")
        bundle = _require_closed(wrapper["lifecycle_evidence"], BUNDLE_FIELDS, "lifecycle evidence")
        mode = wrapper["enrollment_mode"]
        if mode == "NATIVE_LIFECYCLE":
            if wrapper["legacy_adoption_checkpoint"] is not None:
                raise LifecycleAuthorityError("native lifecycle cannot carry a legacy checkpoint")
            result = verify_lifecycle_authority(canonical_json_bytes(bundle), expected)
            return replace(result, historical_proof_mode=NATIVE_PROOF_MODE)
        if mode != "LEGACY_ADOPTION_CHECKPOINT" or wrapper["legacy_adoption_checkpoint"] is None:
            raise LifecycleAuthorityError("published lifecycle enrollment mode is invalid")
        initialization = bundle.get("delivery_initialization")
        if not isinstance(initialization, dict):
            raise LifecycleAuthorityError("legacy lifecycle initialization is malformed")
        policy = _load_lifecycle_trust_policy(_require_repository(initialization.get("repository")))
        result = _verify_unanchored_lifecycle_bundle(bundle, expected)
        verified = _verify_legacy_adoption_checkpoint(
            wrapper["legacy_adoption_checkpoint"], bundle, result, policy
        )
        _require_exact_legacy_checkpoint_terminal(
            wrapper["legacy_adoption_checkpoint"], bundle, verified
        )
        return verified
    # Raw bundles are native only and retain the strict maintained-anchor path.
    return verify_lifecycle_authority(serialized_evidence, expected)


def _verify_lifecycle_authority_for_journal(
    serialized_evidence: bytes | str,
    expected: ExpectedLifecycle | None = None,
    admitted_initialization: Mapping[str, Any] | None = None,
) -> VerifiedLifecycleAuthority:
    """Authenticate one journal-carried chain; journal ancestry selects CURRENT."""

    if not isinstance(serialized_evidence, (bytes, str)):
        raise LifecycleAuthorityError(
            "publication journal requires canonical serialized lifecycle evidence"
        )
    parsed = _load_canonical_json(serialized_evidence, "journal lifecycle evidence")
    if isinstance(parsed, dict) and set(parsed) == EXACT_ADOPTION_PUBLICATION_FIELDS:
        return _verify_exact_state_adoption_bundle(parsed, expected)
    if isinstance(parsed, dict) and set(parsed) == PUBLICATION_EVIDENCE_FIELDS:
        wrapper = _require_closed(
            parsed, PUBLICATION_EVIDENCE_FIELDS, "journal lifecycle evidence"
        )
        if (
            wrapper["schema_version"] != SCHEMA_VERSION
            or wrapper["kind"] != PUBLICATION_EVIDENCE_KIND
            or wrapper["domain"] != PUBLICATION_EVIDENCE_DOMAIN
        ):
            raise LifecycleAuthorityError("unknown journal lifecycle-evidence semantics")
        bundle = _require_closed(
            wrapper["lifecycle_evidence"], BUNDLE_FIELDS, "lifecycle evidence"
        )
        mode = wrapper["enrollment_mode"]
        if mode == "NATIVE_LIFECYCLE":
            if wrapper["legacy_adoption_checkpoint"] is not None:
                raise LifecycleAuthorityError("native lifecycle cannot carry a legacy checkpoint")
            return replace(
                _verify_native_lifecycle_bundle_for_journal(
                    bundle, expected, admitted_initialization
                ),
                historical_proof_mode=NATIVE_PROOF_MODE,
            )
        if mode != "LEGACY_ADOPTION_CHECKPOINT" or wrapper["legacy_adoption_checkpoint"] is None:
            raise LifecycleAuthorityError("journal lifecycle enrollment mode is invalid")
        initialization = bundle.get("delivery_initialization")
        if not isinstance(initialization, dict):
            raise LifecycleAuthorityError("legacy lifecycle initialization is malformed")
        policy = _load_lifecycle_trust_policy(
            _require_repository(initialization.get("repository"))
        )
        result = _verify_unanchored_lifecycle_bundle(bundle, expected)
        return _verify_legacy_adoption_checkpoint(
            wrapper["legacy_adoption_checkpoint"], bundle, result, policy
        )
    return replace(
        _verify_native_lifecycle_bundle_for_journal(
            parsed, expected, admitted_initialization
        ),
        historical_proof_mode=NATIVE_PROOF_MODE,
    )


def verify_lifecycle_authority(
    serialized_evidence: bytes | str,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Verify canonical serialized evidence using only maintained installed trust."""

    if not isinstance(serialized_evidence, (bytes, str)):
        raise LifecycleAuthorityError(
            "public lifecycle verification requires canonical serialized evidence"
        )
    bundle = _require_closed(
        _load_canonical_json(serialized_evidence, "lifecycle evidence"),
        BUNDLE_FIELDS,
        "lifecycle evidence",
    )
    if bundle["schema_version"] != SCHEMA_VERSION:
        raise LifecycleAuthorityError("unknown lifecycle-evidence version")
    if bundle["kind"] != BUNDLE_KIND or bundle["domain"] != BUNDLE_DOMAIN:
        raise LifecycleAuthorityError("unknown lifecycle-evidence kind or domain")
    initialization_value = bundle["delivery_initialization"]
    if not isinstance(initialization_value, dict):
        raise LifecycleAuthorityError("delivery initialization is malformed")
    repository = _require_repository(initialization_value.get("repository"))
    policy = _load_lifecycle_trust_policy(repository)
    signature_verifier = _policy_signature_verifier(policy)
    initialization = _verify_delivery_initialization(
        initialization_value,
        policy=policy,
        signature_verifier=signature_verifier,
    )
    authorities = bundle["authority_chain"]
    events = bundle["transition_authorizations"]
    if not isinstance(authorities, list) or not isinstance(events, list):
        raise LifecycleAuthorityError("complete lifecycle evidence chains are required")
    matching_anchors = [
        anchor
        for anchor in policy.initialization_anchors
        if anchor.delivery_issue == initialization["delivery_issue"]
    ]
    if len(matching_anchors) != 1:
        raise LifecycleAuthorityError(
            "delivery initialization has no unique maintained current terminal"
        )
    current = matching_anchors[0]
    terminal = authorities[-1] if authorities else None
    if (
        not isinstance(terminal, dict)
        or current.initialization_digest != initialization["initialization_digest"]
        or terminal.get("initialization_evidence_digest")
        != current.initialization_digest
        or terminal.get("pull_request") != current.current_pull_request
        or terminal.get("head_sha") != current.current_head_sha
        or terminal.get("authority_digest") != current.current_authority_digest
    ):
        raise LifecycleAuthorityError(
            "lifecycle evidence does not name the maintained current terminal authority"
        )
    result = _verify_lifecycle_authority_objects(
        authorities,
        events,
        accepted_event_signers=policy.transition_signer_identities,
        accepted_authority_signers=policy.authority_signer_identities,
        signature_verifier=signature_verifier,
        expected=expected,
    )
    first_event = events[0]
    first_authority = authorities[0]
    digest = initialization["initialization_digest"]
    if (
        first_event["initialization_evidence_digest"] != digest
        or first_authority["initialization_evidence_digest"] != digest
        or first_event["repository"] != initialization["repository"]
        or first_event["delivery_issue"] != initialization["delivery_issue"]
        or first_event["pull_request"] != initialization["pull_request"]
        or first_event["resulting_head_sha"] != initialization["initial_head_sha"]
        or result.lifecycle_id != delivery_initialization_lifecycle_id(digest)
    ):
        raise LifecycleAuthorityError(
            "genesis does not bind the maintained delivery initialization"
        )
    if (
        current.initialization_digest != result.initialization_evidence_digest
        or result.lifecycle_id
        != delivery_initialization_lifecycle_id(current.initialization_digest)
        or current.current_pull_request != result.pull_request
        or current.current_head_sha != result.head_sha
        or current.current_authority_digest != result.authority_digest
    ):
        raise LifecycleAuthorityError(
            "lifecycle evidence does not match the maintained current terminal authority"
        )
    return result


def _compare_expected(result: VerifiedLifecycleAuthority, expected: ExpectedLifecycle) -> None:
    identity_pairs = (
        (result.repository, _require_repository(expected.repository)),
        (result.delivery_issue, _require_positive_int(expected.delivery_issue, "expected issue")),
        (result.lifecycle_id, _require_identity(expected.lifecycle_id, "expected lifecycle")),
        (result.pull_request, _require_positive_int(expected.pull_request, "expected PR")),
        (result.head_sha, _require_oid(expected.head_sha, "expected head")),
    )
    if any(actual != wanted for actual, wanted in identity_pairs):
        raise LifecycleAuthorityError("verified lifecycle identity does not match consumer constraint")
    state_constraints = {
        "unrestricted_review_count": (
            None
            if expected.unrestricted_review_count is None
            else _require_counter(
                expected.unrestricted_review_count,
                "expected unrestricted-review count",
                MAX_UNRESTRICTED_REVIEWS,
            )
        ),
        "remediation_cycle_count": (
            None
            if expected.remediation_cycle_count is None
            else _require_counter(
                expected.remediation_cycle_count,
                "expected remediation-cycle count",
                MAX_REMEDIATION_CYCLES,
            )
        ),
        "ready": expected.ready,
        "ready_transition_count": expected.ready_transition_count,
        "exceptional_recovery_count": (
            None
            if expected.exceptional_recovery_count is None
            else _require_counter(
                expected.exceptional_recovery_count,
                "expected exceptional-recovery count",
                MAX_EXCEPTIONAL_RECOVERIES,
            )
        ),
        "exceptional_continuation_count": (
            None
            if expected.exceptional_continuation_count is None
            else _require_counter(
                expected.exceptional_continuation_count,
                "expected exceptional-continuation count",
                MAX_EXCEPTIONAL_CONTINUATIONS,
            )
        ),
    }
    if expected.ready is not None and not isinstance(expected.ready, bool):
        raise LifecycleAuthorityError("expected Ready state must be a boolean")
    if expected.ready_transition_count is not None and (
        isinstance(expected.ready_transition_count, bool)
        or not isinstance(expected.ready_transition_count, int)
        or expected.ready_transition_count < 0
    ):
        raise LifecycleAuthorityError(
            "expected Ready-transition count must be a non-negative integer"
        )
    for field, wanted in state_constraints.items():
        if wanted is not None and result.state[field] != wanted:
            raise LifecycleAuthorityError(
                f"verified lifecycle fact does not match consumer constraint: {field}"
            )


def lifecycle_authority_binding(result: VerifiedLifecycleAuthority) -> dict[str, Any]:
    """Return the stable exact facts for downstream receipts and attestations."""

    facts = {
        "unrestricted_review_count": result.state["unrestricted_review_count"],
        "remediation_cycle_count": result.state["remediation_cycle_count"],
        "cycle_3_absent": result.state["cycle_3_absent"],
        "ready": result.state["ready"],
        "ready_transition_count": result.state["ready_transition_count"],
        "ready_history_digest": digest_json(result.state["ready_history"]),
        "exceptional_recovery_count": result.state["exceptional_recovery_count"],
        "exceptional_recovery_history_digest": digest_json(
            result.state["exceptional_recovery_history"]
        ),
        "exceptional_continuation_count": result.state["exceptional_continuation_count"],
        "exceptional_continuation_history_digest": digest_json(
            result.state["exceptional_continuation_history"]
        ),
    }
    fields = {
        "schema_version": SCHEMA_VERSION,
        "kind": "VERIFIED_LIFECYCLE_AUTHORITY_BINDING",
        "lifecycle_authority_digest": result.authority_digest,
        "repository": result.repository,
        "delivery_issue": result.delivery_issue,
        "lifecycle_id": result.lifecycle_id,
        "initialization_evidence_digest": result.initialization_evidence_digest,
        "pull_request": result.pull_request,
        "head_sha": result.head_sha,
        "verified_facts": facts,
    }
    return {**fields, "binding_digest": digest_json(fields)}
