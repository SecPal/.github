# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed, append-only authority for the finite delivery lifecycle.

This module owns lifecycle state derivation, not lifecycle orchestration.  Its
public verifier loads signer roles and credentials from the installed maintained
registry, consumes canonical serialized evidence, and performs SSH/OpenPGP
verification without accepting consumer-selected trust inputs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import cache
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .fast_path import canonical_json_bytes, digest_json


SCHEMA_VERSION = "1.0"
AUTHORITY_KIND = "SECPAL_DELIVERY_LIFECYCLE_AUTHORITY"
AUTHORITY_DOMAIN = "secpal.delivery-lifecycle-authority/v1"
EVENT_KIND = "SECPAL_DELIVERY_LIFECYCLE_TRANSITION_AUTHORIZATION"
EVENT_DOMAIN = "secpal.delivery-lifecycle-transition-authorization/v1"
INITIALIZATION_KIND = "SECPAL_DELIVERY_LIFECYCLE_INITIALIZATION"
INITIALIZATION_DOMAIN = "secpal.delivery-lifecycle-initialization/v1"
BUNDLE_KIND = "SECPAL_DELIVERY_LIFECYCLE_EVIDENCE"
BUNDLE_DOMAIN = "secpal.delivery-lifecycle-evidence/v1"

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
class LifecycleTrustPolicy:
    """Installed trust policy; never accepted as lifecycle evidence input."""

    repository: str
    accepted_formats: frozenset[str]
    transition_signer_identities: frozenset[str]
    authority_signer_identities: frozenset[str]
    signers: Mapping[str, TrustedSigner]
    initialization_anchors: tuple[InitializationAnchor, ...]


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
    return LifecycleTrustPolicy(
        repository=repository,
        accepted_formats=frozenset(formats),
        transition_signer_identities=role_identities(
            "transition_signer_identities"
        ),
        authority_signer_identities=role_identities("authority_signer_identities"),
        signers=signers,
        initialization_anchors=tuple(anchors),
    )


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


def _validate_history(value: Any, label: str, allowed: frozenset[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LifecycleAuthorityError(f"{label} must be a list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        entry = _require_closed(item, HISTORY_FIELDS, f"{label} entry")
        if entry["sequence"] != index or isinstance(entry["sequence"], bool):
            raise LifecycleAuthorityError(f"{label} sequence is not canonical")
        if entry["transition_kind"] not in allowed:
            raise LifecycleAuthorityError(f"{label} transition is invalid")
        normalized.append(
            {
                "sequence": index,
                "transition_kind": entry["transition_kind"],
                "event_authorization_digest": _require_digest(
                    entry["event_authorization_digest"], f"{label} event digest"
                ),
            }
        )
    return normalized


def _validate_state(value: Any) -> dict[str, Any]:
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
    )
    continuation_history = _validate_history(
        state["exceptional_continuation_history"],
        "exceptional-continuation history",
        frozenset({"EXCEPTIONAL_CONTINUATION"}),
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


def derive_state(
    predecessor_state: Mapping[str, Any],
    transition_kind: str,
    event_authorization_digest: str,
    **caller_assertions: Any,
) -> dict[str, Any]:
    """Derive the sole permitted next state; caller-supplied results are refused."""

    if caller_assertions:
        raise LifecycleAuthorityError("caller-supplied resulting lifecycle state is forbidden")
    transition_kind = _require_transition_kind(transition_kind, allow_genesis=False)
    state = copy.deepcopy(_validate_state(dict(predecessor_state)))
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
    return _validate_state(state)


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
) -> dict[str, Any]:
    authority = _require_closed(value, AUTHORITY_FIELDS, "lifecycle authority")
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
        _validate_state(authority["state_before"])
    _validate_state(authority["state_after"])
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
