# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ephemeral admission for one persisted, unacknowledged provider fallback.

The caller must acquire a complete live provider observation and authenticated
CURRENT lifecycle. This module never changes a lifecycle or issues a request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any, Callable, Mapping


# The maintained passive provider observation window is approximately 30 minutes.
PROVIDER_OBSERVATION_WINDOW = timedelta(minutes=30)
TRIGGERS = {"CODE": "@codex review", "SECURITY": "@codex security review"}
PROVIDER = "chatgpt-codex-connector"
OID = re.compile(r"[0-9a-f]{40}\Z")


class ReplacementBlocked(ValueError):
    """The closed replacement preconditions are not all proven."""


@dataclass(frozen=True)
class ReplacementEligibility:
    repository: str
    delivery_issue: int
    pull_request: int
    head_sha: str
    lifecycle_id: str
    lifecycle_authority_digest: str
    lifecycle_publication_oid: str
    review_type: str
    request_actor: str
    first_comment_node_id: str
    first_comment_database_id: int
    first_comment_created_at: str
    first_comment_body_digest: str
    trigger_body: str
    replacement_count: int = 0


@dataclass(frozen=True)
class ReplacementDispatch:
    status: str
    replacement_comment_database_id: int | None
    write_attempts: int = 1


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


def _actor(value: Any) -> str | None:
    if isinstance(value, Mapping):
        login = value.get("login")
        return login.lower() if isinstance(login, str) else None
    return None


def _nodes(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        if value.get("pageInfo", {}).get("hasNextPage") is not False:
            _blocked(f"{label} evidence is incomplete")
        value = value.get("nodes")
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        _blocked(f"{label} evidence is malformed")
    return value


def _type_from_provider_body(body: Any) -> str | None:
    if not isinstance(body, str):
        return None
    if body.lstrip().startswith("### 🛡️ Codex Security Review"):
        return "SECURITY"
    if body.lstrip().startswith("### 💡 Codex Review") or body.startswith("Codex Review:"):
        return "CODE"
    return None


def _summary_rows(
    body: str, repository: str, pull_request: int,
) -> tuple[dict[str, tuple[str, str]], dict[str, Any]]:
    if "<!-- codex-pull-request-review-summary -->" not in body:
        _blocked("provider summary marker is unavailable")
    metadata = re.findall(r"<!--\s*codex-security-review:v1\s+(\{.*?\})\s*-->", body, re.DOTALL)
    if len(metadata) != 1:
        _blocked("provider summary metadata is indeterminate")
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate provider summary key")
            result[key] = value
        return result
    try:
        status = json.loads(metadata[0], object_pairs_hook=unique_pairs)
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
    if (
        not isinstance(repository, str) or not repository
        or type(delivery_issue) is not int or delivery_issue <= 0
        or type(pull_request) is not int or pull_request <= 0
        or not isinstance(head, str) or not OID.fullmatch(head)
        or not isinstance(lifecycle_id, str) or not lifecycle_id
        or not isinstance(authority_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", authority_digest)
        or not isinstance(publication_oid, str) or not OID.fullmatch(publication_oid)
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
    actor = observed.get("actor")
    if not isinstance(actor, str) or not actor:
        _blocked("authorized request actor is unavailable")
    chain = lifecycle.get("authority_chain")
    if not isinstance(chain, list) or any(not isinstance(x, Mapping) for x in chain):
        _blocked("authenticated assessment history is unavailable")
    last_foreign_head = max(
        (i for i, x in enumerate(chain) if x.get("head_sha") != head),
        default=-1,
    )
    if not any(
        i > last_foreign_head
        and x.get("transition_kind") == "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED"
        and x.get("head_sha") == head
        for i, x in enumerate(chain)
    ):
        _blocked("current-head assessment has no consumed review authority")

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
        if comment.get("body") == trigger:
            requests.append((index, comment))
    if len(requests) != 1:
        _blocked("one first fallback and zero replacements are required")
    first_index, first = requests[0]
    first_time = _time(first.get("createdAt"))
    if (
        first_time != _time(timeline[first_index].get("created_at"))
        or first_time < ready_time + PROVIDER_OBSERVATION_WINDOW
        or now < first_time + PROVIDER_OBSERVATION_WINDOW
        or first_time > now
        or _actor(first.get("author")) != actor.lower()
        or not isinstance(first.get("id"), str) or not first["id"]
        or first.get("body") != trigger
    ):
        _blocked("first fallback is unauthenticated or its window is open")
    if _nodes(first.get("reactions"), "fallback reactions"):
        _blocked("first fallback has provider reaction or ambiguous acknowledgement")

    summaries = [
        x for x in comments
        if isinstance(x.get("body"), str)
        and "<!-- codex-pull-request-review-summary -->" in x["body"]
    ]
    if len(summaries) > 1:
        _blocked("provider summary identity is ambiguous")
    if summaries:
        summary = summaries[0]
        if _actor(summary.get("author")) != PROVIDER:
            _blocked("provider summary actor is invalid")
        rows, metadata = _summary_rows(
            summary["body"], repository, pull_request
        )
        summary_status, summary_head = rows[review_type]
        if f"`{head[:7]}`" in summary_head:
            _blocked("exact-head provider summary already acknowledges this type")
        if review_type == "SECURITY" and metadata["headSha"] == head:
            _blocked("exact-head Security provider metadata already exists")
        if (
            "Completed" not in summary_status
            and _time(summary.get("updatedAt", summary.get("createdAt"))) >= first_time
        ):
            _blocked("provider summary contains nonterminal acknowledgement")

    for comment in comments:
        if _actor(comment.get("author")) != PROVIDER or comment in summaries:
            continue
        body = comment.get("body")
        kind = _type_from_provider_body(body)
        comment_time = _time(comment.get("createdAt"))
        if kind == review_type and (
            comment_time >= first_time
            or isinstance(body, str) and head[:10] in body
        ):
            _blocked("provider result or status exists for the requested type")
        if comment_time >= ready_time and kind is None:
            _blocked("provider-owned acknowledgement cannot be classified")
    for review in reviews:
        if _actor(review.get("author")) != PROVIDER:
            continue
        commit = review.get("commit")
        if not isinstance(commit, Mapping) or commit.get("oid") != head:
            continue
        kind = _type_from_provider_body(review.get("body"))
        if kind == review_type or kind is None:
            _blocked("exact-head provider review object exists or is ambiguous")
    reviews_by_id = {review.get("id"): review for review in reviews}
    for thread in threads:
        for comment in _nodes(thread.get("comments"), "review thread comments"):
            if _actor(comment.get("author")) != PROVIDER:
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
                    _blocked("exact-head provider thread acknowledgement exists")
    return ReplacementEligibility(
        repository, delivery_issue, pull_request, head, lifecycle_id,
        authority_digest, publication_oid,
        review_type, actor.lower(), first["id"], first["databaseId"],
        first["createdAt"], sha256(trigger.encode("utf-8")).hexdigest(),
        trigger,
    )


def _persisted_replacement(
    before: ReplacementEligibility, after: Mapping[str, Any],
    response_id: int | None,
) -> ReplacementDispatch:
    """Reconcile exactly one new persisted request, even after an unknown write."""

    lifecycle = after.get("lifecycle")
    if (
        after.get("repository") != before.repository
        or after.get("delivery_issue") != before.delivery_issue
        or after.get("pull_request") != before.pull_request
        or after.get("head_sha") != before.head_sha
        or after.get("pr_state") != "OPEN"
        or after.get("is_draft") is not False
        or not isinstance(after.get("actor"), str)
        or after["actor"].lower() != before.request_actor
        or not isinstance(lifecycle, Mapping)
        or lifecycle.get("lifecycle_id") != before.lifecycle_id
        or lifecycle.get("authority_digest") != before.lifecycle_authority_digest
        or lifecycle.get("publication_oid") != before.lifecycle_publication_oid
        or lifecycle.get("head_sha") != before.head_sha
    ):
        _blocked("replacement reconciliation delivery identity changed")
    comments = after.get("comments")
    timeline = after.get("timeline")
    if not isinstance(comments, list) or not isinstance(timeline, list):
        _blocked("replacement request history is incomplete")
    candidates = [
        x for x in comments
        if isinstance(x, Mapping)
        and x.get("body") == before.trigger_body
        and _actor(x.get("author")) == before.request_actor
        and _time(x.get("createdAt")) >= _time(before.first_comment_created_at)
    ]
    ids = [x.get("databaseId") for x in candidates]
    if (
        len(candidates) > 2 or len(ids) != len(set(ids))
        or before.first_comment_database_id not in ids
    ):
        _blocked("replacement request history is duplicate or substituted")
    if len(candidates) == 1:
        return ReplacementDispatch("INCOMPLETE_UNKNOWN_WRITE_RESULT", None)
    original = next(
        x for x in candidates
        if x.get("databaseId") == before.first_comment_database_id
    )
    if (
        original.get("id") != before.first_comment_node_id
        or original.get("createdAt") != before.first_comment_created_at
        or sha256(original["body"].encode("utf-8")).hexdigest()
            != before.first_comment_body_digest
    ):
        _blocked("original fallback identity changed during reconciliation")
    replacement = next(
        x for x in candidates
        if x.get("databaseId") != before.first_comment_database_id
    )
    replacement_id = replacement.get("databaseId")
    if (
        type(replacement_id) is not int or replacement_id <= 0
        or not isinstance(replacement.get("id"), str) or not replacement["id"]
        or response_id is not None and response_id != replacement_id
        or _time(replacement.get("createdAt")) < _time(before.first_comment_created_at)
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
    return ReplacementDispatch("PERSISTED", replacement_id)


def dispatch_once(
    observe: Callable[[], Mapping[str, Any]],
    write: Callable[[str], int | None],
    review_type: str,
    clock: Callable[[], datetime],
) -> ReplacementDispatch:
    """Re-read immediately before one write; reconcile ambiguity without retry."""

    initial = classify(observe(), review_type, clock())
    current = classify(observe(), review_type, clock())
    if current != initial:
        _blocked("replacement eligibility changed before dispatch")
    response_id: int | None = None
    try:
        response_id = write(current.trigger_body)
    except Exception:
        # An unknown outcome is never a reason to issue a second write.
        pass
    try:
        after = observe()
    except Exception:
        return ReplacementDispatch("INCOMPLETE_UNKNOWN_WRITE_RESULT", None)
    return _persisted_replacement(current, after, response_id)
