# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""The single GitHub read boundary of the work-graph resolver.

Every fact the resolver consumes is read here through `gh api graphql`, using
GitHub's native hierarchy, dependency, state, ordering, and closing-relationship
data. Nothing in this module mutates GitHub or persists state, and no
human-readable `gh` output is parsed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import json
import subprocess
from collections import deque
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from . import acceptance_criteria
from .model import (
    CLOSED,
    Claim,
    Node,
    OPEN,
    PRIORITY_RANKS,
    Snapshot,
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

_REFERENCE_FIELDS = "id number repository { id nameWithOwner }"

ISSUE_QUERY = f"""query WorkGraphIssue($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    issue(number: $number) {{
      id
      number
      title
      url
      state
      stateReason
      body
      repository {{ id nameWithOwner }}
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
      blocking(first: {DEPENDENCY_PAGE_SIZE}) {{
        totalCount
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {_REFERENCE_FIELDS} }}
      }}
      closedByPullRequestsReferences(first: {CLAIM_PAGE_SIZE}, includeClosedPrs: false) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{
          number
          url
          state
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


_CLAIM_SELECTION = "number url state author { login } repository { nameWithOwner }"

# Each paginated connection, keyed by the field name used in the issue query.
PAGE_QUERIES: Mapping[str, str] = {
    "subIssues": _page_query("WorkGraphSubIssues", "subIssues", SUB_ISSUE_PAGE_SIZE, _REFERENCE_FIELDS),
    "blockedBy": _page_query("WorkGraphBlockedBy", "blockedBy", DEPENDENCY_PAGE_SIZE, _REFERENCE_FIELDS),
    "blocking": _page_query("WorkGraphBlocking", "blocking", DEPENDENCY_PAGE_SIZE, _REFERENCE_FIELDS),
    "labels": _page_query("WorkGraphLabels", "labels", LABEL_PAGE_SIZE, "name"),
    "closedByPullRequestsReferences": _page_query(
        "WorkGraphClaims",
        "closedByPullRequestsReferences",
        CLAIM_PAGE_SIZE,
        _CLAIM_SELECTION,
        ", includeClosedPrs: false",
    ),
}

# Relationship inputs that a scope traversal consumes. If one is unreadable,
# even partially, section 3.5 forbids treating the readable part as the complete
# list, so the scope node stays unresolved. Dependency traversal consumes only
# `blockedBy` for cycle detection; ancestors consume neither connection.
# Observability is all-or-nothing per consumed connection.
#
# `parent` is handled separately because it is a single field: an unreadable
# parent is recorded as unobservable containment rather than an unresolved node,
# which is what keeps it distinct from a genuinely absent parent.
#
# Deliberately excluded: `labels` are selection metadata that section 1.2 keeps
# out of `READY`, claims are the exception section 4.2 allows, and `blocking`
# feeds only the advisory section 3.2 limit finding.
REQUIRED_CONNECTIONS = ("subIssues", "blockedBy")

VIEWER_QUERY = "query WorkGraphViewer { viewer { login } }"


class GitHubError(RuntimeError):
    """An operational GitHub failure. It is never converted into absent data."""


@dataclass(frozen=True)
class GraphQLResponse:
    data: Mapping[str, Any] | None
    errors: tuple[Mapping[str, Any], ...]

    def errors_touching(self, field: str) -> tuple[Mapping[str, Any], ...]:
        """Errors anywhere under ``field``, including nested and per-node paths."""
        return tuple(
            error
            for error in self.errors
            if field in [str(segment) for segment in (error.get("path") or ())]
        )


@dataclass
class GitHubGraphQLAdapter:
    """Runs one structured GraphQL document through authenticated ``gh``."""

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


@dataclass
class GitHubReadAdapter(GitHubGraphQLAdapter):
    """The canonical read-only work-graph boundary."""

    def observe_main_protection(self, repository: str, branch: str) -> Mapping[str, Any]:
        """Reuse the maintained effective-rule observer, bounded and read-only.

        Classic admin enforcement is still a mandatory qualification boundary:
        applicable rulesets alone cannot prove absence of administrative bypass.
        """
        owner, name = repository.split("/", 1)
        helper = _review_policy_owner()
        config = helper.default_config(repository)
        config.update(maximum_api_calls=12, maximum_items=1000)
        runner = helper.CommandRunner(
            executable_paths={"gh": str(Path(self.gh_executable).resolve())}
            if Path(self.gh_executable).is_absolute() else None,
            timeout_seconds=max(1, int(self.timeout)))
        client = helper.GitHubClient(runner, helper.Budget(config), owner, name, 0)
        try:
            normalized, _, _ = helper._capture_rules(client, branch, {
                "require_ruleset_evidence": True,
                "require_branch_protection_evidence": True})
            return normalized
        except (RuntimeError, ValueError, OSError):
            raise GitHubError("concurrent-completion effective protection is unavailable") from None

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


def _references(entries: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(reference for reference in (_reference(entry) for entry in entries) if reference)


def _connection_nodes(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not payload:
        return []
    return [entry for entry in (payload.get("nodes") or []) if entry]


class ConnectionUnreadable(Exception):
    """One connection could not be read completely, so its list is unknown."""

    def __init__(self, connection: str, reason: str) -> None:
        super().__init__(f"{connection} could not be read completely")
        self.connection = connection
        self.reason = reason


def _paginate(
    adapter: GitHubReadAdapter,
    connection: str,
    issue: Mapping[str, Any],
    variables: Mapping[str, Any],
    errors: tuple[Mapping[str, Any], ...] = (),
) -> list[Mapping[str, Any]]:
    """Consume every remaining page of one connection, or report it unreadable.

    A payload carrying some nodes plus an access error underneath it is a
    partial read, never a complete short list.
    """
    if errors:
        raise ConnectionUnreadable(connection, _unresolved_reason(errors))
    if issue.get(connection) is None:
        raise ConnectionUnreadable(connection, "unresolved")
    collected = _connection_nodes(issue.get(connection))
    page_info = (issue.get(connection) or {}).get("pageInfo") or {}
    seen_cursors: set[str] = set()
    while page_info.get("hasNextPage"):
        cursor = page_info.get("endCursor")
        if not cursor:
            raise GitHubError(f"{connection} reported another page without a cursor")
        if cursor in seen_cursors:
            raise GitHubError(f"{connection} repeated pagination cursor {cursor!r}")
        seen_cursors.add(cursor)
        response = adapter.query(PAGE_QUERIES[connection], {**variables, "cursor": cursor})
        page_errors = response.errors_touching(connection)
        if page_errors:
            raise ConnectionUnreadable(connection, _unresolved_reason(page_errors))
        nested = ((response.data or {}).get("repository") or {}).get("issue") or {}
        payload = nested.get(connection)
        if payload is None:
            # A page that cannot be read is not an empty page.
            raise ConnectionUnreadable(connection, "unresolved")
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


@dataclass(frozen=True)
class Fetched:
    """One issue read, under the identity GitHub itself returned for it."""

    canonical_key: str
    node: Node
    body: str | None


def _fetch(
    adapter: GitHubReadAdapter, key: str, *, required_connections: Iterable[str]
) -> Fetched:
    """Fetch one issue, or return an unresolved node under the requested key."""
    repository, number = parse_node_key(key)
    owner, name = repository.split("/", 1)
    variables = {"owner": owner, "name": name, "number": number}
    response = adapter.query(ISSUE_QUERY, variables)
    issue = ((response.data or {}).get("repository") or {}).get("issue")
    if not issue:
        return Fetched(key, unresolved_node(key, _unresolved_reason(response.errors)), None)
    if int(issue.get("number", number)) != number:
        # GitHub canonicalizes a repository spelling, never an issue number, so
        # a different number means the answer does not belong to this lookup.
        raise GitHubError(f"{key} resolved to issue number {issue.get('number')}")

    required_connections = tuple(required_connections)
    try:
        relationships = {
            connection: _references(
                _paginate(adapter, connection, issue, variables, response.errors_touching(connection))
            )
            for connection in required_connections
        }
    except ConnectionUnreadable as unreadable:
        return Fetched(key, unresolved_node(key, unreadable.reason), None)

    # Selection metadata and claims degrade on their own instead of taking the
    # node down with them, because section 1.2 keeps them out of `READY`.
    try:
        labels = {
            str(entry.get("name"))
            for entry in _paginate(adapter, "labels", issue, variables, response.errors_touching("labels"))
        }
        priority_labels_observable = True
    except ConnectionUnreadable:
        labels, priority_labels_observable = set(), False

    try:
        claim_entries = _paginate(
            adapter,
            "closedByPullRequestsReferences",
            issue,
            variables,
            response.errors_touching("closedByPullRequestsReferences"),
        )
        claims = _claims(claim_entries)
        claims_observable = True
    except ConnectionUnreadable:
        claims, claims_observable = (), False

    state_reason = issue.get("stateReason")
    body = str(issue.get("body") or "")
    node = Node(
        repository=str((issue.get("repository") or {}).get("nameWithOwner") or repository),
        number=int(issue.get("number", number)),
        node_id=str(issue.get("id") or ""),
        repository_id=str((issue.get("repository") or {}).get("id") or ""),
        title=str(issue.get("title") or ""),
        url=str(issue.get("url") or ""),
        body_digest=hashlib.sha256(body.encode()).hexdigest(),
        state=OPEN if str(issue.get("state", "")).upper() == "OPEN" else CLOSED,
        state_reason=str(state_reason).lower() if state_reason else None,
        parent=_reference(issue.get("parent")),
        parent_observable=not response.errors_touching("parent"),
        children=relationships.get("subIssues", ()),
        children_observable="subIssues" in required_connections,
        blocked_by=relationships.get("blockedBy", ()),
        dependencies_observable="blockedBy" in required_connections,
        blocking=relationships.get("blocking", ()),
        blocking_observable="blocking" in required_connections,
        blocking_count=int((issue.get("blocking") or {}).get("totalCount") or 0),
        priority_labels=tuple(sorted(label for label in labels if label in PRIORITY_RANKS)),
        priority_labels_observable=priority_labels_observable,
        claims=claims,
        claims_observable=claims_observable,
    )
    return Fetched(node.key, node, body)


SCOPE = "scope"
ANCESTOR = "ancestor"
DEPENDENCY = "dependency"
MUTATION_TARGET = "mutation_target"


def _required_connections(mode: str, include_reverse_dependencies: bool = False) -> tuple[str, ...]:
    if mode == SCOPE:
        return REQUIRED_CONNECTIONS + (("blocking",) if include_reverse_dependencies else ())
    if mode == DEPENDENCY:
        return ("blockedBy",)
    if mode == MUTATION_TARGET:
        # Post-write unchanged-relationship verification covers every mutation
        # target, including exact endpoints outside the owning subtree.
        return REQUIRED_CONNECTIONS + ("blocking",)
    # ANCESTOR deliberately observes no relationship connections. Even though
    # ISSUE_QUERY asks for them, unconsumed/unpaginated payloads stay unknown;
    # a later complete read cannot establish their historical values.
    return ()


def _needs_upgrade(node: Node, mode: str, include_reverse_dependencies: bool = False) -> bool:
    required = _required_connections(mode, include_reverse_dependencies)
    return (
        ("subIssues" in required and not node.children_observable)
        or ("blockedBy" in required and not node.dependencies_observable)
        or ("blocking" in required and not node.blocking_observable)
    )


def _merge_node(existing: Node, upgraded: Node) -> Node:
    """Increase known node facts without turning an earlier fact into absence."""
    return replace(
        upgraded,
        parent=existing.parent if existing.parent_observable and not upgraded.parent_observable else upgraded.parent,
        parent_observable=existing.parent_observable or upgraded.parent_observable,
        children=upgraded.children if upgraded.children_observable else existing.children,
        children_observable=existing.children_observable or upgraded.children_observable,
        blocked_by=upgraded.blocked_by if upgraded.dependencies_observable else existing.blocked_by,
        dependencies_observable=existing.dependencies_observable or upgraded.dependencies_observable,
        blocking=upgraded.blocking if upgraded.blocking_observable else existing.blocking,
        blocking_observable=existing.blocking_observable or upgraded.blocking_observable,
        priority_labels=(
            upgraded.priority_labels
            if upgraded.priority_labels_observable
            else existing.priority_labels
        ),
        priority_labels_observable=(
            existing.priority_labels_observable or upgraded.priority_labels_observable
        ),
        claims=upgraded.claims if upgraded.claims_observable else existing.claims,
        claims_observable=existing.claims_observable or upgraded.claims_observable,
    )


def load_snapshot(
    adapter: GitHubReadAdapter,
    scope_root: str,
    *,
    node_executable: str = "node",
    parser_environment: Mapping[str, str] | None = None,
    include_reverse_dependencies: bool = False,
    mutation_targets: Iterable[str] = (),
) -> tuple[Snapshot, str]:
    """Collect one immutable snapshot for ``scope_root``.

    Traversal reads exactly what the canonical predicates need: the scope root's
    subtree, the ancestors section 4.1 evaluates, and the transitive dependency
    targets section 3.5 needs to detect unsatisfied edges and cycles. Ancestors
    contribute their own containment chain only, because section 3.2 never
    inherits dependencies and siblings above the scope root are out of scope.

    Returns the snapshot together with the canonical scope root, because GitHub
    accepts repository spellings it then canonicalizes. Every node is keyed by
    the identity GitHub returned, so one issue is never two graph nodes.
    """
    fetched: dict[str, Node] = {}
    bodies: dict[str, str] = {}
    canonical: dict[str, str] = {}
    expanded: set[tuple[str, str]] = set()
    pending: deque[tuple[str, str]] = deque(
        [(scope_root, SCOPE), *((target, MUTATION_TARGET) for target in mutation_targets)]
    )

    while pending:
        requested, mode = pending.popleft()
        key = canonical.get(requested, requested)
        if (key, mode) in expanded:
            continue

        cached = fetched.get(key)
        if cached is None or (
            cached.resolved and _needs_upgrade(cached, mode, include_reverse_dependencies)
        ):
            if cached is None and len(fetched) >= adapter.max_nodes:
                raise GitHubError(
                    f"graph exceeds the configured budget of {adapter.max_nodes} issues; "
                    "narrow the scope root"
                )
            result = _fetch(
                adapter,
                requested,
                required_connections=_required_connections(mode, include_reverse_dependencies),
            )
            key, node = result.canonical_key, result.node
            if key != requested:
                canonical[requested] = key
            if (key, mode) in expanded:
                continue
            fetched[key] = node if cached is None else _merge_node(cached, node)
            node = fetched[key]
            if result.body is None:
                expanded.add((key, mode))
                if requested == scope_root:
                    raise GitHubError(
                        f"cannot resolve the scope root {scope_root}: {node.unresolved_reason}"
                    )
                continue
            bodies[key] = result.body
        elif not cached.resolved:
            expanded.add((key, mode))
            continue
        else:
            node = cached

        expanded.add((key, mode))
        if mode == SCOPE:
            pending.extend((child, SCOPE) for child in node.children)
            pending.extend((target, DEPENDENCY) for target in node.blocked_by)
            if node.parent:
                pending.append((node.parent, ANCESTOR))
            if include_reverse_dependencies:
                pending.extend((target, MUTATION_TARGET) for target in node.blocking)
        elif mode == ANCESTOR:
            if node.parent:
                pending.append((node.parent, ANCESTOR))
        elif mode == MUTATION_TARGET:
            pending.extend((target, DEPENDENCY) for target in node.blocked_by)
            if node.parent:
                pending.append((node.parent, ANCESTOR))
        else:
            pending.extend((target, DEPENDENCY) for target in node.blocked_by)

    ordered_bodies = list(bodies)
    structural = dict(
        zip(
            ordered_bodies,
            acceptance_criteria.parse(
                [bodies[key] for key in ordered_bodies],
                node_executable=node_executable,
                environment=parser_environment,
            ),
        )
    )
    snapshot = Snapshot(
        {
            key: (
                replace(
                    node,
                    has_acceptance_criteria=structural[key].has_acceptance_criteria,
                    mirror_relationships=structural[key].relationship_mirrors,
                )
                if key in structural
                else node
            )
            for key, node in fetched.items()
        }
    )
    return snapshot, canonical.get(scope_root, scope_root)


def resolve_reference(reference: str, *, default_repository: str | None = None) -> str:
    """Normalize a user-supplied issue reference to a canonical identity.

    Every accepted form is validated here, so an unusable reference is invalid
    input rather than a failure deeper in the read boundary.
    """
    value = reference.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        parts = [part for part in parsed.path.split("/") if part]
        if (
            parsed.hostname == "github.com"
            and len(parts) == 4
            and parts[2] == "issues"
            and parts[3].isdigit()
        ):
            return _canonical(f"{parts[0]}/{parts[1]}", parts[3], reference)
        raise ValueError(f"not a GitHub issue URL: {reference}")
    if "#" in value:
        repository, _, number = value.rpartition("#")
        if repository:
            return _canonical(repository, number, reference)
        value = number
    if not value.isdigit():
        raise ValueError(f"not an issue reference: {reference}")
    if not default_repository:
        raise ValueError(f"{reference} needs a repository; use owner/repo#number or --repo")
    return _canonical(default_repository, value, reference)


def _canonical(repository: str, number: str, reference: str) -> str:
    if not number.isdigit():
        raise ValueError(f"not an issue number in {reference}")
    key = node_key(repository, int(number))
    try:
        parse_node_key(key)
    except ValueError as error:
        raise ValueError(f"{reference} is not repository-qualified as owner/repo#number") from error
    return key


@cache
def _review_policy_owner():
    """Load the existing rule semantics owner; define no parallel policy."""
    path = Path(__file__).resolve().parents[1] / "secpal-pr-review.py"
    name = "_secpal_work_graph_review_policy"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_COMPLETION_TOKEN = object()


def _completion_digest(value) -> str:
    return hashlib.sha256(json.dumps(
        {k: v for k, v in vars(value).items() if k != "_seal"},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _seal_completion(value):
    """Seal only the provider reader's independently reauthenticated result."""
    return replace(value, _seal=(_COMPLETION_TOKEN, _completion_digest(value)))


def require_observed_completion(value) -> None:
    from .replanning import ConcurrentCompletion, PlanError
    seal = getattr(value, "_seal", None)
    if (type(value) is not ConcurrentCompletion or not isinstance(seal, tuple)
            or len(seal) != 2 or seal[0] is not _COMPLETION_TOKEN
            or seal[1] != _completion_digest(value)):
        raise PlanError("concurrent completion has no authenticated provider provenance")


# Completion observations use native closing links, complete state-event history,
# and a pinned protected-main history. They never consume request assertions.
_COMPLETION_CORE = f"""id number state stateReason body
parent {{ {_REFERENCE_FIELDS} }}"""
_COMPLETION_EVENTS = """__typename
... on ClosedEvent { id createdAt actor { login ... on User { id } } }
... on ReopenedEvent { id createdAt actor { login ... on User { id } } }"""
_COMPLETION_CLOSERS = """closedByPullRequestsReferences(first: 2, includeClosedPrs: true) {
  totalCount pageInfo { hasNextPage }
  nodes { id number state mergedAt mergedBy { login ... on User { id } }
    baseRefName repository { id nameWithOwner }
    mergeCommit { oid signature { isValid } }
  }
}"""
_COMPLETION_MAIN = """name
branchProtectionRule { isAdminEnforced requiresStrictStatusChecks }
target { ... on Commit { oid } }"""
COMPLETION_QUERY = f"""query WorkGraphCompletion($owner:String!, $name:String!, $number:Int!) {{
  repository(owner:$owner, name:$name) {{
    id nameWithOwner
    defaultBranchRef {{ {_COMPLETION_MAIN}
      target {{ ... on Commit {{ history(first:100) {{
        nodes {{ oid }} pageInfo {{ hasNextPage endCursor }}
      }} }} }}
    }}
    issue(number:$number) {{ {_COMPLETION_CORE} {_COMPLETION_CLOSERS}
      timelineItems(first:50, itemTypes:[CLOSED_EVENT, REOPENED_EVENT]) {{
        nodes {{ {_COMPLETION_EVENTS} }} pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}"""
COMPLETION_TIMELINE_QUERY = f"""query WorkGraphCompletionEvents(
  $owner:String!, $name:String!, $number:Int!, $cursor:String!) {{
  repository(owner:$owner, name:$name) {{ id nameWithOwner
    issue(number:$number) {{ {_COMPLETION_CORE}
      timelineItems(first:50, after:$cursor, itemTypes:[CLOSED_EVENT, REOPENED_EVENT]) {{
        nodes {{ {_COMPLETION_EVENTS} }} pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}"""
COMPLETION_HISTORY_QUERY = """query WorkGraphCompletionHistory(
  $owner:String!, $name:String!, $oid:String!, $cursor:String!) {
  repository(owner:$owner, name:$name) { id nameWithOwner
    object(expression:$oid) { ... on Commit { oid history(first:100, after:$cursor) {
      nodes { oid } pageInfo { hasNextPage endCursor }
    } } }
  }
}"""
COMPLETION_REAUTH_QUERY = f"""query WorkGraphCompletionReadback(
  $owner:String!, $name:String!, $number:Int!) {{
  repository(owner:$owner, name:$name) {{ id nameWithOwner
    defaultBranchRef {{ {_COMPLETION_MAIN} }}
    issue(number:$number) {{ {_COMPLETION_CORE} {_COMPLETION_CLOSERS}
      timelineItems(last:1, itemTypes:[CLOSED_EVENT, REOPENED_EVENT]) {{
        nodes {{ {_COMPLETION_EVENTS} }}
      }}
    }}
  }}
}}"""


def _completion_issue_projection(issue: Mapping[str, Any]) -> tuple:
    """Normalize only actually returned core fields; never invent omitted data."""
    from .replanning import content_digest

    if not isinstance(issue["body"], str):
        raise ValueError
    return (issue["id"], issue["number"], issue["state"].lower(),
            issue["stateReason"].lower() if issue["stateReason"] else None,
            content_digest(issue["body"]), _reference(issue["parent"]))


def _completion_pr_projection(issue: Mapping[str, Any]) -> tuple:
    connection = issue["closedByPullRequestsReferences"]
    if (connection["totalCount"] != 1 or connection["pageInfo"]["hasNextPage"] is not False
            or len(connection["nodes"]) != 1):
        raise ValueError
    pull = connection["nodes"][0]
    return (pull["id"], pull["number"], pull["state"], pull["baseRefName"],
            pull["repository"]["id"], pull["repository"]["nameWithOwner"],
            pull["mergedAt"], pull["mergedBy"]["id"], pull["mergeCommit"]["oid"],
            (pull["mergeCommit"]["signature"] or {}).get("isValid"))


def _completion_main_projection(reference: Mapping[str, Any]) -> tuple:
    protection = reference["branchProtectionRule"]
    return (reference["name"], reference["target"]["oid"],
            protection["isAdminEnforced"], protection["requiresStrictStatusChecks"])


def _completion_event_projection(event: Mapping[str, Any]) -> tuple:
    return (event["id"], event["__typename"], event["createdAt"],
            (event.get("actor") or {}).get("id", ""))


def observe_completion(
    adapter: GitHubReadAdapter, current: Node, *, started_at: str
):
    """Read one completion with ten-page bounds and independent final readback.

    `started_at` comes from the authenticated signed operation, never JSON input.
    The policy owner separately admits these normalized facts; observing is not
    permission to ignore a changed mutation endpoint.
    """
    from datetime import datetime, timezone
    from .replanning import ConcurrentCompletion

    repository, number = parse_node_key(current.key)
    owner, name = repository.split("/", 1)
    variables = {"owner": owner, "name": name, "number": number}

    def read(query, arguments):
        try:
            response = adapter.query(query, arguments)
        except GitHubError:
            raise GitHubError("concurrent-completion provider query failed") from None
        if response.errors:
            raise GitHubError("concurrent-completion provider observation is incomplete")
        result = (response.data or {}).get("repository")
        if (not isinstance(result, dict) or result.get("id") != current.repository_id
                or result.get("nameWithOwner") != repository):
            raise GitHubError("concurrent-completion repository identity changed")
        return result

    def connection_page(connection, maximum):
        nodes, page = connection["nodes"], connection["pageInfo"]
        if (not isinstance(nodes, list) or len(nodes) > maximum
                or type(page["hasNextPage"]) is not bool):
            raise ValueError
        return nodes, page

    try:
        initial = read(COMPLETION_QUERY, variables)
        issue = initial["issue"]
        core = _completion_issue_projection(issue)
        if core != (current.node_id, number, current.state, current.state_reason,
                    current.body_digest, current.parent):
            raise GitHubError("concurrent-completion current issue observation changed")
        pull = _completion_pr_projection(issue)
        main = _completion_main_projection(initial["defaultBranchRef"])
        protection = adapter.observe_main_protection(repository, main[0])
        if pull[5] != repository:
            raise GitHubError("concurrent-completion closing repository is foreign")

        events = []
        connection = issue["timelineItems"]
        cursors = set()
        for page_number in range(10):
            nodes, page = connection_page(connection, 50)
            events.extend(_completion_event_projection(event) for event in nodes)
            if not page["hasNextPage"]:
                break
            if page_number == 9:
                raise GitHubError("concurrent-completion event history exceeds its bound")
            cursor = page["endCursor"]
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise ValueError
            cursors.add(cursor)
            result = read(COMPLETION_TIMELINE_QUERY, {**variables, "cursor": cursor})
            if _completion_issue_projection(result["issue"]) != core:
                raise GitHubError("concurrent-completion issue changed during pagination")
            connection = result["issue"]["timelineItems"]
        else:
            raise GitHubError("concurrent-completion event history exceeds its bound")

        history = []
        connection = initial["defaultBranchRef"]["target"]["history"]
        cursors = set()
        for page_number in range(10):
            nodes, page = connection_page(connection, 100)
            history.extend(node["oid"] for node in nodes)
            if pull[8] in history or not page["hasNextPage"]:
                break
            if page_number == 9:
                raise GitHubError("concurrent-completion main ancestry exceeds its bound")
            cursor = page["endCursor"]
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise ValueError
            cursors.add(cursor)
            result = read(COMPLETION_HISTORY_QUERY,
                          {"owner": owner, "name": name, "oid": main[1], "cursor": cursor})
            if result["object"]["oid"] != main[1]:
                raise GitHubError("concurrent-completion pinned main identity changed")
            connection = result["object"]["history"]
        else:
            raise GitHubError("concurrent-completion main ancestry exceeds its bound")

        final = read(COMPLETION_REAUTH_QUERY, variables)
        final_protection = adapter.observe_main_protection(repository, main[0])
        if (final_protection != protection
                or _completion_issue_projection(final["issue"]) != core
                or _completion_pr_projection(final["issue"]) != pull
                or _completion_main_projection(final["defaultBranchRef"]) != main
                or not events
                or tuple(_completion_event_projection(event)
                         for event in final["issue"]["timelineItems"]["nodes"]) != (events[-1],)):
            raise GitHubError("concurrent-completion independent readback changed")
    except (KeyError, TypeError, AttributeError, ValueError):
        raise GitHubError("concurrent-completion provider representation is incomplete") from None

    return _seal_completion(ConcurrentCompletion(
        issue_key=current.key, issue_node_id=core[0], repository_id=current.repository_id,
        current_state=core[2], current_state_reason=core[3], current_body_digest=core[4],
        current_parent=core[5], closing_pr_key=node_key(repository, pull[1]),
        closing_pr_node_id=pull[0], closing_pr_repository_id=pull[4],
        closing_pr_base_ref=pull[3], closing_pr_state=pull[2], merged_at=pull[6],
        merged_by_id=pull[7], merge_oid=pull[8], merge_signature_valid=pull[9],
        main_name=main[0], main_oid=main[1], main_admin_enforced=main[2], main_strict=main[3],
        history_oids=tuple(history), state_events=tuple(events), started_at=started_at,
        observed_at=datetime.now(timezone.utc).isoformat(),
    ))
