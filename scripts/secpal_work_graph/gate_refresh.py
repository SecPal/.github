# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Bounded refresh of mutable work-graph evidence on open PR heads."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path
from typing import Protocol

HARD_CONTEXT = "Work-Graph PR Gate"
DEFAULT_MAXIMUM_PULL_REQUESTS = 100
# GitHub's append-only per-repository SHA/context limit. A refresh needs both
# invalidation and a terminal publication; this snapshot reserves neither slot.
STATUS_CAPACITY = 1000
MAXIMUM_STATUS_PAGES = 20
MAXIMUM_RESPONSE_BYTES = 65536
MAXIMUM_STATUS_PAGE_BYTES = 512 * 1024
MAXIMUM_HEADER_BYTES = 8192
_HTTP_STATUS = re.compile(r"HTTP/(?:1\.[01]|2(?:\.0)?) ([1-5][0-9]{2})(?: [^\r\n]*)?")
_REQUEST_ID = re.compile(r"[A-F0-9]{1,16}(?::[A-F0-9]{1,16}){3,4}")
_PROVIDER_CODES = frozenset(
    {"missing", "missing_field", "invalid", "already_exists", "unprocessable", "custom"}
)
_SAFE_MESSAGES = frozenset(
    {
        "Bad credentials",
        "Resource not accessible by integration",
        "Resource not accessible by personal access token",
        "Validation Failed",
        "Not Found",
        "API rate limit exceeded",
        "You have exceeded a secondary rate limit.",
        "This SHA and context has reached the maximum number of statuses.",
    }
)
_CAPACITY_MESSAGE = "This SHA and context has reached the maximum number of statuses."
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_OID = re.compile(r"^[0-9a-f]{40,64}$")


class RefreshError(RuntimeError):
    """The hard-gate candidate set or authenticated refresh failed."""

    def __init__(self, message: str, *, evidence: dict[str, object] | None = None):
        self.evidence = evidence
        super().__init__(
            message + ": " + json.dumps(evidence, sort_keys=True)
            if evidence is not None
            else message
        )


class PublicationError(RefreshError):
    """Safe publication evidence; no arbitrary process output crosses this edge."""

    def __init__(self, evidence: dict[str, object]):
        super().__init__(
            "hard-gate commit status publication failed", evidence=evidence
        )


class CommandError(RefreshError):
    def __init__(self, outcome: str, stdout: str | bytes = ""):
        self.outcome = outcome
        # TimeoutExpired.stdout is explicitly the received stdout stream. Keep
        # only its safe projection; stderr and arbitrary exception text are lost.
        if isinstance(stdout, bytes):
            stdout = stdout[:MAXIMUM_STATUS_PAGE_BYTES].decode(
                "utf-8", errors="replace"
            )
        status, headers, payload = _response(
            stdout, maximum_bytes=MAXIMUM_STATUS_PAGE_BYTES
        )
        self.diagnostics = _diagnostics(status, headers, payload)
        super().__init__("authenticated GitHub command failed")


def _response(
    stdout: str, *, maximum_bytes: int = MAXIMUM_RESPONSE_BYTES
) -> tuple[int | None, dict[str, str], object]:
    """Normalize only gh --include's bounded HTTP envelope, never stderr."""
    lines = stdout[:MAXIMUM_HEADER_BYTES].replace("\r\n", "\n").split("\n", 1)
    match = _HTTP_STATUS.fullmatch(lines[0])
    if match is None:
        return None, {}, None
    status = int(match[1])
    bounded = (
        len(stdout) <= maximum_bytes and len(stdout.encode("utf-8")) <= maximum_bytes
    )
    normalized = (
        stdout.replace("\r\n", "\n")
        if bounded
        else stdout[:MAXIMUM_HEADER_BYTES].replace("\r\n", "\n")
    )
    header, separator, body = normalized.partition("\n\n")
    if not separator or len(header) > MAXIMUM_HEADER_BYTES:
        return status, {}, None
    parsed = Parser().parsestr(header.split("\n", 1)[1] if "\n" in header else "")
    headers = {}
    for name in (
        "X-GitHub-Request-Id",
        "Retry-After",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ):
        values = parsed.get_all(name, [])
        if len(values) == 1 and isinstance(values[0], str):
            headers[name.lower()] = values[0].strip()
    if not bounded:
        return status, headers, None
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):
        payload = None
    return status, headers, payload


def _diagnostics(
    status: int | None, headers: dict[str, str], payload: object
) -> dict[str, object]:
    """Pure finite projection: provider text is selected, never redacted/copied."""
    request_id = headers.get("x-github-request-id", "")
    retry = {}
    for header, key in (
        ("retry-after", "retry_after_seconds"),
        ("x-ratelimit-remaining", "rate_limit_remaining"),
        ("x-ratelimit-reset", "rate_limit_reset"),
    ):
        value = headers.get(header, "")
        if re.fullmatch(r"[0-9]{1,10}", value):
            retry[key] = int(value)
    message = payload.get("message") if isinstance(payload, dict) else None
    safe_message = (
        message if isinstance(message, str) and message in _SAFE_MESSAGES else None
    )
    errors = payload.get("errors") if isinstance(payload, dict) else None
    codes = set()
    capacity = False
    if isinstance(errors, list) and len(errors) <= 16:
        for error in errors:
            if not isinstance(error, dict) or error.get("resource") != "Status":
                continue
            code = error.get("code")
            if isinstance(code, str) and code in _PROVIDER_CODES:
                codes.add(code)
            if code == "custom" and error.get("message") == _CAPACITY_MESSAGE:
                capacity = True
    if status == 422 and capacity:
        category = "CAPACITY_EXHAUSTED"
    elif status == 429 or (
        status == 403
        and (
            retry.get("rate_limit_remaining") == 0
            or safe_message
            in {"API rate limit exceeded", "You have exceeded a secondary rate limit."}
        )
    ):
        category = "RATE_LIMITED"
    elif status in {401, 403}:
        category = "AUTHORIZATION_REJECTED"
    elif status == 422:
        category = "VALIDATION_REJECTED"
    elif status is None:
        category = "NO_HTTP_RESPONSE"
    else:
        category = "UNCLASSIFIED_HTTP_RESPONSE"
    return {
        "http_status": status,
        "http_response": "RECEIVED" if status is not None else "NOT_OBSERVED",
        "category": category,
        "provider_codes": sorted(codes),
        "safe_message": safe_message,
        "request_id": request_id if _REQUEST_ID.fullmatch(request_id) else None,
        "retry": retry,
    }


def _identity(
    repository: str, pull: PullRequest, state: str, phase: str
) -> dict[str, object]:
    return {
        "repository": _repository(repository),
        "pr": pull.number,
        "sha": pull.head_sha,
        "context": HARD_CONTEXT,
        "phase": phase,
        "state": state,
        "target_url": f"https://github.com/{repository}/pull/{pull.number}",
    }


def _status_identity(payload: object, repository: str, pull: PullRequest) -> bool:
    return (
        isinstance(payload, dict)
        and type(payload.get("id")) is int
        and payload["id"] > 0
        and payload.get("url")
        == f"https://api.github.com/repos/{repository}/statuses/{pull.head_sha}"
    )


@dataclass(frozen=True)
class PullRequest:
    number: int
    head_sha: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.number, int)
            or isinstance(self.number, bool)
            or self.number < 1
            or not isinstance(self.head_sha, str)
            or not _OID.fullmatch(self.head_sha)
        ):
            raise RefreshError("open pull-request identity is malformed")


class Gateway(Protocol):
    def open_pull_requests(
        self, repository: str, limit: int
    ) -> tuple[PullRequest, ...]: ...

    def preflight(self, repository: str, pull: PullRequest) -> None: ...

    def publish(
        self,
        repository: str,
        pull: PullRequest,
        state: str,
        description: str,
    ) -> dict[str, object]: ...

    def assess(self, repository: str, pull: PullRequest) -> int: ...


def _repository(value: str) -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise RefreshError("repository identity is malformed")
    return value


def refresh_repository(
    gateway: Gateway,
    repository: str,
    *,
    maximum_pull_requests: int = DEFAULT_MAXIMUM_PULL_REQUESTS,
) -> dict[str, object]:
    """Invalidate every bounded candidate before recomputing canonical truth."""

    repository = _repository(repository)
    if not 1 <= maximum_pull_requests <= DEFAULT_MAXIMUM_PULL_REQUESTS:
        raise RefreshError("bounded candidate limit is invalid")
    report: dict[str, object] = {
        "schema": "secpal-work-graph-gate-refresh/v1",
        "repository": repository,
        "context": HARD_CONTEXT,
        "candidate_count": None,
        "refreshed": 0,
        "failed": [],
        "unavailable": [],
        "publications": [],
    }
    publications = report["publications"]
    try:
        candidates = gateway.open_pull_requests(repository, maximum_pull_requests)
        report["candidate_count"] = len(candidates)
        if len(candidates) > maximum_pull_requests:
            raise RefreshError("bounded candidate limit was exceeded")
        if len({pull.number for pull in candidates}) != len(candidates) or len(
            {pull.head_sha for pull in candidates}
        ) != len(candidates):
            raise RefreshError("open pull-request candidates are duplicated")

        # Complete all read-only capacity checks before invalidating any head.
        # No preflight guarantees space against concurrent append-only writers.
        for pull in candidates:
            gateway.preflight(repository, pull)

        def publish(pull: PullRequest, state: str, description: str) -> None:
            evidence = gateway.publish(repository, pull, state, description)
            if (
                not isinstance(evidence, dict)
                or evidence.get("outcome") != "AUTHENTICATED_SUCCESS"
            ):
                raise PublicationError(
                    {
                        **_identity(
                            repository,
                            pull,
                            state,
                            "invalidation" if state == "pending" else "terminal",
                        ),
                        "outcome": "AMBIGUOUS",
                        "category": "UNCONFIRMED_PUBLICATION",
                    }
                )
            publications.append(evidence)

        # No reassessment until every invalidation has authenticated success.
        for pull in candidates:
            publish(pull, "pending", "Mutable work-graph evidence is being refreshed")

        for pull in candidates:
            try:
                result = gateway.assess(repository, pull)
            except RefreshError:
                raise PublicationError(
                    {
                        **_identity(repository, pull, "unresolved", "assessment"),
                        "outcome": "NOT_ATTEMPTED",
                        "category": "ASSESSMENT_UNAVAILABLE",
                    }
                ) from None
            if result == 0:
                state, description = (
                    "success",
                    "Current canonical work-graph evidence passed",
                )
            elif result == 1:
                state, description = (
                    "failure",
                    "Current canonical work-graph evidence blocked delivery",
                )
                report["failed"].append(pull.number)
            else:
                state, description = (
                    "error",
                    "Current canonical work-graph evidence is unavailable",
                )
                report["unavailable"].append(pull.number)
            publish(pull, state, description)
            report["refreshed"] += 1
    except RefreshError as exc:
        report["outcome"] = (
            "PARTIAL_PUBLICATION" if publications else "BEFORE_PUBLICATION"
        )
        report["failure"] = exc.evidence or {"category": "REFRESH_BLOCKED"}
        # An attempted but unconfirmed first write is not confirmed absence.
        if (
            not publications
            and exc.evidence
            and exc.evidence.get("outcome") == "AMBIGUOUS"
        ):
            report["outcome"] = "AMBIGUOUS_PUBLICATION"
        elif (
            not publications
            and exc.evidence
            and exc.evidence.get("outcome") == "HTTP_REJECTED"
        ):
            report["outcome"] = "REJECTED_PUBLICATION"
        raise RefreshError(
            str(exc) if exc.evidence is None else "hard-gate refresh failed",
            evidence=report,
        ) from None
    report["outcome"] = "COMPLETE"
    return report


class CommandGateway:
    """Authenticated GitHub CLI boundary used by workflow and replan callers."""

    def __init__(self, *, gh: str, repository_root: Path) -> None:
        self.gh = gh
        self.repository_root = repository_root.resolve(strict=True)

    def _run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.gh, *arguments],
                cwd=self.repository_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except UnicodeError:
            raise CommandError("OUTPUT_UNREADABLE") from None
        except subprocess.TimeoutExpired as exc:
            raise CommandError("TIMED_OUT", exc.stdout or "") from None
        except (OSError, subprocess.SubprocessError):
            raise CommandError("EXECUTION_FAILED") from None

    def open_pull_requests(
        self, repository: str, limit: int
    ) -> tuple[PullRequest, ...]:
        owner, name = repository.split("/", 1)
        query = """query GateRefresh($owner: String!, $name: String!, $limit: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    defaultBranchRef { name }
    pullRequests(first: $limit, states: OPEN, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage }
      nodes { number headRefOid baseRefName }
    }
  }
}"""
        result = self._run(
            [
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"limit={limit}",
            ]
        )
        if result.returncode != 0:
            raise RefreshError("open pull-request candidates are unreadable")
        try:
            payload = json.loads(result.stdout)
            repository_payload = payload["data"]["repository"]
            connection = repository_payload["pullRequests"]
            default_branch = repository_payload["defaultBranchRef"]["name"]
            nodes = connection["nodes"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RefreshError("open pull-request candidates are malformed") from exc
        if (
            not isinstance(repository_payload, dict)
            or not isinstance(connection, dict)
            or not isinstance(default_branch, str)
            or not isinstance(nodes, list)
            or any(not isinstance(item, dict) for item in nodes)
            or not isinstance(connection.get("pageInfo"), dict)
            or not isinstance(connection.get("pageInfo", {}).get("hasNextPage"), bool)
            or not isinstance(connection.get("totalCount"), int)
            or isinstance(connection.get("totalCount"), bool)
        ):
            raise RefreshError("open pull-request candidates are malformed")
        if (
            repository_payload.get("nameWithOwner") != repository
            or connection.get("pageInfo", {}).get("hasNextPage")
            or connection.get("totalCount") != len(nodes)
            or connection.get("totalCount", limit + 1) > limit
        ):
            raise RefreshError("bounded candidate limit was exceeded")
        try:
            return tuple(
                PullRequest(item["number"], item["headRefOid"])
                for item in nodes
                if item.get("baseRefName") == default_branch
            )
        except KeyError as exc:
            raise RefreshError("open pull-request candidates are malformed") from exc

    def _observe(
        self,
        arguments: list[str],
        identity: dict[str, object],
        *,
        maximum_bytes: int = MAXIMUM_RESPONSE_BYTES,
    ) -> tuple[dict[str, object], object]:
        try:
            result = self._run(arguments)
        except (CommandError, OSError, subprocess.SubprocessError) as exc:
            failure = (
                exc
                if isinstance(exc, CommandError)
                else CommandError(
                    (
                        "TIMED_OUT"
                        if isinstance(exc, subprocess.TimeoutExpired)
                        else "EXECUTION_FAILED"
                    ),
                    (
                        (exc.stdout or "")
                        if isinstance(exc, subprocess.TimeoutExpired)
                        else ""
                    ),
                )
            )
            return (
                {
                    **identity,
                    **failure.diagnostics,
                    "command": {"outcome": failure.outcome, "returncode": None},
                },
                None,
            )
        status, headers, payload = _response(result.stdout, maximum_bytes=maximum_bytes)
        return (
            {
                **identity,
                **_diagnostics(status, headers, payload),
                "command": {"outcome": "EXITED", "returncode": result.returncode},
            },
            payload,
        )

    def preflight(self, repository: str, pull: PullRequest) -> None:
        identity = _identity(repository, pull, "pending", "capacity_preflight")
        count = 0
        seen = set()
        for page in range(1, MAXIMUM_STATUS_PAGES + 1):
            evidence, payload = self._observe(
                [
                    "api",
                    "--include",
                    "--method",
                    "GET",
                    f"repos/{repository}/commits/{pull.head_sha}/statuses?per_page=100&page={page}",
                ],
                identity,
                maximum_bytes=MAXIMUM_STATUS_PAGE_BYTES,
            )
            evidence["outcome"] = "NOT_ATTEMPTED"
            if (
                evidence["command"]["returncode"] != 0
                or evidence["http_status"] != 200
                or not isinstance(payload, list)
                or len(payload) > 100
            ):
                evidence["category"] = "CAPACITY_UNREADABLE"
                raise PublicationError(evidence)
            for item in payload:
                if (
                    not _status_identity(item, repository, pull)
                    or not isinstance(item.get("context"), str)
                    or item["id"] in seen
                ):
                    evidence["category"] = "CAPACITY_MALFORMED"
                    raise PublicationError(evidence)
                seen.add(item["id"])
                if item["context"].casefold() == HARD_CONTEXT.casefold():
                    count += 1
            if count > STATUS_CAPACITY - 2:
                evidence.update(
                    category="CAPACITY_INSUFFICIENT",
                    observed_count=count,
                    required_slots=2,
                    capacity=STATUS_CAPACITY,
                )
                raise PublicationError(evidence)
            if len(payload) < 100:
                return
        evidence["category"] = "CAPACITY_BOUND_EXCEEDED"
        raise PublicationError(evidence)

    def publish(
        self,
        repository: str,
        pull: PullRequest,
        state: str,
        description: str,
    ) -> dict[str, object]:
        if state not in {"pending", "success", "failure", "error"}:
            raise RefreshError("commit status state is invalid")
        identity = _identity(
            repository,
            pull,
            state,
            "invalidation" if state == "pending" else "terminal",
        )
        evidence, payload = self._observe(
            [
                "api",
                "--include",
                "--method",
                "POST",
                f"repos/{repository}/statuses/{pull.head_sha}",
                "-f",
                f"state={state}",
                "-f",
                f"context={HARD_CONTEXT}",
                "-f",
                f"description={description}",
                "-f",
                f"target_url={identity['target_url']}",
            ],
            identity,
        )
        status = evidence["http_status"]
        if (
            evidence["command"]["returncode"] == 0
            and status == 201
            and _status_identity(payload, repository, pull)
            and payload.get("context") == HARD_CONTEXT
            and payload.get("state") == state
            and payload.get("target_url") == identity["target_url"]
        ):
            evidence.update(
                outcome="AUTHENTICATED_SUCCESS", category="PUBLICATION_CONFIRMED"
            )
            return evidence
        # Timeout/server failure may have committed the write. No automatic retry
        # or claim of absence without independent authenticated read-back.
        evidence["outcome"] = (
            "HTTP_REJECTED"
            if status is not None and 400 <= status < 500 and status != 408
            else "AMBIGUOUS"
        )
        raise PublicationError(evidence)

    def assess(self, repository: str, pull: PullRequest) -> int:
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.repository_root / "scripts/secpal-pr-advisory.py"),
                    "--repo",
                    repository,
                    "--pr",
                    str(pull.number),
                    "--enforce",
                    "--gh",
                    self.gh,
                ],
                cwd=self.repository_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RefreshError("canonical hard-gate assessment failed") from exc
        return completed.returncode
