# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One protected-main, migration-signed pre-enrollment source admission."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Iterator, Mapping

from . import bootstrap_source_admission as transport
from . import fast_path
from . import lifecycle_authority as authority
from . import lifecycle_execution as execution
from . import lifecycle_publication as publication


KIND = "SECPAL_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_ADMISSION"
DOMAIN = "secpal.pre-enrollment-validation-evidence-loss-admission/v1"
ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/pre-enrollment-validation-evidence-loss.json"
CURRENT_SAFETY_PATH = "tests/pre-enrollment-current-safety.py"
CURRENT_SAFETY_INVARIANTS = (
    "candidate_local_issuer_rejected", "complete_feedback", "context_binding",
    "historical_bytes_unavailable", "ordinary_prior_ready", "resolved_feedback",
    "signed_authority_required", "source_history", "wrong_signer",
)
_VERIFIED = object()
_UNSUPPLIED = object()
FIELDS = frozenset({
    "schema_version", "kind", "domain", "repository", "delivery_issue",
    "pull_request", "head_sha", "tree_sha", "parent_sha", "pull_request_state",
    "draft", "source_signer_identity", "commit_signature_evidence_digest",
    "historical_validation_receipt_digest", "historical_package_status",
    "historical_final_attestation_digest", "historical_bytes_reconstructed",
    "loss_proof_policy_digest", "accepted_main_sha", "current_safety",
    "observed_pre_enrollment_history", "intended_state", "adoption_timestamp",
    "admission_id", "bounded_uses", "signer_identity", "signature", "admission_digest",
})
SAFETY_FIELDS = frozenset({
    "receipt_digest", "validated_tree_sha", "validation_policy_digest",
    "command_set_digest", "feedback_digest", "technical_decisions", "successful_result",
})
DECISION_FIELDS = frozenset({
    "source_id", "source_digest", "disposition", "evidence_digest",
})
RECORD_FIELDS = frozenset({
    "repository", "delivery_issue", "pull_request", "head_sha", "tree_sha",
    "parent_sha", "source_signer_identity", "historical_validation_receipt_digest",
    "historical_package_status", "historical_final_attestation_digest",
    "historical_bytes_reconstructed", "observed_pre_enrollment_history",
    "feedback_digest", "technical_decisions",
})
_CHRONOLOGY_PAGE_SIZE = 50
_CHRONOLOGY_MAXIMUM_EVENTS = 100
_CHRONOLOGY_MAXIMUM_PAGES = 2
_CHRONOLOGY_QUERY = r"""
query PreEnrollmentChronology($owner:String!, $name:String!, $number:Int!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    nameWithOwner
    pullRequest(number:$number) {
      number
      timelineItems(first:50, after:$cursor, itemTypes:[READY_FOR_REVIEW_EVENT,CONVERT_TO_DRAFT_EVENT]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on ReadyForReviewEvent { id createdAt }
          ... on ConvertToDraftEvent { id createdAt }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class VerifiedPreEnrollmentValidationEvidenceLossAdmission:
    canonical_admission: dict[str, Any]
    _verification_seal: object


@dataclass(frozen=True)
class PullRequestFacts:
    number: int
    state: str
    draft: bool
    merged: bool
    head_sha: str
    head_repository: str
    base_repository: str
    base_ref: str
    created_at: str


@dataclass(frozen=True)
class IssueFacts:
    number: int
    state: str


@dataclass(frozen=True)
class CommitFacts:
    head_sha: str
    parent_shas: tuple[str, ...]
    committed_at: str


@dataclass(frozen=True)
class CurrentHarnessBlobObservation:
    """Raw Git tree representation captured without deciding conformance."""

    commit_oid: str
    requested_path: str
    tree_entry: bytes


@dataclass(frozen=True)
class CurrentHarnessBlobFacts:
    """Canonical facts normalized from one protected-main tree entry."""

    repository_path: str
    mode: str
    object_type: str
    object_oid: str
    size: int | None


@dataclass(frozen=True)
class CurrentHarnessBlobBinding:
    """Admitted exact repository-blob authority for one registered member."""

    commit_oid: str
    repository_path: str
    mode: str
    blob_oid: str
    size: int


@dataclass(frozen=True)
class SourceCommitFacts:
    head_sha: str
    tree_sha: str
    parent_shas: tuple[str, ...]
    signature_verified: bool


@dataclass(frozen=True)
class ChronologyObservation:
    """Bounded maintained GitHub projections captured without admission."""

    pages: tuple[bytes, ...]


@dataclass(frozen=True)
class ChronologyEvent:
    identity: str
    kind: str
    occurred_at: str


@dataclass(frozen=True)
class NormalizedProviderFacts:
    pull_request: PullRequestFacts
    issue: IssueFacts
    commits: tuple[CommitFacts, ...]
    timeline_events: tuple[ChronologyEvent, ...]
    source_commit: SourceCommitFacts


def _intended_state() -> dict[str, Any]:
    state = authority.initial_state()
    state.update(unrestricted_review_count=1, remediation_cycle_count=2)
    return state


def _decisions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise authority.LifecycleAuthorityError("loss admission technical decisions are missing")
    seen: set[str] = set()
    for raw in value:
        item = authority._require_closed(raw, DECISION_FIELDS, "loss technical decision")
        identity = authority._require_identity(item["source_id"], "technical source")
        if identity in seen or item["disposition"] not in {
            "CORRECTED_AND_VERIFIED", "DISPROVEN_WITH_EVIDENCE", "NON_ACTIONABLE",
        }:
            raise authority.LifecycleAuthorityError("blocking or ambiguous loss technical decision")
        seen.add(identity)
        authority._require_digest(item["source_digest"], "technical source digest")
        authority._require_digest(item["evidence_digest"], "technical proof digest")
    return copy.deepcopy(value)


def _verify_document(value: Any) -> dict[str, Any]:
    """Verify immutable enrollment provenance without consulting a later CURRENT."""

    doc = copy.deepcopy(authority._require_closed(value, FIELDS, "validation-evidence-loss admission"))
    if (
        doc["schema_version"] != "1.0" or doc["kind"] != KIND or doc["domain"] != DOMAIN
        or doc["pull_request_state"] != "OPEN" or doc["draft"] is not True
        or doc["historical_package_status"] != "UNAVAILABLE"
        or doc["historical_final_attestation_digest"] is not None
        or doc["historical_bytes_reconstructed"] is not False
        or type(doc["bounded_uses"]) is not int or doc["bounded_uses"] != 1
    ):
        raise authority.LifecycleAuthorityError("loss admission cannot reconstruct history or authorize Ready")
    authority._require_repository(doc["repository"])
    for field in ("delivery_issue", "pull_request"):
        authority._require_positive_int(doc[field], field)
    for field in ("head_sha", "tree_sha", "parent_sha", "accepted_main_sha"):
        authority._require_oid(doc[field], field)
    if doc["head_sha"] == doc["parent_sha"]:
        raise authority.LifecycleAuthorityError("loss admission parent topology is invalid")
    for field in (
        "commit_signature_evidence_digest", "historical_validation_receipt_digest",
        "loss_proof_policy_digest", "admission_digest",
    ):
        authority._require_digest(doc[field], field)
    for field in ("source_signer_identity", "signer_identity", "admission_id"):
        authority._require_identity(doc[field], field)
    state = authority._validate_state(doc["intended_state"], allow_adopted_observations=True)
    if state != _intended_state():
        raise authority.LifecycleAuthorityError("loss admission must preserve exhausted Draft counters")
    history = authority._normalize_observed_pre_enrollment_history(
        doc["observed_pre_enrollment_history"], expected_head=doc["head_sha"],
        intended_state=state, review_budget_consumption_admitted=True,
    )
    timestamp = authority._parse_adoption_timestamp(doc["adoption_timestamp"], "loss admission time")
    if timestamp < authority._parse_adoption_timestamp(history[-1]["observed_at"], "last observation"):
        raise authority.LifecycleAuthorityError("loss admission cannot be backdated")
    safety = authority._require_closed(doc["current_safety"], SAFETY_FIELDS, "current safety evidence")
    if safety["successful_result"] is not True or safety["validated_tree_sha"] != doc["tree_sha"]:
        raise authority.LifecycleAuthorityError("loss admission requires exact successful current validation")
    for field in ("receipt_digest", "validation_policy_digest", "command_set_digest", "feedback_digest"):
        authority._require_digest(safety[field], field)
    if safety["receipt_digest"] == doc["historical_validation_receipt_digest"]:
        raise authority.LifecycleAuthorityError("loss admission requires divergent current safety evidence")
    _decisions(safety["technical_decisions"])
    signed = {key: item for key, item in doc.items() if key != "admission_digest"}
    if authority.digest_json(signed) != doc["admission_digest"]:
        raise authority.LifecycleAuthorityError("loss admission digest changed")
    trust = authority._load_lifecycle_trust_policy(doc["repository"])
    authority._verify_signature(
        authority.canonical_json_bytes(authority._unsigned(doc, "admission_digest", "signature")),
        doc["signature"], doc["signer_identity"], DOMAIN,
        trust.legacy_adoption_signer_identities, authority._policy_signature_verifier(trust),
    )
    return doc


def _verified_document(value: Any) -> dict[str, Any]:
    if type(value) is not VerifiedPreEnrollmentValidationEvidenceLossAdmission or value._verification_seal is not _VERIFIED:
        raise authority.LifecycleAuthorityError("loss source requires verifier-sealed admission")
    return _verify_document(value.canonical_admission)


def verify(serialized: bytes | str) -> VerifiedPreEnrollmentValidationEvidenceLossAdmission:
    doc = _verify_document(authority.loads_closed_json(serialized))
    _reauthenticate(doc)
    return VerifiedPreEnrollmentValidationEvidenceLossAdmission(copy.deepcopy(doc), _VERIFIED)


def _gh_json(endpoint: str) -> Any:
    result = transport._run_bootstrap_gh(["api", "--hostname", "github.com", endpoint])
    if result.returncode != 0:
        raise authority.LifecycleAuthorityError("loss admission provider acquisition failed")
    return authority.loads_closed_json(result.stdout)


_ACCEPTED_MAIN_COMMIT_METADATA_PROJECTION = (
    '{"sha":.sha,"verified":.commit.verification.verified}'
)


def _observe_accepted_main_commit_metadata(main: str) -> bytes:
    """Project maintained commit facts before bounded provider capture."""

    expected = authority._require_oid(main, "protected main")
    result = transport._run_bootstrap_gh([
        "api", "--hostname", "github.com",
        f"repos/SecPal/.github/commits/{expected}",
        "--jq", _ACCEPTED_MAIN_COMMIT_METADATA_PROJECTION,
    ])
    if result.returncode != 0:
        raise authority.LifecycleAuthorityError(
            "accepted-main commit metadata acquisition failed"
        )
    return result.stdout


def _normalize_accepted_main_commit_metadata(
    main: str, observed: bytes,
) -> dict[str, Any]:
    """Normalize projected provider bytes without granting them authority."""

    expected = authority._require_oid(main, "protected main")
    metadata = authority._require_closed(
        authority.loads_closed_json(observed),
        {"sha", "verified"}, "accepted-main commit metadata",
    )
    if (
        authority._require_oid(metadata["sha"], "accepted-main commit") != expected
        or type(metadata["verified"]) is not bool
        or metadata["verified"] is not True
    ):
        raise authority.LifecycleAuthorityError(
            "accepted-main commit metadata is not verified"
        )
    return {"sha": expected, "verified": True}


def _accepted_main_commit_metadata(main: str) -> dict[str, Any]:
    """Observe then admit only the maintained accepted-main commit facts."""

    expected = authority._require_oid(main, "protected main")
    return _normalize_accepted_main_commit_metadata(
        expected, _observe_accepted_main_commit_metadata(expected)
    )


def _chronology_page_document(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        document = authority.loads_closed_json(raw)
        if not isinstance(document, dict) or set(document) != {"data"}:
            raise authority.LifecycleAuthorityError("chronology provider projection is malformed")
        data = document["data"]
        repository = data["repository"]
        pull_request = repository["pullRequest"]
        connection = pull_request["timelineItems"]
        page_info = connection["pageInfo"]
        if (
            not isinstance(data, dict) or set(data) != {"repository"}
            or not isinstance(repository, dict)
            or set(repository) != {"nameWithOwner", "pullRequest"}
            or not isinstance(pull_request, dict)
            or set(pull_request) != {"number", "timelineItems"}
            or not isinstance(connection, dict)
            or set(connection) != {"pageInfo", "nodes"}
            or not isinstance(page_info, dict)
            or set(page_info) != {"hasNextPage", "endCursor"}
            or not isinstance(connection["nodes"], list)
            or len(connection["nodes"]) > _CHRONOLOGY_PAGE_SIZE
            or type(page_info["hasNextPage"]) is not bool
            or (
                page_info["endCursor"] is not None
                and (
                    not isinstance(page_info["endCursor"], str)
                    or not page_info["endCursor"]
                    or page_info["endCursor"] != page_info["endCursor"].strip()
                )
            )
            or (page_info["hasNextPage"] and page_info["endCursor"] is None)
        ):
            raise authority.LifecycleAuthorityError("chronology provider projection is malformed")
    except authority.LifecycleAuthorityError:
        raise
    except (
        UnicodeDecodeError,
        KeyError,
        TypeError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise authority.LifecycleAuthorityError(
            "chronology provider projection is malformed"
        ) from exc
    return repository, connection


def _observe_chronology(repository: str, pull_request: int) -> ChronologyObservation:
    """Observe only the maintained Ready/Draft projection through bounded pages."""

    repository = authority._require_repository(repository)
    pull_request = authority._require_positive_int(pull_request, "loss pull request")
    owner, name = repository.split("/", 1)
    pages: list[bytes] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    for page_number in range(_CHRONOLOGY_MAXIMUM_PAGES):
        arguments = [
            "api", "--hostname", "github.com", "graphql",
            "-f", f"query={_CHRONOLOGY_QUERY}",
            "-f", f"owner={owner}", "-f", f"name={name}",
            "-F", f"number={pull_request}",
        ]
        if cursor is not None:
            arguments.extend(["-f", f"cursor={cursor}"])
        try:
            result = transport._run_bootstrap_gh(arguments)
        except transport.BootstrapSourceAdmissionError as exc:
            raise authority.LifecycleAuthorityError(
                f"chronology acquisition page {page_number + 1} transport failed"
            ) from exc
        if result.returncode != 0:
            raise authority.LifecycleAuthorityError(
                f"chronology acquisition page {page_number + 1} provider failed"
            )
        raw = bytes(result.stdout)
        _repository, connection = _chronology_page_document(raw)
        pages.append(raw)
        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            return ChronologyObservation(tuple(pages))
        cursor = page_info["endCursor"]
        if cursor in seen_cursors:
            raise authority.LifecycleAuthorityError(
                "chronology provider pagination is ambiguous"
            )
        seen_cursors.add(cursor)
    raise authority.LifecycleAuthorityError(
        "loss source chronology exceeds the maintained bound"
    )


def _normalize_chronology(
    observation: ChronologyObservation, repository: str, pull_request: int,
) -> tuple[ChronologyEvent, ...]:
    """Purely normalize the closed provider projection into chronology facts."""

    if (
        not isinstance(observation, ChronologyObservation)
        or not observation.pages
        or len(observation.pages) > _CHRONOLOGY_MAXIMUM_PAGES
    ):
        raise authority.LifecycleAuthorityError("chronology provider projection is malformed")
    repository = authority._require_repository(repository)
    pull_request = authority._require_positive_int(pull_request, "loss pull request")
    names = {
        "ReadyForReviewEvent": "ready_for_review",
        "ConvertToDraftEvent": "convert_to_draft",
    }
    events: list[ChronologyEvent] = []
    identities: set[str] = set()
    for page_number, raw in enumerate(observation.pages):
        projected_repository, connection = _chronology_page_document(raw)
        if (
            projected_repository["nameWithOwner"] != repository
            or projected_repository["pullRequest"]["number"] != pull_request
            or connection["pageInfo"]["hasNextPage"]
            != (page_number + 1 < len(observation.pages))
        ):
            raise authority.LifecycleAuthorityError(
                "chronology provider identity or pagination changed"
            )
        for node in connection["nodes"]:
            if not isinstance(node, dict) or set(node) != {"__typename", "id", "createdAt"}:
                raise authority.LifecycleAuthorityError("chronology provider event is malformed")
            typename = node["__typename"]
            identity = node["id"]
            occurred_at = node["createdAt"]
            if (
                typename not in names
                or not isinstance(identity, str)
                or not identity
                or identity != identity.strip()
                or identity in identities
                or not isinstance(occurred_at, str)
            ):
                raise authority.LifecycleAuthorityError(
                    "chronology provider event identity or kind is ambiguous"
                )
            authority._parse_adoption_timestamp(occurred_at, "chronology event time")
            identities.add(identity)
            events.append(ChronologyEvent(identity, names[typename], occurred_at))
    if len(events) >= _CHRONOLOGY_MAXIMUM_EVENTS:
        raise authority.LifecycleAuthorityError(
            "loss source chronology exceeds the maintained bound"
        )
    timestamps = [
        authority._parse_adoption_timestamp(item.occurred_at, "chronology event time")
        for item in events
    ]
    if timestamps != sorted(timestamps):
        raise authority.LifecycleAuthorityError("chronology provider ordering is ambiguous")
    return tuple(events)


def _accepted_policy(repository: str, issue: int) -> tuple[str, dict[str, Any], Any, Any]:
    if repository != "SecPal/.github":
        raise authority.LifecycleAuthorityError("loss admission repository is not maintained")
    authority._require_positive_int(issue, "loss issue")
    branch = _gh_json("repos/SecPal/.github/branches/main")
    main = authority._require_oid(branch["commit"]["sha"], "protected main")
    commit = _accepted_main_commit_metadata(main)
    if branch["protected"] is not True or commit["sha"] != main or commit["verified"] is not True:
        raise authority.LifecycleAuthorityError("loss policy requires authenticated protected main")
    if (
        transport._git_text(ROOT, ["rev-parse", "HEAD"]).strip() != main
        or transport._git_text(ROOT, ["status", "--porcelain=v2", "--untracked-files=all"])
    ):
        raise authority.LifecycleAuthorityError("candidate-local loss self-admission is forbidden")
    trusted_paths = [
        *sorted((ROOT / "scripts/secpal_pr_review").glob("*.py")),
        ROOT / "scripts/secpal-pr-review.py", ROOT / "scripts/secpal-pr-review-actions.py",
        ROOT / ".agents/skills/secpal-pr-review/references/repositories.json",
        ROOT / ".agents/skills/secpal-pr-review/references/repositories.schema.json",
        ROOT / POLICY_PATH,
    ]
    for path in trusted_paths:
        relative = str(path.relative_to(ROOT))
        actual = transport._git_text(ROOT, ["hash-object", "--no-filters", relative]).strip()
        expected = transport._git_text(ROOT, ["rev-parse", f"{main}:{relative}"]).strip()
        if actual != expected:
            raise authority.LifecycleAuthorityError("accepted-main loss code or policy bytes changed")
    policy = authority.loads_closed_json((ROOT / POLICY_PATH).read_bytes())
    if set(policy) != {"schema_version", "admissions"} or policy["schema_version"] != "1.0" or not isinstance(policy["admissions"], list):
        raise authority.LifecycleAuthorityError("loss policy is malformed")
    if any(not isinstance(item, dict) for item in policy["admissions"]):
        raise authority.LifecycleAuthorityError("loss policy records are malformed")
    records = [item for item in policy["admissions"] if item.get("repository") == repository and item.get("delivery_issue") == issue]
    if len(records) != 1:
        raise authority.LifecycleAuthorityError("no unique accepted-main evidence-loss proof")
    record = copy.deepcopy(authority._require_closed(records[0], RECORD_FIELDS, "loss proof policy"))
    authority._require_positive_int(record["pull_request"], "loss policy pull request")
    for field in ("head_sha", "tree_sha", "parent_sha"):
        authority._require_oid(record[field], field)
    for field in ("historical_validation_receipt_digest", "feedback_digest"):
        authority._require_digest(record[field], field)
    authority._require_identity(record["source_signer_identity"], "loss source signer")
    authority._normalize_observed_pre_enrollment_history(
        record["observed_pre_enrollment_history"], expected_head=record["head_sha"],
        intended_state=_intended_state(), review_budget_consumption_admitted=True,
    )
    _decisions(record["technical_decisions"])
    if (
        record["historical_package_status"] != "UNAVAILABLE"
        or record["historical_final_attestation_digest"] is not None
        or record["historical_bytes_reconstructed"] is not False
    ):
        raise authority.LifecycleAuthorityError("loss proof cannot reconstruct historical artifacts")
    helper = transport._load_actions_helper()
    entry = helper.select_repository(helper.load_registry(), repository)
    trust = authority._load_lifecycle_trust_policy(repository)
    return main, record, entry, trust


def _provider_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise authority.LifecycleAuthorityError(f"{label} provider representation is malformed")
    return value


def _provider_value(value: Any, path: tuple[str, ...], label: str) -> Any:
    current = value
    try:
        for field in path:
            current = _provider_mapping(current, label)[field]
    except KeyError as exc:
        raise authority.LifecycleAuthorityError(f"{label} provider representation is malformed") from exc
    return current


def _normalize_provider_representations(
    target: Any,
    issue_state: Any,
    commits: Any,
    chronology_before: Any,
    chronology_after: Any,
    source_commit: Any,
) -> NormalizedProviderFacts:
    """Purely convert bounded provider representations into canonical facts."""

    target = _provider_mapping(target, "pull request")
    issue_state = _provider_mapping(issue_state, "issue")
    source_commit = _provider_mapping(source_commit, "source commit")
    if not isinstance(commits, list) or len(commits) > 100:
        raise authority.LifecycleAuthorityError("commit provider representation is malformed")
    try:
        normalized_commits = tuple(
            CommitFacts(
                head_sha=_provider_value(item, ("sha",), "commit"),
                parent_shas=tuple(
                    _provider_value(parent, ("sha",), "commit parent")
                    for parent in _provider_value(item, ("parents",), "commit")
                ),
                committed_at=_provider_value(item, ("commit", "committer", "date"), "commit"),
            )
            for item in commits
        )
        timeline_events = _normalize_chronology(
            chronology_before,
            _provider_value(target, ("base", "repo", "full_name"), "pull request"),
            _provider_value(target, ("number",), "pull request"),
        )
        if timeline_events != _normalize_chronology(
            chronology_after,
            _provider_value(target, ("base", "repo", "full_name"), "pull request"),
            _provider_value(target, ("number",), "pull request"),
        ):
            raise authority.LifecycleAuthorityError(
                "loss source chronology changed during acquisition"
            )
        merged_at = _provider_value(target, ("merged_at",), "pull request")
        if merged_at is not None and not isinstance(merged_at, str):
            raise authority.LifecycleAuthorityError("pull request provider representation is malformed")
        return NormalizedProviderFacts(
            pull_request=PullRequestFacts(
                number=_provider_value(target, ("number",), "pull request"),
                state=str(_provider_value(target, ("state",), "pull request")).upper(),
                draft=_provider_value(target, ("draft",), "pull request"),
                merged=merged_at is not None,
                head_sha=_provider_value(target, ("head", "sha"), "pull request"),
                head_repository=_provider_value(target, ("head", "repo", "full_name"), "pull request"),
                base_repository=_provider_value(target, ("base", "repo", "full_name"), "pull request"),
                base_ref=_provider_value(target, ("base", "ref"), "pull request"),
                created_at=_provider_value(target, ("created_at",), "pull request"),
            ),
            issue=IssueFacts(
                number=_provider_value(issue_state, ("number",), "issue"),
                state=str(_provider_value(issue_state, ("state",), "issue")).upper(),
            ),
            commits=normalized_commits,
            timeline_events=timeline_events,
            source_commit=SourceCommitFacts(
                head_sha=_provider_value(source_commit, ("sha",), "source commit"),
                tree_sha=_provider_value(source_commit, ("commit", "tree", "sha"), "source commit"),
                parent_shas=tuple(
                    _provider_value(parent, ("sha",), "source commit parent")
                    for parent in _provider_value(source_commit, ("parents",), "source commit")
                ),
                signature_verified=_provider_value(
                    source_commit, ("commit", "verification", "verified"), "source commit"
                ),
            ),
        )
    except authority.LifecycleAuthorityError:
        raise
    except (TypeError, ValueError) as exc:
        raise authority.LifecycleAuthorityError("provider representation is malformed") from exc


def _observe(record: Mapping[str, Any], entry: Any, trust: Any) -> tuple[SourceCommitFacts, Any]:
    repository = record["repository"]
    issue = record["delivery_issue"]
    pr = record["pull_request"]
    publication.require_unenrolled_delivery(repository, issue)
    target = _gh_json(f"repos/{repository}/pulls/{pr}")
    issue_state = _gh_json(f"repos/{repository}/issues/{issue}")
    commits = _gh_json(f"repos/{repository}/pulls/{pr}/commits?per_page=100")
    try:
        chronology_before = _observe_chronology(repository, pr)
    except authority.LifecycleAuthorityError as exc:
        raise authority.LifecycleAuthorityError(
            f"pre-feedback chronology acquisition failed: {exc}"
        ) from exc
    helper = transport._load_actions_helper()
    reviewed = helper.FastPathGateway(ROOT, entry).capture_stable_feedback(repository, pr)
    try:
        chronology_after = _observe_chronology(repository, pr)
    except authority.LifecycleAuthorityError as exc:
        raise authority.LifecycleAuthorityError(
            f"post-feedback chronology acquisition failed: {exc}"
        ) from exc
    source_commit = _gh_json(f"repos/{repository}/commits/{record['head_sha']}")
    normalized = _normalize_provider_representations(
        target, issue_state, commits, chronology_before, chronology_after, source_commit,
    )
    return _admit_observation(record, normalized, reviewed)


def _admit_observation(
    record: Mapping[str, Any], provider: NormalizedProviderFacts, reviewed: Any,
) -> tuple[SourceCommitFacts, Any]:
    if type(provider) is not NormalizedProviderFacts:
        raise authority.LifecycleAuthorityError("loss admission requires normalized provider facts")
    repository = record["repository"]
    issue = record["delivery_issue"]
    pr = record["pull_request"]
    target = provider.pull_request
    issue_state = provider.issue
    commits = provider.commits
    timeline = provider.timeline_events
    source_commit = provider.source_commit
    if (
        target.number != pr or target.state != "OPEN" or target.draft is not True
        or target.merged or target.head_sha != record["head_sha"]
        or target.head_repository != repository
        or target.base_repository != repository or target.base_ref != "main"
        or issue_state.number != issue or issue_state.state != "OPEN"
    ):
        raise authority.LifecycleAuthorityError("loss source is not the exact open unenrolled Draft")
    if not commits or len(commits) >= 100:
        raise authority.LifecycleAuthorityError("loss source history is incomplete")
    observations = record["observed_pre_enrollment_history"]
    if [item.head_sha for item in commits] != [item["head_sha"] for item in observations]:
        raise authority.LifecycleAuthorityError("loss source observed history changed")
    for index, item in enumerate(commits):
        if len(item.parent_shas) != 1 or (index and item.parent_shas[0] != commits[index - 1].head_sha):
            raise authority.LifecycleAuthorityError("loss source history parent topology changed")
        timestamp = target.created_at if index == 0 else item.committed_at
        if observations[index]["observed_at"] != timestamp:
            raise authority.LifecycleAuthorityError("loss source history timestamp changed")
    if any(
        event.kind in {"ready_for_review", "convert_to_draft"} for event in timeline
    ):
        raise authority.LifecycleAuthorityError("loss source has Ready history")
    if reviewed.head_sha != record["head_sha"] or reviewed.pr_state != "OPEN" or reviewed.feedback_digest != record["feedback_digest"]:
        raise authority.LifecycleAuthorityError("loss source stable feedback changed")
    sources = fast_path._classified_feedback_sources(reviewed, include_resolved=True)
    decisions = _decisions(record["technical_decisions"])
    expected = {f"{kind}:{identity}": facts[0] for (kind, identity), facts in sources.items()}
    if {item["source_id"]: item["source_digest"] for item in decisions} != expected:
        raise authority.LifecycleAuthorityError("loss source technical decisions are not source-complete")
    if (
        source_commit.head_sha != record["head_sha"]
        or source_commit.tree_sha != record["tree_sha"]
        or list(source_commit.parent_shas) != [record["parent_sha"]]
        or source_commit.signature_verified is not True
    ):
        raise authority.LifecycleAuthorityError("loss source immutable identity or signature changed")
    return source_commit, reviewed


def _source_signature(root: Path, record: Mapping[str, Any], trust: Any) -> str:
    allowed = transport._allowed_signers(root, trust, record["source_signer_identity"])
    result = transport._run_bootstrap_git(root, [
        "-c", f"gpg.ssh.allowedSignersFile={allowed}", "verify-commit", "--raw", record["head_sha"],
    ])
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    principals = re.findall(r'(?m)^Good "git" signature for ([^\r\n]+) with ', output)
    if result.returncode != 0 or principals != [record["source_signer_identity"]]:
        raise authority.LifecycleAuthorityError("loss source signer is not authenticated")
    evidence = {
        "oid": record["head_sha"], "source": "USER", "signer_identity": record["source_signer_identity"],
        "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
        "github_verification": {"verified": True, "reason": "valid"},
    }
    return authority.digest_json(fast_path.verify_commit_signatures(
        [evidence], authority._load_delivery_signature_policy(record["repository"]),
    )[0])


def _verify_source_bytes(root: Path, tree: str, *, expected_listing: str | None = None) -> str:
    listing = (
        transport._git_text(root, ["ls-tree", "-rz", "--full-tree", tree])
        if expected_listing is None else expected_listing
    )
    for entry in listing.rstrip("\0").split("\0"):
        metadata, separator, name = entry.partition("\t")
        fields = metadata.split()
        path = root / name
        if (
            not separator or len(fields) != 3 or fields[1] != "blob"
            or fields[0] not in {"100644", "100755"} or not name
            or Path(name).is_absolute() or ".." in Path(name).parts
        ):
            raise authority.LifecycleAuthorityError("loss source requires regular immutable source bytes")
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise authority.LifecycleAuthorityError("loss source bytes contain a symlink")
        try:
            mode = path.stat().st_mode
            matches = (
                stat.S_ISREG(mode) and bool(mode & stat.S_IXUSR) == (fields[0] == "100755")
                and transport._git_text(root, ["hash-object", "--no-filters", "--", name]).strip() == fields[2]
            )
        except OSError as exc:
            raise authority.LifecycleAuthorityError("loss source bytes are unavailable") from exc
        if not matches:
            raise authority.LifecycleAuthorityError("validation mutated immutable source bytes")
    return listing


def _current_validation_harness_paths(main: str, helper: Any, entry: Any) -> tuple[str, ...]:
    return (_admit_current_safety_path(CURRENT_SAFETY_PATH),)


def _admit_current_safety_path(relative: str) -> str:
    if relative != "tests/pre-enrollment-current-safety.py":
        raise authority.LifecycleAuthorityError("current safety path is not maintained")
    return relative


def _current_safety_profile(main: str) -> dict[str, Any]:
    path = _admit_current_safety_path(CURRENT_SAFETY_PATH)
    mode, blob, size = _current_harness_blob(main, path)
    commands = [{
        "argv": ["python3", path], "working_directory": ".",
        "purpose": "Validate pre-enrollment evidence-loss current safety",
    }]
    return {
        "schema_version": "1.0",
        "policy": "PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_CURRENT_SAFETY",
        "harness": [{"path": path, "mode": mode, "blob_oid": blob, "size": size}],
        "validation_command_set": commands,
        "validation_command_set_digest": authority.digest_json(commands),
        "timeout_seconds": 120,
        "required_invariants": list(CURRENT_SAFETY_INVARIANTS),
        "validation_results": [{"command_digest": authority.digest_json(commands[0]),
                                "exit_status": 0, "successful": True}],
    }


def _admit_current_harness_requested_path(relative: str) -> str:
    """Admit one literal repository-relative harness path without observation."""

    if not isinstance(relative, str):
        raise authority.LifecycleAuthorityError("current validation harness path is unsafe")
    path = Path(relative)
    if (
        not relative or path.is_absolute() or ".." in path.parts
        or path.as_posix() != relative
    ):
        raise authority.LifecycleAuthorityError("current validation harness path is unsafe")
    return relative


def _observe_current_harness_blob(
    main: str, relative: str,
) -> CurrentHarnessBlobObservation:
    """Observe one literal tree entry without deciding harness conformance."""

    record = transport._git(
        ROOT,
        ["ls-tree", "-lz", "--full-tree", main, "--", f":(literal){relative}"],
    ).stdout
    return CurrentHarnessBlobObservation(
        commit_oid=main,
        requested_path=relative,
        tree_entry=bytes(record),
    )


def _normalize_current_harness_blob_observation(
    observation: CurrentHarnessBlobObservation,
) -> CurrentHarnessBlobFacts:
    """Normalize one Git tree representation without external observation."""

    if not isinstance(observation, CurrentHarnessBlobObservation):
        raise authority.LifecycleAuthorityError("current validation harness listing is malformed")
    record = observation.tree_entry
    if not record.endswith(b"\0") or record.count(b"\0") != 1:
        raise authority.LifecycleAuthorityError("current validation harness file is unavailable")
    try:
        metadata, separator, observed_path = record[:-1].decode("utf-8", "strict").partition("\t")
    except UnicodeDecodeError as exc:
        raise authority.LifecycleAuthorityError("current validation harness listing is malformed") from exc
    fields = metadata.split()
    if separator != "\t" or len(fields) != 4:
        raise authority.LifecycleAuthorityError("current validation harness listing is malformed")
    try:
        blob_oid = authority._require_oid(fields[2], "current validation harness blob")
    except authority.LifecycleAuthorityError as exc:
        raise authority.LifecycleAuthorityError("current validation harness blob is invalid") from exc
    size_text = fields[3]
    if size_text != "-" and not size_text.isdecimal():
        raise authority.LifecycleAuthorityError("current validation harness size is invalid")
    return CurrentHarnessBlobFacts(
        repository_path=observed_path,
        mode=fields[0],
        object_type=fields[1],
        object_oid=blob_oid,
        size=None if size_text == "-" else int(size_text),
    )


def _admit_current_harness_blob(
    observation: CurrentHarnessBlobObservation,
    facts: CurrentHarnessBlobFacts,
) -> CurrentHarnessBlobBinding:
    """Admit canonical tree facts as one exact regular protected-main blob."""

    if (
        not isinstance(observation, CurrentHarnessBlobObservation)
        or not isinstance(facts, CurrentHarnessBlobFacts)
    ):
        raise authority.LifecycleAuthorityError("current validation harness listing is malformed")
    commit_oid = authority._require_oid(
        observation.commit_oid, "current validation harness commit",
    )
    requested_path = _admit_current_harness_requested_path(observation.requested_path)
    if (
        facts.repository_path != requested_path
        or facts.mode not in {"100644", "100755"}
        or facts.object_type != "blob"
    ):
        raise authority.LifecycleAuthorityError("current validation harness mode is invalid")
    if facts.size is None:
        raise authority.LifecycleAuthorityError("current validation harness size is invalid")
    return CurrentHarnessBlobBinding(
        commit_oid=commit_oid,
        repository_path=requested_path,
        mode=facts.mode,
        blob_oid=facts.object_oid,
        size=facts.size,
    )


def _current_harness_blob(main: str, relative: str) -> tuple[str, str, int]:
    """Assemble the explicit observation, normalization, and admission stages."""

    relative = _admit_current_harness_requested_path(relative)
    observation = _observe_current_harness_blob(main, relative)
    facts = _normalize_current_harness_blob_observation(observation)
    binding = _admit_current_harness_blob(observation, facts)
    return binding.mode, binding.blob_oid, binding.size


def _verify_current_harness_file(
    destination_root: Path, relative: str, mode: str, blob_oid: str, size: int,
) -> None:
    destination = destination_root / relative
    for parent in destination.parents:
        if parent == destination_root:
            break
        if parent.is_symlink():
            raise authority.LifecycleAuthorityError("current validation harness path is unsafe")
    try:
        metadata = destination.lstat()
    except OSError as exc:
        raise authority.LifecycleAuthorityError("current validation harness file is unavailable") from exc
    expected_permissions = 0o755 if mode == "100755" else 0o644
    if (
        not stat.S_ISREG(metadata.st_mode) or metadata.st_size != size
        or stat.S_IMODE(metadata.st_mode) != expected_permissions
    ):
        raise authority.LifecycleAuthorityError("current validation harness mode or size changed")
    actual = transport._git_text(
        ROOT, ["hash-object", "--no-filters", "--", str(destination)],
    ).strip()
    if actual != blob_oid:
        raise authority.LifecycleAuthorityError("current validation harness bytes are not accepted main")


def _create_harness_parent(destination_root: Path, relative: Path) -> Path:
    """Create only real directories below the private disposable root."""

    try:
        root_metadata = destination_root.lstat()
    except OSError as exc:
        raise authority.LifecycleAuthorityError("current validation harness root is unavailable") from exc
    if not stat.S_ISDIR(root_metadata.st_mode) or destination_root.is_symlink():
        raise authority.LifecycleAuthorityError("current validation harness root is unsafe")
    parent = destination_root
    for part in relative.parent.parts:
        parent /= part
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            try:
                parent.mkdir(mode=0o755)
                metadata = parent.lstat()
            except OSError as exc:
                raise authority.LifecycleAuthorityError(
                    "current validation harness path is unavailable"
                ) from exc
        except OSError as exc:
            raise authority.LifecycleAuthorityError(
                "current validation harness path is unavailable"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
            raise authority.LifecycleAuthorityError("current validation harness path is unsafe")
    return parent


def _copy_current_harness_file(
    main: str,
    relative: str,
    destination_root: Path,
    *,
    registered_paths: frozenset[str],
) -> tuple[str, str, int]:
    if relative not in registered_paths:
        raise authority.LifecycleAuthorityError("current validation harness path is not registered")
    mode, blob_oid, size = _current_harness_blob(main, relative)
    path = Path(relative)
    destination = destination_root / path
    destination_parent = _create_harness_parent(destination_root, path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination_parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            try:
                result = subprocess.run(
                    [
                        transport._resolve_bootstrap_executable("git"),
                        "-C", str(ROOT.resolve(strict=True)),
                        "cat-file", "blob", blob_oid,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    env=transport._bootstrap_command_environment("git", ROOT),
                    timeout=transport._BOOTSTRAP_COMMAND_TIMEOUT_SECONDS,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise authority.LifecycleAuthorityError(
                    "current validation harness blob is unavailable"
                ) from exc
            if result.returncode != 0:
                raise authority.LifecycleAuthorityError(
                    "current validation harness blob is unavailable"
                )
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o755 if mode == "100755" else 0o644)
        if temporary.stat().st_size != size:
            raise authority.LifecycleAuthorityError(
                "current validation harness blob size changed"
            )
        actual = transport._git_text(
            ROOT, ["hash-object", "--no-filters", "--", str(temporary)],
        ).strip()
        if actual != blob_oid:
            raise authority.LifecycleAuthorityError(
                "current validation harness blob bytes changed"
            )
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            # Atomic replacement consumes the temporary path on success.
            pass
    _verify_current_harness_file(destination_root, relative, mode, blob_oid, size)
    return mode, blob_oid, size


@contextmanager
def _current_policy_validation_root(
    main: str,
    *,
    source_root: Path,
    helper: Any,
    entry: Any,
) -> Iterator[Path]:
    """Build a disposable target tree with only accepted-main harness bytes overlaid."""

    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise authority.LifecycleAuthorityError("immutable validation source root is unavailable")
    harness_paths = _current_validation_harness_paths(main, helper, entry)
    registered_paths = frozenset(harness_paths)
    if len(registered_paths) != len(harness_paths):
        raise authority.LifecycleAuthorityError("current validation harness paths are ambiguous")
    if transport._git(ROOT, ["cat-file", "-t", main]).stdout != b"commit\n":
        raise authority.LifecycleAuthorityError("current validation harness commit is invalid")
    tree = transport._git_text(source_root, ["rev-parse", "HEAD^{tree}"]).strip()
    listing = _verify_source_bytes(source_root, tree)
    candidate_listing = "\0".join(
        item for item in listing.rstrip("\0").split("\0")
        if not item.partition("\t")[2].startswith("tests/")
    ) + "\0"
    with tempfile.TemporaryDirectory(prefix="secpal-current-policy-validation-") as directory:
        execution_root = Path(directory) / "source"
        bindings: dict[str, tuple[str, str, int]] = {}
        try:
            shutil.copytree(source_root, execution_root, symlinks=True,
                            ignore=shutil.ignore_patterns(".git"))
            tests_root = execution_root / "tests"
            if tests_root.exists():
                shutil.rmtree(tests_root)
            for relative in harness_paths:
                _admit_current_safety_path(relative)
                bindings[relative] = _copy_current_harness_file(
                    main, relative, execution_root, registered_paths=registered_paths,
                )
        except OSError as exc:
            raise authority.LifecycleAuthorityError("current validation harness preparation failed") from exc
        _verify_current_safety_root(execution_root, tree, candidate_listing, bindings)
        try:
            yield execution_root
        finally:
            _verify_current_safety_root(execution_root, tree, candidate_listing, bindings)
            _verify_source_bytes(source_root, tree, expected_listing=listing)


def _verify_current_safety_root(
    root: Path, tree: str, candidate_listing: str,
    bindings: Mapping[str, tuple[str, str, int]],
) -> None:
    expected = {item.partition("\t")[2]
                for item in candidate_listing.rstrip("\0").split("\0")}
    if expected.intersection(bindings):
        raise authority.LifecycleAuthorityError("candidate and harness ownership overlap")
    expected.update(bindings)
    expected_directories = {
        parent.as_posix() for relative in expected for parent in Path(relative).parents
        if parent != Path(".")
    }
    observed = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise authority.LifecycleAuthorityError("current safety source contains symlink")
        if path.is_dir():
            if path.relative_to(root).as_posix() not in expected_directories:
                raise authority.LifecycleAuthorityError("current safety source contains undeclared directories")
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts:
            raise authority.LifecycleAuthorityError("current safety source contains bytecode")
        observed.add(relative)
    if observed != expected:
        raise authority.LifecycleAuthorityError("current safety source contains undeclared files")
    _verify_source_bytes(root, tree, expected_listing=candidate_listing)
    for relative, binding in bindings.items():
        _verify_current_harness_file(root, relative, *binding)


def _run_current_safety(main: str, root: Path, profile: Mapping[str, Any]) -> None:
    if dict(profile) != _current_safety_profile(main):
        raise authority.LifecycleAuthorityError("current safety profile or command drift")
    with tempfile.TemporaryDirectory(prefix="secpal-current-safety-home-") as home:
        environment = transport._closed_validation_environment(
            authority._load_trusted_command_helper(), Path(home))
        command = profile["validation_command_set"][0]
        result = transport._run_isolated_python(
            transport._isolated_python_command(
                transport._ISOLATED_SOURCE_LAUNCHER,
                "ENTRYPOINT", str(root), command["argv"][1], "main",
            ), cwd=root, timeout=profile["timeout_seconds"], env=environment,
        )
    observed = [{"command_digest": authority.digest_json(command),
                 "exit_status": result.returncode, "successful": result.returncode == 0}]
    if observed != profile["validation_results"]:
        try:
            failed = authority.loads_closed_json(result.stdout)
            if (not isinstance(failed, list) or not failed
                or any(not isinstance(item, str) or item not in CURRENT_SAFETY_INVARIANTS for item in failed)
                or failed != sorted(set(failed))):
                raise ValueError("invalid failure inventory")
        except (ValueError, authority.LifecycleAuthorityError) as exc:
            raise authority.LifecycleAuthorityError("current safety failure report invalid") from exc
        raise authority.LifecycleAuthorityError("current safety assertions failed: " + ", ".join(failed))
    if authority.loads_closed_json(result.stdout) != profile["required_invariants"]:
        raise authority.LifecycleAuthorityError("current safety invariant coverage incomplete")


def _acquire(repository: str, issue: int, *, execute_validation: bool) -> dict[str, Any]:
    main, record, entry, trust = _accepted_policy(repository, issue)
    _, before = _observe(record, entry, trust)
    helper = transport._load_actions_helper()
    binding = helper._fast_registry_binding(entry)
    profile = _current_safety_profile(main)
    binding = {"repository_policy": binding, "current_safety_profile": profile}
    with tempfile.TemporaryDirectory(prefix="secpal-pre-enrollment-safety-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        transport._git(root, ["init", "--quiet"])
        transport._git(root, ["remote", "add", "origin", trust.publication_remote_url])
        transport._git(root, ["fetch", "--quiet", "--no-tags", "--depth=64", "origin", record["head_sha"]])
        if transport._git_text(root, ["rev-parse", "FETCH_HEAD"]).strip() != record["head_sha"]:
            raise authority.LifecycleAuthorityError("loss source fetch changed identity")
        transport._git(root, ["checkout", "--quiet", "--detach", record["head_sha"]])
        if transport._git_text(root, ["rev-parse", "HEAD^{tree}"]).strip() != record["tree_sha"]:
            raise authority.LifecycleAuthorityError("loss source tree changed")
        if transport._git_text(root, ["rev-list", "--parents", "-n", "1", "HEAD"]).split() != [record["head_sha"], record["parent_sha"]]:
            raise authority.LifecycleAuthorityError("loss source sole parent changed")
        signature_digest = _source_signature(root, record, trust)
        if transport._exact_trailer(root, record["head_sha"]) != record["historical_validation_receipt_digest"]:
            raise authority.LifecycleAuthorityError("loss source historical signed receipt changed")
        source_listing = _verify_source_bytes(root, record["tree_sha"])
        if execute_validation:
            with _current_policy_validation_root(
                main, source_root=root, helper=helper, entry=entry,
            ) as validation_root:
                _run_current_safety(main, validation_root, profile)
        _verify_source_bytes(root, record["tree_sha"], expected_listing=source_listing)
        if (
            transport._git_text(root, ["rev-parse", "HEAD"]).strip() != record["head_sha"]
            or transport._git_text(root, ["diff", "--name-only", "HEAD"])
        ):
            raise authority.LifecycleAuthorityError("validation mutated the immutable source")
    _, after = _observe(record, entry, trust)
    if before.state_digest != after.state_digest:
        raise authority.LifecycleAuthorityError("current safety feedback is not stable")
    if _accepted_policy(repository, issue)[0] != main:
        raise authority.LifecycleAuthorityError("accepted-main authority changed during admission")
    return _assemble_source_facts(main, record, binding, profile["validation_command_set"], after, signature_digest)


def _assemble_source_facts(
    main: str, record: Mapping[str, Any], binding: Any, commands: Any,
    reviewed: Any, signature_digest: str,
) -> dict[str, Any]:
    current_safety_identity = authority.digest_json({
        "domain": "secpal.pre-enrollment-current-safety/v1",
        "repository": record["repository"], "head_sha": record["head_sha"],
        "tree_sha": record["tree_sha"], "validation_policy": binding,
        "commands": commands,
        "reviewed_state_digest": reviewed.state_digest, "successful_result": True,
    })
    return {
        **{field: copy.deepcopy(record[field]) for field in RECORD_FIELDS - {"feedback_digest", "technical_decisions"}},
        "pull_request_state": "OPEN", "draft": True,
        "commit_signature_evidence_digest": signature_digest,
        "loss_proof_policy_digest": authority.digest_json(record),
        "accepted_main_sha": main,
        "intended_state": _intended_state(),
        "current_safety": {
            "receipt_digest": current_safety_identity, "validated_tree_sha": record["tree_sha"],
            "validation_policy_digest": authority.digest_json(binding),
            "command_set_digest": authority.digest_json(commands),
            "feedback_digest": reviewed.feedback_digest,
            "technical_decisions": copy.deepcopy(record["technical_decisions"]),
            "successful_result": True,
        },
    }


def _reauthenticate(doc: Mapping[str, Any]) -> None:
    current = _acquire(doc["repository"], doc["delivery_issue"], execute_validation=False)
    if any(doc[field] != expected for field, expected in current.items()):
        raise authority.LifecycleAuthorityError("loss admission is stale or cross-context")


def issue(repository: str, delivery_issue: int, *, historical_package: Any = _UNSUPPLIED) -> dict[str, Any]:
    if historical_package is not _UNSUPPLIED:
        raise authority.LifecycleAuthorityError("supplied historical evidence cannot downgrade to loss admission")
    acquired = _acquire(repository, delivery_issue, execute_validation=True)
    identity, signer = execution._production_legacy_adoption_signer(repository)
    fields = {
        "schema_version": "1.0", "kind": KIND, "domain": DOMAIN, **acquired,
        "admission_id": f"pre-enrollment-validation-loss:{authority.digest_json(acquired)}",
        "adoption_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bounded_uses": 1, "signer_identity": identity,
    }
    signature = signer(authority.canonical_json_bytes(fields), DOMAIN)
    signed = {**fields, "signature": signature}
    return _verify_document({**signed, "admission_digest": authority.digest_json(signed)})
