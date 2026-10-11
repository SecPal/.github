# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ephemeral admission for one persisted, unacknowledged provider fallback.

The fixed live consumer authenticates complete provider evidence and CURRENT.
Only the maintained protected claim executor may invoke its request writer.
Provider dispatch never advances a lifecycle or consumes review authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from . import bootstrap_source_admission, fast_path, lifecycle_authority
from . import lifecycle_execution, lifecycle_publication as publication
from . import provider_acquisition


PROVIDER_OBSERVATION_WINDOW = provider_acquisition.PROVIDER_OBSERVATION_WINDOW
TRIGGERS = publication.PROVIDER_DISPATCH_TRIGGERS
PROVIDER = "chatgpt-codex-connector"
OID = re.compile(r"[0-9a-f]{40}\Z")


class ReplacementBlocked(ValueError):
    """The closed replacement preconditions are not all proven."""


class ProviderAcknowledged(ReplacementBlocked):
    """A provider acknowledgement cancels the need for a replacement."""


@dataclass(frozen=True)
class ReplacementEligibility:
    dispatch_key: publication.ProviderDispatchKey
    request_actor: tuple[str, str, int]


def _blocked(reason: str) -> None:
    raise ReplacementBlocked(reason)


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        _blocked("provider chronology timestamp is unavailable")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _blocked("provider chronology timestamp is malformed")
    if result.tzinfo is None:
        _blocked("provider chronology timestamp has no timezone")
    return result.astimezone(timezone.utc)


def _actor(value: Any) -> tuple[str, str, int]:
    if not isinstance(value, Mapping):
        _blocked("stable actor identity is unavailable")
    try:
        normalized = fast_path._actor({
            "login": value.get("login"),
            "node_id": value.get("id", value.get("node_id")),
            "database_id": value.get("databaseId", value.get("database_id")),
        }, "provider fallback")
    except fast_path.SecurityBlocker as exc:
        raise ReplacementBlocked(str(exc)) from exc
    return normalized["login"], normalized["node_id"], normalized["database_id"]


def _provider(value: Any) -> bool:
    actor = _actor(value)
    expected = fast_path.CODEX_REVIEW_PROVIDER
    if actor[1:] == (expected["node_id"], expected["database_id"]):
        return True
    if actor[0].removesuffix("[bot]") == PROVIDER:
        _blocked("provider stable actor identity changed")
    return False


def _nodes(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        if value.get("pageInfo", {}).get("hasNextPage") is not False:
            _blocked(f"{label} evidence is incomplete")
        value = value.get("nodes")
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        _blocked(f"{label} evidence is malformed")
    return value


def _type_from_provider_body(body: Any) -> str | None:
    return fast_path.codex_review_type(body)


def _summary_rows(
    body: str, repository: str, pull_request: int,
) -> tuple[dict[str, tuple[str, str]], dict[str, Any]]:
    if "<!-- codex-pull-request-review-summary -->" not in body:
        _blocked("provider summary marker is unavailable")
    metadata = fast_path.CODEX_REVIEW_STATUS.findall(body)
    if len(metadata) != 1:
        _blocked("provider summary metadata is indeterminate")
    try:
        status = json.loads(metadata[0], object_pairs_hook=publication._reject_duplicate_pairs)
    except (json.JSONDecodeError, ValueError):
        _blocked("provider summary metadata is malformed")
    if (
        not isinstance(status, dict)
        or status.get("repository") != repository
        or status.get("pullRequestNumber") != pull_request
        or not isinstance(status.get("headSha"), str)
        or not OID.fullmatch(status["headSha"])
        or status.get("status") != "completed"
    ):
        _blocked("provider summary identity is invalid")
    try:
        fast_path.verify_codex_provider_summary(
            body, head_sha=status["headSha"], repository=repository,
            pull_request_number=pull_request,
        )
    except fast_path.SecurityBlocker as exc:
        raise ReplacementBlocked(str(exc)) from exc
    result: dict[str, tuple[str, str]] = {}
    for review_type, label in (("CODE", "Code Review"), ("SECURITY", "Security Review")):
        rows = [line for line in body.splitlines() if f"**{label}**" in line]
        if len(rows) != 1:
            _blocked("provider summary review row is indeterminate")
        cells = rows[0].split("|")
        if len(cells) < 5:
            _blocked("provider summary review row is malformed")
        result[review_type] = (cells[2].strip(), cells[3].strip())
    return result, status


def classify(
    observed: Mapping[str, Any], review_type: str, now: datetime,
) -> ReplacementEligibility:
    """Classify complete acquired facts; never accept a selected comment ID."""

    if review_type not in TRIGGERS:
        _blocked("provider review type is unsupported")
    if not isinstance(now, datetime) or now.tzinfo is None:
        _blocked("observation time is unavailable")
    now = now.astimezone(timezone.utc)
    if not isinstance(observed, Mapping):
        _blocked("provider observation is malformed")
    lifecycle = observed.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        _blocked("authenticated lifecycle is unavailable")
    state = lifecycle.get("state")
    if not isinstance(state, Mapping):
        _blocked("authenticated lifecycle state is unavailable")
    repository = observed.get("repository")
    delivery_issue = observed.get("delivery_issue")
    pull_request = observed.get("pull_request")
    head = observed.get("head_sha")
    lifecycle_id = lifecycle.get("lifecycle_id")
    authority_digest = lifecycle.get("authority_digest")
    publication_oid = lifecycle.get("publication_oid")
    publication_digest = lifecycle.get("publication_digest")
    if (
        not isinstance(repository, str) or not repository
        or type(delivery_issue) is not int or delivery_issue <= 0
        or type(pull_request) is not int or pull_request <= 0
        or not isinstance(head, str) or not OID.fullmatch(head)
        or not isinstance(lifecycle_id, str) or not lifecycle_id
        or not isinstance(authority_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", authority_digest)
        or not isinstance(publication_oid, str) or not OID.fullmatch(publication_oid)
        or not isinstance(publication_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", publication_digest)
        or lifecycle.get("repository") != repository
        or lifecycle.get("delivery_issue") != delivery_issue
        or lifecycle.get("pull_request") != pull_request
        or lifecycle.get("head_sha") != head
        or observed.get("pr_state") != "OPEN"
        or observed.get("is_draft") is not False
        or state.get("ready") is not True
        or state.get("ready_transition_count") != 1
        or state.get("cycle_3_absent") is not True
        or state.get("unrestricted_review_count") != 1
        or type(state.get("unrestricted_review_count")) is not int
    ):
        _blocked("delivery or existing assessment identity changed")
    actor = _actor(observed.get("actor"))
    bundle = lifecycle.get("bundle")
    if not isinstance(bundle, Mapping):
        _blocked("authenticated assessment history is unavailable")
    try:
        assessment_digest = publication.provider_dispatch_assessment_authority(
            bundle, head_sha=head, pull_request=pull_request,
        )
    except publication.LifecyclePublicationError as exc:
        raise ReplacementBlocked(str(exc)) from exc

    timeline = observed.get("timeline")
    if not isinstance(timeline, list) or any(not isinstance(x, dict) for x in timeline):
        _blocked("complete PR chronology is unavailable")
    ready = [
        (i, x) for i, x in enumerate(timeline)
        if x.get("event") == "ready_for_review"
    ]
    committed = [
        (i, x) for i, x in enumerate(timeline)
        if x.get("event") == "committed"
    ]
    if (
        len(ready) != 1 or not committed
        or committed[-1][1].get("sha") != head
        or sum(x.get("sha") == head for _, x in committed) != 1
        or any(x.get("event") == "convert_to_draft" for x in timeline)
    ):
        _blocked("primary Ready or current-head chronology is indeterminate")
    ready_index, ready_event = ready[0]
    boundary = max(ready_index, committed[-1][0])
    ready_time = _time(ready_event.get("created_at"))
    head_publication = observed.get("head_publication")
    if not isinstance(head_publication, Mapping) or head_publication.get("head") != head:
        _blocked("authenticated current-head publication is unavailable")
    assessment_start = max(ready_time, _time(head_publication.get("created_at")))
    comments = observed.get("comments")
    reviews = observed.get("reviews")
    threads = observed.get("threads")
    if (
        not isinstance(comments, list) or any(not isinstance(x, dict) for x in comments)
        or not isinstance(reviews, list) or any(not isinstance(x, dict) for x in reviews)
        or not isinstance(threads, list) or any(not isinstance(x, dict) for x in threads)
    ):
        _blocked("complete provider transport is unavailable")
    comment_ids = [x.get("databaseId") for x in comments]
    if any(type(x) is not int or x <= 0 for x in comment_ids) or len(set(comment_ids)) != len(comment_ids):
        _blocked("request comment identity is ambiguous")
    indexed_comments = {x["databaseId"]: x for x in comments}
    trigger = TRIGGERS[review_type]
    requests: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(timeline):
        if event.get("event") != "commented" or index <= boundary:
            continue
        comment = indexed_comments.get(event.get("id"))
        if comment is None:
            _blocked("PR comment chronology is incomplete")
        if (
            isinstance(comment.get("body"), str) and comment["body"].strip() == trigger
            or trigger in event.get("canonical_trigger_history", ())
        ):
            requests.append((index, comment))
    if len(requests) != 1:
        _blocked("one first fallback and zero replacements are required")
    first_index, first = requests[0]
    first_time = _time(first.get("createdAt"))
    if _actor(first.get("author"))[1:] != actor[1:]:
        _blocked("first fallback stable actor identity changed")
    if (
        first_time != _time(timeline[first_index].get("created_at"))
        or first_time < assessment_start + PROVIDER_OBSERVATION_WINDOW
        or now < first_time + PROVIDER_OBSERVATION_WINDOW
        or first_time > now
        or first.get("updatedAt") != first.get("createdAt")
        or not isinstance(first.get("id"), str) or not first["id"]
        or first.get("body") != trigger
    ):
        _blocked("first fallback is unauthenticated or its window is open")
    if _nodes(first.get("reactions"), "fallback reactions"):
        raise ProviderAcknowledged("first fallback has provider reaction or ambiguous acknowledgement")

    summaries = [
        x for x in comments
        if isinstance(x.get("body"), str)
        and "<!-- codex-pull-request-review-summary -->" in x["body"]
    ]
    if len(summaries) > 1:
        _blocked("provider summary identity is ambiguous")
    if summaries:
        summary = summaries[0]
        if not _provider(summary.get("author")):
            _blocked("provider summary actor is invalid")
        rows, metadata = _summary_rows(
            summary["body"], repository, pull_request
        )
        summary_status, summary_head = rows[review_type]
        if f"`{head[:7]}`" in summary_head:
            raise ProviderAcknowledged("exact-head provider summary already acknowledges this type")
        if review_type == "SECURITY" and metadata["headSha"] == head:
            raise ProviderAcknowledged("exact-head Security provider metadata already exists")
        if (
            "Completed" not in summary_status
            and _time(summary.get("updatedAt", summary.get("createdAt"))) >= first_time
        ):
            raise ProviderAcknowledged("provider summary contains nonterminal acknowledgement")

    for comment in comments:
        if not _provider(comment.get("author")) or comment in summaries:
            continue
        body = comment.get("body")
        kind = _type_from_provider_body(body)
        comment_time = _time(comment.get("createdAt"))
        if kind == review_type and (
            comment_time >= first_time
            or isinstance(body, str) and head[:10] in body
        ):
            raise ProviderAcknowledged("provider result or status exists for the requested type")
        if comment_time >= ready_time and kind is None:
            raise ProviderAcknowledged("provider-owned acknowledgement cannot be classified")
    for review in reviews:
        if not _provider(review.get("author")):
            continue
        commit = review.get("commit")
        if not isinstance(commit, Mapping) or commit.get("oid") != head:
            continue
        kind = _type_from_provider_body(review.get("body"))
        if kind == review_type or kind is None:
            raise ProviderAcknowledged("exact-head provider review object exists or is ambiguous")
    reviews_by_id = {review.get("id"): review for review in reviews}
    for thread in threads:
        for comment in _nodes(thread.get("comments"), "review thread comments"):
            if not _provider(comment.get("author")):
                continue
            parent = comment.get("pullRequestReview")
            parent_id = parent.get("id") if isinstance(parent, Mapping) else None
            review = reviews_by_id.get(parent_id)
            if not isinstance(review, Mapping):
                _blocked("provider-owned thread review identity is unavailable")
            commit = review.get("commit")
            if isinstance(commit, Mapping) and commit.get("oid") == head:
                kind = _type_from_provider_body(review.get("body"))
                if kind == review_type or kind is None:
                    raise ProviderAcknowledged("exact-head provider thread acknowledgement exists")
    key = publication.ProviderDispatchKey(
        repository=repository, delivery_issue=delivery_issue, pull_request=pull_request,
        lifecycle_id=lifecycle_id, current_head_sha=head,
        current_authority_digest=authority_digest, current_publication_oid=publication_oid,
        current_publication_digest=publication_digest, review_type=review_type,
        assessment_authority_digest=assessment_digest,
        original_fallback_comment_node_id=first["id"],
        original_fallback_comment_database_id=first["databaseId"],
        original_fallback_body_digest=sha256(trigger.encode("utf-8")).hexdigest(),
        original_fallback_actor_node_id=actor[1], original_fallback_actor_database_id=actor[2],
        original_fallback_created_at=first["createdAt"],
    )
    return ReplacementEligibility(key, actor)


def _persisted_replacement(
    before: publication.ProviderDispatchKey, after: Mapping[str, Any],
    response_id: int | None,
) -> publication.ProviderDispatchReconciliation:
    """Reconcile exactly one new persisted request, even after an unknown write."""

    lifecycle = after.get("lifecycle")
    if (
        after.get("repository") != before.repository
        or after.get("delivery_issue") != before.delivery_issue
        or after.get("pull_request") != before.pull_request
        or after.get("head_sha") != before.current_head_sha
        or after.get("pr_state") != "OPEN"
        or after.get("is_draft") is not False
        or _actor(after.get("actor"))[1:] != (before.original_fallback_actor_node_id, before.original_fallback_actor_database_id)
        or not isinstance(lifecycle, Mapping)
        or lifecycle.get("lifecycle_id") != before.lifecycle_id
        or lifecycle.get("authority_digest") != before.current_authority_digest
        or lifecycle.get("publication_oid") != before.current_publication_oid
        or lifecycle.get("publication_digest") != before.current_publication_digest
        or lifecycle.get("head_sha") != before.current_head_sha
    ):
        _blocked("replacement reconciliation delivery identity changed")
    comments = after.get("comments")
    timeline = after.get("timeline")
    if not isinstance(comments, list) or not isinstance(timeline, list):
        _blocked("replacement request history is incomplete")
    trigger = TRIGGERS[before.review_type]
    historical_ids = {
        event.get("id") for event in timeline
        if isinstance(event, Mapping) and event.get("event") == "commented"
        and trigger in event.get("canonical_trigger_history", ())
        and _time(event.get("created_at")) >= _time(before.original_fallback_created_at)
    }
    candidates = [
        x for x in comments
        if isinstance(x, Mapping)
        and (isinstance(x.get("body"), str) and x["body"].strip() == trigger
             or x.get("databaseId") in historical_ids)
        and _time(x.get("createdAt")) >= _time(before.original_fallback_created_at)
    ]
    ids = [x.get("databaseId") for x in candidates]
    if (
        len(candidates) > 2 or len(ids) != len(set(ids))
        or before.original_fallback_comment_database_id not in ids
        or not historical_ids.issubset(ids)
    ):
        _blocked("replacement request history is duplicate or substituted")
    if any(x.get("body") != trigger
            or _actor(x.get("author"))[1:] != (before.original_fallback_actor_node_id, before.original_fallback_actor_database_id)
            or x.get("updatedAt") != x.get("createdAt") for x in candidates):
        _blocked("replacement request actor or canonical body changed")
    original = next(
        x for x in candidates
        if x.get("databaseId") == before.original_fallback_comment_database_id
    )
    if (
        original.get("id") != before.original_fallback_comment_node_id
        or original.get("createdAt") != before.original_fallback_created_at
        or sha256(original["body"].encode("utf-8")).hexdigest()
            != before.original_fallback_body_digest
    ):
        _blocked("original fallback identity changed during reconciliation")
    if len(candidates) == 1:
        return publication.ProviderDispatchReconciliation(0, None)
    replacement = next(
        x for x in candidates
        if x.get("databaseId") != before.original_fallback_comment_database_id
    )
    replacement_id = replacement.get("databaseId")
    if (
        type(replacement_id) is not int or replacement_id <= 0
        or not isinstance(replacement.get("id"), str) or not replacement["id"]
        or response_id is not None and response_id != replacement_id
        or _time(replacement.get("createdAt")) < _time(before.original_fallback_created_at) + PROVIDER_OBSERVATION_WINDOW
        or sum(
            1 for event in timeline
            if isinstance(event, Mapping)
            and event.get("event") == "commented"
            and event.get("id") == replacement_id
            and _time(event.get("created_at"))
                == _time(replacement.get("createdAt"))
        ) != 1
    ):
        _blocked("replacement comment identity or chronology is invalid")
    return publication.ProviderDispatchReconciliation(1, replacement_id)


class LiveProviderObservation:
    """Compose maintained CURRENT, provider transport and native chronology reads."""

    def __init__(self, repository: str, delivery_issue: int, pull_request: int) -> None:
        self.repository = repository
        self.delivery_issue = delivery_issue
        self.pull_request = pull_request
        self.actions = bootstrap_source_admission._load_actions_helper()
        self.github = self.actions.LiveGitHub()

    def observe(self) -> dict[str, Any]:
        current = publication.verify_current_lifecycle_authority(self.repository, self.delivery_issue)
        transport = self.github.read_provider_fallback_transport({
            "repository": self.repository, "pull_request_number": self.pull_request,
        })["provider_transport"]
        chronology = provider_acquisition._observe(self.repository, self.pull_request)
        if provider_acquisition._observe(self.repository, self.pull_request) != chronology:
            _blocked("PR chronology changed between bounded reads")
        actor = self.github.inspect_actor()
        if _actor(actor)[1:] != chronology["author"][1:]:
            _blocked("authenticated request actor is not the delivery actor")
        lifecycle = current.lifecycle
        if (chronology["repository"] != self.repository
                or chronology["pull_request"] != self.pull_request
                or chronology["head"] != lifecycle.head_sha
                or chronology["state"] != "OPEN" or chronology["draft"] is not False):
            _blocked("native chronology delivery identity changed")
        signed, _ = publication._canonical_bundle(current.serialized_lifecycle_evidence)
        bundle = publication._lifecycle_bundle({"lifecycle_evidence": signed})
        timeline = []
        for event in chronology["events"]:
            item = {"created_at": event["created_at"]}
            if event["kind"] == "COMMIT":
                item.update(event="committed", sha=event["head"])
            elif event["kind"] == "ReadyForReviewEvent":
                item.update(event="ready_for_review")
            elif event["kind"] == "IssueComment":
                item.update(event="commented", id=event["database_id"],
                    canonical_trigger_history=tuple(body.strip() for _, body in event["versions"]))
            elif event["kind"] == "PullRequestReview":
                continue
            else:
                _blocked("PR Ready/head chronology contains an exceptional transition")
            timeline.append(item)
        # This read follows all external transport/chronology/actor reads. The
        # claim owner also checks CURRENT before and after winning protected CAS.
        fresh = publication.verify_current_lifecycle_authority(self.repository, self.delivery_issue)
        if (fresh.publication_oid != current.publication_oid
                or fresh.publication_digest != current.publication_digest
                or fresh.lifecycle.authority_digest != lifecycle.authority_digest
                or fresh.lifecycle.lifecycle_id != lifecycle.lifecycle_id
                or fresh.lifecycle.pull_request != lifecycle.pull_request
                or fresh.lifecycle.head_sha != lifecycle.head_sha):
            _blocked("CURRENT changed after external provider reads")
        return {
            **transport, "delivery_issue": self.delivery_issue, "actor": actor,
            "head_publication": chronology["head_publication"], "timeline": timeline,
            "lifecycle": {
                "repository": lifecycle.repository, "delivery_issue": lifecycle.delivery_issue,
                "pull_request": lifecycle.pull_request, "head_sha": lifecycle.head_sha,
                "lifecycle_id": lifecycle.lifecycle_id, "authority_digest": lifecycle.authority_digest,
                "publication_oid": current.publication_oid,
                "publication_digest": current.publication_digest,
                "bundle": bundle, "state": lifecycle.state,
            },
        }

    def write(self, body: str) -> int | None:
        if body not in TRIGGERS.values():
            _blocked("replacement trigger body is not canonical")
        try:
            response = self.github.runner.run([
                "gh", "api", "--hostname", "github.com",
                f"repos/{self.repository}/issues/{self.pull_request}/comments",
                "--method", "POST", "-f", f"body={body}",
            ])
        except self.actions.ActionCommandFailure as exc:
            # A terminal API rejection proves non-persistence. A timeout or
            # transport failure does not; only the latter is reconciled.
            if exc.returncode == 4 or re.search(r"HTTP 4[0-9]{2}\b", exc.stderr + "\n" + exc.stdout):
                raise
            raise publication.AmbiguousProviderDispatchWrite("provider POST outcome is unknown") from exc
        except self.actions.MutationFailure as exc:
            raise publication.AmbiguousProviderDispatchWrite("provider POST response is indeterminate") from exc
        if (not isinstance(response, dict) or response.get("body") != body
                or type(response.get("id")) is not int or response["id"] <= 0):
            raise publication.AmbiguousProviderDispatchWrite("provider POST response identity is indeterminate")
        return response["id"]


_RUNTIME_CLASS = LiveProviderObservation
_RUNTIME_METHODS = tuple(
    (name, getattr(_RUNTIME_CLASS, name)) for name in ("__init__", "observe", "write")
)
_RUNTIME_INIT, _RUNTIME_OBSERVE, _RUNTIME_WRITE = (
    method for _, method in _RUNTIME_METHODS
)


def _new_runtime(repository: str, delivery_issue: int, pull_request: int) -> LiveProviderObservation:
    if LiveProviderObservation is not _RUNTIME_CLASS or any(
        getattr(_RUNTIME_CLASS, name) is not method for name, method in _RUNTIME_METHODS
    ):
        _blocked("provider runtime callable identity changed")
    runtime = object.__new__(_RUNTIME_CLASS)
    _RUNTIME_INIT(runtime, repository, delivery_issue, pull_request)
    return runtime


def _runtime(repository: str, delivery_issue: int) -> LiveProviderObservation:
    current = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    return _new_runtime(repository, delivery_issue, current.lifecycle.pull_request)


def authenticate_claim_eligibility(
    repository: str, delivery_issue: int, review_type: str,
) -> publication.ProviderDispatchEligibility | publication.ProviderDispatchNoLongerRequired:
    try:
        eligible = classify(_RUNTIME_OBSERVE(_runtime(repository, delivery_issue)), review_type, datetime.now(timezone.utc))
    except ProviderAcknowledged:
        return publication.ProviderDispatchNoLongerRequired()
    return publication.ProviderDispatchEligibility(eligible.dispatch_key, fast_path.digest_json(asdict(eligible)))


def write_claimed_replacement(
    repository: str, delivery_issue: int, review_type: str,
    key: publication.ProviderDispatchKey, body: str,
) -> int | None:
    if (type(key) is not publication.ProviderDispatchKey
            or (key.repository, key.delivery_issue, key.review_type) != (repository, delivery_issue, review_type)
            or body != TRIGGERS.get(review_type)):
        _blocked("replacement trigger substituted another review type")
    return _RUNTIME_WRITE(_new_runtime(repository, delivery_issue, key.pull_request), body)


def reconcile_claimed_replacement(
    key: publication.ProviderDispatchKey, response_id: int | None,
) -> publication.ProviderDispatchReconciliation:
    runtime = _new_runtime(key.repository, key.delivery_issue, key.pull_request)
    try:
        observed = _RUNTIME_OBSERVE(runtime)
    except ReplacementBlocked:
        raise
    except Exception as exc:
        raise publication.ProviderDispatchHistoryUnavailable("complete replacement request history is unavailable") from exc
    return _persisted_replacement(key, observed, response_id)

def inspect(runtime: LiveProviderObservation, review_type: str) -> ReplacementEligibility:
    """Read-only eligibility and prospective claim availability; never claim."""
    eligible = classify(runtime.observe(), review_type, datetime.now(timezone.utc))
    key = eligible.dispatch_key
    current, claims = publication.verify_provider_dispatch_claims(key.repository, key.delivery_issue)
    if (current.publication_oid != key.current_publication_oid
            or current.publication_digest != key.current_publication_digest):
        _blocked("CURRENT changed during prospective claim inspection")
    if any(publication.provider_dispatch_claim_id(claim.key)
           == publication.provider_dispatch_claim_id(key) for claim in claims):
        _blocked("provider dispatch claim already exists")
    return eligible


def dispatch(repository: str, delivery_issue: int, pull_request: int, review_type: str) -> publication.ProviderDispatchResult:
    # Claim authority must never execute an unaccepted candidate verifier.
    actions = bootstrap_source_admission._load_actions_helper()
    actions._require_accepted_main_bridge_source(repository)
    policy = lifecycle_authority._load_lifecycle_trust_policy(repository)
    identity, signer = lifecycle_execution._policy_role_signer(
        policy, policy.publication_signer_identities, "publication signer role",
        allow_routine_default=True,
    )
    return publication.execute_provider_dispatch_with_claim(
        repository, delivery_issue, review_type,
        signer_identity=identity, signer=signer,
        expected_pull_request=pull_request,
    )
