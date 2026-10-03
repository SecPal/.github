# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only authentication of persisted first post-Ready provider fallbacks.

Observation, normalization and admission are separate. This owner implements
no replacement classification, dispatch, claim, writer or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any

from . import fast_path
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication

PROVIDER_OBSERVATION_WINDOW = timedelta(minutes=30)
_CANONICAL_TRIGGERS = dict(publication.PROVIDER_DISPATCH_TRIGGERS)
_ACQUISITION_TOKEN = object()
_QUERY = """query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    nameWithOwner
    pullRequest(number:$number) {
      number state isDraft headRefOid headRefName
      author { __typename login ... on User { id databaseId } ... on Bot { id databaseId } }
      timelineItems(first:100, itemTypes:[READY_FOR_REVIEW_EVENT,
        CONVERT_TO_DRAFT_EVENT,PULL_REQUEST_COMMIT,HEAD_REF_FORCE_PUSHED_EVENT,
        HEAD_REF_DELETED_EVENT,HEAD_REF_RESTORED_EVENT,ISSUE_COMMENT,PULL_REQUEST_REVIEW]) {
        nodes {
          __typename
          ... on ReadyForReviewEvent { id createdAt actor {
            __typename login ... on User { id databaseId } ... on Bot { id databaseId }
          } }
          ... on ConvertToDraftEvent { id createdAt }
          ... on HeadRefDeletedEvent { id createdAt }
          ... on HeadRefRestoredEvent { id createdAt }
          ... on HeadRefForcePushedEvent { id createdAt beforeCommit { oid } afterCommit { oid } }
          ... on PullRequestCommit { id commit { oid committedDate } }
          ... on IssueComment { id databaseId body createdAt updatedAt
            userContentEdits(first:100) { nodes { id editedAt deletedAt diff editor {
              __typename login ... on User { id databaseId } ... on Bot { id databaseId }
            } } pageInfo { hasNextPage } }
            author {
            __typename login ... on User { id databaseId } ... on Bot { id databaseId }
          } }
          ... on PullRequestReview { id databaseId body submittedAt state commit { oid } author {
            __typename login ... on User { id databaseId } ... on Bot { id databaseId }
          } }
        }
        pageInfo { hasNextPage }
      }
    }
  }
}"""


@dataclass(frozen=True)
class FirstFallbackAcquisition:
    review_type: str
    request_node_id: str
    request_database_id: int
    request_actor: tuple[str, str, int]
    request_created_at: str
    canonical_trigger_digest: str
    acquisition_kind: str = "BOUNDED_POST_READY_FIRST_FALLBACK"


@dataclass(frozen=True)
class _AcquisitionSeal:
    token: object
    digest: str


@dataclass(frozen=True)
class VerifiedFirstFallbackAcquisitions:
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    current_publication_oid: str
    current_publication_digest: str
    current_authority_digest: str
    assessment_head: str
    feedback_state_digest: str
    head_publication: tuple[tuple[str, Any], ...]
    acquisitions: tuple[FirstFallbackAcquisition, ...]
    # Raw bodies are ephemeral observations, never a new Stable Feedback field.
    conversation_bodies: tuple[tuple[str, str], ...]
    review_bodies: tuple[tuple[str, str], ...]
    review_database_ids: tuple[tuple[str, int], ...]
    _seal: _AcquisitionSeal | None


def _projection(value: VerifiedFirstFallbackAcquisitions) -> dict[str, Any]:
    return {
        key: [vars(item) for item in value.acquisitions] if key == "acquisitions"
        else getattr(value, key)
        for key in value.__dataclass_fields__ if key != "_seal"
    }


def require_verified_acquisitions(
    value: Any, feedback: fast_path.StableFeedbackState,
) -> VerifiedFirstFallbackAcquisitions:
    """Reject caller-authored, altered, cross-head or subset feedback facts."""

    if (
        type(value) is not VerifiedFirstFallbackAcquisitions
        or type(value._seal) is not _AcquisitionSeal
        or value._seal.token is not _ACQUISITION_TOKEN
        or value._seal.digest != fast_path.digest_json(_projection(value))
        or value.repository != feedback.repository
        or value.pull_request != feedback.pull_request_number
        or value.assessment_head != feedback.head_sha
        or value.feedback_state_digest != feedback.state_digest
        or tuple(item.review_type for item in value.acquisitions) != ("CODE", "SECURITY")
    ):
        raise fast_path.SecurityBlocker("first fallback acquisition is not independently authenticated")
    return value


def _observe(repository: str, pull_request: int) -> dict[str, Any]:
    """One complete bounded live timeline; truncation grants no authority."""

    owner, name = repository.split("/", 1)
    result = publication._run_gh([
        "api", "--hostname", "github.com", "graphql", "-f", f"query={_QUERY}",
        "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"number={pull_request}",
    ])
    if result.returncode != 0:
        raise fast_path.SecurityBlocker("first fallback timeline observation is unavailable")
    try:
        raw = json.loads(result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
    except (ValueError, UnicodeDecodeError) as exc:
        raise fast_path.SecurityBlocker("first fallback timeline observation is malformed") from exc
    observed = _normalize_observation(raw)
    observed["head_publication"] = _observe_head_publication(observed)
    return observed


def _select_head_publication(events: Any, observed: dict[str, Any]) -> dict[str, Any] | None:
    """A positive server-created PushEvent, never intrinsic commit metadata."""

    if not isinstance(events, list) or len(events) > 100:
        raise fast_path.SecurityBlocker("first fallback push observation is incomplete")
    matches = []
    try:
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "PushEvent":
                continue
            payload = event["payload"]
            if payload.get("ref") != "refs/heads/" + observed["head_ref"] or payload.get("head") != observed["head"]:
                continue
            actor, repo = event["actor"], event["repo"]
            if (
                repo["name"] != observed["repository"]
                or authority._require_positive_int(repo["id"], "push repository") != payload["repository_id"]
                or (actor["login"], actor["id"]) != (observed["author"][0], observed["author"][2])
            ):
                raise fast_path.SecurityBlocker("first fallback push identity was substituted")
            event_id = event["id"]
            if not isinstance(event_id, str) or not event_id.isdecimal() or int(event_id) < 1:
                raise fast_path.SecurityBlocker("first fallback push event identity is invalid")
            _timestamp(event["created_at"])
            before = authority._require_oid(payload["before"], "push predecessor")
            if before == observed["head"]:
                raise fast_path.SecurityBlocker("first fallback push did not publish a head")
            matches.append({"event_id": event_id, "push_id": authority._require_positive_int(payload["push_id"], "push identity"), "head": observed["head"], "before": before, "ref": payload["ref"], "created_at": event["created_at"]})
    except (KeyError, TypeError, ValueError, authority.LifecycleAuthorityError) as exc:
        raise fast_path.SecurityBlocker("first fallback push observation is malformed") from exc
    if len(matches) > 1:
        raise fast_path.SecurityBlocker("first fallback head publication is ambiguous")
    return matches[0] if matches else None


def _observe_head_publication(observed: dict[str, Any]) -> dict[str, Any]:
    """Find one positive immutable event within GitHub's bounded event feed.

    This is no proof of absent repository activity. Missing/delayed/expired
    evidence fails closed; native PR chronology separately excludes head reuse.
    """

    for page in range(1, 4):
        result = publication._run_gh(["api", "--hostname", "github.com", f"repos/{observed['repository']}/events?per_page=100&page={page}"])
        if result.returncode != 0:
            raise fast_path.SecurityBlocker("first fallback head publication is unavailable")
        try:
            events = json.loads(result.stdout, object_pairs_hook=publication._reject_duplicate_pairs)
        except (ValueError, UnicodeDecodeError) as exc:
            raise fast_path.SecurityBlocker("first fallback push observation is malformed") from exc
        selected = _select_head_publication(events, observed)
        if selected is not None:
            return selected
        if len(events) < 100:
            break
    raise fast_path.SecurityBlocker("first fallback has no observable current-head publication")


def _comment_versions(node: dict[str, Any], actor: tuple[str, str, int]) -> tuple[tuple[str, str], ...]:
    """Retained native content snapshots prevent edited-request budget erasure."""

    history = node["userContentEdits"]
    edits = history["nodes"]
    if history["pageInfo"]["hasNextPage"] is not False or not isinstance(edits, list) or len(edits) > 100:
        raise fast_path.SecurityBlocker("first fallback content history is incomplete")
    if not edits:
        if node["createdAt"] != node["updatedAt"]:
            raise fast_path.SecurityBlocker("first fallback edited content history is missing")
        return ((node["createdAt"], node["body"]),)
    versions = []
    seen = set()
    for edit in edits:
        identity = authority._require_identity(edit["id"], "content edit")
        if identity in seen or edit["deletedAt"] is not None or _actor(edit["editor"]) != actor:
            raise fast_path.SecurityBlocker("first fallback content history is deleted or substituted")
        seen.add(identity)
        _timestamp(edit["editedAt"])
        body = edit["diff"]
        if not isinstance(body, str) or len(body.encode("utf-8")) > 64 * 1024:
            raise fast_path.SecurityBlocker("first fallback historical content is unavailable")
        versions.append((edit["editedAt"], body))
    versions.sort()
    if (
        versions[0][0] != node["createdAt"]
        or versions[-1] != (node["updatedAt"], node["body"])
        or len({stamp for stamp, _body in versions}) != len(versions)
    ):
        raise fast_path.SecurityBlocker("first fallback content chronology is ambiguous")
    return tuple(versions)


def _timestamp(value: Any) -> datetime:
    fast_path._require_github_timestamp(value, "first fallback chronology")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _result_timestamp(value: str) -> datetime:
    """Preserve fractional seconds emitted by canonical Codex result rows."""

    whole_seconds = re.sub(r"\.[0-9]{1,6}Z$", "Z", value)
    _timestamp(whole_seconds)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _actor(value: Any) -> tuple[str, str, int]:
    if not isinstance(value, dict) or value.get("__typename") not in {"User", "Bot"}:
        raise fast_path.SecurityBlocker("first fallback actor is incomplete")
    return (
        authority._require_github_login(value.get("login"), "first fallback actor"),
        authority._require_identity(value.get("id"), "first fallback actor node"),
        authority._require_positive_int(value.get("databaseId"), "first fallback actor database ID"),
    )


def _normalize_observation(raw: Any) -> dict[str, Any]:
    """Normalize the provider's actual closed timeline representation, purely."""

    try:
        if not isinstance(raw, dict) or raw.get("errors"):
            raise fast_path.SecurityBlocker("first fallback timeline is incomplete")
        repo = raw["data"]["repository"]
        pull = repo["pullRequest"]
        connection = pull["timelineItems"]
        nodes = connection["nodes"]
        if connection["pageInfo"]["hasNextPage"] is not False or not isinstance(nodes, list) or len(nodes) > 100:
            raise fast_path.SecurityBlocker("first fallback timeline exceeds the complete 100-event bound")
        author = _actor(pull["author"])
        if pull["author"]["__typename"] != "User":
            raise fast_path.SecurityBlocker("first fallback author is not an authorized user")
        events = []
        seen = set()
        database_ids = set()
        for node in nodes:
            kind = node["__typename"]
            node_id = authority._require_identity(node["id"], "first fallback timeline node")
            if node_id in seen:
                raise fast_path.SecurityBlocker("first fallback timeline repeats an identity")
            seen.add(node_id)
            if kind == "PullRequestCommit":
                stamp = node["commit"]["committedDate"]
                event = {"kind": "COMMIT", "node_id": node_id, "head": authority._require_oid(node["commit"]["oid"], "timeline head")}
            elif kind in {"ReadyForReviewEvent", "ConvertToDraftEvent", "HeadRefForcePushedEvent", "HeadRefDeletedEvent", "HeadRefRestoredEvent"}:
                stamp = node["createdAt"]
                event = {"kind": kind, "node_id": node_id}
                if kind == "ReadyForReviewEvent":
                    event["actor"] = _actor(node["actor"])
            elif kind in {"IssueComment", "PullRequestReview"}:
                database_id = authority._require_positive_int(node["databaseId"], "first fallback source database ID")
                if (kind, database_id) in database_ids:
                    raise fast_path.SecurityBlocker("first fallback timeline substitutes a database identity")
                database_ids.add((kind, database_id))
                body = node["body"]
                if not isinstance(body, str) or len(body.encode("utf-8")) > 64 * 1024:
                    raise fast_path.SecurityBlocker("first fallback source body is invalid")
                stamp = node["createdAt"] if kind == "IssueComment" else node["submittedAt"]
                event = {"kind": kind, "node_id": node_id, "database_id": database_id, "actor": _actor(node["author"]), "body": body}
                if kind == "IssueComment":
                    _timestamp(node["updatedAt"])
                    event["updated_at"] = node["updatedAt"]
                    event["versions"] = _comment_versions(node, event["actor"])
                else:
                    event.update(head=authority._require_oid(node["commit"]["oid"], "review head"), state=node["state"])
            else:
                raise fast_path.SecurityBlocker("first fallback timeline has an unknown event")
            _timestamp(stamp)
            event["created_at"] = stamp
            events.append(event)
        return {
            "repository": repo["nameWithOwner"], "pull_request": pull["number"],
            "state": pull["state"], "draft": pull["isDraft"], "head": pull["headRefOid"],
            "author": author, "head_ref": authority._require_identity(pull["headRefName"], "PR head ref"), "events": tuple(events),
        }
    except (KeyError, TypeError, ValueError, authority.LifecycleAuthorityError) as exc:
        raise fast_path.SecurityBlocker("first fallback timeline is malformed") from exc


def _admit(
    current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
    observed: dict[str, Any],
    review_types: tuple[str, ...] = ("CODE", "SECURITY"),
) -> VerifiedFirstFallbackAcquisitions:
    """Derive both first acquisitions from CURRENT and complete live facts."""

    lifecycle = current.lifecycle
    state = authority._validate_state(lifecycle.state)
    if (
        observed["repository"] != lifecycle.repository
        or observed["pull_request"] != lifecycle.pull_request
        or observed["state"] != "OPEN" or observed["draft"] is not False
        or observed["head"] != lifecycle.head_sha
        or feedback.repository != lifecycle.repository
        or feedback.pull_request_number != lifecycle.pull_request
        or feedback.head_sha != lifecycle.head_sha or feedback.pr_state != "OPEN"
        or state["ready"] is not True or state["draft"] is not False
        or state["unrestricted_review_count"] != 1 or state["ready_transition_count"] != 1
        or state["remediation_cycle_count"] != 1
        or state["cycle_3_absent"] is not True
        or state["exceptional_recovery_count"] != 0 or state["exceptional_continuation_count"] != 0
    ):
        raise fast_path.SecurityBlocker("first fallback does not bind ordinary Ready CURRENT")
    events = observed["events"]
    ready = [e for e in events if e["kind"] == "ReadyForReviewEvent"]
    if len(ready) != 1 or ready[0]["actor"] != observed["author"] or any(e["kind"] in {"ConvertToDraftEvent", "HeadRefForcePushedEvent", "HeadRefDeletedEvent", "HeadRefRestoredEvent"} for e in events):
        raise fast_path.SecurityBlocker("first fallback Ready chronology is ambiguous")
    ready_at = _timestamp(ready[0]["created_at"])
    commits = [event for event in events if event["kind"] == "COMMIT"]
    if not commits or commits[-1]["head"] != lifecycle.head_sha:
        raise fast_path.SecurityBlocker("first fallback timeline does not end at CURRENT head")
    stamps = [_timestamp(event["created_at"]) for event in events]
    if stamps != sorted(stamps):
        raise fast_path.SecurityBlocker("first fallback event chronology is ambiguous")
    comments = {e["node_id"]: e for e in events if e["kind"] == "IssueComment"}
    reviews = {e["node_id"]: e for e in events if e["kind"] == "PullRequestReview"}
    for category, observed_sources in (("conversation_comments", comments), ("reviews", reviews)):
        sources = feedback.feedback[category]
        if set(observed_sources) != {s["node_id"] for s in sources}:
            raise fast_path.SecurityBlocker("first fallback complete feedback source inventory changed")
        for source in sources:
            event = observed_sources[source["node_id"]]
            actor = source["actor"]
            if event["actor"] != (actor["login"], actor["node_id"], actor["database_id"]) or fast_path.digest_text(event["body"]) != source["body_digest"]:
                raise fast_path.SecurityBlocker("first fallback feedback source was substituted")
            if category == "conversation_comments" and event["updated_at"] != source["updated_at"]:
                raise fast_path.SecurityBlocker("first fallback comment chronology changed")
            if category == "reviews" and (event["head"] != source["commit_oid"] or event["state"] != source["state"] or event["created_at"] != source["submitted_at"]):
                raise fast_path.SecurityBlocker("first fallback review chronology changed")
    head_publication = observed.get("head_publication")
    if (
        not isinstance(head_publication, dict)
        or head_publication.get("head") != lifecycle.head_sha
        or head_publication.get("ref") != "refs/heads/" + observed["head_ref"]
    ):
        raise fast_path.SecurityBlocker("first fallback has no authenticated head publication")
    head_visible_at = _timestamp(head_publication["created_at"])
    acquisitions = []
    for review_type in review_types:
        trigger = _CANONICAL_TRIGGERS[review_type]
        # Trim only to recognize and reject edited/noncanonical trigger variants.
        requests = [e for e in comments.values() if any(body.strip() == trigger for _stamp, body in e["versions"])]
        if len(requests) != 1:
            raise fast_path.SecurityBlocker("first fallback request is missing or duplicated")
        request = requests[0]
        requested_at = _timestamp(request["created_at"])
        request_position = next(i for i, event in enumerate(events) if event["node_id"] == request["node_id"])
        if (
            events.index(ready[0]) >= request_position
            or any(event["kind"] == "COMMIT" for event in events[request_position + 1:])
        ):
            raise fast_path.SecurityBlocker("first fallback request belongs to another head or Ready assessment")
        preceding_head = None
        head_at = None
        for event in events:
            at = _timestamp(event["created_at"])
            if event["node_id"] == request["node_id"]:
                break
            if event["kind"] == "COMMIT":
                preceding_head, head_at = event["head"], at
        if (
            request["body"] != trigger or request["actor"] != observed["author"]
            or request["updated_at"] != request["created_at"]
            or preceding_head != lifecycle.head_sha or head_at is None
            or requested_at < max(ready_at, head_visible_at) + PROVIDER_OBSERVATION_WINDOW
        ):
            raise fast_path.SecurityBlocker("first fallback was not lawfully acquired after the observation window")
        codex = fast_path.CODEX_REVIEW_PROVIDER
        provider = (codex["login"], codex["node_id"], codex["database_id"])
        for event in events:
            if event.get("actor") != provider:
                continue
            # Observable exact-head results before the request disprove startup
            # absence. Updated summaries cannot reconstruct lost historical rows.
            if event["kind"] == "PullRequestReview" and event["head"] == lifecycle.head_sha:
                is_security = event["body"].lstrip().startswith("### 🛡️ Codex Security Review")
                if (review_type == "SECURITY") == is_security and _timestamp(event["created_at"]) <= requested_at:
                    raise fast_path.SecurityBlocker("first fallback follows an existing exact-head provider review")
            if event["kind"] == "IssueComment" and f"**Reviewed commit:** `{lifecycle.head_sha[:10]}`" in event["body"]:
                is_security = event["body"].lstrip().startswith("### 🛡️ Codex Security Review")
                if (review_type == "SECURITY") == is_security and _timestamp(event["created_at"]) <= requested_at:
                    raise fast_path.SecurityBlocker("first fallback follows an existing exact-head provider result")
            if event["kind"] == "IssueComment":
                label = "Code Review" if review_type == "CODE" else "Security Review"
                for version_at, body in event["versions"]:
                    if fast_path.CODEX_REVIEW_SUMMARY_MARKER not in body:
                        continue
                    rows = [line for line in body.splitlines() if f"**{label}**" in line]
                    if not rows:
                        continue
                    if len(rows) != 1:
                        raise fast_path.SecurityBlocker("first fallback historical summary is ambiguous")
                    cells = rows[0].split("|")
                    if len(cells) != 6:
                        raise fast_path.SecurityBlocker("first fallback historical result row is malformed")
                    commit = re.fullmatch(r"`([0-9a-f]{7,40})`", cells[3].strip())
                    if commit is None or not lifecycle.head_sha.startswith(commit[1]):
                        continue
                    result_times = re.findall(r'datetime="([^"]+)"', cells[2])
                    if (
                        _timestamp(version_at) <= requested_at
                        or len(result_times) > 1
                        or result_times and _result_timestamp(result_times[0]).replace(microsecond=0) <= requested_at
                    ):
                        raise fast_path.SecurityBlocker("first fallback follows observable exact-head provider startup")
        acquisitions.append(FirstFallbackAcquisition(
            review_type, request["node_id"], request["database_id"], request["actor"],
            request["created_at"], fast_path.digest_text(trigger),
        ))
    provisional = VerifiedFirstFallbackAcquisitions(
        lifecycle.repository, lifecycle.delivery_issue, lifecycle.pull_request,
        lifecycle.lifecycle_id, current.publication_oid, current.publication_digest,
        lifecycle.authority_digest, lifecycle.head_sha, feedback.state_digest,
        tuple(sorted(head_publication.items())), tuple(acquisitions), tuple(sorted((k, v["body"]) for k, v in comments.items())),
        tuple(sorted((k, v["body"]) for k, v in reviews.items())),
        tuple(sorted((k, v["database_id"]) for k, v in reviews.items())), None,
    )
    return VerifiedFirstFallbackAcquisitions(**{
        **vars(provisional), "_seal": _AcquisitionSeal(_ACQUISITION_TOKEN, fast_path.digest_json(_projection(provisional))),
    })


def _authenticate(
    current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
    review_types: tuple[str, ...],
) -> VerifiedFirstFallbackAcquisitions:
    """Reauthenticate protected CURRENT and live feedback; perform zero writes."""

    if type(current) is not publication.VerifiedLifecyclePublication:
        raise fast_path.SecurityBlocker("first fallback requires protected CURRENT")
    # Import lazily to reuse the complete maintained feedback reader without a
    # module import cycle. No candidate-provided observer or policy is accepted.
    from . import lifecycle_orchestration

    first = publication.verify_current_lifecycle_authority(current.lifecycle.repository, current.lifecycle.delivery_issue)
    if first != current:
        raise fast_path.SecurityBlocker("first fallback CURRENT changed")
    observed = _observe(current.lifecycle.repository, current.lifecycle.pull_request)
    live = lifecycle_orchestration._capture_current_stable_feedback(current.lifecycle.repository, current.lifecycle.pull_request, capture_provider_summary=True)
    if live.to_dict() != feedback.to_dict():
        raise fast_path.SecurityBlocker("first fallback live feedback differs from the complete assessment")
    admitted = _admit(current, feedback, observed, review_types)
    if _observe(current.lifecycle.repository, current.lifecycle.pull_request) != observed:
        raise fast_path.SecurityBlocker("first fallback live chronology changed")
    if publication.verify_current_lifecycle_authority(current.lifecycle.repository, current.lifecycle.delivery_issue) != current:
        raise fast_path.SecurityBlocker("first fallback CURRENT changed")
    return admitted


def authenticate_first_fallback_acquisition(
    current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
    review_type: str,
) -> VerifiedFirstFallbackAcquisitions:
    """Authenticate one exact review type without selecting its request identity."""

    if review_type not in _CANONICAL_TRIGGERS:
        raise fast_path.SecurityBlocker("first fallback review type is invalid")
    return _authenticate(current, feedback, (review_type,))


def authenticate_first_fallback_acquisitions(
    current: publication.VerifiedLifecyclePublication,
    feedback: fast_path.StableFeedbackState,
) -> VerifiedFirstFallbackAcquisitions:
    """Authenticate both first acquisitions required for Codex-only growth."""

    return _authenticate(current, feedback, ("CODE", "SECURITY"))
