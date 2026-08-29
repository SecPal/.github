# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Pure advisory delivery-PR assessment layered on maintained authorities.

Graph predicates come from :mod:`resolver`; review-disposition validity comes
from :func:`replanning.classify`.  This module owns only report shape and never
authorizes, blocks, mutates, or redefines either authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from . import replanning, resolver

SCHEMA = "secpal-pr-advisory/v1"
CONTRACT = "docs/work-graph-contract.md"


@dataclass(frozen=True)
class Observation:
    """An explicit human/agent judgment fact, not a source-code inference."""

    kind: str
    evidence: str


@dataclass(frozen=True)
class FeedbackClaim:
    """One reported disposition checked by the maintained classifier."""

    finding_id: str
    classification: Mapping[str, Any]
    reported_technically_blocking: bool
    reported_mechanically_blocking: bool


@dataclass(frozen=True)
class LifecycleClaim:
    """A lifecycle concern already established from #692 authority evidence."""

    kind: str
    evidence: str
    technically_blocking: bool
    mechanically_blocking: bool


@dataclass(frozen=True)
class ReviewSmells:
    """Non-decisive counts retained for reviewer context only."""

    tests: int = 0
    changed_lines: int = 0
    mutations: int = 0


_OBSERVATION_RULES = MappingProxyType(
    {
        "SECOND_RESPONSIBILITY": (
            "SECOND_RESPONSIBILITY_WITHOUT_REPLANNING",
            "work-graph section 7.2",
            "Replan the independent responsibility in the native graph before expanding this PR.",
        ),
        "DUPLICATE_INVARIANT_WITHOUT_BOUNDARY_JUSTIFICATION": (
            "DUPLICATE_AUTHORITATIVE_INVARIANT",
            "work-graph section 11",
            "Reuse the authoritative invariant or name and test the independent trust boundary.",
        ),
        "UNNAMED_EVIDENCE": (
            "EVIDENCE_WITHOUT_NAMED_CONTRACT",
            "work-graph sections 9 and 10",
            "Name the contract distinction or evidence class proved by the new test or guard.",
        ),
        "STRUCTURAL_EVIDENCE_AS_BEHAVIOR": (
            "STRUCTURAL_EVIDENCE_OVERCLAIMED",
            "work-graph section 9.3",
            "Classify this as structural evidence or justify the behavior boundary it exercises.",
        ),
        "CUSTOM_MECHANISM_WITHOUT_STANDARDS_CHECK": (
            "CUSTOM_MECHANISM_WITHOUT_STANDARDS_CHECK",
            "work-graph section 12.1",
            "Document the checked language, framework, library, or platform mechanism before keeping custom code.",
        ),
        "FINITE_DENYLIST_WHERE_ALLOWLIST_IS_PRACTICAL": (
            "FINITE_POLICY_USES_DENYLIST",
            "work-graph section 12.2",
            "Use the practical closed allowlist and reject unknown capability values.",
        ),
        "IN_SCOPE_PRE_FREEZE_OFFLOAD": (
            "IN_SCOPE_PRE_FREEZE_DEFECT_OFFLOADED",
            "work-graph section 8.1",
            "Keep the in-contract defect in this delivery and correct it with proportionate evidence.",
        ),
    }
)

_LIFECYCLE_RULES = MappingProxyType(
    {
        "COUNTER_RESET": (
            "LIFECYCLE_COUNTER_RESET",
            "#692 PR_REBOUND transition in the maintained lifecycle authority",
            "Bind the replacement to CURRENT lifecycle authority and preserve every consumed counter.",
        ),
        "RECURSIVE_REVIEW_RESTART": (
            "RECURSIVE_REVIEW_CHURN",
            "#692 observation-event path and explicit Cycle-3 absence",
            "Keep late feedback inside the maintained finite disposition path; do not restart review/remediation.",
        ),
        "UNOWNED_FOLLOW_UP": (
            "UNOWNED_FOLLOW_UP",
            "#692 NON_BLOCKING_FOLLOWUP ownership verifier",
            "Attach the follow-up to the existing owning epic or sub-epic before disposition.",
        ),
    }
)


def _graph_state(graph: resolver.Resolution, issue: str) -> dict[str, Any]:
    node = graph.snapshot.require(issue)
    state = graph.states.get(issue)
    if state is None:
        return {
            "role": "unresolved",
            "open": False,
            "ready": False,
            "blocked": False,
            "malformed": True,
            "reasons": [node.unresolved_reason or "not_in_resolution"],
        }
    return {
        "role": "leaf" if state.leaf else "non_leaf",
        "open": state.open,
        "ready": state.ready,
        "blocked": state.blocked,
        "malformed": state.malformed,
        "reasons": list(state.reasons),
    }


def _finding(
    *,
    code: str,
    owning_issue: str,
    graph_state: Mapping[str, Any],
    rule: str,
    evidence: str,
    action: str,
    technically_blocking: bool | None = None,
    mechanically_blocking: bool | None = None,
    lifecycle_rule: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "owning_issue": owning_issue,
        "graph_state": dict(graph_state),
        "rule": rule,
        "evidence": evidence,
        "action": action,
        "advisory": True,
        "technically_blocking": technically_blocking,
        "mechanically_blocking": mechanically_blocking,
    }
    if lifecycle_rule is not None:
        item["lifecycle_rule"] = lifecycle_rule
    return item


def assess(
    *,
    pull_request: str,
    primary_issue: str,
    closing_issues: Sequence[str],
    graph: resolver.Resolution,
    closing_graphs: Mapping[str, resolver.Resolution] | None = None,
    observations: Sequence[Observation] = (),
    feedback: Sequence[FeedbackClaim] = (),
    lifecycle_claims: Sequence[LifecycleClaim] = (),
    smells: ReviewSmells | None = None,
) -> dict[str, Any]:
    """Return concise report-only findings for one delivery pull request."""

    primary_state = _graph_state(graph, primary_issue)
    findings: list[dict[str, Any]] = []

    issue_graphs = dict(closing_graphs or {})
    for issue in dict.fromkeys(closing_issues):
        state = _graph_state(issue_graphs.get(issue, graph), issue)
        if state["role"] == "non_leaf":
            findings.append(
                _finding(
                    code="PR_CLOSES_NON_LEAF",
                    owning_issue=primary_issue,
                    graph_state=state,
                    rule="work-graph section 5.2",
                    evidence=f"{pull_request} closes non-leaf planning issue {issue}",
                    action="Remove the closing relationship; epics close through the canonical closure procedure.",
                    technically_blocking=False,
                    mechanically_blocking=False,
                )
            )

    if primary_state["blocked"]:
        findings.append(
            _finding(
                code="PRIMARY_ISSUE_BLOCKED",
                owning_issue=primary_issue,
                graph_state=primary_state,
                rule="work-graph sections 3.2 and 4.1",
                evidence=f"Canonical resolver reports {primary_issue} BLOCKED",
                action="Resolve the native dependency or replan it before treating this delivery as graph-ready.",
                technically_blocking=False,
                mechanically_blocking=False,
            )
        )

    unique_closures = tuple(dict.fromkeys(closing_issues))
    if len(unique_closures) > 1:
        findings.append(
            _finding(
                code="MULTIPLE_DELIVERY_CONTRACTS",
                owning_issue=primary_issue,
                graph_state=primary_state,
                rule="work-graph section 5.2",
                evidence="Closing issues: " + ", ".join(unique_closures),
                action="Keep exactly one primary closing leaf and replan independent contracts before delivery.",
                technically_blocking=False,
                mechanically_blocking=False,
            )
        )

    for observation in observations:
        if observation.kind not in _OBSERVATION_RULES:
            raise ValueError(f"unsupported advisory observation: {observation.kind}")
        code, rule, action = _OBSERVATION_RULES[observation.kind]
        findings.append(
            _finding(
                code=code,
                owning_issue=primary_issue,
                graph_state=primary_state,
                rule=rule,
                evidence=observation.evidence,
                action=action,
                lifecycle_rule=(
                    "#692 pre-freeze IN_CONTRACT_DEFECT disposition"
                    if observation.kind == "IN_SCOPE_PRE_FREEZE_OFFLOAD"
                    else None
                ),
                technically_blocking=(
                    True if observation.kind == "IN_SCOPE_PRE_FREEZE_OFFLOAD" else None
                ),
                mechanically_blocking=(
                    True if observation.kind == "IN_SCOPE_PRE_FREEZE_OFFLOAD" else None
                ),
            )
        )

    for claim in feedback:
        try:
            classification = replanning.classify(claim.classification)
        except replanning.PlanError as error:
            findings.append(
                _finding(
                    code="INVALID_LIFECYCLE_DISPOSITION",
                    owning_issue=primary_issue,
                    graph_state=primary_state,
                    rule="work-graph section 8.1",
                    lifecycle_rule="work-graph section 8.1 via #692 orchestration",
                    evidence=f"{claim.finding_id}: {error}",
                    action="Reclassify the finding through the maintained lifecycle/disposition authority.",
                    technically_blocking=None,
                    mechanically_blocking=None,
                )
            )
            continue
        if (
            claim.reported_technically_blocking != classification.technically_blocking
            or claim.reported_mechanically_blocking != classification.mechanically_blocking
        ):
            findings.append(
                _finding(
                    code="BLOCKING_STATUS_MISREPORTED",
                    owning_issue=primary_issue,
                    graph_state=primary_state,
                    rule="work-graph section 8.1",
                    lifecycle_rule="work-graph section 8.1 via #692 orchestration",
                    evidence=f"{claim.finding_id}: reported technical/mechanical status differs from canonical classification",
                    action="Report technical and mechanical blocking independently from the canonical classification.",
                    technically_blocking=classification.technically_blocking,
                    mechanically_blocking=classification.mechanically_blocking,
                )
            )

    for claim in lifecycle_claims:
        if claim.kind not in _LIFECYCLE_RULES:
            raise ValueError(f"unsupported lifecycle claim: {claim.kind}")
        code, lifecycle_rule, action = _LIFECYCLE_RULES[claim.kind]
        findings.append(
            _finding(
                code=code,
                owning_issue=primary_issue,
                graph_state=primary_state,
                rule="work-graph section 8.1",
                lifecycle_rule=lifecycle_rule,
                evidence=claim.evidence,
                action=action,
                technically_blocking=claim.technically_blocking,
                mechanically_blocking=claim.mechanically_blocking,
            )
        )

    smell = smells or ReviewSmells()
    return {
        "schema": SCHEMA,
        "semantics": CONTRACT,
        "pull_request": pull_request,
        "owning_issue": primary_issue,
        "graph_state": primary_state,
        "advisory": True,
        "status": "advisory_findings" if findings else "advisory_clean",
        "findings": findings,
        "review_smells": {
            "tests": smell.tests,
            "changed_lines": smell.changed_lines,
            "mutations": smell.mutations,
        },
    }
