# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed, append-only authority for the finite delivery lifecycle.

This module owns lifecycle state derivation, not lifecycle orchestration.  Its
signature callbacks are trust-boundary adapters: callers must back them with a
maintained SSH/OpenPGP verifier and an independently configured signer set.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping, Sequence

from .fast_path import canonical_json_bytes, digest_json


SCHEMA_VERSION = "1.0"
AUTHORITY_KIND = "SECPAL_DELIVERY_LIFECYCLE_AUTHORITY"
AUTHORITY_DOMAIN = "secpal.delivery-lifecycle-authority/v1"
EVENT_KIND = "SECPAL_DELIVERY_LIFECYCLE_TRANSITION_AUTHORIZATION"
EVENT_DOMAIN = "secpal.delivery-lifecycle-transition-authorization/v1"

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

_OID = re.compile(r"[0-9a-f]{40,64}")
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
    pull_request: int
    head_sha: str
    state: dict[str, Any]
    authority_signer_identity: str


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


def loads_closed_json(raw: bytes | str) -> Any:
    """Parse JSON while rejecting duplicate object keys before normalization."""

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise LifecycleAuthorityError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=closed_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LifecycleAuthorityError("lifecycle authority JSON is malformed") from exc


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
    if transition_kind not in TRANSITIONS - {"INITIALIZED_DRAFT"}:
        raise LifecycleAuthorityError("unknown or non-predecessor lifecycle transition")
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
    signer_identity: str,
    signer: Signer,
) -> dict[str, Any]:
    """Create independently signed authorization for one exact transition."""

    if transition_kind not in TRANSITIONS:
        raise LifecycleAuthorityError("unknown lifecycle transition")
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
    if transition == "INITIALIZED_DRAFT":
        if predecessor_digest is not None or predecessor_head is not None or replacement is not None:
            raise LifecycleAuthorityError("genesis cannot claim a predecessor or replacement")
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


def verify_transition_authorization(
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
    if event["transition_kind"] not in TRANSITIONS:
        raise LifecycleAuthorityError("unknown lifecycle transition")
    _require_identity(event["event_id"], "event identity")
    _require_repository(event["repository"])
    _require_positive_int(event["delivery_issue"], "delivery issue")
    _require_identity(event["lifecycle_id"], "lifecycle identity")
    _require_positive_int(event["pull_request"], "pull request")
    _require_oid(event["resulting_head_sha"], "resulting head")
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

    event = verify_transition_authorization(
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
        verified = verify_lifecycle_authority(
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
    if authority["transition_kind"] not in TRANSITIONS:
        raise LifecycleAuthorityError("unknown lifecycle transition")
    _require_digest(authority["event_authorization_digest"], "event authorization digest")
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


def verify_lifecycle_authority(
    authority_chain: Sequence[Mapping[str, Any]],
    transition_authorizations: Sequence[Mapping[str, Any]],
    *,
    accepted_event_signers: frozenset[str],
    accepted_authority_signers: frozenset[str],
    signature_verifier: SignatureVerifier,
    expected: ExpectedLifecycle | None = None,
) -> VerifiedLifecycleAuthority:
    """Independently verify an authority chain from typed genesis to current state."""

    if not authority_chain or len(authority_chain) != len(transition_authorizations):
        raise LifecycleAuthorityError("complete authority and event chains are required")
    events: list[dict[str, Any]] = []
    event_digests: set[str] = set()
    event_ids: set[str] = set()
    for value in transition_authorizations:
        event = verify_transition_authorization(
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
        pull_request=verified_authority["pull_request"],
        head_sha=verified_authority["head_sha"],
        state=copy.deepcopy(current_state),
        authority_signer_identity=verified_authority["signer_identity"],
    )
    if expected is not None:
        _compare_expected(result, expected)
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
        "pull_request": result.pull_request,
        "head_sha": result.head_sha,
        "verified_facts": facts,
    }
    return {**fields, "binding_digest": digest_json(fields)}
