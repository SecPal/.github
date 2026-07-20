#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Validate finite review plans and apply one exact guarded GitHub mutation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import pwd
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_HELPER = REPOSITORY_ROOT / "scripts/secpal-pr-review.py"
PLAN_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / ".agents/skills/secpal-pr-review/references/mutation-plan.schema.json"
)
REGISTRY_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / ".agents/skills/secpal-pr-review/references/repositories.schema.json"
)
REGISTRY_PATH = (
    REPOSITORY_ROOT
    / ".agents/skills/secpal-pr-review/references/repositories.json"
)
EXTERNAL_COMMAND_TIMEOUT_SECONDS = 30
LOCAL_VALIDATION_TIMEOUT_SECONDS = 600


def _load_evidence_helper() -> Any:
    spec = importlib.util.spec_from_file_location("secpal_pr_review_evidence_shared", EVIDENCE_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load accepted evidence helper: {EVIDENCE_HELPER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evidence = _load_evidence_helper()
ACCOUNT_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
LOCAL_VALIDATION_COMMAND_DIRECTORIES = (
    *evidence.TRUSTED_COMMAND_DIRECTORIES,
    ACCOUNT_HOME / ".local/bin",
    ACCOUNT_HOME / f"Library/Python/{sys.version_info.major}.{sys.version_info.minor}/bin",
)

CLASSIFICATIONS = (
    "VALID_ACTIONABLE",
    "INVALID_FALSE_OR_MISLEADING",
    "AMBIGUOUS_NEEDS_USER_DECISION",
    "INFORMATIONAL",
    "DUPLICATE",
    "OUTDATED_BUT_STILL_VALID",
    "OUTDATED_AND_OBSOLETE",
    "ALREADY_FIXED_ON_SNAPSHOT_HEAD",
    "SUPERSEDED",
    "OUTSIDE_PR_SCOPE",
    "CROSS_REPOSITORY",
    "CONFLICTING_REVIEWERS",
    "SECURITY_WEAKENING_SUGGESTION",
)
ALLOWED_OPERATION_KINDS = ("REACTION", "EVIDENCE_REPLY", "THREAD_RESOLUTION")
PROHIBITED_OPERATION_KINDS = (
    "REVIEW_REQUEST",
    "READY_TRANSITION",
    "LABEL",
    "ISSUE",
    "REVIEW_SUBMISSION",
    "MERGE",
    "AUTO_MERGE",
    "COMMENT_DELETE",
    "REVIEW_DISMISSAL",
    "BRANCH_WRITE",
)
SESSION_LIMITS = {
    "remediation_cycles": 2,
    "state_captures": 3,
    "holistic_audits": 1,
    "signed_commits": 2,
    "fast_forward_pushes": 2,
    "evidence_replies": 10,
}
P21_CONFIGURATION_KEYS = (
    "repository",
    "default_branch",
    "allowed_base_repositories",
    "reviewer_identities",
    "signature_policy",
    "check_policy",
    "maximum_api_calls",
    "maximum_items",
    "maximum_threads",
    "maximum_comments",
    "maximum_reactions",
)
RESOLVABLE_DISPOSITIONS = {
    "CORRECTED_AND_VERIFIED",
    "PROVEN_EXISTING_FIX",
    "DISPROVEN_WITH_EVIDENCE",
    "NON_ACTIONABLE",
    "DUPLICATE_OF_CANONICAL",
    "OBSOLETE_ON_CURRENT_HEAD",
    "SUPERSEDED_BY_CANONICAL",
    "REJECTED_SECURITY_WEAKENING",
}
RESOLVABLE_CLASSIFICATIONS = {
    "VALID_ACTIONABLE",
    "INVALID_FALSE_OR_MISLEADING",
    "INFORMATIONAL",
    "DUPLICATE",
    "OUTDATED_BUT_STILL_VALID",
    "OUTDATED_AND_OBSOLETE",
    "ALREADY_FIXED_ON_SNAPSHOT_HEAD",
    "SUPERSEDED",
    "SECURITY_WEAKENING_SUGGESTION",
}
REPLY_CLASSIFICATIONS = {
    "INVALID_FALSE_OR_MISLEADING",
    "OUTSIDE_PR_SCOPE",
    "CROSS_REPOSITORY",
    "SECURITY_WEAKENING_SUGGESTION",
}
STATUS_REPLY = re.compile(
    r"(?is)^\s*(?:fixed|addressed|resolved|done)(?:\s+in\s+[0-9a-f]{7,64})?[.!\s]*$|^\s*status\s*:.*$"
)
SECRET_VALUE = re.compile(
    r"(?i)(?:github_pat_|gh[opsu]_|-----BEGIN [A-Z ]*PRIVATE KEY-----|authorization\s*:\s*bearer)"
)
OID_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_COMMAND_NAME = re.compile(r"^(?:[A-Za-z0-9_.+-]+|\./[A-Za-z0-9_./+-]+)$")
DESTRUCTIVE_COMMANDS = {"rm", "rmdir", "shred", "mkfs", "dd", "sudo", "git-clean"}
SHELL_EXECUTABLES = {"sh", "bash", "zsh", "fish", "pwsh", "powershell", "cmd"}
DISPOSITION_POLICY = {
    "VALID_ACTIONABLE": {"PENDING", "CORRECTED_AND_VERIFIED", "PROVEN_EXISTING_FIX"},
    "INVALID_FALSE_OR_MISLEADING": {"DISPROVEN_WITH_EVIDENCE"},
    "AMBIGUOUS_NEEDS_USER_DECISION": {"USER_DECISION_REQUIRED"},
    "INFORMATIONAL": {"NON_ACTIONABLE"},
    "DUPLICATE": {"DUPLICATE_OF_CANONICAL"},
    "OUTDATED_BUT_STILL_VALID": {
        "PENDING",
        "CORRECTED_AND_VERIFIED",
        "PROVEN_EXISTING_FIX",
    },
    "OUTDATED_AND_OBSOLETE": {"OBSOLETE_ON_CURRENT_HEAD"},
    "ALREADY_FIXED_ON_SNAPSHOT_HEAD": {"PROVEN_EXISTING_FIX"},
    "SUPERSEDED": {"SUPERSEDED_BY_CANONICAL"},
    "OUTSIDE_PR_SCOPE": {"OUT_OF_SCOPE"},
    "CROSS_REPOSITORY": {"CROSS_REPOSITORY_BLOCKER"},
    "CONFLICTING_REVIEWERS": {"PENDING", "USER_DECISION_REQUIRED"},
    "SECURITY_WEAKENING_SUGGESTION": {"REJECTED_SECURITY_WEAKENING"},
}


class PlanError(ValueError):
    """The mutation plan is invalid or is not bound to supplied evidence."""


class RegistryError(ValueError):
    """The production registry is invalid or does not support a repository."""


class MutationBlocked(RuntimeError):
    """Current GitHub or remediation evidence blocks the intended mutation."""


class MutationFailure(RuntimeError):
    """One GitHub mutation failed; the invocation must end without retry."""


class ActionCommandFailure(RuntimeError):
    def __init__(self, arguments: list[str], returncode: int, stdout: str, stderr: str) -> None:
        self.arguments = list(arguments)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = evidence.redact_diagnostic(stderr or stdout or "GitHub command failed")
        super().__init__(f"gh exited {returncode}: {detail}")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _target_belongs_to_pull_request(url: Any, repository: str, number: int) -> bool:
    prefix = f"https://github.com/{repository}/pull/{number}"
    return isinstance(url, str) and (url == prefix or url.startswith(f"{prefix}#"))


def _read_json(path: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"Cannot load {label}: {evidence.redact_diagnostic(str(exc))}") from exc
    if not isinstance(value, dict):
        raise PlanError(f"{label} must be a JSON object")
    return value


def _validate_schema(value: dict[str, Any], path: Path, label: str, error_type: type[ValueError]) -> None:
    try:
        evidence.validate_against_authoritative_schema(value, path, label)
    except evidence.ContractError as exc:
        raise error_type(str(exc)) from exc


def _all_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)


def validate_session_state(session: dict[str, Any]) -> None:
    if not isinstance(session, dict):
        raise PlanError("session must be an object")
    for key, maximum in SESSION_LIMITS.items():
        value = session.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise PlanError(f"session counter {key} exceeds finite maximum {maximum}")
    for key in ("reaction_writes", "thread_resolutions"):
        value = session.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PlanError(f"session counter {key} must be a non-negative integer")
    if session.get("fast_forward_pushes", 0) > session.get("signed_commits", 0):
        raise PlanError("a fast-forward push cannot precede its signed remediation commit")
    if session.get("signed_commits", 0) > session.get("remediation_cycles", 0):
        raise PlanError("signed remediation commits cannot exceed completed remediation cycles")
    if session.get("remediation_cycles", 0) and session.get("holistic_audits", 0) != 1:
        raise PlanError("a remediation session requires exactly one holistic audit before readiness")


def determine_terminal_outcome(session: dict[str, Any]) -> str:
    """Return the finite contract outcome; technical classification remains agent-reasoned."""

    if session.get("remediation_cycles", 0) > SESSION_LIMITS["remediation_cycles"]:
        return "BLOCKED_CYCLE_LIMIT_REACHED"
    if not session.get("worktree_clean", False):
        return "BLOCKED_UNCLEAN_WORKTREE"
    if not session.get("head_matches", False):
        return "BLOCKED_HEAD_MOVED"
    if session.get("unexplained_commit", False):
        return "BLOCKED_UNEXPLAINED_COMMIT"
    if not session.get("signatures_valid", False):
        return "BLOCKED_INVALID_SIGNATURE"
    if (
        not session.get("snapshot_digest_matches", False)
        or not session.get("evidence_complete", False)
        or session.get("late_feedback_detected", False)
    ):
        return "BLOCKED_INCOMPLETE_REVIEW_STATE"
    if session.get("scope_requires_other_repository", False):
        return "BLOCKED_SCOPE_REQUIRES_OTHER_REPOSITORY"
    if session.get("mutation_failed", False):
        return "BLOCKED_MUTATION_FAILED"
    if session.get("push_failed", False):
        return "NOT_READY_FOR_MERGE"
    if not session.get("github_state_safe", False):
        return "BLOCKED_UNSAFE_GITHUB_STATE"
    if not session.get("actionable_findings", False) and not session.get(
        "unresolved_material_finding", False
    ):
        return "NO_ACTIONABLE_FINDINGS"
    if session.get("ci_state") != "SUCCESS":
        return "BLOCKED_FAILED_OR_PENDING_CI"
    if session.get("unresolved_material_finding", False):
        if session.get("remediation_cycles", 0) >= SESSION_LIMITS["remediation_cycles"]:
            return "BLOCKED_CYCLE_LIMIT_REACHED"
        return "BLOCKED_UNRESOLVED_MATERIAL_FINDING"
    if session.get("merge_ready_evidence", False):
        return "READY_FOR_USER_AUTHORIZED_SQUASH_MERGE"
    return "NOT_READY_FOR_MERGE"


def _validate_finding_semantics(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in findings:
        identifier = item["logical_finding_id"]
        if identifier in by_id:
            raise PlanError(f"duplicate logical finding ID: {identifier}")
        by_id[identifier] = item
        if item["classification"] not in CLASSIFICATIONS:
            raise PlanError(f"unsupported classification: {item['classification']}")
        if item["disposition"] not in DISPOSITION_POLICY[item["classification"]]:
            raise PlanError("logical finding disposition is invalid for its classification")
    for identifier, item in by_id.items():
        canonical = item["canonical_finding_id"]
        if item["classification"] in {"DUPLICATE", "SUPERSEDED"}:
            if not canonical or canonical == identifier or canonical not in by_id:
                raise PlanError(f"{item['classification']} finding requires a distinct canonical finding")
        elif canonical is not None:
            raise PlanError("only duplicate or superseded findings may name a canonical finding")
        if item["disposition"] in {
            "CORRECTED_AND_VERIFIED",
            "PROVEN_EXISTING_FIX",
        } and (item["commit_sha"] is None or not item["test_evidence"]):
            raise PlanError("fixed findings require commit and test evidence")
    for identifier in by_id:
        visited = {identifier}
        current = identifier
        while canonical := by_id[current]["canonical_finding_id"]:
            if canonical in visited:
                raise PlanError("canonical finding references contain a cycle")
            visited.add(canonical)
            current = canonical
    return by_id


def _validate_operation_semantics(
    plan: dict[str, Any],
    findings: dict[str, dict[str, Any]],
) -> None:
    operation_ids: set[str] = set()
    reacted_findings: set[str] = set()
    reacted_targets: set[str] = set()
    replied_findings: set[str] = set()
    resolved_threads: set[str] = set()
    reply_count = 0
    recorded_writes = {
        "REACTION": 0,
        "EVIDENCE_REPLY": 0,
        "THREAD_RESOLUTION": 0,
    }
    for operation in plan["operations"]:
        operation_id = operation["operation_id"]
        if operation_id in operation_ids:
            raise PlanError(f"duplicate operation ID: {operation_id}")
        operation_ids.add(operation_id)
        kind = operation["kind"]
        if kind not in ALLOWED_OPERATION_KINDS:
            raise PlanError(f"operation kind is prohibited: {kind}")
        mutation_identity = operation["applied_mutation_identity"]
        if mutation_identity is not None:
            if not mutation_identity:
                raise PlanError("recorded mutation identity must be non-empty")
            recorded_writes[kind] += 1
        finding_id = operation["logical_finding_id"]
        finding = findings.get(finding_id)
        if finding is None:
            raise PlanError(f"operation references unknown logical finding: {finding_id}")
        classification = operation["classification"]
        if classification != finding["classification"]:
            raise PlanError("operation classification differs from its logical finding")
        if kind == "REACTION":
            if finding_id in reacted_findings:
                raise PlanError("only one intended reaction is allowed per initial logical finding")
            reacted_findings.add(finding_id)
            if operation["target_node_id"] in reacted_targets:
                raise PlanError("only one intended reaction is allowed per snapshot target")
            reacted_targets.add(operation["target_node_id"])
            expected_reaction = {
                "VALID_ACTIONABLE": "THUMBS_UP",
                "INVALID_FALSE_OR_MISLEADING": "THUMBS_DOWN",
                "SECURITY_WEAKENING_SUGGESTION": "THUMBS_DOWN",
            }.get(classification)
            if (
                expected_reaction is None
                or operation["reaction"] != expected_reaction
                or operation["reply_body"] is not None
            ):
                raise PlanError("reaction does not match the classification policy")
            if operation["target_database_id"] is None:
                raise PlanError("reaction target requires a database ID")
            if operation["expected_current_state"]["target_type"] not in {
                "ISSUE_COMMENT",
                "PULL_REQUEST_REVIEW",
                "PULL_REQUEST_REVIEW_COMMENT",
            }:
                raise PlanError("reaction target type is not supported by the exact endpoint allowlist")
            if (
                classification == "SECURITY_WEAKENING_SUGGESTION"
                and not operation["expected_current_state"]["material_misunderstanding"]
            ):
                raise PlanError("security-weakening reaction requires a material misunderstanding")
            if operation["resolution_preconditions"] is not None:
                raise PlanError("reaction cannot carry resolution preconditions")
        elif kind == "EVIDENCE_REPLY":
            reply_count += 1
            if finding_id in replied_findings:
                raise PlanError("only one evidence reply is allowed per qualifying invalid finding")
            replied_findings.add(finding_id)
            body = operation["reply_body"]
            if (
                classification not in REPLY_CLASSIFICATIONS
                or operation["reaction"] is not None
                or not isinstance(body, str)
                or not body.strip()
                or not operation["expected_current_state"]["material_misunderstanding"]
                or not operation["expected_current_state"]["invalidity_non_obvious"]
            ):
                raise PlanError("evidence reply is not justified by its classification and expected state")
            if STATUS_REPLY.fullmatch(body):
                raise PlanError("redundant fixed or status reply is prohibited")
            if operation["target_database_id"] is None:
                raise PlanError("inline evidence reply requires a target database ID")
            if operation["expected_current_state"]["target_type"] != "PULL_REQUEST_REVIEW_COMMENT":
                raise PlanError("inline evidence replies require a pull-request review comment")
            if operation["resolution_preconditions"] is not None:
                raise PlanError("evidence reply cannot carry resolution preconditions")
        elif kind == "THREAD_RESOLUTION":
            thread_id = operation["parent_thread_id"]
            if (
                plan["created_for_state"] != "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE"
                or not thread_id
                or operation["target_node_id"] != thread_id
                or operation["target_database_id"] is not None
                or operation["reaction"] is not None
                or operation["reply_body"] is not None
                or classification not in RESOLVABLE_CLASSIFICATIONS
                or finding["disposition"] not in RESOLVABLE_DISPOSITIONS
            ):
                raise PlanError("thread resolution is not eligible under the classification policy")
            preconditions = operation["resolution_preconditions"]
            if not isinstance(preconditions, dict) or not all(preconditions.values()):
                raise PlanError("thread resolution requires every remediation precondition")
            if thread_id in resolved_threads:
                raise PlanError("only one resolution operation is allowed per eligible thread")
            resolved_threads.add(thread_id)
    if reply_count > SESSION_LIMITS["evidence_replies"]:
        raise PlanError("maximum evidence replies total is 10")
    expected_counters = {
        "reaction_writes": recorded_writes["REACTION"],
        "evidence_replies": recorded_writes["EVIDENCE_REPLY"],
        "thread_resolutions": recorded_writes["THREAD_RESOLUTION"],
    }
    for counter, recorded in expected_counters.items():
        if plan["session"][counter] != recorded:
            raise PlanError(
                f"session counter {counter} must equal its recorded mutation identities"
            )
    if len(reacted_findings) > len(findings):
        raise PlanError("reaction count exceeds initial logical finding count")
    if plan["created_for_state"] == "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES" and any(
        item["kind"] == "THREAD_RESOLUTION" for item in plan["operations"]
    ):
        raise PlanError("resolution operations require the final verified state")
    if plan["created_for_state"] == "RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE" and any(
        item["kind"] != "THREAD_RESOLUTION" and item["applied_mutation_identity"] is None
        for item in plan["operations"]
    ):
        raise PlanError("final-state plans may retain only recorded prior reaction or reply operations")


def _snapshot_evidence_ids(
    snapshot: dict[str, Any],
) -> tuple[
    set[str],
    set[int],
    set[str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    node_ids: set[str] = set()
    database_ids: set[int] = set()
    thread_ids = {thread["id"] for thread in snapshot["review_threads"]}
    actors: dict[str, dict[str, Any]] = {}
    targets: dict[str, dict[str, Any]] = {}
    for target_type, items in (
        ("PULL_REQUEST_REVIEW", snapshot["reviews"]),
        ("ISSUE_COMMENT", snapshot["conversation_comments"]),
    ):
        for item in items:
            node_ids.add(item["id"])
            database_ids.add(item["database_id"])
            actors[item["id"]] = item["author"]
            targets[item["id"]] = {
                "target_type": target_type,
                "database_id": item["database_id"],
                "parent_thread_id": None,
                "reply_to_id": None,
                "body_digest": sha256_text(item["body"]),
                "is_resolved": None,
                "is_outdated": False,
                "url": item["url"],
            }
    for thread in snapshot["review_threads"]:
        thread_actor = thread["comments"][0]["author"] if thread["comments"] else None
        if thread_actor is not None:
            actors[thread["id"]] = thread_actor
        targets[thread["id"]] = {
            "target_type": "PULL_REQUEST_REVIEW_THREAD",
            "database_id": None,
            "parent_thread_id": thread["id"],
            "reply_to_id": None,
            "body_digest": None,
            "is_resolved": thread["is_resolved"],
            "is_outdated": thread["is_outdated"],
            "url": thread["comments"][0]["url"] if thread["comments"] else None,
        }
        for item in thread["comments"]:
            node_ids.add(item["id"])
            database_ids.add(item["database_id"])
            actors[item["id"]] = item["author"]
            targets[item["id"]] = {
                "target_type": "PULL_REQUEST_REVIEW_COMMENT",
                "database_id": item["database_id"],
                "parent_thread_id": thread["id"],
                "reply_to_id": item["reply_to_id"],
                "body_digest": sha256_text(item["body"]),
                "is_resolved": thread["is_resolved"],
                "is_outdated": thread["is_outdated"],
                "url": item["url"],
            }
    return node_ids, database_ids, thread_ids, actors, targets


def _validate_snapshot_bindings(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    findings: dict[str, dict[str, Any]],
) -> None:
    node_ids, database_ids, thread_ids, actors, targets = _snapshot_evidence_ids(snapshot)
    commit_ids = {commit["oid"] for commit in snapshot["commits"]}
    for finding in findings.values():
        if not set(finding["source_node_ids"]) <= node_ids:
            raise PlanError("logical finding source node is absent from the bound snapshot")
        source_targets = [targets[node_id] for node_id in finding["source_node_ids"]]
        source_database_ids = {
            target["database_id"]
            for target in source_targets
            if target["database_id"] is not None
        }
        if set(finding["source_database_ids"]) != source_database_ids:
            raise PlanError("logical finding source IDs do not identify the same snapshot feedback")
        source_thread_ids = {target["parent_thread_id"] for target in source_targets}
        if source_thread_ids != {finding["parent_thread_id"]}:
            raise PlanError("logical finding sources do not belong to its declared thread")
        if finding["parent_thread_id"] is not None and finding["parent_thread_id"] not in thread_ids:
            raise PlanError("logical finding parent thread is absent from the bound snapshot")
        if finding["commit_sha"] is not None and finding["commit_sha"] not in commit_ids:
            raise PlanError("logical finding commit is absent from the bound snapshot")
    for operation in plan["operations"]:
        finding = findings[operation["logical_finding_id"]]
        if operation["kind"] == "THREAD_RESOLUTION":
            if operation["target_node_id"] not in thread_ids:
                raise PlanError("resolution target is absent from the bound snapshot")
            if finding["parent_thread_id"] != operation["target_node_id"]:
                raise PlanError("resolution target does not belong to its logical finding")
        elif (
            operation["target_node_id"] not in node_ids
            or operation["target_database_id"] not in database_ids
        ):
            raise PlanError("mutation target is absent from the bound snapshot")
        elif operation["target_node_id"] not in finding["source_node_ids"]:
            raise PlanError("mutation target does not belong to its logical finding")
        snapshot_target = targets[operation["target_node_id"]]
        if (
            operation["kind"] == "EVIDENCE_REPLY"
            and snapshot_target["reply_to_id"] is not None
        ):
            raise PlanError("inline evidence replies require a top-level review comment")
        if not _target_belongs_to_pull_request(
            snapshot_target["url"],
            plan["repository"],
            plan["pull_request_number"],
        ):
            raise PlanError("mutation target does not belong to the bound pull request")
        if (
            operation["target_database_id"] != snapshot_target["database_id"]
            or operation["parent_thread_id"] != snapshot_target["parent_thread_id"]
        ):
            raise PlanError("mutation target identity differs from the bound snapshot")
        expected_state = operation["expected_current_state"]
        if any(
            expected_state[key] != snapshot_target[key]
            for key in ("target_type", "body_digest", "is_resolved", "is_outdated")
        ):
            raise PlanError("mutation expected current state differs from immutable snapshot state")
        expected_actor = operation["expected_source_actor_identity"]
        source_actor = actors.get(operation["target_node_id"])
        if source_actor is None or any(
            source_actor.get(key) != expected_actor.get(key)
            for key in ("login", "node_id", "database_id")
        ):
            raise PlanError("expected source actor identity differs from the bound snapshot")
    if plan["session"]["reaction_writes"] > len(findings):
        raise PlanError("reaction writes exceed initial logical finding count")
    if plan["session"]["thread_resolutions"] > len(thread_ids):
        raise PlanError("thread resolution writes exceed eligible initial thread count")


def validate_plan(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    configuration: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise PlanError("mutation plan must be a JSON object")
    _validate_schema(plan, PLAN_SCHEMA_PATH, "mutation_plan", PlanError)
    try:
        evidence.validate_config(configuration)
        evidence.validate_snapshot(snapshot)
    except evidence.ContractError as exc:
        raise PlanError(f"accepted P2.1 evidence validation failed: {exc}") from exc
    try:
        registered = select_repository(load_registry(), plan["repository"])
    except RegistryError as exc:
        raise PlanError(f"production registry rejected the mutation plan: {exc}") from exc
    registered_configuration = _package_21_configuration(registered)
    if configuration != registered_configuration:
        raise PlanError("repository configuration differs from the production registry entry")
    try:
        verified_evidence = evidence.verify_snapshot_evidence(snapshot, configuration)
    except (evidence.ContractError, evidence.BlockedError) as exc:
        raise PlanError(f"accepted P2.1 evidence verification failed: {exc}") from exc
    if not verified_evidence["evidence_verified"]:
        raise PlanError("accepted P2.1 evidence verification is blocked")
    if plan["repository"] != configuration["repository"] or plan["repository"] != snapshot["repository"]["name_with_owner"]:
        raise PlanError("mutation plan repository identity does not match supplied evidence")
    if plan["pull_request_number"] != snapshot["pull_request"]["number"]:
        raise PlanError("mutation plan pull request identity does not match supplied evidence")
    if plan["snapshot_digest"] != snapshot["snapshot_digest"]:
        raise PlanError("mutation plan snapshot digest does not match supplied evidence")
    if plan["expected_head_sha"] != snapshot["pull_request"]["head_oid_after"]:
        raise PlanError("mutation plan expected head does not match supplied evidence")
    if (
        plan["created_for_state"] == "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES"
        and plan["initial_snapshot_digest"] != plan["snapshot_digest"]
    ):
        raise PlanError("initial mutation plan must bind to the immutable initial snapshot digest")
    if any(SECRET_VALUE.search(value) for value in _all_strings(plan)):
        raise PlanError("mutation plan must not contain credentials or secrets")
    validate_session_state(plan["session"])
    if plan["cycle_number"] != plan["session"]["remediation_cycles"]:
        raise PlanError("plan cycle number must match the finite session counter")
    findings = _validate_finding_semantics(plan["findings"])
    _validate_operation_semantics(plan, findings)
    _validate_snapshot_bindings(plan, snapshot, findings)
    return copy.deepcopy(plan)


def _validate_command(command: dict[str, Any]) -> None:
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item for item in argv):
        raise RegistryError("validation command argv must be a non-empty argument array")
    executable = Path(argv[0]).name
    executable_path = Path(argv[0])
    if (
        not SAFE_COMMAND_NAME.fullmatch(argv[0])
        or executable_path.is_absolute()
        or ".." in executable_path.parts
        or executable in SHELL_EXECUTABLES
        or executable in {"git", "gh", "npx"}
    ):
        raise RegistryError("validation command must not use a shell or dynamic executable")
    if executable in DESTRUCTIVE_COMMANDS or any(
        item in {"--force", "--delete", "--hard", "deploy", "migrate:fresh"}
        or item.startswith(("deploy:", "publish:"))
        for item in argv[1:]
    ):
        raise RegistryError("destructive validation command is prohibited")
    if (executable in {"python", "python3"} and "-c" in argv[1:]) or (
        executable in {"node", "ruby", "perl"} and "-e" in argv[1:]
    ):
        raise RegistryError("dynamic validation code is prohibited")
    if executable == "npm" and (len(argv) < 3 or argv[1] != "run"):
        raise RegistryError("registry npm commands must name a checked-in package script")
    working_directory = command.get("working_directory")
    if not isinstance(working_directory, str) or not working_directory or Path(working_directory).is_absolute() or ".." in Path(working_directory).parts:
        raise RegistryError("validation working directory must stay repository-relative")
    if not isinstance(command.get("purpose"), str) or not command["purpose"].strip():
        raise RegistryError("validation command purpose is required")


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise RegistryError("repository registry must be a JSON object")
    _validate_schema(registry, REGISTRY_SCHEMA_PATH, "workflow_registry", RegistryError)
    repositories: set[str] = set()
    for entry in registry["repositories"]:
        repository = entry["repository"]
        if not REPOSITORY_PATTERN.fullmatch(repository):
            raise RegistryError(f"invalid repository identity: {repository}")
        if repository in repositories:
            raise RegistryError(f"duplicate repository registry entry: {repository}")
        repositories.add(repository)
        p21_configuration = _package_21_configuration(entry)
        try:
            evidence.validate_config(p21_configuration)
        except evidence.ContractError as exc:
            raise RegistryError(f"invalid Package 2.1 configuration for {repository}: {exc}") from exc
        for command in (*entry["focused_validation"], *entry["required_local_validation"]):
            _validate_command(command)
        if not entry["required_local_validation"] and not entry["manual_gates"]:
            raise RegistryError("incomplete validation requires an explicit manual gate")
        if set(entry["unsupported_operations"]) != set(PROHIBITED_OPERATION_KINDS):
            raise RegistryError("unsupported operations must retain every prohibited capability")
    return copy.deepcopy(registry)


def _package_21_configuration(entry: dict[str, Any]) -> dict[str, Any]:
    configuration = {
        key: copy.deepcopy(entry[key])
        for key in P21_CONFIGURATION_KEYS
    }
    configuration["schema_version"] = "1.0"
    return configuration


def load_registry(path: str | None = None) -> dict[str, Any]:
    registry = _read_json(path or str(REGISTRY_PATH), "workflow repository registry")
    return validate_registry(registry)


def select_repository(registry: dict[str, Any], repository: str) -> dict[str, Any]:
    validated = validate_registry(registry)
    for entry in validated["repositories"]:
        if entry["repository"] == repository:
            return entry
    raise RegistryError(f"unsupported repository: {repository}")


def _validation_executable(
    command: dict[str, Any],
    working_directory: Path,
    repository_root: Path,
) -> str:
    executable = command["argv"][0]
    if executable.startswith("./"):
        try:
            candidate = (working_directory / executable).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise RegistryError("registered validation executable is unavailable") from exc
        if (
            candidate != repository_root
            and repository_root not in candidate.parents
        ) or not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise RegistryError("registered validation executable is unsafe or not executable")
        return str(candidate)
    for directory in LOCAL_VALIDATION_COMMAND_DIRECTORIES:
        candidate = directory / executable
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RegistryError("registered validation executable is unavailable")


def _run_registered_validations(
    repository: dict[str, Any], repository_root: Path
) -> bool:
    """Run every checked-in validation command once, without a shell or diagnostic output."""

    repository_root = repository_root.resolve()
    if not repository_root.is_dir():
        return False
    commands = (*repository["focused_validation"], *repository["required_local_validation"])
    for command in commands:
        _validate_command(command)
        working_directory = (repository_root / command["working_directory"]).resolve()
        if working_directory != repository_root and repository_root not in working_directory.parents:
            return False
        try:
            executable = _validation_executable(
                command, working_directory, repository_root
            )
            completed = subprocess.run(
                [executable, *command["argv"][1:]],
                cwd=working_directory,
                env=evidence.command_environment("git"),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=LOCAL_VALIDATION_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired, RegistryError):
            return False
        if completed.returncode != 0:
            return False
    return True


CURRENT_MUTATION_TARGET_QUERY = r"""
query CurrentMutationTarget($owner:String!, $name:String!, $number:Int!, $targetNodeId:ID!, $threadNodeId:ID!) {
  viewer { id databaseId login }
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id headRefOid state }
  }
  node(id:$targetNodeId) {
    __typename
    ... on IssueComment {
      id databaseId body url
      author {
        login
        ... on User { id databaseId }
        ... on Bot { id databaseId }
        ... on Organization { id databaseId }
        ... on Mannequin { id databaseId }
      }
      reactions(first:100) { nodes { id databaseId content user { id databaseId login } } pageInfo { hasNextPage } }
    }
    ... on PullRequestReviewComment {
      id databaseId body url
      replyTo { databaseId }
      author {
        login
        ... on User { id databaseId }
        ... on Bot { id databaseId }
        ... on Organization { id databaseId }
        ... on Mannequin { id databaseId }
      }
      reactions(first:100) { nodes { id databaseId content user { id databaseId login } } pageInfo { hasNextPage } }
    }
    ... on PullRequestReview {
      id databaseId body url
      author {
        login
        ... on User { id databaseId }
        ... on Bot { id databaseId }
        ... on Organization { id databaseId }
        ... on Mannequin { id databaseId }
      }
      reactions(first:100) { nodes { id databaseId content user { id databaseId login } } pageInfo { hasNextPage } }
    }
    ... on PullRequestReviewThread { id isResolved isOutdated }
  }
  thread: node(id:$threadNodeId) {
    ... on PullRequestReviewThread {
      id isResolved isOutdated
      comments(first:100) {
        nodes {
          id databaseId body url
          replyTo { databaseId }
          author {
            login
            ... on User { id databaseId }
            ... on Bot { id databaseId }
            ... on Organization { id databaseId }
            ... on Mannequin { id databaseId }
          }
        }
        pageInfo { hasNextPage }
      }
    }
  }
}
"""
RESOLVE_REVIEW_THREAD_MUTATION = r"""
mutation ResolveReviewThread($threadId:ID!) {
  resolveReviewThread(input:{threadId:$threadId}) { thread { id isResolved } }
}
"""
ADD_REACTION_MUTATION = r"""
mutation AddReaction($subjectId:ID!, $content:ReactionContent!) {
  addReaction(input:{subjectId:$subjectId, content:$content}) {
    reaction { id databaseId content user { id databaseId login } }
    subject { id }
  }
}
"""
VIEWER_IDENTITY_QUERY = r"""
query ViewerIdentity {
  viewer { id databaseId login }
}
"""


def _graphql_arguments(query: str, variables: dict[str, Any]) -> list[str]:
    arguments = ["gh", "api", "--hostname", "github.com", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        arguments.extend([flag, f"{key}={value}"])
    return arguments


def _validate_action_command(arguments: list[str]) -> None:
    if arguments[:4] != ["gh", "api", "--hostname", "github.com"]:
        raise MutationBlocked("GitHub command must use the exact pinned api host")
    if len(arguments) > 4 and arguments[4] == "graphql":
        if len(arguments) < 7 or arguments[5] != "-f" or not arguments[6].startswith("query="):
            raise MutationBlocked("GraphQL command does not match an allowlisted shape")
        query = arguments[6].split("=", 1)[1]
        if query not in {
            CURRENT_MUTATION_TARGET_QUERY,
            ADD_REACTION_MUTATION,
            RESOLVE_REVIEW_THREAD_MUTATION,
            VIEWER_IDENTITY_QUERY,
        }:
            raise MutationBlocked("GraphQL document is not exactly allowlisted")
        variable_arguments = arguments[7:]
        if len(variable_arguments) % 2:
            raise MutationBlocked("GraphQL variables must be exact flag/value pairs")
        variables: dict[str, tuple[str, str]] = {}
        for index in range(0, len(variable_arguments), 2):
            flag, assignment = variable_arguments[index : index + 2]
            if flag not in {"-f", "-F"} or "=" not in assignment:
                raise MutationBlocked("GraphQL variables must be exact flag/value pairs")
            key, value = assignment.split("=", 1)
            if key in variables:
                raise MutationBlocked("duplicate GraphQL variable is prohibited")
            variables[key] = (flag, value)
        if query == VIEWER_IDENTITY_QUERY:
            expected_variables = {}
        elif query == RESOLVE_REVIEW_THREAD_MUTATION:
            expected_variables = {"threadId": "-f"}
        elif query == ADD_REACTION_MUTATION:
            expected_variables = {"subjectId": "-f", "content": "-f"}
        else:
            expected_variables = {
                "owner": "-f",
                "name": "-f",
                "number": "-F",
                "targetNodeId": "-f",
                "threadNodeId": "-f",
            }
        if set(variables) != set(expected_variables) or any(
            variables[key][0] != flag or not variables[key][1]
            for key, flag in expected_variables.items()
        ):
            raise MutationBlocked("GraphQL variables do not match the allowlisted document")
        return
    if len(arguments) != 11 or arguments[5:7] != ["--method", "POST"]:
        raise MutationBlocked("REST mutation must use the exact POST command shape")
    endpoint = arguments[4]
    repository = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    reaction_endpoint = re.fullmatch(
        rf"repos/{repository}/(?:issues/comments|pulls/comments)/[1-9][0-9]*/reactions",
        endpoint,
    )
    reply_endpoint = re.fullmatch(rf"repos/{repository}/pulls/[1-9][0-9]*/comments", endpoint)
    if not reaction_endpoint and not reply_endpoint:
        raise MutationBlocked("REST endpoint is not exactly allowlisted")
    if reaction_endpoint:
        if arguments[7:10] != [
            "--header",
            "Accept: application/vnd.github+json",
            "-f",
        ] or arguments[10] not in {"content=+1", "content=-1"}:
            raise MutationBlocked("reaction arguments are not exactly allowlisted")
    if reply_endpoint:
        if (
            arguments[7] != "-f"
            or not arguments[8].startswith("body=")
            or arguments[9] != "-F"
            or not re.fullmatch(r"in_reply_to=[1-9][0-9]*", arguments[10])
        ):
            raise MutationBlocked("inline reply arguments are not exactly allowlisted")


class ActionCommandRunner:
    """Run one exact GitHub read or mutation without shell, retry, or polling."""

    def __init__(self, executable_path: str | None = None) -> None:
        if executable_path is None:
            try:
                self.executable_path = evidence.resolve_trusted_executable("gh")
            except evidence.CommandPolicyError as exc:
                raise MutationBlocked("trusted GitHub CLI is unavailable") from exc
        else:
            path = Path(executable_path)
            if not path.is_absolute() or path.name != "gh" or not path.is_file() or not os.access(path, os.X_OK):
                raise MutationBlocked("invalid explicit gh executable")
            self.executable_path = str(path.resolve())

    def run(self, arguments: list[str]) -> dict[str, Any]:
        _validate_action_command(arguments)
        try:
            completed = subprocess.run(
                [self.executable_path, *arguments[1:]],
                check=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=evidence.command_environment("gh"),
                timeout=EXTERNAL_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise ActionCommandFailure(arguments, 124, "", "gh command timed out") from exc
        if completed.returncode != 0:
            raise ActionCommandFailure(arguments, completed.returncode, completed.stdout, completed.stderr)
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MutationFailure("GitHub returned malformed JSON") from exc
        if not isinstance(value, dict):
            raise MutationFailure("GitHub returned a non-object response")
        return value


def _actor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"login": None, "node_id": None, "database_id": None}
    database_id = value.get("databaseId", value.get("database_id"))
    return {
        "login": value.get("login"),
        "node_id": value.get("id", value.get("node_id")),
        "database_id": database_id if isinstance(database_id, int) and not isinstance(database_id, bool) else None,
    }


class LiveGitHub:
    def __init__(self, runner: ActionCommandRunner | None = None) -> None:
        self.runner = runner or ActionCommandRunner()

    def inspect_actor(self) -> dict[str, Any]:
        try:
            value = self.runner.run(_graphql_arguments(VIEWER_IDENTITY_QUERY, {}))
            actor = _actor(value["data"]["viewer"])
        except (ActionCommandFailure, KeyError, MutationBlocked, TypeError) as exc:
            raise MutationFailure(str(exc)) from exc
        if any(actor.get(key) is None for key in ("login", "node_id", "database_id")):
            raise MutationBlocked("authenticated actor identity is incomplete")
        return actor

    def read_current_state(self, plan: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
        owner, name = plan["repository"].split("/", 1)
        thread_id = operation["parent_thread_id"] or operation["target_node_id"]
        try:
            payload = self.runner.run(
                _graphql_arguments(
                    CURRENT_MUTATION_TARGET_QUERY,
                    {
                        "owner": owner,
                        "name": name,
                        "number": plan["pull_request_number"],
                        "targetNodeId": operation["target_node_id"],
                        "threadNodeId": thread_id,
                    },
                )
            )
        except (ActionCommandFailure, MutationBlocked) as exc:
            raise MutationFailure(str(exc)) from exc
        try:
            data = payload["data"]
            pull_request = data["repository"]["pullRequest"]
            target = data["node"]
        except (KeyError, TypeError) as exc:
            raise MutationBlocked("current GitHub target state is incomplete") from exc
        if not isinstance(target, dict) or not isinstance(pull_request, dict):
            raise MutationBlocked("current GitHub target is unavailable")
        target_type = {
            "IssueComment": "ISSUE_COMMENT",
            "PullRequestReview": "PULL_REQUEST_REVIEW",
            "PullRequestReviewComment": "PULL_REQUEST_REVIEW_COMMENT",
            "PullRequestReviewThread": "PULL_REQUEST_REVIEW_THREAD",
        }.get(target.get("__typename"))
        if target_type is None:
            raise MutationBlocked("current GitHub target type is unsupported")
        thread = data.get("thread")
        if not isinstance(thread, dict):
            thread = target.get("pullRequestReviewThread")
        if not isinstance(thread, dict):
            thread = target if target_type == "PULL_REQUEST_REVIEW_THREAD" else {}
        reactions_connection = target.get("reactions") or {}
        comments_connection = thread.get("comments") or {}
        if reactions_connection.get("pageInfo", {}).get("hasNextPage") or comments_connection.get("pageInfo", {}).get("hasNextPage"):
            raise MutationBlocked("current target state exceeds the single bounded idempotency read")
        thread_comments = [
            item for item in comments_connection.get("nodes", []) if isinstance(item, dict)
        ]
        target_author = target.get("author")
        target_url = target.get("url")
        if target_type == "PULL_REQUEST_REVIEW_THREAD" and thread_comments:
            target_author = thread_comments[0].get("author")
            target_url = thread_comments[0].get("url")
        return {
            "head_sha": pull_request.get("headRefOid"),
            "pr_state": pull_request.get("state"),
            "actor": _actor(target_author),
            "viewer": _actor(data.get("viewer")),
            "target": {
                "node_id": target.get("id"),
                "database_id": target.get("databaseId"),
                "parent_thread_id": thread.get("id") or operation["parent_thread_id"],
                "target_type": target_type,
                "url": target_url,
                "body_digest": sha256_text(target.get("body", "")) if "body" in target else None,
                "is_resolved": thread.get("isResolved"),
                "is_outdated": bool(thread.get("isOutdated", False)),
                "reply_to_database_id": (
                    target.get("replyTo", {}).get("databaseId")
                    if isinstance(target.get("replyTo"), dict)
                    else None
                ),
                "reactions": [
                    {
                        "mutation_id": item.get("id") or str(item.get("databaseId") or ""),
                        "content": item.get("content"),
                        "actor": _actor(item.get("user")),
                    }
                    for item in reactions_connection.get("nodes", [])
                    if isinstance(item, dict)
                ],
                "replies": [
                    {
                        "mutation_id": item.get("id"),
                        "body": item.get("body"),
                        "actor": _actor(item.get("author")),
                        "reply_to_database_id": (
                            item.get("replyTo", {}).get("databaseId")
                            if isinstance(item.get("replyTo"), dict)
                            else None
                        ),
                    }
                    for item in thread_comments
                    if item.get("id") != operation["target_node_id"]
                ],
                "thread_comments": [
                    {
                        "node_id": item.get("id"),
                        "body_digest": sha256_text(item.get("body", "")),
                        "actor": _actor(item.get("author")),
                    }
                    for item in thread_comments
                ],
            },
        }

    def apply_reaction(self, plan: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
        target_type = operation["expected_current_state"]["target_type"]
        if target_type == "PULL_REQUEST_REVIEW":
            try:
                value = self.runner.run(
                    _graphql_arguments(
                        ADD_REACTION_MUTATION,
                        {
                            "subjectId": operation["target_node_id"],
                            "content": operation["reaction"],
                        },
                    )
                )
                reaction = value["data"]["addReaction"]["reaction"]
                subject = value["data"]["addReaction"]["subject"]
            except (ActionCommandFailure, KeyError, MutationBlocked, TypeError) as exc:
                raise MutationFailure(str(exc)) from exc
            if (
                subject.get("id") != operation["target_node_id"]
                or reaction.get("content") != operation["reaction"]
                or not _same_actor(_actor(reaction.get("user")), operation["expected_actor_identity"])
            ):
                raise MutationFailure("GitHub reaction response identity or content changed")
            return {
                "mutation_id": reaction.get("id") or str(reaction.get("databaseId") or ""),
                "content": reaction.get("content"),
            }
        namespace = "issues/comments" if target_type == "ISSUE_COMMENT" else "pulls/comments"
        endpoint = f"repos/{plan['repository']}/{namespace}/{operation['target_database_id']}/reactions"
        content = "+1" if operation["reaction"] == "THUMBS_UP" else "-1"
        try:
            value = self.runner.run(
                [
                    "gh", "api", "--hostname", "github.com", endpoint,
                    "--method", "POST",
                    "--header", "Accept: application/vnd.github+json",
                    "-f", f"content={content}",
                ]
            )
        except (ActionCommandFailure, MutationBlocked) as exc:
            raise MutationFailure(str(exc)) from exc
        if value.get("content") != content:
            raise MutationFailure("GitHub reaction response content changed")
        return {"mutation_id": value.get("node_id") or str(value.get("id") or ""), "content": content}

    def apply_reply(self, plan: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
        endpoint = f"repos/{plan['repository']}/pulls/{plan['pull_request_number']}/comments"
        try:
            value = self.runner.run(
                [
                    "gh", "api", "--hostname", "github.com", endpoint,
                    "--method", "POST",
                    "-f", f"body={operation['reply_body']}",
                    "-F", f"in_reply_to={operation['target_database_id']}",
                ]
            )
        except (ActionCommandFailure, MutationBlocked) as exc:
            raise MutationFailure(str(exc)) from exc
        actor = value.get("user")
        actual_actor = {
            "login": actor.get("login") if isinstance(actor, dict) else None,
            "node_id": actor.get("node_id") if isinstance(actor, dict) else None,
            "database_id": actor.get("id") if isinstance(actor, dict) else None,
        }
        if (
            value.get("body") != operation["reply_body"]
            or value.get("in_reply_to_id") != operation["target_database_id"]
            or not _same_actor(actual_actor, operation["expected_actor_identity"])
        ):
            raise MutationFailure("GitHub reply response identity, parent, or body changed")
        return {"mutation_id": value.get("node_id") or str(value.get("id") or "")}

    def apply_resolution(self, _plan: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
        try:
            value = self.runner.run(
                _graphql_arguments(
                    RESOLVE_REVIEW_THREAD_MUTATION,
                    {"threadId": operation["target_node_id"]},
                )
            )
            thread = value["data"]["resolveReviewThread"]["thread"]
        except (ActionCommandFailure, KeyError, MutationBlocked, TypeError) as exc:
            raise MutationFailure(str(exc)) from exc
        if thread.get("id") != operation["target_node_id"] or thread.get("isResolved") is not True:
            raise MutationFailure("GitHub resolution response identity or state changed")
        return {"mutation_id": thread.get("id"), "is_resolved": thread.get("isResolved")}


def _same_actor(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == expected.get(key) for key in ("login", "node_id", "database_id"))


def _terminal_mutation_blocker(session: dict[str, Any]) -> str | None:
    hard_blockers = (
        (not session["worktree_clean"], "BLOCKED_UNCLEAN_WORKTREE"),
        (not session["head_matches"], "BLOCKED_HEAD_MOVED"),
        (session["unexplained_commit"], "BLOCKED_UNEXPLAINED_COMMIT"),
        (not session["signatures_valid"], "BLOCKED_INVALID_SIGNATURE"),
        (
            not session["snapshot_digest_matches"]
            or not session["evidence_complete"]
            or session["late_feedback_detected"],
            "BLOCKED_INCOMPLETE_REVIEW_STATE",
        ),
        (session["scope_requires_other_repository"], "BLOCKED_SCOPE_REQUIRES_OTHER_REPOSITORY"),
        (session["mutation_failed"], "BLOCKED_MUTATION_FAILED"),
        (session["push_failed"], "NOT_READY_FOR_MERGE"),
        (not session["github_state_safe"], "BLOCKED_UNSAFE_GITHUB_STATE"),
    )
    return next((outcome for blocked, outcome in hard_blockers if blocked), None)


def _snapshot_thread_comments(snapshot: dict[str, Any], thread_id: str) -> list[dict[str, Any]]:
    thread = next(
        (item for item in snapshot["review_threads"] if item["id"] == thread_id),
        None,
    )
    if thread is None:
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: resolution thread left the snapshot")
    return [
        {
            "node_id": comment["id"],
            "body_digest": sha256_text(comment["body"]),
            "actor": {
                key: comment["author"].get(key)
                for key in ("login", "node_id", "database_id")
            },
        }
        for comment in thread["comments"]
    ]


def _verify_current_state(
    plan: dict[str, Any],
    operation: dict[str, Any],
    current: dict[str, Any],
    snapshot: dict[str, Any],
) -> tuple[str, str] | None:
    if current.get("head_sha") != plan["expected_head_sha"]:
        raise MutationBlocked("BLOCKED_HEAD_MOVED: current PR head differs from the mutation plan")
    if current.get("pr_state") != "OPEN":
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: pull request is not open")
    if not _same_actor(current.get("actor", {}), operation["expected_source_actor_identity"]):
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: source actor identity changed")
    viewer = current.get("viewer")
    if not isinstance(viewer, dict) or any(
        viewer.get(key) is None for key in ("login", "node_id", "database_id")
    ):
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: authenticated actor identity is incomplete")
    if not _same_actor(viewer, operation["expected_actor_identity"]):
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: authenticated actor identity changed")
    target = current.get("target")
    if not isinstance(target, dict):
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: mutation target is unavailable")
    if (
        target.get("node_id") != operation["target_node_id"]
        or (
            operation["target_database_id"] is not None
            and target.get("database_id") != operation["target_database_id"]
        )
        or target.get("parent_thread_id") != operation["parent_thread_id"]
        or target.get("target_type") != operation["expected_current_state"]["target_type"]
    ):
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: mutation target identity changed")
    if not _target_belongs_to_pull_request(
        target.get("url"),
        plan["repository"],
        plan["pull_request_number"],
    ):
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: target pull request changed")
    for key in ("body_digest", "is_outdated"):
        if target.get(key) != operation["expected_current_state"][key]:
            raise MutationBlocked(f"BLOCKED_UNSAFE_GITHUB_STATE: target {key} changed")
    if operation["kind"] == "THREAD_RESOLUTION":
        if target.get("thread_comments") != _snapshot_thread_comments(
            snapshot, operation["target_node_id"]
        ):
            raise MutationBlocked(
                "BLOCKED_INCOMPLETE_REVIEW_STATE: thread comments changed after the final snapshot"
            )
        if target.get("is_resolved") is True:
            if operation["applied_mutation_identity"] == operation["target_node_id"]:
                return "ALREADY_APPLIED", operation["target_node_id"]
            raise MutationBlocked(
                "BLOCKED_UNSAFE_GITHUB_STATE: thread resolution state changed"
            )
    if target.get("is_resolved") is not operation["expected_current_state"]["is_resolved"]:
        raise MutationBlocked("BLOCKED_UNSAFE_GITHUB_STATE: thread resolution state changed")
    if operation["kind"] == "REACTION":
        for item in target.get("reactions", []):
            if item.get("content") == operation["reaction"] and _same_actor(
                item.get("actor", {}), viewer
            ):
                return "ALREADY_APPLIED", item.get("mutation_id") or operation["target_node_id"]
    if operation["kind"] == "EVIDENCE_REPLY":
        if target.get("reply_to_database_id") is not None:
            raise MutationBlocked(
                "BLOCKED_UNSAFE_GITHUB_STATE: evidence reply target is not a top-level review comment"
            )
        for item in target.get("replies", []):
            if (
                item.get("reply_to_database_id") == operation["target_database_id"]
                and item.get("body") == operation["reply_body"]
                and _same_actor(item.get("actor", {}), viewer)
            ):
                return "ALREADY_APPLIED", item.get("mutation_id") or operation["target_node_id"]
    return None


def _verify_retained_feedback_mutations(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    github: Any,
) -> set[str]:
    """Verify every retained reaction or reply against its exact live target."""

    verified: set[str] = set()
    for operation in plan["operations"]:
        identity = operation["applied_mutation_identity"]
        if operation["kind"] not in {"REACTION", "EVIDENCE_REPLY"} or identity is None:
            continue
        current = github.read_current_state(plan, operation)
        current_status = _verify_current_state(plan, operation, current, snapshot)
        if current_status is None or current_status[1] != identity:
            raise MutationBlocked(
                "BLOCKED_UNSAFE_GITHUB_STATE: retained mutation identity is absent or changed"
            )
        verified.add(identity)
    return verified


def execute_operation(
    plan: dict[str, Any],
    operation_id: str,
    snapshot: dict[str, Any],
    configuration: dict[str, Any],
    github: Any,
    *,
    apply: bool,
    resolution_evidence: dict[str, bool] | None,
) -> dict[str, Any]:
    validated = validate_plan(plan, snapshot, configuration)
    operation = next(
        (item for item in validated["operations"] if item["operation_id"] == operation_id),
        None,
    )
    if operation is None:
        raise PlanError(f"unknown operation ID: {operation_id}")
    terminal_blocker = _terminal_mutation_blocker(validated["session"])
    if terminal_blocker is not None:
        raise MutationBlocked(f"{terminal_blocker}: session already records a terminal blocker")
    current = github.read_current_state(validated, operation)
    current_status = _verify_current_state(validated, operation, current, snapshot)
    recorded_identity = operation["applied_mutation_identity"]
    if recorded_identity is not None:
        if current_status is None or current_status[1] != recorded_identity:
            raise MutationBlocked(
                "BLOCKED_UNSAFE_GITHUB_STATE: recorded mutation identity is absent or changed"
            )
        return {
            "status": "ALREADY_APPLIED_RECORDED",
            "operation_id": operation_id,
            "kind": operation["kind"],
            "mutation_identity": recorded_identity,
            "retry_performed": False,
        }
    if current_status is not None:
        status, mutation_identity = current_status
        return {
            "status": status,
            "operation_id": operation_id,
            "kind": operation["kind"],
            "mutation_identity": mutation_identity,
            "retry_performed": False,
        }
    if not apply:
        return {
            "status": "VALIDATED_NO_MUTATION",
            "operation_id": operation_id,
            "kind": operation["kind"],
            "mutation_identity": None,
            "retry_performed": False,
        }
    if operation["kind"] == "THREAD_RESOLUTION":
        required = {
            "local_verified",
            "final_evidence_verified",
            "no_late_feedback",
            "all_threads_classified",
            "registered_validation_verified",
        }
        if not isinstance(resolution_evidence, dict) or not all(
            resolution_evidence.get(key) is True for key in required
        ):
            raise MutationBlocked("BLOCKED_UNRESOLVED_MATERIAL_FINDING: resolution evidence is incomplete")
    method = {
        "REACTION": github.apply_reaction,
        "EVIDENCE_REPLY": github.apply_reply,
        "THREAD_RESOLUTION": github.apply_resolution,
    }[operation["kind"]]
    result = method(validated, operation)
    mutation_identity = result.get("mutation_id")
    if not isinstance(mutation_identity, str) or not mutation_identity:
        raise MutationFailure("GitHub mutation returned no stable identity")
    return {
        "status": "APPLIED",
        "operation_id": operation_id,
        "kind": operation["kind"],
        "mutation_identity": mutation_identity,
        "retry_performed": False,
    }


def _thread_feedback(snapshot: dict[str, Any]) -> dict[str, list[tuple[str, str, str | None]]]:
    return {
        thread["id"]: [
            (comment["id"], comment["body"], comment["author"]["login"])
            for comment in thread["comments"]
        ]
        for thread in snapshot["review_threads"]
    }


def _top_level_feedback(snapshot: dict[str, Any], key: str) -> list[tuple[Any, ...]]:
    if key == "reviews":
        return [
            (
                item["id"],
                item["body"],
                item["author"]["login"],
                item["state"],
                item["commit_oid"],
            )
            for item in snapshot[key]
        ]
    return [
        (item["id"], item["body"], item["author"]["login"], item["updated_at"])
        for item in snapshot[key]
    ]


def _reaction_feedback(
    snapshot: dict[str, Any],
) -> dict[str, set[tuple[str, str, str | None, str | None, int | None]]]:
    targets: list[dict[str, Any]] = [snapshot["pull_request"]]
    targets.extend(snapshot["reviews"])
    targets.extend(snapshot["conversation_comments"])
    targets.extend(
        comment
        for thread in snapshot["review_threads"]
        for comment in thread["comments"]
    )
    return {
        target["id"]: {
            (
                reaction["id"],
                reaction["content"],
                reaction["user"]["login"],
                reaction["user"]["node_id"],
                reaction["user"]["database_id"],
            )
            for reaction in target["reactions"]
        }
        for target in targets
    }


def _no_late_feedback(
    plan: dict[str, Any],
    initial_snapshot: dict[str, Any],
    final_snapshot: dict[str, Any],
    verified_mutation_identities: set[str] | None = None,
) -> bool:
    verified_identities = verified_mutation_identities or set()
    recorded_feedback_identities = {
        operation["applied_mutation_identity"]
        for operation in plan["operations"]
        if operation["kind"] in {"REACTION", "EVIDENCE_REPLY"}
        and operation["applied_mutation_identity"] is not None
    }
    if not recorded_feedback_identities <= verified_identities:
        return False
    if _top_level_feedback(initial_snapshot, "reviews") != _top_level_feedback(final_snapshot, "reviews"):
        return False
    if _top_level_feedback(initial_snapshot, "conversation_comments") != _top_level_feedback(final_snapshot, "conversation_comments"):
        return False
    initial_threads = _thread_feedback(initial_snapshot)
    final_threads = _thread_feedback(final_snapshot)
    if initial_threads.keys() != final_threads.keys():
        return False
    initial_thread_state = {
        thread["id"]: thread["is_resolved"] for thread in initial_snapshot["review_threads"]
    }
    final_thread_state = {
        thread["id"]: thread["is_resolved"] for thread in final_snapshot["review_threads"]
    }
    if initial_thread_state != final_thread_state:
        return False
    allowed_replies = {
        (
            operation["parent_thread_id"],
            operation["applied_mutation_identity"],
            operation["reply_body"],
            operation["expected_actor_identity"]["login"],
        )
        for operation in plan["operations"]
        if operation["kind"] == "EVIDENCE_REPLY"
        and operation["applied_mutation_identity"] is not None
        and operation["applied_mutation_identity"] in verified_identities
    }
    final_reply_evidence = {
        (thread_id, comment_id, body, actor_login)
        for thread_id, comments in final_threads.items()
        for comment_id, body, actor_login in comments
    }
    if not allowed_replies <= final_reply_evidence:
        return False
    for thread_id, initial_comments in initial_threads.items():
        final_comments = final_threads[thread_id]
        if final_comments[: len(initial_comments)] != initial_comments:
            return False
        for comment_id, body, actor_login in final_comments[len(initial_comments) :]:
            if (thread_id, comment_id, body, actor_login) not in allowed_replies:
                return False
    initial_reactions = _reaction_feedback(initial_snapshot)
    final_reactions = _reaction_feedback(final_snapshot)
    allowed_reply_target_ids = {item[1] for item in allowed_replies}
    if not initial_reactions.keys() <= final_reactions.keys():
        return False
    if final_reactions.keys() - initial_reactions.keys() != (
        allowed_reply_target_ids - initial_reactions.keys()
    ):
        return False
    if any(
        final_reactions[target_id]
        for target_id in final_reactions.keys() - initial_reactions.keys()
    ):
        return False
    allowed_reactions: dict[
        str, set[tuple[str, str, str | None, str | None, int | None]]
    ] = {}
    for operation in plan["operations"]:
        mutation_identity = operation["applied_mutation_identity"]
        if (
            operation["kind"] != "REACTION"
            or mutation_identity is None
            or mutation_identity not in verified_identities
        ):
            continue
        actor = operation["expected_actor_identity"]
        allowed_reactions.setdefault(operation["target_node_id"], set()).add(
            (
                mutation_identity,
                operation["reaction"],
                actor["login"],
                actor["node_id"],
                actor["database_id"],
            )
        )
    for target_id, initial_items in initial_reactions.items():
        final_items = final_reactions[target_id]
        recorded_items = allowed_reactions.get(target_id, set())
        if not initial_items <= final_items:
            return False
        if not recorded_items <= final_items:
            return False
        if final_items - initial_items != recorded_items - initial_items:
            return False
    return True


def _all_initial_threads_classified(plan: dict[str, Any], initial_snapshot: dict[str, Any]) -> bool:
    findings_by_thread: dict[str, list[dict[str, Any]]] = {}
    findings_by_id = {
        finding["logical_finding_id"]: finding for finding in plan["findings"]
    }
    covered_top_level_source_ids: set[str] = set()
    for finding in plan["findings"]:
        thread_id = finding["parent_thread_id"]
        if thread_id:
            findings_by_thread.setdefault(thread_id, []).append(finding)
        elif (
            finding["classification"] == "AMBIGUOUS_NEEDS_USER_DECISION"
            or finding["disposition"] not in RESOLVABLE_DISPOSITIONS
        ):
            return False
        else:
            covered_top_level_source_ids.update(finding["source_node_ids"])
    for finding in plan["findings"]:
        canonical_id = finding["canonical_finding_id"]
        if canonical_id is None:
            continue
        canonical = findings_by_id.get(canonical_id)
        if canonical is None or (
            canonical["classification"] == "AMBIGUOUS_NEEDS_USER_DECISION"
            or canonical["disposition"] not in RESOLVABLE_DISPOSITIONS
        ):
            return False
    initial_top_level_source_ids = {
        item["id"]
        for key in ("reviews", "conversation_comments")
        for item in initial_snapshot[key]
    }
    if not initial_top_level_source_ids <= covered_top_level_source_ids:
        return False
    initial_thread_ids = {thread["id"] for thread in initial_snapshot["review_threads"]}
    if any(
        operation["kind"] == "THREAD_RESOLUTION"
        and operation["target_node_id"] not in initial_thread_ids
        for operation in plan["operations"]
    ):
        return False
    for thread in initial_snapshot["review_threads"]:
        findings = findings_by_thread.get(thread["id"], [])
        covered_source_ids = {
            source_id
            for finding in findings
            for source_id in finding["source_node_ids"]
        }
        thread_comment_ids = {comment["id"] for comment in thread["comments"]}
        if not thread_comment_ids <= covered_source_ids or any(
            finding["classification"] == "AMBIGUOUS_NEEDS_USER_DECISION"
            or finding["disposition"] not in RESOLVABLE_DISPOSITIONS
            for finding in findings
        ):
            return False
    return True


def build_resolution_evidence(
    plan: dict[str, Any],
    initial_snapshot: dict[str, Any],
    final_snapshot: dict[str, Any],
    configuration: dict[str, Any],
    command_runner: Any | None = None,
    validation_runner: Any | None = None,
    verified_mutation_identities: set[str] | None = None,
) -> dict[str, bool]:
    empty = {
        "local_verified": False,
        "final_evidence_verified": False,
        "no_late_feedback": False,
        "all_threads_classified": False,
        "registered_validation_verified": False,
    }
    try:
        evidence.validate_snapshot(initial_snapshot)
        verified = evidence.verify_snapshot_evidence(final_snapshot, configuration)
    except (evidence.ContractError, evidence.BlockedError):
        return empty
    if (
        initial_snapshot["snapshot_digest"] != plan["initial_snapshot_digest"]
        or initial_snapshot["repository"]["name_with_owner"] != plan["repository"]
        or initial_snapshot["pull_request"]["number"] != plan["pull_request_number"]
        or final_snapshot["repository"]["name_with_owner"] != plan["repository"]
        or final_snapshot["pull_request"]["number"] != plan["pull_request_number"]
        or final_snapshot["pull_request"]["head_oid_after"] != plan["expected_head_sha"]
        or not {
            commit["oid"] for commit in initial_snapshot["commits"]
        } <= {
            commit["oid"] for commit in final_snapshot["commits"]
        }
        or initial_snapshot["pull_request"]["head_oid_after"]
        not in {commit["oid"] for commit in final_snapshot["commits"]}
    ):
        return empty
    local_runner = command_runner or evidence.CommandRunner()
    try:
        local = evidence.verify_local_against_snapshot(
            final_snapshot,
            configuration,
            local_runner,
            plan["expected_head_sha"],
        )
    except (evidence.BlockedError, evidence.ContractError):
        local = {"blockers": ["local verification failed closed"]}
    result = {
        "local_verified": not local["blockers"],
        "final_evidence_verified": verified["evidence_verified"],
        "no_late_feedback": _no_late_feedback(
            plan,
            initial_snapshot,
            final_snapshot,
            verified_mutation_identities,
        ),
        "all_threads_classified": _all_initial_threads_classified(plan, initial_snapshot),
        "registered_validation_verified": False,
    }
    if all(result[key] for key in result if key != "registered_validation_verified"):
        try:
            registered = select_repository(load_registry(), plan["repository"])
            runner = validation_runner or _run_registered_validations
            result["registered_validation_verified"] = runner(
                registered, Path(local["repository_root"])
            ) is True
        except (OSError, RegistryError):
            result["registered_validation_verified"] = False
    if result["registered_validation_verified"]:
        try:
            final_local = evidence.verify_local_against_snapshot(
                final_snapshot,
                configuration,
                local_runner,
                plan["expected_head_sha"],
            )
            result["local_verified"] = not final_local["blockers"]
        except (evidence.BlockedError, evidence.ContractError):
            result["local_verified"] = False
    return result


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _add_plan_evidence_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--config", required=True)


def _add_mutation_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_evidence_arguments(parser)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=_positive_integer)
    parser.add_argument("--snapshot-digest", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--apply", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one deterministic review mutation plan or apply one allowlisted operation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect-actor")
    validate_parser = subparsers.add_parser("validate-plan")
    _add_plan_evidence_arguments(validate_parser)
    for name in ("react", "reply", "resolve"):
        mutation_parser = subparsers.add_parser(name)
        _add_mutation_arguments(mutation_parser)
        if name == "resolve":
            mutation_parser.add_argument("--initial-snapshot", required=True)
    return parser


def _load_inputs(arguments: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = _read_json(arguments.plan, "mutation plan")
    snapshot = _read_json(arguments.snapshot, "snapshot")
    configuration = _read_json(arguments.config, "repository configuration")
    return plan, snapshot, configuration


def _command_validate(arguments: argparse.Namespace) -> int:
    plan, snapshot, configuration = _load_inputs(arguments)
    value = validate_plan(plan, snapshot, configuration)
    report = {
        "status": "PLAN_VALID",
        "repository": value["repository"],
        "pull_request_number": value["pull_request_number"],
        "snapshot_digest": value["snapshot_digest"],
        "expected_head_sha": value["expected_head_sha"],
        "operation_count": len(value["operations"]),
        "mutation_performed": False,
    }
    sys.stdout.buffer.write(canonical_json_bytes(report))
    return 0


def _command_inspect_actor() -> int:
    actor = LiveGitHub().inspect_actor()
    report = {
        "status": "ACTOR_VERIFIED",
        "actor": actor,
        "mutation_performed": False,
    }
    sys.stdout.buffer.write(canonical_json_bytes(report))
    return 0


def _command_mutation(arguments: argparse.Namespace) -> int:
    plan, snapshot, configuration = _load_inputs(arguments)
    plan = validate_plan(plan, snapshot, configuration)
    expected_kind = {"react": "REACTION", "reply": "EVIDENCE_REPLY", "resolve": "THREAD_RESOLUTION"}[
        arguments.command
    ]
    if (
        arguments.repo != plan.get("repository")
        or arguments.pr != plan.get("pull_request_number")
        or arguments.snapshot_digest != plan.get("snapshot_digest")
        or arguments.expected_head != plan.get("expected_head_sha")
    ):
        raise PlanError("explicit mutation anchors do not match the mutation plan")
    operation = next(
        (item for item in plan.get("operations", []) if item.get("operation_id") == arguments.operation_id),
        None,
    )
    if not isinstance(operation, dict) or operation.get("kind") != expected_kind:
        raise PlanError(f"{arguments.command} requires an operation of kind {expected_kind}")
    resolution_evidence = None
    github = LiveGitHub()
    if arguments.command == "resolve" and arguments.apply:
        initial_snapshot = _read_json(arguments.initial_snapshot, "initial snapshot")
        verified_mutation_identities = _verify_retained_feedback_mutations(
            plan,
            snapshot,
            github,
        )
        resolution_evidence = build_resolution_evidence(
            plan,
            initial_snapshot,
            snapshot,
            configuration,
            verified_mutation_identities=verified_mutation_identities,
        )
    result = execute_operation(
        plan,
        arguments.operation_id,
        snapshot,
        configuration,
        github,
        apply=arguments.apply,
        resolution_evidence=resolution_evidence,
    )
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "inspect-actor":
            return _command_inspect_actor()
        if arguments.command == "validate-plan":
            return _command_validate(arguments)
        return _command_mutation(arguments)
    except MutationFailure as exc:
        report = {
            "status": "BLOCKED_MUTATION_FAILED",
            "blocker": evidence.redact_diagnostic(str(exc)),
            "retry_performed": False,
        }
        print(canonical_json_bytes(report).decode("utf-8"), file=sys.stderr, end="")
        return 3
    except MutationBlocked as exc:
        report = {
            "status": "BLOCKED",
            "blocker": evidence.redact_diagnostic(str(exc)),
            "retry_performed": False,
        }
        print(canonical_json_bytes(report).decode("utf-8"), file=sys.stderr, end="")
        return 3
    except (PlanError, RegistryError, OSError) as exc:
        report = {
            "status": "INVALID_OR_UNSAFE_INPUT",
            "error": evidence.redact_diagnostic(str(exc)),
        }
        print(canonical_json_bytes(report).decode("utf-8"), file=sys.stderr, end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
