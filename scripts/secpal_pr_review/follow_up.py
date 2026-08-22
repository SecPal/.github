# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Canonical tracked-follow-up identity and live work-graph verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class FollowUpError(ValueError):
    """Tracked follow-up evidence is malformed or no longer valid."""


@dataclass(frozen=True)
class FollowUpIdentity:
    repository: str
    issue_number: int
    issue_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
        }


@dataclass(frozen=True)
class LiveFollowUpState:
    identity: FollowUpIdentity
    open: bool
    structurally_complete: bool
    blocked: bool
    malformed: bool
    graph_complete: bool


@dataclass
class _BudgetedGitHubReadAdapter:
    """Charge each canonical adapter query to the caller's shared authority."""

    delegate: Any
    query_consumer: Callable[[Any], None]
    query_context: Any

    @property
    def max_nodes(self) -> int:
        return self.delegate.max_nodes

    def query(self, document: str, variables: Mapping[str, Any]) -> Any:
        self.query_consumer(self.query_context)
        return self.delegate.query(document, variables)


def parse_follow_up(value: Any) -> FollowUpIdentity:
    """Require one exact canonical GitHub issue identity."""

    if not isinstance(value, dict) or set(value) != {
        "repository",
        "issue_number",
        "issue_url",
    }:
        raise FollowUpError("follow-up identity is missing or malformed")
    repository = value.get("repository")
    issue_number = value.get("issue_number")
    issue_url = value.get("issue_url")
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise FollowUpError("follow-up repository identity is malformed")
    if (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number < 1
    ):
        raise FollowUpError("follow-up issue number must be positive")
    expected_url = f"https://github.com/{repository}/issues/{issue_number}"
    if not isinstance(issue_url, str) or issue_url != expected_url:
        raise FollowUpError(
            "follow-up URL must exactly match its repository and issue number"
        )
    return FollowUpIdentity(repository, issue_number, issue_url)


def read_live_follow_up(
    identity: FollowUpIdentity,
    *,
    gh_executable: str = "gh",
    environment: Mapping[str, str] | None = None,
    node_executable: str = "node",
    parser_environment: Mapping[str, str] | None = None,
    adapter: Any | None = None,
    query_consumer: Callable[[Any], None] | None = None,
    query_context: Any = None,
) -> LiveFollowUpState:
    """Read the exact issue through the canonical work-graph implementation."""

    try:
        from secpal_work_graph import github, resolver
        from secpal_work_graph.acceptance_criteria import MarkdownParserUnavailable
    except ImportError as exc:
        raise FollowUpError("canonical work-graph implementation is unavailable") from exc
    try:
        requested = f"{identity.repository}#{identity.issue_number}"
        canonical_adapter = adapter or github.GitHubReadAdapter(
            gh_executable=gh_executable,
            environment=environment,
        )
        graph_adapter = (
            canonical_adapter
            if query_consumer is None
            else _BudgetedGitHubReadAdapter(
                canonical_adapter,
                query_consumer,
                query_context,
            )
        )
        snapshot, canonical = github.load_snapshot(
            graph_adapter,
            requested,
            node_executable=node_executable,
            parser_environment=parser_environment,
        )
        resolution = resolver.resolve(snapshot, canonical)
    except (github.GitHubError, MarkdownParserUnavailable, resolver.ScopeRootUnresolved) as exc:
        raise FollowUpError("follow-up issue is missing or inaccessible") from exc
    node = snapshot.get(canonical)
    state = resolution.states.get(canonical)
    if node is None or state is None:
        raise FollowUpError("follow-up issue is missing or inaccessible")
    repository, _, number = canonical.rpartition("#")
    live_identity = FollowUpIdentity(
        repository=repository,
        issue_number=int(number),
        issue_url=node.url,
    )
    return LiveFollowUpState(
        identity=live_identity,
        open=state.open,
        structurally_complete=node.has_acceptance_criteria,
        blocked=state.blocked,
        malformed=state.malformed or resolution.structurally_malformed,
        graph_complete=resolution.complete,
    )


def verify_live_follow_up(
    identity: FollowUpIdentity,
    *,
    state: LiveFollowUpState | None = None,
    state_reader: Callable[[FollowUpIdentity], LiveFollowUpState] = read_live_follow_up,
) -> LiveFollowUpState:
    """Fail closed unless the authenticated issue remains open and complete."""

    try:
        observed_state = state if state is not None else state_reader(identity)
    except FollowUpError:
        raise
    except Exception as exc:
        raise FollowUpError("follow-up issue is missing or inaccessible") from exc
    if (
        not isinstance(observed_state, LiveFollowUpState)
        or observed_state.identity != identity
    ):
        raise FollowUpError("follow-up live identity does not match authenticated evidence")
    if not observed_state.open:
        raise FollowUpError("follow-up issue is closed")
    if not observed_state.structurally_complete:
        raise FollowUpError("follow-up issue is structurally incomplete")
    if observed_state.malformed:
        raise FollowUpError("follow-up canonical graph state is malformed")
    if not observed_state.graph_complete:
        raise FollowUpError("follow-up canonical graph state is incomplete")
    return observed_state
