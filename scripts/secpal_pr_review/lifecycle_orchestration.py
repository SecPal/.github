# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finite policy orchestration over authenticated delivery-lifecycle state.

The signed state machine remains owned by :mod:`lifecycle_authority`.  This
module authenticates CURRENT publication, consumes the canonical work-graph
classification, and selects at most one bounded next action.  It performs no
GitHub mutation, signing, publication, review request, Ready/Draft transition,
push, polling, or merge.
"""

from __future__ import annotations

import base64
import binascii
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping

from scripts.secpal_work_graph import replanning

from . import bootstrap_source_admission
from . import exceptional_recovery
from . import fast_path
from . import follow_up
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication
from . import late_disposition
from . import version_collision


REQUEST_FIELDS = frozenset(
    {
        "event_kind",
        "event_id",
        "pull_request",
        "head_sha",
        "replacement_pull_request",
        "classification",
        "follow_up",
        "authorization",
    }
)
CONTINUATION_REQUEST_FIELDS = REQUEST_FIELDS | {"continuation_evidence"}
CONTINUATION_EVIDENCE_FIELDS = frozenset(
    {"reviewed_state_evidence", "eligibility_evidence"}
)
CONTINUATION_SUCCESSOR_EVIDENCE_FIELDS = CONTINUATION_EVIDENCE_FIELDS | {
    "successor_safety_evidence"
}
COLLISION_CONTINUATION_FIELDS = frozenset({
    "schema_version", "trigger", "repository_root", "reviewed_state_evidence",
    "eligibility_evidence", "continuation_document", "predecessor_safety_evidence",
    "successor_safety_evidence", "validation_attestation",
})
CONTINUATION_REANCHOR_EVIDENCE_FIELDS = CONTINUATION_SUCCESSOR_EVIDENCE_FIELDS | {
    "reanchor_evidence",
    "expected_signer",
}
REJECTED_CONTINUATION_REANCHOR_SCHEMA_VERSION = "1.0"
REJECTED_CONTINUATION_REANCHOR_KIND = (
    "REJECTED_EXCEPTIONAL_CONTINUATION_REANCHOR"
)
REJECTED_CONTINUATION_REANCHOR_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "repository",
        "delivery_issue_number",
        "original_pull_request_number",
        "replacement_pull_request_number",
        "lifecycle_id",
        "current_publication_oid",
        "current_publication_digest",
        "current_authority_digest",
        "current_head_sha",
        "current_tree_sha",
        "rebound_predecessor_publication_oid",
        "rebound_event_digest",
        "rejected_candidate_head_sha",
        "rejected_candidate_tree_sha",
        "rejected_candidate_expected_signer",
        "rejected_continuation_evidence",
        "rejected_eligibility_evidence",
        "rejected_reviewed_state_evidence",
        "rejected_candidate_state_evidence",
        "rejected_successor_safety_evidence",
        "rejected_validation_receipt",
        "rejected_final_attestation",
        "replacement_reviewed_state_evidence",
    }
)
AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "domain",
        "authorization_id",
        "repository",
        "delivery_issue",
        "lifecycle_id",
        "publication_oid",
        "publication_digest",
        "authority_digest",
        "pull_request",
        "head_sha",
        "operation",
        "reason",
        "scope",
        "bounded_uses",
        "signer_identity",
        "signature",
        "authorization_digest",
    }
)
AUTHORIZATION_SCHEMA_VERSION = "1.0"
AUTHORIZATION_KIND = "SECPAL_LIFECYCLE_ORCHESTRATION_USER_AUTHORIZATION"
AUTHORIZATION_DOMAIN = "secpal.lifecycle-orchestration-user-authorization/v1"
OBSERVATION_EVENTS = frozenset(
    {
        "REVIEW_EVENT_OBSERVED",
        "CI_OBSERVED",
        "PR_REOPENED",
        "READY_INTEGRATION_VALIDATED",
        "FEEDBACK_ASSESSMENT_COMPLETED",
    }
)
EVENTS = OBSERVATION_EVENTS | frozenset(
    {
        "PR_REPLACED",
        "REMEDIATION_COMMIT_PUSHED",
        "RECOVERY_COMMIT_PUSHED",
        "CONTINUATION_COMMIT_PUSHED",
        "DRAFT_TO_READY",
        "READY_TO_DRAFT",
        "LATE_FEEDBACK_CLASSIFIED",
        "ADDITIONAL_REVIEW_AUTHORIZED",
    }
)

CurrentReader = Callable[[str, int], Any]
FollowUpVerifier = Callable[[follow_up.FollowUpIdentity], Any]
AuthorizationVerifier = Callable[
    [Any, Any, authority.VerifiedLifecycleAuthority], dict[str, Any]
]


class LifecycleOrchestrationError(ValueError):
    """The requested event is stale, ambiguous, recursive, or unauthorized."""


@dataclass(frozen=True)
class AcceptedMainComparisonFacts:
    """Closed provider observation used by pure accepted-main lineage admission."""

    status: str
    behind_by: int
    merge_base_sha: str


@dataclass(frozen=True)
class LifecycleDecision:
    """One fail-closed decision over the independently authenticated CURRENT tip."""

    publication_oid: str
    publication_digest: str
    lifecycle_identity: str
    pull_request: int
    head_sha: str
    resulting_pull_request: int
    resulting_head_sha: str
    unrestricted_reviews: int
    remediation_cycles: int
    cycle_3_absent: bool
    exceptional_recoveries: int
    exceptional_continuations: int
    ready: bool
    ready_transition_already_performed: bool
    lifecycle_transition: str | None = None
    preserve_ready: bool = False
    transition_to_draft: bool = False
    transition_to_ready: bool = False
    request_review: bool = False
    requires_fresh_head_evidence: bool = False
    additional_review_authorized: bool = False
    technically_blocking: bool = False
    mechanically_blocking: bool = False
    merge_ready: bool = False
    explicit_recovery_required: bool = False
    resolution_eligible: bool = False
    guarded_resolution_candidate: bool = False
    authenticated_resolution_required: bool = False
    resolution_meaning_if_applied: str | None = None
    authorization_digest: str | None = None
    requires_authorization_publication: bool = False
    stop_after_bounded_pass: bool = True


@dataclass(frozen=True)
class VerifiedExceptionalRecoveryAuthority:
    """Closed verified facts for one existing Exceptional Recovery."""

    recovery_digest: str
    authorization_id: str
    authorization_digest: str
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    predecessor_publication_oid: str
    predecessor_publication_digest: str
    recovery_publication_oid: str
    recovery_publication_digest: str
    predecessor_authority_digest: str
    recovery_authority_digest: str
    prior_ready_head_sha: str
    resulting_head_sha: str
    prior_ready_tree_sha: str
    recovery_tree_sha: str
    reviewed_state_digest: str | None
    reviewed_feedback_digest: str | None
    eligibility_evidence_digest: str | None
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedExceptionalContinuationAuthority:
    """Closed composite authority for one source-changing Continuation."""

    continuation_digest: str
    authorization_id: str
    authorization_digest: str
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    predecessor_publication_oid: str
    predecessor_publication_digest: str
    continuation_publication_oid: str
    continuation_publication_digest: str
    predecessor_authority_digest: str
    continuation_authority_digest: str
    prior_ready_head_sha: str
    resulting_head_sha: str
    prior_ready_tree_sha: str
    continuation_tree_sha: str
    reviewed_state_digest: str
    reviewed_feedback_digest: str
    eligibility_evidence_digest: str
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    source_signer_kind: str
    source_signer_identity: str
    reanchor_evidence_digest: str | None = None
    original_pull_request: int | None = None
    rejected_candidate_head_sha: str | None = None
    rejected_candidate_tree_sha: str | None = None
    rejected_continuation_evidence_digest: str | None = None
    diagnostic_thread_ids: tuple[str, ...] = ()
    finding_source_digest: str | None = None
    provider_reaction_replacement_digest: str | None = None
    predecessor_provider_growth_digest: str | None = None


@dataclass(frozen=True)
class VerifiedContinuationFindingAuthority:
    """Finding facts derived from canonical current-head feedback evidence."""

    reviewed_state_digest: str
    reviewed_feedback_digest: str
    eligibility_evidence_digest: str
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    reanchor: "VerifiedRejectedContinuationReanchor | None" = None
    continuation_tree_sha: str | None = None
    corrected_successor_state_digest: str | None = None
    predecessor_provider_growth_digest: str | None = None


_ORDINARY_READY_REMEDIATION_FINDING_AUTHORITY_SEAL = object()
_POST_READY_VALIDATION_DEFECT_AUTHORITY_SEAL = object()


@dataclass(frozen=True)
class VerifiedOrdinaryReadyRemediationFindingAuthority:
    """Provider-growth findings bound to the remaining ordinary Ready slot."""

    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    current_publication_oid: str
    current_publication_digest: str
    current_authority_digest: str
    provider_head_sha: str
    current_head_sha: str
    resulting_head_sha: str
    predecessor_state_digest: str
    resulting_state_digest: str
    provider_growth_digest: str
    predecessor_eligibility_evidence_digest: str
    eligibility_evidence_digest: str
    finding_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    finding_authority_digest: str
    _verification_seal: object


@dataclass(frozen=True)
class VerifiedPostReadyValidationDefectAuthority:
    """One independently reproduced validation defect using the remaining slot."""

    source_kind: str
    classification: str
    technically_blocking: bool
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    current_publication_oid: str
    current_publication_digest: str
    current_authority_digest: str
    current_head_sha: str
    current_tree_sha: str
    resulting_head_sha: str
    resulting_tree_sha: str
    failure_observation_digest: str
    defect_proof_digest: str
    candidate_validation_digest: str
    correction_authentication_digest: str
    finding_id: str
    finding_authority_digest: str
    _verification_seal: object


def _post_ready_validation_defect_projection(
    value: VerifiedPostReadyValidationDefectAuthority,
) -> dict[str, Any]:
    return {
        "domain": "secpal.post-ready-validation-defect-authority/v1",
        "source_kind": value.source_kind,
        "classification": value.classification,
        "technically_blocking": value.technically_blocking,
        "repository": value.repository,
        "delivery_issue": value.delivery_issue,
        "pull_request": value.pull_request,
        "lifecycle_id": value.lifecycle_id,
        "current_publication_oid": value.current_publication_oid,
        "current_publication_digest": value.current_publication_digest,
        "current_authority_digest": value.current_authority_digest,
        "current_head_sha": value.current_head_sha,
        "current_tree_sha": value.current_tree_sha,
        "resulting_head_sha": value.resulting_head_sha,
        "resulting_tree_sha": value.resulting_tree_sha,
        "failure_observation_digest": value.failure_observation_digest,
        "defect_proof_digest": value.defect_proof_digest,
        "candidate_validation_digest": value.candidate_validation_digest,
        "correction_authentication_digest": value.correction_authentication_digest,
        "finding_id": value.finding_id,
    }


_FAILURE_OBSERVATION_FIELDS = frozenset(
    {
        "repository", "pull_request", "head_sha", "pr_state", "draft",
        "workflow_name", "workflow_path", "check_name", "workflow_run_id", "check_run_id",
        "status", "conclusion", "attempt",
    }
)


def _read_live_post_ready_failure(repository: str, pull_request: int) -> dict[str, Any]:
    """Read one deterministic terminal failure from the exact live PR head."""

    result = publication._run_gh([
        "pr", "view", str(pull_request), "--repo", repository,
        "--json", "state,isDraft,headRefOid,headRepository,statusCheckRollup",
    ])
    if result.returncode != 0:
        raise LifecycleOrchestrationError("live validation failure is unavailable")
    try:
        payload = json.loads(
            result.stdout,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        if (
            payload.get("state") != "OPEN"
            or payload.get("isDraft") is not False
            or (payload.get("headRepository") or {}).get("nameWithOwner")
            != repository
        ):
            raise LifecycleOrchestrationError(
                "live validation failure does not belong to an OPEN Ready PR"
            )
        failures = [
            item for item in payload.get("statusCheckRollup", [])
            if isinstance(item, dict)
            and item.get("__typename") == "CheckRun"
            and item.get("status") == "COMPLETED"
            and item.get("conclusion") == "FAILURE"
            and isinstance(item.get("detailsUrl"), str)
        ]
        failures.sort(key=lambda item: (
            str(item.get("workflowName", "")), str(item.get("name", "")),
            str(item.get("detailsUrl", "")),
        ))
        if len(failures) != 1:
            raise LifecycleOrchestrationError(
                "exact current head must have one unique terminal validation failure"
            )
        failure = failures[0]
        match = re.fullmatch(
            r"https://github\.com/([^/]+/[^/]+)/actions/runs/([1-9][0-9]*)/job/([1-9][0-9]*)",
            failure["detailsUrl"],
        )
        if match is None or match.group(1) != repository:
            raise LifecycleOrchestrationError(
                "validation failure run identity is malformed or cross-repository"
            )
        workflow_run_id = int(match.group(2))
        run = publication._run_gh([
            "api", "--hostname", "github.com",
            f"repos/{repository}/actions/runs/{workflow_run_id}",
        ])
        if run.returncode != 0:
            raise LifecycleOrchestrationError(
                "validation failure attempt identity is unavailable"
            )
        run_payload = json.loads(
            run.stdout,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        if (
            run_payload.get("id") != workflow_run_id
            or run_payload.get("head_sha") != payload.get("headRefOid")
            or run_payload.get("status") != "completed"
            or run_payload.get("conclusion") != "failure"
            or (run_payload.get("repository") or {}).get("full_name") != repository
            or not isinstance(run_payload.get("path"), str)
            or not run_payload["path"].startswith(".github/workflows/")
        ):
            raise LifecycleOrchestrationError(
                "validation failure attempt differs from the current PR head"
            )
        job = publication._run_gh([
            "api", "--hostname", "github.com",
            f"repos/{repository}/actions/jobs/{match.group(3)}",
        ])
        if job.returncode != 0:
            raise LifecycleOrchestrationError(
                "validation failure job identity is unavailable"
            )
        job_payload = json.loads(
            job.stdout,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        if (
            job_payload.get("id") != int(match.group(3))
            or job_payload.get("run_id") != workflow_run_id
            or job_payload.get("head_sha") != payload.get("headRefOid")
            or job_payload.get("status") != "completed"
            or job_payload.get("conclusion") != "failure"
            or job_payload.get("name") != failure.get("name")
        ):
            raise LifecycleOrchestrationError(
                "validation failure job differs from the selected failed check"
            )
        return {
            "repository": repository,
            "pull_request": pull_request,
            "head_sha": payload["headRefOid"],
            "pr_state": payload["state"],
            "draft": payload["isDraft"],
            "workflow_name": failure.get("workflowName"),
            "workflow_path": run_payload["path"],
            "check_name": failure.get("name"),
            "workflow_run_id": workflow_run_id,
            "check_run_id": int(match.group(3)),
            "status": failure["status"],
            "conclusion": failure["conclusion"],
            "attempt": run_payload.get("run_attempt"),
        }
    except LifecycleOrchestrationError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LifecycleOrchestrationError(
            "live validation failure evidence is malformed"
        ) from exc


def _validated_failure_observation(
    value: Any, lifecycle: authority.VerifiedLifecycleAuthority,
) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict) or set(value) != _FAILURE_OBSERVATION_FIELDS:
        raise LifecycleOrchestrationError("validation failure observation is not closed")
    if (
        value["repository"] != lifecycle.repository
        or value["pull_request"] != lifecycle.pull_request
        or value["head_sha"] != lifecycle.head_sha
        or value["pr_state"] != "OPEN"
        or value["draft"] is not False
        or value["status"] != "COMPLETED"
        or value["conclusion"] != "FAILURE"
        or not isinstance(value["workflow_name"], str)
        or not value["workflow_name"].strip()
        or not isinstance(value["workflow_path"], str)
        or not re.fullmatch(r"\.github/workflows/[^/]+\.ya?ml", value["workflow_path"])
        or not isinstance(value["check_name"], str)
        or not value["check_name"].strip()
        or any(
            not isinstance(value[field], int)
            or isinstance(value[field], bool)
            or value[field] <= 0
            for field in ("workflow_run_id", "check_run_id", "attempt")
        )
    ):
        raise LifecycleOrchestrationError(
            "validation failure is stale, non-terminal, or cross-identity"
        )
    normalized = copy.deepcopy(value)
    return normalized, fast_path.digest_json({
        "domain": "secpal.post-ready-validation-failure-observation/v1",
        **normalized,
    })


def _git_text(root: Path, revision: str, path: str) -> str:
    result = publication._run_git(root, ["show", f"{revision}:{path}"])
    if result.returncode != 0:
        raise LifecycleOrchestrationError(
            "candidate invariant input is unavailable from authenticated bytes"
        )
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LifecycleOrchestrationError(
            "candidate invariant input is not UTF-8"
        ) from exc


def _node_version_floor(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^\s*(?:\^|~|>=\s*)?([0-9]+)(?:\.([0-9xX*]+))?(?:\.([0-9xX*]+))?", value)
    if match is None:
        return None
    parts = [match.group(1), match.group(2), match.group(3)]
    return tuple(
        0 if part is None or part.lower() in {"x", "*"} else int(part)
        for part in parts
    )


def _setup_node_selectors(workflow: str) -> tuple[str, ...]:
    lines = workflow.splitlines()
    selectors: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(r"\buses:\s*actions/setup-node@", line):
            continue
        uses_indentation = len(line) - len(line.lstrip())
        uses_key_indentation = uses_indentation + (
            2 if re.match(r"^\s*-\s+uses:", line) else 0
        )
        step_indentation = uses_indentation
        if not re.match(r"^\s*-\s+uses:", line):
            for predecessor in reversed(lines[:index]):
                if not predecessor.strip():
                    continue
                predecessor_indent = len(predecessor) - len(predecessor.lstrip())
                if predecessor_indent < uses_indentation:
                    if re.match(r"^\s*-\s+", predecessor):
                        step_indentation = predecessor_indent
                    break
        with_indentation: int | None = None
        for candidate in lines[index + 1 :]:
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if (
                candidate.strip()
                and candidate_indent <= step_indentation
                and re.match(r"^\s*-\s+", candidate)
            ):
                break
            if re.match(r"^\s*with:\s*(?:#.*)?$", candidate):
                if candidate_indent != uses_key_indentation:
                    break
                with_indentation = candidate_indent
                continue
            if with_indentation is None:
                continue
            if candidate.strip() and candidate_indent <= with_indentation:
                break
            match = re.match(
                r"^\s*node-version:\s*['\"]?([^'\"#]+?)['\"]?\s*(?:#.*)?$",
                candidate,
            )
            if match:
                selectors.append(match.group(1).strip())
                break
    return tuple(selectors)


def _workflow_name(workflow: str) -> str | None:
    for line in workflow.splitlines():
        match = re.match(r"^name:\s*['\"]?([^'\"#]+?)['\"]?\s*(?:#.*)?$", line)
        if match:
            return match.group(1).strip()
    return None


def _node_engine_contract(root: Path, revision: str) -> str:
    try:
        package = json.loads(
            _git_text(root, revision, "package.json"),
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
        engine = package["engines"]["node"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LifecycleOrchestrationError(
            "candidate Node engine contract is unavailable or malformed"
        ) from exc
    if not isinstance(engine, str) or not engine.strip():
        raise LifecycleOrchestrationError(
            "candidate Node engine contract is unavailable or malformed"
        )
    return engine


def _node_selector_violations(root: Path, revision: str) -> tuple[dict[str, Any], ...]:
    engine = _node_engine_contract(root, revision)
    engine_floor = _node_version_floor(engine)
    if engine_floor is None:
        raise LifecycleOrchestrationError(
            "candidate Node engine floor cannot be derived deterministically"
        )
    listed = publication._run_git(
        root,
        ["ls-tree", "-r", "--name-only", revision, "--", ".github/workflows"],
    )
    if listed.returncode != 0:
        raise LifecycleOrchestrationError("candidate workflow bytes are unavailable")
    paths = sorted(
        path for path in listed.stdout.decode("utf-8").splitlines()
        if path.endswith((".yml", ".yaml"))
    )
    violations: list[dict[str, Any]] = []
    for path in paths:
        workflow = _git_text(root, revision, path)
        workflow_name = _workflow_name(workflow)
        for selector in _setup_node_selectors(workflow):
            selector_floor = _node_version_floor(selector)
            if (
                selector_floor is not None
                and selector_floor < engine_floor
            ):
                violations.append({
                    "path": path,
                    "workflow_name": workflow_name,
                    "selector": selector,
                    "selector_floor": ".".join(map(str, selector_floor)),
                    "engine": engine,
                    "engine_floor": ".".join(map(str, engine_floor)),
                })
    return tuple(violations)


def _require_corrected_selector_contract(
    root: Path,
    revision: str,
    paths: set[str],
    engine_floor: tuple[int, int, int],
) -> None:
    """Require every corrected setup-node step to retain one parseable safe selector."""

    for path in sorted(paths):
        workflow = _git_text(root, revision, path)
        setup_count = len(re.findall(r"\buses:\s*actions/setup-node@", workflow))
        selectors = _setup_node_selectors(workflow)
        floors = tuple(_node_version_floor(selector) for selector in selectors)
        if (
            setup_count == 0
            or len(selectors) != setup_count
            or any(floor is None or floor < engine_floor for floor in floors)
        ):
            raise LifecycleOrchestrationError(
                "corrected workflow selector is missing, unparseable, or below the engine floor"
            )


def _content_owned_toolchain_guard(
    root: Path, predecessor_head: str, resulting_head: str, path: str
) -> bool:
    """Admit an existing guard only when its changed hunk proves toolchain ownership."""

    try:
        before = _git_text(root, predecessor_head, path)
        after = _git_text(root, resulting_head, path)
    except LifecycleOrchestrationError:
        return False
    ownership_terms = ("actions/setup-node", "node-version", "engines.node")
    if any(term not in before or term not in after for term in ownership_terms):
        return False
    diff = publication._run_git(
        root,
        ["diff", "--unified=12", predecessor_head, resulting_head, "--", path],
    )
    if diff.returncode != 0:
        return False
    hunks = re.split(r"(?=^@@ )", diff.stdout.decode("utf-8"), flags=re.MULTILINE)[1:]
    return bool(hunks) and all(
        "actions/setup-node" in hunk
        and "node-version" in hunk
        and "engines.node" in hunk
        for hunk in hunks
    )


def _verify_node_selector_defect_correction(
    root: Path,
    *,
    repository: str,
    pull_request: int,
    predecessor_head: str,
    predecessor_tree: str,
    resulting_head: str,
    resulting_tree: str,
    observed_workflow_name: str,
    observed_workflow_path: str,
) -> str:
    head = publication._run_git(root, ["rev-parse", "HEAD"])
    tree = publication._run_git(root, ["rev-parse", "HEAD^{tree}"])
    parent = publication._run_git(root, ["rev-parse", "HEAD^"])
    predecessor_tree_result = publication._run_git(
        root, ["rev-parse", f"{predecessor_head}^{{tree}}"]
    )
    if (
        head.returncode != 0
        or tree.returncode != 0
        or parent.returncode != 0
        or predecessor_tree_result.returncode != 0
        or head.stdout.decode().strip() != resulting_head
        or tree.stdout.decode().strip() != resulting_tree
        or parent.stdout.decode().strip() != predecessor_head
        or predecessor_tree_result.stdout.decode().strip() != predecessor_tree
    ):
        raise LifecycleOrchestrationError(
            "correction is not the exact sole-parent successor"
        )
    predecessor_violations = _node_selector_violations(root, predecessor_head)
    resulting_violations = _node_selector_violations(root, resulting_head)
    if (
        _node_engine_contract(root, predecessor_head)
        != _node_engine_contract(root, resulting_head)
    ):
        raise LifecycleOrchestrationError(
            "correction changed rather than enforced the candidate engine contract"
        )
    observed_violations = tuple(
        item for item in predecessor_violations
        if (
            item["workflow_name"] == observed_workflow_name
            and item["path"] == observed_workflow_path
        )
    )
    if not observed_violations or resulting_violations:
        raise LifecycleOrchestrationError(
            "candidate defect is not independently reproduced and corrected"
        )
    changed = publication._run_git(
        root, ["diff-tree", "--no-commit-id", "--name-only", "-r", resulting_head]
    )
    if changed.returncode != 0:
        raise LifecycleOrchestrationError("correction path evidence is unavailable")
    changed_paths = sorted(filter(None, changed.stdout.decode("utf-8").splitlines()))
    relevant_workflows = {item["path"] for item in predecessor_violations}
    engine_floor = _node_version_floor(_node_engine_contract(root, resulting_head))
    if engine_floor is None:
        raise LifecycleOrchestrationError(
            "corrected Node engine floor cannot be derived deterministically"
        )
    _require_corrected_selector_contract(
        root, resulting_head, relevant_workflows, engine_floor
    )
    def relevant(path: str) -> bool:
        return (
            path in relevant_workflows
            or _content_owned_toolchain_guard(
                root, predecessor_head, resulting_head, path
            )
        )
    if not changed_paths or any(not relevant(path) for path in changed_paths):
        raise LifecycleOrchestrationError(
            "correction contains changes unrelated to the reproduced defect"
        )
    proof = {
        "domain": "secpal.workflow-node-selector-engine-proof/v1",
        "repository": repository,
        "pull_request": pull_request,
        "predecessor_head_sha": predecessor_head,
        "predecessor_tree_sha": predecessor_tree,
        "resulting_head_sha": resulting_head,
        "resulting_tree_sha": resulting_tree,
        "classification": "IN_CONTRACT_DEFECT",
        "technically_blocking": True,
        "observed_workflow_name": observed_workflow_name,
        "observed_workflow_path": observed_workflow_path,
        "violations": list(observed_violations),
        "changed_paths": changed_paths,
    }
    return fast_path.digest_json(proof)


def _ordinary_ready_remediation_finding_authority_projection(
    value: VerifiedOrdinaryReadyRemediationFindingAuthority,
) -> dict[str, Any]:
    return {
        "domain": "secpal.ordinary-ready-remediation-finding-authority/v1",
        "repository": value.repository,
        "delivery_issue": value.delivery_issue,
        "pull_request": value.pull_request,
        "lifecycle_id": value.lifecycle_id,
        "current_publication_oid": value.current_publication_oid,
        "current_publication_digest": value.current_publication_digest,
        "current_authority_digest": value.current_authority_digest,
        "provider_head_sha": value.provider_head_sha,
        "current_head_sha": value.current_head_sha,
        "resulting_head_sha": value.resulting_head_sha,
        "predecessor_state_digest": value.predecessor_state_digest,
        "resulting_state_digest": value.resulting_state_digest,
        "provider_growth_digest": value.provider_growth_digest,
        "predecessor_eligibility_evidence_digest": (
            value.predecessor_eligibility_evidence_digest
        ),
        "eligibility_evidence_digest": value.eligibility_evidence_digest,
        "finding_ids": list(value.finding_ids),
        "thread_ids": list(value.thread_ids),
    }


def verify_ready_remediation_provider_growth_authority(
    current: publication.VerifiedLifecyclePublication,
    *,
    predecessor_validation: fast_path.VerifiedValidationEvidence,
    candidate_validation: fast_path.VerifiedValidationEvidence,
    predecessor_eligibility_evidence: Any,
    eligibility_evidence: Any,
) -> VerifiedOrdinaryReadyRemediationFindingAuthority:
    """Compose existing CURRENT, validation, feedback, and eligibility authority."""

    if not isinstance(current, publication.VerifiedLifecyclePublication):
        raise LifecycleOrchestrationError(
            "ordinary Ready provider growth requires authenticated CURRENT"
        )
    lifecycle = current.lifecycle
    try:
        state = authority._validate_state(copy.deepcopy(lifecycle.state))
        reviewed, predecessor_eligibility = (
            fast_path.verified_validation_review_context(predecessor_validation)
        )
        resulting, candidate_eligibility = (
            fast_path.verified_validation_review_context(candidate_validation)
        )
        eligibility = fast_path.normalize_resolution_eligibility_evidence(
            eligibility_evidence,
            repository=lifecycle.repository,
            reviewed_state=resulting,
        )
        predecessor_eligibility_document = (
            fast_path.normalize_resolution_eligibility_evidence(
                predecessor_eligibility_evidence,
                repository=lifecycle.repository,
                reviewed_state=reviewed,
            )
        )
        provider = publication.derive_ready_source_recovery_provider_binding(
            current
        )
        live_resulting = _capture_current_stable_feedback(
            lifecycle.repository,
            lifecycle.pull_request,
            ready_remediation_provider_binding=provider,
        )
    except (
        authority.LifecycleAuthorityError,
        fast_path.SecurityBlocker,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "ordinary Ready provider growth source authority is invalid"
        ) from exc

    if (
        state["unrestricted_review_count"] != authority.MAX_UNRESTRICTED_REVIEWS
        or state["remediation_cycle_count"] != 1
        or state["remediation_cycle_count"] >= authority.MAX_REMEDIATION_CYCLES
        or state["cycle_3_absent"] is not True
        or state["draft"] is not False
        or state["ready"] is not True
        or state["ready_transition_count"] != 1
        or state["exceptional_recovery_count"] != 0
        or state["exceptional_continuation_count"] != 0
        or predecessor_eligibility is None
        or predecessor_validation.repository != lifecycle.repository
        or predecessor_validation.delivery_issue_number != lifecycle.delivery_issue
        or predecessor_validation.pull_request_number != lifecycle.pull_request
        or predecessor_validation.head_sha != lifecycle.head_sha
        or predecessor_validation.tree_sha != lifecycle.tree_sha
        or predecessor_validation.validation_receipt_digest
        != lifecycle.validation_receipt_digest
        or predecessor_validation.final_attestation_digest
        != lifecycle.adoption_source_evidence_digest
        or candidate_validation.repository != lifecycle.repository
        or candidate_validation.delivery_issue_number != lifecycle.delivery_issue
        or candidate_validation.pull_request_number != lifecycle.pull_request
        or candidate_validation.head_sha == lifecycle.head_sha
        or resulting.repository != lifecycle.repository
        or resulting.pull_request_number != lifecycle.pull_request
        or resulting.head_sha != lifecycle.head_sha
        or live_resulting.to_dict() != resulting.to_dict()
        or reviewed.repository != lifecycle.repository
        or reviewed.pull_request_number != lifecycle.pull_request
        or provider.repository != lifecycle.repository
        or provider.delivery_issue != lifecycle.delivery_issue
        or provider.pull_request != lifecycle.pull_request
        or provider.lifecycle_id != lifecycle.lifecycle_id
        or provider.current_head_sha != lifecycle.head_sha
        or provider.current_authority_digest != lifecycle.authority_digest
        or provider.current_publication_oid != current.publication_oid
        or provider.current_publication_digest != current.publication_digest
        or publication.ORDINARY_REMEDIATION_SUFFIX
        not in provider.provider_binding_sources
        or len(provider.remediation_event_digests) != 1
        or reviewed.head_sha != provider.provider_head_sha
        or predecessor_eligibility
        != fast_path.digest_json(predecessor_eligibility_document)
        or candidate_eligibility != fast_path.digest_json(eligibility)
    ):
        raise LifecycleOrchestrationError(
            "ordinary Ready provider growth differs from the remaining remediation slot"
        )

    try:
        growth = fast_path.verify_ordinary_ready_remediation_provider_growth(
            reviewed,
            resulting,
            provider_head_sha=provider.provider_head_sha,
            predecessor_eligibility_evidence=predecessor_eligibility_document,
            eligibility_evidence=eligibility,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "ordinary Ready provider growth is incomplete or unauthenticated"
        ) from exc
    fields = {
        "repository": lifecycle.repository,
        "delivery_issue": lifecycle.delivery_issue,
        "pull_request": lifecycle.pull_request,
        "lifecycle_id": lifecycle.lifecycle_id,
        "current_publication_oid": current.publication_oid,
        "current_publication_digest": current.publication_digest,
        "current_authority_digest": lifecycle.authority_digest,
        "provider_head_sha": provider.provider_head_sha,
        "current_head_sha": lifecycle.head_sha,
        "resulting_head_sha": candidate_validation.head_sha,
        "predecessor_state_digest": growth.predecessor_state_digest,
        "resulting_state_digest": growth.resulting_state_digest,
        "provider_growth_digest": growth.growth_digest,
        "predecessor_eligibility_evidence_digest": predecessor_eligibility,
        "eligibility_evidence_digest": growth.eligibility_evidence_digest,
        "finding_ids": growth.finding_ids,
        "thread_ids": growth.thread_ids,
    }
    provisional = VerifiedOrdinaryReadyRemediationFindingAuthority(
        **fields,
        finding_authority_digest="0" * 64,
        _verification_seal=None,
    )
    digest = fast_path.digest_json(
        _ordinary_ready_remediation_finding_authority_projection(provisional)
    )
    return VerifiedOrdinaryReadyRemediationFindingAuthority(
        **fields,
        finding_authority_digest=digest,
        _verification_seal=_ORDINARY_READY_REMEDIATION_FINDING_AUTHORITY_SEAL,
    )


def ordinary_ready_remediation_authorization_scope(
    value: (
        VerifiedOrdinaryReadyRemediationFindingAuthority
        | VerifiedPostReadyValidationDefectAuthority
    ),
) -> dict[str, Any]:
    """Derive the existing ordinary authorization scope without a caller subset."""

    if isinstance(value, VerifiedPostReadyValidationDefectAuthority):
        if (
            value._verification_seal
            is not _POST_READY_VALIDATION_DEFECT_AUTHORITY_SEAL
            or value.finding_authority_digest
            != fast_path.digest_json(_post_ready_validation_defect_projection(value))
        ):
            raise LifecycleOrchestrationError(
                "post-Ready validation-defect authority is unauthenticated"
            )
        return {
            "pull_request": value.pull_request,
            "predecessor_head_sha": value.current_head_sha,
            "resulting_head_sha": value.resulting_head_sha,
            "finding_ids": [value.finding_id],
            "finding_authority_digest": value.finding_authority_digest,
        }
    if (
        not isinstance(value, VerifiedOrdinaryReadyRemediationFindingAuthority)
        or value._verification_seal
        is not _ORDINARY_READY_REMEDIATION_FINDING_AUTHORITY_SEAL
        or value.finding_authority_digest
        != fast_path.digest_json(
            _ordinary_ready_remediation_finding_authority_projection(value)
        )
    ):
        raise LifecycleOrchestrationError(
            "ordinary Ready remediation finding authority is unauthenticated"
        )
    return {
        "pull_request": value.pull_request,
        "predecessor_head_sha": value.current_head_sha,
        "resulting_head_sha": value.resulting_head_sha,
        "finding_ids": list(value.finding_ids),
        "finding_authority_digest": value.finding_authority_digest,
    }


def _verify_post_ready_validation_defect_authority(
    current: publication.VerifiedLifecyclePublication,
    *,
    candidate_validation: fast_path.VerifiedValidationEvidence,
    authenticated_commit: fast_path.AuthenticatedIntegrationCommit,
    repository_root: Path | str,
    failure_reader: Callable[[str, int], Any] = _read_live_post_ready_failure,
) -> VerifiedPostReadyValidationDefectAuthority:
    """Admit one exact validation defect into the existing remaining slot."""

    if not isinstance(current, publication.VerifiedLifecyclePublication):
        raise LifecycleOrchestrationError(
            "post-Ready validation remediation requires authenticated CURRENT"
        )
    lifecycle = current.lifecycle
    try:
        state = authority._validate_state(copy.deepcopy(lifecycle.state))
        root = Path(repository_root).resolve(strict=True)
    except (authority.LifecycleAuthorityError, OSError, RuntimeError) as exc:
        raise LifecycleOrchestrationError(
            "post-Ready validation remediation source authority is invalid"
        ) from exc
    if (
        state["unrestricted_review_count"] != authority.MAX_UNRESTRICTED_REVIEWS
        or state["remediation_cycle_count"] != 1
        or state["remediation_cycle_count"] >= authority.MAX_REMEDIATION_CYCLES
        or state["cycle_3_absent"] is not True
        or state["draft"] is not False
        or state["ready"] is not True
        or state["ready_transition_count"] != 1
        or state["exceptional_recovery_count"] != 0
        or state["exceptional_continuation_count"] != 0
        or not isinstance(lifecycle.tree_sha, str)
    ):
        raise LifecycleOrchestrationError(
            "post-Ready validation remediation requires the exact remaining-slot state"
        )
    observation, observation_digest = _validated_failure_observation(
        failure_reader(lifecycle.repository, lifecycle.pull_request), lifecycle
    )
    try:
        reviewed_state, _eligibility_digest = (
            fast_path.verified_validation_review_context(candidate_validation)
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "corrected candidate reviewed-head authority is invalid"
        ) from exc
    if (
        reviewed_state.repository != lifecycle.repository
        or reviewed_state.pull_request_number != lifecycle.pull_request
        or reviewed_state.head_sha != lifecycle.head_sha
    ):
        raise LifecycleOrchestrationError(
            "corrected candidate validation is not bound to the CURRENT reviewed head"
        )
    if (
        not fast_path.is_verified_validation_evidence(candidate_validation)
        or candidate_validation.repository != lifecycle.repository
        or candidate_validation.delivery_issue_number != lifecycle.delivery_issue
        or candidate_validation.pull_request_number != lifecycle.pull_request
        or candidate_validation.head_sha == lifecycle.head_sha
        or candidate_validation.validation_receipt_digest
        == lifecycle.validation_receipt_digest
        or candidate_validation.final_attestation_digest
        == lifecycle.adoption_source_evidence_digest
        or not fast_path._authenticated_integration_commit_agrees(
            authenticated_commit,
            repository=lifecycle.repository,
            head_sha=candidate_validation.head_sha,
            tree_sha=candidate_validation.tree_sha,
            parent_shas=[lifecycle.head_sha],
            expected_signer={
                "kind": authenticated_commit.signer_kind,
                "identity": authenticated_commit.signer_identity,
            },
        )
    ):
        raise LifecycleOrchestrationError(
            "corrected candidate validation, topology, or signer is invalid"
        )
    proof_digest = _verify_node_selector_defect_correction(
        root,
        repository=lifecycle.repository,
        pull_request=lifecycle.pull_request,
        predecessor_head=lifecycle.head_sha,
        predecessor_tree=lifecycle.tree_sha,
        resulting_head=candidate_validation.head_sha,
        resulting_tree=candidate_validation.tree_sha,
        observed_workflow_name=observation["workflow_name"],
        observed_workflow_path=observation["workflow_path"],
    )
    candidate_validation_digest = fast_path.digest_json(
        fast_path._validation_evidence_binding(candidate_validation)
    )
    finding_id = f"POST_READY_VALIDATION:{proof_digest[:32]}"
    fields = {
        "source_kind": "POST_READY_IN_CONTRACT_VALIDATION_DEFECT",
        "classification": "IN_CONTRACT_DEFECT",
        "technically_blocking": True,
        "repository": lifecycle.repository,
        "delivery_issue": lifecycle.delivery_issue,
        "pull_request": lifecycle.pull_request,
        "lifecycle_id": lifecycle.lifecycle_id,
        "current_publication_oid": current.publication_oid,
        "current_publication_digest": current.publication_digest,
        "current_authority_digest": lifecycle.authority_digest,
        "current_head_sha": lifecycle.head_sha,
        "current_tree_sha": lifecycle.tree_sha,
        "resulting_head_sha": candidate_validation.head_sha,
        "resulting_tree_sha": candidate_validation.tree_sha,
        "failure_observation_digest": observation_digest,
        "defect_proof_digest": proof_digest,
        "candidate_validation_digest": candidate_validation_digest,
        "correction_authentication_digest": authenticated_commit.authentication_digest,
        "finding_id": finding_id,
    }
    provisional = VerifiedPostReadyValidationDefectAuthority(
        **fields,
        finding_authority_digest="0" * 64,
        _verification_seal=None,
    )
    digest = fast_path.digest_json(_post_ready_validation_defect_projection(provisional))
    return VerifiedPostReadyValidationDefectAuthority(
        **fields,
        finding_authority_digest=digest,
        _verification_seal=_POST_READY_VALIDATION_DEFECT_AUTHORITY_SEAL,
    )


def _authenticate_maintained_correction_commit(
    repository_root: Path | str,
    repository: str,
    head_sha: str,
) -> fast_path.AuthenticatedIntegrationCommit:
    """Authenticate the correction from Git and live GitHub under maintained trust."""

    from . import lifecycle_execution

    try:
        policy = authority._load_lifecycle_trust_policy(repository)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "correction signer policy is unavailable"
        ) from exc
    authenticated: list[fast_path.AuthenticatedIntegrationCommit] = []
    for identity in sorted(policy.transition_signer_identities):
        try:
            authenticated.append(
                lifecycle_execution._authenticate_source_commit(
                    repository,
                    head_sha,
                    identity,
                    repository_root=repository_root,
                )
            )
        except lifecycle_execution.LifecycleExecutionError:
            continue
    if len(authenticated) != 1:
        raise LifecycleOrchestrationError(
            "correction signer is invalid or ambiguous under maintained trust"
        )
    return authenticated[0]


def verify_post_ready_validation_defect_authority(
    current: publication.VerifiedLifecyclePublication,
    *,
    candidate_validation: fast_path.VerifiedValidationEvidence,
    repository_root: Path | str,
) -> VerifiedPostReadyValidationDefectAuthority:
    """Use only the maintained live GitHub observation boundary in production."""

    authenticated_commit = _authenticate_maintained_correction_commit(
        repository_root,
        current.lifecycle.repository,
        candidate_validation.head_sha,
    )
    return _verify_post_ready_validation_defect_authority(
        current,
        candidate_validation=candidate_validation,
        authenticated_commit=authenticated_commit,
        repository_root=repository_root,
        failure_reader=_read_live_post_ready_failure,
    )


def issue_post_ready_validation_remediation_authorization(
    *,
    authorization_id: str,
    reason: str,
    current: publication.VerifiedLifecyclePublication,
    finding_authority: VerifiedPostReadyValidationDefectAuthority,
    signer_identity: str,
    signer: authority.Signer,
) -> bytes:
    """Issue one-use ordinary remediation from the sealed defect proof."""

    if not isinstance(finding_authority, VerifiedPostReadyValidationDefectAuthority):
        raise LifecycleOrchestrationError(
            "post-Ready validation-defect authority source is invalid"
        )
    scope = ordinary_ready_remediation_authorization_scope(finding_authority)
    lifecycle = current.lifecycle if isinstance(
        current, publication.VerifiedLifecyclePublication
    ) else None
    if (
        not isinstance(lifecycle, authority.VerifiedLifecycleAuthority)
        or finding_authority.repository != lifecycle.repository
        or finding_authority.delivery_issue != lifecycle.delivery_issue
        or finding_authority.pull_request != lifecycle.pull_request
        or finding_authority.lifecycle_id != lifecycle.lifecycle_id
        or finding_authority.current_publication_oid != current.publication_oid
        or finding_authority.current_publication_digest != current.publication_digest
        or finding_authority.current_authority_digest != lifecycle.authority_digest
        or finding_authority.current_head_sha != lifecycle.head_sha
        or finding_authority.current_tree_sha != lifecycle.tree_sha
    ):
        raise LifecycleOrchestrationError(
            "post-Ready validation-defect authority is stale or substituted"
        )
    return _create_user_authorization(
        authorization_id=authorization_id,
        repository=lifecycle.repository,
        delivery_issue=lifecycle.delivery_issue,
        lifecycle=lifecycle,
        publication_oid=current.publication_oid,
        publication_digest=current.publication_digest,
        operation="REMEDIATION_COMPLETED",
        reason=reason,
        scope=scope,
        signer_identity=signer_identity,
        signer=signer,
        allow_finding_authority_digest=True,
    )


def issue_ready_remediation_provider_growth_authorization(
    *,
    authorization_id: str,
    reason: str,
    current: publication.VerifiedLifecyclePublication,
    finding_authority: VerifiedOrdinaryReadyRemediationFindingAuthority,
    signer_identity: str,
    signer: authority.Signer,
) -> bytes:
    """Issue the existing ordinary authorization from verifier-derived findings."""

    if not isinstance(
        finding_authority, VerifiedOrdinaryReadyRemediationFindingAuthority
    ):
        raise LifecycleOrchestrationError(
            "ordinary Ready provider-growth authority source is invalid"
        )
    scope = ordinary_ready_remediation_authorization_scope(finding_authority)
    lifecycle = current.lifecycle if isinstance(
        current, publication.VerifiedLifecyclePublication
    ) else None
    if (
        not isinstance(lifecycle, authority.VerifiedLifecycleAuthority)
        or finding_authority.repository != lifecycle.repository
        or finding_authority.delivery_issue != lifecycle.delivery_issue
        or finding_authority.pull_request != lifecycle.pull_request
        or finding_authority.lifecycle_id != lifecycle.lifecycle_id
        or finding_authority.current_publication_oid != current.publication_oid
        or finding_authority.current_publication_digest
        != current.publication_digest
        or finding_authority.current_authority_digest != lifecycle.authority_digest
        or finding_authority.current_head_sha != lifecycle.head_sha
    ):
        raise LifecycleOrchestrationError(
            "ordinary Ready remediation finding authority is stale or substituted"
        )
    return _create_user_authorization(
        authorization_id=authorization_id,
        repository=lifecycle.repository,
        delivery_issue=lifecycle.delivery_issue,
        lifecycle=lifecycle,
        publication_oid=current.publication_oid,
        publication_digest=current.publication_digest,
        operation="REMEDIATION_COMPLETED",
        reason=reason,
        scope=scope,
        signer_identity=signer_identity,
        signer=signer,
        allow_finding_authority_digest=True,
    )


@dataclass(frozen=True)
class VerifiedRejectedContinuationReanchor:
    """Closed diagnostic authority for one rejected unpublished candidate."""

    evidence_digest: str
    original_pull_request: int
    replacement_pull_request: int
    rejected_candidate_head_sha: str
    rejected_candidate_tree_sha: str
    rejected_continuation_evidence_digest: str
    rejected_validation_receipt_digest: str
    rejected_final_attestation_digest: str
    rejected_state_digest: str
    replacement_state_digest: str
    material_finding_ids: tuple[str, ...]
    material_thread_ids: tuple[str, ...]
    finding_source_digest: str
    historical_accepted_main_base_sha: str | None = None
    current_protected_main_base_sha: str | None = None
    provider_reaction_replacement_digest: str | None = None


def _continuation_authorization_scope(
    findings: VerifiedContinuationFindingAuthority,
    *,
    pull_request: int,
    predecessor_head_sha: str,
    resulting_head_sha: str,
) -> dict[str, Any]:
    """Own the exact signed scope for both existing Continuation evidence forms."""

    scope = {
        "pull_request": pull_request,
        "predecessor_head_sha": predecessor_head_sha,
        "resulting_head_sha": resulting_head_sha,
        "reviewed_state_digest": findings.reviewed_state_digest,
        "reviewed_feedback_digest": findings.reviewed_feedback_digest,
        "eligibility_evidence_digest": findings.eligibility_evidence_digest,
        "finding_ids": list(findings.finding_ids),
        "thread_ids": list(findings.thread_ids),
    }
    if findings.reanchor is not None:
        reanchor = findings.reanchor
        scope.update(
            {
                "original_pull_request": reanchor.original_pull_request,
                "continuation_tree_sha": findings.continuation_tree_sha,
                "reanchor_evidence_digest": reanchor.evidence_digest,
                "rejected_candidate_head_sha": reanchor.rejected_candidate_head_sha,
                "rejected_candidate_tree_sha": reanchor.rejected_candidate_tree_sha,
                "rejected_continuation_evidence_digest": (
                    reanchor.rejected_continuation_evidence_digest
                ),
                "rejected_validation_receipt_digest": (
                    reanchor.rejected_validation_receipt_digest
                ),
                "rejected_final_attestation_digest": (
                    reanchor.rejected_final_attestation_digest
                ),
                "rejected_state_digest": reanchor.rejected_state_digest,
                "replacement_state_digest": reanchor.replacement_state_digest,
                "finding_source_digest": reanchor.finding_source_digest,
                "corrected_successor_state_digest": (
                    findings.corrected_successor_state_digest
                ),
                **(
                    {
                        "predecessor_provider_growth_digest": (
                            findings.predecessor_provider_growth_digest
                        )
                    }
                    if findings.predecessor_provider_growth_digest is not None
                    else {}
                ),
                **(
                    {
                        "provider_reaction_replacement_digest": (
                            reanchor.provider_reaction_replacement_digest
                        )
                    }
                    if reanchor.provider_reaction_replacement_digest is not None
                    else {}
                ),
            }
        )
    return scope


def _capture_current_stable_feedback(
    repository: str,
    pull_request: int,
    *,
    ready_remediation_provider_binding: (
        publication.VerifiedReadySourceRecoveryProviderBinding | None
    ) = None,
) -> fast_path.StableFeedbackState:
    """Reuse the maintained bounded provider capture without duplicating it."""

    repository_root = Path(__file__).resolve().parents[2]
    action = repository_root / "scripts/secpal-pr-review-actions.py"
    try:
        environment = bootstrap_source_admission._closed_launcher_environment(
            authority._load_trusted_command_helper()
        )
        with tempfile.TemporaryDirectory(
            prefix="secpal-continuation-feedback-"
        ) as directory:
            output = Path(directory) / "reviewed-state.json"
            provider_binding = Path(directory) / "provider-binding.json"
            arguments = [
                bootstrap_source_admission._trusted_python(),
                "-I",
                "-B",
                str(action),
                "resolve-batch",
                "--repo",
                repository,
                "--pr",
                str(pull_request),
                "--repo-root",
                str(repository_root),
                "--capture-reviewed-state",
                str(output),
            ]
            if ready_remediation_provider_binding is not None:
                binding = ready_remediation_provider_binding
                fast_path.atomic_write_json(
                    provider_binding,
                    {
                        "repository": binding.repository,
                        "pull_request": binding.pull_request,
                        "current_head_sha": binding.current_head_sha,
                        "provider_head_sha": binding.provider_head_sha,
                    },
                )
                arguments.extend(
                    [
                        "--ready-remediation-provider-binding",
                        str(provider_binding),
                    ]
                )
            result = bootstrap_source_admission._run_isolated_python(
                arguments,
                cwd=repository_root,
                timeout=60,
                env=environment,
            )
            if result.returncode != 0:
                raise LifecycleOrchestrationError(
                    "current stable feedback could not be authenticated"
                )
            return fast_path.verify_reviewed_state_evidence(
                authority.loads_closed_json(output.read_bytes())
            )
    except (
        OSError,
        authority.LifecycleAuthorityError,
        bootstrap_source_admission.BootstrapSourceAdmissionError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise LifecycleOrchestrationError(
            "current stable feedback could not be authenticated"
        ) from exc


def _closed_mapping(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise LifecycleOrchestrationError(f"{label} contains unknown or missing fields")
    return copy.deepcopy(dict(value))


def _closed_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) not in {
        REQUEST_FIELDS,
        CONTINUATION_REQUEST_FIELDS,
    }:
        raise LifecycleOrchestrationError(
            "lifecycle event contains unknown or missing fields"
        )
    item = copy.deepcopy(dict(value))
    item.setdefault("continuation_evidence", None)
    return item


def _successor_classification_signer(
    repository: str, value: Any
) -> late_disposition.SignerIdentity:
    if not isinstance(value, Mapping) or set(value) != {"kind", "identity"}:
        raise LifecycleOrchestrationError(
            "successor classification signer selector is malformed"
        )
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
        kind = value.get("kind")
        identity = _identity(value.get("identity"), "successor classification signer")
        if kind == "SSH_PRINCIPAL":
            if identity not in policy.transition_signer_identities:
                raise LifecycleOrchestrationError(
                    "successor classification signer is not authorized"
                )
            keys = policy.signers[identity].ssh_public_keys
            if len(keys) != 1:
                raise LifecycleOrchestrationError(
                    "successor classification signer key is ambiguous"
                )
            return late_disposition.SignerIdentity(
                "ssh", _ssh_public_key_fingerprint(keys[0])
            )
        if kind == "OPENPGP_FINGERPRINT" and any(
            signer in policy.transition_signer_identities
            and identity in policy.signers[signer].openpgp_fingerprints
            for signer in policy.signers
        ):
            return late_disposition.SignerIdentity("openpgp", identity.upper())
    except (KeyError, ValueError, authority.LifecycleAuthorityError) as exc:
        raise LifecycleOrchestrationError(
            "successor classification signer is unavailable"
        ) from exc
    raise LifecycleOrchestrationError(
        "successor classification signer is not authorized"
    )


def _authenticate_successor_safety_evidence(
    value: Any,
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_state_digest: str,
    resulting_head_sha: str,
    resulting_state_digest: str,
    reanchored_classified_review: bool = False,
    collision_provider_growth: bool = False,
    predecessor_correction_authority: (
        VerifiedRejectedContinuationReanchor | None
    ) = None,
) -> Any:
    return _authenticate_successor_safety_evidence_with_policy(
        value,
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        predecessor_state_digest=predecessor_state_digest,
        resulting_head_sha=resulting_head_sha,
        resulting_state_digest=resulting_state_digest,
        rejected_candidate=False,
        reanchored_classified_review=reanchored_classified_review,
        collision_provider_growth=collision_provider_growth,
        predecessor_correction_authority=predecessor_correction_authority,
    )


def _authenticate_rejected_successor_safety_evidence(
    value: Any,
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_state_digest: str,
    resulting_head_sha: str,
    resulting_state_digest: str,
) -> Any:
    return _authenticate_successor_safety_evidence_with_policy(
        value,
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        predecessor_state_digest=predecessor_state_digest,
        resulting_head_sha=resulting_head_sha,
        resulting_state_digest=resulting_state_digest,
        rejected_candidate=True,
        reanchored_classified_review=False,
        collision_provider_growth=False,
        predecessor_correction_authority=None,
    )


def _authenticate_successor_safety_evidence_with_policy(
    value: Any,
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_state_digest: str,
    resulting_head_sha: str,
    resulting_state_digest: str,
    rejected_candidate: bool,
    reanchored_classified_review: bool,
    collision_provider_growth: bool,
    predecessor_correction_authority: VerifiedRejectedContinuationReanchor | None,
) -> Any:
    if value is None:
        return None
    expected_keys = {
        "schema_version",
        "repository",
        "pull_request_number",
        "predecessor_state_digest",
        "resulting_head_sha",
        "resulting_state_digest",
        "provider_transport",
        "successor_findings",
        "classification_signer",
    }
    schema_version = (
        value.get("schema_version") if isinstance(value, Mapping) else None
    )
    provider_reaction_replacement = (
        rejected_candidate and schema_version == "1.2"
    )
    predecessor_provider_growth = (
        reanchored_classified_review and schema_version == "1.2"
    )
    collision_reaction_removal = (
        collision_provider_growth
        and schema_version == "1.3"
        and isinstance(value, Mapping)
        and "provider_completion_reaction_removal" in value
        and "provider_completion_reaction_replacement" not in value
    )
    collision_reaction_replacement = (
        collision_provider_growth
        and schema_version == "1.3"
        and isinstance(value, Mapping)
        and "provider_completion_reaction_replacement" in value
        and "provider_completion_reaction_removal" not in value
    )
    provider_reaction_replacement = (
        provider_reaction_replacement or collision_reaction_replacement
    )
    if provider_reaction_replacement:
        expected_keys.add("provider_completion_reaction_replacement")
    if predecessor_provider_growth:
        expected_keys.add("predecessor_provider_feedback")
    if predecessor_provider_growth or collision_reaction_removal:
        expected_keys.add("provider_completion_reaction_removal")
    expected_schema_version = (
        "1.3"
        if collision_provider_growth
        else "1.2"
        if provider_reaction_replacement
        else "1.2"
        if predecessor_provider_growth
        else "1.1"
        if rejected_candidate or reanchored_classified_review
        else "1.0"
    )
    if (
        not isinstance(value, Mapping)
        or set(value) != expected_keys
        or schema_version != expected_schema_version
        or (
            collision_provider_growth
            and collision_reaction_removal == collision_reaction_replacement
        )
    ):
        raise LifecycleOrchestrationError(
            "successor safety evidence contains unknown or missing fields"
        )
    if predecessor_provider_growth:
        if not isinstance(
            predecessor_correction_authority,
            VerifiedRejectedContinuationReanchor,
        ):
            raise LifecycleOrchestrationError(
                "predecessor provider correction authority is unavailable"
            )
        predecessor_feedback = value.get("predecessor_provider_feedback")
        expected_correction_authority = {
            "reanchor_evidence_digest": (
                predecessor_correction_authority.evidence_digest
            ),
            "material_finding_ids": list(
                predecessor_correction_authority.material_finding_ids
            ),
            "finding_source_digest": (
                predecessor_correction_authority.finding_source_digest
            ),
        }
        if (
            not isinstance(predecessor_feedback, Mapping)
            or predecessor_feedback.get("correction_authority")
            != expected_correction_authority
        ):
            raise LifecycleOrchestrationError(
                "predecessor provider feedback differs from re-anchor authority"
            )
    signer = _successor_classification_signer(
        repository, value.get("classification_signer")
    )
    raw_findings = value.get("successor_findings")
    if not isinstance(raw_findings, list):
        raise LifecycleOrchestrationError("successor finding evidence is malformed")
    findings: list[dict[str, Any]] = []
    for raw in raw_findings:
        if not isinstance(raw, Mapping) or set(raw) != {
            "sources",
            "classification_artifact",
            "classification_signature",
        }:
            raise LifecycleOrchestrationError(
                "successor finding evidence is malformed"
            )
        encoded_artifact = raw.get("classification_artifact")
        encoded_signature = raw.get("classification_signature")
        if (
            not isinstance(encoded_artifact, str)
            or len(encoded_artifact)
            > 4 * late_disposition.MAXIMUM_ARTIFACT_BYTES // 3 + 8
            or not isinstance(encoded_signature, str)
            or len(encoded_signature)
            > 4 * late_disposition.MAXIMUM_SIGNATURE_BYTES // 3 + 8
        ):
            raise LifecycleOrchestrationError(
                "successor finding classification is oversized"
            )
        try:
            artifact = base64.b64decode(
                encoded_artifact, validate=True
            )
            signature = base64.b64decode(
                encoded_signature, validate=True
            )
            with tempfile.TemporaryDirectory(
                prefix="secpal-successor-classification-"
            ) as directory:
                root = Path(directory)
                artifact_path = root / "classification.json"
                signature_path = root / "classification.sig"
                late_disposition._write_private_file(artifact_path, artifact)
                late_disposition._write_private_file(signature_path, signature)
                parser = (
                    late_disposition.parse_rejected_successor_classification_artifact
                    if rejected_candidate
                    else late_disposition.parse_successor_classification_artifact
                )
                verified = parser(
                    artifact_path,
                    signature_path,
                    expected_signer=signer,
                    repository=repository,
                    delivery_issue_number=delivery_issue,
                    pull_request_number=pull_request,
                    head_sha=resulting_head_sha,
                    predecessor_state_digest=predecessor_state_digest,
                    resulting_state_digest=resulting_state_digest,
                )
        except (
            KeyError,
            TypeError,
            ValueError,
            binascii.Error,
            OSError,
            late_disposition.LateDispositionError,
        ) as exc:
            raise LifecycleOrchestrationError(
                "successor finding classification is not authenticated"
            ) from exc
        signed_sources = [
            {"kind": kind, "node_id": node_id, "digest": digest}
            for kind, node_id, digest, _thread_id in verified.sources
        ]
        if list(raw["sources"]) != signed_sources:
            raise LifecycleOrchestrationError(
                "successor finding sources differ from signed classification"
            )
        thread = verified.thread
        findings.append(
            {
                "sources": signed_sources,
                "classification_evidence": fast_path._seal_successor_classification(
                    repository=verified.repository,
                    delivery_issue_number=verified.delivery_issue_number,
                    pull_request_number=verified.pull_request_number,
                    head_sha=verified.head_sha,
                    finding_id=verified.finding_id,
                    finding_evidence_digest=verified.finding_evidence_digest,
                    thread_id=thread.thread_id,
                    top_level_comment_node_id=thread.top_level_comment_node_id,
                    finding_body_digest=thread.finding_body_digest,
                    reply_count=thread.reply_count,
                    is_resolved=thread.is_resolved,
                    is_outdated=thread.is_outdated,
                    classification=thread.classification,
                    disposition=thread.disposition,
                    technically_blocking=thread.technically_blocking,
                    technical_blockers=verified.technical_blockers,
                    classification_evidence_digest=verified.evidence_digest,
                    source_bindings=verified.sources,
                ),
            }
        )
    prepared = copy.deepcopy(dict(value))
    prepared.pop("classification_signer")
    prepared["successor_findings"] = findings
    return prepared


def _verify_continuation_finding_authority(
    value: Any,
    *,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    predecessor_head_sha: str,
    resulting_head_sha: str,
    feedback_reader: Callable[[str, int], fast_path.StableFeedbackState],
    observed: Any = None,
    repository_root: Path | None = None,
    reanchor_verifier: Callable[..., VerifiedRejectedContinuationReanchor] | None = None,
    source_commit_verifier: Callable[..., fast_path.AuthenticatedIntegrationCommit] | None = None,
) -> VerifiedContinuationFindingAuthority:
    """Derive a finite material finding set from maintained feedback evidence."""

    if (
        not isinstance(value, Mapping)
        or set(value)
        not in {
            CONTINUATION_EVIDENCE_FIELDS,
            CONTINUATION_SUCCESSOR_EVIDENCE_FIELDS,
            CONTINUATION_REANCHOR_EVIDENCE_FIELDS,
        }
    ):
        raise LifecycleOrchestrationError(
            "continuation finding evidence contains unknown or missing fields"
        )
    item = copy.deepcopy(dict(value))
    try:
        reviewed = fast_path.verify_reviewed_state_evidence(
            item["reviewed_state_evidence"]
        )
        eligibility = fast_path.normalize_resolution_eligibility_evidence(
            item["eligibility_evidence"],
            repository=repository,
            reviewed_state=reviewed,
        )
        reanchor = None
        continuation_tree_sha = None
        if "reanchor_evidence" in item:
            if reanchor_verifier is None or source_commit_verifier is None:
                raise LifecycleOrchestrationError(
                    "rejected Continuation re-anchor verifier is unavailable"
                )
            reanchor = reanchor_verifier(
                item["reanchor_evidence"],
                observed=observed,
                repository_root=repository_root,
            )
            if not isinstance(reanchor, VerifiedRejectedContinuationReanchor):
                raise LifecycleOrchestrationError(
                    "rejected Continuation re-anchor authority is invalid"
                )
            if (
                reanchor.replacement_pull_request != pull_request
                or reanchor.replacement_state_digest != reviewed.state_digest
                or eligibility.get("eligible_threads") != []
            ):
                raise LifecycleOrchestrationError(
                    "replacement PR feedback differs from re-anchor authority"
                )
            source = source_commit_verifier(
                repository_root,
                repository,
                predecessor_head_sha,
                resulting_head_sha,
                item.get("expected_signer"),
            )
            continuation_tree_sha = _oid(
                source.tree_sha, "re-anchored Continuation tree"
            )
            if (
                resulting_head_sha == reanchor.rejected_candidate_head_sha
                or continuation_tree_sha == reanchor.rejected_candidate_tree_sha
            ):
                raise LifecycleOrchestrationError(
                    "corrected source reuses the rejected Continuation candidate"
                )
            finding_ids = list(reanchor.material_finding_ids)
            thread_ids = []
        else:
            finding_ids, thread_ids = fast_path.continuation_material_finding_projection(
                reviewed, eligibility
            )
        current = feedback_reader(repository, pull_request)
        predecessor_provider_growth_digest = None
        raw_successor_safety = item.get("successor_safety_evidence")
        successor_safety = _authenticate_successor_safety_evidence(
            raw_successor_safety,
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            predecessor_state_digest=reviewed.state_digest,
            resulting_head_sha=resulting_head_sha,
            resulting_state_digest=current.state_digest,
            reanchored_classified_review=(
                reanchor is not None
                and isinstance(raw_successor_safety, Mapping)
                and raw_successor_safety.get("schema_version") in {"1.1", "1.2"}
            ),
            predecessor_correction_authority=reanchor,
        )
        if reanchor is not None:
            predecessor_provider_growth_digest = (
                fast_path.verify_reanchored_stable_feedback_successor(
                    reviewed,
                    current,
                    resulting_head_sha=resulting_head_sha,
                    successor_safety_evidence=successor_safety,
                    predecessor_correction_authority=(
                        fast_path._seal_predecessor_correction_authority(
                            reanchor_evidence_digest=reanchor.evidence_digest,
                            material_finding_ids=reanchor.material_finding_ids,
                            finding_source_digest=reanchor.finding_source_digest,
                        )
                        if isinstance(raw_successor_safety, Mapping)
                        and raw_successor_safety.get("schema_version") == "1.2"
                        else None
                    ),
                )
            )
        else:
            fast_path.verify_stable_feedback_successor(
                reviewed,
                current,
                resulting_head_sha=resulting_head_sha,
                authorized_thread_ids=thread_ids,
                successor_safety_evidence=successor_safety,
            )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "continuation finding evidence is invalid or stale"
        ) from exc
    if (
        reviewed.repository != repository
        or reviewed.pull_request_number != pull_request
        or reviewed.head_sha != predecessor_head_sha
        or reviewed.pr_state != "OPEN"
    ):
        raise LifecycleOrchestrationError(
            "continuation feedback differs from the CURRENT Ready head"
        )
    return VerifiedContinuationFindingAuthority(
        reviewed_state_digest=reviewed.state_digest,
        reviewed_feedback_digest=reviewed.feedback_digest,
        eligibility_evidence_digest=fast_path.digest_json(eligibility),
        finding_ids=tuple(finding_ids),
        thread_ids=tuple(thread_ids),
        reanchor=reanchor,
        continuation_tree_sha=continuation_tree_sha,
        corrected_successor_state_digest=(
            current.state_digest if reanchor is not None else None
        ),
        predecessor_provider_growth_digest=predecessor_provider_growth_digest,
    )


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise LifecycleOrchestrationError(f"{label} must be a positive integer")
    return value


def _identity(value: Any, label: str) -> str:
    try:
        return authority._require_identity(value, label)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def _authenticate_diagnostic_recovery_source() -> str:
    """Expose only the closed accepted-main diagnostic authentication boundary."""

    return exceptional_recovery.authenticate_maintained_code()


def _verify_diagnostic_recovery_admission(
    value: Any, observed: Any, repository_root: Path
) -> dict[str, Any]:
    """Expose only the closed diagnostic admission verifier to the binder."""

    return exceptional_recovery.verify_admission(
        value, observed, repository_root
    )


def _oid(value: Any, label: str) -> str:
    try:
        return authority._require_oid(value, label)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def _create_user_authorization(
    *,
    authorization_id: str,
    repository: str,
    delivery_issue: int,
    lifecycle: authority.VerifiedLifecycleAuthority,
    publication_oid: str,
    publication_digest: str,
    operation: str,
    reason: str,
    scope: Mapping[str, Any],
    signer_identity: str,
    signer: authority.Signer,
    allow_finding_authority_digest: bool,
) -> bytes:
    """Create signed authority for one exact CURRENT orchestration decision."""

    if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
        raise LifecycleOrchestrationError("user authorization reason is invalid")
    if (
        isinstance(scope, Mapping)
        and "finding_authority_digest" in scope
        and not allow_finding_authority_digest
    ):
        raise LifecycleOrchestrationError(
            "ordinary Ready finding authority requires its maintained issuer"
        )
    try:
        fields = {
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "kind": AUTHORIZATION_KIND,
            "domain": AUTHORIZATION_DOMAIN,
            "authorization_id": _identity(
                authorization_id, "authorization identity"
            ),
            "repository": authority._require_repository(repository),
            "delivery_issue": _positive_int(delivery_issue, "delivery issue"),
            "lifecycle_id": _identity(lifecycle.lifecycle_id, "lifecycle identity"),
            "publication_oid": _oid(publication_oid, "publication object"),
            "publication_digest": authority._require_digest(
                publication_digest, "publication digest"
            ),
            "authority_digest": authority._require_digest(
                lifecycle.authority_digest, "authority digest"
            ),
            "pull_request": _positive_int(lifecycle.pull_request, "pull request"),
            "head_sha": _oid(lifecycle.head_sha, "head"),
            "operation": _identity(operation, "authorized operation"),
            "reason": reason,
            "scope": copy.deepcopy(dict(scope)),
            "bounded_uses": 1,
            "signer_identity": _identity(
                signer_identity, "authorization signer"
            ),
        }
        signature = authority._normalize_signature(
            signer(authority.canonical_json_bytes(fields), AUTHORIZATION_DOMAIN),
            fields["signer_identity"],
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    signed = {**fields, "signature": signature}
    artifact = {**signed, "authorization_digest": authority.digest_json(signed)}
    return authority.canonical_json_bytes(artifact)


def create_user_authorization(
    *,
    authorization_id: str,
    repository: str,
    delivery_issue: int,
    lifecycle: authority.VerifiedLifecycleAuthority,
    publication_oid: str,
    publication_digest: str,
    operation: str,
    reason: str,
    scope: Mapping[str, Any],
    signer_identity: str,
    signer: authority.Signer,
) -> bytes:
    """Create ordinary signed authority without verifier-owned growth scope."""

    return _create_user_authorization(
        authorization_id=authorization_id,
        repository=repository,
        delivery_issue=delivery_issue,
        lifecycle=lifecycle,
        publication_oid=publication_oid,
        publication_digest=publication_digest,
        operation=operation,
        reason=reason,
        scope=scope,
        signer_identity=signer_identity,
        signer=signer,
        allow_finding_authority_digest=False,
    )


def _verify_signed_user_authorization(
    value: Any,
    repository: str,
) -> dict[str, Any]:
    """Verify signed bytes without selecting CURRENT or historical authority."""

    if not isinstance(value, (bytes, str)):
        raise LifecycleOrchestrationError(
            "user authorization requires canonical signed evidence"
        )
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    try:
        parsed = authority.loads_closed_json(raw)
        item = _closed_mapping(parsed, AUTHORIZATION_FIELDS, "user authorization")
        if authority.canonical_json_bytes(item) != raw:
            raise LifecycleOrchestrationError("user authorization is not canonical")
        if (
            item["schema_version"] != AUTHORIZATION_SCHEMA_VERSION
            or item["kind"] != AUTHORIZATION_KIND
            or item["domain"] != AUTHORIZATION_DOMAIN
        ):
            raise LifecycleOrchestrationError("user authorization semantics are unknown")
        signer_identity = _identity(item["signer_identity"], "authorization signer")
        repository = authority._require_repository(repository)
        if item["repository"] != repository:
            raise LifecycleOrchestrationError(
                "user authorization repository differs from expected authority"
            )
        policy = authority._load_lifecycle_trust_policy(repository)
        signed = {
            key: copy.deepcopy(entry)
            for key, entry in item.items()
            if key != "authorization_digest"
        }
        if authority._require_digest(
            item["authorization_digest"], "authorization digest"
        ) != authority.digest_json(signed):
            raise LifecycleOrchestrationError("user authorization digest mismatch")
        unsigned = {
            key: copy.deepcopy(entry)
            for key, entry in signed.items()
            if key != "signature"
        }
        authority._verify_signature(
            authority.canonical_json_bytes(unsigned),
            item["signature"],
            signer_identity,
            AUTHORIZATION_DOMAIN,
            policy.transition_signer_identities,
            authority._policy_signature_verifier(policy),
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError("user authorization is invalid") from exc
    return item


def _verify_user_authorization(
    value: Any,
    observed: Any,
    lifecycle: authority.VerifiedLifecycleAuthority,
) -> dict[str, Any]:
    item = _verify_signed_user_authorization(value, lifecycle.repository)
    if (
        item["repository"] != lifecycle.repository
        or item["delivery_issue"] != lifecycle.delivery_issue
        or item["lifecycle_id"] != lifecycle.lifecycle_id
        or item["publication_oid"] != observed.publication_oid
        or item["publication_digest"] != observed.publication_digest
        or item["authority_digest"] != lifecycle.authority_digest
        or item["pull_request"] != lifecycle.pull_request
        or item["head_sha"] != lifecycle.head_sha
    ):
        raise LifecycleOrchestrationError(
            "user authorization differs from CURRENT lifecycle publication"
        )
    return item


def _authorization(
    value: Any,
    *,
    event_id: str,
    operation: str,
    expected_scope: Mapping[str, Any],
    observed: Any,
    lifecycle: authority.VerifiedLifecycleAuthority,
    verifier: AuthorizationVerifier,
    verified_item: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = (
        verifier(value, observed, lifecycle)
        if verified_item is None
        else copy.deepcopy(dict(verified_item))
    )
    reason = item.get("reason")
    if (
        item.get("operation") != operation
        or item.get("bounded_uses") != 1
        or isinstance(item.get("bounded_uses"), bool)
        or not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 512
        or item.get("scope") != dict(expected_scope)
    ):
        raise LifecycleOrchestrationError(
            f"{operation} requires one exact, reasoned, bounded user authorization"
        )
    _identity(item.get("authorization_id"), "authorization identity")
    try:
        digest = authority._require_digest(
            item.get("authorization_digest"), "authorization digest"
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    if event_id != f"authorization:{digest}":
        raise LifecycleOrchestrationError(
            "event identity is not bound to the signed user authorization"
        )
    return item


def _immutable_commit_tree(
    repository_root: Path,
    repository: str,
    head_sha: str,
) -> str:
    """Derive one tree from an exact commit in the authenticated repository."""

    if not isinstance(repository_root, Path):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository root is unavailable"
        )
    try:
        root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository root is unavailable"
        ) from exc
    if not root.is_dir():
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository root is unavailable"
        )
    head_sha = _oid(head_sha, "Exceptional Recovery commit")
    origin = publication._run_git(root, ["remote", "get-url", "origin"])
    if origin.returncode != 0:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository identity is unavailable"
        )
    try:
        origin_text = origin.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository identity is malformed"
        ) from exc
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        origin_text,
    )
    if match is None or match.group(1) != repository:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery repository identity changed"
        )
    object_type = publication._run_git(root, ["cat-file", "-t", head_sha])
    if object_type.returncode != 0 or object_type.stdout != b"commit\n":
        raise LifecycleOrchestrationError(
            "Exceptional Recovery commit object is unavailable"
        )
    tree = publication._run_git(root, ["rev-parse", f"{head_sha}^{{tree}}"])
    if tree.returncode != 0:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery commit tree is unavailable"
        )
    try:
        return _oid(tree.stdout.decode("ascii").strip(), "Exceptional Recovery tree")
    except (UnicodeDecodeError, LifecycleOrchestrationError) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery commit tree is malformed"
        ) from exc


def _immutable_commit_receipt(
    repository_root: Path,
    repository: str,
    head_sha: str,
) -> str:
    """Read exactly one validation-receipt trailer from an authenticated commit."""

    _immutable_commit_tree(repository_root, repository, head_sha)
    result = publication._run_git(
        repository_root.resolve(strict=True),
        [
            "show",
            "-s",
            "--format=%(trailers:key=SecPal-Validation-Receipt,valueonly,separator=%x00)",
            head_sha,
        ],
    )
    if result.returncode != 0:
        raise LifecycleOrchestrationError(
            "rejected Continuation validation receipt is unavailable"
        )
    try:
        values = [
            item.strip()
            for item in result.stdout.decode("utf-8").rstrip("\n").split("\x00")
            if item.strip()
        ]
    except UnicodeDecodeError as exc:
        raise LifecycleOrchestrationError(
            "rejected Continuation validation receipt is malformed"
        ) from exc
    if len(values) != 1:
        raise LifecycleOrchestrationError(
            "rejected Continuation must bind exactly one validation receipt"
        )
    try:
        return authority._require_digest(values[0], "rejected validation receipt")
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def _validation_registry_binding(repository: str) -> dict[str, Any]:
    """Select validation policy only from the maintained accepted-main registry."""

    path = (
        Path(__file__).resolve().parents[2]
        / ".agents/skills/secpal-pr-review/references/repositories.json"
    )
    try:
        registry = authority.loads_closed_json(path.read_bytes())
        entries = registry.get("repositories") if isinstance(registry, dict) else None
        matches = [
            item
            for item in entries
            if isinstance(item, dict) and item.get("repository") == repository
        ] if isinstance(entries, list) else []
        if len(matches) != 1:
            raise LifecycleOrchestrationError(
                "maintained validation registry selection is ambiguous"
            )
        return fast_path.validation_registry_projection(matches[0])
    except (
        OSError,
        authority.LifecycleAuthorityError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise LifecycleOrchestrationError(
            "maintained validation registry is unavailable"
        ) from exc


def _observe_accepted_main_comparison(
    repository: str,
    ancestor_sha: str,
    descendant_sha: str,
) -> AcceptedMainComparisonFacts:
    """Normalize one bounded GitHub Compare response without admitting lineage."""

    try:
        comparison_result = bootstrap_source_admission._run_bootstrap_gh(
            [
                "api",
                "--hostname",
                "github.com",
                f"repos/{repository}/compare/{ancestor_sha}...{descendant_sha}",
                "--jq",
                (
                    '{"status":.status,"behind_by":.behind_by,'
                    '"merge_base_sha":.merge_base_commit.sha}'
                ),
            ]
        )
        if comparison_result.returncode != 0:
            raise LifecycleOrchestrationError(
                "accepted-main comparison observation failed"
            )
        comparison = authority.loads_closed_json(comparison_result.stdout)
        if (
            not isinstance(comparison, Mapping)
            or set(comparison)
            != {"status", "behind_by", "merge_base_sha"}
            or comparison.get("status")
            not in {"ahead", "behind", "diverged", "identical"}
            or not isinstance(comparison.get("behind_by"), int)
            or isinstance(comparison.get("behind_by"), bool)
            or comparison["behind_by"] < 0
        ):
            raise LifecycleOrchestrationError(
                "accepted-main comparison observation is malformed"
            )
        merge_base_sha = authority._require_oid(
            comparison.get("merge_base_sha"),
            "accepted-main comparison merge base",
        )
        return AcceptedMainComparisonFacts(
            status=comparison["status"],
            behind_by=comparison["behind_by"],
            merge_base_sha=merge_base_sha,
        )
    except (
        OSError,
        TypeError,
        authority.LifecycleAuthorityError,
        bootstrap_source_admission.BootstrapSourceAdmissionError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "accepted-main lineage is unavailable"
        ) from exc


def _require_accepted_main_ancestor(
    ancestor_sha: str,
    descendant_sha: str,
    comparison: AcceptedMainComparisonFacts,
) -> None:
    """Purely admit one observed comparison as accepted-main ancestry."""

    try:
        ancestor_sha = authority._require_oid(
            ancestor_sha, "accepted-main ancestor"
        )
        descendant_sha = authority._require_oid(
            descendant_sha, "accepted-main descendant"
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    if (
        not isinstance(comparison, AcceptedMainComparisonFacts)
        or comparison.status not in {"ahead", "identical"}
        or comparison.behind_by != 0
        or comparison.merge_base_sha != ancestor_sha
        or (comparison.status == "identical") != (ancestor_sha == descendant_sha)
    ):
        raise LifecycleOrchestrationError(
            "re-anchor base advancement is not accepted-main lineage"
        )


def _authenticate_accepted_main_ancestor(
    repository: str,
    ancestor_sha: str,
    descendant_sha: str,
) -> None:
    """Compose bounded Compare observation with pure lineage admission."""

    comparison = _observe_accepted_main_comparison(
        repository,
        ancestor_sha,
        descendant_sha,
    )
    _require_accepted_main_ancestor(
        ancestor_sha,
        descendant_sha,
        comparison,
    )


def _historical_validation_registry_authority(
    repository_root: Path,
    repository: str,
    head_sha: str,
) -> tuple[dict[str, Any], bootstrap_source_admission.ProtectedMainFacts]:
    """Authenticate an immutable registry base and the current protected main."""

    try:
        protected = bootstrap_source_admission._normalize_protected_main(
            bootstrap_source_admission._observe_protected_main()
        )
        if protected.repository != repository:
            raise LifecycleOrchestrationError(
                "rejected-candidate validation repository changed"
            )
        _authenticate_accepted_main_ancestor(
            repository,
            head_sha,
            protected.head_sha,
        )
        actions = bootstrap_source_admission._load_actions_helper()
        binding = actions._prior_delivery_registry_binding(
            repository_root,
            head_sha,
            repository,
        )
        if binding.get("default_branch") != protected.default_branch:
            raise LifecycleOrchestrationError(
                "rejected-candidate validation default branch changed"
            )
        return binding, protected
    except (
        AttributeError,
        OSError,
        TypeError,
        authority.LifecycleAuthorityError,
        bootstrap_source_admission.BootstrapSourceAdmissionError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise LifecycleOrchestrationError(
            "immutable rejected-candidate validation registry is unavailable"
        ) from exc


def _historical_validation_registry_binding(
    repository_root: Path,
    repository: str,
    head_sha: str,
) -> dict[str, Any]:
    """Preserve the existing registry-only accepted-main boundary."""

    binding, _protected = _historical_validation_registry_authority(
        repository_root,
        repository,
        head_sha,
    )
    return binding


def verify_rejected_continuation_reanchor(
    value: Any,
    *,
    observed: Any,
    repository_root: Path | None,
    historical_reader: Callable[
        [str, int, str], publication.VerifiedLifecyclePublicationTransition
    ] = publication._verify_historical_lifecycle_transition,
) -> VerifiedRejectedContinuationReanchor:
    """Authenticate one rejected candidate as diagnostic-only correction input."""

    item = _closed_mapping(
        value,
        REJECTED_CONTINUATION_REANCHOR_FIELDS,
        "rejected Continuation re-anchor evidence",
    )
    if (
        item.get("schema_version")
        != REJECTED_CONTINUATION_REANCHOR_SCHEMA_VERSION
        or item.get("kind") != REJECTED_CONTINUATION_REANCHOR_KIND
    ):
        raise LifecycleOrchestrationError(
            "rejected Continuation re-anchor evidence kind is unsupported"
        )
    try:
        repository = authority._require_repository(item.get("repository"))
        delivery_issue = _positive_int(
            item.get("delivery_issue_number"), "re-anchor delivery issue"
        )
        original_pr = _positive_int(
            item.get("original_pull_request_number"), "original pull request"
        )
        replacement_pr = _positive_int(
            item.get("replacement_pull_request_number"), "replacement pull request"
        )
        current_publication_oid = _oid(
            item.get("current_publication_oid"), "CURRENT publication"
        )
        current_publication_digest = authority._require_digest(
            item.get("current_publication_digest"), "CURRENT publication"
        )
        current_authority_digest = authority._require_digest(
            item.get("current_authority_digest"), "CURRENT authority"
        )
        current_head = _oid(item.get("current_head_sha"), "CURRENT head")
        current_tree = _oid(item.get("current_tree_sha"), "CURRENT tree")
        rebound_predecessor_oid = _oid(
            item.get("rebound_predecessor_publication_oid"),
            "PR_REBOUND predecessor publication",
        )
        rebound_event_digest = authority._require_digest(
            item.get("rebound_event_digest"), "PR_REBOUND event"
        )
        rejected_head = _oid(
            item.get("rejected_candidate_head_sha"), "rejected candidate head"
        )
        rejected_tree = _oid(
            item.get("rejected_candidate_tree_sha"), "rejected candidate tree"
        )
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    if original_pr == replacement_pr or rejected_head == current_head:
        raise LifecycleOrchestrationError(
            "rejected Continuation topology is not a replacement sibling"
        )
    lifecycle = getattr(observed, "lifecycle", None)
    if (
        not isinstance(observed, publication.VerifiedLifecyclePublication)
        or not isinstance(lifecycle, authority.VerifiedLifecycleAuthority)
        or observed.publication_oid != current_publication_oid
        or observed.publication_digest != current_publication_digest
        or observed.predecessor_publication_oid != rebound_predecessor_oid
        or lifecycle.repository != repository
        or lifecycle.delivery_issue != delivery_issue
        or lifecycle.lifecycle_id != item.get("lifecycle_id")
        or lifecycle.pull_request != replacement_pr
        or lifecycle.head_sha != current_head
        or lifecycle.authority_digest != current_authority_digest
    ):
        raise LifecycleOrchestrationError(
            "rejected Continuation re-anchor differs from CURRENT authority"
        )
    try:
        state = authority._validate_state(copy.deepcopy(lifecycle.state))
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "rejected Continuation CURRENT state is invalid"
        ) from exc
    if (
        state["unrestricted_review_count"] != authority.MAX_UNRESTRICTED_REVIEWS
        or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
        or state["cycle_3_absent"] is not True
        or state["draft"] is not False
        or state["ready"] is not True
        or state["exceptional_recovery_count"]
        != authority.MAX_EXCEPTIONAL_RECOVERIES
        or state["exceptional_continuation_count"] != 0
        or state["exceptional_continuation_history"] != []
    ):
        raise LifecycleOrchestrationError(
            "rejected Continuation requires the closed unconsumed CURRENT state"
        )
    try:
        rebound = historical_reader(
            repository, delivery_issue, rebound_predecessor_oid
        )
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "authenticated PR_REBOUND is unavailable"
        ) from exc
    if (
        rebound.transition_kind != "PR_REBOUND"
        or rebound.event_digest != rebound_event_digest
        or rebound.predecessor.publication_oid != rebound_predecessor_oid
        or rebound.successor.publication_oid != observed.publication_oid
        or rebound.successor.publication_digest != observed.publication_digest
        or rebound.predecessor.lifecycle.repository != repository
        or rebound.predecessor.lifecycle.delivery_issue != delivery_issue
        or rebound.predecessor.lifecycle.lifecycle_id != lifecycle.lifecycle_id
        or rebound.predecessor.lifecycle.pull_request != original_pr
        or rebound.predecessor.lifecycle.head_sha != current_head
        or rebound.resulting_head_sha != current_head
        or rebound.successor.lifecycle != lifecycle
        or rebound.predecessor.lifecycle.state != lifecycle.state
    ):
        raise LifecycleOrchestrationError(
            "PR_REBOUND does not preserve the exact lifecycle and CURRENT head"
        )
    if repository_root is None:
        raise LifecycleOrchestrationError(
            "rejected Continuation repository root is unavailable"
        )
    if _immutable_commit_tree(repository_root, repository, current_head) != current_tree:
        raise LifecycleOrchestrationError("CURRENT tree changed")
    try:
        rejected_reviewed = fast_path.verify_reviewed_state_evidence(
            item.get("rejected_reviewed_state_evidence")
        )
        rejected_state = fast_path.verify_reviewed_state_evidence(
            item.get("rejected_candidate_state_evidence")
        )
        replacement_reviewed = fast_path.verify_reviewed_state_evidence(
            item.get("replacement_reviewed_state_evidence")
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "rejected or replacement Stable Feedback evidence is invalid"
        ) from exc
    if (
        rejected_reviewed.repository != repository
        or rejected_reviewed.pull_request_number != original_pr
        or rejected_reviewed.head_sha != current_head
        or rejected_reviewed.pr_state != "OPEN"
        or rejected_state.repository != repository
        or rejected_state.pull_request_number != original_pr
        or rejected_state.head_sha != rejected_head
        or rejected_state.pr_state != "OPEN"
        or replacement_reviewed.repository != repository
        or replacement_reviewed.pull_request_number != replacement_pr
        or replacement_reviewed.head_sha != current_head
        or replacement_reviewed.pr_state != "OPEN"
        or (
            rejected_reviewed.base_ref,
            rejected_reviewed.base_sha,
        )
        != (rejected_state.base_ref, rejected_state.base_sha)
    ):
        raise LifecycleOrchestrationError(
            "rejected or replacement Stable Feedback identity changed"
        )
    source = _authenticate_continuation_commit(
        repository_root,
        repository,
        current_head,
        rejected_head,
        item.get("rejected_candidate_expected_signer"),
    )
    if source.tree_sha != rejected_tree:
        raise LifecycleOrchestrationError("rejected candidate tree changed")
    receipt_digest = _immutable_commit_receipt(
        repository_root, repository, rejected_head
    )
    try:
        rejected_continuation = (
            fast_path.normalize_exceptional_continuation_evidence(
                item.get("rejected_continuation_evidence"),
                repository=repository,
                reviewed_state=rejected_reviewed,
                validated_tree_sha=rejected_tree,
                eligibility_evidence=item.get("rejected_eligibility_evidence"),
            )
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "rejected Continuation evidence is invalid or stale"
        ) from exc
    rejected_lifecycle_projection = {
        "unrestricted_reviews": state["unrestricted_review_count"],
        "remediation_cycles": state["remediation_cycle_count"],
        "cycle_3": not state["cycle_3_absent"],
        "draft": state["draft"],
        "ready": state["ready"],
        "ready_transition_count": state["ready_transition_count"],
        "ready_history": state["ready_history"],
        "exceptional_recovery_count": state["exceptional_recovery_count"],
        "exceptional_recovery_history": state["exceptional_recovery_history"],
        "exceptional_continuation_predecessor_count": 0,
        "exceptional_continuation_successor_count": 1,
    }
    if (
        rejected_continuation.get("delivery_issue_number") != delivery_issue
        or rejected_continuation.get("prior_ready_tree_sha") != current_tree
        or rejected_continuation.get("expected_signer")
        != {
            "kind": source.signer_kind,
            "identity": source.signer_identity,
        }
        or rejected_continuation.get("lifecycle")
        != rejected_lifecycle_projection
    ):
        raise LifecycleOrchestrationError(
            "rejected Continuation differs from authenticated lifecycle or source"
        )
    rejected_continuation_digest = fast_path.digest_json(rejected_continuation)
    registry, protected_main = _historical_validation_registry_authority(
        repository_root,
        repository,
        rejected_reviewed.base_sha,
    )
    historical_base = rejected_reviewed.base_sha
    replacement_base = replacement_reviewed.base_sha
    protected_main_advancement = replacement_base != historical_base
    if (
        rejected_reviewed.base_ref != registry["default_branch"]
        or replacement_reviewed.base_ref != registry["default_branch"]
        or protected_main.repository != repository
        or protected_main.default_branch != registry["default_branch"]
    ):
        raise LifecycleOrchestrationError(
            "rejected Continuation base is not the maintained default branch"
        )
    if protected_main_advancement:
        _authenticate_accepted_main_ancestor(
            repository,
            historical_base,
            replacement_base,
        )
        if replacement_base != protected_main.head_sha:
            _authenticate_accepted_main_ancestor(
                repository,
                replacement_base,
                protected_main.head_sha,
            )
    attestation = item.get("rejected_final_attestation")
    receipt = item.get("rejected_validation_receipt")
    try:
        expected_receipt = fast_path.create_validation_receipt(
            repository=repository,
            head_sha=current_head,
            validated_tree_sha=rejected_tree,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=rejected_reviewed,
            manual_gate_evidence=(
                receipt.get("manual_gate_evidence")
                if isinstance(receipt, Mapping)
                else None
            ),
            eligibility_evidence_digest=rejected_continuation[
                "eligibility_evidence_digest"
            ],
            exceptional_recovery_evidence_digest=(
                receipt.get("exceptional_recovery_evidence_digest")
                if isinstance(receipt, Mapping)
                else None
            ),
            exceptional_continuation_evidence_digest=(
                rejected_continuation_digest
            ),
        )
        if receipt != expected_receipt or receipt_digest != expected_receipt["receipt_digest"]:
            raise fast_path.SecurityBlocker(
                "rejected validation receipt is invalid or stale"
            )
        validation = fast_path.verify_validation_attestation(
            attestation,
            repository=repository,
            head_sha=rejected_head,
            registry=registry,
            command_set=registry["validation"],
            reviewed_state=rejected_reviewed,
            commit_parent_sha=current_head,
            commit_tree_sha=rejected_tree,
            commit_validation_receipt_digest=receipt_digest,
            delivery_issue_number=delivery_issue,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "rejected Continuation validation evidence is invalid"
        ) from exc
    prepared_safety = _authenticate_rejected_successor_safety_evidence(
        item.get("rejected_successor_safety_evidence"),
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=original_pr,
        predecessor_state_digest=rejected_reviewed.state_digest,
        resulting_head_sha=rejected_head,
        resulting_state_digest=rejected_state.state_digest,
    )
    try:
        material = fast_path.verify_rejected_stable_feedback_successor(
            rejected_reviewed,
            rejected_state,
            resulting_head_sha=rejected_head,
            rejected_successor_evidence=prepared_safety,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "rejected candidate material findings are invalid"
        ) from exc
    source_projection = [
        {
            "kind": kind,
            "node_id": node_id,
            "digest": digest,
            "thread_id": thread_id,
        }
        for kind, node_id, digest, thread_id in material.source_bindings
    ]
    projection = {
        "schema_version": REJECTED_CONTINUATION_REANCHOR_SCHEMA_VERSION,
        "kind": REJECTED_CONTINUATION_REANCHOR_KIND,
        "repository": repository,
        "delivery_issue_number": delivery_issue,
        "original_pull_request_number": original_pr,
        "replacement_pull_request_number": replacement_pr,
        "lifecycle_id": lifecycle.lifecycle_id,
        "current_publication_oid": observed.publication_oid,
        "current_publication_digest": observed.publication_digest,
        "current_authority_digest": lifecycle.authority_digest,
        "current_head_sha": current_head,
        "current_tree_sha": current_tree,
        "rebound_predecessor_publication_oid": rebound_predecessor_oid,
        "rebound_event_digest": rebound.event_digest,
        "rejected_candidate_head_sha": rejected_head,
        "rejected_candidate_tree_sha": rejected_tree,
        "rejected_commit_authentication_digest": source.authentication_digest,
        "rejected_continuation_evidence_digest": rejected_continuation_digest,
        "rejected_validation_receipt_digest": validation.validation_receipt_digest,
        "rejected_final_attestation_digest": validation.final_attestation_digest,
        "rejected_source_reviewed_state_digest": rejected_reviewed.state_digest,
        "rejected_state_digest": rejected_state.state_digest,
        "replacement_state_digest": replacement_reviewed.state_digest,
        "material_finding_ids": list(material.finding_ids),
        "material_thread_ids": list(material.thread_ids),
        "finding_sources": source_projection,
        "classification_evidence_digests": list(
            material.classification_evidence_digests
        ),
    }
    if protected_main_advancement:
        projection.update(
            {
                "historical_accepted_main_base_sha": historical_base,
                "current_protected_main_base_sha": replacement_base,
            }
        )
    if material.provider_reaction_replacement_digest is not None:
        projection["provider_reaction_replacement_digest"] = (
            material.provider_reaction_replacement_digest
        )
    return VerifiedRejectedContinuationReanchor(
        evidence_digest=fast_path.digest_json(projection),
        original_pull_request=original_pr,
        replacement_pull_request=replacement_pr,
        rejected_candidate_head_sha=rejected_head,
        rejected_candidate_tree_sha=rejected_tree,
        rejected_continuation_evidence_digest=rejected_continuation_digest,
        rejected_validation_receipt_digest=validation.validation_receipt_digest,
        rejected_final_attestation_digest=validation.final_attestation_digest,
        rejected_state_digest=rejected_state.state_digest,
        replacement_state_digest=replacement_reviewed.state_digest,
        material_finding_ids=material.finding_ids,
        material_thread_ids=material.thread_ids,
        finding_source_digest=fast_path.digest_json(source_projection),
        historical_accepted_main_base_sha=(
            historical_base if protected_main_advancement else None
        ),
        current_protected_main_base_sha=(
            replacement_base if protected_main_advancement else None
        ),
        provider_reaction_replacement_digest=(
            material.provider_reaction_replacement_digest
        ),
    )


def verify_exceptional_recovery_authority(
    recovery_evidence: Any,
    *,
    orchestration_authorization: bytes | str,
    reviewed_state_evidence: Any,
    eligibility_evidence: Any,
    repository_root: Path,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    resulting_head_sha: str,
) -> VerifiedExceptionalRecoveryAuthority:
    """Authenticate one Recovery projection through all accepted authorities.

    The signed orchestration authorization selects an exact historical
    predecessor publication.  Protected publication ancestry then proves the
    one signed lifecycle successor; no caller-provided lifecycle bundle or
    trust configuration is accepted.
    """

    try:
        repository = authority._require_repository(repository)
        delivery_issue = _positive_int(delivery_issue, "delivery issue")
        pull_request = _positive_int(pull_request, "pull request")
        resulting_head_sha = _oid(resulting_head_sha, "resulting head")
        authorization = _verify_signed_user_authorization(
            orchestration_authorization, repository
        )
        transition = publication._verify_historical_lifecycle_transition(
            repository,
            delivery_issue,
            authorization.get("publication_oid"),
        )
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery lifecycle authority is invalid"
        ) from exc

    predecessor = transition.predecessor.lifecycle
    successor = transition.successor.lifecycle
    if (
        authorization.get("delivery_issue") != delivery_issue
        or authorization.get("lifecycle_id") != predecessor.lifecycle_id
        or authorization.get("publication_oid")
        != transition.predecessor.publication_oid
        or authorization.get("publication_digest")
        != transition.predecessor.publication_digest
        or authorization.get("authority_digest") != predecessor.authority_digest
        or authorization.get("pull_request") != pull_request
        or authorization.get("pull_request") != predecessor.pull_request
        or authorization.get("head_sha") != predecessor.head_sha
        or transition.transition_kind != "EXCEPTIONAL_RECOVERY"
        or transition.pull_request != pull_request
        or transition.predecessor_authority_digest
        != predecessor.authority_digest
        or transition.predecessor_head_sha != predecessor.head_sha
        or transition.resulting_head_sha != resulting_head_sha
        or predecessor.head_sha == resulting_head_sha
        or transition.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.repository != repository
        or successor.delivery_issue != delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.pull_request != pull_request
        or successor.head_sha != resulting_head_sha
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery signed lifecycle identity changed"
        )

    if isinstance(recovery_evidence, dict) and recovery_evidence.get("schema_version") == "1.1":
        if reviewed_state_evidence is not None or eligibility_evidence is not None:
            raise LifecycleOrchestrationError("diagnostic Recovery grants no thread-resolution authority")
        try:
            exceptional_recovery.authenticate_maintained_code()
            recovery = exceptional_recovery.verify_admission(recovery_evidence, transition.predecessor, repository_root)
            if recovery["authorization_id"] != authorization["authorization_id"]:
                raise LifecycleOrchestrationError(
                    "diagnostic Recovery authorization identity changed"
                )
            exceptional_recovery.require_successor(repository_root, recovery, resulting_head_sha)
            _authorization(
                orchestration_authorization,
                event_id=transition.event_id,
                operation="EXCEPTIONAL_RECOVERY",
                expected_scope=exceptional_recovery.authorization_scope(
                    recovery, resulting_head_sha
                ),
                observed=transition.predecessor,
                lifecycle=predecessor,
                verifier=_verify_user_authorization,
                verified_item=authorization,
            )
            expected_state = authority.derive_state(predecessor.state, "EXCEPTIONAL_RECOVERY", transition.event_digest)
            if successor.state != expected_state or transition.event_signer_identity != authorization["signer_identity"]:
                raise LifecycleOrchestrationError("diagnostic Recovery lifecycle successor changed")
        except exceptional_recovery.DiagnosticRecoveryError as exc:
            raise LifecycleOrchestrationError(str(exc)) from exc
        return VerifiedExceptionalRecoveryAuthority(
            recovery_digest=fast_path.digest_json(recovery),
            authorization_id=authorization["authorization_id"],
            authorization_digest=authorization["authorization_digest"],
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=pull_request,
            lifecycle_id=predecessor.lifecycle_id,
            predecessor_publication_oid=transition.predecessor.publication_oid,
            predecessor_publication_digest=transition.predecessor.publication_digest,
            recovery_publication_oid=transition.successor.publication_oid,
            recovery_publication_digest=transition.successor.publication_digest,
            predecessor_authority_digest=predecessor.authority_digest,
            recovery_authority_digest=successor.authority_digest,
            prior_ready_head_sha=predecessor.head_sha,
            resulting_head_sha=resulting_head_sha,
            prior_ready_tree_sha=recovery["prior_ready_tree_sha"],
            recovery_tree_sha=recovery["recovery_tree_sha"],
            reviewed_state_digest=None,
            reviewed_feedback_digest=None,
            eligibility_evidence_digest=None,
            finding_ids=tuple(recovery["finding_ids"]),
            thread_ids=(),
        )

    try:
        reviewed = fast_path.verify_reviewed_state_evidence(
            reviewed_state_evidence
        )
        eligibility = fast_path.normalize_resolution_eligibility_evidence(
            eligibility_evidence,
            repository=repository,
            reviewed_state=reviewed,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery reviewed or eligibility evidence is invalid"
        ) from exc
    if reviewed.pull_request_number != pull_request:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery reviewed pull request changed"
        )

    eligible_threads = eligibility["eligible_threads"]
    thread_ids = sorted(item["thread_id"] for item in eligible_threads)
    flattened_findings = [
        finding_id
        for item in eligible_threads
        for finding_id in item["finding_ids"]
    ]
    if len(flattened_findings) != len(set(flattened_findings)):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery eligibility repeats a finding"
        )
    finding_ids = sorted(flattened_findings)
    eligibility_digest = fast_path.digest_json(eligibility)

    _authorization(
        orchestration_authorization,
        event_id=transition.event_id,
        operation="EXCEPTIONAL_RECOVERY",
        expected_scope={
            "pull_request": pull_request,
            "predecessor_head_sha": predecessor.head_sha,
            "resulting_head_sha": resulting_head_sha,
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "eligibility_evidence_digest": eligibility_digest,
            "finding_ids": finding_ids,
            "thread_ids": thread_ids,
        },
        observed=transition.predecessor,
        lifecycle=predecessor,
        verifier=_verify_user_authorization,
        verified_item=authorization,
    )

    try:
        prior_tree = _immutable_commit_tree(
            repository_root, repository, predecessor.head_sha
        )
        recovery_tree = _immutable_commit_tree(
            repository_root, repository, resulting_head_sha
        )
        recovery = fast_path.normalize_exceptional_recovery_evidence(
            recovery_evidence,
            repository=repository,
            reviewed_state=reviewed,
            validated_tree_sha=recovery_tree,
            eligibility_evidence_digest=eligibility_digest,
        )
    except (fast_path.SecurityBlocker, publication.LifecyclePublicationError) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery document is invalid or stale"
        ) from exc
    if (
        recovery["authorization_id"] != authorization.get("authorization_id")
        or recovery["delivery_issue_number"] != delivery_issue
        or recovery["pull_request_number"] != pull_request
        or recovery["prior_ready_head_sha"] != predecessor.head_sha
        or recovery["prior_ready_tree_sha"] != prior_tree
        or recovery["recovery_tree_sha"] != recovery_tree
        or recovery["finding_ids"] != finding_ids
        or recovery["thread_ids"] != thread_ids
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery projection differs from verified authority"
        )

    try:
        predecessor_state = authority._validate_state(
            copy.deepcopy(predecessor.state)
        )
        successor_state = authority._validate_state(copy.deepcopy(successor.state))
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery lifecycle state is invalid"
        ) from exc
    unchanged_fields = (
        "unrestricted_review_count",
        "remediation_cycle_count",
        "cycle_3_absent",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_continuation_count",
        "exceptional_continuation_history",
    )
    if (
        any(
            predecessor_state[field] != successor_state[field]
            for field in unchanged_fields
        )
        or predecessor_state["unrestricted_review_count"]
        != authority.MAX_UNRESTRICTED_REVIEWS
        or predecessor_state["remediation_cycle_count"]
        != authority.MAX_REMEDIATION_CYCLES
        or predecessor_state["cycle_3_absent"] is not True
        or predecessor_state["draft"] is not False
        or predecessor_state["ready"] is not True
        or predecessor_state["exceptional_recovery_count"] != 0
        or successor_state["exceptional_recovery_count"] != 1
        or successor_state["exceptional_recovery_history"]
        != [
            {
                "sequence": 1,
                "transition_kind": "EXCEPTIONAL_RECOVERY",
                "event_authorization_digest": transition.event_digest,
            }
        ]
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Recovery lifecycle projection is invalid"
        )
    lifecycle_projection = {
        "unrestricted_reviews": successor_state["unrestricted_review_count"],
        "remediation_cycles": successor_state["remediation_cycle_count"],
        "cycle_3": not successor_state["cycle_3_absent"],
        "draft": successor_state["draft"],
        "ready": successor_state["ready"],
        "ready_transition": transition.transition_kind == "DRAFT_TO_READY",
        "exceptional_recovery_count": successor_state[
            "exceptional_recovery_count"
        ],
    }
    if recovery["lifecycle"] != lifecycle_projection:
        raise LifecycleOrchestrationError(
            "Exceptional Recovery embedded lifecycle projection changed"
        )

    recovery_digest = fast_path.digest_json(recovery)
    return VerifiedExceptionalRecoveryAuthority(
        recovery_digest=recovery_digest,
        authorization_id=authorization["authorization_id"],
        authorization_digest=authorization["authorization_digest"],
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        lifecycle_id=predecessor.lifecycle_id,
        predecessor_publication_oid=transition.predecessor.publication_oid,
        predecessor_publication_digest=transition.predecessor.publication_digest,
        recovery_publication_oid=transition.successor.publication_oid,
        recovery_publication_digest=transition.successor.publication_digest,
        predecessor_authority_digest=predecessor.authority_digest,
        recovery_authority_digest=successor.authority_digest,
        prior_ready_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        prior_ready_tree_sha=prior_tree,
        recovery_tree_sha=recovery_tree,
        reviewed_state_digest=reviewed.state_digest,
        reviewed_feedback_digest=reviewed.feedback_digest,
        eligibility_evidence_digest=eligibility_digest,
        finding_ids=tuple(finding_ids),
        thread_ids=tuple(thread_ids),
    )


def _authenticate_continuation_commit(
    repository_root: Path,
    repository: str,
    predecessor_head_sha: str,
    resulting_head_sha: str,
    expected_signer: Any,
    *,
    authenticated_source: fast_path.AuthenticatedIntegrationCommit | None = None,
) -> fast_path.AuthenticatedIntegrationCommit:
    """Reuse the ordinary signed-commit verifier for the one-parent successor."""

    if (
        not isinstance(expected_signer, Mapping)
        or set(expected_signer) != {"kind", "identity"}
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation source signer is malformed"
        )
    try:
        policy = authority._load_lifecycle_trust_policy(repository)
        signer_kind = expected_signer.get("kind")
        signer_identity = _identity(
            expected_signer.get("identity"), "continuation source signer"
        )
        if signer_kind == "SSH_PRINCIPAL":
            authorized = signer_identity in policy.transition_signer_identities
        elif signer_kind == "OPENPGP_FINGERPRINT":
            authorized = any(
                identity in policy.transition_signer_identities
                and signer_identity in policy.signers[identity].openpgp_fingerprints
                for identity in policy.signers
            )
        else:
            authorized = False
        if not authorized:
            raise LifecycleOrchestrationError(
                "Exceptional Continuation source signer is not authorized"
            )
        signature_policy = {
            "require_github_verified": False,
            "require_local_verified": True,
            "accepted_formats": sorted(policy.accepted_formats),
        }
        if authenticated_source is None:
            verified = fast_path.authenticate_integration_commit(
                repository_root=repository_root,
                repository=repository,
                head_sha=resulting_head_sha,
                expected_signer=dict(expected_signer),
                signature_policy=signature_policy,
            )
        elif fast_path._authenticated_integration_commit_agrees(
            authenticated_source,
            repository=repository,
            head_sha=resulting_head_sha,
            expected_signer=dict(expected_signer),
            signature_policy=signature_policy,
        ):
            verified = authenticated_source
        else:
            raise fast_path.SecurityBlocker(
                "preauthenticated collision source identity changed"
            )
    except (
        authority.LifecycleAuthorityError,
        fast_path.RecoverableLocalError,
        fast_path.SecurityBlocker,
    ) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation signed source commit is invalid"
        ) from exc
    if signer_kind == "SSH_PRINCIPAL":
        try:
            trusted_fingerprints = {
                _ssh_public_key_fingerprint(key)
                for key in policy.signers[signer_identity].ssh_public_keys
            }
        except (KeyError, ValueError) as exc:
            raise LifecycleOrchestrationError(
                "Exceptional Continuation maintained SSH key is invalid"
            ) from exc
        if verified.signature_fingerprint not in trusted_fingerprints:
            raise LifecycleOrchestrationError(
                "Exceptional Continuation signature does not match the maintained SSH key"
            )
    if verified.parent_shas != (predecessor_head_sha,):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation requires one exact predecessor parent"
        )
    return verified


def _ssh_public_key_fingerprint(public_key: str) -> str:
    """Derive the OpenSSH SHA-256 fingerprint for one maintained public key."""

    parts = public_key.split()
    if len(parts) < 2:
        raise ValueError("SSH public key is malformed")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("SSH public key is malformed") from exc
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii")
    return "SHA256:" + digest.rstrip("=")


def verify_exceptional_continuation_authority(
    continuation_evidence: Any,
    *,
    orchestration_authorization: bytes | str,
    reviewed_state_evidence: Any,
    eligibility_evidence: Any,
    successor_safety_evidence: Any = None,
    reanchor_evidence: Any = None,
    repository_root: Path,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    resulting_head_sha: str,
) -> VerifiedExceptionalContinuationAuthority:
    """Authenticate one Continuation through publication, findings, and source."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = _positive_int(delivery_issue, "delivery issue")
        pull_request = _positive_int(pull_request, "pull request")
        resulting_head_sha = _oid(resulting_head_sha, "resulting head")
        authorization = _verify_signed_user_authorization(
            orchestration_authorization, repository
        )
        transition = publication._verify_historical_lifecycle_transition(
            repository,
            delivery_issue,
            authorization.get("publication_oid"),
        )
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation lifecycle authority is invalid"
        ) from exc

    predecessor = transition.predecessor.lifecycle
    successor = transition.successor.lifecycle
    if (
        authorization.get("delivery_issue") != delivery_issue
        or authorization.get("lifecycle_id") != predecessor.lifecycle_id
        or authorization.get("publication_oid")
        != transition.predecessor.publication_oid
        or authorization.get("publication_digest")
        != transition.predecessor.publication_digest
        or authorization.get("authority_digest") != predecessor.authority_digest
        or authorization.get("pull_request") != pull_request
        or predecessor.pull_request != pull_request
        or authorization.get("head_sha") != predecessor.head_sha
        or transition.transition_kind != "EXCEPTIONAL_CONTINUATION"
        or transition.pull_request != pull_request
        or transition.predecessor_authority_digest != predecessor.authority_digest
        or transition.predecessor_head_sha != predecessor.head_sha
        or transition.resulting_head_sha != resulting_head_sha
        or predecessor.head_sha == resulting_head_sha
        or transition.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.repository != repository
        or successor.delivery_issue != delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.pull_request != pull_request
        or successor.head_sha != resulting_head_sha
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation signed lifecycle identity changed"
        )

    reanchored = (
        isinstance(continuation_evidence, Mapping)
        and continuation_evidence.get("schema_version") == "1.1"
    )
    finding_evidence = {
        "reviewed_state_evidence": reviewed_state_evidence,
        "eligibility_evidence": eligibility_evidence,
        **(
            {"successor_safety_evidence": successor_safety_evidence}
            if successor_safety_evidence is not None
            else {}
        ),
    }
    if reanchored:
        finding_evidence.update(
            {
                "successor_safety_evidence": successor_safety_evidence,
                "reanchor_evidence": reanchor_evidence,
                "expected_signer": continuation_evidence.get("expected_signer"),
            }
        )
    findings = _verify_continuation_finding_authority(
        finding_evidence,
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        predecessor_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        feedback_reader=_capture_current_stable_feedback,
        observed=transition.predecessor,
        repository_root=repository_root,
        reanchor_verifier=verify_rejected_continuation_reanchor,
        source_commit_verifier=_authenticate_continuation_commit,
    )
    _authorization(
        orchestration_authorization,
        event_id=transition.event_id,
        operation="EXCEPTIONAL_CONTINUATION",
        expected_scope=_continuation_authorization_scope(
            findings,
            pull_request=pull_request,
            predecessor_head_sha=predecessor.head_sha,
            resulting_head_sha=resulting_head_sha,
        ),
        observed=transition.predecessor,
        lifecycle=predecessor,
        verifier=_verify_user_authorization,
        verified_item=authorization,
    )

    try:
        predecessor_state = authority._validate_state(
            copy.deepcopy(predecessor.state)
        )
        successor_state = authority._validate_state(copy.deepcopy(successor.state))
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation lifecycle state is invalid"
        ) from exc
    unchanged_fields = (
        "unrestricted_review_count",
        "remediation_cycle_count",
        "cycle_3_absent",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_recovery_count",
        "exceptional_recovery_history",
    )
    if (
        any(
            predecessor_state[field] != successor_state[field]
            for field in unchanged_fields
        )
        or predecessor_state["unrestricted_review_count"]
        != authority.MAX_UNRESTRICTED_REVIEWS
        or predecessor_state["remediation_cycle_count"]
        != authority.MAX_REMEDIATION_CYCLES
        or predecessor_state["cycle_3_absent"] is not True
        or predecessor_state["draft"] is not False
        or predecessor_state["ready"] is not True
        or predecessor_state["exceptional_recovery_count"]
        != authority.MAX_EXCEPTIONAL_RECOVERIES
        or len(predecessor_state["exceptional_recovery_history"])
        != authority.MAX_EXCEPTIONAL_RECOVERIES
        or predecessor_state["exceptional_continuation_count"] != 0
        or predecessor_state["exceptional_continuation_history"] != []
        or successor_state["exceptional_continuation_count"] != 1
        or successor_state["exceptional_continuation_history"]
        != [
            {
                "sequence": 1,
                "transition_kind": "EXCEPTIONAL_CONTINUATION",
                "event_authorization_digest": transition.event_digest,
            }
        ]
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation lifecycle projection is invalid"
        )

    try:
        reviewed = fast_path.verify_reviewed_state_evidence(reviewed_state_evidence)
        source = _authenticate_continuation_commit(
            repository_root,
            repository,
            predecessor.head_sha,
            resulting_head_sha,
            continuation_evidence.get("expected_signer")
            if isinstance(continuation_evidence, Mapping)
            else None,
        )
        prior_tree = _immutable_commit_tree(
            repository_root, repository, predecessor.head_sha
        )
        continuation = fast_path.normalize_exceptional_continuation_evidence(
            continuation_evidence,
            repository=repository,
            reviewed_state=reviewed,
            validated_tree_sha=source.tree_sha,
            eligibility_evidence=eligibility_evidence,
            reanchor_authority=findings.reanchor,
        )
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "Exceptional Continuation document is invalid or stale"
        ) from exc
    lifecycle_projection = {
        "unrestricted_reviews": predecessor_state["unrestricted_review_count"],
        "remediation_cycles": predecessor_state["remediation_cycle_count"],
        "cycle_3": not predecessor_state["cycle_3_absent"],
        "draft": predecessor_state["draft"],
        "ready": predecessor_state["ready"],
        "ready_transition_count": predecessor_state["ready_transition_count"],
        "ready_history": predecessor_state["ready_history"],
        "exceptional_recovery_count": predecessor_state[
            "exceptional_recovery_count"
        ],
        "exceptional_recovery_history": predecessor_state[
            "exceptional_recovery_history"
        ],
        "exceptional_continuation_predecessor_count": 0,
        "exceptional_continuation_successor_count": 1,
    }
    if (
        continuation["authorization_id"] != authorization.get("authorization_id")
        or continuation["delivery_issue_number"] != delivery_issue
        or continuation["pull_request_number"] != pull_request
        or continuation["prior_ready_head_sha"] != predecessor.head_sha
        or continuation["prior_ready_tree_sha"] != prior_tree
        or continuation["continuation_tree_sha"] != source.tree_sha
        or continuation["reviewed_state_digest"]
        != findings.reviewed_state_digest
        or continuation["reviewed_feedback_digest"]
        != findings.reviewed_feedback_digest
        or continuation["eligibility_evidence_digest"]
        != findings.eligibility_evidence_digest
        or continuation["finding_ids"] != list(findings.finding_ids)
        or continuation["thread_ids"] != list(findings.thread_ids)
        or (
            findings.reanchor is not None
            and continuation.get("reanchor", {}).get("evidence_digest")
            != findings.reanchor.evidence_digest
        )
        or continuation["lifecycle"] != lifecycle_projection
    ):
        raise LifecycleOrchestrationError(
            "Exceptional Continuation projection differs from verified authority"
        )
    return VerifiedExceptionalContinuationAuthority(
        continuation_digest=fast_path.digest_json(continuation),
        authorization_id=authorization["authorization_id"],
        authorization_digest=authorization["authorization_digest"],
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        lifecycle_id=predecessor.lifecycle_id,
        predecessor_publication_oid=transition.predecessor.publication_oid,
        predecessor_publication_digest=transition.predecessor.publication_digest,
        continuation_publication_oid=transition.successor.publication_oid,
        continuation_publication_digest=transition.successor.publication_digest,
        predecessor_authority_digest=predecessor.authority_digest,
        continuation_authority_digest=successor.authority_digest,
        prior_ready_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        prior_ready_tree_sha=prior_tree,
        continuation_tree_sha=source.tree_sha,
        reviewed_state_digest=findings.reviewed_state_digest,
        reviewed_feedback_digest=findings.reviewed_feedback_digest,
        eligibility_evidence_digest=findings.eligibility_evidence_digest,
        finding_ids=findings.finding_ids,
        thread_ids=findings.thread_ids,
        source_signer_kind=source.signer_kind,
        source_signer_identity=source.signer_identity,
        reanchor_evidence_digest=(
            findings.reanchor.evidence_digest
            if findings.reanchor is not None
            else None
        ),
        original_pull_request=(
            findings.reanchor.original_pull_request
            if findings.reanchor is not None
            else None
        ),
        rejected_candidate_head_sha=(
            findings.reanchor.rejected_candidate_head_sha
            if findings.reanchor is not None
            else None
        ),
        rejected_candidate_tree_sha=(
            findings.reanchor.rejected_candidate_tree_sha
            if findings.reanchor is not None
            else None
        ),
        rejected_continuation_evidence_digest=(
            findings.reanchor.rejected_continuation_evidence_digest
            if findings.reanchor is not None
            else None
        ),
        diagnostic_thread_ids=(
            findings.reanchor.material_thread_ids
            if findings.reanchor is not None
            else ()
        ),
        finding_source_digest=(
            findings.reanchor.finding_source_digest
            if findings.reanchor is not None
            else None
        ),
        provider_reaction_replacement_digest=(
            findings.reanchor.provider_reaction_replacement_digest
            if findings.reanchor is not None
            else None
        ),
        predecessor_provider_growth_digest=(
            findings.predecessor_provider_growth_digest
        ),
    )


def collision_validation_binding_for_historical_attestation(
    continuation_evidence: Any,
    *,
    orchestration_authorization: bytes | str,
    repository_root: Path,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    resulting_head_sha: str,
) -> tuple[dict[str, Any], str]:
    """Authenticate collision receipt policy before generic evidence loading."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = _positive_int(delivery_issue, "delivery issue")
        pull_request = _positive_int(pull_request, "pull request")
        resulting_head_sha = _oid(resulting_head_sha, "resulting head")
        authorization = _verify_signed_user_authorization(
            orchestration_authorization, repository
        )
        scope = authorization.get("scope")
        scope_mapping = scope if isinstance(scope, Mapping) else {}
        collision = scope_mapping.get("collision")
        expected_signer = (
            continuation_evidence.get("expected_signer")
            if isinstance(continuation_evidence, Mapping)
            else None
        )
        if (
            not isinstance(collision, dict)
            or authorization.get("delivery_issue") != delivery_issue
            or authorization.get("pull_request") != pull_request
            or authorization.get("operation") != "EXCEPTIONAL_CONTINUATION"
            or scope_mapping.get("trigger") != version_collision.TRIGGER
            or scope_mapping.get("predecessor_head_sha")
            != authorization.get("head_sha")
            or scope_mapping.get("resulting_head_sha") != resulting_head_sha
            or collision.get("predecessor_head")
            != authorization.get("head_sha")
            or collision.get("resulting_head") != resulting_head_sha
            or not isinstance(continuation_evidence, Mapping)
            or continuation_evidence.get("schema_version") != "1.1"
            or continuation_evidence.get("trigger")
            != version_collision.TRIGGER
        ):
            raise LifecycleOrchestrationError(
                "collision Continuation preload authority is invalid"
            )
        sealed, binding, _source, receipt_digest = (
            version_collision._historical_collision_validation_binding_for_commit(
                repository=repository,
                delivery_issue=delivery_issue,
                pull_request=pull_request,
                predecessor_head=authorization["head_sha"],
                resulting_head=resulting_head_sha,
                repository_root=repository_root,
                protected_main=collision.get("protected_main"),
                expected_signer=expected_signer,
                expected_collision_digest=continuation_evidence.get(
                    "collision_digest"
                ),
            )
        )
        authenticated_collision = sealed.to_dict()
        if (
            collision != authenticated_collision
            or continuation_evidence.get("collision_digest")
            != fast_path.digest_json(
                version_collision.validation_collision_projection(
                    authenticated_collision
                )
            )
        ):
            raise LifecycleOrchestrationError(
                "collision Continuation preload authority changed"
            )
        return copy.deepcopy(binding), receipt_digest
    except (
        KeyError,
        TypeError,
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
        version_collision.VersionCollisionError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "collision Continuation preload authority is invalid"
        ) from exc


def verify_collision_continuation_authority(
    continuation_evidence: Any,
    *,
    orchestration_authorization: bytes | str,
    reviewed_state_evidence: Any,
    eligibility_evidence: Any,
    validation_attestation: Any,
    repository_root: Path,
    repository: str,
    delivery_issue: int,
    pull_request: int,
    resulting_head_sha: str,
) -> VerifiedExceptionalContinuationAuthority:
    """Authenticate a published collision Continuation with zero thread authority."""

    try:
        repository = authority._require_repository(repository)
        delivery_issue = _positive_int(delivery_issue, "delivery issue")
        pull_request = _positive_int(pull_request, "pull request")
        resulting_head_sha = _oid(resulting_head_sha, "resulting head")
        authorization = _verify_signed_user_authorization(
            orchestration_authorization, repository
        )
        transition = publication._verify_historical_lifecycle_transition(
            repository,
            delivery_issue,
            authorization.get("publication_oid"),
        )
    except (
        authority.LifecycleAuthorityError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "collision Continuation lifecycle authority is invalid"
        ) from exc

    predecessor = transition.predecessor.lifecycle
    successor = transition.successor.lifecycle
    if (
        authorization.get("delivery_issue") != delivery_issue
        or authorization.get("lifecycle_id") != predecessor.lifecycle_id
        or authorization.get("publication_oid")
        != transition.predecessor.publication_oid
        or authorization.get("publication_digest")
        != transition.predecessor.publication_digest
        or authorization.get("authority_digest") != predecessor.authority_digest
        or authorization.get("pull_request") != pull_request
        or predecessor.pull_request != pull_request
        or authorization.get("head_sha") != predecessor.head_sha
        or transition.transition_kind != "EXCEPTIONAL_CONTINUATION"
        or transition.pull_request != pull_request
        or transition.predecessor_authority_digest != predecessor.authority_digest
        or transition.predecessor_head_sha != predecessor.head_sha
        or transition.resulting_head_sha != resulting_head_sha
        or predecessor.head_sha == resulting_head_sha
        or transition.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.repository != repository
        or successor.delivery_issue != delivery_issue
        or successor.lifecycle_id != predecessor.lifecycle_id
        or successor.initialization_evidence_digest
        != predecessor.initialization_evidence_digest
        or successor.pull_request != pull_request
        or successor.head_sha != resulting_head_sha
    ):
        raise LifecycleOrchestrationError(
            "collision Continuation signed lifecycle identity changed"
        )
    scope = authorization.get("scope")
    authorized_collision = (
        scope.get("collision") if isinstance(scope, Mapping) else None
    )
    if not isinstance(authorized_collision, Mapping):
        raise LifecycleOrchestrationError(
            "collision Continuation authorization scope is invalid"
        )

    try:
        predecessor_state = authority._validate_state(copy.deepcopy(predecessor.state))
        successor_state = authority._validate_state(copy.deepcopy(successor.state))
        reviewed = fast_path.verify_reviewed_state_evidence(reviewed_state_evidence)
        continuation = fast_path.normalize_exceptional_continuation_evidence(
            continuation_evidence,
            repository=repository,
            reviewed_state=reviewed,
            validated_tree_sha=authorized_collision.get("resulting_tree"),
            eligibility_evidence=eligibility_evidence,
        )
        (
            sealed_collision,
            validation_registry,
            authenticated_source,
            receipt_digest,
        ) = (
            version_collision._historical_collision_validation_binding_for_commit(
                repository=repository,
                delivery_issue=delivery_issue,
                pull_request=pull_request,
                predecessor_head=predecessor.head_sha,
                resulting_head=resulting_head_sha,
                repository_root=repository_root,
                protected_main=authorized_collision.get("protected_main"),
                expected_signer=continuation["expected_signer"],
                expected_collision_digest=continuation[
                    "collision_digest"
                ],
            )
        )
        authenticated_collision = sealed_collision.to_dict()
        source = _authenticate_continuation_commit(
            repository_root,
            repository,
            predecessor.head_sha,
            resulting_head_sha,
            continuation["expected_signer"],
            authenticated_source=authenticated_source,
        )
        prior_tree = authenticated_collision["predecessor_tree"]
        validation = fast_path.verify_validation_attestation(
            validation_attestation,
            repository=repository,
            head_sha=resulting_head_sha,
            registry=validation_registry,
            command_set=validation_registry["validation"],
            reviewed_state=reviewed,
            commit_parent_sha=predecessor.head_sha,
            commit_tree_sha=source.tree_sha,
            commit_validation_receipt_digest=receipt_digest,
            delivery_issue_number=delivery_issue,
        )
        if validation_attestation.get(
            "exceptional_continuation_evidence_digest"
        ) != fast_path.digest_json(continuation):
            raise LifecycleOrchestrationError(
                "validation attestation does not bind collision Continuation"
            )
    except (
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        authority.LifecycleAuthorityError,
        fast_path.SecurityBlocker,
        publication.LifecyclePublicationError,
        version_collision.VersionCollisionError,
    ) as exc:
        raise LifecycleOrchestrationError(
            "collision Continuation evidence is invalid or stale"
        ) from exc

    unchanged_fields = (
        "unrestricted_review_count",
        "remediation_cycle_count",
        "cycle_3_absent",
        "draft",
        "ready",
        "ready_transition_count",
        "ready_history",
        "exceptional_recovery_count",
        "exceptional_recovery_history",
    )
    lifecycle_projection = {
        "unrestricted_reviews": predecessor_state["unrestricted_review_count"],
        "remediation_cycles": predecessor_state["remediation_cycle_count"],
        "cycle_3": not predecessor_state["cycle_3_absent"],
        "draft": predecessor_state["draft"],
        "ready": predecessor_state["ready"],
        "ready_transition_count": predecessor_state["ready_transition_count"],
        "ready_history": predecessor_state["ready_history"],
        "exceptional_recovery_count": predecessor_state[
            "exceptional_recovery_count"
        ],
        "exceptional_recovery_history": predecessor_state[
            "exceptional_recovery_history"
        ],
        "exceptional_continuation_predecessor_count": 0,
        "exceptional_continuation_successor_count": 1,
    }
    if (
        any(
            predecessor_state[field] != successor_state[field]
            for field in unchanged_fields
        )
        or predecessor_state["unrestricted_review_count"]
        != authority.MAX_UNRESTRICTED_REVIEWS
        or predecessor_state["remediation_cycle_count"]
        != authority.MAX_REMEDIATION_CYCLES
        or predecessor_state["cycle_3_absent"] is not True
        or predecessor_state["draft"] is not False
        or predecessor_state["ready"] is not True
        or predecessor_state["exceptional_recovery_count"]
        != authority.MAX_EXCEPTIONAL_RECOVERIES
        or predecessor_state["exceptional_continuation_count"] != 0
        or predecessor_state["exceptional_continuation_history"] != []
        or successor_state["exceptional_continuation_count"] != 1
        or successor_state["exceptional_continuation_history"]
        != [{
            "sequence": 1,
            "transition_kind": "EXCEPTIONAL_CONTINUATION",
            "event_authorization_digest": transition.event_digest,
        }]
        or continuation["schema_version"] != "1.1"
        or continuation["trigger"] != version_collision.TRIGGER
        or continuation["authorization_id"]
        != authorization.get("authorization_id")
        or continuation["delivery_issue_number"] != delivery_issue
        or continuation["pull_request_number"] != pull_request
        or continuation["prior_ready_head_sha"] != predecessor.head_sha
        or continuation["prior_ready_tree_sha"] != prior_tree
        or continuation["continuation_tree_sha"] != source.tree_sha
        or continuation["lifecycle"] != lifecycle_projection
        or successor.tree_sha != validation.tree_sha
        or successor.validation_receipt_digest
        != validation.validation_receipt_digest
        or successor.source_validation_evidence_digest
        != validation.source_validation_evidence_digest
        or successor.adoption_source_evidence_digest
        != validation.final_attestation_digest
    ):
        raise LifecycleOrchestrationError(
            "collision Continuation projection differs from verified authority"
        )

    scope_fields = {
        "trigger",
        "pull_request",
        "predecessor_head_sha",
        "resulting_head_sha",
        "collision",
        "reviewed_state_digest",
        "stable_state_digest",
        "reviewed_feedback_digest",
        "predecessor_safety_digest",
        "continuation_evidence_digest",
        "validation_attestation_digest",
        "validation_receipt_digest",
    }
    collision = scope.get("collision") if isinstance(scope, Mapping) else None
    try:
        if (
            not isinstance(scope, dict)
            or set(scope) != scope_fields
            or not isinstance(collision, dict)
            or scope["trigger"] != version_collision.TRIGGER
            or scope["pull_request"] != pull_request
            or scope["predecessor_head_sha"] != predecessor.head_sha
            or scope["resulting_head_sha"] != resulting_head_sha
            or scope["reviewed_state_digest"] != reviewed.state_digest
            or scope["stable_state_digest"] != reviewed.state_digest
            or scope["reviewed_feedback_digest"] != reviewed.feedback_digest
            or scope["continuation_evidence_digest"]
            != fast_path.digest_json(continuation)
            or collision.get("trigger") != version_collision.TRIGGER
            or collision.get("repository") != repository
            or collision.get("delivery_issue") != delivery_issue
            or collision.get("pull_request") != pull_request
            or collision.get("predecessor_head") != predecessor.head_sha
            or collision.get("predecessor_tree") != prior_tree
            or collision.get("resulting_head") != resulting_head_sha
            or collision.get("resulting_tree") != source.tree_sha
            or collision != authenticated_collision
            or continuation["collision_digest"]
            != fast_path.digest_json(
                version_collision.validation_collision_projection(collision)
            )
            or scope["validation_attestation_digest"]
            != validation.final_attestation_digest
            or scope["validation_receipt_digest"]
            != validation.validation_receipt_digest
        ):
            raise LifecycleOrchestrationError(
                "collision Continuation authorization scope is invalid"
            )
        for field in (
            "predecessor_safety_digest",
            "validation_attestation_digest",
            "validation_receipt_digest",
        ):
            authority._require_digest(scope[field], "collision Continuation " + field)
    except (authority.LifecycleAuthorityError, TypeError) as exc:
        raise LifecycleOrchestrationError(
            "collision Continuation authorization scope is invalid"
        ) from exc

    _authorization(
        orchestration_authorization,
        event_id=transition.event_id,
        operation="EXCEPTIONAL_CONTINUATION",
        expected_scope=copy.deepcopy(scope),
        observed=transition.predecessor,
        lifecycle=predecessor,
        verifier=_verify_user_authorization,
        verified_item=authorization,
    )
    return VerifiedExceptionalContinuationAuthority(
        continuation_digest=fast_path.digest_json(continuation),
        authorization_id=authorization["authorization_id"],
        authorization_digest=authorization["authorization_digest"],
        repository=repository,
        delivery_issue=delivery_issue,
        pull_request=pull_request,
        lifecycle_id=predecessor.lifecycle_id,
        predecessor_publication_oid=transition.predecessor.publication_oid,
        predecessor_publication_digest=transition.predecessor.publication_digest,
        continuation_publication_oid=transition.successor.publication_oid,
        continuation_publication_digest=transition.successor.publication_digest,
        predecessor_authority_digest=predecessor.authority_digest,
        continuation_authority_digest=successor.authority_digest,
        prior_ready_head_sha=predecessor.head_sha,
        resulting_head_sha=resulting_head_sha,
        prior_ready_tree_sha=prior_tree,
        continuation_tree_sha=source.tree_sha,
        reviewed_state_digest=reviewed.state_digest,
        reviewed_feedback_digest=reviewed.feedback_digest,
        eligibility_evidence_digest=continuation["eligibility_evidence_digest"],
        finding_ids=(),
        thread_ids=(),
        source_signer_kind=source.signer_kind,
        source_signer_identity=source.signer_identity,
    )


def _collision_request(value: Any) -> dict[str, Any]:
    item = _closed_mapping(value, COLLISION_CONTINUATION_FIELDS, "collision continuation evidence")
    if (
        item["schema_version"] != "1.1" or item["trigger"] != version_collision.TRIGGER
        or not isinstance(item["repository_root"], str) or not 0 < len(item["repository_root"]) <= 4096
    ):
        raise LifecycleOrchestrationError("collision continuation evidence has unsupported semantics")
    return item


def _require_continuation_predecessor(state: Mapping[str, Any], predecessor: str, resulting: str) -> None:
    if (
        state["ready"] is not True or state["draft"] is not False or resulting == predecessor
        or state["unrestricted_review_count"] != authority.MAX_UNRESTRICTED_REVIEWS
        or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
        or state["exceptional_recovery_count"] != authority.MAX_EXCEPTIONAL_RECOVERIES
        or state["exceptional_continuation_count"] != 0 or state["cycle_3_absent"] is not True
    ):
        raise LifecycleOrchestrationError("exceptional continuation requires the exact exhausted Ready predecessor")


def _authenticate_collision_predecessor_safety(
    value: Any, *, reviewed: fast_path.StableFeedbackState, delivery_issue: int,
) -> Any:
    item = copy.deepcopy(value)
    historical = item.pop("historical_thread_classifications", []) if isinstance(item, dict) else []
    if not isinstance(historical, list) or len(historical) > 32:
        raise LifecycleOrchestrationError("historical predecessor classifications exceed the bound")
    prepared = _authenticate_successor_safety_evidence(
        item, repository=reviewed.repository, delivery_issue=delivery_issue,
        pull_request=reviewed.pull_request_number, predecessor_state_digest=reviewed.state_digest,
        resulting_head_sha=reviewed.head_sha, resulting_state_digest=reviewed.state_digest,
    )
    if not historical:
        return prepared
    signer = _successor_classification_signer(reviewed.repository, item["classification_signer"])
    threads = {thread["node_id"]: thread for thread in reviewed.feedback["threads"]}
    for raw in historical:
        try:
            if not isinstance(raw, dict) or set(raw) != {"thread_id", "classification_artifact", "classification_signature"}:
                raise ValueError("historical classification is not closed")
            thread = threads.get(raw["thread_id"])
            if not isinstance(thread, dict) or len(thread["comments"]) != 1 or thread["comments"][0]["reply_to_id"] is not None:
                raise ValueError("historical classification requires an exact reply-free thread")
            for key, limit in (("classification_artifact", late_disposition.MAXIMUM_ARTIFACT_BYTES),
                               ("classification_signature", late_disposition.MAXIMUM_SIGNATURE_BYTES)):
                if not isinstance(raw[key], str) or len(raw[key]) > 4 * limit // 3 + 8:
                    raise ValueError("historical classification exceeds the bound")
            with tempfile.TemporaryDirectory(prefix="secpal-collision-predecessor-") as directory:
                root = Path(directory)
                artifact_path, signature_path = root / "classification.json", root / "classification.sig"
                late_disposition._write_private_file(artifact_path, base64.b64decode(raw["classification_artifact"], validate=True))
                late_disposition._write_private_file(signature_path, base64.b64decode(raw["classification_signature"], validate=True))
                verified = late_disposition.parse_preserved_thread_classification_artifact(
                    artifact_path, signature_path, expected_signer=signer, repository=reviewed.repository,
                    delivery_issue_number=delivery_issue, pull_request_number=reviewed.pull_request_number,
                    head_sha=reviewed.head_sha, thread_id=raw["thread_id"],
                )
            authorized = verified.thread
            if (
                authority.loads_closed_json(verified.canonical_payload)["schema_version"] != "1.3"
                or authorized.classification != "VALID_ACTIONABLE" or authorized.disposition != "CORRECTED_AND_VERIFIED"
                or authorized.reply_count != 0 or authorized.reply_state_digest != fast_path.digest_json([])
                or authorized.top_level_comment_node_id != thread["comments"][0]["node_id"]
                or authorized.finding_body_digest != thread["comments"][0]["body_digest"]
                or authorized.is_resolved != thread["is_resolved"] or authorized.is_outdated != thread["is_outdated"]
            ):
                raise ValueError("historical classification does not bind the current thread")
        except (KeyError, TypeError, ValueError, OSError, late_disposition.LateDispositionError) as exc:
            raise LifecycleOrchestrationError("historical predecessor correction is not authenticated") from exc
        sources = (("THREAD_COMMENT", authorized.top_level_comment_node_id, authorized.finding_body_digest, authorized.thread_id),)
        prepared["successor_findings"].append({
            "sources": [{"kind": kind, "node_id": node, "digest": digest} for kind, node, digest, _thread in sources],
            "classification_evidence": fast_path._seal_successor_classification(
                repository=verified.repository, delivery_issue_number=verified.delivery_issue_number,
                pull_request_number=verified.pull_request_number, head_sha=verified.head_sha,
                finding_id=verified.finding_id, finding_evidence_digest=verified.finding_evidence_digest,
                thread_id=authorized.thread_id, top_level_comment_node_id=authorized.top_level_comment_node_id,
                finding_body_digest=authorized.finding_body_digest, reply_count=0,
                is_resolved=authorized.is_resolved, is_outdated=authorized.is_outdated,
                classification=authorized.classification, disposition=authorized.disposition,
                technically_blocking=authorized.technically_blocking, technical_blockers=verified.technical_blockers,
                classification_evidence_digest=verified.evidence_digest, source_bindings=sources,
            ),
        })
    return prepared


def _collision_predecessor_gate(
    item: Mapping[str, Any], lifecycle: authority.VerifiedLifecycleAuthority,
) -> tuple[fast_path.StableFeedbackState, Any]:
    """Authenticate cheap predecessor feedback authority before Git acquisition."""

    reviewed = fast_path.verify_reviewed_state_evidence(
        item["reviewed_state_evidence"]
    )
    if (
        reviewed.repository != lifecycle.repository
        or reviewed.pull_request_number != lifecycle.pull_request
        or reviewed.head_sha != lifecycle.head_sha
        or reviewed.pr_state != "OPEN"
    ):
        raise LifecycleOrchestrationError(
            "collision predecessor feedback differs from CURRENT"
        )
    try:
        safety = _authenticate_collision_predecessor_safety(
            item["predecessor_safety_evidence"],
            reviewed=reviewed,
            delivery_issue=lifecycle.delivery_issue,
        )
        fast_path.verify_clean_feedback_gate(reviewed, safety)
    except fast_path.SecurityBlocker as exc:
        raise LifecycleOrchestrationError(
            "collision predecessor feedback is not safely dispositioned"
        ) from exc
    return reviewed, safety


def _collision_scope(
    item: Mapping[str, Any], *, observed: Any, resulting_head: str,
    collision_validation_reader: Callable[
        ...,
        tuple[
            version_collision.VerifiedVersionCollision,
            dict[str, Any],
            fast_path.AuthenticatedIntegrationCommit,
            str,
        ],
    ],
) -> tuple[dict[str, Any], fast_path.StableFeedbackState, fast_path.VerifiedValidationEvidence]:
    _require_continuation_predecessor(
        observed.lifecycle.state, observed.lifecycle.head_sha, resulting_head,
    )
    predecessor_gate = _collision_predecessor_gate(item, observed.lifecycle)
    root = Path(item["repository_root"]).resolve(strict=True)
    sealed, validation_registry, source, receipt_digest = (
        collision_validation_reader(
            repository=observed.lifecycle.repository,
            delivery_issue=observed.lifecycle.delivery_issue,
            pull_request=observed.lifecycle.pull_request,
            predecessor_head=observed.lifecycle.head_sha,
            resulting_head=resulting_head,
            repository_root=root,
            expected_signer=item["continuation_document"].get(
                "expected_signer"
            ),
        )
    )
    return _collision_scope_from_source(
        {**item, "repository_root": str(root)},
        observed=observed,
        resulting_head=resulting_head,
        sealed_collision=sealed,
        predecessor_gate=predecessor_gate,
        validation_registry=validation_registry,
        authenticated_source=source,
        receipt_digest=receipt_digest,
    )


def _collision_scope_from_source(
    item: Mapping[str, Any], *, observed: Any, resulting_head: str,
    sealed_collision: version_collision.VerifiedVersionCollision,
    predecessor_gate: tuple[fast_path.StableFeedbackState, Any],
    validation_registry: dict[str, Any],
    authenticated_source: fast_path.AuthenticatedIntegrationCommit,
    receipt_digest: str,
) -> tuple[dict[str, Any], fast_path.StableFeedbackState, fast_path.VerifiedValidationEvidence]:
    lifecycle = observed.lifecycle
    _require_continuation_predecessor(lifecycle.state, lifecycle.head_sha, resulting_head)
    reviewed, safety = predecessor_gate
    root = Path(item["repository_root"]).resolve(strict=True)
    if not isinstance(
        sealed_collision, version_collision.VerifiedVersionCollision
    ):
        raise LifecycleOrchestrationError("collision authority requires a verifier-sealed result")
    collision = sealed_collision.to_dict()
    if any(collision.get(key) != value for key, value in {
        "repository": lifecycle.repository, "delivery_issue": lifecycle.delivery_issue,
        "pull_request": lifecycle.pull_request, "predecessor_head": lifecycle.head_sha,
        "resulting_head": resulting_head, "trigger": version_collision.TRIGGER,
    }.items()):
        raise LifecycleOrchestrationError("collision authority differs from CURRENT source identity")
    document = fast_path.normalize_exceptional_continuation_evidence(
        item["continuation_document"], repository=lifecycle.repository, reviewed_state=reviewed,
        validated_tree_sha=collision["resulting_tree"], eligibility_evidence=item["eligibility_evidence"],
    )
    state = lifecycle.state
    projection = {
        "unrestricted_reviews": state["unrestricted_review_count"],
        "remediation_cycles": state["remediation_cycle_count"], "cycle_3": not state["cycle_3_absent"],
        "draft": state["draft"], "ready": state["ready"], "ready_transition_count": state["ready_transition_count"],
        "ready_history": state["ready_history"], "exceptional_recovery_count": state["exceptional_recovery_count"],
        "exceptional_recovery_history": state["exceptional_recovery_history"],
        "exceptional_continuation_predecessor_count": 0, "exceptional_continuation_successor_count": 1,
    }
    if (
        document.get("schema_version") != "1.1" or document.get("trigger") != version_collision.TRIGGER
        or document["delivery_issue_number"] != lifecycle.delivery_issue
        or document["prior_ready_tree_sha"] != collision["predecessor_tree"]
        or document["collision_digest"] != fast_path.digest_json(version_collision.validation_collision_projection(collision))
        or document["lifecycle"] != projection
    ):
        raise LifecycleOrchestrationError("continuation evidence differs from authenticated collision")
    source = _authenticate_continuation_commit(
        root,
        lifecycle.repository,
        lifecycle.head_sha,
        resulting_head,
        document["expected_signer"],
        authenticated_source=authenticated_source,
    )
    if source.tree_sha != collision["resulting_tree"]:
        raise LifecycleOrchestrationError("collision successor tree differs from signed source")
    registry = copy.deepcopy(validation_registry)
    if re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None:
        raise LifecycleOrchestrationError("collision signed validation receipt is absent or ambiguous")
    attestation = item["validation_attestation"]
    validation = fast_path.verify_validation_attestation(
        attestation, repository=lifecycle.repository, head_sha=resulting_head,
        registry=registry, command_set=registry["validation"], reviewed_state=reviewed,
        commit_parent_sha=lifecycle.head_sha, commit_tree_sha=source.tree_sha,
        commit_validation_receipt_digest=receipt_digest, delivery_issue_number=lifecycle.delivery_issue,
    )
    if attestation.get("exceptional_continuation_evidence_digest") != fast_path.digest_json(document):
        raise LifecycleOrchestrationError("collision validation does not bind continuation evidence")
    scope = {
        "trigger": version_collision.TRIGGER, "pull_request": lifecycle.pull_request,
        "predecessor_head_sha": lifecycle.head_sha, "resulting_head_sha": resulting_head,
        "collision": collision, "reviewed_state_digest": reviewed.state_digest,
        "stable_state_digest": reviewed.state_digest, "reviewed_feedback_digest": reviewed.feedback_digest,
        "predecessor_safety_digest": fast_path.digest_json(item["predecessor_safety_evidence"]),
        "continuation_evidence_digest": fast_path.digest_json(document),
        "validation_attestation_digest": attestation["attestation_digest"],
        "validation_receipt_digest": receipt_digest,
    }
    return scope, reviewed, validation


def issue_collision_continuation_authorization(
    *, repository: str, delivery_issue: int, authorization_id: str,
    reason: str, resulting_head: str, evidence: Mapping[str, Any],
) -> bytes:
    """Issue existing-family user authority after fixed live and source acquisition."""

    from . import lifecycle_execution

    item = _collision_request(evidence)
    if item["successor_safety_evidence"] is not None:
        raise LifecycleOrchestrationError("collision authorization must precede successor publication")
    observed, lifecycle, _ = _authenticated_current(repository, delivery_issue, publication.verify_current_lifecycle_authority)
    current_main = version_collision._authenticate_installed_collision_issuer()
    live = _capture_current_stable_feedback(repository, lifecycle.pull_request)
    continuation = item["continuation_document"]

    def authenticated_epoch_reader(**arguments: Any) -> tuple[
        version_collision.VerifiedVersionCollision,
        dict[str, Any],
        fast_path.AuthenticatedIntegrationCommit,
        str,
    ]:
        return version_collision.collision_validation_binding_for_issuance(
            **arguments,
            expected_collision_digest=continuation.get("collision_digest"),
        )

    scope, reviewed, _ = _collision_scope(
        item, observed=observed, resulting_head=_oid(resulting_head, "collision successor"),
        collision_validation_reader=authenticated_epoch_reader,
    )
    if live.to_dict() != reviewed.to_dict() or item["continuation_document"]["authorization_id"] != authorization_id:
        raise LifecycleOrchestrationError("collision authorization differs from exact live predecessor")
    actual_pr = lifecycle_execution._read_live_github(repository, lifecycle.pull_request)
    if (
        actual_pr.repository != repository or actual_pr.pull_request != lifecycle.pull_request
        or actual_pr.head_sha != lifecycle.head_sha or actual_pr.state != "OPEN" or actual_pr.draft is not False
    ):
        raise LifecycleOrchestrationError("collision authorization requires the exact live Ready predecessor")
    final = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    if (
        final.publication_oid != observed.publication_oid
        or final.publication_digest != observed.publication_digest
        or _capture_current_stable_feedback(repository, lifecycle.pull_request).to_dict() != live.to_dict()
        or version_collision._observe_main() != current_main
    ):
        raise LifecycleOrchestrationError("collision predecessor changed before authorization signing")
    policy = authority._load_lifecycle_trust_policy(repository)
    identity, signer = lifecycle_execution._policy_role_signer(
        policy, policy.transition_signer_identities, "transition signer role", allow_routine_default=True,
    )
    result = create_user_authorization(
        authorization_id=authorization_id, repository=repository, delivery_issue=delivery_issue,
        lifecycle=lifecycle, publication_oid=observed.publication_oid,
        publication_digest=observed.publication_digest, operation="EXCEPTIONAL_CONTINUATION",
        reason=reason, scope=scope, signer_identity=identity, signer=signer,
    )
    _verify_user_authorization(result, observed, lifecycle)
    return result


def publish_collision_continuation(
    repository: str, delivery_issue: int, request: Mapping[str, Any],
) -> publication.VerifiedLifecyclePublication:
    """Publish one admitted existing transition; no PR or thread mutation is performed."""

    from . import lifecycle_execution

    item = _closed_request(request)
    if item.get("event_kind") != "CONTINUATION_COMMIT_PUSHED":
        raise LifecycleOrchestrationError("collision publication requires the continuation event")
    collision_item = _collision_request(item.get("continuation_evidence"))
    observed = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    current_main = version_collision._authenticate_installed_collision_issuer()
    authorization = _verify_user_authorization(
        item["authorization"], observed, observed.lifecycle
    )
    collision_scope = authorization.get("scope", {}).get("collision", {})

    def authenticated_epoch_reader(**arguments: Any) -> tuple[
        version_collision.VerifiedVersionCollision,
        dict[str, Any],
        fast_path.AuthenticatedIntegrationCommit,
        str,
    ]:
        return version_collision._historical_collision_validation_binding_for_commit(
            **arguments,
            protected_main=collision_scope.get("protected_main"),
            expected_collision_digest=collision_item["continuation_document"].get(
                "collision_digest"
            ),
        )

    validation: list[tuple[fast_path.VerifiedValidationEvidence, str]] = []
    decision = _orchestrate_event(
        repository, delivery_issue, item, current_reader=lambda *_args: observed,
        collision_validation_reader=authenticated_epoch_reader,
        _collision_validation_output=validation,
    )
    if decision.lifecycle_transition != "EXCEPTIONAL_CONTINUATION" or len(validation) != 1:
        raise LifecycleOrchestrationError("collision publication has no complete admitted transition")
    signers = lifecycle_execution._production_signing_authorities(repository, authorization["signer_identity"])
    successor = lifecycle_execution._append_successor_evidence(
        observed, authorization, signers, resulting_head_sha=item["head_sha"], current_head_evidence=validation[0][0],
    )
    current = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    actual_pr = lifecycle_execution._read_live_github(repository, observed.lifecycle.pull_request)
    final_feedback = _capture_current_stable_feedback(
        repository, observed.lifecycle.pull_request
    )
    final_protected_main = version_collision._observe_main()
    if (
        current.publication_oid != observed.publication_oid or current.publication_digest != observed.publication_digest
        or actual_pr.repository != repository or actual_pr.pull_request != observed.lifecycle.pull_request
        or actual_pr.head_sha != item["head_sha"] or actual_pr.state != "OPEN" or actual_pr.draft is not False
        or final_feedback.state_digest != validation[0][1]
        or final_protected_main != current_main
    ):
        raise LifecycleOrchestrationError("collision publication predecessor or live Ready successor drifted")
    published = publication.advance_current_terminal(
        successor, signer_identity=signers.publication_identity, signer=signers.publication_signer,
    )
    readback = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    if (
        readback.publication_oid != published.publication_oid or readback.publication_digest != published.publication_digest
        or readback.lifecycle.head_sha != item["head_sha"]
        or readback.lifecycle.state["exceptional_continuation_count"] != 1
    ):
        raise LifecycleOrchestrationError("collision publication readback is not the exact successor")
    return readback


def _authorized_finding_ids(value: Any) -> list[str]:
    scope = value.get("scope") if isinstance(value, Mapping) else None
    finding_ids = scope.get("finding_ids") if isinstance(scope, Mapping) else None
    if (
        not isinstance(finding_ids, list)
        or not finding_ids
        or len(finding_ids) != len(set(finding_ids))
        or any(not isinstance(item, str) or not item for item in finding_ids)
    ):
        raise LifecycleOrchestrationError(
            "source-change authorization requires exact finding identities"
        )
    for finding_id in finding_ids:
        _identity(finding_id, "authorized finding identity")
    return finding_ids


def _remediation_authorization_scope(
    value: Mapping[str, Any],
    lifecycle: authority.VerifiedLifecycleAuthority,
    resulting_head_sha: str,
) -> dict[str, Any]:
    """Preserve ordinary scope and its optional verified growth binding."""

    finding_ids = _authorized_finding_ids(value)
    scope = {
        "pull_request": lifecycle.pull_request,
        "predecessor_head_sha": lifecycle.head_sha,
        "resulting_head_sha": resulting_head_sha,
        "finding_ids": finding_ids,
    }
    supplied = value.get("scope")
    finding_authority_digest = (
        supplied.get("finding_authority_digest")
        if isinstance(supplied, Mapping)
        else None
    )
    if finding_authority_digest is not None:
        try:
            scope["finding_authority_digest"] = authority._require_digest(
                finding_authority_digest,
                "ordinary remediation finding authority",
            )
        except authority.LifecycleAuthorityError as exc:
            raise LifecycleOrchestrationError(str(exc)) from exc
    return scope


def _authenticated_current(
    repository: str,
    delivery_issue: int,
    reader: CurrentReader,
) -> tuple[Any, authority.VerifiedLifecycleAuthority, dict[str, Any]]:
    try:
        observed = reader(repository, delivery_issue)
    except (authority.LifecycleAuthorityError, publication.LifecyclePublicationError) as exc:
        raise LifecycleOrchestrationError(
            "CURRENT lifecycle publication is unavailable or invalid"
        ) from exc
    lifecycle = getattr(observed, "lifecycle", None)
    publication_oid = getattr(observed, "publication_oid", None)
    publication_digest = getattr(observed, "publication_digest", None)
    if (
        not isinstance(lifecycle, authority.VerifiedLifecycleAuthority)
        or lifecycle.repository != repository
        or lifecycle.delivery_issue != delivery_issue
    ):
        raise LifecycleOrchestrationError(
            "CURRENT lifecycle publication identity does not match the delivery"
        )
    try:
        state = authority._validate_state(copy.deepcopy(lifecycle.state))
        _oid(publication_oid, "publication object")
        authority._require_digest(publication_digest, "publication digest")
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(
            "CURRENT lifecycle publication is malformed"
        ) from exc
    return observed, lifecycle, state


def _base_decision(
    observed: Any,
    lifecycle: authority.VerifiedLifecycleAuthority,
    state: Mapping[str, Any],
    **changes: Any,
) -> LifecycleDecision:
    fields = {
        "publication_oid": observed.publication_oid,
        "publication_digest": observed.publication_digest,
        "lifecycle_identity": lifecycle.lifecycle_id,
        "pull_request": lifecycle.pull_request,
        "head_sha": lifecycle.head_sha,
        "resulting_pull_request": lifecycle.pull_request,
        "resulting_head_sha": lifecycle.head_sha,
        "unrestricted_reviews": state["unrestricted_review_count"],
        "remediation_cycles": state["remediation_cycle_count"],
        "cycle_3_absent": state["cycle_3_absent"],
        "exceptional_recoveries": state["exceptional_recovery_count"],
        "exceptional_continuations": state["exceptional_continuation_count"],
        "ready": state["ready"],
        "ready_transition_already_performed": state["ready_transition_count"] > 0,
        "preserve_ready": state["ready"],
    }
    fields.update(changes)
    return LifecycleDecision(**fields)


def _prove_transition_is_finite(
    state: Mapping[str, Any], transition: str, event_id: str
) -> None:
    event_digest = authority.digest_json(
        {"event_id": event_id, "transition_kind": transition}
    )
    try:
        authority.derive_state(state, transition, event_digest)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc


def _orchestrate_event(
    repository: str,
    delivery_issue: int,
    request: Mapping[str, Any],
    *,
    current_reader: CurrentReader = publication.verify_current_lifecycle_authority,
    follow_up_verifier: FollowUpVerifier = follow_up.verify_live_follow_up,
    authorization_verifier: AuthorizationVerifier = _verify_user_authorization,
    feedback_reader: Callable[
        [str, int], fast_path.StableFeedbackState
    ] = _capture_current_stable_feedback,
    collision_validation_reader: Callable[
        ...,
        tuple[
            version_collision.VerifiedVersionCollision,
            dict[str, Any],
            fast_path.AuthenticatedIntegrationCommit,
            str,
        ],
    ] = version_collision.collision_validation_binding_for_commit,
    _collision_validation_output: list[tuple[fast_path.VerifiedValidationEvidence, str]] | None = None,
    reanchor_verifier: Callable[
        ..., VerifiedRejectedContinuationReanchor
    ] | None = None,
    source_commit_verifier: Callable[
        ..., fast_path.AuthenticatedIntegrationCommit
    ] = _authenticate_continuation_commit,
) -> LifecycleDecision:
    """Authenticate CURRENT state and select one bounded, non-recursive action."""

    try:
        repository = authority._require_repository(repository)
    except authority.LifecycleAuthorityError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc
    delivery_issue = _positive_int(delivery_issue, "delivery issue")
    item = _closed_request(request)
    event_kind = item.get("event_kind")
    if event_kind not in EVENTS:
        raise LifecycleOrchestrationError("lifecycle event kind is not allowlisted")
    event_id = _identity(item.get("event_id"), "event identity")
    request_pr = _positive_int(item.get("pull_request"), "event pull request")
    request_head = _oid(item.get("head_sha"), "event head")
    observed, lifecycle, state = _authenticated_current(
        repository, delivery_issue, current_reader
    )
    if request_pr != lifecycle.pull_request:
        raise LifecycleOrchestrationError(
            "event pull request differs from CURRENT lifecycle authority"
        )

    classification_value = item.get("classification")
    follow_up_value = item.get("follow_up")
    authorization_value = item.get("authorization")
    replacement = item.get("replacement_pull_request")
    continuation_evidence = item.get("continuation_evidence")

    if event_kind in OBSERVATION_EVENTS:
        if (
            request_head != lifecycle.head_sha
            or replacement is not None
            or classification_value is not None
            or follow_up_value is not None
            or authorization_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError(
                "observation event differs from CURRENT lifecycle state"
            )
        return _base_decision(observed, lifecycle, state)

    if event_kind == "PR_REPLACED":
        replacement_pr = _positive_int(replacement, "replacement pull request")
        if request_head != lifecycle.head_sha or replacement_pr == lifecycle.pull_request:
            raise LifecycleOrchestrationError("replacement PR binding is invalid")
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("replacement cannot carry feedback facts")
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="PR_REBOUND",
            expected_scope={
                "predecessor_pull_request": lifecycle.pull_request,
                "replacement_pull_request": replacement_pr,
                "head_sha": lifecycle.head_sha,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
        )
        _prove_transition_is_finite(state, "PR_REBOUND", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="PR_REBOUND",
            resulting_pull_request=replacement_pr,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if replacement is not None:
        raise LifecycleOrchestrationError("only PR replacement may name another PR")

    if event_kind == "REMEDIATION_COMMIT_PUSHED":
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError(
                "remediation cannot carry feedback classification"
            )
        if not state["ready"] or request_head == lifecycle.head_sha:
            raise LifecycleOrchestrationError(
                "Ready remediation requires an authenticated new head"
            )
        verified_authorization = authorization_verifier(
            authorization_value, observed, lifecycle
        )
        expected_scope = _remediation_authorization_scope(
            verified_authorization,
            lifecycle,
            request_head,
        )
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="REMEDIATION_COMPLETED",
            expected_scope=expected_scope,
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
            verified_item=verified_authorization,
        )
        _prove_transition_is_finite(state, "REMEDIATION_COMPLETED", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="REMEDIATION_COMPLETED",
            preserve_ready=True,
            resulting_head_sha=request_head,
            requires_fresh_head_evidence=True,
            merge_ready=False,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind == "RECOVERY_COMMIT_PUSHED":
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("recovery cannot carry feedback classification")
        if (
            not state["ready"]
            or request_head == lifecycle.head_sha
            or state["unrestricted_review_count"]
            != authority.MAX_UNRESTRICTED_REVIEWS
            or state["remediation_cycle_count"] != authority.MAX_REMEDIATION_CYCLES
        ):
            raise LifecycleOrchestrationError(
                "exceptional recovery requires an exhausted Ready lifecycle and a new head"
            )
        verified_authorization = authorization_verifier(
            authorization_value, observed, lifecycle
        )
        finding_ids = _authorized_finding_ids(verified_authorization)
        scope = verified_authorization.get("scope", {})
        expected_scope = {
            "pull_request": lifecycle.pull_request,
            "predecessor_head_sha": lifecycle.head_sha,
            "resulting_head_sha": request_head,
            "finding_ids": finding_ids,
        }
        if scope.get("admission_kind") == exceptional_recovery.ADMISSION_KIND:
            try:
                exceptional_recovery.authenticate_maintained_code()
                recovery = exceptional_recovery.verify_admission(scope.get("recovery_evidence"), observed, Path.cwd())
                if recovery["authorization_id"] != verified_authorization["authorization_id"]:
                    raise LifecycleOrchestrationError(
                        "diagnostic Recovery authorization identity changed"
                    )
                exceptional_recovery.require_successor(Path.cwd(), recovery, request_head)
                expected_scope = exceptional_recovery.authorization_scope(
                    recovery, request_head
                )
            except exceptional_recovery.DiagnosticRecoveryError as exc:
                raise LifecycleOrchestrationError(str(exc)) from exc
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="EXCEPTIONAL_RECOVERY",
            expected_scope=expected_scope,
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
            verified_item=verified_authorization,
        )
        _prove_transition_is_finite(state, "EXCEPTIONAL_RECOVERY", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="EXCEPTIONAL_RECOVERY",
            preserve_ready=True,
            resulting_head_sha=request_head,
            requires_fresh_head_evidence=True,
            merge_ready=False,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind == "CONTINUATION_COMMIT_PUSHED":
        if classification_value is not None or follow_up_value is not None:
            raise LifecycleOrchestrationError(
                "continuation cannot carry caller-classified feedback"
            )
        _require_continuation_predecessor(state, lifecycle.head_sha, request_head)
        if isinstance(continuation_evidence, Mapping) and continuation_evidence.get("trigger") == version_collision.TRIGGER:
            collision_item = _collision_request(continuation_evidence)
            verified_authorization = authorization_verifier(authorization_value, observed, lifecycle)
            try:
                scope, reviewed, validation = _collision_scope(
                    collision_item, observed=observed, resulting_head=request_head,
                    collision_validation_reader=collision_validation_reader,
                )
                if collision_item["continuation_document"]["authorization_id"] != verified_authorization.get("authorization_id"):
                    raise LifecycleOrchestrationError("collision continuation authorization identity changed")
                authorization = _authorization(
                    authorization_value, event_id=event_id, operation="EXCEPTIONAL_CONTINUATION",
                    expected_scope=scope, observed=observed, lifecycle=lifecycle,
                    verifier=authorization_verifier, verified_item=verified_authorization,
                )
                current = feedback_reader(repository, lifecycle.pull_request)
                raw_successor = collision_item["successor_safety_evidence"]
                successor = _authenticate_successor_safety_evidence(
                    raw_successor, repository=repository,
                    delivery_issue=delivery_issue, pull_request=lifecycle.pull_request,
                    predecessor_state_digest=reviewed.state_digest, resulting_head_sha=request_head,
                    resulting_state_digest=current.state_digest,
                    collision_provider_growth=(
                        isinstance(raw_successor, Mapping)
                        and raw_successor.get("schema_version") == "1.3"
                    ),
                )
                if successor is None or not any(
                    isinstance(item, dict) and item.get("role") == "CODEX_SUMMARY_UPDATE"
                    for item in successor["provider_transport"]
                ):
                    raise LifecycleOrchestrationError("collision continuation requires resulting-head providers")
                fast_path.verify_collision_feedback_successor(
                    reviewed, current, resulting_head_sha=request_head,
                    successor_safety_evidence=successor,
                )
                _prove_transition_is_finite(state, "EXCEPTIONAL_CONTINUATION", event_id)
            except (fast_path.SecurityBlocker, version_collision.VersionCollisionError, OSError, ValueError) as exc:
                raise LifecycleOrchestrationError("collision continuation authentication failed") from exc
            if _collision_validation_output is not None:
                _collision_validation_output.append((validation, current.state_digest))
            return _base_decision(
                observed, lifecycle, state, lifecycle_transition="EXCEPTIONAL_CONTINUATION",
                preserve_ready=True, resulting_head_sha=request_head, requires_fresh_head_evidence=True,
                merge_ready=False, authorization_digest=authorization["authorization_digest"],
                requires_authorization_publication=True,
            )
        findings = _verify_continuation_finding_authority(
            continuation_evidence,
            repository=repository,
            delivery_issue=delivery_issue,
            pull_request=lifecycle.pull_request,
            predecessor_head_sha=lifecycle.head_sha,
            resulting_head_sha=request_head,
            feedback_reader=feedback_reader,
            observed=observed,
            repository_root=Path.cwd(),
            reanchor_verifier=(
                verify_rejected_continuation_reanchor
                if reanchor_verifier is None
                else reanchor_verifier
            ),
            source_commit_verifier=source_commit_verifier,
        )
        verified_authorization = authorization_verifier(
            authorization_value, observed, lifecycle
        )
        expected_scope = _continuation_authorization_scope(
            findings,
            pull_request=lifecycle.pull_request,
            predecessor_head_sha=lifecycle.head_sha,
            resulting_head_sha=request_head,
        )
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="EXCEPTIONAL_CONTINUATION",
            expected_scope=expected_scope,
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
            verified_item=verified_authorization,
        )
        _prove_transition_is_finite(state, "EXCEPTIONAL_CONTINUATION", event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="EXCEPTIONAL_CONTINUATION",
            preserve_ready=True,
            resulting_head_sha=request_head,
            requires_fresh_head_evidence=True,
            merge_ready=False,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if request_head != lifecycle.head_sha:
        raise LifecycleOrchestrationError(
            "event head differs from CURRENT lifecycle authority"
        )

    if event_kind in {"DRAFT_TO_READY", "READY_TO_DRAFT"}:
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("Ready/Draft transition cannot carry feedback facts")
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation=event_kind,
            expected_scope={
                "pull_request": lifecycle.pull_request,
                "head_sha": lifecycle.head_sha,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
        )
        _prove_transition_is_finite(state, event_kind, event_id)
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition=event_kind,
            preserve_ready=False,
            transition_to_draft=event_kind == "READY_TO_DRAFT",
            transition_to_ready=event_kind == "DRAFT_TO_READY",
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind == "ADDITIONAL_REVIEW_AUTHORIZED":
        if (
            classification_value is not None
            or follow_up_value is not None
            or continuation_evidence is not None
        ):
            raise LifecycleOrchestrationError("additional review cannot carry feedback facts")
        authorization = _authorization(
            authorization_value,
            event_id=event_id,
            operation="ADDITIONAL_REVIEW",
            expected_scope={
                "pull_request": lifecycle.pull_request,
                "head_sha": lifecycle.head_sha,
            },
            observed=observed,
            lifecycle=lifecycle,
            verifier=authorization_verifier,
        )
        _prove_transition_is_finite(
            state, "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED", event_id
        )
        return _base_decision(
            observed,
            lifecycle,
            state,
            lifecycle_transition="ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
            additional_review_authorized=True,
            authorization_digest=authorization["authorization_digest"],
            requires_authorization_publication=True,
        )

    if event_kind != "LATE_FEEDBACK_CLASSIFIED":
        raise LifecycleOrchestrationError("lifecycle event is not implemented")
    if continuation_evidence is not None:
        raise LifecycleOrchestrationError(
            "late feedback cannot carry continuation evidence"
        )
    if authorization_value is not None:
        raise LifecycleOrchestrationError(
            "feedback evidence cannot smuggle lifecycle authorization"
        )
    try:
        classification = replanning.classify(classification_value)
    except replanning.PlanError as exc:
        raise LifecycleOrchestrationError(str(exc)) from exc

    guarded_resolution_candidate = False
    resolution_meaning_if_applied = None
    if classification.name == "NON_BLOCKING_FOLLOWUP":
        try:
            identity = follow_up.parse_follow_up(follow_up_value)
            verified_follow_up = follow_up_verifier(identity)
        except follow_up.FollowUpError as exc:
            raise LifecycleOrchestrationError(str(exc)) from exc
        except Exception as exc:
            raise LifecycleOrchestrationError(
                "authenticated live follow-up verification failed"
            ) from exc
        if getattr(verified_follow_up, "identity", None) != identity:
            raise LifecycleOrchestrationError(
                "authenticated live follow-up identity changed"
            )
        guarded_resolution_candidate = True
        resolution_meaning_if_applied = "SAFELY_DISPOSITIONED_TRACKED"
    elif follow_up_value is not None:
        raise LifecycleOrchestrationError(
            "only a canonical non-blocking follow-up may carry tracking identity"
        )

    technically_blocking = classification.technically_blocking
    return _base_decision(
        observed,
        lifecycle,
        state,
        technically_blocking=technically_blocking,
        mechanically_blocking=classification.mechanically_blocking,
        merge_ready=False,
        explicit_recovery_required=technically_blocking and state["ready"],
        resolution_eligible=False,
        guarded_resolution_candidate=guarded_resolution_candidate,
        authenticated_resolution_required=guarded_resolution_candidate,
        resolution_meaning_if_applied=resolution_meaning_if_applied,
    )


def orchestrate_event(
    repository: str,
    delivery_issue: int,
    request: Mapping[str, Any],
) -> LifecycleDecision:
    """Use only maintained CURRENT and live-follow-up authority sources."""

    return _orchestrate_event(
        repository,
        delivery_issue,
        request,
        current_reader=publication.verify_current_lifecycle_authority,
        follow_up_verifier=follow_up.verify_live_follow_up,
    )
