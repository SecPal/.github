# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""The single GitHub read boundary of the work-graph resolver.

Every fact the resolver consumes is read here through `gh api graphql`, using
GitHub's native hierarchy, dependency, state, ordering, and closing-relationship
data. Nothing in this module mutates GitHub or persists state, and no
human-readable `gh` output is parsed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

from . import acceptance_criteria
from .model import (
    CLOSED,
    Claim,
    Node,
    OPEN,
    PRIORITY_RANKS,
    Snapshot,
    mirror_relationships,
    node_key,
    parse_node_key,
    unresolved_node,
)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_NODES = 1000
SUB_ISSUE_PAGE_SIZE = 100
DEPENDENCY_PAGE_SIZE = 50
LABEL_PAGE_SIZE = 100
CLAIM_PAGE_SIZE = 50

# GraphQL error types that describe one unreadable node rather than an
# operational failure of the invocation.
UNRESOLVED_ERROR_TYPES = frozenset({"NOT_FOUND", "FORBIDDEN"})

_REFERENCE_FIELDS = "number repository { nameWithOwner }"

ISSUE_QUERY = f"""query WorkGraphIssue($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    issue(number: $number) {{
      number
      title
      url
      state
      stateReason
      body
      repository {{ nameWithOwner }}
      parent {{ {_REFERENCE_FIELDS} }}
      labels(first: {LABEL_PAGE_SIZE}) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ name }}
      }}
      subIssues(first: {SUB_ISSUE_PAGE_SIZE}) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {_REFERENCE_FIELDS} }}
      }}
      blockedBy(first: {DEPENDENCY_PAGE_SIZE}) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {_REFERENCE_FIELDS} }}
      }}
      blocking(first: 1) {{ totalCount }}
      closedByPullRequestsReferences(first: {CLAIM_PAGE_SIZE}, includeClosedPrs: false) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{
          number
          url
          state
          isDraft
          author {{ login }}
          repository {{ nameWithOwner }}
        }}
      }}
    }}
  }}
}}"""


def _page_query(
    operation: str, connection: str, page_size: int, selection: str, extra_arguments: str = ""
) -> str:
    return f"""query {operation}($owner: String!, $name: String!, $number: Int!, $cursor: String!) {{
  repository(owner: $owner, name: $name) {{
    issue(number: $number) {{
      {connection}(first: {page_size}, after: $cursor{extra_arguments}) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {selection} }}
      }}
    }}
  }}
}}"""


_CLAIM_SELECTION = "number url state isDraft author { login } repository { nameWithOwner }"

# Each paginated connection, keyed by the field name used in the issue query.
PAGE_QUERIES: Mapping[str, str] = {
    "subIssues": _page_query("WorkGraphSubIssues", "subIssues", SUB_ISSUE_PAGE_SIZE, _REFERENCE_FIELDS),
    "blockedBy": _page_query("WorkGraphBlockedBy", "blockedBy", DEPENDENCY_PAGE_SIZE, _REFERENCE_FIELDS),
    "labels": _page_query("WorkGraphLabels", "labels", LABEL_PAGE_SIZE, "name"),
    "closedByPullRequestsReferences": _page_query(
        "WorkGraphClaims",
        "closedByPullRequestsReferences",
        CLAIM_PAGE_SIZE,
        _CLAIM_SELECTION,
        ", includeClosedPrs: false",
    ),
}

# Connections whose absence means the native relationship data is unreadable.
# Section 3.5 forbids treating that as "no relationship"; claims are the single
# exception the contract allows (section 4.2).
REQUIRED_CONNECTIONS = ("labels", "subIssues", "blockedBy", "blocking")

VIEWER_QUERY = "query WorkGraphViewer { viewer { login } }"


class GitHubError(RuntimeError):
    """An operational GitHub failure. It is never converted into absent data."""


@dataclass(frozen=True)
class GraphQLResponse:
    data: Mapping[str, Any] | None
    errors: tuple[Mapping[str, Any], ...]

    def errors_under(self, *path_tail: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(error for error in self.errors if tuple(error.get("path") or ())[-1:] == path_tail)


@dataclass
class GitHubReadAdapter:
    """Runs read-only GraphQL documents through the `gh` CLI."""

    gh_executable: str = "gh"
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_nodes: int = DEFAULT_MAX_NODES
    environment: Mapping[str, str] | None = None

    def query(self, document: str, variables: Mapping[str, Any]) -> GraphQLResponse:
        payload = json.dumps({"query": document, "variables": dict(variables)})
        try:
            completed = subprocess.run(
                [self.gh_executable, "api", "graphql", "--input", "-"],
                input=payload,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout,
                env=dict(self.environment) if self.environment is not None else None,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GitHubError(f"cannot run {self.gh_executable}: {error}") from error

        if not completed.stdout.strip():
            raise GitHubError(
                f"gh produced no response (exit {completed.returncode}): {completed.stderr.strip()}"
            )
        try:
            body = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise GitHubError(f"unreadable gh response: {error}") from error
        if not isinstance(body, dict):
            raise GitHubError("unreadable gh response: expected a JSON object")

        errors = tuple(body.get("errors") or ())
        fatal = [error for error in errors if error.get("type") not in UNRESOLVED_ERROR_TYPES]
        if fatal:
            raise GitHubError("; ".join(str(error.get("message", error)) for error in fatal))
        return GraphQLResponse(body.get("data"), errors)

    def viewer_login(self) -> str:
        """Resolve the invocation-context executor identity from `gh` authentication."""
        response = self.query(VIEWER_QUERY, {})
        login = ((response.data or {}).get("viewer") or {}).get("login")
        if not login:
            raise GitHubError("cannot resolve the authenticated GitHub identity")
        return str(login)


def _reference(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    repository = (payload.get("repository") or {}).get("nameWithOwner")
    number = payload.get("number")
    if not repository or number is None:
        return None
    return node_key(str(repository), int(number))


def _connection_nodes(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not payload:
        return []
    return [entry for entry in (payload.get("nodes") or []) if entry]


def _paginate(
    adapter: GitHubReadAdapter,
    connection: str,
    issue: Mapping[str, Any],
    variables: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Consume every remaining page of one connection."""
    collected = _connection_nodes(issue.get(connection))
    page_info = (issue.get(connection) or {}).get("pageInfo") or {}
    while page_info.get("hasNextPage"):
        cursor = page_info.get("endCursor")
        if not cursor:
            raise GitHubError(f"{connection} reported another page without a cursor")
        response = adapter.query(PAGE_QUERIES[connection], {**variables, "cursor": cursor})
        nested = ((response.data or {}).get("repository") or {}).get("issue") or {}
        payload = nested.get(connection)
        if payload is None:
            # A page that cannot be read is not an empty page.
            raise GitHubError(f"{connection} page after {cursor} could not be read")
        collected.extend(_connection_nodes(payload))
        page_info = payload.get("pageInfo") or {}
    return collected


def _claims(entries: Iterable[Mapping[str, Any]]) -> tuple[Claim, ...]:
    """Section 4.2: an open primary delivery pull request with a named author."""
    claims = []
    for entry in entries:
        if str(entry.get("state", "")).upper() != "OPEN":
            continue
        login = (entry.get("author") or {}).get("login")
        if not login:
            continue
        repository = (entry.get("repository") or {}).get("nameWithOwner")
        number = entry.get("number")
        if not repository or number is None:
            continue
        claims.append(Claim(str(login), node_key(str(repository), int(number)), str(entry.get("url") or "")))
    return tuple(sorted(claims))


def _unresolved_reason(errors: Iterable[Mapping[str, Any]]) -> str:
    return next((str(error.get("type")) for error in errors if error.get("type")), "unresolved")


def _fetch(adapter: GitHubReadAdapter, key: str) -> tuple[Node, str | None]:
    """Fetch one issue. Returns the raw node and its body, or an unresolved node."""
    repository, number = parse_node_key(key)
    owner, name = repository.split("/", 1)
    variables = {"owner": owner, "name": name, "number": number}
    response = adapter.query(ISSUE_QUERY, variables)
    issue = ((response.data or {}).get("repository") or {}).get("issue")
    if not issue:
        return unresolved_node(key, _unresolved_reason(response.errors)), None
    if any(issue.get(connection) is None for connection in REQUIRED_CONNECTIONS):
        return unresolved_node(key, _unresolved_reason(response.errors)), None

    claims_errors = response.errors_under("closedByPullRequestsReferences")
    claims_observable = not claims_errors and issue.get("closedByPullRequestsReferences") is not None

    labels = {str(entry.get("name")) for entry in _paginate(adapter, "labels", issue, variables)}
    children = tuple(
        reference
        for reference in (
            _reference(entry) for entry in _paginate(adapter, "subIssues", issue, variables)
        )
        if reference
    )
    blocked_by = tuple(
        reference
        for reference in (
            _reference(entry) for entry in _paginate(adapter, "blockedBy", issue, variables)
        )
        if reference
    )
    claims = (
        _claims(_paginate(adapter, "closedByPullRequestsReferences", issue, variables))
        if claims_observable
        else ()
    )

    state_reason = issue.get("stateReason")
    node = Node(
        repository=str((issue.get("repository") or {}).get("nameWithOwner") or repository),
        number=int(issue.get("number", number)),
        title=str(issue.get("title") or ""),
        url=str(issue.get("url") or ""),
        state=OPEN if str(issue.get("state", "")).upper() == "OPEN" else CLOSED,
        state_reason=str(state_reason).lower() if state_reason else None,
        parent=_reference(issue.get("parent")),
        children=children,
        blocked_by=blocked_by,
        blocking_count=int((issue.get("blocking") or {}).get("totalCount") or 0),
        priority_labels=tuple(sorted(label for label in labels if label in PRIORITY_RANKS)),
        claims=claims,
        claims_observable=claims_observable,
        mirror_relationships=mirror_relationships(issue.get("body")),
    )
    return node, issue.get("body") or ""


SCOPE = "scope"
ANCESTOR = "ancestor"
DEPENDENCY = "dependency"


def load_snapshot(adapter: GitHubReadAdapter, scope_root: str) -> Snapshot:
    """Collect one immutable snapshot for ``scope_root``.

    Traversal reads exactly what the canonical predicates need: the scope root's
    subtree, the ancestors section 4.1 evaluates, and the transitive dependency
    targets section 3.5 needs to detect unsatisfied edges and cycles. Ancestors
    contribute their own containment chain only, because section 3.2 never
    inherits dependencies and siblings above the scope root are out of scope.
    """
    fetched: dict[str, Node] = {}
    bodies: dict[str, str] = {}
    expanded: set[tuple[str, str]] = set()
    pending: list[tuple[str, str]] = [(scope_root, SCOPE)]

    while pending:
        key, mode = pending.pop(0)
        if (key, mode) in expanded:
            continue
        expanded.add((key, mode))

        node = fetched.get(key)
        if node is None:
            if len(fetched) >= adapter.max_nodes:
                raise GitHubError(
                    f"graph exceeds the configured budget of {adapter.max_nodes} issues; "
                    "narrow the scope root"
                )
            node, body = _fetch(adapter, key)
            fetched[key] = node
            if body is None:
                if key == scope_root:
                    raise GitHubError(
                        f"cannot resolve the scope root {scope_root}: {node.unresolved_reason}"
                    )
                continue
            bodies[key] = body
        elif not node.resolved:
            continue

        if mode == SCOPE:
            pending.extend((child, SCOPE) for child in node.children)
            pending.extend((target, DEPENDENCY) for target in node.blocked_by)
            if node.parent:
                pending.append((node.parent, ANCESTOR))
        elif mode == ANCESTOR:
            if node.parent:
                pending.append((node.parent, ANCESTOR))
        else:
            pending.extend((target, DEPENDENCY) for target in node.blocked_by)

    ordered_bodies = list(bodies)
    detected = dict(zip(ordered_bodies, acceptance_criteria.detect([bodies[key] for key in ordered_bodies])))
    return Snapshot(
        {
            key: (replace(node, has_acceptance_criteria=detected[key]) if key in detected else node)
            for key, node in fetched.items()
        }
    )


def resolve_reference(reference: str, *, default_repository: str | None = None) -> str:
    """Normalize a user-supplied issue reference to a canonical identity."""
    value = reference.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parts = [part for part in value.split("/") if part]
        if len(parts) >= 5 and parts[-2] in {"issues", "pull"}:
            return node_key(f"{parts[-4]}/{parts[-3]}", int(parts[-1]))
        raise ValueError(f"not a GitHub issue URL: {reference}")
    if "#" in value:
        repository, _, number = value.rpartition("#")
        if repository:
            return node_key(repository, int(number))
        value = number
    if not value.isdigit():
        raise ValueError(f"not an issue reference: {reference}")
    if not default_repository:
        raise ValueError(f"{reference} needs a repository; use owner/repo#number or --repo")
    return node_key(default_repository, int(value))
