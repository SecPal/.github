# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One protected-main, migration-signed pre-enrollment source admission."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import tempfile
from typing import Any, Iterator, Mapping

from . import bootstrap_source_admission as transport
from . import exact_source_safety
from . import fast_path
from . import lifecycle_authority as authority
from . import lifecycle_execution as execution
from . import lifecycle_publication as publication


KIND = "SECPAL_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_ADMISSION"
DOMAIN = "secpal.pre-enrollment-validation-evidence-loss-admission/v1"
ANCESTOR_SCHEMA_VERSION = "1.1"
ANCESTOR_DOMAIN = "secpal.pre-enrollment-validation-evidence-loss-admission/v1.1"
CURRENT_RECEIPT_SCHEMA_VERSION = "1.3"
CURRENT_RECEIPT_DOMAIN = (
    "secpal.pre-enrollment-validation-evidence-loss-admission/v1.3"
)
ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/pre-enrollment-validation-evidence-loss.json"
CURRENT_SAFETY_PATH = "tests/pre-enrollment-current-safety.py"
REGISTERED_CURRENT_SAFETY_PATH = (
    "tests/pre-enrollment-registered-repository-current-safety.py"
)
CURRENT_RECEIPT_SAFETY_PATH = "tests/pre-enrollment-github-948-current-safety.py"
CURRENT_SAFETY_INVARIANTS = (
    "candidate_local_issuer_rejected", "complete_feedback", "context_binding",
    "historical_bytes_unavailable", "ordinary_prior_ready", "resolved_feedback",
    "signed_authority_required", "source_history", "wrong_signer",
)
REGISTERED_CURRENT_SAFETY_INVARIANTS = (
    "current_tree_exact", "historical_bytes_unavailable",
    "registered_validation", "source_history",
)
REGISTERED_CURRENT_SAFETY_POLICY = (
    "REGISTERED_REPOSITORY_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_CURRENT_SAFETY"
)
CURRENT_RECEIPT_SAFETY_POLICY = (
    "EXACT_STATE_ADOPTION_CURRENT_RECEIPT_CURRENT_SAFETY"
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
ANCESTOR_FIELDS = frozenset(FIELDS | {
    "historical_receipt_head_sha", "source_history", "source_history_digest",
    "historical_receipt_provenance_digest",
    "historical_provider_summary_digest",
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
ANCESTOR_RECORD_FIELDS = frozenset({
    "admission_schema_version", "repository", "delivery_issue", "pull_request",
    "head_sha", "tree_sha", "parent_sha", "source_signer_identity",
    "historical_package_status", "historical_final_attestation_digest",
    "historical_bytes_reconstructed", "observed_pre_enrollment_history",
    "intended_state", "feedback_digest", "technical_decisions",
    "historical_provider_summary_digest", "current_safety_harness_path",
})
CURRENT_RECEIPT_RECORD_FIELDS = frozenset(
    ANCESTOR_RECORD_FIELDS | {"historical_validation_receipt_digest"}
)
SOURCE_HISTORY_FIELDS = frozenset({
    "head_sha", "tree_sha", "parent_shas", "committed_at", "signer_identity",
    "commit_signature_evidence_digest",
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
    tree_sha: str
    parent_shas: tuple[str, ...]
    committed_at: str
    signature_verified: bool


CurrentHarnessBlobObservation = exact_source_safety.HarnessBlobObservation
CurrentHarnessBlobFacts = exact_source_safety.HarnessBlobFacts
CurrentHarnessBlobBinding = exact_source_safety.HarnessBlobBinding


@dataclass(frozen=True)
class SourceCommitFacts:
    head_sha: str
    tree_sha: str
    parent_shas: tuple[str, ...]
    signature_verified: bool


@dataclass(frozen=True)
class HistoricalProviderBinding:
    """Authenticate one legacy terminal provider summary through exact PR history."""

    repository: str
    pull_request: int
    current_head_sha: str
    provider_head_sha: str
    summary_digest: str

    def _scope(
        self, *, repository: str, pull_request: int, current_head_sha: str,
    ) -> None:
        if (
            repository != self.repository
            or pull_request != self.pull_request
            or current_head_sha != self.current_head_sha
        ):
            raise fast_path.SecurityBlocker(
                "historical review-provider source scope changed"
            )

    def provider_head(
        self, *, repository: str, pull_request: int, current_head_sha: str,
    ) -> str:
        self._scope(
            repository=repository, pull_request=pull_request,
            current_head_sha=current_head_sha,
        )
        return self.provider_head_sha

    def verify_historical_provider_summary(
        self, *, body: Any, repository: str, pull_request: int,
        current_head_sha: str,
    ) -> None:
        self._scope(
            repository=repository, pull_request=pull_request,
            current_head_sha=current_head_sha,
        )
        code_rows = [
            line for line in body.splitlines() if "**Code Review**" in line
        ] if isinstance(body, str) else []
        security_rows = [
            line for line in body.splitlines() if "**Security Review**" in line
        ] if isinstance(body, str) else []
        if (
            not isinstance(body, str)
            or len(body.encode("utf-8")) > 64 * 1024
            or fast_path.digest_text(body) != self.summary_digest
            or body.count(fast_path.CODEX_REVIEW_SUMMARY_MARKER) != 1
            or len(code_rows) != 1
            or security_rows
            or "✅ **Completed**" not in code_rows[0]
            or f"`{self.provider_head_sha[:7]}`" not in code_rows[0]
        ):
            raise fast_path.SecurityBlocker(
                "historical review-provider summary is invalid"
            )


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


def _validate_source_history(
    value: Any, *, current_head: str, current_tree: str, current_parent: str,
    source_signer: str, current_signature_digest: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) < 2 or len(value) >= 100:
        raise authority.LifecycleAuthorityError(
            "loss source history is incomplete or ambiguous"
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_time: datetime | None = None
    for index, raw in enumerate(value):
        item = copy.deepcopy(
            authority._require_closed(raw, SOURCE_HISTORY_FIELDS, "loss source history")
        )
        head = authority._require_oid(item["head_sha"], "loss history head")
        tree = authority._require_oid(item["tree_sha"], "loss history tree")
        parents = item["parent_shas"]
        if not isinstance(parents, list):
            raise authority.LifecycleAuthorityError(
                "loss source history topology or signer is invalid"
            )
        normalized_parents = [
            authority._require_oid(parent, "loss history parent")
            for parent in parents
        ]
        committed_at = authority._require_adoption_timestamp(
            item["committed_at"], "loss history commit time"
        )
        instant = authority._parse_adoption_timestamp(
            committed_at, "loss history commit time"
        )
        if (
            head in seen
            or not 1 <= len(normalized_parents) <= 2
            or len(normalized_parents) != len(set(normalized_parents))
            or head in normalized_parents
            or (index and normalized_parents[0] != normalized[-1]["head_sha"])
            or (previous_time is not None and instant < previous_time)
            or item["signer_identity"] != source_signer
        ):
            raise authority.LifecycleAuthorityError(
                "loss source history topology or signer is invalid"
            )
        authority._require_identity(item["signer_identity"], "loss history signer")
        authority._require_digest(
            item["commit_signature_evidence_digest"],
            "loss history signature evidence",
        )
        item.update(
            head_sha=head, tree_sha=tree, parent_shas=normalized_parents,
            committed_at=committed_at,
        )
        normalized.append(item)
        seen.add(head)
        previous_time = instant
    if (
        normalized[-1]["head_sha"] != current_head
        or normalized[-1]["tree_sha"] != current_tree
        or normalized[-1]["parent_shas"] != [current_parent]
        or normalized[-1]["commit_signature_evidence_digest"]
        != current_signature_digest
    ):
        raise authority.LifecycleAuthorityError("loss source history tip changed")
    return normalized


def _verify_document(value: Any) -> dict[str, Any]:
    """Verify immutable enrollment provenance without consulting a later CURRENT."""

    if not isinstance(value, Mapping):
        raise authority.LifecycleAuthorityError(
            "validation-evidence-loss admission is malformed"
        )
    version = value.get("schema_version")
    fields = FIELDS if version == "1.0" else ANCESTOR_FIELDS
    doc = copy.deepcopy(
        authority._require_closed(value, fields, "validation-evidence-loss admission")
    )
    if (
        version not in {
            "1.0", ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
        }
        or doc["kind"] != KIND
        or doc["domain"]
        != {
            "1.0": DOMAIN,
            ANCESTOR_SCHEMA_VERSION: ANCESTOR_DOMAIN,
            CURRENT_RECEIPT_SCHEMA_VERSION: CURRENT_RECEIPT_DOMAIN,
        }[version]
        or doc["pull_request_state"] != "OPEN"
        or doc["draft"] is not (version == "1.0")
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
    state = authority._validate_state(
        doc["intended_state"], allow_adopted_observations=True
    )
    if version == "1.0":
        if state != _intended_state():
            raise authority.LifecycleAuthorityError(
                "loss admission must preserve exhausted Draft counters"
            )
    else:
        authority._ready_source_recovery_state(
            state, historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
        )
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
    if version in {
        ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
    }:
        receipt_head = authority._require_oid(
            doc["historical_receipt_head_sha"], "historical receipt head"
        )
        if (
            version == ANCESTOR_SCHEMA_VERSION
            and receipt_head == doc["head_sha"]
        ) or (
            version == CURRENT_RECEIPT_SCHEMA_VERSION
            and receipt_head != doc["head_sha"]
        ):
            raise authority.LifecycleAuthorityError(
                "historical receipt placement changed"
            )
        authority._require_digest(
            doc["historical_provider_summary_digest"],
            "historical review-provider summary",
        )
        source_history = _validate_source_history(
            doc["source_history"], current_head=doc["head_sha"],
            current_tree=doc["tree_sha"], current_parent=doc["parent_sha"],
            source_signer=doc["source_signer_identity"],
            current_signature_digest=doc["commit_signature_evidence_digest"],
        )
        if sum(item["head_sha"] == receipt_head for item in source_history) != 1:
            raise authority.LifecycleAuthorityError(
                "historical receipt head is outside exact delivery history"
            )
        source_history_digest = authority.digest_json(source_history)
        if doc["source_history_digest"] != source_history_digest:
            raise authority.LifecycleAuthorityError("loss source history digest changed")
        provenance = {
            "repository": doc["repository"],
            "delivery_issue": doc["delivery_issue"],
            "pull_request": doc["pull_request"],
            "current_head_sha": doc["head_sha"],
            "current_tree_sha": doc["tree_sha"],
            "historical_receipt_head_sha": receipt_head,
            "historical_validation_receipt_digest": doc[
                "historical_validation_receipt_digest"
            ],
            "source_history_digest": source_history_digest,
        }
        if doc["historical_receipt_provenance_digest"] != authority.digest_json(
            provenance
        ):
            raise authority.LifecycleAuthorityError(
                "historical receipt provenance changed"
            )
        authority._require_digest(
            doc["historical_receipt_provenance_digest"],
            "historical receipt provenance",
        )
    signed = {key: item for key, item in doc.items() if key != "admission_digest"}
    if authority.digest_json(signed) != doc["admission_digest"]:
        raise authority.LifecycleAuthorityError("loss admission digest changed")
    trust = authority._load_lifecycle_trust_policy(doc["repository"])
    authority._verify_signature(
        authority.canonical_json_bytes(authority._unsigned(doc, "admission_digest", "signature")),
        doc["signature"], doc["signer_identity"], doc["domain"],
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


def _admit_registered_repository_entry(
    entry: Any, repository: str,
) -> Mapping[str, Any]:
    if (
        not isinstance(entry, Mapping)
        or entry.get("repository") != repository
        or not isinstance(entry.get("lifecycle_authority_policy"), Mapping)
    ):
        raise authority.LifecycleAuthorityError(
            "loss admission repository has no maintained lifecycle authority"
        )
    return entry


def _accepted_policy(repository: str, issue: int) -> tuple[str, dict[str, Any], Any, Any]:
    repository = authority._require_repository(repository)
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
    helper = transport._load_actions_helper()
    try:
        entry = helper.select_repository(helper.load_registry(), repository)
    except (fast_path.SecurityBlocker, KeyError, TypeError, ValueError) as exc:
        raise authority.LifecycleAuthorityError(
            "loss admission repository is not registered"
        ) from exc
    entry = _admit_registered_repository_entry(entry, repository)
    trust = authority._load_lifecycle_trust_policy(repository)
    try:
        publication._verify_live_protection(trust)
    except publication.LifecyclePublicationError as exc:
        raise authority.LifecycleAuthorityError(
            "loss admission lifecycle publication policy is not protected"
        ) from exc
    records = [item for item in policy["admissions"] if item.get("repository") == repository and item.get("delivery_issue") == issue]
    if len(records) != 1:
        raise authority.LifecycleAuthorityError("no unique accepted-main evidence-loss proof")
    record_version = records[0].get("admission_schema_version", "1.0")
    record_fields = {
        "1.0": RECORD_FIELDS,
        ANCESTOR_SCHEMA_VERSION: ANCESTOR_RECORD_FIELDS,
        CURRENT_RECEIPT_SCHEMA_VERSION: CURRENT_RECEIPT_RECORD_FIELDS,
    }.get(record_version, ANCESTOR_RECORD_FIELDS)
    record = copy.deepcopy(
        authority._require_closed(records[0], record_fields, "loss proof policy")
    )
    if record_version not in {
        "1.0", ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
    }:
        raise authority.LifecycleAuthorityError(
            "loss proof policy version is unknown"
        )
    if record_version == "1.0" and repository != "SecPal/.github":
        raise authority.LifecycleAuthorityError(
            "version-1.0 loss admission repository is not maintained"
        )
    authority._require_positive_int(record["pull_request"], "loss policy pull request")
    for field in ("head_sha", "tree_sha", "parent_sha"):
        authority._require_oid(record[field], field)
    digest_fields = ["feedback_digest"]
    if record_version == "1.0":
        digest_fields.append("historical_validation_receipt_digest")
    elif record_version == ANCESTOR_SCHEMA_VERSION:
        digest_fields.append("historical_provider_summary_digest")
    else:
        digest_fields.extend((
            "historical_provider_summary_digest",
            "historical_validation_receipt_digest",
        ))
    for field in digest_fields:
        authority._require_digest(record[field], field)
    authority._require_identity(record["source_signer_identity"], "loss source signer")
    intended_state = (
        _intended_state()
        if record_version == "1.0"
        else authority._ready_source_recovery_state(
            record["intended_state"],
            historical_proof_mode=authority.EXACT_ADOPTION_PROOF_MODE,
        )
    )
    authority._normalize_observed_pre_enrollment_history(
        record["observed_pre_enrollment_history"], expected_head=record["head_sha"],
        intended_state=intended_state, review_budget_consumption_admitted=True,
    )
    _decisions(record["technical_decisions"])
    if (
        record["historical_package_status"] != "UNAVAILABLE"
        or record["historical_final_attestation_digest"] is not None
        or record["historical_bytes_reconstructed"] is not False
    ):
        raise authority.LifecycleAuthorityError("loss proof cannot reconstruct historical artifacts")
    maintained_harness = {
        ANCESTOR_SCHEMA_VERSION: REGISTERED_CURRENT_SAFETY_PATH,
        CURRENT_RECEIPT_SCHEMA_VERSION: CURRENT_RECEIPT_SAFETY_PATH,
    }.get(record_version)
    if maintained_harness is not None and (
        record["current_safety_harness_path"] != maintained_harness
    ):
        raise authority.LifecycleAuthorityError(
            "registered loss current-safety policy is not maintained"
        )
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
                tree_sha=(
                    item.get("commit", {}).get("tree", {}).get("sha")
                    if isinstance(item, Mapping)
                    and isinstance(item.get("commit"), Mapping)
                    and isinstance(item["commit"].get("tree"), Mapping)
                    else None
                ),
                parent_shas=tuple(
                    authority._require_oid(
                        _provider_value(parent, ("sha",), "commit parent"),
                        "provider commit parent",
                    )
                    for parent in _provider_value(item, ("parents",), "commit")
                ),
                committed_at=_provider_value(item, ("commit", "committer", "date"), "commit"),
                signature_verified=(
                    item.get("commit", {}).get("verification", {}).get(
                        "verified", False
                    )
                    if isinstance(item, Mapping)
                    and isinstance(item.get("commit"), Mapping)
                    and isinstance(item["commit"].get("verification"), Mapping)
                    else False
                ),
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


def _record_version(record: Mapping[str, Any]) -> str:
    return record.get("admission_schema_version", "1.0")


def _source_fetch_depth(
    record: Mapping[str, Any], commits: tuple[CommitFacts, ...],
) -> int:
    """Cover every admitted first-parent source commit and its predecessor."""

    if _record_version(record) == "1.0":
        return 64
    if not 2 <= len(commits) < 100:
        raise authority.LifecycleAuthorityError(
            "loss source history is incomplete or ambiguous"
        )
    return len(commits) + 1


def _effective_source_head(
    commits: tuple[CommitFacts, ...], occurred_at: str,
) -> str:
    instant = authority._parse_adoption_timestamp(
        occurred_at, "loss source event time"
    )
    eligible = [
        item for item in commits
        if authority._parse_adoption_timestamp(
            item.committed_at, "loss history commit time"
        ) <= instant
    ]
    if not eligible:
        raise authority.LifecycleAuthorityError(
            "loss source event predates authenticated delivery history"
        )
    return eligible[-1].head_sha


def _historical_provider_binding(
    record: Mapping[str, Any], provider: NormalizedProviderFacts,
) -> HistoricalProviderBinding:
    ready = [
        item for item in provider.timeline_events
        if item.kind == "ready_for_review"
    ]
    draft = [
        item for item in provider.timeline_events
        if item.kind == "convert_to_draft"
    ]
    if len(ready) != 1 or draft:
        raise authority.LifecycleAuthorityError(
            "loss source Ready chronology is ambiguous"
        )
    return _historical_provider_binding_for_ready(
        record,
        provider.commits,
        ready[0].occurred_at,
    )


def _historical_provider_binding_for_ready(
    record: Mapping[str, Any],
    commits: tuple[CommitFacts, ...],
    ready_at: str,
    *,
    observed_ready_head: str | None = None,
) -> HistoricalProviderBinding:
    """Derive the v1.1 provider head from one authenticated Ready instant."""

    provider_head = _effective_source_head(commits, ready_at)
    if observed_ready_head is not None and provider_head != observed_ready_head:
        raise authority.LifecycleAuthorityError(
            "loss source Ready head changed"
        )
    source_heads = [item.head_sha for item in commits]
    if (
        not source_heads
        or source_heads[-1] != record["head_sha"]
        or source_heads.count(provider_head) != 1
        or source_heads.index(provider_head) >= len(source_heads) - 1
    ):
        raise authority.LifecycleAuthorityError(
            "historical review-provider head is not an ancestor"
        )
    return HistoricalProviderBinding(
        repository=record["repository"],
        pull_request=record["pull_request"],
        current_head_sha=record["head_sha"],
        provider_head_sha=provider_head,
        summary_digest=record["historical_provider_summary_digest"],
    )


def authenticate_historical_provider_binding(
    admission: Any,
) -> HistoricalProviderBinding:
    """Project accepted v1.1 admission provenance into its maintained binding."""

    document = _verify_document(admission)
    if document["schema_version"] not in {
        ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
    }:
        raise authority.LifecycleAuthorityError(
            "historical provider binding requires v1.1 or v1.3 Ready loss provenance"
        )
    main, record, _entry, _trust = _accepted_policy(
        document["repository"], document["delivery_issue"]
    )
    accepted_main = document["accepted_main_sha"]
    if accepted_main != main:
        _authenticate_accepted_policy_epoch(accepted_main, main, record)
    record_fields = (
        "repository", "delivery_issue", "pull_request", "head_sha",
        "tree_sha", "parent_sha", "source_signer_identity",
        "historical_package_status", "historical_final_attestation_digest",
        "historical_bytes_reconstructed", "observed_pre_enrollment_history",
        "intended_state", "historical_provider_summary_digest",
    )
    if document["schema_version"] == CURRENT_RECEIPT_SCHEMA_VERSION:
        record_fields = (*record_fields, "historical_validation_receipt_digest")
    if (
        _record_version(record) != document["schema_version"]
        or document["loss_proof_policy_digest"] != authority.digest_json(record)
        or any(document[field] != record[field] for field in record_fields)
        or document["current_safety"]["feedback_digest"]
        != record["feedback_digest"]
        or document["current_safety"]["technical_decisions"]
        != record["technical_decisions"]
    ):
        raise authority.LifecycleAuthorityError(
            "historical provider binding differs from accepted Ready policy"
        )
    history = document["observed_pre_enrollment_history"]
    ready = [
        item for item in history
        if item["kind"] == "DRAFT_TO_READY_OBSERVED"
    ]
    draft = [
        item for item in history
        if item["kind"] == "READY_TO_DRAFT_OBSERVED"
    ]
    if len(ready) != 1 or draft:
        raise authority.LifecycleAuthorityError(
            "loss source Ready chronology is ambiguous"
        )
    commits = tuple(
        CommitFacts(
            head_sha=item["head_sha"],
            tree_sha=item["tree_sha"],
            parent_shas=tuple(item["parent_shas"]),
            committed_at=item["committed_at"],
            signature_verified=True,
        )
        for item in document["source_history"]
    )
    return _historical_provider_binding_for_ready(
        document,
        commits,
        ready[0]["observed_at"],
        observed_ready_head=ready[0]["head_sha"],
    )


def _authenticate_accepted_policy_epoch(
    accepted_main: str,
    current_main: str,
    current_record: Mapping[str, Any],
) -> None:
    """Require the admission epoch in protected-main ancestry and unchanged policy."""

    accepted_main = authority._require_oid(
        accepted_main, "historical accepted main"
    )
    current_main = authority._require_oid(current_main, "current accepted main")
    commit = _accepted_main_commit_metadata(accepted_main)
    ancestry = publication._run_git(
        ROOT,
        ["merge-base", "--is-ancestor", accepted_main, current_main],
    )
    policy_result = publication._run_git(
        ROOT,
        ["show", f"{accepted_main}:{POLICY_PATH}"],
    )
    if (
        commit != {"sha": accepted_main, "verified": True}
        or ancestry.returncode != 0
        or ancestry.stdout
        or policy_result.returncode != 0
    ):
        raise authority.LifecycleAuthorityError(
            "historical loss policy epoch is not accepted main"
        )
    policy = authority.loads_closed_json(policy_result.stdout)
    if (
        not isinstance(policy, dict)
        or set(policy) != {"schema_version", "admissions"}
        or policy["schema_version"] != "1.0"
        or not isinstance(policy["admissions"], list)
        or any(not isinstance(item, dict) for item in policy["admissions"])
    ):
        raise authority.LifecycleAuthorityError(
            "historical loss policy epoch is malformed"
        )
    matches = [
        item for item in policy["admissions"]
        if item.get("repository") == current_record.get("repository")
        and item.get("delivery_issue") == current_record.get("delivery_issue")
    ]
    if len(matches) != 1 or matches[0] != current_record:
        raise authority.LifecycleAuthorityError(
            "historical loss policy is incompatible with current accepted policy"
        )


def _observe(
    record: Mapping[str, Any], entry: Any, trust: Any,
) -> tuple[SourceCommitFacts, Any, tuple[CommitFacts, ...]]:
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
    gateway_arguments: dict[str, Any] = {}
    if _record_version(record) in {
        ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
    }:
        source_commit = _gh_json(
            f"repos/{repository}/commits/{record['head_sha']}"
        )
        preliminary = _normalize_provider_representations(
            target, issue_state, commits, chronology_before,
            chronology_before, source_commit,
        )
        gateway_arguments["ready_source_provider_binding"] = (
            _historical_provider_binding(record, preliminary)
        )
    reviewed = helper.FastPathGateway(
        ROOT, entry, **gateway_arguments
    ).capture_stable_feedback(repository, pr)
    try:
        chronology_after = _observe_chronology(repository, pr)
    except authority.LifecycleAuthorityError as exc:
        raise authority.LifecycleAuthorityError(
            f"post-feedback chronology acquisition failed: {exc}"
        ) from exc
    if _record_version(record) == "1.0":
        source_commit = _gh_json(
            f"repos/{repository}/commits/{record['head_sha']}"
        )
    normalized = _normalize_provider_representations(
        target, issue_state, commits, chronology_before, chronology_after,
        source_commit,
    )
    source, stable = _admit_observation(record, normalized, reviewed)
    return source, stable, normalized.commits


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
    version = _record_version(record)
    if (
        target.number != pr or target.state != "OPEN"
        or target.draft is not (version == "1.0")
        or target.merged or target.head_sha != record["head_sha"]
        or target.head_repository != repository
        or target.base_repository != repository or target.base_ref != "main"
        or issue_state.number != issue or issue_state.state != "OPEN"
    ):
        raise authority.LifecycleAuthorityError("loss source is not the exact open unenrolled Draft")
    if not commits or len(commits) >= 100:
        raise authority.LifecycleAuthorityError("loss source history is incomplete")
    observations = record["observed_pre_enrollment_history"]
    head_kinds = {
        "PR_CREATED_DRAFT", "REMEDIATION_HEAD_OBSERVED",
        "EXCEPTIONAL_RECOVERY_OBSERVED", "EXCEPTIONAL_CONTINUATION_OBSERVED",
        "HEAD_ADVANCED_OBSERVED",
    }
    head_observations = [
        item for item in observations if item["kind"] in head_kinds
    ]
    if [item.head_sha for item in commits] != [
        item["head_sha"] for item in head_observations
    ]:
        raise authority.LifecycleAuthorityError("loss source observed history changed")
    for index, item in enumerate(commits):
        if version in {
            ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
        }:
            authority._require_oid(item.tree_sha, "loss history tree")
        if (
            not 1 <= len(item.parent_shas) <= (1 if version == "1.0" else 2)
            or len(item.parent_shas) != len(set(item.parent_shas))
            or (index and item.parent_shas[0] != commits[index - 1].head_sha)
            or (
                version in {
                    ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
                }
                and item.signature_verified is not True
            )
        ):
            raise authority.LifecycleAuthorityError(
                "loss source history parent topology or signature changed"
            )
        timestamp = target.created_at if index == 0 else item.committed_at
        if head_observations[index]["observed_at"] != timestamp:
            raise authority.LifecycleAuthorityError("loss source history timestamp changed")
    if version == "1.0":
        if any(
            event.kind in {"ready_for_review", "convert_to_draft"}
            for event in timeline
        ):
            raise authority.LifecycleAuthorityError("loss source has Ready history")
    else:
        transitions = [
            item for item in observations
            if item["kind"] in {
                "DRAFT_TO_READY_OBSERVED", "READY_TO_DRAFT_OBSERVED"
            }
        ]
        expected_transitions = [
            {
                "kind": (
                    "DRAFT_TO_READY_OBSERVED"
                    if event.kind == "ready_for_review"
                    else "READY_TO_DRAFT_OBSERVED"
                ),
                "observed_at": event.occurred_at,
                "head_sha": _effective_source_head(
                    commits, event.occurred_at
                ),
            }
            for event in timeline
        ]
        if [
            {
                "kind": item["kind"],
                "observed_at": item["observed_at"],
                "head_sha": item["head_sha"],
            }
            for item in transitions
        ] != expected_transitions:
            raise authority.LifecycleAuthorityError(
                "loss source Ready chronology changed"
            )
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


def _commit_signature(
    root: Path, head_sha: str, signer_identity: str, trust: Any,
) -> str:
    head_sha = authority._require_oid(head_sha, "loss signed source head")
    signer_identity = authority._require_identity(
        signer_identity, "loss source signer"
    )
    allowed = transport._allowed_signers(root, trust, signer_identity)
    result = transport._run_bootstrap_git(root, [
        "-c", f"gpg.ssh.allowedSignersFile={allowed}", "verify-commit", "--raw", head_sha,
    ])
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    principals = re.findall(r'(?m)^Good "git" signature for ([^\r\n]+) with ', output)
    if result.returncode != 0 or principals != [signer_identity]:
        raise authority.LifecycleAuthorityError("loss source signer is not authenticated")
    evidence = {
        "oid": head_sha, "source": "USER", "signer_identity": signer_identity,
        "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
        "github_verification": {"verified": True, "reason": "valid"},
    }
    return authority.digest_json(fast_path.verify_commit_signatures(
        [evidence], authority._load_delivery_signature_policy(trust.repository),
    )[0])


def _source_signature(root: Path, record: Mapping[str, Any], trust: Any) -> str:
    return _commit_signature(
        root, record["head_sha"], record["source_signer_identity"], trust
    )


def _optional_validation_receipt_trailer(root: Path, head_sha: str) -> str | None:
    value = transport._git_text(
        root,
        [
            "show", "-s",
            "--format=%(trailers:key=SecPal-Validation-Receipt,valueonly,separator=%x00)",
            head_sha,
        ],
    ).rstrip("\n")
    trailers = [item.strip() for item in value.split("\x00") if item.strip()]
    if not trailers:
        return None
    if len(trailers) != 1:
        raise authority.LifecycleAuthorityError(
            "loss source commit has ambiguous validation receipt trailers"
        )
    return authority._require_digest(
        trailers[0], "historical validation receipt"
    )


def _authenticate_source_history(
    root: Path, record: Mapping[str, Any], commits: tuple[CommitFacts, ...],
    trust: Any,
) -> dict[str, Any]:
    """Authenticate all exact PR edges and derive the sole receipt ancestor."""

    if not commits or commits[-1].head_sha != record["head_sha"]:
        raise authority.LifecycleAuthorityError(
            "loss source history does not reach the current head"
        )
    history: list[dict[str, Any]] = []
    receipt_candidates: list[tuple[str, str]] = []
    for index, commit in enumerate(commits):
        local_tree = transport._git_text(
            root, ["rev-parse", f"{commit.head_sha}^{{tree}}"]
        ).strip()
        local_topology = transport._git_text(
            root, ["rev-list", "--parents", "-n", "1", commit.head_sha]
        ).split()
        if (
            local_tree != commit.tree_sha
            or local_topology != [commit.head_sha, *commit.parent_shas]
            or not 1 <= len(commit.parent_shas) <= 2
            or (
                index
                and commit.parent_shas[0] != commits[index - 1].head_sha
            )
            or commit.signature_verified is not True
        ):
            raise authority.LifecycleAuthorityError(
                "loss source history edge, tree, or provider signature changed"
            )
        signature_digest = _commit_signature(
            root, commit.head_sha, record["source_signer_identity"], trust
        )
        trailer = _optional_validation_receipt_trailer(root, commit.head_sha)
        if trailer is not None:
            authority._require_digest(trailer, "historical validation receipt")
            receipt_candidates.append((commit.head_sha, trailer))
        history.append({
            "head_sha": commit.head_sha,
            "tree_sha": commit.tree_sha,
            "parent_shas": list(commit.parent_shas),
            "committed_at": authority._require_adoption_timestamp(
                commit.committed_at, "loss history commit time"
            ),
            "signer_identity": record["source_signer_identity"],
            "commit_signature_evidence_digest": signature_digest,
        })
    if len(receipt_candidates) != 1:
        raise authority.LifecycleAuthorityError(
            "loss source has no unique historical receipt ancestor"
        )
    receipt_head, receipt_digest = receipt_candidates[0]
    current_receipt = _record_version(record) == CURRENT_RECEIPT_SCHEMA_VERSION
    if (receipt_head == record["head_sha"]) is not current_receipt:
        raise authority.LifecycleAuthorityError(
            "loss source historical receipt placement changed"
        )
    source_history_digest = authority.digest_json(history)
    provenance = {
        "repository": record["repository"],
        "delivery_issue": record["delivery_issue"],
        "pull_request": record["pull_request"],
        "current_head_sha": record["head_sha"],
        "current_tree_sha": record["tree_sha"],
        "historical_receipt_head_sha": receipt_head,
        "historical_validation_receipt_digest": receipt_digest,
        "source_history_digest": source_history_digest,
    }
    return {
        "historical_receipt_head_sha": receipt_head,
        "historical_validation_receipt_digest": receipt_digest,
        "source_history": history,
        "source_history_digest": source_history_digest,
        "historical_receipt_provenance_digest": authority.digest_json(provenance),
        "commit_signature_evidence_digest": history[-1][
            "commit_signature_evidence_digest"
        ],
    }


def _verify_source_bytes(root: Path, tree: str, *, expected_listing: str | None = None) -> str:
    return exact_source_safety.verify_source_bytes(
        root, tree, expected_listing=expected_listing,
    )


def _current_validation_harness_paths(main: str, helper: Any, entry: Any) -> tuple[str, ...]:
    return (_admit_current_safety_path(CURRENT_SAFETY_PATH),)


def _admit_current_safety_path(relative: str) -> str:
    if relative != "tests/pre-enrollment-current-safety.py":
        raise authority.LifecycleAuthorityError("current safety path is not maintained")
    return relative


def _current_safety_profile(main: str) -> dict[str, Any]:
    return exact_source_safety.build_profile(
        ROOT, main,
        policy="PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_CURRENT_SAFETY",
        harness_paths=(CURRENT_SAFETY_PATH,),
        purpose="Validate pre-enrollment evidence-loss current safety",
        required_invariants=CURRENT_SAFETY_INVARIANTS,
    )


def _registered_current_safety_profile(main: str) -> dict[str, Any]:
    return exact_source_safety.build_profile(
        ROOT, main,
        policy=REGISTERED_CURRENT_SAFETY_POLICY,
        harness_paths=(REGISTERED_CURRENT_SAFETY_PATH,),
        purpose="Validate registered repository pre-enrollment current safety",
        required_invariants=REGISTERED_CURRENT_SAFETY_INVARIANTS,
    )


def _current_receipt_safety_profile(main: str) -> dict[str, Any]:
    return exact_source_safety.build_profile(
        ROOT, main,
        policy=CURRENT_RECEIPT_SAFETY_POLICY,
        harness_paths=(CURRENT_RECEIPT_SAFETY_PATH,),
        purpose="Validate exact current-receipt adoption current safety",
        required_invariants=REGISTERED_CURRENT_SAFETY_INVARIANTS,
    )


def _current_safety_profile_for_record(
    main: str, record: Mapping[str, Any],
) -> dict[str, Any]:
    if _record_version(record) == "1.0":
        return _current_safety_profile(main)
    if (
        _record_version(record) == ANCESTOR_SCHEMA_VERSION
        and record.get("current_safety_harness_path") == REGISTERED_CURRENT_SAFETY_PATH
    ):
        return _registered_current_safety_profile(main)
    if (
        _record_version(record) == CURRENT_RECEIPT_SCHEMA_VERSION
        and record.get("current_safety_harness_path") == CURRENT_RECEIPT_SAFETY_PATH
    ):
        return _current_receipt_safety_profile(main)
    raise authority.LifecycleAuthorityError(
        "loss current-safety profile is not maintained"
    )


def _admit_current_harness_requested_path(relative: str) -> str:
    """Admit one literal repository-relative harness path without observation."""
    return exact_source_safety.admit_harness_path(
        relative, allowed_paths=frozenset({relative}) if isinstance(relative, str) else frozenset(),
    )


def _observe_current_harness_blob(
    main: str, relative: str,
) -> CurrentHarnessBlobObservation:
    """Observe one literal tree entry without deciding harness conformance."""
    observed = exact_source_safety._observe_harness_blob(ROOT, main, relative)
    return CurrentHarnessBlobObservation(
        observed.commit_oid, observed.requested_path, observed.tree_entry,
    )


def _normalize_current_harness_blob_observation(
    observation: CurrentHarnessBlobObservation,
) -> CurrentHarnessBlobFacts:
    """Normalize one Git tree representation without external observation."""
    if not isinstance(observation, CurrentHarnessBlobObservation):
        raise authority.LifecycleAuthorityError("current validation harness listing is malformed")
    return exact_source_safety._normalize_harness_blob(observation)


def _admit_current_harness_blob(
    observation: CurrentHarnessBlobObservation,
    facts: CurrentHarnessBlobFacts,
) -> CurrentHarnessBlobBinding:
    """Admit canonical tree facts as one exact regular protected-main blob."""
    if not isinstance(observation, CurrentHarnessBlobObservation) or not isinstance(
        facts, CurrentHarnessBlobFacts
    ):
        raise authority.LifecycleAuthorityError("current validation harness listing is malformed")
    return exact_source_safety._admit_harness_blob(
        observation,
        facts,
        allowed_paths=frozenset({observation.requested_path}),
    )


def _current_harness_blob(main: str, relative: str) -> tuple[str, str, int]:
    """Assemble the explicit observation, normalization, and admission stages."""
    return exact_source_safety.harness_blob(
        ROOT, main, relative,
        allowed_paths=frozenset({relative}) if isinstance(relative, str) else frozenset(),
    )


def _verify_current_harness_file(
    destination_root: Path, relative: str, mode: str, blob_oid: str, size: int,
) -> None:
    exact_source_safety._verify_harness_file(
        ROOT, destination_root, relative, mode, blob_oid, size,
    )


def _create_harness_parent(destination_root: Path, relative: Path) -> Path:
    """Create only real directories below the private disposable root."""
    return exact_source_safety._create_harness_parent(destination_root, relative)


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
    return exact_source_safety._copy_harness_file(
        ROOT, main,
        {"path": relative, "mode": mode, "blob_oid": blob_oid, "size": size},
        destination_root, allowed_paths=registered_paths,
    )


@contextmanager
def _current_policy_validation_root(
    main: str,
    *,
    source_root: Path,
    helper: Any,
    entry: Any,
    profile: Mapping[str, Any] | None = None,
) -> Iterator[Path]:
    """Build a disposable target tree with only accepted-main harness bytes overlaid."""
    profile = _current_safety_profile(main) if profile is None else profile
    with exact_source_safety.execution_root(
        ROOT, main, source_root=source_root, profile=profile,
    ) as prepared:
        yield prepared


def _verify_current_safety_root(
    root: Path, tree: str, candidate_listing: str,
    bindings: Mapping[str, tuple[str, str, int]],
) -> None:
    exact_source_safety._verify_execution_root(
        ROOT, root, tree, candidate_listing, bindings,
    )


def _run_current_safety(main: str, root: Path, profile: Mapping[str, Any]) -> None:
    builders = {
        REGISTERED_CURRENT_SAFETY_POLICY: _registered_current_safety_profile,
        CURRENT_RECEIPT_SAFETY_POLICY: _current_receipt_safety_profile,
    }
    builder = builders.get(profile.get("policy"), _current_safety_profile)
    expected = builder(main)
    exact_source_safety.run_profile(
        root, profile, expected_profile=expected,
    )


def _acquire(repository: str, issue: int, *, execute_validation: bool) -> dict[str, Any]:
    main, record, entry, trust = _accepted_policy(repository, issue)
    observed_before = _observe(record, entry, trust)
    _, before, before_commits = observed_before
    helper = transport._load_actions_helper()
    binding = helper._fast_registry_binding(entry)
    profile = _current_safety_profile_for_record(main, record)
    binding = {"repository_policy": binding, "current_safety_profile": profile}
    with tempfile.TemporaryDirectory(prefix="secpal-pre-enrollment-safety-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        transport._git(root, ["init", "--quiet"])
        transport._git(root, ["remote", "add", "origin", trust.publication_remote_url])
        fetch_depth = _source_fetch_depth(record, before_commits)
        transport._git(root, [
            "fetch", "--quiet", "--no-tags", f"--depth={fetch_depth}",
            "origin", record["head_sha"],
        ])
        if transport._git_text(root, ["rev-parse", "FETCH_HEAD"]).strip() != record["head_sha"]:
            raise authority.LifecycleAuthorityError("loss source fetch changed identity")
        transport._git(root, ["checkout", "--quiet", "--detach", record["head_sha"]])
        if transport._git_text(root, ["rev-parse", "HEAD^{tree}"]).strip() != record["tree_sha"]:
            raise authority.LifecycleAuthorityError("loss source tree changed")
        if transport._git_text(root, ["rev-list", "--parents", "-n", "1", "HEAD"]).split() != [record["head_sha"], record["parent_sha"]]:
            raise authority.LifecycleAuthorityError("loss source sole parent changed")
        provenance = None
        if _record_version(record) == "1.0":
            signature_digest = _source_signature(root, record, trust)
            if transport._exact_trailer(root, record["head_sha"]) != record["historical_validation_receipt_digest"]:
                raise authority.LifecycleAuthorityError("loss source historical signed receipt changed")
        else:
            provenance = _authenticate_source_history(
                root, record, before_commits, trust
            )
            signature_digest = provenance[
                "commit_signature_evidence_digest"
            ]
        source_listing = _verify_source_bytes(root, record["tree_sha"])
        if execute_validation:
            validation_arguments = {
                "source_root": root, "helper": helper, "entry": entry,
            }
            if _record_version(record) in {
                ANCESTOR_SCHEMA_VERSION, CURRENT_RECEIPT_SCHEMA_VERSION,
            }:
                validation_arguments["profile"] = profile
            with _current_policy_validation_root(
                main, **validation_arguments,
            ) as validation_root:
                _run_current_safety(main, validation_root, profile)
        _verify_source_bytes(root, record["tree_sha"], expected_listing=source_listing)
        if (
            transport._git_text(root, ["rev-parse", "HEAD"]).strip() != record["head_sha"]
            or transport._git_text(root, ["diff", "--name-only", "HEAD"])
        ):
            raise authority.LifecycleAuthorityError("validation mutated the immutable source")
    _, after, after_commits = _observe(record, entry, trust)
    if before.state_digest != after.state_digest or before_commits != after_commits:
        raise authority.LifecycleAuthorityError("current safety feedback is not stable")
    if _accepted_policy(repository, issue)[0] != main:
        raise authority.LifecycleAuthorityError("accepted-main authority changed during admission")
    return _assemble_source_facts(
        main, record, binding, profile["validation_command_set"], after,
        signature_digest, provenance=provenance,
    )


def _assemble_source_facts(
    main: str, record: Mapping[str, Any], binding: Any, commands: Any,
    reviewed: Any, signature_digest: str,
    *, provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current_safety_identity = authority.digest_json({
        "domain": "secpal.pre-enrollment-current-safety/v1",
        "repository": record["repository"], "head_sha": record["head_sha"],
        "tree_sha": record["tree_sha"], "validation_policy": binding,
        "commands": commands,
        "reviewed_state_digest": reviewed.state_digest, "successful_result": True,
    })
    common_fields = {
        field: copy.deepcopy(record[field])
        for field in {
            "repository", "delivery_issue", "pull_request", "head_sha",
            "tree_sha", "parent_sha", "source_signer_identity",
            "historical_package_status", "historical_final_attestation_digest",
            "historical_bytes_reconstructed", "observed_pre_enrollment_history",
        }
    }
    if _record_version(record) == "1.0":
        common_fields["historical_validation_receipt_digest"] = record[
            "historical_validation_receipt_digest"
        ]
    else:
        if provenance is None:
            raise authority.LifecycleAuthorityError(
                "historical receipt provenance is unavailable"
            )
        common_fields.update(copy.deepcopy(dict(provenance)))
        common_fields["historical_provider_summary_digest"] = record[
            "historical_provider_summary_digest"
        ]
    intended_state = (
        _intended_state()
        if _record_version(record) == "1.0"
        else copy.deepcopy(record["intended_state"])
    )
    return {
        **common_fields,
        "pull_request_state": "OPEN",
        "draft": _record_version(record) == "1.0",
        "commit_signature_evidence_digest": signature_digest,
        "loss_proof_policy_digest": authority.digest_json(record),
        "accepted_main_sha": main,
        "intended_state": intended_state,
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
    if "historical_receipt_head_sha" not in acquired:
        version, domain = "1.0", DOMAIN
    elif acquired["historical_receipt_head_sha"] == acquired["head_sha"]:
        version, domain = CURRENT_RECEIPT_SCHEMA_VERSION, CURRENT_RECEIPT_DOMAIN
    else:
        version, domain = ANCESTOR_SCHEMA_VERSION, ANCESTOR_DOMAIN
    fields = {
        "schema_version": version, "kind": KIND, "domain": domain, **acquired,
        "admission_id": f"pre-enrollment-validation-loss:{authority.digest_json(acquired)}",
        "adoption_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bounded_uses": 1, "signer_identity": identity,
    }
    signature = signer(authority.canonical_json_bytes(fields), domain)
    signed = {**fields, "signature": signature}
    return _verify_document({**signed, "admission_digest": authority.digest_json(signed)})
