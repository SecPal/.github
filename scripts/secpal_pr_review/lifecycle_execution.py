# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed execution of authenticated Ready/Draft lifecycle decisions.

Lifecycle orchestration remains the decision authority, lifecycle_authority
remains the state-machine authority, and lifecycle_publication remains the
CURRENT/CAS writer.  This module only composes their existing decisions with
one exact GitHub Ready/Draft mutation and bounded convergence verification.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from . import late_disposition
from . import lifecycle_authority as authority
from . import lifecycle_orchestration as orchestration
from . import lifecycle_publication as publication
from .fast_path import canonical_json_bytes


SUPPORTED_OPERATIONS = frozenset({"DRAFT_TO_READY", "READY_TO_DRAFT"})
CURRENT_POSITIONS = frozenset({"PREDECESSOR", "TARGET"})

LIVE_PULL_REQUEST_QUERY = r"""
query LifecycleExecutionPullRequest($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    nameWithOwner
    pullRequest(number:$number) { number state isDraft headRefOid }
  }
}
"""


class LifecycleExecutionError(ValueError):
    """The transition cannot be executed from authenticated external state."""


@dataclass(frozen=True)
class LivePullRequest:
    repository: str
    pull_request: int
    state: str
    head_sha: str
    draft: bool


@dataclass(frozen=True)
class SigningAuthorities:
    transition_identity: str
    transition_signer: authority.Signer
    authority_identity: str
    authority_signer: authority.Signer
    publication_identity: str
    publication_signer: authority.Signer


@dataclass(frozen=True)
class LifecycleExecutionResult:
    status: str
    observed_case: str
    operation: str
    repository: str
    delivery_issue: int
    pull_request: int
    head_sha: str
    authorization_digest: str
    github_write_attempts: int
    publication_write_attempts: int
    github_target_verified: bool
    current_target_verified: bool
    publication_oid: str | None
    publication_digest: str | None


CurrentReader = Callable[[str, int], publication.VerifiedLifecyclePublication]
HistoricalReader = Callable[
    [str, int, str], publication.VerifiedLifecyclePublicationTransition
]
GitHubReader = Callable[[str, int], LivePullRequest]
GitHubWriter = Callable[[str, int, str], str]
Publisher = Callable[..., publication.VerifiedLifecyclePublication]
SigningAuthorityProvider = Callable[[str, str], SigningAuthorities]


def classify_observed_state(
    *, github_draft: bool, current_position: str, operation: str
) -> str:
    """Classify the closed two-authority state without performing observation."""

    if operation not in SUPPORTED_OPERATIONS:
        raise LifecycleExecutionError("lifecycle transition is not executable")
    if not isinstance(github_draft, bool) or current_position not in CURRENT_POSITIONS:
        raise LifecycleExecutionError("observed lifecycle execution state is unknown")
    predecessor_draft = operation == "DRAFT_TO_READY"
    github_at_predecessor = github_draft is predecessor_draft
    current_at_predecessor = current_position == "PREDECESSOR"
    if github_at_predecessor and current_at_predecessor:
        return "NOT_STARTED"
    if not github_at_predecessor and current_at_predecessor:
        return "GITHUB_APPLIED_PUBLICATION_PENDING"
    if not github_at_predecessor and not current_at_predecessor:
        return "COMPLETE"
    if github_at_predecessor and not current_at_predecessor:
        return "UNSAFE_REVERSE_PARTIAL"


def _validate_live_pull_request(
    observed: Any, authorization: Mapping[str, Any]
) -> LivePullRequest:
    if not isinstance(observed, LivePullRequest):
        raise LifecycleExecutionError("live GitHub pull-request evidence is malformed")
    try:
        repository = authority._require_repository(observed.repository)
        pull_request = authority._require_positive_int(
            observed.pull_request, "live pull request"
        )
        head_sha = authority._require_oid(observed.head_sha, "live pull-request head")
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleExecutionError(str(exc)) from exc
    if (
        repository != authorization["repository"]
        or pull_request != authorization["pull_request"]
        or head_sha != authorization["head_sha"]
        or observed.state != "OPEN"
        or not isinstance(observed.draft, bool)
    ):
        raise LifecycleExecutionError("live GitHub pull-request identity or state changed")
    return observed


def _is_exact_predecessor(
    observed: Any, authorization: Mapping[str, Any]
) -> bool:
    lifecycle = getattr(observed, "lifecycle", None)
    return (
        isinstance(observed, publication.VerifiedLifecyclePublication)
        and isinstance(lifecycle, authority.VerifiedLifecycleAuthority)
        and observed.publication_oid == authorization["publication_oid"]
        and observed.publication_digest == authorization["publication_digest"]
        and lifecycle.repository == authorization["repository"]
        and lifecycle.delivery_issue == authorization["delivery_issue"]
        and lifecycle.lifecycle_id == authorization["lifecycle_id"]
        and lifecycle.pull_request == authorization["pull_request"]
        and lifecycle.head_sha == authorization["head_sha"]
        and lifecycle.authority_digest == authorization["authority_digest"]
    )


def _request_from_authorization(authorization: Mapping[str, Any]) -> dict[str, Any]:
    operation = authorization["operation"]
    digest = authorization["authorization_digest"]
    return {
        "event_kind": operation,
        "event_id": f"authorization:{digest}",
        "pull_request": authorization["pull_request"],
        "head_sha": authorization["head_sha"],
        "replacement_pull_request": None,
        "classification": None,
        "follow_up": None,
        "authorization": None,
    }


def _authenticate_predecessor_decision(
    observed: publication.VerifiedLifecyclePublication,
    serialized_authorization: bytes | str,
    authorization: Mapping[str, Any],
) -> orchestration.LifecycleDecision:
    request = _request_from_authorization(authorization)
    request["authorization"] = serialized_authorization
    try:
        decision = orchestration._orchestrate_event(
            authorization["repository"],
            authorization["delivery_issue"],
            request,
            current_reader=lambda *_args: observed,
        )
    except orchestration.LifecycleOrchestrationError as exc:
        raise LifecycleExecutionError(
            "authenticated orchestration decision is not executable"
        ) from exc
    if (
        decision.lifecycle_transition != authorization["operation"]
        or decision.authorization_digest != authorization["authorization_digest"]
        or decision.publication_oid != authorization["publication_oid"]
        or decision.publication_digest != authorization["publication_digest"]
        or decision.lifecycle_identity != authorization["lifecycle_id"]
        or decision.pull_request != authorization["pull_request"]
        or decision.head_sha != authorization["head_sha"]
    ):
        raise LifecycleExecutionError("authenticated orchestration decision changed")
    return decision


def _validate_transition_delta(
    transition: publication.VerifiedLifecyclePublicationTransition,
    authorization: Mapping[str, Any],
    serialized_authorization: bytes | str,
) -> None:
    predecessor = transition.predecessor
    successor = transition.successor
    try:
        verified_authorization = orchestration._verify_user_authorization(
            serialized_authorization, predecessor, predecessor.lifecycle
        )
        orchestration._authorization(
            serialized_authorization,
            event_id=transition.event_id,
            operation=authorization["operation"],
            expected_scope={
                "pull_request": authorization["pull_request"],
                "head_sha": authorization["head_sha"],
            },
            observed=predecessor,
            lifecycle=predecessor.lifecycle,
            verifier=orchestration._verify_user_authorization,
            verified_item=verified_authorization,
        )
        successor_state = _derive_transition_state(
            predecessor.lifecycle,
            transition.transition_kind,
            transition.event_digest,
        )
    except (authority.LifecycleAuthorityError, orchestration.LifecycleOrchestrationError) as exc:
        raise LifecycleExecutionError("published transition authority is invalid") from exc
    if (
        transition.transition_kind != authorization["operation"]
        or transition.event_id
        != f"authorization:{authorization['authorization_digest']}"
        or transition.event_signer_identity != authorization["signer_identity"]
        or transition.pull_request != authorization["pull_request"]
        or transition.predecessor_authority_digest != authorization["authority_digest"]
        or transition.predecessor_head_sha != authorization["head_sha"]
        or transition.resulting_head_sha != authorization["head_sha"]
        or transition.initialization_evidence_digest
        != predecessor.lifecycle.initialization_evidence_digest
        or successor.lifecycle.repository != predecessor.lifecycle.repository
        or successor.lifecycle.delivery_issue != predecessor.lifecycle.delivery_issue
        or successor.lifecycle.lifecycle_id != predecessor.lifecycle.lifecycle_id
        or successor.lifecycle.initialization_evidence_digest
        != predecessor.lifecycle.initialization_evidence_digest
        or successor.lifecycle.pull_request != predecessor.lifecycle.pull_request
        or successor.lifecycle.head_sha != predecessor.lifecycle.head_sha
        or successor.lifecycle.state != successor_state
    ):
        raise LifecycleExecutionError("published transition is not the exact authorization successor")


def _authenticate_target(
    observed: publication.VerifiedLifecyclePublication,
    serialized_authorization: bytes | str,
    authorization: Mapping[str, Any],
    historical_reader: HistoricalReader,
) -> publication.VerifiedLifecyclePublicationTransition:
    try:
        transition = historical_reader(
            authorization["repository"],
            authorization["delivery_issue"],
            authorization["publication_oid"],
        )
    except (authority.LifecycleAuthorityError, publication.LifecyclePublicationError) as exc:
        raise LifecycleExecutionError("authorized predecessor has no exact published successor") from exc
    _validate_transition_delta(transition, authorization, serialized_authorization)
    target = transition.successor
    if (
        observed.publication_oid != target.publication_oid
        or observed.publication_digest != target.publication_digest
        or observed.lifecycle != target.lifecycle
    ):
        raise LifecycleExecutionError("CURRENT is not the exact authorized successor")
    return transition


def _current_position(
    observed: publication.VerifiedLifecyclePublication,
    serialized_authorization: bytes | str,
    authorization: Mapping[str, Any],
    historical_reader: HistoricalReader,
) -> tuple[str, publication.VerifiedLifecyclePublicationTransition | None]:
    if _is_exact_predecessor(observed, authorization):
        _authenticate_predecessor_decision(
            observed, serialized_authorization, authorization
        )
        return "PREDECESSOR", None
    return "TARGET", _authenticate_target(
        observed, serialized_authorization, authorization, historical_reader
    )


def _append_successor_evidence(
    predecessor: publication.VerifiedLifecyclePublication,
    authorization: Mapping[str, Any],
    signers: SigningAuthorities,
) -> bytes:
    raw = predecessor.serialized_lifecycle_evidence
    if not isinstance(raw, bytes):
        raise LifecycleExecutionError("authenticated CURRENT evidence is unavailable")
    try:
        parsed = authority._load_canonical_json(raw, "CURRENT lifecycle evidence")
        if not isinstance(parsed, dict):
            raise authority.LifecycleAuthorityError("CURRENT lifecycle evidence is malformed")
        event = authority.create_transition_authorization(
            event_id=f"authorization:{authorization['authorization_digest']}",
            repository=predecessor.lifecycle.repository,
            delivery_issue=predecessor.lifecycle.delivery_issue,
            lifecycle_id=predecessor.lifecycle.lifecycle_id,
            pull_request=predecessor.lifecycle.pull_request,
            predecessor_authority_digest=predecessor.lifecycle.authority_digest,
            predecessor_head_sha=predecessor.lifecycle.head_sha,
            resulting_head_sha=predecessor.lifecycle.head_sha,
            transition_kind=authorization["operation"],
            replacement_pull_request=None,
            initialization_evidence_digest=(
                predecessor.lifecycle.initialization_evidence_digest
            ),
            signer_identity=signers.transition_identity,
            signer=signers.transition_signer,
        )
        if (
            parsed.get("kind") == authority.EXACT_ADOPTION_EVIDENCE_KIND
            and set(parsed) == authority.EXACT_ADOPTION_PUBLICATION_FIELDS
        ):
            snapshot = authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=raw,
                authorization=event,
                signer_identity=signers.authority_identity,
                authority_signer=signers.authority_signer,
            )
            parsed["transition_authorizations"].append(event)
            parsed["authority_chain"].append(snapshot)
        else:
            bundle = (
                parsed.get("lifecycle_evidence")
                if parsed.get("kind") == authority.PUBLICATION_EVIDENCE_KIND
                else parsed
            )
            if not isinstance(bundle, dict):
                raise authority.LifecycleAuthorityError(
                    "CURRENT lifecycle evidence bundle is malformed"
                )
            events = bundle.get("transition_authorizations")
            snapshots = bundle.get("authority_chain")
            if not isinstance(events, list) or not isinstance(snapshots, list):
                raise authority.LifecycleAuthorityError(
                    "CURRENT lifecycle evidence chain is malformed"
                )
            policy = authority._load_lifecycle_trust_policy(
                predecessor.lifecycle.repository
            )
            snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=snapshots,
                transition_authorizations=events,
                authorization=event,
                signer_identity=signers.authority_identity,
                authority_signer=signers.authority_signer,
                accepted_event_signers=policy.transition_signer_identities,
                accepted_authority_signers=policy.authority_signer_identities,
                signature_verifier=authority._policy_signature_verifier(policy),
            )
            events.append(event)
            snapshots.append(snapshot)
        successor_raw = canonical_json_bytes(parsed)
        admitted_initialization = None
        if predecessor.lifecycle.historical_proof_mode == authority.NATIVE_PROOF_MODE:
            native_bundle = (
                parsed.get("lifecycle_evidence")
                if parsed.get("kind") == authority.PUBLICATION_EVIDENCE_KIND
                else parsed
            )
            if not isinstance(native_bundle, dict) or not isinstance(
                native_bundle.get("delivery_initialization"), dict
            ):
                raise authority.LifecycleAuthorityError(
                    "native CURRENT initialization is unavailable"
                )
            admitted_initialization = native_bundle["delivery_initialization"]
        successor = authority._verify_lifecycle_authority_for_journal(
            successor_raw, admitted_initialization=admitted_initialization
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleExecutionError("exact lifecycle successor could not be derived") from exc
    expected_state = _derive_transition_state(
        predecessor.lifecycle, authorization["operation"], event["event_digest"]
    )
    if (
        successor.repository != predecessor.lifecycle.repository
        or successor.delivery_issue != predecessor.lifecycle.delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle.lifecycle_id
        or successor.initialization_evidence_digest
        != predecessor.lifecycle.initialization_evidence_digest
        or successor.pull_request != predecessor.lifecycle.pull_request
        or successor.head_sha != predecessor.lifecycle.head_sha
        or successor.state != expected_state
    ):
        raise LifecycleExecutionError("derived lifecycle successor changed preserved state")
    return successor_raw


def _derive_transition_state(
    lifecycle: authority.VerifiedLifecycleAuthority,
    transition_kind: str,
    event_digest: str,
) -> dict[str, Any]:
    adopted = (
        lifecycle.historical_proof_mode == authority.EXACT_ADOPTION_PROOF_MODE
    )
    state = authority._validate_state(
        copy.deepcopy(lifecycle.state),
        allow_adopted_observations=adopted,
    )
    return authority._derive_state(
        state,
        transition_kind,
        event_digest,
        allow_adopted_observations=adopted,
    )


def _single_role_identity(identities: frozenset[str], label: str) -> str:
    if len(identities) != 1:
        raise LifecycleExecutionError(f"{label} is not one closed maintained signer")
    return next(iter(identities))


def _policy_role_signer(
    policy: authority.LifecycleTrustPolicy,
    identities: frozenset[str],
    label: str,
    *,
    allow_routine_default: bool,
) -> tuple[str, authority.Signer]:
    identity = _single_role_identity(identities, label)
    try:
        environment = late_disposition.signing_environment()
        signature_format, signing_key = (
            late_disposition.read_role_signing_configuration(
                identity,
                allow_routine_default=allow_routine_default,
                environment=environment,
            )
        )
    except late_disposition.LateDispositionError as exc:
        raise LifecycleExecutionError(str(exc)) from exc
    if signature_format not in policy.accepted_formats:
        raise LifecycleExecutionError(
            "maintained local signing format is not accepted by policy"
        )
    verifier = authority._policy_signature_verifier(
        policy, command_environment=environment
    )

    def sign(payload: bytes, domain: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory(prefix="secpal-lifecycle-execution-sign-") as directory:
            root = Path(directory)
            artifact = root / "payload"
            artifact.write_bytes(payload)
            try:
                if signature_format == "ssh":
                    executable = late_disposition._trusted_executable("ssh-keygen")
                    completed = late_disposition._run_signature_command(
                        executable,
                        ("-Y", "sign", "-f", signing_key, "-n", domain, str(artifact)),
                        environment=environment,
                    )
                    signature_path = Path(f"{artifact}.sig")
                elif signature_format == "openpgp":
                    executable = late_disposition._trusted_executable("gpg")
                    signature_path = root / "payload.asc"
                    completed = late_disposition._run_signature_command(
                        executable,
                        (
                            "--batch", "--no-tty", "--armor", "--local-user",
                            signing_key, "--output", str(signature_path),
                            "--detach-sign", str(artifact),
                        ),
                        environment=environment,
                    )
                else:
                    raise LifecycleExecutionError(
                        "maintained signature format is unsupported"
                    )
            except late_disposition.LateDispositionError as exc:
                raise LifecycleExecutionError(
                    "maintained lifecycle credential is unusable"
                ) from exc
            try:
                signature = signature_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise LifecycleExecutionError(
                    "maintained lifecycle credential is unusable"
                ) from exc
            if completed.returncode != 0 or not signature:
                raise LifecycleExecutionError(
                    "maintained lifecycle credential is unusable"
                )
            result = {
                "format": signature_format,
                "signer_identity": identity,
                "value": signature,
            }
            try:
                verified = verifier(payload, result, identity, domain)
            except authority.LifecycleAuthorityError as exc:
                raise LifecycleExecutionError(
                    "maintained lifecycle credential does not match accepted policy identity"
                ) from exc
            if (
                verified.signer_identity != identity
                or verified.signature_format != signature_format
            ):
                raise LifecycleExecutionError(
                    "maintained lifecycle credential does not match accepted policy identity"
                )
            return result

    return identity, sign


def _production_signing_authorities(
    repository: str, authorization_signer: str
) -> SigningAuthorities:
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleExecutionError("maintained lifecycle signing policy is unavailable") from exc
    transition_identity, transition_signer = _policy_role_signer(
        policy,
        policy.transition_signer_identities,
        "transition signer role",
        allow_routine_default=True,
    )
    authority_identity, authority_signer = _policy_role_signer(
        policy,
        policy.authority_signer_identities,
        "authority signer role",
        allow_routine_default=True,
    )
    publication_identity, publication_signer = _policy_role_signer(
        policy,
        policy.publication_signer_identities,
        "publication signer role",
        allow_routine_default=True,
    )
    if authorization_signer != transition_identity:
        raise LifecycleExecutionError("authorization signer differs from maintained transition signer")
    return SigningAuthorities(
        transition_identity, transition_signer,
        authority_identity, authority_signer,
        publication_identity, publication_signer,
    )


def _production_legacy_adoption_signer(
    repository: str,
) -> tuple[str, authority.Signer]:
    """Supply the maintained exact-adoption constructors' accepted signer role."""

    try:
        policy = authority._load_lifecycle_trust_policy(repository)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleExecutionError(
            "maintained lifecycle signing policy is unavailable"
        ) from exc
    return _policy_role_signer(
        policy,
        policy.legacy_adoption_signer_identities,
        "legacy-adoption signer role",
        allow_routine_default=False,
    )


def _read_live_github(repository: str, pull_request: int) -> LivePullRequest:
    owner, name = repository.split("/", 1)
    arguments = [
        "api", "--hostname", "github.com", "graphql",
        "-f", f"query={LIVE_PULL_REQUEST_QUERY}",
        "-f", f"owner={owner}", "-f", f"name={name}",
        "-F", f"number={pull_request}",
    ]
    result = publication._run_gh(arguments)
    if result.returncode != 0:
        raise LifecycleExecutionError("live GitHub pull-request observation is unavailable")
    try:
        value = json.loads(
            result.stdout, object_pairs_hook=publication._reject_duplicate_pairs
        )
        if not isinstance(value, dict) or value.get("errors"):
            raise LifecycleExecutionError(
                "live GitHub pull-request observation is incomplete"
            )
        observed_repository = value["data"]["repository"]
        observed_pr = observed_repository["pullRequest"]
        if not isinstance(observed_repository, dict) or not isinstance(
            observed_pr, dict
        ):
            raise LifecycleExecutionError(
                "live GitHub pull-request observation is incomplete"
            )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleExecutionError("live GitHub pull-request observation is malformed") from exc
    return LivePullRequest(
        repository=observed_repository.get("nameWithOwner"),
        pull_request=observed_pr.get("number"),
        state=observed_pr.get("state"),
        head_sha=observed_pr.get("headRefOid"),
        draft=observed_pr.get("isDraft"),
    )


def _write_live_github(repository: str, pull_request: int, operation: str) -> str:
    if operation not in SUPPORTED_OPERATIONS:
        raise LifecycleExecutionError("GitHub lifecycle mutation is not allowlisted")
    arguments = ["pr", "ready", str(pull_request), "--repo", repository]
    if operation == "READY_TO_DRAFT":
        arguments.append("--undo")
    result = publication._run_gh(arguments)
    return "SUCCESS" if result.returncode == 0 else "AMBIGUOUS"


def _result(
    *, status: str, observed_case: str, authorization: Mapping[str, Any],
    github_attempts: int, publication_attempts: int,
    github_verified: bool, current_verified: bool,
    current: publication.VerifiedLifecyclePublication | None,
) -> LifecycleExecutionResult:
    return LifecycleExecutionResult(
        status=status,
        observed_case=observed_case,
        operation=authorization["operation"],
        repository=authorization["repository"],
        delivery_issue=authorization["delivery_issue"],
        pull_request=authorization["pull_request"],
        head_sha=authorization["head_sha"],
        authorization_digest=authorization["authorization_digest"],
        github_write_attempts=github_attempts,
        publication_write_attempts=publication_attempts,
        github_target_verified=github_verified,
        current_target_verified=current_verified,
        publication_oid=(None if current is None else current.publication_oid),
        publication_digest=(None if current is None else current.publication_digest),
    )


def _execute_lifecycle_transition(
    repository: str,
    delivery_issue: int,
    serialized_authorization: bytes | str,
    *,
    current_reader: CurrentReader,
    historical_reader: HistoricalReader,
    github_reader: GitHubReader,
    github_writer: GitHubWriter,
    publisher: Publisher,
    signing_authority_provider: SigningAuthorityProvider,
) -> LifecycleExecutionResult:
    try:
        repository = authority._require_repository(repository)
        delivery_issue = authority._require_positive_int(delivery_issue, "delivery issue")
        authorization = orchestration._verify_signed_user_authorization(
            serialized_authorization, repository
        )
    except (authority.LifecycleAuthorityError, orchestration.LifecycleOrchestrationError) as exc:
        raise LifecycleExecutionError("lifecycle execution authorization is invalid") from exc
    if (
        authorization["delivery_issue"] != delivery_issue
        or authorization["operation"] not in SUPPORTED_OPERATIONS
    ):
        raise LifecycleExecutionError("authorization does not select this executable transition")

    current = current_reader(repository, delivery_issue)
    position, _ = _current_position(
        current, serialized_authorization, authorization, historical_reader
    )
    live = _validate_live_pull_request(
        github_reader(repository, authorization["pull_request"]), authorization
    )
    observed_case = classify_observed_state(
        github_draft=live.draft,
        current_position=position,
        operation=authorization["operation"],
    )
    github_attempts = 0
    publication_attempts = 0

    if observed_case == "UNSAFE_REVERSE_PARTIAL":
        raise LifecycleExecutionError("CURRENT target with GitHub predecessor is unsafe")
    if observed_case == "COMPLETE":
        final_github = _validate_live_pull_request(
            github_reader(repository, authorization["pull_request"]), authorization
        )
        final_current = current_reader(repository, delivery_issue)
        final_position, _ = _current_position(
            final_current, serialized_authorization, authorization, historical_reader
        )
        if classify_observed_state(
            github_draft=final_github.draft,
            current_position=final_position,
            operation=authorization["operation"],
        ) != "COMPLETE":
            raise LifecycleExecutionError("final lifecycle convergence changed")
        return _result(
            status="COMPLETE", observed_case="COMPLETE",
            authorization=authorization, github_attempts=0,
            publication_attempts=0, github_verified=True,
            current_verified=True, current=final_current,
        )

    if observed_case == "NOT_STARTED":
        current = current_reader(repository, delivery_issue)
        if not _is_exact_predecessor(current, authorization):
            raise LifecycleExecutionError("CURRENT changed before GitHub mutation")
        _authenticate_predecessor_decision(
            current, serialized_authorization, authorization
        )
        live = _validate_live_pull_request(
            github_reader(repository, authorization["pull_request"]), authorization
        )
        if classify_observed_state(
            github_draft=live.draft,
            current_position="PREDECESSOR",
            operation=authorization["operation"],
        ) != "NOT_STARTED":
            raise LifecycleExecutionError("GitHub state changed before mutation")
        github_attempts = 1
        try:
            github_outcome = github_writer(
                repository, authorization["pull_request"], authorization["operation"]
            )
        except Exception:
            github_outcome = "AMBIGUOUS"
        if github_outcome not in {"SUCCESS", "AMBIGUOUS"}:
            raise LifecycleExecutionError("GitHub mutation returned unknown semantics")
        live = _validate_live_pull_request(
            github_reader(repository, authorization["pull_request"]), authorization
        )
        readback_case = classify_observed_state(
            github_draft=live.draft,
            current_position="PREDECESSOR",
            operation=authorization["operation"],
        )
        if readback_case == "NOT_STARTED":
            return _result(
                status="GITHUB_MUTATION_INCOMPLETE",
                observed_case="NOT_STARTED", authorization=authorization,
                github_attempts=github_attempts, publication_attempts=0,
                github_verified=False, current_verified=False, current=current,
            )
        if readback_case != "GITHUB_APPLIED_PUBLICATION_PENDING":
            raise LifecycleExecutionError("GitHub mutation read-back is unsafe")

    current = current_reader(repository, delivery_issue)
    if not _is_exact_predecessor(current, authorization):
        raise LifecycleExecutionError("CURRENT changed before successor publication")
    _authenticate_predecessor_decision(current, serialized_authorization, authorization)
    live = _validate_live_pull_request(
        github_reader(repository, authorization["pull_request"]), authorization
    )
    if classify_observed_state(
        github_draft=live.draft,
        current_position="PREDECESSOR",
        operation=authorization["operation"],
    ) != "GITHUB_APPLIED_PUBLICATION_PENDING":
        raise LifecycleExecutionError("GitHub target changed before successor publication")
    signers = signing_authority_provider(repository, authorization["signer_identity"])
    successor_raw = _append_successor_evidence(current, authorization, signers)
    current = current_reader(repository, delivery_issue)
    if not _is_exact_predecessor(current, authorization):
        raise LifecycleExecutionError("CURRENT changed immediately before publication")
    _authenticate_predecessor_decision(current, serialized_authorization, authorization)
    live = _validate_live_pull_request(
        github_reader(repository, authorization["pull_request"]), authorization
    )
    if classify_observed_state(
        github_draft=live.draft,
        current_position="PREDECESSOR",
        operation=authorization["operation"],
    ) != "GITHUB_APPLIED_PUBLICATION_PENDING":
        raise LifecycleExecutionError(
            "GitHub target changed immediately before publication"
        )
    publication_attempts = 1
    try:
        published = publisher(
            successor_raw,
            signer_identity=signers.publication_identity,
            signer=signers.publication_signer,
        )
    except Exception:
        observed_current = current_reader(repository, delivery_issue)
        if _is_exact_predecessor(observed_current, authorization):
            return _result(
                status="PUBLICATION_PENDING",
                observed_case="GITHUB_APPLIED_PUBLICATION_PENDING",
                authorization=authorization, github_attempts=github_attempts,
                publication_attempts=publication_attempts,
                github_verified=True, current_verified=False,
                current=observed_current,
            )
        _authenticate_target(
            observed_current, serialized_authorization, authorization,
            historical_reader,
        )
    else:
        observed_current = current_reader(repository, delivery_issue)
        _authenticate_target(
            observed_current, serialized_authorization, authorization,
            historical_reader,
        )
        if (
            not isinstance(published, publication.VerifiedLifecyclePublication)
            or published.publication_oid != observed_current.publication_oid
            or published.publication_digest != observed_current.publication_digest
            or published.lifecycle != observed_current.lifecycle
        ):
            raise LifecycleExecutionError("publication response differs from verified CURRENT")

    final_github = _validate_live_pull_request(
        github_reader(repository, authorization["pull_request"]), authorization
    )
    final_current = current_reader(repository, delivery_issue)
    final_position, _ = _current_position(
        final_current, serialized_authorization, authorization, historical_reader
    )
    if classify_observed_state(
        github_draft=final_github.draft,
        current_position=final_position,
        operation=authorization["operation"],
    ) != "COMPLETE":
        raise LifecycleExecutionError("final GitHub/CURRENT convergence is not exact")
    return _result(
        status="COMPLETE", observed_case=observed_case,
        authorization=authorization, github_attempts=github_attempts,
        publication_attempts=publication_attempts,
        github_verified=True, current_verified=True, current=final_current,
    )


def execute_lifecycle_transition(
    repository: str,
    delivery_issue: int,
    serialized_authorization: bytes | str,
) -> LifecycleExecutionResult:
    """Execute one exact signed Ready/Draft authorization and verify convergence."""

    return _execute_lifecycle_transition(
        repository,
        delivery_issue,
        serialized_authorization,
        current_reader=publication.verify_current_lifecycle_authority,
        historical_reader=publication._verify_historical_lifecycle_transition,
        github_reader=_read_live_github,
        github_writer=_write_live_github,
        publisher=publication.advance_current_terminal,
        signing_authority_provider=_production_signing_authorities,
    )
