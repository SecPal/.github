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
from . import fast_path
from . import follow_up
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication


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
    reviewed_state_digest: str
    reviewed_feedback_digest: str
    eligibility_evidence_digest: str
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


def _verify_continuation_finding_authority(
    value: Any,
    *,
    repository: str,
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
        fast_path.verify_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=resulting_head_sha,
            authorized_thread_ids=thread_ids,
            successor_safety_evidence=item.get("successor_safety_evidence"),
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
        },
        repository=repository,
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
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="EXCEPTIONAL_RECOVERY",
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
        if (
            state["ready"] is not True
            or state["draft"] is not False
            or request_head == lifecycle.head_sha
            or state["unrestricted_review_count"]
            != authority.MAX_UNRESTRICTED_REVIEWS
            or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
            or state["exceptional_recovery_count"]
            != authority.MAX_EXCEPTIONAL_RECOVERIES
            or state["exceptional_continuation_count"] != 0
            or state["cycle_3_absent"] is not True
        ):
            raise LifecycleOrchestrationError(
                "exceptional continuation requires the exact exhausted Ready predecessor"
            )
        findings = _verify_continuation_finding_authority(
            continuation_evidence,
            repository=repository,
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
