# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Pure derivation of work-graph state from an immutable snapshot.

Every predicate here implements docs/work-graph-contract.md sections 3 and 4 and
reads nothing beyond the inputs section 1.2 declares. No GitHub access happens in
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from types import MappingProxyType, NotImplementedType
from typing import Iterable, Mapping

from .model import (
    MAX_DEPENDENCIES_PER_TYPE,
    MAX_NESTING_DEPTH,
    MAX_SUB_ISSUES_PER_PARENT,
    Claim,
    Finding,
    Node,
    Snapshot,
)

# Reasons a node is not `READY`. They are the `READY` conditions of section 4.1
# themselves, which is what section 4.2 requires an empty executable set to report.
REASON_CLOSED = "closed"
REASON_NOT_LEAF = "not_a_leaf"
REASON_UNSATISFIED_DEPENDENCY = "unsatisfied_dependency"
REASON_UNRESOLVED_DEPENDENCY = "unresolved_dependency"
REASON_DEPENDENCY_CYCLE = "dependency_cycle"
REASON_CONTAINMENT_CYCLE = "containment_cycle"
REASON_CONTAINMENT_INCONSISTENT = "containment_inconsistent"
REASON_UNRESOLVED_ANCESTOR = "unresolved_ancestor"
REASON_CLOSED_ANCESTOR = "closed_ancestor"
REASON_MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"

REASON_ORDER = (
    REASON_CLOSED,
    REASON_NOT_LEAF,
    REASON_CONTAINMENT_CYCLE,
    REASON_CONTAINMENT_INCONSISTENT,
    REASON_UNRESOLVED_ANCESTOR,
    REASON_CLOSED_ANCESTOR,
    REASON_DEPENDENCY_CYCLE,
    REASON_UNRESOLVED_DEPENDENCY,
    REASON_UNSATISFIED_DEPENDENCY,
    REASON_MISSING_ACCEPTANCE_CRITERIA,
)

# Section 3.5 fail-closed containment conditions, as distinct from `BLOCKED`.
MALFORMED_REASONS = frozenset(
    {REASON_CONTAINMENT_CYCLE, REASON_CONTAINMENT_INCONSISTENT, REASON_UNRESOLVED_ANCESTOR}
)

FINDING_CONTAINMENT_CYCLE = "containment_cycle"
FINDING_CONTAINMENT_INCONSISTENT = "containment_inconsistent"
FINDING_UNRESOLVED_ANCESTOR = "unresolved_ancestor"
FINDING_CLOSED_ANCESTOR = "closed_ancestor"
FINDING_DEPENDENCY_CYCLE = "dependency_cycle"
FINDING_UNRESOLVED_DEPENDENCY = "unresolved_dependency"
FINDING_UNRESOLVED_SUB_ISSUE = "unresolved_sub_issue"
FINDING_MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"
FINDING_SUB_ISSUE_LIMIT = "sub_issue_limit_exceeded"
FINDING_NESTING_DEPTH = "nesting_depth_exceeded"
FINDING_DEPENDENCY_LIMIT = "dependency_limit_exceeded"
FINDING_DEPENDENCY_LIMIT_BLOCKING = "blocking_limit_exceeded"
FINDING_MULTIPLE_PARENTS = "multiple_parents"
FINDING_MIRROR_RELATIONSHIP = "body_relationship_mirror"
FINDING_CLAIMS_UNOBSERVABLE = "claims_unobservable"

# Findings that mean required graph data could not be resolved.
INCOMPLETE_FINDINGS = frozenset(
    {
        FINDING_CONTAINMENT_CYCLE,
        FINDING_CONTAINMENT_INCONSISTENT,
        FINDING_UNRESOLVED_ANCESTOR,
        FINDING_UNRESOLVED_DEPENDENCY,
        FINDING_UNRESOLVED_SUB_ISSUE,
    }
)

# Findings that leave the set of possible `READY` candidates, or their path
# order, unknown. A leaf that merely fails closed on its own inputs is not one
# of these: that is a complete answer about that leaf, and section 3.1 keeps it
# from affecting a sibling.
CANDIDATE_SCOPE_FINDINGS = frozenset({FINDING_UNRESOLVED_SUB_ISSUE, FINDING_CONTAINMENT_INCONSISTENT})

NO_READY_LEAF = "no_ready_leaf"
ALL_CANDIDATES_CLAIMED = "all_candidates_claimed"

# `NEXT` is undecidable rather than empty when its declared inputs are unknown.
# These are not canonical no-selection reasons: section 4.3 defines those two
# only for a complete input set.
INCOMPLETE_CANDIDATE_SCOPE = "incomplete_candidate_scope"
INCOMPLETE_SELECTION_METADATA = "incomplete_selection_metadata"


class ScopeRootUnresolved(Exception):
    """The requested scope root itself could not be resolved."""


@total_ordering
@dataclass(frozen=True)
class SelectionKey:
    """The four ordering keys of section 4.3, highest priority first.

    Priority ranks descending while the remaining keys ascend, so the ordering
    cannot come from the dataclass field order and is derived from `__lt__` and
    the dataclass equality instead.
    """

    priority_rank: int
    path: tuple[int, ...]
    repository: str
    number: int

    def _ordering(self) -> tuple[int, tuple[int, ...], str, int]:
        return (-self.priority_rank, self.path, self.repository, self.number)

    def __lt__(self, other: object) -> bool | NotImplementedType:
        if not isinstance(other, SelectionKey):
            return NotImplemented
        return self._ordering() < other._ordering()


@dataclass(frozen=True)
class NodeState:
    """Derived state for one node inside the resolved scope."""

    key: str
    path: tuple[int, ...]
    depth: int
    leaf: bool
    open: bool
    done: bool
    blocked: bool
    ready: bool
    active: bool
    malformed: bool
    reasons: tuple[str, ...]
    priority_rank: int
    priority_observable: bool
    claims: tuple[Claim, ...]

    @property
    def selection_key(self) -> SelectionKey:
        repository, _, number = self.key.rpartition("#")
        return SelectionKey(self.priority_rank, self.path, repository, int(number))


@dataclass(frozen=True)
class NextResult:
    """Section 4.3 result.

    Exactly one of three shapes: a selected leaf, a canonical no-selection
    reason, or an incompleteness reason meaning the declared inputs were not
    fully observable and no canonical answer exists.
    """

    selected: str | None
    no_selection_reason: str | None
    candidates: tuple[str, ...]
    incomplete_reason: str | None = None


@dataclass(frozen=True)
class Resolution:
    snapshot: Snapshot
    scope_root: str
    ancestors: tuple[str, ...]
    order: tuple[str, ...]
    states: Mapping[str, NodeState]
    findings: tuple[Finding, ...]

    @property
    def complete(self) -> bool:
        return not any(finding.code in INCOMPLETE_FINDINGS for finding in self.findings)

    def resolved_states(self) -> tuple[NodeState, ...]:
        """Subtree states in traversal order, skipping nodes that stayed unresolved."""
        return tuple(self.states[key] for key in self.order if key in self.states)

    def ready_leaves(self) -> tuple[str, ...]:
        """Section 4.2 executable leaf set, in section 4.3 selection order."""
        ready = [state for state in self.resolved_states() if state.ready]
        return tuple(state.key for state in sorted(ready, key=lambda state: state.selection_key))

    def next_inputs_incomplete(self) -> str | None:
        """Return why `NEXT` is undecidable here, or None when it is decidable."""
        if any(finding.code in CANDIDATE_SCOPE_FINDINGS for finding in self.findings):
            return INCOMPLETE_CANDIDATE_SCOPE
        if any(not self.states[key].priority_observable for key in self.ready_leaves()):
            return INCOMPLETE_SELECTION_METADATA
        return None

    def select_next(self, executor: str) -> NextResult:
        incomplete = self.next_inputs_incomplete()
        if incomplete is not None:
            return NextResult(None, None, (), incomplete)
        executable = self.ready_leaves()
        candidates = tuple(
            key for key in executable if not _claimed_by_another(self.states[key].claims, executor)
        )
        if candidates:
            return NextResult(candidates[0], None, candidates)
        reason = ALL_CANDIDATES_CLAIMED if executable else NO_READY_LEAF
        return NextResult(None, reason, ())


def _claimed_by_another(claims: Iterable[Claim], executor: str) -> bool:
    return any(claim.executor.casefold() != executor.casefold() for claim in claims)


def _ancestor_chain(snapshot: Snapshot, key: str) -> tuple[tuple[str, ...], str | None]:
    """Walk native containment upwards; return the chain and any fail-closed reason.

    The chain is ordered from the graph root down to the node's parent.
    """
    seen = {key}
    upward: list[str] = []
    current = snapshot.get(key)
    while current is not None:
        if not current.parent_observable:
            # An inaccessible parent is not an absent parent, so the chain ends
            # unresolved rather than at a root.
            return tuple(reversed(upward)), REASON_UNRESOLVED_ANCESTOR
        if current.parent is None:
            break
        parent_key = current.parent
        if parent_key in seen:
            return tuple(reversed(upward)), REASON_CONTAINMENT_CYCLE
        parent = snapshot.get(parent_key)
        upward.append(parent_key)
        if parent is None or not parent.resolved:
            return tuple(reversed(upward)), REASON_UNRESOLVED_ANCESTOR
        seen.add(parent_key)
        current = parent
    return tuple(reversed(upward)), None


@dataclass(frozen=True)
class DependencyCycles:
    """Section 3.5 cycle facts.

    `members` are the nodes that participate in a cycle, which is what section
    4.1 makes `BLOCKED`. `tainted` additionally holds the nodes that depend on a
    member, which section 3.5 keeps out of `READY` without making them `BLOCKED`.
    """

    members: frozenset[str]
    tainted: frozenset[str]
    cycles: tuple[tuple[str, ...], ...]


def _dependents(snapshot: Snapshot) -> Mapping[str, tuple[str, ...]]:
    dependents: dict[str, list[str]] = {}
    for key, node in snapshot.nodes.items():
        for target in node.blocked_by:
            dependents.setdefault(target, []).append(key)
    return MappingProxyType({key: tuple(value) for key, value in dependents.items()})


def _dependency_cycles(snapshot: Snapshot) -> DependencyCycles:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    components: list[tuple[str, ...]] = []
    counter = 0

    def edges(key: str) -> tuple[str, ...]:
        node = snapshot.get(key)
        return node.blocked_by if node is not None else ()

    for start in snapshot.nodes:
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            key, child_position = work[-1]
            if child_position == 0:
                index[key] = low[key] = counter
                counter += 1
                stack.append(key)
                on_stack[key] = True
            neighbours = edges(key)
            if child_position < len(neighbours):
                work[-1] = (key, child_position + 1)
                target = neighbours[child_position]
                if target not in index:
                    if snapshot.get(target) is not None:
                        work.append((target, 0))
                elif on_stack.get(target):
                    low[key] = min(low[key], index[target])
                continue
            work.pop()
            if work:
                parent_key = work[-1][0]
                low[parent_key] = min(low[parent_key], low[key])
            if low[key] == index[key]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component.append(member)
                    if member == key:
                        break
                if len(component) > 1 or key in edges(key):
                    components.append(tuple(sorted(component)))

    members = {member for component in components for member in component}
    dependents = _dependents(snapshot)

    tainted = set(members)
    queue = list(members)
    while queue:
        key = queue.pop()
        for dependent in dependents.get(key, ()):
            if dependent not in tainted:
                tainted.add(dependent)
                queue.append(dependent)
    return DependencyCycles(frozenset(members), frozenset(tainted), tuple(sorted(components)))


@dataclass(frozen=True)
class Subtree:
    order: tuple[str, ...]
    paths: Mapping[str, tuple[int, ...]]
    # Children a parent listed whose own native parent does not confirm the edge.
    # One invocation reads issues through several requests, so the two views can
    # disagree; neither is preferred over the other.
    inconsistent: Mapping[str, str]


def _subtree(snapshot: Snapshot, root: str) -> Subtree:
    """Walk native containment downwards, recording the section 4.3 path vector."""
    order: list[str] = []
    paths: dict[str, tuple[int, ...]] = {}
    inconsistent: dict[str, str] = {}
    stack: list[tuple[str, tuple[int, ...]]] = [(root, ())]
    while stack:
        key, path = stack.pop()
        if key in paths:
            continue
        paths[key] = path
        order.append(key)
        node = snapshot.get(key)
        if node is None or not node.resolved:
            continue
        if key in inconsistent:
            # The child itself stays visible with its malformed containment
            # finding, but its descendants are outside a provable scope.
            continue
        for position, child in reversed(list(enumerate(node.children))):
            child_node = snapshot.get(child)
            if child_node is not None and child_node.resolved and child_node.parent != key:
                inconsistent[child] = key
            if child not in paths:
                stack.append((child, path + (position,)))
    return Subtree(tuple(order), paths, inconsistent)


def _cycle_reaches_scope(
    cycle: tuple[str, ...], dependents: Mapping[str, Iterable[str]], scope_keys: Iterable[str]
) -> bool:
    """Return whether one cycle can block a node in the requested scope."""
    scope = set(scope_keys)
    pending = list(cycle)
    reached = set(cycle)
    while pending:
        key = pending.pop()
        if key in scope:
            return True
        for dependent in dependents.get(key, ()):
            if dependent not in reached:
                reached.add(dependent)
                pending.append(dependent)
    return False


def resolve(snapshot: Snapshot, scope_root: str) -> Resolution:
    """Derive every contract state for the subtree of ``scope_root``."""
    root_node = snapshot.get(scope_root)
    if root_node is None or not root_node.resolved:
        raise ScopeRootUnresolved(scope_root)

    subtree = _subtree(snapshot, scope_root)
    order = subtree.order
    root_ancestors, _ = _ancestor_chain(snapshot, scope_root)
    cycles = _dependency_cycles(snapshot)
    dependents = _dependents(snapshot)

    states: dict[str, NodeState] = {}
    findings: list[Finding] = []

    for key in order:
        node = snapshot.get(key)
        if node is None or not node.resolved:
            findings.append(
                Finding(
                    FINDING_UNRESOLVED_SUB_ISSUE,
                    key,
                    node.unresolved_reason if node is not None else "not_in_snapshot",
                )
            )
            continue
        state, node_findings = _derive(
            snapshot,
            node,
            path=subtree.paths[key],
            cycles=cycles,
            listing_parent=subtree.inconsistent.get(key),
        )
        states[key] = state
        findings.extend(node_findings)

    for cycle in cycles.cycles:
        if _cycle_reaches_scope(cycle, dependents, states):
            findings.append(Finding(FINDING_DEPENDENCY_CYCLE, cycle[0], ", ".join(cycle)))

    findings.extend(_multiple_parent_findings(snapshot, order))

    return Resolution(
        snapshot=snapshot,
        scope_root=scope_root,
        ancestors=root_ancestors,
        order=order,
        states=MappingProxyType(states),
        findings=tuple(sorted(set(findings))),
    )


def _multiple_parent_findings(snapshot: Snapshot, order: Iterable[str]) -> list[Finding]:
    """Section 3.1 forbids more than one parent; report it if the data shows one."""
    claimed: dict[str, list[str]] = {}
    for key in order:
        node = snapshot.get(key)
        if node is None or not node.resolved:
            continue
        for child in node.children:
            claimed.setdefault(child, []).append(key)
    return [
        Finding(FINDING_MULTIPLE_PARENTS, child, ", ".join(sorted(parents)))
        for child, parents in claimed.items()
        if len(parents) > 1
    ]


def _derive(
    snapshot: Snapshot,
    node: Node,
    *,
    path: tuple[int, ...],
    cycles: DependencyCycles,
    listing_parent: str | None = None,
) -> tuple[NodeState, list[Finding]]:
    findings: list[Finding] = []
    reasons: set[str] = set()

    is_open = node.is_open
    is_leaf = not node.children
    if not is_open:
        reasons.add(REASON_CLOSED)
    if not is_leaf:
        reasons.add(REASON_NOT_LEAF)

    if listing_parent is not None:
        reasons.add(REASON_CONTAINMENT_INCONSISTENT)
        findings.append(Finding(FINDING_CONTAINMENT_INCONSISTENT, node.key, listing_parent))

    # Section 4.1 reads every ancestor up to the graph root, not just the ones
    # inside the requested scope.
    own_ancestors, containment_problem = _ancestor_chain(snapshot, node.key)
    if containment_problem is not None:
        reasons.add(containment_problem)
        code = (
            FINDING_CONTAINMENT_CYCLE
            if containment_problem == REASON_CONTAINMENT_CYCLE
            else FINDING_UNRESOLVED_ANCESTOR
        )
        detail = own_ancestors[0] if own_ancestors else ""
        findings.append(Finding(code, node.key, detail))

    for ancestor_key in own_ancestors:
        ancestor = snapshot.get(ancestor_key)
        if ancestor is not None and ancestor.resolved and not ancestor.is_open:
            reasons.add(REASON_CLOSED_ANCESTOR)
            if is_open:
                findings.append(Finding(FINDING_CLOSED_ANCESTOR, node.key, ancestor_key))

    depth = len(own_ancestors)
    if depth > MAX_NESTING_DEPTH:
        findings.append(Finding(FINDING_NESTING_DEPTH, node.key, str(depth)))

    # Dependencies. Section 3.2: satisfied only by closure reason `completed`.
    for target_key in node.blocked_by:
        target = snapshot.get(target_key)
        if target is None or not target.resolved:
            reasons.add(REASON_UNRESOLVED_DEPENDENCY)
            findings.append(Finding(FINDING_UNRESOLVED_DEPENDENCY, node.key, target_key))
        elif not target.is_done:
            reasons.add(REASON_UNSATISFIED_DEPENDENCY)
    if node.key in cycles.tainted:
        reasons.add(REASON_DEPENDENCY_CYCLE)

    if not node.has_acceptance_criteria:
        reasons.add(REASON_MISSING_ACCEPTANCE_CRITERIA)
        if is_open and is_leaf:
            findings.append(Finding(FINDING_MISSING_ACCEPTANCE_CRITERIA, node.key))

    if len(node.children) > MAX_SUB_ISSUES_PER_PARENT:
        findings.append(Finding(FINDING_SUB_ISSUE_LIMIT, node.key, str(len(node.children))))
    if len(node.blocked_by) > MAX_DEPENDENCIES_PER_TYPE:
        findings.append(Finding(FINDING_DEPENDENCY_LIMIT, node.key, str(len(node.blocked_by))))
    if node.blocking_count > MAX_DEPENDENCIES_PER_TYPE:
        findings.append(Finding(FINDING_DEPENDENCY_LIMIT_BLOCKING, node.key, str(node.blocking_count)))
    if node.mirror_relationships:
        findings.append(
            Finding(FINDING_MIRROR_RELATIONSHIP, node.key, ", ".join(node.mirror_relationships))
        )
    if not node.claims_observable:
        findings.append(Finding(FINDING_CLAIMS_UNOBSERVABLE, node.key))

    # Section 4.1 `BLOCKED`: an open node with an unsatisfied or unresolvable
    # dependency, or one that itself participates in a dependency cycle. Merely
    # depending on a cycle member is not participation, and malformed
    # containment is deliberately not `BLOCKED` either.
    blocked = is_open and (
        bool(reasons & {REASON_UNSATISFIED_DEPENDENCY, REASON_UNRESOLVED_DEPENDENCY})
        or node.key in cycles.members
    )
    ready = not reasons
    claims = tuple(sorted(node.claims)) if node.claims_observable else ()

    state = NodeState(
        key=node.key,
        path=path,
        depth=depth,
        leaf=is_leaf,
        open=is_open,
        done=node.is_done,
        blocked=blocked,
        ready=ready,
        active=ready and bool(claims),
        malformed=bool(reasons & MALFORMED_REASONS),
        reasons=tuple(reason for reason in REASON_ORDER if reason in reasons),
        priority_rank=node.priority_rank,
        priority_observable=node.priority_labels_observable,
        claims=claims,
    )
    return state, findings
