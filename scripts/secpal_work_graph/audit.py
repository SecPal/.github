# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Advisory migration classification layered on canonical resolver results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from . import resolver
from .model import CLOSED, Node, Snapshot

SCHEMA = "secpal-work-graph-audit/v1"
DEFAULT_REPOSITORIES = (
    "SecPal/.github", "SecPal/android", "SecPal/frontend", "SecPal/deployment",
    "SecPal/api", "SecPal/contracts", "SecPal/secpal.app", "SecPal/GuardGuide",
    "SecPal/guardguide.de",
)
_PRIORITY = {"before_rollout": 0, "normal": 1, "cleanup": 2}


@dataclass(frozen=True)
class AdvisoryIssueFacts:
    """Audit-local discovery evidence that never becomes resolver input."""

    key: str
    repository: str
    discovery_source: str
    relationship_mirrors: tuple[str, ...] = ()
    has_status_checklist: bool = False
    legacy_epic_candidate: bool = False
    native_children_count: int = 0
    closing_pull_requests: tuple[str, ...] = ()
    blocked_by_count: int = 0
    blocking_count: int = 0


def _finding(
    node: Node,
    kind: str,
    classification: str,
    source: str,
    evidence: str,
    **extra,
):
    return _issue_finding(
        node.repository, node.key, kind, classification, source, evidence, **extra
    )


def _issue_finding(
    repository: str,
    issue: str,
    kind: str,
    classification: str,
    source: str,
    evidence: str,
    **extra,
):
    result = {
        "kind": kind,
        "classification": classification,
        "migration_priority": (
            "before_rollout" if classification == "execution_blocker" else "normal"
        ),
        "repository": repository,
        "issue": issue,
        "discovery_source": source,
        "requires_judgment": False,
        "evidence": evidence,
    }
    result.update(extra)
    return result


def classify_advisory(facts: AdvisoryIssueFacts) -> list[dict]:
    """Classify migration evidence without constructing canonical graph state."""
    findings: list[dict] = []
    if facts.relationship_mirrors:
        findings.append(
            _issue_finding(
                facts.repository,
                facts.key,
                "body_relationship_mirror",
                "migration_debt",
                facts.discovery_source,
                "Markdown mirrors: " + ", ".join(facts.relationship_mirrors),
            )
        )
        missing_dependency = (
            any(name in {"blocked by", "depends on"} for name in facts.relationship_mirrors)
            and facts.blocked_by_count == 0
        ) or ("blocks" in facts.relationship_mirrors and facts.blocking_count == 0)
        if missing_dependency:
            findings.append(
                _issue_finding(
                    facts.repository,
                    facts.key,
                    "prose_only_blocker",
                    "migration_debt",
                    facts.discovery_source,
                    "Dependency mirror has no corresponding native relationship",
                )
            )
    if facts.has_status_checklist:
        findings.append(
            _issue_finding(
                facts.repository,
                facts.key,
                "duplicated_markdown_status",
                "migration_debt",
                facts.discovery_source,
                "Parser-derived Markdown task-list status mirror",
            )
        )
    if len(facts.closing_pull_requests) > 1:
        findings.append(
            _issue_finding(
                facts.repository,
                facts.key,
                "multi_contract_leaf_candidate",
                "migration_debt",
                facts.discovery_source,
                "Multiple native closing pull-request relationships; review its delivery contract",
                requires_judgment=True,
            )
        )
    if (
        facts.native_children_count > 0 or facts.legacy_epic_candidate
    ) and facts.closing_pull_requests:
        for pull_request in facts.closing_pull_requests:
            findings.append(
                _issue_finding(
                    facts.repository,
                    facts.key,
                    "direct_epic_delivery_pull_request",
                    "migration_debt",
                    facts.discovery_source,
                    "Epic has a native closing pull-request relationship",
                    pull_request=pull_request,
                )
            )
    return findings


def classify_native(snapshot: Snapshot, root: str, *, repository: str) -> list[dict]:
    """Classify facts; all graph predicates are delegated to ``resolver``."""
    resolution = resolver.resolve(snapshot, root)
    findings: list[dict] = []
    for state in resolution.resolved_states():
        node = snapshot.nodes[state.key]
        if node.repository != repository:
            continue
        source = "native"
        if (
            state.leaf
            and node.is_open
            and resolver.REASON_MISSING_ACCEPTANCE_CRITERIA in state.reasons
        ):
            findings.append(
                _finding(
                    node,
                    "structurally_incomplete_delivery_leaf",
                    "execution_blocker",
                    source,
                    "Canonical resolver reports missing_acceptance_criteria",
                )
            )
        if node.state == CLOSED and node.children:
            for child_key in node.children:
                child = snapshot.get(child_key)
                if child and child.is_open:
                    findings.append(
                        _finding(
                            node,
                            "closed_parent_open_child",
                            "execution_blocker",
                            source,
                            "Native child remains open",
                            related_issue=child_key,
                        )
                    )
    for finding in resolution.findings:
        if finding.code in resolver.INCOMPLETE_FINDINGS or finding.code in {
            resolver.FINDING_CONTAINMENT_CYCLE, resolver.FINDING_DEPENDENCY_CYCLE,
        }:
            node = snapshot.require(finding.node or root)
            if node.repository == repository:
                findings.append(
                    _finding(
                        node,
                        finding.code,
                        "execution_blocker",
                        "native",
                        finding.detail or finding.code,
                    )
                )
    return findings


def deduplicate_findings(findings: Iterable[dict]) -> list[dict]:
    """Deduplicate complete semantic finding documents deterministically."""
    import json

    unique = {
        json.dumps(finding, sort_keys=True, separators=(",", ":")): finding
        for finding in findings
    }
    return [unique[key] for key in sorted(unique)]


def document(results: Iterable[dict]) -> dict:
    repositories = sorted(results, key=lambda item: item["repository"])
    for result in repositories:
        result["findings"].sort(key=lambda f: (0 if f["classification"] == "execution_blocker" else 1,
            _PRIORITY[f["migration_priority"]], f["repository"], int(f["issue"].rsplit("#", 1)[1]),
            f["kind"], f.get("related_issue", f.get("pull_request", ""))))
    findings = [finding for result in repositories for finding in result["findings"]]
    return {"schema": SCHEMA, "repositories": repositories,
            "summary": {"repositories": len(repositories), "execution_blockers": sum(f["classification"] == "execution_blocker" for f in findings),
                        "migration_debt": sum(f["classification"] == "migration_debt" for f in findings),
                        "requires_judgment": sum(f["requires_judgment"] for f in findings)}}
