# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Bounded refresh of mutable work-graph evidence on open PR heads."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

HARD_CONTEXT = "Work-Graph PR Gate"
DEFAULT_MAXIMUM_PULL_REQUESTS = 100
_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
_OID = re.compile(r"^[0-9a-f]{40,64}$")


class RefreshError(RuntimeError):
    """The hard-gate candidate set or authenticated refresh failed."""


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

    def publish(
        self,
        repository: str,
        pull: PullRequest,
        state: str,
        description: str,
    ) -> None: ...

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
    candidates = gateway.open_pull_requests(repository, maximum_pull_requests)
    if len(candidates) > maximum_pull_requests:
        raise RefreshError("bounded candidate limit was exceeded")
    if len({pull.number for pull in candidates}) != len(candidates) or len(
        {pull.head_sha for pull in candidates}
    ) != len(candidates):
        raise RefreshError("open pull-request candidates are duplicated")

    # Publish every pending state first. If invalidation cannot cover the whole
    # finite set, no candidate is reassessed and already-invalidated heads stay
    # fail closed.
    for pull in candidates:
        gateway.publish(
            repository,
            pull,
            "pending",
            "Mutable work-graph evidence is being refreshed",
        )

    failed: list[int] = []
    unavailable: list[int] = []
    for pull in candidates:
        result = gateway.assess(repository, pull)
        if result == 0:
            state = "success"
            description = "Current canonical work-graph evidence passed"
        elif result == 1:
            state = "failure"
            description = "Current canonical work-graph evidence blocked delivery"
            failed.append(pull.number)
        else:
            state = "error"
            description = "Current canonical work-graph evidence is unavailable"
            unavailable.append(pull.number)
        gateway.publish(repository, pull, state, description)

    return {
        "schema": "secpal-work-graph-gate-refresh/v1",
        "repository": repository,
        "context": HARD_CONTEXT,
        "candidate_count": len(candidates),
        "refreshed": len(candidates),
        "failed": failed,
        "unavailable": unavailable,
    }


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
        except (OSError, subprocess.SubprocessError) as exc:
            raise RefreshError("authenticated GitHub command failed") from exc

    def open_pull_requests(self, repository: str, limit: int) -> tuple[PullRequest, ...]:
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

    def publish(
        self,
        repository: str,
        pull: PullRequest,
        state: str,
        description: str,
    ) -> None:
        if state not in {"pending", "success", "failure", "error"}:
            raise RefreshError("commit status state is invalid")
        result = self._run(
            [
                "api",
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
                f"target_url=https://github.com/{repository}/pull/{pull.number}",
            ]
        )
        if result.returncode != 0:
            raise RefreshError("hard-gate commit status publication failed")

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
