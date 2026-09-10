# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finite policy orchestration over authenticated delivery-lifecycle state.

The signed state machine remains owned by :mod:`lifecycle_authority`.  This
module authenticates CURRENT publication, consumes the canonical work-graph
classification, and selects at most one bounded next action.  It performs no
GitHub mutation, signing, publication, review request, Ready/Draft transition,
push, polling, or merge.
"""

from __future__ import annotations

import base64
import binascii
import copy
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping

from scripts.secpal_work_graph import replanning

from . import bootstrap_source_admission
from . import exceptional_recovery
from . import fast_path
from . import follow_up
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication
from . import late_disposition
from . import version_collision


REQUEST_FIELDS = frozenset(
    {
        "event_kind",
        "event_id",
        "pull_request",
        "head_sha",
        "replacement_pull_request",
        "classification",
        "follow_up",
        "authorization",
    }
)
CONTINUATION_REQUEST_FIELDS = REQUEST_FIELDS | {"continuation_evidence"}
CONTINUATION_EVIDENCE_FIELDS = frozenset(
    {"reviewed_state_evidence", "eligibility_evidence"}
)
CONTINUATION_SUCCESSOR_EVIDENCE_FIELDS = CONTINUATION_EVIDENCE_FIELDS | {
    "successor_safety_evidence"
}
COLLISION_CONTINUATION_FIELDS = frozenset({
    "schema_version", "trigger", "repository_root", "reviewed_state_evidence",
    "eligibility_evidence", "continuation_document", "predecessor_safety_evidence",
    "successor_safety_evidence", "validation_attestation",
})
AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "authorization_id",
        "repository",
        "delivery_issue",
        "lifecycle_id",
        "publication_oid",
        "publication_digest",
        "authority_digest",
        "pull_request",
        "head_sha",
        "operation",
        "reason",
        "scope",
        "bounded_uses",
        "signer_identity",
        "signature",
        "authorization_digest",
    }
)
AUTHORIZATION_SCHEMA_VERSION = "1.0"
AUTHORIZATION_KIND = "SECPAL_LIFECYCLE_ORCHESTRATION_USER_AUTHORIZATION"
AUTHORIZATION_DOMAIN = "secpal.lifecycle-orchestration-user-authorization/v1"
OBSERVATION_EVENTS = frozenset(
    {
        "REVIEW_EVENT_OBSERVED",
        "CI_OBSERVED",
        "PR_REOPENED",
        "READY_INTEGRATION_VALIDATED",
        "FEEDBACK_ASSESSMENT_COMPLETED",
    }
)
EVENTS = OBSERVATION_EVENTS | frozenset(
    {
        "PR_REPLACED",
        "REMEDIATION_COMMIT_PUSHED",
        "RECOVERY_COMMIT_PUSHED",
        "CONTINUATION_COMMIT_PUSHED",
        "DRAFT_TO_READY",
        "READY_TO_DRAFT",
        "LATE_FEEDBACK_CLASSIFIED",
        "ADDITIONAL_REVIEW_AUTHORIZED",
    }
)

CurrentReader = Callable[[str, int], Any]
FollowUpVerifier = Callable[[follow_up.FollowUpIdentity], Any]
AuthorizationVerifier = Callable[
    [Any, Any, authority.VerifiedLifecycleAuthority], dict[str, Any]
]


class LifecycleOrchestrationError(ValueError):
    """The requested event is stale, ambiguous, recursive, or unauthorized."""


@dataclass(frozen=True)
class LifecycleDecision:
    """One fail-closed decision over the independently authenticated CURRENT tip."""

    publication_oid: str
    publication_digest: str
    lifecycle_identity: str
    pull_request: int
    head_sha: str
    resulting_pull_request: int
    resulting_head_sha: str
    unrestricted_reviews: int
    remediation_cycles: int
    cycle_3_absent: bool
    exceptional_recoveries: int
    exceptional_continuations: int
    ready: bool
    ready_transition_already_performed: bool
    lifecycle_transition: str | None = None
    preserve_ready: bool = False
    transition_to_draft: bool = False
    transition_to_ready: bool = False
    request_review: bool = False
    requires_fresh_head_evidence: bool = False
    additional_review_authorized: bool = False
    technically_blocking: bool = False
    mechanically_blocking: bool = False
    merge_ready: bool = False
    explicit_recovery_required: bool = False
    resolution_eligible: bool = False
    guarded_resolution_candidate: bool = False
    authenticated_resolution_required: bool = False
    resolution_meaning_if_applied: str | None = None
    authorization_digest: str | None = None
    requires_authorization_publication: bool = False
    stop_after_bounded_pass: bool = True


@dataclass(frozen=True)
class VerifiedExceptionalRecoveryAuthority:
    """Closed verified facts for one existing Exceptional Recovery."""

    recovery_digest: str
    authorization_id: str
    authorization_digest: str
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    predecessor_publication_oid: str
    predecessor_publication_digest: str
    recovery_publication_oid: str
    recovery_publication_digest: str
    predecessor_authority_digest: str
    recovery_authority_digest: str
    prior_ready_head_sha: str
    resulting_head_sha: str
    prior_ready_tree_sha: str
    recovery_tree_sha: str
    reviewed_state_digest: str | None
    reviewed_feedback_digest: str | None
    eligibility_evidence_digest: str | None
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedExceptionalContinuationAuthority:
    """Closed composite authority for one source-changing Continuation."""

    continuation_digest: str
    authorization_id: str
    authorization_digest: str
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    predecessor_publication_oid: str
    predecessor_publication_digest: str
    continuation_publication_oid: str
    continuation_publication_digest: str
    predecessor_authority_digest: str
    continuation_authority_digest: str
    prior_ready_head_sha: str
    resulting_head_sha: str
    prior_ready_tree_sha: str
    continuation_tree_sha: str
    reviewed_state_digest: str
    reviewed_feedback_digest: str
    eligibility_evidence_digest: str
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    source_signer_kind: str
    source_signer_identity: str


@dataclass(frozen=True)
class VerifiedContinuationFindingAuthority:
    """Finding facts derived from canonical current-head feedback evidence."""

    reviewed_state_digest: str
    reviewed_feedback_digest: str
    eligibility_evidence_digest: str
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]


def _capture_current_stable_feedback(
    repository: str, pull_request: int
) -> fast_path.StableFeedbackState:
    """Reuse the maintained bounded provider capture without duplicating it."""

    repository_root = Path(__file__).resolve().parents[2]
    action = repository_root / "scripts/secpal-pr-review-actions.py"
    try:
        environment = bootstrap_source_admission._closed_launcher_environment(
            authority._load_trusted_command_helper()
        )
        with tempfile.TemporaryDirectory(
            prefix="secpal-continuation-feedback-"
        ) as directory:
            output = Path(directory) / "reviewed-state.json"
            result = bootstrap_source_admission._run_isolated_python(
                [
                    bootstrap_source_admission._trusted_python(),
                    "-I",
                    "-B",
                    str(action),
                    "resolve-batch",
                    "--repo",
                    repository,
                    "--pr",
                    str(pull_request),
                    "--repo-root",
                    str(repository_root),
                    "--capture-reviewed-state",
                    str(output),
                ],
                cwd=repository_root,
                timeout=60,
                env=environment,
            )
            if result.returncode != 0:
                raise LifecycleOrchestrationError(
                    "current stable feedback could not be authenticated"
                )
            return fast_path.verify_reviewed_state_evidence(
                authority.loads_closed_json(output.read_bytes())
            )
    except (
        OSError,
        authority.LifecycleAuthorityError,
        bootstrap_source_admission.BootstrapSourceAdmissionError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise LifecycleOrchestrationError(
            "current stable feedback could not be authenticated"
        ) from exc


def _closed_mapping(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise LifecycleOrchestrationError(f"{label} contains unknown or missing fields")
    return copy.deepcopy(dict(value))


def _closed_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) not in {
        REQUEST_FIELDS,
        CONTINUATION_REQUEST_FIELDS,
    }:
        raise LifecycleOrchestrationError(
            "lifecycle event contains unknown or missing fields"
        )
    item = copy.deepcopy(dict(value))
    item.setdefault("continuation_evidence", None)
    return item


def _successor_classification_signer(
    repository: str, value: Any
) -> late_disposition.SignerIdentity:
    if not isinstance(value, Mapping) or set(value) != {"kind", "identity"}:
        raise LifecycleOrchestrationError(
            "successor classification signer selector is malformed"
        )
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
        kind = value.get("kind")
        identity = _identity(value.get("identity"), "successor classification signer")
        if kind == "SSH_PRINCIPAL":
            if identity not in policy.transition_signer_identities:
                raise LifecycleOrchestrationError(
                    "successor classification signer is not authorized"
                )
            keys = policy.signers[identity].ssh_public_keys
            if len(keys) != 1:
                raise LifecycleOrchestrationError(
                    "successor classification signer key is ambiguous"
                )
            return late_disposition.SignerIdentity(
                "ssh", _ssh_public_key_fingerprint(keys[0])
            )
        if kind == "OPENPGP_FINGERPRINT" and any(
            signer in policy.transition_signer_identities
            and identity in policy.signers[signer].openpgp_fingerprints
            for signer in policy.signers
        ):
            return late_disposition.SignerIdentity("openpgp", identity.upper())
    except (KeyError, ValueError, authority.LifecycleAuthorityError) as exc:
        raise LifecycleOrchestrationError(
            "successor classification signer is unavailable"
        ) from exc
    raise LifecycleOrchestrationError(
        "successor classification signer is not authorized"
    )


def _authenticate_successor_safety_evidence(
    value: Any,
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_state_digest: str,
    resulting_head_sha: str,
    resulting_state_digest: str,
) -> Any:
    if value is None:
        return None
    expected_keys = {
        "schema_version",
        "repository",
        "pull_request_number",
        "predecessor_state_digest",
        "resulting_head_sha",
        "resulting_state_digest",
        "provider_transport",
        "successor_findings",
        "classification_signer",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise LifecycleOrchestrationError(
            "successor safety evidence contains unknown or missing fields"
        )
    signer = _successor_classification_signer(
        repository, value.get("classification_signer")
    )
    raw_findings = value.get("successor_findings")
    if not isinstance(raw_findings, list):
        raise LifecycleOrchestrationError("successor finding evidence is malformed")
    findings: list[dict[str, Any]] = []
    for raw in raw_findings:
        if not isinstance(raw, Mapping) or set(raw) != {
            "sources",
            "classification_artifact",
            "classification_signature",
        }:
            raise LifecycleOrchestrationError(
                "successor finding evidence is malformed"
            )
        encoded_artifact = raw.get("classification_artifact")
        encoded_signature = raw.get("classification_signature")
        if (
            not isinstance(encoded_artifact, str)
            or len(encoded_artifact)
            > 4 * late_disposition.MAXIMUM_ARTIFACT_BYTES // 3 + 8
            or not isinstance(encoded_signature, str)
            or len(encoded_signature)
            > 4 * late_disposition.MAXIMUM_SIGNATURE_BYTES // 3 + 8
        ):
            raise LifecycleOrchestrationError(
                "successor finding classification is oversized"
            )
        try:
            artifact = base64.b64decode(
                encoded_artifact, validate=True
            )
            signature = base64.b64decode(
                encoded_signature, validate=True
            )
            with tempfile.TemporaryDirectory(
                prefix="secpal-successor-classification-"
            ) as directory:
                root = Path(directory)
                artifact_path = root / "classification.json"
                signature_path = root / "classification.sig"
                late_disposition._write_private_file(artifact_path, artifact)
                late_disposition._write_private_file(signature_path, signature)
                verified = late_disposition.parse_successor_classification_artifact(
                    artifact_path,
                    signature_path,
                    expected_signer=signer,
                    repository=repository,
                    delivery_issue_number=delivery_issue,
                    pull_request_number=pull_request,
                    head_sha=resulting_head_sha,
                    predecessor_state_digest=predecessor_state_digest,
                    resulting_state_digest=resulting_state_digest,
                )
        except (
            KeyError,
            TypeError,
            ValueError,
            binascii.Error,
            OSError,
            late_disposition.LateDispositionError,
        ) as exc:
            raise LifecycleOrchestrationError(
                "successor finding classification is not authenticated"
            ) from exc
        signed_sources = [
            {"kind": kind, "node_id": node_id, "digest": digest}
            for kind, node_id, digest, _thread_id in verified.sources
        ]
        if list(raw["sources"]) != signed_sources:
            raise LifecycleOrchestrationError(
                "successor finding sources differ from signed classification"
            )
        thread = verified.thread
        findings.append(
            {
                "sources": signed_sources,
                "classification_evidence": fast_path._seal_successor_classification(
                    repository=verified.repository,
                    delivery_issue_number=verified.delivery_issue_number,
                    pull_request_number=verified.pull_request_number,
                    head_sha=verified.head_sha,
                    finding_id=verified.finding_id,
                    finding_evidence_digest=verified.finding_evidence_digest,
                    thread_id=thread.thread_id,
                    top_level_comment_node_id=thread.top_level_comment_node_id,
                    finding_body_digest=thread.finding_body_digest,
                    reply_count=thread.reply_count,
                    is_resolved=thread.is_resolved,
                    is_outdated=thread.is_outdated,
                    classification=thread.classification,
                    disposition=thread.disposition,
                    technically_blocking=thread.technically_blocking,
                    technical_blockers=verified.technical_blockers,
                    classification_evidence_digest=verified.evidence_digest,
                    source_bindings=verified.sources,
                ),
            }
        )
    prepared = copy.deepcopy(dict(value))
    prepared.pop("classification_signer")
    prepared["successor_findings"] = findings
    return prepared


def _verify_continuation_finding_authority(
    value: Any,
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_head_sha: str,
    resulting_head_sha: str,
    feedback_reader: Callable[[str, int], fast_path.StableFeedbackState],
) -> VerifiedContinuationFindingAuthority:
    """Derive a finite material finding set from maintained feedback evidence."""

    if (
        not isinstance(value, Mapping)
        or set(value)
        not in {
            CONTINUATION_EVIDENCE_FIELDS,
            CONTINUATION_SUCCESSOR_EVIDENCE_FIELDS,
        }
    ):
        raise LifecycleOrchestrationError(
            "continuation finding evidence contains unknown or missing fields"
        )
    item = copy.deepcopy(dict(value))
    try:
        reviewed = fast_path.verify_reviewed_state_evidence(
            item["reviewed_state_evidence"]
        )
        eligibility = fast_path.normalize_resolution_eligibility_evidence(
            item["eligibility_evidence"],
            repository=repository,
            reviewed_state=reviewed,
        )
        finding_ids, thread_ids = fast_path.continuation_material_finding_projection(
            reviewed, eligibility
        )
        current = feedback_reader(repository, pull_request)
        successor_safety = _authenticate_successor_safety_evidence(
            item.get("successor_safety_evidence"),
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            predecessor_state_digest=reviewed.state_digest,
            resulting_head_sha=resulting_head_sha,
            resulting_state_digest=current.state_digest,
        )
        fast_path.verify_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=resulting_head_sha,
            authorized_thread_ids=thread_ids,
            successor_safety_evidence=successor_safety,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "continuation finding evidence is invalid or stale"
        ) from exc
    if (
        reviewed.repository != repository
        or reviewed.pull_request_number != pull_request
        or reviewed.head_sha != predecessor_head_sha
        or reviewed.pr_state != "OPEN"
    ):
        raise LifecycleOrchestrationError(
            "continuation feedback differs from the CURRENT Ready head"
        )
    return VerifiedContinuationFindingAuthority(
        reviewed_state_digest=reviewed.state_digest,
        reviewed_feedback_digest=reviewed.feedback_digest,
        eligibility_evidence_digest=fast_path.digest_json(eligibility),
        finding_ids=tuple(finding_ids),
        thread_ids=tuple(thread_ids),
    )


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise LifecycleOrchestrationError(f"{label} must be a positive integer")
    return value


def _identity(value: Any, label: str) -> str:
    try:
        return authority._require_identity(value, label)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def _authenticate_diagnostic_recovery_source() -> str:
    """Expose only the closed accepted-main diagnostic authentication boundary."""

    return exceptional_recovery.authenticate_maintained_code()


def _verify_diagnostic_recovery_admission(
    value: Any, observed: Any, repository_root: Path
) -> dict[str, Any]:
    """Expose only the closed diagnostic admission verifier to the binder."""

    return exceptional_recovery.verify_admission(
        value, observed, repository_root
    )


def _oid(value: Any, label: str) -> str:
    try:
        return authority._require_oid(value, label)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def create_user_authorization(
    *,
    authorization_id: str,
    repository: str,
    delivery_issue: int,
    lifecycle: authority.VerifiedLifecycleAuthority,
    publication_oid: str,
    publication_digest: str,
    operation: str,
    reason: str,
    scope: Mapping[str, Any],
    signer_identity: str,
    signer: authority.Signer,
) -> bytes:
    """Create signed authority for one exact CURRENT orchestration decision."""

    if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
        raise LifecycleOrchestrationError("user authorization reason is invalid")
    try:
        fields = {
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "kind": AUTHORIZATION_KIND,
            "domain": AUTHORIZATION_DOMAIN,
            "authorization_id": _identity(
                authorization_id, "authorization identity"
            ),
            "repository": authority._require_repository(repository),
            "delivery_issue": _positive_int(delivery_issue, "delivery issue"),
            "lifecycle_id": _identity(lifecycle.lifecycle_id, "lifecycle identity"),
            "publication_oid": _oid(publication_oid, "publication object"),
            "publication_digest": authority._require_digest(
                publication_digest, "publication digest"
            ),
            "authority_digest": authority._require_digest(
                lifecycle.authority_digest, "authority digest"
            ),
            "pull_request": _positive_int(lifecycle.pull_request, "pull request"),
            "head_sha": _oid(lifecycle.head_sha, "head"),
            "operation": _identity(operation, "authorized operation"),
            "reason": reason,
            "scope": copy.deepcopy(dict(scope)),
            "bounded_uses": 1,
            "signer_identity": _identity(
                signer_identity, "authorization signer"
            ),
        }
        signature = authority._normalize_signature(
            signer(authority.canonical_json_bytes(fields), AUTHORIZATION_DOMAIN),
            fields["signer_identity"],
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    signed = {**fields, "signature": signature}
    artifact = {**signed, "authorization_digest": authority.digest_json(signed)}
    return authority.canonical_json_bytes(artifact)


def _verify_signed_user_authorization(
    value: Any,
    repository: str,
) -> dict[str, Any]:
    """Verify signed bytes without selecting CURRENT or historical authority."""

    if not isinstance(value, (bytes, str)):
        raise LifecycleOrchestrationError(
            "user authorization requires canonical signed evidence"
        )
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    try:
        parsed = authority.loads_closed_json(raw)
        item = _closed_mapping(parsed, AUTHORIZATION_FIELDS, "user authorization")
        if authority.canonical_json_bytes(item) != raw:
            raise LifecycleOrchestrationError("user authorization is not canonical")
        if (
            item["schema_version"] != AUTHORIZATION_SCHEMA_VERSION
            or item["kind"] != AUTHORIZATION_KIND
            or item["domain"] != AUTHORIZATION_DOMAIN
        ):
            raise LifecycleOrchestrationError("user authorization semantics are unknown")
        signer_identity = _identity(item["signer_identity"], "authorization signer")
        repository = authority._require_repository(repository)
        if item["repository"] != repository:
            raise LifecycleOrchestrationError(
                "user authorization repository differs from expected authority"
            )
        policy = authority._load_lifecycle_trust_policy(repository)
        signed = {
            key: copy.deepcopy(entry)
            for key, entry in item.items()
            if key != "authorization_digest"
        }
        if authority._require_digest(
            item["authorization_digest"], "authorization digest"
        ) != authority.digest_json(signed):
            raise LifecycleOrchestrationError("user authorization digest mismatch")
        unsigned = {
            key: copy.deepcopy(entry)
            for key, entry in signed.items()
            if key != "signature"
        }
        authority._verify_signature(
            authority.canonical_json_bytes(unsigned),
            item["signature"],
            signer_identity,
            AUTHORIZATION_DOMAIN,
            policy.transition_signer_identities,
            authority._policy_signature_verifier(policy),
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError("user authorization is invalid") from exc
    return item


def _verify_user_authorization(
    value: Any,
    observed: Any,
    lifecycle: authority.VerifiedLifecycleAuthority,
) -> dict[str, Any]:
    item = _verify_signed_user_authorization(value, lifecycle.repository)
    if (
        item["repository"] != lifecycle.repository
        or item["delivery_issue"] != lifecycle.delivery_issue
        or item["lifecycle_id"] != lifecycle.lifecycle_id
        or item["publication_oid"] != observed.publication_oid
        or item["publication_digest"] != observed.publication_digest
        or item["authority_digest"] != lifecycle.authority_digest
        or item["pull_request"] != lifecycle.pull_request
        or item["head_sha"] != lifecycle.head_sha
    ):
        raise LifecycleOrchestrationError(
            "user authorization differs from CURRENT lifecycle publication"
        )
    return item


def _authorization(
    value: Any,
    *,
    event_id: str,
    operation: str,
    expected_scope: Mapping[str, Any],
    observed: Any,
    lifecycle: authority.VerifiedLifecycleAuthority,
    verifier: AuthorizationVerifier,
    verified_item: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = (
        verifier(value, observed, lifecycle)
        if verified_item is None
        else copy.deepcopy(dict(verified_item))
    )
    reason = item.get("reason")
    if (
        item.get("operation") != operation
        or item.get("bounded_uses") != 1
        or isinstance(item.get("bounded_uses"), bool)
        or not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 512
        or item.get("scope") != dict(expected_scope)
    ):
        raise LifecycleOrchestrationError(
            f"{operation} requires one exact, reasoned, bounded user authorization"
        )
    _identity(item.get("authorization_id"), "authorization identity")
    try:
        digest = authority._require_digest(
            item.get("authorization_digest"), "authorization digest"
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    if event_id != f"authorization:{digest}":
        raise LifecycleOrchestrationError(
            "event identity is not bound to the signed user authorization"
        )
    return item


def _immutable_commit_tree(
    repository_root: Path,
    repository: str,
    head_sha: str,
) -> str:
    """Derive one tree from an exact commit in the authenticated repository."""

    if not isinstance(repository_root, Path):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository root is unavailable"
        )
    try:
        root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository root is unavailable"
        ) from exc
    if not root.is_dir():
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository root is unavailable"
        )
    head_sha = _oid(head_sha, "Exceptional Recovery commit")
    origin = publication._run_git(root, ["remote", "get-url", "origin"])
    if origin.returncode != 0:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository identity is unavailable"
        )
    try:
        origin_text = origin.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository identity is malformed"
        ) from exc
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        origin_text,
    )
    if match is None or match.group(1) != repository:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository identity changed"
        )
    object_type = publication._run_git(root, ["cat-file", "-t", head_sha])
    if object_type.returncode != 0 or object_type.stdout != b"commit\n":
        raise LifecycleOrchestrationError(
            "Exceptional Recovery commit object is unavailable"
        )
    tree = publication._run_git(root, ["rev-parse", f"{head_sha}^{{tree}}"])
    if tree.returncode != 0:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery commit tree is unavailable"
        )
    try:
        return _oid(tree.stdout.decode("ascii").strip(), "Exceptional Recovery tree")
    except (UnicodeDecodeError, LifecycleOrchestrationError) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery commit tree is malformed"
        ) from exc


def verify_exceptional_recovery_authority(
    recovery_evidence: Any,
    *,
    orchestration_authorization: bytes | str,
    reviewed_state_evidence: Any,
    eligibility_evidence: Any,
    repository_root: Path,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    resulting_head_sha: str,
) -> VerifiedExceptionalRecoveryAuthority:
    """Authenticate one Recovery projection through all accepted authorities.

    The signed orchestration authorization selects an exact historical
    predecessor publication.  Protected publication ancestry then proves the
    one signed lifecycle successor; no caller-provided lifecycle bundle or
    trust configuration is accepted.
    """

    try:
        repository = authority._require_repository(repository)
        delivery_issue = _positive_int(delivery_issue, "delivery issue")
        pull_request = _positive_int(pull_request, "pull request")
        resulting_head_sha = _oid(resulting_head_sha, "resulting head")
        authorization = _verify_signed_user_authorization(
            orchestration_authorization, repository
        )
        transition = publication._verify_historical_lifecycle_transition(
            repository,
            delivery_issue,
            authorization.get("publication_oid"),
        )
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery lifecycle authority is invalid"
        ) from exc

    predecessor = transition.predecessor.lifecycle
    successor = transition.successor.lifecycle
    if (
        authorization.get("delivery_issue") != delivery_issue
        or authorization.get("lifecycle_id") != predecessor.lifecycle_id
        or authorization.get("publication_oid")
        != transition.predecessor.publication_oid
        or authorization.get("publication_digest")
        != transition.predecessor.publication_digest
        or authorization.get("authority_digest") != predecessor.authority_digest
        or authorization.get("pull_request") != pull_request
        or authorization.get("pull_request") != predecessor.pull_request
        or authorization.get("head_sha") != predecessor.head_sha
        or transition.transition_kind != "EXCEPTIONAL_RECOVERY"
        or transition.pull_request != pull_request
        or transition.predecessor_authority_digest
        != predecessor.authority_digest
        or transition.predecessor_head_sha != predecessor.head_sha
        or transition.resulting_head_sha != resulting_head_sha
        or predecessor.head_sha == resulting_head_sha
        or transition.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.repository != repository
        or successor.delivery_issue != delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.pull_request != pull_request
        or successor.head_sha != resulting_head_sha
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery signed lifecycle identity changed"
        )

    if isinstance(recovery_evidence, dict) and recovery_evidence.get("schema_version") == "1.1":
        if reviewed_state_evidence is not None or eligibility_evidence is not None:
            raise LifecycleOrchestrationError("diagnostic Recovery grants no thread-resolution authority")
        try:
            exceptional_recovery.authenticate_maintained_code()
            recovery = exceptional_recovery.verify_admission(recovery_evidence, transition.predecessor, repository_root)
            if recovery["authorization_id"] != authorization["authorization_id"]:
                raise LifecycleOrchestrationError(
                    "diagnostic Recovery authorization identity changed"
                )
            exceptional_recovery.require_successor(repository_root, recovery, resulting_head_sha)
            _authorization(
                orchestration_authorization,
                event_id=transition.event_id,
                operation="EXCEPTIONAL_RECOVERY",
                expected_scope=exceptional_recovery.authorization_scope(
                    recovery, resulting_head_sha
                ),
                observed=transition.predecessor,
                lifecycle=predecessor,
                verifier=_verify_user_authorization,
                verified_item=authorization,
            )
            expected_state = authority.derive_state(predecessor.state, "EXCEPTIONAL_RECOVERY", transition.event_digest)
            if successor.state != expected_state or transition.event_signer_identity != authorization["signer_identity"]:
                raise LifecycleOrchestrationError("diagnostic Recovery lifecycle successor changed")
        except exceptional_recovery.DiagnosticRecoveryError as exc:
            raise LifecycleOrchestrationError(str(exc)) from exc
        return VerifiedExceptionalRecoveryAuthority(
            recovery_digest=fast_path.digest_json(recovery),
            authorization_id=authorization["authorization_id"],
            authorization_digest=authorization["authorization_digest"],
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            lifecycle_id=predecessor.lifecycle_id,
            predecessor_publication_oid=transition.predecessor.publication_oid,
            predecessor_publication_digest=transition.predecessor.publication_digest,
            recovery_publication_oid=transition.successor.publication_oid,
            recovery_publication_digest=transition.successor.publication_digest,
            predecessor_authority_digest=predecessor.authority_digest,
            recovery_authority_digest=successor.authority_digest,
            prior_ready_head_sha=predecessor.head_sha,
            resulting_head_sha=resulting_head_sha,
            prior_ready_tree_sha=recovery["prior_ready_tree_sha"],
            recovery_tree_sha=recovery["recovery_tree_sha"],
            reviewed_state_digest=None,
            reviewed_feedback_digest=None,
            eligibility_evidence_digest=None,
            finding_ids=tuple(recovery["finding_ids"]),
            thread_ids=(),
        )

    try:
        reviewed = fast_path.verify_reviewed_state_evidence(
            reviewed_state_evidence
        )
        eligibility = fast_path.normalize_resolution_eligibility_evidence(
            eligibility_evidence,
            repository=repository,
            reviewed_state=reviewed,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery reviewed or eligibility evidence is invalid"
        ) from exc
    if reviewed.pull_request_number != pull_request:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery reviewed pull request changed"
        )

    eligible_threads = eligibility["eligible_threads"]
    thread_ids = sorted(item["thread_id"] for item in eligible_threads)
    flattened_findings = [
        finding_id
        for item in eligible_threads
        for finding_id in item["finding_ids"]
    ]
    if len(flattened_findings) != len(set(flattened_findings)):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery eligibility repeats a finding"
        )
    finding_ids = sorted(flattened_findings)
    eligibility_digest = fast_path.digest_json(eligibility)

    _authorization(
        orchestration_authorization,
        event_id=transition.event_id,
        operation="EXCEPTIONAL_RECOVERY",
        expected_scope={
            "pull_request": pull_request,
            "predecessor_head_sha": predecessor.head_sha,
            "resulting_head_sha": resulting_head_sha,
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "eligibility_evidence_digest": eligibility_digest,
            "finding_ids": finding_ids,
            "thread_ids": thread_ids,
        },
        observed=transition.predecessor,
        lifecycle=predecessor,
        verifier=_verify_user_authorization,
        verified_item=authorization,
    )

    try:
        prior_tree = _immutable_commit_tree(
            repository_root, repository, predecessor.head_sha
        )
        recovery_tree = _immutable_commit_tree(
            repository_root, repository, resulting_head_sha
        )
        recovery = fast_path.normalize_exceptional_recovery_evidence(
            recovery_evidence,
            repository=repository,
            reviewed_state=reviewed,
            validated_tree_sha=recovery_tree,
            eligibility_evidence_digest=eligibility_digest,
        )
    except (fast_path.SecurityBlocker, publication.LifecyclePublicationError) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery document is invalid or stale"
        ) from exc
    if (
        recovery["authorization_id"] != authorization.get("authorization_id")
        or recovery["delivery_issue_number"] != delivery_issue
        or recovery["pull_request_number"] != pull_request
        or recovery["prior_ready_head_sha"] != predecessor.head_sha
        or recovery["prior_ready_tree_sha"] != prior_tree
        or recovery["recovery_tree_sha"] != recovery_tree
        or recovery["finding_ids"] != finding_ids
        or recovery["thread_ids"] != thread_ids
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery projection differs from verified authority"
        )

    try:
        predecessor_state = authority._validate_state(
            copy.deepcopy(predecessor.state)
        )
        successor_state = authority._validate_state(copy.deepcopy(successor.state))
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery lifecycle state is invalid"
        ) from exc
    unchanged_fields = (
        "unrestricted_review_count",
        "remediation_cycle_count",
        "cycle_3_absent",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_continuation_count",
        "exceptional_continuation_history",
    )
    if (
        any(
            predecessor_state[field] != successor_state[field]
            for field in unchanged_fields
        )
        or predecessor_state["unrestricted_review_count"]
        != authority.MAX_UNRESTRICTED_REVIEWS
        or predecessor_state["remediation_cycle_count"]
        != authority.MAX_REMEDIATION_CYCLES
        or predecessor_state["cycle_3_absent"] is not True
        or predecessor_state["draft"] is not False
        or predecessor_state["ready"] is not True
        or predecessor_state["exceptional_recovery_count"] != 0
        or successor_state["exceptional_recovery_count"] != 1
        or successor_state["exceptional_recovery_history"]
        != [
            {
                "sequence": 1,
                "transition_kind": "EXCEPTIONAL_RECOVERY",
                "event_authorization_digest": transition.event_digest,
            }
        ]
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery lifecycle projection is invalid"
        )
    lifecycle_projection = {
        "unrestricted_reviews": successor_state["unrestricted_review_count"],
        "remediation_cycles": successor_state["remediation_cycle_count"],
        "cycle_3": not successor_state["cycle_3_absent"],
        "draft": successor_state["draft"],
        "ready": successor_state["ready"],
        "ready_transition": transition.transition_kind == "DRAFT_TO_READY",
        "exceptional_recovery_count": successor_state[
            "exceptional_recovery_count"
        ],
    }
    if recovery["lifecycle"] != lifecycle_projection:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery embedded lifecycle projection changed"
        )

    recovery_digest = fast_path.digest_json(recovery)
    return VerifiedExceptionalRecoveryAuthority(
        recovery_digest=recovery_digest,
        authorization_id=authorization["authorization_id"],
        authorization_digest=authorization["authorization_digest"],
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        lifecycle_id=predecessor.lifecycle_id,
        predecessor_publication_oid=transition.predecessor.publication_oid,
        predecessor_publication_digest=transition.predecessor.publication_digest,
        recovery_publication_oid=transition.successor.publication_oid,
        recovery_publication_digest=transition.successor.publication_digest,
        predecessor_authority_digest=predecessor.authority_digest,
        recovery_authority_digest=successor.authority_digest,
        prior_ready_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        prior_ready_tree_sha=prior_tree,
        recovery_tree_sha=recovery_tree,
        reviewed_state_digest=reviewed.state_digest,
        reviewed_feedback_digest=reviewed.feedback_digest,
        eligibility_evidence_digest=eligibility_digest,
        finding_ids=tuple(finding_ids),
        thread_ids=tuple(thread_ids),
    )


def _authenticate_continuation_commit(
    repository_root: Path,
    repository: str,
    predecessor_head_sha: str,
    resulting_head_sha: str,
    expected_signer: Any,
) -> fast_path.AuthenticatedIntegrationCommit:
    """Reuse the ordinary signed-commit verifier for the one-parent successor."""

    if (
        not isinstance(expected_signer, Mapping)
        or set(expected_signer) != {"kind", "identity"}
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation source signer is malformed"
        )
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
        signer_kind = expected_signer.get("kind")
        signer_identity = _identity(
            expected_signer.get("identity"), "continuation source signer"
        )
        if signer_kind == "SSH_PRINCIPAL":
            authorized = signer_identity in policy.transition_signer_identities
        elif signer_kind == "OPENPGP_FINGERPRINT":
            authorized = any(
                identity in policy.transition_signer_identities
                and signer_identity in policy.signers[identity].openpgp_fingerprints
                for identity in policy.signers
            )
        else:
            authorized = False
        if not authorized:
            raise LifecycleOrchestrationError(
                "Exceptional Continuation source signer is not authorized"
            )
        verified = fast_path.authenticate_integration_commit(
            repository_root=repository_root,
            repository=repository,
            head_sha=resulting_head_sha,
            expected_signer=dict(expected_signer),
            signature_policy={
                "require_github_verified": False,
                "require_local_verified": True,
                "accepted_formats": sorted(policy.accepted_formats),
            },
        )
    except (
        authority.LifecycleAuthorityError,
        fast_path.RecoverableLocalError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation signed source commit is invalid"
        ) from exc
    if signer_kind == "SSH_PRINCIPAL":
        try:
            trusted_fingerprints = {
                _ssh_public_key_fingerprint(key)
                for key in policy.signers[signer_identity].ssh_public_keys
            }
        except (KeyError, ValueError) as exc:
            raise LifecycleOrchestrationError(
                "Exceptional Continuation maintained SSH key is invalid"
            ) from exc
        if verified.signature_fingerprint not in trusted_fingerprints:
            raise LifecycleOrchestrationError(
                "Exceptional Continuation signature does not match the maintained SSH key"
            )
    if verified.parent_shas != (predecessor_head_sha,):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation requires one exact predecessor parent"
        )
    return verified


def _ssh_public_key_fingerprint(public_key: str) -> str:
    """Derive the OpenSSH SHA-256 fingerprint for one maintained public key."""

    parts = public_key.split()
    if len(parts) < 2:
        raise ValueError("SSH public key is malformed")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("SSH public key is malformed") from exc
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii")
    return "SHA256:" + digest.rstrip("=")


def verify_exceptional_continuation_authority(
    continuation_evidence: Any,
    *,
    orchestration_authorization: bytes | str,
    reviewed_state_evidence: Any,
    eligibility_evidence: Any,
    successor_safety_evidence: Any = None,
    repository_root: Path,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    resulting_head_sha: str,
) -> VerifiedExceptionalContinuationAuthority:
    """Authenticate one Continuation through publication, findings, and source."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = _positive_int(delivery_issue, "delivery issue")
        pull_request = _positive_int(pull_request, "pull request")
        resulting_head_sha = _oid(resulting_head_sha, "resulting head")
        authorization = _verify_signed_user_authorization(
            orchestration_authorization, repository
        )
        transition = publication._verify_historical_lifecycle_transition(
            repository,
            delivery_issue,
            authorization.get("publication_oid"),
        )
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation lifecycle authority is invalid"
        ) from exc

    predecessor = transition.predecessor.lifecycle
    successor = transition.successor.lifecycle
    if (
        authorization.get("delivery_issue") != delivery_issue
        or authorization.get("lifecycle_id") != predecessor.lifecycle_id
        or authorization.get("publication_oid")
        != transition.predecessor.publication_oid
        or authorization.get("publication_digest")
        != transition.predecessor.publication_digest
        or authorization.get("authority_digest") != predecessor.authority_digest
        or authorization.get("pull_request") != pull_request
        or predecessor.pull_request != pull_request
        or authorization.get("head_sha") != predecessor.head_sha
        or transition.transition_kind != "EXCEPTIONAL_CONTINUATION"
        or transition.pull_request != pull_request
        or transition.predecessor_authority_digest != predecessor.authority_digest
        or transition.predecessor_head_sha != predecessor.head_sha
        or transition.resulting_head_sha != resulting_head_sha
        or predecessor.head_sha == resulting_head_sha
        or transition.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.repository != repository
        or successor.delivery_issue != delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.pull_request != pull_request
        or successor.head_sha != resulting_head_sha
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation signed lifecycle identity changed"
        )

    findings = _verify_continuation_finding_authority(
        {
            "reviewed_state_evidence": reviewed_state_evidence,
            "eligibility_evidence": eligibility_evidence,
            **(
                {"successor_safety_evidence": successor_safety_evidence}
                if successor_safety_evidence is not None
                else {}
            ),
        },
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        predecessor_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        feedback_reader=_capture_current_stable_feedback,
    )
    _authorization(
        orchestration_authorization,
        event_id=transition.event_id,
        operation="EXCEPTIONAL_CONTINUATION",
        expected_scope={
            "pull_request": pull_request,
            "predecessor_head_sha": predecessor.head_sha,
            "resulting_head_sha": resulting_head_sha,
            "reviewed_state_digest": findings.reviewed_state_digest,
            "reviewed_feedback_digest": findings.reviewed_feedback_digest,
            "eligibility_evidence_digest": findings.eligibility_evidence_digest,
            "finding_ids": list(findings.finding_ids),
            "thread_ids": list(findings.thread_ids),
        },
        observed=transition.predecessor,
        lifecycle=predecessor,
        verifier=_verify_user_authorization,
        verified_item=authorization,
    )

    try:
        predecessor_state = authority._validate_state(
            copy.deepcopy(predecessor.state)
        )
        successor_state = authority._validate_state(copy.deepcopy(successor.state))
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation lifecycle state is invalid"
        ) from exc
    unchanged_fields = (
        "unrestricted_review_count",
        "remediation_cycle_count",
        "cycle_3_absent",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_recovery_count",
        "exceptional_recovery_history",
    )
    if (
        any(
            predecessor_state[field] != successor_state[field]
            for field in unchanged_fields
        )
        or predecessor_state["unrestricted_review_count"]
        != authority.MAX_UNRESTRICTED_REVIEWS
        or predecessor_state["remediation_cycle_count"]
        != authority.MAX_REMEDIATION_CYCLES
        or predecessor_state["cycle_3_absent"] is not True
        or predecessor_state["draft"] is not False
        or predecessor_state["ready"] is not True
        or predecessor_state["exceptional_recovery_count"]
        != authority.MAX_EXCEPTIONAL_RECOVERIES
        or len(predecessor_state["exceptional_recovery_history"])
        != authority.MAX_EXCEPTIONAL_RECOVERIES
        or predecessor_state["exceptional_continuation_count"] != 0
        or predecessor_state["exceptional_continuation_history"] != []
        or successor_state["exceptional_continuation_count"] != 1
        or successor_state["exceptional_continuation_history"]
        != [
            {
                "sequence": 1,
                "transition_kind": "EXCEPTIONAL_CONTINUATION",
                "event_authorization_digest": transition.event_digest,
            }
        ]
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation lifecycle projection is invalid"
        )

    try:
        reviewed = fast_path.verify_reviewed_state_evidence(reviewed_state_evidence)
        source = _authenticate_continuation_commit(
            repository_root,
            repository,
            predecessor.head_sha,
            resulting_head_sha,
            continuation_evidence.get("expected_signer")
            if isinstance(continuation_evidence, Mapping)
            else None,
        )
        prior_tree = _immutable_commit_tree(
            repository_root, repository, predecessor.head_sha
        )
        continuation = fast_path.normalize_exceptional_continuation_evidence(
            continuation_evidence,
            repository=repository,
            reviewed_state=reviewed,
            validated_tree_sha=source.tree_sha,
            eligibility_evidence=eligibility_evidence,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation document is invalid or stale"
        ) from exc
    lifecycle_projection = {
        "unrestricted_reviews": predecessor_state["unrestricted_review_count"],
        "remediation_cycles": predecessor_state["remediation_cycle_count"],
        "cycle_3": not predecessor_state["cycle_3_absent"],
        "draft": predecessor_state["draft"],
        "ready": predecessor_state["ready"],
        "ready_transition_count": predecessor_state["ready_transition_count"],
        "ready_history": predecessor_state["ready_history"],
        "exceptional_recovery_count": predecessor_state[
            "exceptional_recovery_count"
        ],
        "exceptional_recovery_history": predecessor_state[
            "exceptional_recovery_history"
        ],
        "exceptional_continuation_predecessor_count": 0,
        "exceptional_continuation_successor_count": 1,
    }
    if (
        continuation["authorization_id"] != authorization.get("authorization_id")
        or continuation["delivery_issue_number"] != delivery_issue
        or continuation["pull_request_number"] != pull_request
        or continuation["prior_ready_head_sha"] != predecessor.head_sha
        or continuation["prior_ready_tree_sha"] != prior_tree
        or continuation["continuation_tree_sha"] != source.tree_sha
        or continuation["reviewed_state_digest"]
        != findings.reviewed_state_digest
        or continuation["reviewed_feedback_digest"]
        != findings.reviewed_feedback_digest
        or continuation["eligibility_evidence_digest"]
        != findings.eligibility_evidence_digest
        or continuation["finding_ids"] != list(findings.finding_ids)
        or continuation["thread_ids"] != list(findings.thread_ids)
        or continuation["lifecycle"] != lifecycle_projection
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation projection differs from verified authority"
        )
    return VerifiedExceptionalContinuationAuthority(
        continuation_digest=fast_path.digest_json(continuation),
        authorization_id=authorization["authorization_id"],
        authorization_digest=authorization["authorization_digest"],
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        lifecycle_id=predecessor.lifecycle_id,
        predecessor_publication_oid=transition.predecessor.publication_oid,
        predecessor_publication_digest=transition.predecessor.publication_digest,
        continuation_publication_oid=transition.successor.publication_oid,
        continuation_publication_digest=transition.successor.publication_digest,
        predecessor_authority_digest=predecessor.authority_digest,
        continuation_authority_digest=successor.authority_digest,
        prior_ready_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        prior_ready_tree_sha=prior_tree,
        continuation_tree_sha=source.tree_sha,
        reviewed_state_digest=findings.reviewed_state_digest,
        reviewed_feedback_digest=findings.reviewed_feedback_digest,
        eligibility_evidence_digest=findings.eligibility_evidence_digest,
        finding_ids=findings.finding_ids,
        thread_ids=findings.thread_ids,
        source_signer_kind=source.signer_kind,
        source_signer_identity=source.signer_identity,
    )


def _collision_request(value: Any) -> dict[str, Any]:
    item = _closed_mapping(value, COLLISION_CONTINUATION_FIELDS, "collision continuation evidence")
    if (
        item["schema_version"] != "1.1" or item["trigger"] != version_collision.TRIGGER
        or not isinstance(item["repository_root"], str) or not 0 < len(item["repository_root"]) <= 4096
    ):
        raise LifecycleOrchestrationError("collision continuation evidence has unsupported semantics")
    return item


def _require_continuation_predecessor(state: Mapping[str, Any], predecessor: str, resulting: str) -> None:
    if (
        state["ready"] is not True or state["draft"] is not False or resulting == predecessor
        or state["unrestricted_review_count"] != authority.MAX_UNRESTRICTED_REVIEWS
        or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
        or state["exceptional_recovery_count"] != authority.MAX_EXCEPTIONAL_RECOVERIES
        or state["exceptional_continuation_count"] != 0 or state["cycle_3_absent"] is not True
    ):
        raise LifecycleOrchestrationError("exceptional continuation requires the exact exhausted Ready predecessor")


def _authenticate_collision_predecessor_safety(
    value: Any, *, reviewed: fast_path.StableFeedbackState, delivery_issue: int,
) -> Any:
    item = copy.deepcopy(value)
    historical = item.pop("historical_thread_classifications", []) if isinstance(item, dict) else []
    if not isinstance(historical, list) or len(historical) > 32:
        raise LifecycleOrchestrationError("historical predecessor classifications exceed the bound")
    prepared = _authenticate_successor_safety_evidence(
        item, repository=reviewed.repository, delivery_issue=delivery_issue,
        pull_request=reviewed.pull_request_number, predecessor_state_digest=reviewed.state_digest,
        resulting_head_sha=reviewed.head_sha, resulting_state_digest=reviewed.state_digest,
    )
    if not historical:
        return prepared
    signer = _successor_classification_signer(reviewed.repository, item["classification_signer"])
    threads = {thread["node_id"]: thread for thread in reviewed.feedback["threads"]}
    for raw in historical:
        try:
            if not isinstance(raw, dict) or set(raw) != {"thread_id", "classification_artifact", "classification_signature"}:
                raise ValueError("historical classification is not closed")
            thread = threads.get(raw["thread_id"])
            if not isinstance(thread, dict) or len(thread["comments"]) != 1 or thread["comments"][0]["reply_to_id"] is not None:
                raise ValueError("historical classification requires an exact reply-free thread")
            for key, limit in (("classification_artifact", late_disposition.MAXIMUM_ARTIFACT_BYTES),
                               ("classification_signature", late_disposition.MAXIMUM_SIGNATURE_BYTES)):
                if not isinstance(raw[key], str) or len(raw[key]) > 4 * limit // 3 + 8:
                    raise ValueError("historical classification exceeds the bound")
            with tempfile.TemporaryDirectory(prefix="secpal-collision-predecessor-") as directory:
                root = Path(directory)
                artifact_path, signature_path = root / "classification.json", root / "classification.sig"
                late_disposition._write_private_file(artifact_path, base64.b64decode(raw["classification_artifact"], validate=True))
                late_disposition._write_private_file(signature_path, base64.b64decode(raw["classification_signature"], validate=True))
                verified = late_disposition.parse_classification_artifact(
                    artifact_path, signature_path, expected_signer=signer, repository=reviewed.repository,
                    delivery_issue_number=delivery_issue, pull_request_number=reviewed.pull_request_number,
                    head_sha=reviewed.head_sha, thread_id=raw["thread_id"],
                )
            authorized = verified.thread
            if (
                authority.loads_closed_json(verified.canonical_payload)["schema_version"] != "1.3"
                or authorized.classification != "VALID_ACTIONABLE" or authorized.disposition != "CORRECTED_AND_VERIFIED"
                or authorized.reply_count != 0 or authorized.reply_state_digest != fast_path.digest_json([])
                or authorized.top_level_comment_node_id != thread["comments"][0]["node_id"]
                or authorized.finding_body_digest != thread["comments"][0]["body_digest"]
                or authorized.is_resolved != thread["is_resolved"] or authorized.is_outdated != thread["is_outdated"]
            ):
                raise ValueError("historical classification does not bind the current thread")
        except (KeyError, TypeError, ValueError, OSError, late_disposition.LateDispositionError) as exc:
            raise LifecycleOrchestrationError("historical predecessor correction is not authenticated") from exc
        sources = (("THREAD_COMMENT", authorized.top_level_comment_node_id, authorized.finding_body_digest, authorized.thread_id),)
        prepared["successor_findings"].append({
            "sources": [{"kind": kind, "node_id": node, "digest": digest} for kind, node, digest, _thread in sources],
            "classification_evidence": fast_path._seal_successor_classification(
                repository=verified.repository, delivery_issue_number=verified.delivery_issue_number,
                pull_request_number=verified.pull_request_number, head_sha=verified.head_sha,
                finding_id=verified.finding_id, finding_evidence_digest=verified.finding_evidence_digest,
                thread_id=authorized.thread_id, top_level_comment_node_id=authorized.top_level_comment_node_id,
                finding_body_digest=authorized.finding_body_digest, reply_count=0,
                is_resolved=authorized.is_resolved, is_outdated=authorized.is_outdated,
                classification=authorized.classification, disposition=authorized.disposition,
                technically_blocking=authorized.technically_blocking, technical_blockers=verified.technical_blockers,
                classification_evidence_digest=verified.evidence_digest, source_bindings=sources,
            ),
        })
    return prepared


def _collision_scope(
    item: Mapping[str, Any], *, observed: Any, resulting_head: str,
    collision_reader: Callable[..., version_collision.VerifiedVersionCollision],
) -> tuple[dict[str, Any], fast_path.StableFeedbackState, fast_path.VerifiedValidationEvidence]:
    if collision_reader is not version_collision.authenticate_collision_source:
        return _collision_scope_from_source(item, observed=observed, resulting_head=resulting_head,
                                            collision_reader=collision_reader)
    with version_collision._authenticated_source_checkout(
        Path(item["repository_root"]), observed.lifecycle.head_sha, resulting_head,
    ) as (root, main):
        def read_collision(**arguments: Any) -> version_collision.VerifiedVersionCollision:
            arguments.pop("repository_root")
            return version_collision._seal_collision(version_collision._derive_collision_from_git(
                root, protected_main=main, **arguments,
            ))

        return _collision_scope_from_source(
            {**item, "repository_root": str(root)}, observed=observed, resulting_head=resulting_head,
            collision_reader=read_collision,
        )


def _collision_scope_from_source(
    item: Mapping[str, Any], *, observed: Any, resulting_head: str,
    collision_reader: Callable[..., version_collision.VerifiedVersionCollision],
) -> tuple[dict[str, Any], fast_path.StableFeedbackState, fast_path.VerifiedValidationEvidence]:
    lifecycle = observed.lifecycle
    _require_continuation_predecessor(lifecycle.state, lifecycle.head_sha, resulting_head)
    reviewed = fast_path.verify_reviewed_state_evidence(item["reviewed_state_evidence"])
    if (
        reviewed.repository != lifecycle.repository or reviewed.pull_request_number != lifecycle.pull_request
        or reviewed.head_sha != lifecycle.head_sha or reviewed.pr_state != "OPEN"
    ):
        raise LifecycleOrchestrationError("collision predecessor feedback differs from CURRENT")
    root = Path(item["repository_root"]).resolve(strict=True)
    sealed = collision_reader(
        repository=lifecycle.repository, delivery_issue=lifecycle.delivery_issue,
        pull_request=lifecycle.pull_request, predecessor_head=lifecycle.head_sha,
        resulting_head=resulting_head, repository_root=root,
    )
    if not isinstance(sealed, version_collision.VerifiedVersionCollision):
        raise LifecycleOrchestrationError("collision authority requires a verifier-sealed result")
    collision = sealed.to_dict()
    if any(collision.get(key) != value for key, value in {
        "repository": lifecycle.repository, "delivery_issue": lifecycle.delivery_issue,
        "pull_request": lifecycle.pull_request, "predecessor_head": lifecycle.head_sha,
        "resulting_head": resulting_head, "trigger": version_collision.TRIGGER,
    }.items()):
        raise LifecycleOrchestrationError("collision authority differs from CURRENT source identity")
    document = fast_path.normalize_exceptional_continuation_evidence(
        item["continuation_document"], repository=lifecycle.repository, reviewed_state=reviewed,
        validated_tree_sha=collision["resulting_tree"], eligibility_evidence=item["eligibility_evidence"],
    )
    state = lifecycle.state
    projection = {
        "unrestricted_reviews": state["unrestricted_review_count"],
        "remediation_cycles": state["remediation_cycle_count"], "cycle_3": not state["cycle_3_absent"],
        "draft": state["draft"], "ready": state["ready"], "ready_transition_count": state["ready_transition_count"],
        "ready_history": state["ready_history"], "exceptional_recovery_count": state["exceptional_recovery_count"],
        "exceptional_recovery_history": state["exceptional_recovery_history"],
        "exceptional_continuation_predecessor_count": 0, "exceptional_continuation_successor_count": 1,
    }
    if (
        document.get("schema_version") != "1.1" or document.get("trigger") != version_collision.TRIGGER
        or document["delivery_issue_number"] != lifecycle.delivery_issue
        or document["prior_ready_tree_sha"] != collision["predecessor_tree"]
        or document["collision_digest"] != fast_path.digest_json(version_collision.validation_collision_projection(collision))
        or document["lifecycle"] != projection
    ):
        raise LifecycleOrchestrationError("continuation evidence differs from authenticated collision")
    source = _authenticate_continuation_commit(
        root, lifecycle.repository, lifecycle.head_sha, resulting_head, document["expected_signer"],
    )
    if source.tree_sha != collision["resulting_tree"]:
        raise LifecycleOrchestrationError("collision successor tree differs from signed source")
    safety = _authenticate_collision_predecessor_safety(
        item["predecessor_safety_evidence"], reviewed=reviewed, delivery_issue=lifecycle.delivery_issue,
    )
    fast_path.verify_clean_feedback_gate(reviewed, safety)
    raw_registry = authority.loads_closed_json(
        bootstrap_source_admission._read_protected_main_registry(collision["protected_main"])
    )
    entries = [entry for entry in raw_registry.get("repositories", [])
               if isinstance(entry, dict) and entry.get("repository") == lifecycle.repository]
    if len(entries) != 1:
        raise LifecycleOrchestrationError("collision validation has no unique accepted registry")
    registry = fast_path.validation_registry_projection(entries[0])
    trailer = publication._run_git(root, ["show", "-s",
        "--format=%(trailers:key=SecPal-Validation-Receipt,valueonly,separator=%x00)", resulting_head])
    if trailer.returncode != 0 or len(trailer.stdout) > 256:
        raise LifecycleOrchestrationError("collision signed validation receipt is unavailable")
    receipt_digest = trailer.stdout.decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None:
        raise LifecycleOrchestrationError("collision signed validation receipt is absent or ambiguous")
    attestation = item["validation_attestation"]
    validation = fast_path.verify_validation_attestation(
        attestation, repository=lifecycle.repository, head_sha=resulting_head,
        registry=registry, command_set=registry["validation"], reviewed_state=reviewed,
        commit_parent_sha=lifecycle.head_sha, commit_tree_sha=source.tree_sha,
        commit_validation_receipt_digest=receipt_digest, delivery_issue_number=lifecycle.delivery_issue,
    )
    if attestation.get("exceptional_continuation_evidence_digest") != fast_path.digest_json(document):
        raise LifecycleOrchestrationError("collision validation does not bind continuation evidence")
    scope = {
        "trigger": version_collision.TRIGGER, "pull_request": lifecycle.pull_request,
        "predecessor_head_sha": lifecycle.head_sha, "resulting_head_sha": resulting_head,
        "collision": collision, "reviewed_state_digest": reviewed.state_digest,
        "stable_state_digest": reviewed.state_digest, "reviewed_feedback_digest": reviewed.feedback_digest,
        "predecessor_safety_digest": fast_path.digest_json(item["predecessor_safety_evidence"]),
        "continuation_evidence_digest": fast_path.digest_json(document),
        "validation_attestation_digest": attestation["attestation_digest"],
        "validation_receipt_digest": receipt_digest,
    }
    return scope, reviewed, validation


def issue_collision_continuation_authorization(
    *, repository: str, delivery_issue: int, authorization_id: str,
    reason: str, resulting_head: str, evidence: Mapping[str, Any],
) -> bytes:
    """Issue existing-family user authority after fixed live and source acquisition."""

    from . import lifecycle_execution

    item = _collision_request(evidence)
    if item["successor_safety_evidence"] is not None:
        raise LifecycleOrchestrationError("collision authorization must precede successor publication")
    observed, lifecycle, _ = _authenticated_current(repository, delivery_issue, publication.verify_current_lifecycle_authority)
    live = _capture_current_stable_feedback(repository, lifecycle.pull_request)
    scope, reviewed, _ = _collision_scope(
        item, observed=observed, resulting_head=_oid(resulting_head, "collision successor"),
        collision_reader=version_collision.authenticate_collision_source,
    )
    if live.to_dict() != reviewed.to_dict() or item["continuation_document"]["authorization_id"] != authorization_id:
        raise LifecycleOrchestrationError("collision authorization differs from exact live predecessor")
    actual_pr = lifecycle_execution._read_live_github(repository, lifecycle.pull_request)
    if (
        actual_pr.repository != repository or actual_pr.pull_request != lifecycle.pull_request
        or actual_pr.head_sha != lifecycle.head_sha or actual_pr.state != "OPEN" or actual_pr.draft is not False
    ):
        raise LifecycleOrchestrationError("collision authorization requires the exact live Ready predecessor")
    final = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    if (
        final.publication_oid != observed.publication_oid
        or final.publication_digest != observed.publication_digest
        or _capture_current_stable_feedback(repository, lifecycle.pull_request).to_dict() != live.to_dict()
        or version_collision._observe_main() != scope["collision"]["protected_main"]
    ):
        raise LifecycleOrchestrationError("collision predecessor changed before authorization signing")
    policy = authority._load_lifecycle_trust_policy(repository)
    identity, signer = lifecycle_execution._policy_role_signer(
        policy, policy.transition_signer_identities, "transition signer role", allow_routine_default=True,
    )
    result = create_user_authorization(
        authorization_id=authorization_id, repository=repository, delivery_issue=delivery_issue,
        lifecycle=lifecycle, publication_oid=observed.publication_oid,
        publication_digest=observed.publication_digest, operation="EXCEPTIONAL_CONTINUATION",
        reason=reason, scope=scope, signer_identity=identity, signer=signer,
    )
    _verify_user_authorization(result, observed, lifecycle)
    return result


def publish_collision_continuation(
    repository: str, delivery_issue: int, request: Mapping[str, Any],
) -> publication.VerifiedLifecyclePublication:
    """Publish one admitted existing transition; no PR or thread mutation is performed."""

    from . import lifecycle_execution

    item = _closed_request(request)
    if item.get("event_kind") != "CONTINUATION_COMMIT_PUSHED":
        raise LifecycleOrchestrationError("collision publication requires the continuation event")
    _collision_request(item.get("continuation_evidence"))
    observed = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    validation: list[tuple[fast_path.VerifiedValidationEvidence, str]] = []
    decision = _orchestrate_event(
        repository, delivery_issue, item, current_reader=lambda *_args: observed,
        _collision_validation_output=validation,
    )
    if decision.lifecycle_transition != "EXCEPTIONAL_CONTINUATION" or len(validation) != 1:
        raise LifecycleOrchestrationError("collision publication has no complete admitted transition")
    authorization = _verify_user_authorization(item["authorization"], observed, observed.lifecycle)
    signers = lifecycle_execution._production_signing_authorities(repository, authorization["signer_identity"])
    successor = lifecycle_execution._append_successor_evidence(
        observed, authorization, signers, resulting_head_sha=item["head_sha"], current_head_evidence=validation[0][0],
    )
    current = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    actual_pr = lifecycle_execution._read_live_github(repository, observed.lifecycle.pull_request)
    if (
        current.publication_oid != observed.publication_oid or current.publication_digest != observed.publication_digest
        or actual_pr.repository != repository or actual_pr.pull_request != observed.lifecycle.pull_request
        or actual_pr.head_sha != item["head_sha"] or actual_pr.state != "OPEN" or actual_pr.draft is not False
        or version_collision._observe_main() != authorization["scope"]["collision"]["protected_main"]
        or _capture_current_stable_feedback(repository, observed.lifecycle.pull_request).state_digest != validation[0][1]
    ):
        raise LifecycleOrchestrationError("collision publication predecessor or live Ready successor drifted")
    published = publication.advance_current_terminal(
        successor, signer_identity=signers.publication_identity, signer=signers.publication_signer,
    )
    readback = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    if (
        readback.publication_oid != published.publication_oid or readback.publication_digest != published.publication_digest
        or readback.lifecycle.head_sha != item["head_sha"]
        or readback.lifecycle.state["exceptional_continuation_count"] != 1
    ):
        raise LifecycleOrchestrationError("collision publication readback is not the exact successor")
    return readback


def _authorized_finding_ids(value: Any) -> list[str]:
    scope = value.get("scope") if isinstance(value, Mapping) else None
    finding_ids = scope.get("finding_ids") if isinstance(scope, Mapping) else None
    if (
        not isinstance(finding_ids, list)
        or not finding_ids
        or len(finding_ids) != len(set(finding_ids))
        or any(not isinstance(item, str) or not item for item in finding_ids)
    ):
        raise LifecycleOrchestrationError(
            "source-change authorization requires exact finding identities"
        )
    for finding_id in finding_ids:
        _identity(finding_id, "authorized finding identity")
    return finding_ids


def _authenticated_current(
    repository: str,
    delivery_issue: int,
    reader: CurrentReader,
) -> tuple[Any, authority.VerifiedLifecycleAuthority, dict[str, Any]]:
    try:
        observed = reader(repository, delivery_issue)
    except (authority.LifecycleAuthorityError, publication.LifecyclePublicationError) as exc:
        raise LifecycleOrchestrationError(
            "CURRENT lifecycle publication is unavailable or invalid"
        ) from exc
    lifecycle = getattr(observed, "lifecycle", None)
    publication_oid = getattr(observed, "publication_oid", None)
    publication_digest = getattr(observed, "publication_digest", None)
    if (
        not isinstance(lifecycle, authority.VerifiedLifecycleAuthority)
        or lifecycle.repository != repository
        or lifecycle.delivery_issue != delivery_issue
    ):
        raise LifecycleOrchestrationError(
            "CURRENT lifecycle publication identity does not match the delivery"
        )
    try:
        state = authority._validate_state(copy.deepcopy(lifecycle.state))
        _oid(publication_oid, "publication object")
        authority._require_digest(publication_digest, "publication digest")
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "CURRENT lifecycle publication is malformed"
        ) from exc
    return observed, lifecycle, state


def _base_decision(
    observed: Any,
    lifecycle: authority.VerifiedLifecycleAuthority,
    state: Mapping[str, Any],
    **changes: Any,
) -> LifecycleDecision:
    fields = {
        "publication_oid": observed.publication_oid,
        "publication_digest": observed.publication_digest,
        "lifecycle_identity": lifecycle.lifecycle_id,
        "pull_request": lifecycle.pull_request,
        "head_sha": lifecycle.head_sha,
        "resulting_pull_request": lifecycle.pull_request,
        "resulting_head_sha": lifecycle.head_sha,
        "unrestricted_reviews": state["unrestricted_review_count"],
        "remediation_cycles": state["remediation_cycle_count"],
        "cycle_3_absent": state["cycle_3_absent"],
        "exceptional_recoveries": state["exceptional_recovery_count"],
        "exceptional_continuations": state["exceptional_continuation_count"],
        "ready": state["ready"],
        "ready_transition_already_performed": state["ready_transition_count"] > 0,
        "preserve_ready": state["ready"],
    }
    fields.update(changes)
    return LifecycleDecision(**fields)


def _prove_transition_is_finite(
    state: Mapping[str, Any], transition: str, event_id: str
) -> None:
    event_digest = authority.digest_json(
        {"event_id": event_id, "transition_kind": transition}
    )
    try:
        authority.derive_state(state, transition, event_digest)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def _orchestrate_event(
    repository: str,
    delivery_issue: int,
    request: Mapping[str, Any],
    *,
    current_reader: CurrentReader = publication.verify_current_lifecycle_authority,
    follow_up_verifier: FollowUpVerifier = follow_up.verify_live_follow_up,
    authorization_verifier: AuthorizationVerifier = _verify_user_authorization,
    feedback_reader: Callable[
        [str, int], fast_path.StableFeedbackState
    ] = _capture_current_stable_feedback,
    collision_reader: Callable[..., version_collision.VerifiedVersionCollision] = version_collision.authenticate_collision_source,
    _collision_validation_output: list[tuple[fast_path.VerifiedValidationEvidence, str]] | None = None,
) -> LifecycleDecision:
    """Authenticate CURRENT state and select one bounded, non-recursive action."""

    try:
        repository = authority._require_repository(repository)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    delivery_issue = _positive_int(delivery_issue, "delivery issue")
    item = _closed_request(request)
    event_kind = item.get("event_kind")
    if event_kind not in EVENTS:
        raise LifecycleOrchestrationError("lifecycle event kind is not allowlisted")
    event_id = _identity(item.get("event_id"), "event identity")
    request_pr = _positive_int(item.get("pull_request"), "event pull request")
    request_head = _oid(item.get("head_sha"), "event head")
    observed, lifecycle, state = _authenticated_current(
        repository, delivery_issue, current_reader
    )
    if request_pr != lifecycle.pull_request:
        raise LifecycleOrchestrationError(
            "event pull request differs from CURRENT lifecycle authority"
        )

    classification_value = item.get("classification")
    follow_up_value = item.get("follow_up")
    authorization_value = item.get("authorization")
    replacement = item.get("replacement_pull_request")
    continuation_evidence = item.get("continuation_evidence")

    if event_kind in OBSERVATION_EVENTS:
        if (
            request_head != lifecycle.head_sha
            or replacement is not None
            or classification_value is not None
            or follow_up_value is not None
            or authorization_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError(
                "observation event differs from CURRENT lifecycle state"
            )
        return _base_decision(observed, lifecycle, state)

    if event_kind == "PR_REPLACED":
        replacement_pr = _positive_int(replacement, "replacement pull request")
        if request_head != lifecycle.head_sha or replacement_pr == lifecycle.pull_request:
            raise LifecycleOrchestrationError("replacement PR binding is invalid")
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("replacement cannot carry feedback facts")
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="PR_REBOUND",
            expected_scope={
                "predecessor_pull_request": lifecycle.pull_request,
                "replacement_pull_request": replacement_pr,
                "head_sha": lifecycle.head_sha,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
        )
        _prove_transition_is_finite(state, "PR_REBOUND", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="PR_REBOUND",
            resulting_pull_request=replacement_pr,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if replacement is not None:
        raise LifecycleOrchestrationError("only PR replacement may name another PR")

    if event_kind == "REMEDIATION_COMMIT_PUSHED":
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError(
                "remediation cannot carry feedback classification"
            )
        if not state["ready"] or request_head == lifecycle.head_sha:
            raise LifecycleOrchestrationError(
                "Ready remediation requires an authenticated new head"
            )
        verified_authorization = authorization_verifier(
            authorization_value, observed, lifecycle
        )
        finding_ids = _authorized_finding_ids(verified_authorization)
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="REMEDIATION_COMPLETED",
            expected_scope={
                "pull_request": lifecycle.pull_request,
                "predecessor_head_sha": lifecycle.head_sha,
                "resulting_head_sha": request_head,
                "finding_ids": finding_ids,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
            verified_item=verified_authorization,
        )
        _prove_transition_is_finite(state, "REMEDIATION_COMPLETED", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="REMEDIATION_COMPLETED",
            preserve_ready=True,
            resulting_head_sha=request_head,
            requires_fresh_head_evidence=True,
            merge_ready=False,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind == "RECOVERY_COMMIT_PUSHED":
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("recovery cannot carry feedback classification")
        if (
            not state["ready"]
            or request_head == lifecycle.head_sha
            or state["unrestricted_review_count"]
            != authority.MAX_UNRESTRICTED_REVIEWS
            or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
        ):
            raise LifecycleOrchestrationError(
                "exceptional recovery requires an exhausted Ready lifecycle and a new head"
            )
        verified_authorization = authorization_verifier(
            authorization_value, observed, lifecycle
        )
        finding_ids = _authorized_finding_ids(verified_authorization)
        scope = verified_authorization.get("scope", {})
        expected_scope = {
            "pull_request": lifecycle.pull_request,
            "predecessor_head_sha": lifecycle.head_sha,
            "resulting_head_sha": request_head,
            "finding_ids": finding_ids,
        }
        if scope.get("admission_kind") == exceptional_recovery.ADMISSION_KIND:
            try:
                exceptional_recovery.authenticate_maintained_code()
                recovery = exceptional_recovery.verify_admission(scope.get("recovery_evidence"), observed, Path.cwd())
                if recovery["authorization_id"] != verified_authorization["authorization_id"]:
                    raise LifecycleOrchestrationError(
                        "diagnostic Recovery authorization identity changed"
                    )
                exceptional_recovery.require_successor(Path.cwd(), recovery, request_head)
                expected_scope = exceptional_recovery.authorization_scope(
                    recovery, request_head
                )
            except exceptional_recovery.DiagnosticRecoveryError as exc:
                raise LifecycleOrchestrationError(str(exc)) from exc
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="EXCEPTIONAL_RECOVERY",
            expected_scope=expected_scope,
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
            verified_item=verified_authorization,
        )
        _prove_transition_is_finite(state, "EXCEPTIONAL_RECOVERY", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="EXCEPTIONAL_RECOVERY",
            preserve_ready=True,
            resulting_head_sha=request_head,
            requires_fresh_head_evidence=True,
            merge_ready=False,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind == "CONTINUATION_COMMIT_PUSHED":
        if classification_value is not None or follow_up_value is not None:
            raise LifecycleOrchestrationError(
                "continuation cannot carry caller-classified feedback"
            )
        _require_continuation_predecessor(state, lifecycle.head_sha, request_head)
        if isinstance(continuation_evidence, Mapping) and continuation_evidence.get("trigger") == version_collision.TRIGGER:
            collision_item = _collision_request(continuation_evidence)
            verified_authorization = authorization_verifier(authorization_value, observed, lifecycle)
            try:
                scope, reviewed, validation = _collision_scope(
                    collision_item, observed=observed, resulting_head=request_head,
                    collision_reader=collision_reader,
                )
                if collision_item["continuation_document"]["authorization_id"] != verified_authorization.get("authorization_id"):
                    raise LifecycleOrchestrationError("collision continuation authorization identity changed")
                authorization = _authorization(
                    authorization_value, event_id=event_id, operation="EXCEPTIONAL_CONTINUATION",
                    expected_scope=scope, observed=observed, lifecycle=lifecycle,
                    verifier=authorization_verifier, verified_item=verified_authorization,
                )
                current = feedback_reader(repository, lifecycle.pull_request)
                successor = _authenticate_successor_safety_evidence(
                    collision_item["successor_safety_evidence"], repository=repository,
                    delivery_issue=delivery_issue, pull_request=lifecycle.pull_request,
                    predecessor_state_digest=reviewed.state_digest, resulting_head_sha=request_head,
                    resulting_state_digest=current.state_digest,
                )
                if successor is None or not any(
                    isinstance(item, dict) and item.get("role") == "CODEX_SUMMARY_UPDATE"
                    for item in successor["provider_transport"]
                ):
                    raise LifecycleOrchestrationError("collision continuation requires resulting-head providers")
                fast_path.verify_collision_feedback_successor(
                    reviewed, current, resulting_head_sha=request_head,
                    successor_safety_evidence=successor,
                )
                _prove_transition_is_finite(state, "EXCEPTIONAL_CONTINUATION", event_id)
            except (fast_path.SecurityBlocker, version_collision.VersionCollisionError, OSError, ValueError) as exc:
                raise LifecycleOrchestrationError("collision continuation authentication failed") from exc
            if _collision_validation_output is not None:
                _collision_validation_output.append((validation, current.state_digest))
            return _base_decision(
                observed, lifecycle, state, lifecycle_transition="EXCEPTIONAL_CONTINUATION",
                preserve_ready=True, resulting_head_sha=request_head, requires_fresh_head_evidence=True,
                merge_ready=False, authorization_digest=authorization["authorization_digest"],
                requires_authorization_publication=True,
            )
        findings = _verify_continuation_finding_authority(
            continuation_evidence,
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=lifecycle.pull_request,
            predecessor_head_sha=lifecycle.head_sha,
            resulting_head_sha=request_head,
            feedback_reader=feedback_reader,
        )
        verified_authorization = authorization_verifier(
            authorization_value, observed, lifecycle
        )
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="EXCEPTIONAL_CONTINUATION",
            expected_scope={
                "pull_request": lifecycle.pull_request,
                "predecessor_head_sha": lifecycle.head_sha,
                "resulting_head_sha": request_head,
                "reviewed_state_digest": findings.reviewed_state_digest,
                "reviewed_feedback_digest": findings.reviewed_feedback_digest,
                "eligibility_evidence_digest": findings.eligibility_evidence_digest,
                "finding_ids": list(findings.finding_ids),
                "thread_ids": list(findings.thread_ids),
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
            verified_item=verified_authorization,
        )
        _prove_transition_is_finite(state, "EXCEPTIONAL_CONTINUATION", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="EXCEPTIONAL_CONTINUATION",
            preserve_ready=True,
            resulting_head_sha=request_head,
            requires_fresh_head_evidence=True,
            merge_ready=False,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if request_head != lifecycle.head_sha:
        raise LifecycleOrchestrationError(
            "event head differs from CURRENT lifecycle authority"
        )

    if event_kind in {"DRAFT_TO_READY", "READY_TO_DRAFT"}:
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("Ready/Draft transition cannot carry feedback facts")
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation=event_kind,
            expected_scope={
                "pull_request": lifecycle.pull_request,
                "head_sha": lifecycle.head_sha,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
        )
        _prove_transition_is_finite(state, event_kind, event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition=event_kind,
            preserve_ready=False,
            transition_to_draft=event_kind == "READY_TO_DRAFT",
            transition_to_ready=event_kind == "DRAFT_TO_READY",
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind == "ADDITIONAL_REVIEW_AUTHORIZED":
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("additional review cannot carry feedback facts")
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="ADDITIONAL_REVIEW",
            expected_scope={
                "pull_request": lifecycle.pull_request,
                "head_sha": lifecycle.head_sha,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
        )
        _prove_transition_is_finite(
            state, "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED", event_id
        )
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
            additional_review_authorized=True,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind != "LATE_FEEDBACK_CLASSIFIED":
        raise LifecycleOrchestrationError("lifecycle event is not implemented")
    if continuation_evidence is not None:
        raise LifecycleOrchestrationError(
            "late feedback cannot carry continuation evidence"
        )
    if authorization_value is not None:
        raise LifecycleOrchestrationError(
            "feedback evidence cannot smuggle lifecycle authorization"
        )
    try:
        classification = replanning.classify(classification_value)
    except replanning.PlanError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc

    guarded_resolution_candidate = False
    resolution_meaning_if_applied = None
    if classification.name == "NON_BLOCKING_FOLLOWUP":
        try:
            identity = follow_up.parse_follow_up(follow_up_value)
            verified_follow_up = follow_up_verifier(identity)
        except follow_up.FollowUpError as exc:
            raise LifecycleOrchestrationError(str(exc)) from exc
        except Exception as exc:
            raise LifecycleOrchestrationError(
                "authenticated live follow-up verification failed"
            ) from exc
        if getattr(verified_follow_up, "identity", None) != identity:
            raise LifecycleOrchestrationError(
                "authenticated live follow-up identity changed"
            )
        guarded_resolution_candidate = True
        resolution_meaning_if_applied = "SAFELY_DISPOSITIONED_TRACKED"
    elif follow_up_value is not None:
        raise LifecycleOrchestrationError(
            "only a canonical non-blocking follow-up may carry tracking identity"
        )

    technically_blocking = classification.technically_blocking
    return _base_decision(
        observed,
        lifecycle,
        state,
        technically_blocking=technically_blocking,
        mechanically_blocking=classification.mechanically_blocking,
        merge_ready=False,
        explicit_recovery_required=technically_blocking and state["ready"],
        resolution_eligible=False,
        guarded_resolution_candidate=guarded_resolution_candidate,
        authenticated_resolution_required=guarded_resolution_candidate,
        resolution_meaning_if_applied=resolution_meaning_if_applied,
    )


def orchestrate_event(
    repository: str,
    delivery_issue: int,
    request: Mapping[str, Any],
) -> LifecycleDecision:
    """Use only maintained CURRENT and live-follow-up authority sources."""

    return _orchestrate_event(
        repository,
        delivery_issue,
        request,
        current_reader=publication.verify_current_lifecycle_authority,
        follow_up_verifier=follow_up.verify_live_follow_up,
    )
