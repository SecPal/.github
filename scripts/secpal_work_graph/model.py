# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Immutable normalized work-graph snapshot.

Semantics: docs/work-graph-contract.md. This module only declares the inputs the
contract consumes; it derives nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

OPEN = "open"
CLOSED = "closed"
COMPLETED = "completed"

# Section 4.3 recognizes exactly these label names, by exact name.
PRIORITY_RANKS: Mapping[str, int] = MappingProxyType(
    {
        "priority: blocker": 3,
        "priority: high": 2,
        "priority: medium": 1,
    }
)
UNRECOGNIZED_PRIORITY_RANK = 0

# Native GitHub limits named by sections 2.2 and 3.2.
MAX_SUB_ISSUES_PER_PARENT = 100
MAX_NESTING_DEPTH = 8
MAX_DEPENDENCIES_PER_TYPE = 50

_REFERENCE = re.compile(r"^(?P<repository>[^/\s]+/[^/#\s]+)#(?P<number>\d+)$")

# Bootstrap mirrors named by section 1. They are reported for migration and
# never read as graph state, so a textual scan is the whole of their handling.
_MIRROR_PATTERN = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?(?:\*\*|__)?(parent|order|blocked by|blocks|depends on)(?:\*\*|__)?[ \t]*:",
    re.IGNORECASE | re.MULTILINE,
)


def node_key(repository: str, number: int) -> str:
    """Return the canonical repository-qualified identity of an issue."""
    return f"{repository}#{number}"


def parse_node_key(reference: str) -> tuple[str, int]:
    """Split a canonical ``owner/repo#number`` identity."""
    match = _REFERENCE.match(reference.strip())
    if match is None:
        raise ValueError(f"not a repository-qualified issue identity: {reference!r}")
    return match.group("repository"), int(match.group("number"))


def mirror_relationships(body: str | None) -> tuple[str, ...]:
    """Return the lowercased mirror relationship keywords present in a body."""
    if not body:
        return ()
    return tuple(sorted({match.group(1).lower() for match in _MIRROR_PATTERN.finditer(body)}))


@dataclass(frozen=True, order=True)
class Claim:
    """A valid execution claim as defined by section 4.2."""

    executor: str
    pull_request: str
    url: str = ""


@dataclass(frozen=True)
class Node:
    """One normalized issue.

    Only fields the canonical contract consumes, or that are required to explain
    a structural finding, belong here.
    """

    repository: str
    number: int
    title: str = ""
    url: str = ""
    state: str = OPEN
    state_reason: str | None = None
    parent: str | None = None
    children: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    blocking_count: int = 0
    priority_labels: tuple[str, ...] = ()
    has_acceptance_criteria: bool = False
    claims: tuple[Claim, ...] = ()
    claims_observable: bool = True
    resolved: bool = True
    unresolved_reason: str | None = None
    mirror_relationships: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return node_key(self.repository, self.number)

    @property
    def is_open(self) -> bool:
        return self.resolved and self.state == OPEN

    @property
    def is_done(self) -> bool:
        """Section 4.1 `DONE`: closed with the native closure reason `completed`."""
        return self.resolved and self.state == CLOSED and self.state_reason == COMPLETED

    @property
    def priority_rank(self) -> int:
        return max(
            (PRIORITY_RANKS[label] for label in self.priority_labels if label in PRIORITY_RANKS),
            default=UNRECOGNIZED_PRIORITY_RANK,
        )


def unresolved_node(key: str, reason: str) -> Node:
    """Return a placeholder for an issue that was requested but not resolvable."""
    repository, number = parse_node_key(key)
    return Node(repository=repository, number=number, resolved=False, unresolved_reason=reason)


@dataclass(frozen=True)
class Snapshot:
    """One invocation's collected GitHub data, treated as immutable."""

    nodes: Mapping[str, Node] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))

    def get(self, key: str) -> Node | None:
        return self.nodes.get(key)

    def require(self, key: str) -> Node:
        """Return the node for ``key``, or an unresolved placeholder."""
        node = self.nodes.get(key)
        if node is None:
            return unresolved_node(key, "not_in_snapshot")
        return node


def build_snapshot(nodes: Iterable[Node]) -> Snapshot:
    return Snapshot({node.key: node for node in nodes})


@dataclass(frozen=True, order=True)
class Finding:
    """A machine-derivable structural fact about the graph."""

    code: str
    node: str = ""
    detail: str = ""

    def as_json(self) -> dict[str, str]:
        return {"code": self.code, "node": self.node, "detail": self.detail}
