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
class Candidate:
    key: str
    discovery_source: str
    status_checklist: bool = False
    epic_candidate: bool = False


def is_epic(node: Node) -> bool:
    return bool(node.children) or "epic" in node.title.casefold() or "epic" in node.priority_labels


def _finding(node: Node, kind: str, classification: str, source: str, evidence: str, **extra):
    result = {"kind": kind, "classification": classification,
              "migration_priority": "before_rollout" if classification == "execution_blocker" else "normal",
              "repository": node.repository, "issue": node.key,
              "discovery_source": source, "requires_judgment": False, "evidence": evidence}
    result.update(extra)
    return result


def classify(
    snapshot: Snapshot, root: str, candidate: Candidate, *, repository: str
) -> list[dict]:
    """Classify facts; all graph predicates are delegated to ``resolver``."""
    resolution = resolver.resolve(snapshot, root)
    findings: list[dict] = []
    for state in resolution.resolved_states():
        node = snapshot.nodes[state.key]
        if node.repository != repository:
            continue
        source = candidate.discovery_source if state.key == candidate.key else "native"
        if node.mirror_relationships:
            findings.append(_finding(node, "body_relationship_mirror", "migration_debt", source,
                "Markdown mirrors: " + ", ".join(node.mirror_relationships)))
            if any(name in {"blocked by", "blocks", "depends on"} for name in node.mirror_relationships) and not node.blocked_by:
                findings.append(_finding(node, "prose_only_blocker", "migration_debt", source,
                    "Dependency mirror has no native dependency"))
        if state.leaf and node.is_open and resolver.REASON_MISSING_ACCEPTANCE_CRITERIA in state.reasons:
            findings.append(_finding(node, "structurally_incomplete_delivery_leaf", "execution_blocker", source,
                "Canonical resolver reports missing_acceptance_criteria"))
        if state.leaf and len(node.closing_pull_requests) > 1:
            findings.append(_finding(node, "multi_contract_leaf_candidate", "migration_debt", source,
                "Multiple native closing pull-request relationships; review its delivery contract",
                requires_judgment=True))
        if node.state == CLOSED and node.children:
            for child_key in node.children:
                child = snapshot.get(child_key)
                if child and child.is_open:
                    findings.append(_finding(node, "closed_parent_open_child", "execution_blocker", source,
                        "Native child remains open", related_issue=child_key))
        if (is_epic(node) or (node.key == candidate.key and candidate.epic_candidate)) and node.closing_pull_requests:
            for pull_request in node.closing_pull_requests:
                findings.append(_finding(node, "direct_epic_delivery_pull_request", "migration_debt", source,
                    "Epic has a native closing pull-request relationship", pull_request=pull_request))
    if candidate.status_checklist:
        node = snapshot.require(candidate.key)
        findings.append(_finding(node, "duplicated_markdown_status", "migration_debt", candidate.discovery_source,
            "Parser-derived Markdown task-list status mirror"))
    for finding in resolution.findings:
        if finding.code in resolver.INCOMPLETE_FINDINGS or finding.code in {
            resolver.FINDING_CONTAINMENT_CYCLE, resolver.FINDING_DEPENDENCY_CYCLE,
        }:
            node = snapshot.require(finding.node or root)
            if node.repository == repository:
                findings.append(_finding(node, finding.code, "execution_blocker", "native", finding.detail or finding.code))
    return findings


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
