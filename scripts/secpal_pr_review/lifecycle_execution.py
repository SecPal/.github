# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed execution of authenticated Ready/Draft lifecycle decisions.

Lifecycle orchestration remains the decision authority, lifecycle_authority
remains the state-machine authority, and lifecycle_publication remains the
CURRENT/CAS writer.  This module only composes their existing decisions with
one exact GitHub Ready/Draft mutation and bounded convergence verification.
"""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from . import late_disposition
from . import lifecycle_authority as authority
from . import lifecycle_orchestration as orchestration
from . import lifecycle_publication as publication
from . import fast_path
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

LIVE_PULL_REQUEST_HISTORY_QUERY = r"""
query LifecycleExecutionHistory($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      timelineItems(first:100, itemTypes:[PULL_REQUEST_COMMIT,READY_FOR_REVIEW_EVENT,CONVERT_TO_DRAFT_EVENT,HEAD_REF_FORCE_PUSHED_EVENT]) {
        pageInfo { hasNextPage }
        nodes {
          __typename
          ... on PullRequestCommit { commit { oid } }
        }
      }
    }
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
class GitHubLifecycleEvent:
    kind: str
    head_sha: str | None


@dataclass(frozen=True)
class GitHubLifecycleHistory:
    complete: bool
    events: tuple[GitHubLifecycleEvent, ...]


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
GitHubHistoryReader = Callable[[str, int], GitHubLifecycleHistory]
SourceCommitAuthenticator = Callable[..., fast_path.AuthenticatedIntegrationCommit]


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
    observed: Any, authorization: Mapping[str, Any], *, expected_head: str | None = None
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
        or head_sha != (authorization["head_sha"] if expected_head is None else expected_head)
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
    *,
    resulting_head_sha: str | None = None,
    current_head_evidence: fast_path.VerifiedValidationEvidence | None = None,
) -> bytes:
    raw = predecessor.serialized_lifecycle_evidence
    if not isinstance(raw, bytes):
        raise LifecycleExecutionError("authenticated CURRENT evidence is unavailable")
    try:
        parsed = authority._load_canonical_json(raw, "CURRENT lifecycle evidence")
        if not isinstance(parsed, dict):
            raise authority.LifecycleAuthorityError("CURRENT lifecycle evidence is malformed")
        resulting_head = (
            predecessor.lifecycle.head_sha
            if resulting_head_sha is None
            else authority._require_oid(resulting_head_sha, "resulting head")
        )
        event = authority.create_transition_authorization(
            event_id=f"authorization:{authorization['authorization_digest']}",
            repository=predecessor.lifecycle.repository,
            delivery_issue=predecessor.lifecycle.delivery_issue,
            lifecycle_id=predecessor.lifecycle.lifecycle_id,
            pull_request=predecessor.lifecycle.pull_request,
            predecessor_authority_digest=predecessor.lifecycle.authority_digest,
            predecessor_head_sha=predecessor.lifecycle.head_sha,
            resulting_head_sha=resulting_head,
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
                current_head_evidence=current_head_evidence,
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
                current_head_evidence=current_head_evidence,
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
        or successor.head_sha != resulting_head
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


def _read_live_github_history(
    repository: str, pull_request: int
) -> GitHubLifecycleHistory:
    owner, name = repository.split("/", 1)
    result = publication._run_gh(
        [
            "api", "--hostname", "github.com", "graphql",
            "-f", f"query={LIVE_PULL_REQUEST_HISTORY_QUERY}",
            "-f", f"owner={owner}", "-f", f"name={name}",
            "-F", f"number={pull_request}",
        ]
    )
    if result.returncode != 0:
        raise LifecycleExecutionError("GitHub lifecycle history is unavailable")
    try:
        value = json.loads(
            result.stdout, object_pairs_hook=publication._reject_duplicate_pairs
        )
        connection = value["data"]["repository"]["pullRequest"]["timelineItems"]
        nodes = connection["nodes"]
        if value.get("errors") or not isinstance(nodes, list):
            raise LifecycleExecutionError("GitHub lifecycle history is incomplete")
        names = {
            "ReadyForReviewEvent": "READY",
            "ConvertToDraftEvent": "DRAFT",
            "HeadRefForcePushedEvent": "FORCE_PUSH",
        }
        events: list[GitHubLifecycleEvent] = []
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("__typename"), str):
                raise LifecycleExecutionError("GitHub lifecycle history is malformed")
            typename = node["__typename"]
            if typename == "PullRequestCommit":
                head = authority._require_oid(node["commit"]["oid"], "timeline commit")
                events.append(GitHubLifecycleEvent("COMMIT", head))
            elif typename in names:
                events.append(GitHubLifecycleEvent(names[typename], None))
            else:
                raise LifecycleExecutionError("GitHub lifecycle history is not closed")
        complete = connection["pageInfo"]["hasNextPage"] is False
    except (
        KeyError,
        TypeError,
        json.JSONDecodeError,
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleExecutionError("GitHub lifecycle history is malformed") from exc
    return GitHubLifecycleHistory(complete=complete, events=tuple(events))


def _validate_github_ready_history(
    observed: Any, predecessor_head: str, resulting_head: str
) -> None:
    if not isinstance(observed, GitHubLifecycleHistory) or observed.complete is not True:
        raise LifecycleExecutionError(
            "GitHub Ready history exceeds the closed timelineItems(first:100) bound"
        )
    if any(
        not isinstance(event, GitHubLifecycleEvent)
        or event.kind not in {"COMMIT", "READY", "DRAFT", "FORCE_PUSH"}
        or (event.kind == "COMMIT") != (event.head_sha is not None)
        for event in observed.events
    ):
        raise LifecycleExecutionError("GitHub Ready history is malformed")
    predecessor_positions = [
        index
        for index, event in enumerate(observed.events)
        if event.kind == "COMMIT" and event.head_sha == predecessor_head
    ]
    resulting_positions = [
        index
        for index, event in enumerate(observed.events)
        if event.kind == "COMMIT" and event.head_sha == resulting_head
    ]
    if len(predecessor_positions) != 1 or len(resulting_positions) != 1:
        raise LifecycleExecutionError("GitHub Ready history does not bind both heads")
    start, end = predecessor_positions[0], resulting_positions[0]
    between = observed.events[start + 1 : end]
    if (
        start >= end
        or sum(event.kind == "READY" for event in between) != 1
        or any(event.kind in {"COMMIT", "DRAFT", "FORCE_PUSH"} for event in between)
        or any(
            event.kind in {"COMMIT", "DRAFT", "FORCE_PUSH", "READY"}
            for event in observed.events[end + 1 :]
        )
    ):
        raise LifecycleExecutionError("GitHub Ready/head chronology is ambiguous")


def _reauthenticate_external_convergence(
    repository: str,
    authorization: Mapping[str, Any],
    resulting_head: str,
    github_reader: GitHubReader,
    github_history_reader: GitHubHistoryReader,
) -> None:
    live = _validate_live_pull_request(
        github_reader(repository, authorization["pull_request"]),
        authorization,
        expected_head=resulting_head,
    )
    if live.draft:
        raise LifecycleExecutionError("GitHub is still Draft")
    _validate_github_ready_history(
        github_history_reader(repository, authorization["pull_request"]),
        authorization["head_sha"],
        resulting_head,
    )


def _source_signature_policy(
    policy: authority.LifecycleTrustPolicy,
) -> dict[str, Any]:
    return {
        # GitHub verification is authenticated independently from the live API
        # below.  This policy describes only the local commit verifier whose
        # digest is retained by AuthenticatedIntegrationCommit.
        "require_github_verified": False,
        "require_local_verified": True,
        "accepted_formats": sorted(policy.accepted_formats),
    }


def _ssh_public_key_fingerprint(public_key: str) -> str:
    if not isinstance(public_key, str):
        raise LifecycleExecutionError("maintained SSH key is malformed")
    fields = public_key.strip().split()
    if len(fields) not in {2, 3} or fields[0] not in {
        "ssh-ed25519",
        "ssh-rsa",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
    }:
        raise LifecycleExecutionError("maintained SSH key is malformed")
    try:
        decoded = base64.b64decode(fields[1], validate=True)
    except (ValueError, TypeError) as exc:
        raise LifecycleExecutionError("maintained SSH key is malformed") from exc
    if not decoded:
        raise LifecycleExecutionError("maintained SSH key is malformed")
    fingerprint = base64.b64encode(hashlib.sha256(decoded).digest()).decode("ascii")
    return f"SHA256:{fingerprint.rstrip('=')}"


def _verify_live_github_commit_signature(repository: str, head_sha: str) -> None:
    result = publication._run_gh(
        [
            "api",
            "--hostname",
            "github.com",
            f"repos/{repository}/commits/{head_sha}",
        ]
    )
    if result.returncode != 0:
        raise LifecycleExecutionError("GitHub source signature verification failed")
    try:
        payload = json.loads(result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
        verification = payload["commit"]["verification"]
        if (
            payload["sha"] != head_sha
            or not isinstance(verification, dict)
            or verification.get("verified") is not True
            or verification.get("reason") != "valid"
        ):
            raise LifecycleExecutionError("GitHub verification rejected source head")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LifecycleExecutionError(
            "GitHub source signature verification is malformed"
        ) from exc


def _authenticate_source_commit(
    repository: str,
    head_sha: str,
    signer_identity: str,
) -> fast_path.AuthenticatedIntegrationCommit:
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
        signer = policy.signers[signer_identity]
    except (KeyError, authority.LifecycleAuthorityError) as exc:
        raise LifecycleExecutionError("source signer is not maintained") from exc
    _verify_live_github_commit_signature(repository, head_sha)
    maintained_ssh_fingerprints = frozenset(
        _ssh_public_key_fingerprint(public_key)
        for public_key in signer.ssh_public_keys
    )
    expected: list[dict[str, str]] = []
    if signer.ssh_public_keys:
        expected.append({"kind": "SSH_PRINCIPAL", "identity": signer_identity})
    expected.extend(
        {"kind": "OPENPGP_FINGERPRINT", "identity": fingerprint}
        for fingerprint in signer.openpgp_fingerprints
    )
    authenticated: list[fast_path.AuthenticatedIntegrationCommit] = []
    rejected_ssh_fingerprint = False
    for expected_signer in expected:
        try:
            candidate = fast_path.authenticate_integration_commit(
                repository_root=Path.cwd(),
                repository=repository,
                head_sha=head_sha,
                expected_signer=expected_signer,
                signature_policy=_source_signature_policy(policy),
            )
        except (fast_path.RecoverableLocalError, fast_path.SecurityBlocker):
            continue
        if (
            candidate.signer_kind == "SSH_PRINCIPAL"
            and candidate.signature_fingerprint not in maintained_ssh_fingerprints
        ):
            rejected_ssh_fingerprint = True
            continue
        authenticated.append(candidate)
    if len(authenticated) != 1:
        if rejected_ssh_fingerprint and not authenticated:
            raise LifecycleExecutionError(
                "source head signature does not match a maintained key"
            )
        raise LifecycleExecutionError("source head signer is invalid or ambiguous")
    return authenticated[0]


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
    result_head: str | None = None,
) -> LifecycleExecutionResult:
    return LifecycleExecutionResult(
        status=status,
        observed_case=observed_case,
        operation=authorization["operation"],
        repository=authorization["repository"],
        delivery_issue=authorization["delivery_issue"],
        pull_request=authorization["pull_request"],
        head_sha=(authorization["head_sha"] if result_head is None else result_head),
        authorization_digest=authorization["authorization_digest"],
        github_write_attempts=github_attempts,
        publication_write_attempts=publication_attempts,
        github_target_verified=github_verified,
        current_target_verified=current_verified,
        publication_oid=(None if current is None else current.publication_oid),
        publication_digest=(None if current is None else current.publication_digest),
    )


def _same_publication(
    left: publication.VerifiedLifecyclePublication,
    right: publication.VerifiedLifecyclePublication,
) -> bool:
    return (
        isinstance(left, publication.VerifiedLifecyclePublication)
        and isinstance(right, publication.VerifiedLifecyclePublication)
        and left.publication_oid == right.publication_oid
        and left.publication_digest == right.publication_digest
        and left.lifecycle == right.lifecycle
    )


def _verified_lifecycle_from_raw(raw: bytes) -> authority.VerifiedLifecycleAuthority:
    try:
        parsed = authority._load_canonical_json(raw, "derived lifecycle successor")
        admitted_initialization = None
        if parsed.get("kind") != authority.EXACT_ADOPTION_EVIDENCE_KIND:
            bundle = (
                parsed.get("lifecycle_evidence")
                if parsed.get("kind") == authority.PUBLICATION_EVIDENCE_KIND
                else parsed
            )
            if isinstance(bundle, dict):
                admitted_initialization = bundle.get("delivery_initialization")
        return authority._verify_lifecycle_authority_for_journal(
            raw, admitted_initialization=admitted_initialization
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleExecutionError("derived lifecycle successor is invalid") from exc


def _validate_remediation_transition_delta(
    transition: publication.VerifiedLifecyclePublicationTransition,
    authorization: Mapping[str, Any],
    validation: fast_path.VerifiedValidationEvidence,
) -> None:
    predecessor = transition.predecessor
    successor = transition.successor
    try:
        expected_state = _derive_transition_state(
            predecessor.lifecycle,
            "REMEDIATION_COMPLETED",
            transition.event_digest,
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleExecutionError("published remediation state is invalid") from exc
    if (
        transition.transition_kind != "REMEDIATION_COMPLETED"
        or transition.event_id
        != f"authorization:{authorization['authorization_digest']}"
        or transition.event_signer_identity != authorization["signer_identity"]
        or transition.pull_request != authorization["pull_request"]
        or transition.predecessor_authority_digest
        != predecessor.lifecycle.authority_digest
        or transition.predecessor_head_sha != authorization["head_sha"]
        or transition.resulting_head_sha != validation.head_sha
        or successor.lifecycle.repository != predecessor.lifecycle.repository
        or successor.lifecycle.delivery_issue != predecessor.lifecycle.delivery_issue
        or successor.lifecycle.lifecycle_id != predecessor.lifecycle.lifecycle_id
        or successor.lifecycle.pull_request != predecessor.lifecycle.pull_request
        or successor.lifecycle.head_sha != validation.head_sha
        or successor.lifecycle.tree_sha != validation.tree_sha
        or successor.lifecycle.validation_receipt_digest
        != validation.validation_receipt_digest
        or successor.lifecycle.source_validation_evidence_digest
        != validation.source_validation_evidence_digest
        or successor.lifecycle.adoption_source_evidence_digest
        != validation.final_attestation_digest
        or successor.lifecycle.state != expected_state
    ):
        raise LifecycleExecutionError(
            "published remediation is not the exact authenticated successor"
        )


def _verify_remediation_authorization(
    raw: bytes | str,
    predecessor: publication.VerifiedLifecyclePublication,
    ready_successor: publication.VerifiedLifecyclePublication,
    resulting_head: str,
) -> tuple[dict[str, Any], orchestration.LifecycleDecision]:
    try:
        verified = orchestration._verify_user_authorization(
            raw, predecessor, predecessor.lifecycle
        )
        finding_ids = orchestration._authorized_finding_ids(verified)
        event_id = f"authorization:{verified['authorization_digest']}"
        orchestration._authorization(
            raw,
            event_id=event_id,
            operation="REMEDIATION_COMPLETED",
            expected_scope={
                "pull_request": predecessor.lifecycle.pull_request,
                "predecessor_head_sha": predecessor.lifecycle.head_sha,
                "resulting_head_sha": resulting_head,
                "finding_ids": finding_ids,
            },
            observed=predecessor,
            lifecycle=predecessor.lifecycle,
            verifier=orchestration._verify_user_authorization,
            verified_item=verified,
        )
        request = {
            "event_kind": "REMEDIATION_COMMIT_PUSHED",
            "event_id": event_id,
            "pull_request": predecessor.lifecycle.pull_request,
            "head_sha": resulting_head,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": raw,
        }
        preverified = lambda *_args: copy.deepcopy(verified)
        try:
            orchestration._orchestrate_event(
                predecessor.lifecycle.repository,
                predecessor.lifecycle.delivery_issue,
                request,
                current_reader=lambda *_args: predecessor,
                authorization_verifier=preverified,
            )
        except orchestration.LifecycleOrchestrationError:
            pass
        else:
            raise LifecycleExecutionError(
                "source transition is valid while Draft; ordering is ambiguous"
            )
        decision = orchestration._orchestrate_event(
            predecessor.lifecycle.repository,
            predecessor.lifecycle.delivery_issue,
            request,
            current_reader=lambda *_args: ready_successor,
            authorization_verifier=preverified,
        )
    except (authority.LifecycleAuthorityError, orchestration.LifecycleOrchestrationError) as exc:
        raise LifecycleExecutionError(
            "remediation source-change authorization is invalid"
        ) from exc
    if (
        decision.lifecycle_transition != "REMEDIATION_COMPLETED"
        or decision.preserve_ready is not True
        or decision.transition_to_draft
        or decision.resulting_head_sha != resulting_head
        or decision.authorization_digest != verified["authorization_digest"]
    ):
        raise LifecycleExecutionError("remediation transition ordering is ambiguous")
    return verified, decision


def _validate_source_advancement(
    repository: str,
    delivery_issue: int,
    predecessor_head: str,
    authorization: Mapping[str, Any],
    validation: Any,
    authenticated_commit: Any,
) -> None:
    if (
        not authority.is_verified_validation_evidence(validation)
        or validation.repository != repository
        or validation.delivery_issue_number != delivery_issue
        or validation.pull_request_number != authorization["pull_request"]
        or validation.head_sha != authorization["scope"]["resulting_head_sha"]
    ):
        raise LifecycleExecutionError("remediation validation evidence is invalid")
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
        maintained_signer = policy.signers[authorization["signer_identity"]]
    except (KeyError, authority.LifecycleAuthorityError) as exc:
        raise LifecycleExecutionError("remediation source signer is not maintained") from exc
    if not isinstance(authenticated_commit, fast_path.AuthenticatedIntegrationCommit):
        raise LifecycleExecutionError("remediation source head is not authenticated")
    if authenticated_commit.signer_kind == "SSH_PRINCIPAL":
        expected_signer = {
            "kind": "SSH_PRINCIPAL",
            "identity": authorization["signer_identity"],
        }
        signer_accepted = bool(maintained_signer.ssh_public_keys)
    else:
        expected_signer = {
            "kind": "OPENPGP_FINGERPRINT",
            "identity": authenticated_commit.signer_identity,
        }
        signer_accepted = (
            authenticated_commit.signer_identity.upper()
            in {item.upper() for item in maintained_signer.openpgp_fingerprints}
        )
    if (
        not signer_accepted
        or not fast_path._authenticated_integration_commit_agrees(
            authenticated_commit,
            repository=repository,
            head_sha=validation.head_sha,
            tree_sha=validation.tree_sha,
            parent_shas=[predecessor_head],
            expected_signer=expected_signer,
            signature_policy=_source_signature_policy(policy),
        )
    ):
        raise LifecycleExecutionError(
            "remediation source lineage, tree, or signer is invalid"
        )


def _converge_pending_ready_head_advancement(
    repository: str,
    delivery_issue: int,
    serialized_ready_authorization: bytes | str,
    serialized_remediation_authorization: bytes | str,
    remediation_validation_evidence: fast_path.VerifiedValidationEvidence,
    *,
    current_reader: CurrentReader,
    historical_reader: HistoricalReader,
    github_reader: GitHubReader,
    github_history_reader: GitHubHistoryReader,
    publisher: Publisher,
    signing_authority_provider: SigningAuthorityProvider,
    source_commit_authenticator: SourceCommitAuthenticator,
) -> LifecycleExecutionResult:
    """Converge one fixed Ready publication followed by one remediation head."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = authority._require_positive_int(
            delivery_issue, "delivery issue"
        )
        ready_authorization = orchestration._verify_signed_user_authorization(
            serialized_ready_authorization, repository
        )
    except (authority.LifecycleAuthorityError, orchestration.LifecycleOrchestrationError) as exc:
        raise LifecycleExecutionError("Ready authorization is invalid") from exc
    if (
        ready_authorization["delivery_issue"] != delivery_issue
        or ready_authorization["operation"] != "DRAFT_TO_READY"
    ):
        raise LifecycleExecutionError("convergence requires exact Draft-to-Ready authority")
    if not isinstance(
        remediation_validation_evidence, fast_path.VerifiedValidationEvidence
    ):
        raise LifecycleExecutionError("remediation validation evidence is malformed")

    current = current_reader(repository, delivery_issue)
    if _is_exact_predecessor(current, ready_authorization):
        predecessor = current
        ready_transition = None
        position = "PREDECESSOR"
    else:
        try:
            ready_transition = historical_reader(
                repository, delivery_issue, ready_authorization["publication_oid"]
            )
        except (authority.LifecycleAuthorityError, publication.LifecyclePublicationError) as exc:
            raise LifecycleExecutionError("pending Ready predecessor is not CURRENT ancestry") from exc
        _validate_transition_delta(
            ready_transition, ready_authorization, serialized_ready_authorization
        )
        predecessor = ready_transition.predecessor
        if _same_publication(current, ready_transition.successor):
            position = "MIDPOINT"
        else:
            position = "TARGET_CANDIDATE"

    _authenticate_predecessor_decision(
        predecessor, serialized_ready_authorization, ready_authorization
    )
    _reauthenticate_external_convergence(
        repository,
        ready_authorization,
        remediation_validation_evidence.head_sha,
        github_reader,
        github_history_reader,
    )

    signers = signing_authority_provider(
        repository, ready_authorization["signer_identity"]
    )
    if ready_transition is None:
        ready_raw = _append_successor_evidence(
            predecessor, ready_authorization, signers
        )
        ready_lifecycle = _verified_lifecycle_from_raw(ready_raw)
        ready_successor = publication.VerifiedLifecyclePublication(
            "f" * 40,
            authority.digest_json({"candidate": ready_lifecycle.authority_digest}),
            predecessor.publication_branch,
            predecessor.publication_oid,
            predecessor.publication_oid,
            ready_lifecycle,
            ready_raw,
        )
    else:
        ready_raw = ready_transition.successor.serialized_lifecycle_evidence
        ready_successor = ready_transition.successor

    remediation_authorization, _ = _verify_remediation_authorization(
        serialized_remediation_authorization,
        predecessor,
        ready_successor,
        remediation_validation_evidence.head_sha,
    )
    if remediation_authorization["signer_identity"] != signers.transition_identity:
        raise LifecycleExecutionError(
            "remediation authorization signer differs from maintained transition signer"
        )
    authenticated_commit = source_commit_authenticator(
        repository,
        remediation_validation_evidence.head_sha,
        remediation_authorization["signer_identity"],
    )
    _validate_source_advancement(
        repository,
        delivery_issue,
        ready_authorization["head_sha"],
        remediation_authorization,
        remediation_validation_evidence,
        authenticated_commit,
    )

    remediation_transition = None
    if position == "TARGET_CANDIDATE":
        try:
            remediation_transition = historical_reader(
                repository, delivery_issue, ready_successor.publication_oid
            )
        except (authority.LifecycleAuthorityError, publication.LifecyclePublicationError) as exc:
            raise LifecycleExecutionError("CURRENT is not an exact composed successor") from exc
        _validate_remediation_transition_delta(
            remediation_transition,
            remediation_authorization,
            remediation_validation_evidence,
        )
        if not _same_publication(current, remediation_transition.successor):
            raise LifecycleExecutionError("CURRENT advanced incompatibly")
        position = "TARGET"

    publication_attempts = 0
    if position == "PREDECESSOR":
        before = current_reader(repository, delivery_issue)
        if not _same_publication(before, predecessor):
            raise LifecycleExecutionError("CURRENT changed before Ready publication")
        _reauthenticate_external_convergence(
            repository,
            ready_authorization,
            remediation_validation_evidence.head_sha,
            github_reader,
            github_history_reader,
        )
        publication_attempts += 1
        try:
            published = publisher(
                ready_raw,
                signer_identity=signers.publication_identity,
                signer=signers.publication_signer,
            )
        except Exception:
            published = None
        observed = current_reader(repository, delivery_issue)
        if _same_publication(observed, predecessor):
            return _result(
                status="PUBLICATION_PENDING",
                observed_case="COMPOSED_HEAD_ADVANCEMENT",
                authorization=ready_authorization,
                github_attempts=0,
                publication_attempts=publication_attempts,
                github_verified=True,
                current_verified=False,
                current=observed,
                result_head=remediation_validation_evidence.head_sha,
            )
        ready_transition = historical_reader(
            repository, delivery_issue, predecessor.publication_oid
        )
        _validate_transition_delta(
            ready_transition, ready_authorization, serialized_ready_authorization
        )
        ready_successor = ready_transition.successor
        if not _same_publication(observed, ready_successor):
            raise LifecycleExecutionError("Ready midpoint publication is incompatible")
        if published is not None and not _same_publication(published, observed):
            raise LifecycleExecutionError("Ready publication response differs from CURRENT")
        position = "MIDPOINT"

    if position == "MIDPOINT":
        _reauthenticate_external_convergence(
            repository,
            ready_authorization,
            remediation_validation_evidence.head_sha,
            github_reader,
            github_history_reader,
        )
        observed = current_reader(repository, delivery_issue)
        if not _same_publication(observed, ready_successor):
            raise LifecycleExecutionError("CURRENT changed before remediation publication")
        remediation_raw = _append_successor_evidence(
            ready_successor,
            remediation_authorization,
            signers,
            resulting_head_sha=remediation_validation_evidence.head_sha,
            current_head_evidence=remediation_validation_evidence,
        )
        publication_attempts += 1
        try:
            published = publisher(
                remediation_raw,
                signer_identity=signers.publication_identity,
                signer=signers.publication_signer,
            )
        except Exception:
            published = None
        observed = current_reader(repository, delivery_issue)
        if _same_publication(observed, ready_successor):
            return _result(
                status="PUBLICATION_PENDING",
                observed_case="COMPOSED_HEAD_ADVANCEMENT",
                authorization=ready_authorization,
                github_attempts=0,
                publication_attempts=publication_attempts,
                github_verified=True,
                current_verified=False,
                current=observed,
                result_head=remediation_validation_evidence.head_sha,
            )
        remediation_transition = historical_reader(
            repository, delivery_issue, ready_successor.publication_oid
        )
        _validate_remediation_transition_delta(
            remediation_transition,
            remediation_authorization,
            remediation_validation_evidence,
        )
        if not _same_publication(observed, remediation_transition.successor):
            raise LifecycleExecutionError("remediation publication is incompatible")
        if published is not None and not _same_publication(published, observed):
            raise LifecycleExecutionError("remediation publication response differs from CURRENT")

    _reauthenticate_external_convergence(
        repository,
        ready_authorization,
        remediation_validation_evidence.head_sha,
        github_reader,
        github_history_reader,
    )
    final_current = current_reader(repository, delivery_issue)
    if remediation_transition is None:
        remediation_transition = historical_reader(
            repository, delivery_issue, ready_successor.publication_oid
        )
        _validate_remediation_transition_delta(
            remediation_transition,
            remediation_authorization,
            remediation_validation_evidence,
        )
    if not _same_publication(final_current, remediation_transition.successor):
        raise LifecycleExecutionError("final composed lifecycle convergence is not exact")
    return _result(
        status="COMPLETE",
        observed_case="COMPOSED_HEAD_ADVANCEMENT",
        authorization=ready_authorization,
        github_attempts=0,
        publication_attempts=publication_attempts,
        github_verified=True,
        current_verified=True,
        current=final_current,
        result_head=remediation_validation_evidence.head_sha,
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


def converge_pending_ready_head_advancement(
    repository: str,
    delivery_issue: int,
    serialized_ready_authorization: bytes | str,
    serialized_remediation_authorization: bytes | str,
    remediation_validation_evidence: fast_path.VerifiedValidationEvidence,
) -> LifecycleExecutionResult:
    """Converge the sole supported two-successor lifecycle publication shape."""

    return _converge_pending_ready_head_advancement(
        repository,
        delivery_issue,
        serialized_ready_authorization,
        serialized_remediation_authorization,
        remediation_validation_evidence,
        current_reader=publication.verify_current_lifecycle_authority,
        historical_reader=publication._verify_historical_lifecycle_transition,
        github_reader=_read_live_github,
        github_history_reader=_read_live_github_history,
        publisher=publication.advance_current_terminal,
        signing_authority_provider=_production_signing_authorities,
        source_commit_authenticator=_authenticate_source_commit,
    )
