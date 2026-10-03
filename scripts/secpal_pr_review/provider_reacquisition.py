# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Same-head reconciliation of unavailable historical acquisition evidence.

Historical validity stays unknown. Fresh requests and results have distinct
identities. Observation, normalization, admission and assembly are explicit;
callers cannot supply a loss declaration, provider subset or observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import json
import re
from pathlib import Path
from typing import Any

from . import fast_path
from . import provider_acquisition as acquisition
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication
from . import bootstrap_source_admission as transport
from . import legacy_enrolled_package_loss


OPERATION = "PROVIDER_ACQUISITION_EVIDENCE_LOSS_REACQUISITION"
CLASSIFICATION = "REQUIRED_HISTORICAL_ACQUISITION_EVIDENCE_UNAVAILABLE"
MAINTAINED_STORES = tuple(legacy_enrolled_package_loss.EXPECTED_DURABLE_STORES)
_LOSS_TOKEN = object()
AUTHORIZATION_KIND = "SECPAL_PROVIDER_REACQUISITION_AUTHORIZATION"
AUTHORIZATION_DOMAIN = "secpal.provider-dispatch-reacquisition-authorization/v1"
_AUTHORIZATION_TOKEN = object()
_FRESH_ACQUISITION_TOKEN = object()
_BINDING_FIELDS = (
    "repository", "delivery_issue", "pull_request", "lifecycle_id",
    "current_publication_oid", "current_publication_digest", "current_authority_digest",
    "head_sha", "tree_sha", "lifecycle_state",
)
_AUTHORIZATION_FIELDS = frozenset(_BINDING_FIELDS) | {
    "schema_version", "kind", "domain", "operation", "bounded_uses",
    "review_types", "assessment_id", "loss_proof", "loss_proof_digest",
    "authorized_at", "signer_identity", "signature", "authorization_digest",
}
_SURVEY_FIELDS = frozenset({
    "source_history", "source_packages", "journal_packages",
    "historical_digest_identities", "maintained_stores", "unsearched_stores",
    "retained_local_store", "output_scope", "authoritative_head_publication",
})


def _retained_package_digests(current: publication.VerifiedLifecyclePublication) -> tuple[str, ...]:
    return tuple(sorted({d for d in (
        current.lifecycle.validation_receipt_digest,
        current.lifecycle.source_validation_evidence_digest,
        current.lifecycle.adoption_source_evidence_digest,
    ) if d is not None}))


@dataclass(frozen=True)
class VerifiedAcquisitionEvidenceLoss:
    classification: str
    original_first_fallback_validity: str
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    current_publication_oid: str
    current_publication_digest: str
    current_authority_digest: str
    head_sha: str
    tree_sha: str
    lifecycle_state: dict[str, Any]
    review_types: tuple[str, ...]
    historical_requests: tuple[dict[str, Any], ...]
    historical_results: tuple[dict[str, Any], ...]
    historical_summary: str
    historical_observation: dict[str, Any]
    historical_feedback: dict[str, Any]
    survey: dict[str, Any]
    proof_digest: str
    _seal: object


def _loss_projection(value: VerifiedAcquisitionEvidenceLoss) -> dict[str, Any]:
    return {k: v for k, v in vars(value).items() if k not in {"proof_digest", "_seal"}}


def require_verified_loss(value: Any) -> VerifiedAcquisitionEvidenceLoss:
    if (type(value) is not VerifiedAcquisitionEvidenceLoss
            or value._seal is not _LOSS_TOKEN
            or value.proof_digest != fast_path.digest_json(_loss_projection(value))):
        raise fast_path.SecurityBlocker("acquisition loss is not independently authenticated")
    return value


def _admit_loss(
    current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
    observed: dict[str, Any],
    survey: dict[str, Any],
) -> VerifiedAcquisitionEvidenceLoss:
    """Pure admission of a complete bounded survey, never universal absence."""

    if type(current) is not publication.VerifiedLifecyclePublication:
        raise fast_path.SecurityBlocker("acquisition loss requires protected CURRENT")
    lifecycle = current.lifecycle
    state = authority._validate_state(lifecycle.state,
        allow_adopted_observations=lifecycle.historical_proof_mode == authority.EXACT_ADOPTION_PROOF_MODE)
    if (
        lifecycle.repository != "SecPal/.github"
        or observed["repository"] != lifecycle.repository
        or observed["pull_request"] != lifecycle.pull_request
        or observed["state"] != "OPEN" or observed["draft"] is not False
        or observed["head"] != lifecycle.head_sha
        or feedback.repository != lifecycle.repository
        or feedback.pull_request_number != lifecycle.pull_request
        or feedback.head_sha != lifecycle.head_sha or feedback.pr_state != "OPEN"
        or state["ready"] is not True or state["draft"] is not False
        or state["unrestricted_review_count"] != 1
        or state["ready_transition_count"] != 1
        or state["remediation_cycle_count"] != 1
        or state["cycle_3_absent"] is not True
        or state["exceptional_recovery_count"] != 0
        or state["exceptional_continuation_count"] != 0
    ):
        raise fast_path.SecurityBlocker("acquisition loss does not bind ordinary Ready CURRENT")
    authority._require_oid(lifecycle.tree_sha, "acquisition loss tree")
    if (
        not isinstance(survey, dict) or set(survey) != _SURVEY_FIELDS
        or survey["maintained_stores"] != MAINTAINED_STORES
        or survey["unsearched_stores"] != ()
        or survey["retained_local_store"] != "NO_MAINTAINED_RETAINED_STORE"
        or survey["output_scope"] != "GITIGNORED_WORKSPACE_LOCAL"
        or survey["source_packages"] != () or survey["journal_packages"] != ()
        or not survey["source_history"]
        or survey["source_history"][-1] != (lifecycle.head_sha, lifecycle.tree_sha)
        or not survey["historical_digest_identities"]
        or survey["historical_digest_identities"] != _retained_package_digests(current)
        or survey["authoritative_head_publication"] is not None
    ):
        raise fast_path.SecurityBlocker("required historical acquisition loss survey is incomplete or proof remains available")
    for digest in survey["historical_digest_identities"]:
        authority._require_digest(digest, "historical acquisition package identity")
    events = observed["events"]
    acquisition._require_feedback_inventory(feedback,
        {e["node_id"]: e for e in events if e["kind"] == "IssueComment"},
        {e["node_id"]: e for e in events if e["kind"] == "PullRequestReview"})
    ready = [e for e in events if e["kind"] == "ReadyForReviewEvent"]
    commits = [e for e in events if e["kind"] == "COMMIT"]
    if (
        len(ready) != 1 or ready[0]["actor"] != observed["author"]
        or not commits or commits[-1]["head"] != lifecycle.head_sha
        or any(e["kind"] in {"ConvertToDraftEvent", "HeadRefForcePushedEvent", "HeadRefDeletedEvent", "HeadRefRestoredEvent"} for e in events)
    ):
        raise fast_path.SecurityBlocker("historical acquisition Ready/head history is ambiguous")
    if tuple(head for head, _tree in survey["source_history"]) != tuple(e["head"] for e in commits):
        raise fast_path.SecurityBlocker("historical acquisition source survey does not cover exact complete history")
    for head, tree in survey["source_history"]:
        authority._require_oid(head, "surveyed historical head")
        authority._require_oid(tree, "surveyed historical tree")
    # Provider requirements belong to the canonical terminal assessment policy.
    review_types = fast_path.required_codex_review_types()
    summary = getattr(feedback, "provider_summary_body", None)
    fast_path.verify_codex_provider_summary(summary, head_sha=lifecycle.head_sha,
        repository=lifecycle.repository, pull_request_number=lifecycle.pull_request)
    provider = fast_path.CODEX_REVIEW_PROVIDER
    actor = (provider["login"], provider["node_id"], provider["database_id"])
    summaries = [e for e in events if e["kind"] == "IssueComment"
                 and e["actor"] == actor and e["body"] == summary]
    if len(summaries) != 1:
        raise fast_path.SecurityBlocker("historical acquisition terminal summary is unauthenticated")
    requests, results = [], []
    for review_type in review_types:
        trigger = acquisition._CANONICAL_TRIGGERS[review_type]
        matches = [e for e in events if e["kind"] == "IssueComment"
                   and any(body.strip() == trigger for _stamp, body in e["versions"])]
        if len(matches) != 1:
            raise fast_path.SecurityBlocker("historical acquisition request is absent or duplicated")
        request = matches[0]
        position = events.index(request)
        if (request["body"] != trigger or request["actor"] != observed["author"]
                or request["updated_at"] != request["created_at"]
                or events.index(ready[0]) >= position
                or events.index(commits[-1]) >= position):
            raise fast_path.SecurityBlocker("historical acquisition identity/head was substituted")
        # Request creation is known; head publication time is deliberately unknown.
        terminal = [e for e in events
                    if _provider_result_type(e, lifecycle.head_sha) == review_type
                    and acquisition._timestamp(e["created_at"]) > acquisition._timestamp(request["created_at"])]
        if len(terminal) != 1:
            raise fast_path.SecurityBlocker("historical acquisition terminal result is missing or ambiguous")
        requests.append({"review_type": review_type, **request})
        results.append({"review_type": review_type, **terminal[0]})
    fields = dict(
        classification=CLASSIFICATION,
        original_first_fallback_validity="UNPROVABLE_FROM_RETAINED_AUTHORITY",
        repository=lifecycle.repository, delivery_issue=lifecycle.delivery_issue,
        pull_request=lifecycle.pull_request, lifecycle_id=lifecycle.lifecycle_id,
        current_publication_oid=current.publication_oid,
        current_publication_digest=current.publication_digest,
        current_authority_digest=lifecycle.authority_digest,
        head_sha=lifecycle.head_sha, tree_sha=lifecycle.tree_sha,
        lifecycle_state=state, review_types=review_types,
        historical_requests=tuple(requests), historical_results=tuple(results),
        historical_summary=summary, historical_observation=observed,
        historical_feedback=feedback.to_dict(), survey=survey,
    )
    return VerifiedAcquisitionEvidenceLoss(**fields,
        proof_digest=fast_path.digest_json(fields), _seal=_LOSS_TOKEN)


def _gh_json(arguments: list[str], operation: str) -> Any:
    result = publication._run_gh(["api", "--hostname", "github.com", *arguments])
    if result.returncode != 0:
        raise fast_path.SecurityBlocker(f"reacquisition {operation} observation unavailable")
    try:
        return json.loads(result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
    except (ValueError, UnicodeDecodeError) as exc:
        raise fast_path.SecurityBlocker(f"reacquisition {operation} observation malformed") from exc


def _observe_timeline(repository: str, pull_request: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    return acquisition._normalize_observation(_gh_json([
        "graphql", "-f", f"query={acquisition._QUERY}", "-f", f"owner={owner}",
        "-f", f"name={name}", "-F", f"number={pull_request}",
    ], "complete request history"))


def _observe_push_survey(observed: dict[str, Any]) -> dict[str, Any] | None:
    """The same maintained three-page feed; absence alone grants nothing."""

    for page in range(1, 4):
        events = _gh_json([f"repos/{observed['repository']}/events?per_page=100&page={page}"], "head publication survey")
        selected = acquisition._select_head_publication(events, observed)
        if selected is not None:
            return selected
        if len(events) < 100:
            break
    return None


def _package_identities(raw: bytes, current: publication.VerifiedLifecyclePublication) -> tuple[str, ...]:
    """Identify available typed JSON package bytes, never digest references."""

    try:
        value = json.loads(raw, object_pairs_hook=publication._reject_duplicate_pairs)
    except (ValueError, UnicodeDecodeError):
        return ()
    matches = []
    def visit(item: Any) -> None:
        if isinstance(item, dict):
            integration = (item.get("kind") == fast_path.READY_INTEGRATION_KIND
                and item.get("delivery_issue", item.get("delivery_issue_number")) == current.lifecycle.delivery_issue
                and (item.get("validated_tree_sha") == current.lifecycle.tree_sha
                     or item.get("head_sha") == current.lifecycle.head_sha))
            companion = (item.get("head_sha") == current.lifecycle.head_sha
                and any(isinstance(item.get(field), str) and item[field] == expected
                    for field, expected in (("receipt_digest", current.lifecycle.validation_receipt_digest),
                        ("attestation_digest", current.lifecycle.adoption_source_evidence_digest))))
            if item.get("repository") == current.lifecycle.repository and (integration or companion):
                matches.append(fast_path.digest_json(item))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)
    return tuple(sorted(matches))


def _git(root: Any, arguments: list[str]) -> bytes:
    result = publication._run_git(root, arguments)
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("reacquisition source-store survey unavailable")
    return result.stdout


def _admit_blob_sizes(expected: tuple[str, ...], raw: bytes) -> None:
    """Bound immutable source bytes before the batch payload is acquired."""

    lines = raw.splitlines()
    if len(lines) != len(expected):
        raise fast_path.SecurityBlocker("reacquisition source blob size inventory is incomplete")
    total = 0
    for identity, line in zip(expected, lines):
        fields = line.split()
        if (len(fields) != 3 or fields[0] != identity.encode("ascii")
                or fields[1] != b"blob" or not fields[2].isdigit()):
            raise fast_path.SecurityBlocker("reacquisition source blob size inventory is malformed")
        size = int(fields[2])
        total += size
        if size > 16 * 1024 * 1024 or total > 64 * 1024 * 1024:
            raise fast_path.SecurityBlocker("reacquisition source package bytes exceed maintained bound")


def _observe_package_survey(
    current: publication.VerifiedLifecyclePublication, observed: dict[str, Any],
) -> dict[str, Any]:
    """Reuse the maintained source-history/journal inventory and isolated Git.

    Workspace-local .context packages have no maintained retained-session store.
    A source which tracked that scope cannot use this exact loss class. All
    source blobs are surveyed, regardless of extension, under explicit bounds.
    """

    policy = authority._load_lifecycle_trust_policy(current.lifecycle.repository)
    publication._verify_live_protection(policy)
    source_heads = [e["head"] for e in observed["events"] if e["kind"] == "COMMIT"]
    if not source_heads or len(source_heads) > 100 or len(set(source_heads)) != len(source_heads):
        raise fast_path.SecurityBlocker("reacquisition source history is incomplete")
    history, source_packages, journal_packages = [], [], []
    with publication._isolated_repository(policy, write=False) as (root, _environment):
        tip = publication._observe_remote_current_once(root, policy.publication_remote_url, policy.publication_branch)
        if tip is None:
            raise fast_path.SecurityBlocker("reacquisition journal survey unavailable")
        _entries, latest, _admissions = publication._walk_journal(root, tip, policy.publication_branch)
        selected = latest.get((current.lifecycle.repository, current.lifecycle.delivery_issue))
        if selected is None or selected[0] != current.publication_oid or selected[1]["publication_digest"] != current.publication_digest:
            raise fast_path.SecurityBlocker("reacquisition CURRENT changed during survey")
        cursor, count = tip, 0
        while cursor is not None:
            count += 1
            if count > 4096:
                raise fast_path.SecurityBlocker("reacquisition journal exceeds maintained survey bound")
            raw, cursor = publication._read_publication_object(root, cursor)
            journal_packages.extend(_package_identities(raw, current))
        _git(root, ["fetch", "--no-tags", policy.publication_remote_url, current.lifecycle.head_sha])
        blob_ids = set()
        for head in source_heads:
            tree = _git(root, ["rev-parse", f"{head}^{{tree}}"]).decode("ascii").strip()
            authority._require_oid(tree, "surveyed source tree")
            history.append((head, tree))
            ignored = _git(root, ["show", f"{head}:.gitignore"]).decode("utf-8").splitlines()
            if ".context/" not in ignored:
                raise fast_path.SecurityBlocker("reacquisition output persistence scope is not proven")
            listing = _git(root, ["ls-tree", "-r", "-z", head]).split(b"\0")
            if len(listing) > 10001:
                raise fast_path.SecurityBlocker("reacquisition source tree exceeds maintained survey bound")
            for entry in filter(None, listing):
                metadata, path = entry.split(b"\t", 1)
                mode, kind, oid = metadata.split()
                if path == b".context" or path.startswith(b".context/"):
                    raise fast_path.SecurityBlocker("reacquisition has a retained tracked package store")
                if mode == b"160000":
                    raise fast_path.SecurityBlocker("reacquisition source has an unsurveyed linked package store")
                if kind == b"blob":
                    blob_ids.add(oid.decode("ascii"))
        if len(blob_ids) > 20000:
            raise fast_path.SecurityBlocker("reacquisition source blob inventory exceeds bound")
        # One bounded immutable-object batch avoids an API request per file.
        if not blob_ids:
            raise fast_path.SecurityBlocker("reacquisition source package survey incomplete")
        object_input = "".join(oid + "\n" for oid in sorted(blob_ids)).encode("ascii")
        sizes = publication._run_git(root, ["cat-file", "--batch-check"], input_bytes=object_input)
        if sizes.returncode != 0:
            raise fast_path.SecurityBlocker("reacquisition source blob sizes unavailable")
        _admit_blob_sizes(tuple(sorted(blob_ids)), sizes.stdout)
        batch = publication._run_git(
            root, ["cat-file", "--batch"], input_bytes=object_input)
        if batch.returncode != 0 or len(batch.stdout) > 64 * 1024 * 1024:
            raise fast_path.SecurityBlocker("reacquisition source package survey incomplete")
        remaining = batch.stdout
        for expected in sorted(blob_ids):
            header, remaining = remaining.split(b"\n", 1)
            oid, kind, size = header.split()
            if oid.decode("ascii") != expected or kind != b"blob" or not size.isdigit():
                raise fast_path.SecurityBlocker("reacquisition source package survey malformed")
            length = int(size)
            if len(remaining) < length + 1 or remaining[length:length + 1] != b"\n":
                raise fast_path.SecurityBlocker("reacquisition source package survey truncated")
            source_packages.extend(_package_identities(remaining[:length], current))
            remaining = remaining[length + 1:]
        if remaining:
            raise fast_path.SecurityBlocker("reacquisition source package survey ambiguous")
    return {
        "source_history": tuple(history), "source_packages": tuple(sorted(source_packages)),
        "journal_packages": tuple(sorted(journal_packages)),
        "historical_digest_identities": _retained_package_digests(current), "maintained_stores": MAINTAINED_STORES,
        "unsearched_stores": (), "retained_local_store": "NO_MAINTAINED_RETAINED_STORE",
        "output_scope": "GITIGNORED_WORKSPACE_LOCAL",
        "authoritative_head_publication": _observe_push_survey(observed),
    }


def _require_accepted_main(repository: str, *, expected_main: str | None = None) -> str:
    actions = transport._load_actions_helper()
    try:
        return actions._require_accepted_main_bridge_source(repository, expected_main=expected_main)
    except actions.fast_path.SecurityBlocker as exc:
        # The maintained actions loader has its own concrete helper class.
        # Normalize only that exact boundary, preserving the fail-closed result.
        raise fast_path.SecurityBlocker(str(exc)) from exc


def authenticate_loss(repository: str, delivery_issue: int) -> VerifiedAcquisitionEvidenceLoss:
    """No caller observations, provider selector or package-loss flags."""

    if repository != "SecPal/.github":
        raise fast_path.SecurityBlocker("provider reacquisition is not maintained for this repository")
    accepted_main = _require_accepted_main(repository)
    current = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    issue = _gh_json([f"repos/{repository}/issues/{delivery_issue}"], "delivery issue")
    if issue.get("number") != delivery_issue or issue.get("state") != "open" or "pull_request" in issue:
        raise fast_path.SecurityBlocker("reacquisition delivery issue is not OPEN")
    observed = _observe_timeline(repository, current.lifecycle.pull_request)
    from . import lifecycle_orchestration
    feedback = lifecycle_orchestration._capture_current_stable_feedback(
        repository, current.lifecycle.pull_request, capture_provider_summary=True)
    survey = _observe_package_survey(current, observed)
    admitted = _admit_loss(current, feedback, observed, survey)
    if _observe_timeline(repository, current.lifecycle.pull_request) != observed:
        raise fast_path.SecurityBlocker("reacquisition history changed during loss survey")
    if publication.verify_current_lifecycle_authority(repository, delivery_issue) != current:
        raise fast_path.SecurityBlocker("reacquisition CURRENT changed during loss survey")
    _require_accepted_main(repository, expected_main=accepted_main)
    return admitted


@dataclass(frozen=True)
class VerifiedReacquisitionAuthorization:
    document: dict[str, Any]
    _seal: object
    _digest: str


def _assessment_id(proof: dict[str, Any]) -> str:
    return fast_path.digest_json({"domain": AUTHORIZATION_DOMAIN,
        **{name: proof[name] for name in _BINDING_FIELDS},
        "historical_acquisition_loss_proof_digest": fast_path.digest_json(proof)})


def _authorization_fields(
    proof: VerifiedAcquisitionEvidenceLoss, authorized_at: str, signer_identity: str,
) -> dict[str, Any]:
    require_verified_loss(proof)
    acquisition._timestamp(authorized_at)
    projection = _loss_projection(proof)
    return {
        "schema_version": "1.0", "kind": AUTHORIZATION_KIND,
        "domain": AUTHORIZATION_DOMAIN, "operation": OPERATION,
        **{name: getattr(proof, name) for name in _BINDING_FIELDS},
        "bounded_uses": 1, "review_types": list(proof.review_types),
        "assessment_id": _assessment_id(projection), "loss_proof": projection,
        "loss_proof_digest": proof.proof_digest, "authorized_at": authorized_at,
        "signer_identity": signer_identity,
    }


def verify_authorization(
    value: Any, current: publication.VerifiedLifecyclePublication,
) -> VerifiedReacquisitionAuthorization:
    """Independently verify closed signed authority against protected CURRENT."""

    # Canonical JSON roundtrip avoids aliased caller mutation after verification.
    try:
        document = authority.loads_closed_json(fast_path.canonical_json_bytes(value))
        proof = document["loss_proof"]
        expected = {
            "repository": current.lifecycle.repository,
            "delivery_issue": current.lifecycle.delivery_issue,
            "pull_request": current.lifecycle.pull_request,
            "lifecycle_id": current.lifecycle.lifecycle_id,
            "current_publication_oid": current.publication_oid,
            "current_publication_digest": current.publication_digest,
            "current_authority_digest": current.lifecycle.authority_digest,
            "head_sha": current.lifecycle.head_sha, "tree_sha": current.lifecycle.tree_sha,
            "lifecycle_state": current.lifecycle.state,
        }
        if (
            type(current) is not publication.VerifiedLifecyclePublication
            or set(document) != _AUTHORIZATION_FIELDS
            or document["schema_version"] != "1.0" or document["kind"] != AUTHORIZATION_KIND
            or document["domain"] != AUTHORIZATION_DOMAIN or document["operation"] != OPERATION
            or type(document["bounded_uses"]) is not int or document["bounded_uses"] != 1
            or document["review_types"] != list(fast_path.required_codex_review_types())
            or proof["classification"] != CLASSIFICATION
            or proof["original_first_fallback_validity"] != "UNPROVABLE_FROM_RETAINED_AUTHORITY"
            or document["loss_proof_digest"] != fast_path.digest_json(proof)
            or document["assessment_id"] != _assessment_id(proof)
            or any(document[name] != expected[name] or proof[name] != expected[name] for name in _BINDING_FIELDS)
            or fast_path.canonical_json_bytes(document["lifecycle_state"]) != fast_path.canonical_json_bytes(current.lifecycle.state)
            or document["authorization_digest"] != fast_path.digest_json({k:v for k,v in document.items() if k != "authorization_digest"})
        ):
            raise fast_path.SecurityBlocker("reacquisition authorization scope, chronology or digest changed")
        acquisition._timestamp(document["authorized_at"])
        policy = authority._load_lifecycle_trust_policy(current.lifecycle.repository)
        authority._verify_signature(
            fast_path.canonical_json_bytes({k:v for k,v in document.items() if k not in {"signature", "authorization_digest"}}),
            document["signature"], document["signer_identity"], AUTHORIZATION_DOMAIN,
            policy.publication_signer_identities, authority._policy_signature_verifier(policy))
        _replay_signed_loss(proof, current)
    except (KeyError, TypeError, ValueError, authority.LifecycleAuthorityError) as exc:
        raise fast_path.SecurityBlocker("reacquisition authorization is invalid") from exc
    return VerifiedReacquisitionAuthorization(document, _AUTHORIZATION_TOKEN, fast_path.digest_json(document))


def _replay_signed_loss(
    proof: dict[str, Any], current: publication.VerifiedLifecyclePublication,
) -> VerifiedAcquisitionEvidenceLoss:
    """Recheck semantic closure of signed facts; signature never replaces it."""

    expected_fields = set(VerifiedAcquisitionEvidenceLoss.__dataclass_fields__) - {"proof_digest", "_seal"}
    if set(proof) != expected_fields:
        raise fast_path.SecurityBlocker("signed acquisition loss proof is not closed")
    observed = json.loads(fast_path.canonical_json_bytes(proof["historical_observation"]))
    observed["author"] = tuple(observed["author"])
    for event in observed["events"]:
        if "actor" in event:
            event["actor"] = tuple(event["actor"])
        if "versions" in event:
            event["versions"] = tuple(tuple(v) for v in event["versions"])
    observed["events"] = tuple(observed["events"])
    survey = {**proof["survey"]}
    for field in ("source_packages", "journal_packages", "historical_digest_identities", "maintained_stores", "unsearched_stores"):
        survey[field] = tuple(survey[field])
    survey["source_history"] = tuple(tuple(item) for item in survey["source_history"])
    feedback = fast_path.verify_reviewed_state_evidence(proof["historical_feedback"])
    feedback.provider_summary_body = proof["historical_summary"]
    loss = _admit_loss(current, feedback, observed, survey)
    if fast_path.canonical_json_bytes(_loss_projection(loss)) != fast_path.canonical_json_bytes(proof):
        raise fast_path.SecurityBlocker("signed acquisition loss proof does not independently rederive")
    return loss


def _require_authorization(value: Any) -> dict[str, Any]:
    if (type(value) is not VerifiedReacquisitionAuthorization
            or value._seal is not _AUTHORIZATION_TOKEN
            or value._digest != fast_path.digest_json(value.document)):
        raise fast_path.SecurityBlocker("reacquisition authorization is not verified")
    return value.document


def _server_time(repository: str, pull_request: int) -> str:
    result = publication._run_gh(["api", "--hostname", "github.com", "--include",
        f"repos/{repository}/pulls/{pull_request}"])
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("reacquisition fresh server chronology unavailable")
    try:
        headers, _body = result.stdout.replace(b"\r\n", b"\n").split(b"\n\n", 1)
        dates = [line.split(b":", 1)[1].strip().decode("ascii") for line in headers.splitlines()
                 if line.lower().startswith(b"date:")]
        if len(dates) != 1:
            raise ValueError("ambiguous Date header")
        return parsedate_to_datetime(dates[0]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, UnicodeDecodeError) as exc:
        raise fast_path.SecurityBlocker("reacquisition fresh server chronology malformed") from exc


def issue_authorization(repository: str, delivery_issue: int) -> dict[str, Any]:
    """Issue one exact intent from authenticated accepted-main rules, read-only."""

    from . import lifecycle_execution
    loss = authenticate_loss(repository, delivery_issue)
    policy = authority._load_lifecycle_trust_policy(repository)
    identity, signer = lifecycle_execution._policy_role_signer(
        policy, policy.publication_signer_identities, "provider dispatch publication", allow_routine_default=True)
    fields = _authorization_fields(loss, _server_time(repository, loss.pull_request), identity)
    signed = {**fields, "signature": authority._normalize_signature(
        signer(fast_path.canonical_json_bytes(fields), AUTHORIZATION_DOMAIN), identity)}
    document = {**signed, "authorization_digest": fast_path.digest_json(signed)}
    current = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    verify_authorization(document, current)
    _require_accepted_main(repository)
    return document


def derive_dispatch_keys(
    authorization: VerifiedReacquisitionAuthorization,
    current: publication.VerifiedLifecyclePublication,
) -> tuple[publication.ProviderDispatchKey, ...]:
    document = _require_authorization(authorization)
    verify_authorization(document, current)
    proof = document["loss_proof"]
    keys = []
    for review_type in fast_path.required_codex_review_types():
        requests = [r for r in proof["historical_requests"] if r["review_type"] == review_type]
        if len(requests) != 1:
            raise fast_path.SecurityBlocker("reacquisition original request inventory changed")
        request = requests[0]
        keys.append(publication.ProviderDispatchKey(
            repository=document["repository"], delivery_issue=document["delivery_issue"],
            pull_request=document["pull_request"], lifecycle_id=document["lifecycle_id"],
            current_head_sha=document["head_sha"], current_authority_digest=document["current_authority_digest"],
            current_publication_oid=document["current_publication_oid"], current_publication_digest=document["current_publication_digest"],
            review_type=review_type, assessment_authority_digest=document["assessment_id"],
            original_fallback_comment_node_id=request["node_id"], original_fallback_comment_database_id=request["database_id"],
            original_fallback_body_digest=fast_path.digest_text(acquisition._CANONICAL_TRIGGERS[review_type]),
            original_fallback_actor_node_id=request["actor"][1], original_fallback_actor_database_id=request["actor"][2],
            original_fallback_created_at=request["created_at"]))
    return tuple(keys)


def _provider_result_type(event: dict[str, Any], head: str) -> str | None:
    provider = fast_path.CODEX_REVIEW_PROVIDER
    if event.get("actor") not in ((provider["login"], provider["node_id"], provider["database_id"]),
                                 [provider["login"], provider["node_id"], provider["database_id"]]):
        return None
    body = event.get("body")
    reviewed = f"**Reviewed commit:** `{head[:10]}`"
    if not isinstance(body, str) or body.count(reviewed) != 1:
        return None
    if event["kind"] == "PullRequestReview":
        if event.get("head") != head or event.get("state") != "COMMENTED":
            return None
        return fast_path.codex_review_type(body)
    if event["kind"] == "IssueComment":
        matches = [t for t, text in fast_path.CODEX_NO_FINDING_TEXT.items() if text in body]
        if len(matches) == 1:
            return matches[0]
    return None


def _admit_live_history(
    document: dict[str, Any], observed: dict[str, Any],
    claims: tuple[publication.VerifiedProviderDispatchClaim, ...],
) -> tuple[dict[str, dict[str, Any]], tuple[dict[str, Any], ...]]:
    """Separate the complete signed historical inventory from fresh identities."""

    original = document["loss_proof"]["historical_observation"]
    if fast_path.canonical_json_bytes({k:v for k,v in original.items() if k != "events"}) != fast_path.canonical_json_bytes({k:v for k,v in observed.items() if k != "events"}):
        raise fast_path.SecurityBlocker("reacquisition live delivery/head/Ready source changed")
    before = {e["node_id"]: e for e in original["events"]}
    after = {e["node_id"]: e for e in observed["events"]}
    if len(after) != len(observed["events"]) or not set(before).issubset(after):
        raise fast_path.SecurityBlocker("reacquisition historical source inventory disappeared or duplicated")
    summary = document["loss_proof"]["historical_summary"]
    for identity, event in before.items():
        live = after[identity]
        if event.get("body") == summary:
            # A provider may update its single summary. Complete native content
            # history must still authenticate the signed historical snapshot.
            stable = {k:v for k,v in event.items() if k not in {"body", "updated_at", "versions"}}
            live_stable = {k:v for k,v in live.items() if k not in {"body", "updated_at", "versions"}}
            if (fast_path.canonical_json_bytes(stable) != fast_path.canonical_json_bytes(live_stable)
                    or not any(stamp == event["updated_at"] and body == summary for stamp, body in live["versions"])):
                raise fast_path.SecurityBlocker("reacquisition retained historical summary changed")
        elif fast_path.canonical_json_bytes(event) != fast_path.canonical_json_bytes(live):
            raise fast_path.SecurityBlocker("reacquisition historical request/result/history changed")
    fresh = [e for e in observed["events"] if e["node_id"] not in before]
    requests: dict[str, dict[str, Any]] = {}
    results = []
    authorized_at = acquisition._timestamp(document["authorized_at"])
    for event in fresh:
        types = [t for t, trigger in acquisition._CANONICAL_TRIGGERS.items()
                 if event["kind"] == "IssueComment" and any(body.strip() == trigger for _stamp, body in event["versions"])]
        if types:
            if len(types) != 1:
                raise fast_path.SecurityBlocker("reacquisition request type is ambiguous")
            review_type = types[0]
            eligible_claims = [claim for claim in claims if claim.key.review_type == review_type
                and claim.key.repository == document["repository"] and claim.key.pull_request == document["pull_request"]
                and claim.key.current_head_sha == document["head_sha"]
                and claim.reacquisition_authorization is not None
                and fast_path.canonical_json_bytes(claim.reacquisition_authorization) == fast_path.canonical_json_bytes(document)]
            if (review_type in requests or len(eligible_claims) != 1
                    or event["body"] != acquisition._CANONICAL_TRIGGERS[review_type]
                    or tuple(event["actor"]) != tuple(observed["author"])
                    or event["updated_at"] != event["created_at"]
                    or acquisition._timestamp(event["created_at"]) < authorized_at):
                raise fast_path.SecurityBlocker("reacquisition request is duplicate, unclaimed, edited or substituted")
            requests[review_type] = event
        else:
            review_type = _provider_result_type(event, document["head_sha"])
            if review_type is None or acquisition._timestamp(event["created_at"]) < authorized_at:
                raise fast_path.SecurityBlocker("reacquisition contains an unauthenticated new provider source")
            results.append({"review_type": review_type, **event})
    for result in results:
        request = requests.get(result["review_type"])
        if request is None or acquisition._timestamp(result["created_at"]) <= acquisition._timestamp(request["created_at"]):
            raise fast_path.SecurityBlocker("historical or unrequested result cannot be relabeled fresh")
    return requests, tuple(results)


def _reconcile_request(
    document: dict[str, Any], review_type: str, observed: dict[str, Any],
    claims: tuple[publication.VerifiedProviderDispatchClaim, ...], response_id: int | None,
) -> publication.ProviderDispatchReconciliation:
    requests, _results = _admit_live_history(document, observed, claims)
    request = requests.get(review_type)
    if request is None:
        return publication.ProviderDispatchReconciliation(0, None)
    identity = request["database_id"]
    if response_id is not None and identity != response_id:
        raise fast_path.SecurityBlocker("reacquisition write response differs from complete request history")
    return publication.ProviderDispatchReconciliation(1, identity)


@dataclass(frozen=True)
class ReacquisitionObservation:
    authorization: VerifiedReacquisitionAuthorization
    current: publication.VerifiedLifecyclePublication
    claims: tuple[publication.VerifiedProviderDispatchClaim, ...]
    feedback: fast_path.StableFeedbackState
    timeline: dict[str, Any]
    requests: dict[str, dict[str, Any]]
    results: tuple[dict[str, Any], ...]
    accepted_main_sha: str


def _capture_reacquisition_feedback(repository: str, pull_request: int) -> fast_path.StableFeedbackState:
    helper = transport._load_actions_helper()
    root = Path(helper.__file__).resolve().parents[1]
    gateway = helper.FastPathGateway(root, helper.select_repository(helper.load_registry(None), repository))
    try:
        observed = gateway.observe_provider_acquisition_feedback(repository, pull_request)
    except (helper.fast_path.SecurityBlocker, helper.fast_path.TransientReadFailure) as exc:
        raise fast_path.SecurityBlocker(str(exc)) from exc
    feedback = fast_path.StableFeedbackState.from_payload({"repository": repository,
        "pull_request_number": pull_request, **observed})
    feedback.provider_summary_body = observed.get("provider_summary_body")
    feedback.review_database_ids = observed.get("provider_review_database_ids")
    return feedback


def _authenticate_execution(document: dict[str, Any]) -> ReacquisitionObservation:
    """Reauthenticate every maintained source immediately before dispatch."""

    repository, issue = document["repository"], document["delivery_issue"]
    if repository != "SecPal/.github":
        raise fast_path.SecurityBlocker("provider reacquisition is not maintained for this repository")
    main = _require_accepted_main(repository)
    current, claims = publication.verify_provider_dispatch_claims(repository, issue)
    authorization = verify_authorization(document, current)
    document = authorization.document
    issue_facts = _gh_json([f"repos/{repository}/issues/{issue}"], "delivery issue")
    if issue_facts.get("state") != "open" or issue_facts.get("number") != issue or "pull_request" in issue_facts:
        raise fast_path.SecurityBlocker("reacquisition requires the unchanged OPEN delivery issue")
    observed = _observe_timeline(repository, document["pull_request"])
    survey = _observe_package_survey(current, observed)
    if fast_path.canonical_json_bytes(survey) != fast_path.canonical_json_bytes(document["loss_proof"]["survey"]):
        raise fast_path.SecurityBlocker("reacquisition bounded loss authority changed")
    requests, results = _admit_live_history(document, observed, claims)
    feedback = _capture_reacquisition_feedback(repository, document["pull_request"])
    acquisition._require_feedback_inventory(feedback,
        {e["node_id"]: e for e in observed["events"] if e["kind"] == "IssueComment"},
        {e["node_id"]: e for e in observed["events"] if e["kind"] == "PullRequestReview"})
    # The signed baseline is complete. Original threads and sources cannot be
    # silently removed, edited or resolved during acquisition.
    original_feedback = document["loss_proof"]["historical_feedback"]
    if feedback.feedback["provider_review_requests"] != original_feedback["provider_review_requests"]:
        raise fast_path.SecurityBlocker("reacquisition assessment provider lineage changed")
    threads = {thread["node_id"]: thread for thread in feedback.feedback["threads"]}
    for original in original_feedback["threads"]:
        live = threads.get(original["node_id"])
        if live is None or live["is_resolved"] != original["is_resolved"] or live["is_outdated"] != original["is_outdated"]:
            raise fast_path.SecurityBlocker("reacquisition historical thread inventory/state changed")
        comments = {comment["node_id"]: comment for comment in live["comments"]}
        for comment in original["comments"]:
            if comments.get(comment["node_id"]) != comment:
                raise fast_path.SecurityBlocker("reacquisition historical finding source changed")
    actor = _gh_json(["user"], "authenticated request actor")
    if (actor.get("login"), actor.get("node_id"), actor.get("id")) != tuple(observed["author"]):
        raise fast_path.SecurityBlocker("reacquisition authenticated actor is not the authorized PR author")
    if _observe_timeline(repository, document["pull_request"]) != observed:
        raise fast_path.SecurityBlocker("reacquisition request history changed during authentication")
    if publication.verify_current_lifecycle_authority(repository, issue) != current:
        raise fast_path.SecurityBlocker("reacquisition CURRENT changed during authentication")
    _require_accepted_main(repository, expected_main=main)
    return ReacquisitionObservation(authorization, current, claims, feedback, observed, requests, results, main)


def _terminal_result(observation: ReacquisitionObservation, review_type: str) -> dict[str, Any] | None:
    """Fresh per-type terminality never borrows an old same-head result."""

    document = _require_authorization(observation.authorization)
    request = observation.requests.get(review_type)
    results = [result for result in observation.results if result["review_type"] == review_type]
    if request is None or not results:
        return None
    if len(results) != 1:
        raise fast_path.SecurityBlocker("reacquisition provider result inventory is ambiguous")
    summary = getattr(observation.feedback, "provider_summary_body", None)
    try:
        fast_path.verify_codex_provider_summary(summary, head_sha=document["head_sha"],
            repository=document["repository"], pull_request_number=document["pull_request"])
    except fast_path.SecurityBlocker:
        return None
    label = {"CODE": "Code Review", "SECURITY": "Security Review"}[review_type]
    row = next(line for line in summary.splitlines() if f"**{label}**" in line)
    cells = row.split("|")
    commit = re.fullmatch(r"`([0-9a-f]{7,40})`", cells[3].strip())
    stamps = re.findall(r'datetime="([^"]+)"', cells[2])
    if (commit is None or not document["head_sha"].startswith(commit[1])
            or len(stamps) != 1 or cells[4].strip() != "Manual request"):
        raise fast_path.SecurityBlocker("reacquisition terminal summary does not identify the fresh manual result")
    completed_at = acquisition._result_timestamp(stamps[0])
    if (completed_at <= acquisition._timestamp(request["created_at"])
            or completed_at < acquisition._timestamp(results[0]["created_at"])):
        raise fast_path.SecurityBlocker("reacquisition cannot relabel a historical summary row as fresh")
    if completed_at > acquisition._timestamp(request["created_at"]) + acquisition.PROVIDER_OBSERVATION_WINDOW:
        return None
    return {**results[0], "summary_completed_at": stamps[0], "request_node_id": request["node_id"]}


def _write_request(observation: ReacquisitionObservation, review_type: str, body: str) -> int | None:
    document = _require_authorization(observation.authorization)
    if body != acquisition._CANONICAL_TRIGGERS[review_type]:
        raise fast_path.SecurityBlocker("reacquisition writer body is not canonical")
    # Final native re-read follows the protected ownership check. No source or
    # request can change during the preceding journal observation unnoticed.
    _require_accepted_main(
        document["repository"], expected_main=observation.accepted_main_sha)
    live = _observe_timeline(document["repository"], document["pull_request"])
    if live != observation.timeline:
        raise fast_path.SecurityBlocker("reacquisition native state changed immediately before write")
    try:
        result = publication._run_gh(["api", "--hostname", "github.com",
            f"repos/{document['repository']}/issues/{document['pull_request']}/comments",
            "-X", "POST", "-f", f"body={body}"])
        if result.returncode != 0:
            raise publication.AmbiguousProviderDispatchWrite("reacquisition POST persistence is uncertain")
        response = authority.loads_closed_json(result.stdout)
        identity = authority._require_positive_int(response.get("id"), "reacquisition response comment")
        if response.get("body") != body:
            raise publication.AmbiguousProviderDispatchWrite("reacquisition POST response changed")
        return identity
    except (publication.LifecyclePublicationError, authority.LifecycleAuthorityError, ValueError) as exc:
        raise publication.AmbiguousProviderDispatchWrite("reacquisition POST persistence is uncertain") from exc


def dispatch_next(document: dict[str, Any]) -> dict[str, Any]:
    """Derive the next required type; one claim and at most one POST per call.

    CODE precedes SECURITY. An in-flight request or stranded claim never causes
    another request. Observation of provider completion is a separate read.
    """

    from . import lifecycle_execution
    observation = _authenticate_execution(document)
    verified = observation.authorization
    document = verified.document
    keys = derive_dispatch_keys(verified, observation.current)
    selected = None
    for key in keys:
        if _terminal_result(observation, key.review_type) is not None:
            continue
        if key.review_type in observation.requests:
            return {"status": "PROVIDER_NON_TERMINAL", "review_type": key.review_type, "write_attempts": 0}
        if any(claim.key == key and claim.reacquisition_authorization is not None for claim in observation.claims):
            return {"status": "CLAIM_CONSUMED_WITHOUT_AUTHENTICATED_REQUEST", "review_type": key.review_type, "write_attempts": 0}
        selected = key
        break
    if selected is None:
        return {"status": "FRESH_RESULTS_TERMINAL_CAPTURE_REQUIRED", "write_attempts": 0}
    policy = authority._load_lifecycle_trust_policy(selected.repository)
    identity, signer = lifecycle_execution._policy_role_signer(policy,
        policy.publication_signer_identities, "provider dispatch publication", allow_routine_default=True)
    latest = observation

    def authenticate() -> publication.ProviderDispatchEligibility | publication.ProviderDispatchNoLongerRequired:
        nonlocal latest
        latest = _authenticate_execution(document)
        if _terminal_result(latest, selected.review_type) is not None:
            return publication.ProviderDispatchNoLongerRequired()
        if selected.review_type in latest.requests:
            raise fast_path.SecurityBlocker("reacquisition already has a persisted request")
        return publication.ProviderDispatchEligibility(selected, document["loss_proof_digest"])

    def reconcile(key: publication.ProviderDispatchKey, response_id: int | None) -> publication.ProviderDispatchReconciliation:
        try:
            after = _authenticate_execution(document)
        except (fast_path.SecurityBlocker, publication.LifecyclePublicationError, authority.LifecycleAuthorityError) as exc:
            raise publication.ProviderDispatchHistoryUnavailable("reacquisition request history unavailable") from exc
        return _reconcile_request(document, key.review_type, after.timeline, after.claims, response_id)

    result = publication._execute_provider_dispatch_with_claim(authenticate,
        lambda body: _write_request(latest, selected.review_type, body), reconcile,
        signer_identity=identity, signer=signer, reacquisition_authorization=document)
    return {"status": result.status, "review_type": selected.review_type,
        "request_database_id": result.replacement_comment_database_id,
        "write_attempts": result.write_attempts}


def authenticate_assessment(document: dict[str, Any]) -> dict[str, Any]:
    """One bounded read, complete current feedback, zero caller finding selection."""

    observation = _authenticate_execution(document)
    document = observation.authorization.document
    results = [_terminal_result(observation, t) for t in fast_path.required_codex_review_types()]
    if any(result is None for result in results):
        return {"status": "PROVIDER_NON_TERMINAL", "assessment_id": document["assessment_id"],
            "requests": observation.requests,
            "terminal_review_types": [t for t, result in zip(fast_path.required_codex_review_types(), results) if result is not None],
            "observation_window_seconds": int(acquisition.PROVIDER_OBSERVATION_WINDOW.total_seconds())}
    baseline = fast_path.verify_reviewed_state_evidence(document["loss_proof"]["historical_feedback"])
    before = fast_path._successor_source_inventory(baseline)
    after = fast_path._successor_source_inventory(observation.feedback)
    summary = observation.feedback.provider_summary_body
    summaries = [e for e in observation.timeline["events"] if e.get("body") == summary
                 and e["kind"] == "IssueComment"]
    if len(summaries) != 1:
        raise fast_path.SecurityBlocker("fresh reacquisition summary inventory is ambiguous")
    provider_transport = [{"role": "CODEX_SUMMARY_UPDATE", "kind": "CONVERSATION_COMMENT",
        "node_id": summaries[0]["node_id"], "body": summary}]
    for review_type in fast_path.required_codex_review_types():
        request = observation.requests[review_type]
        provider_transport.append({"role": "CODEX_REVIEW_REQUEST" if review_type == "CODE" else "CODEX_SECURITY_REVIEW_REQUEST",
            "kind": "CONVERSATION_COMMENT", "node_id": request["node_id"], "body": request["body"]})
    for result in results:
        is_review = result["kind"] == "PullRequestReview"
        provider_transport.append({"role": "CODEX_REVIEW" if is_review else
            "CODEX_CODE_REVIEW_RESULT" if result["review_type"] == "CODE" else "CODEX_SECURITY_REVIEW_RESULT",
            "kind": "REVIEW" if is_review else "CONVERSATION_COMMENT",
            "node_id": result["node_id"], "body": result["body"]})
    # Reuse the maintained complete dual-type transport invariant. The existing
    # flag names its transport shape, and grants no continuation authority here.
    fast_path._verify_successor_transport(provider_transport, reviewed_sources=before,
        current_sources=after, resulting_head_sha=document["head_sha"], rejected_candidate=True)
    reviews = {e["node_id"]: e["database_id"] for e in observation.timeline["events"] if e["kind"] == "PullRequestReview"}
    captured = getattr(observation.feedback, "review_database_ids", None)
    if not isinstance(captured, list) or {r["node_id"]: r["database_id"] for r in captured} != reviews or len(captured) != len(reviews):
        raise fast_path.SecurityBlocker("fresh reacquisition review database identities changed")
    original_threads = {t["node_id"] for t in baseline.feedback["threads"]}
    new_reviews = {r["node_id"] for r in results if r["kind"] == "PullRequestReview"}
    findings = []
    for thread in observation.feedback.feedback["threads"]:
        if not thread["comments"]:
            raise fast_path.SecurityBlocker("fresh reacquisition thread lacks its complete finding source")
        first = thread["comments"][0]
        if thread["node_id"] not in original_threads and (
                first.get("review_id") not in new_reviews or first["actor"] != fast_path.CODEX_REVIEW_PROVIDER):
            raise fast_path.SecurityBlocker("fresh reacquisition contains an unaccounted finding source")
        findings.append({"thread_id": thread["node_id"], "finding_id": first["node_id"],
            "parent_review_id": first.get("review_id"), "provider": first["actor"],
            "body_digest": first["body_digest"], "is_resolved": thread["is_resolved"],
            "is_outdated": thread["is_outdated"], "fresh_provider_result": first.get("review_id") in new_reviews})
    assessment = {
        "status": "PROVIDER_REACQUISITION_COMPLETE", "operation": OPERATION,
        "acquisition_kind": "SAME_HEAD_BOUNDED_REACQUISITION",
        "historical_first_fallback_validity": "UNPROVABLE_FROM_RETAINED_AUTHORITY",
        "assessment_id": document["assessment_id"], "authorization": document,
        "current_publication_oid": observation.current.publication_oid,
        "current_publication_digest": observation.current.publication_digest,
        "head_sha": document["head_sha"], "tree_sha": document["tree_sha"],
        "lifecycle_state": observation.current.lifecycle.state,
        "claims": [{"publication_oid": c.publication_oid, "publication_digest": c.publication_digest,
            "claim_id": c.claim_id, "review_type": c.key.review_type}
            for c in observation.claims if c.reacquisition_authorization is not None],
        "requests": observation.requests, "provider_results": results,
        "review_database_ids": captured, "stable_feedback": observation.feedback.to_dict(),
        "finding_inventory": findings, "provider_source_hidden": False,
        "classification_boundary": "COMPLETE_ORDINARY_FINDING_CLASSIFICATION_REQUIRED",
    }
    return {**assessment, "assessment_digest": fast_path.digest_json(assessment)}


@dataclass(frozen=True)
class _FreshAcquisitionSeal:
    token: object
    digest: str


@dataclass(frozen=True)
class VerifiedFreshProviderAcquisitions:
    """Ephemeral verifier evidence, distinct from historical first fallbacks."""

    canonical_assessment: dict[str, Any]
    _seal: _FreshAcquisitionSeal


def _seal_fresh_assessment(assessment: dict[str, Any]) -> VerifiedFreshProviderAcquisitions:
    if (assessment.get("status") != "PROVIDER_REACQUISITION_COMPLETE"
            or assessment.get("operation") != OPERATION
            or assessment.get("acquisition_kind") != "SAME_HEAD_BOUNDED_REACQUISITION"
            or assessment.get("assessment_digest") != fast_path.digest_json({k:v for k,v in assessment.items() if k != "assessment_digest"})):
        raise fast_path.SecurityBlocker("fresh provider acquisition assessment is incomplete")
    document = authority.loads_closed_json(fast_path.canonical_json_bytes(assessment))
    return VerifiedFreshProviderAcquisitions(document,
        _FreshAcquisitionSeal(_FRESH_ACQUISITION_TOKEN, fast_path.digest_json(document)))


def require_verified_fresh_acquisitions(
    value: Any, current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
) -> VerifiedFreshProviderAcquisitions:
    if (type(value) is not VerifiedFreshProviderAcquisitions
            or type(value._seal) is not _FreshAcquisitionSeal
            or value._seal.token is not _FRESH_ACQUISITION_TOKEN
            or value._seal.digest != fast_path.digest_json(value.canonical_assessment)
            or value.canonical_assessment["stable_feedback"] != feedback.to_dict()
            or value.canonical_assessment["current_publication_oid"] != current.publication_oid
            or value.canonical_assessment["current_publication_digest"] != current.publication_digest):
        raise fast_path.SecurityBlocker("fresh provider acquisition is not independently authenticated")
    verify_authorization(value.canonical_assessment["authorization"], current)
    return value


def authenticate_fresh_provider_acquisitions(
    current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
) -> VerifiedFreshProviderAcquisitions:
    """Derive the sole signed intent from protected claims; accept no selector."""

    if type(current) is not publication.VerifiedLifecyclePublication:
        raise fast_path.SecurityBlocker("fresh provider acquisition requires protected CURRENT")
    live, claims = publication.verify_provider_dispatch_claims(
        current.lifecycle.repository, current.lifecycle.delivery_issue)
    if live != current:
        raise fast_path.SecurityBlocker("fresh provider acquisition CURRENT changed")
    authorizations = {fast_path.canonical_json_bytes(c.reacquisition_authorization)
        for c in claims if c.reacquisition_authorization is not None
        and c.key.current_publication_oid == current.publication_oid
        and c.key.current_head_sha == current.lifecycle.head_sha}
    if len(authorizations) != 1:
        raise fast_path.SecurityBlocker("fresh provider acquisition has no unique protected authorization")
    document = authority.loads_closed_json(next(iter(authorizations)))
    sealed = _seal_fresh_assessment(authenticate_assessment(document))
    return require_verified_fresh_acquisitions(sealed, current, feedback)
