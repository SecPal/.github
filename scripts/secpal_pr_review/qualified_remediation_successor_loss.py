# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact accepted-main admission for one qualified remediation successor loss."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from dataclasses import dataclass
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/qualified-remediation-successor-evidence-loss.json"
KIND = "QUALIFIED_TWO_PARENT_REMEDIATION_SUCCESSOR_WITH_MISSING_COMMIT_BOUND_EVIDENCE"
_OID = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
EXPECTED_THREAD_IDS = (
    "PRRT_kwDOQFR1MM6jHjKn", "PRRT_kwDOQFR1MM6jHjKu",
    "PRRT_kwDOQFR1MM6jHjK0", "PRRT_kwDOQFR1MM6jHjK4",
    "PRRT_kwDOQFR1MM6jHjK6", "PRRT_kwDOQFR1MM6jHjK_",
    "PRRT_kwDOQFR1MM6jHjLD", "PRRT_kwDOQFR1MM6jHjLI",
    "PRRT_kwDOQFR1MM6jHjLO", "PRRT_kwDOQFR1MM6jHmaj",
    "PRRT_kwDOQFR1MM6jHmbU", "PRRT_kwDOQFR1MM6jHmb3",
)
_RECORD_FIELDS = frozenset(
    {
        "schema_version", "kind", "repository", "delivery_issue",
        "pull_request", "accepted_main_at_classification", "predecessor",
        "successor", "predecessor_state", "resulting_state", "qualification",
        "stable_thread_inventory", "current_material_finding_ids",
        "transition_kind", "bounded_uses", "historical_package_status",
        "historical_integration_evidence_digest",
        "historical_validation_receipt_digest", "historical_bytes_reconstructed",
        "publication_branch", "signer_identity", "policy_path",
        "registration_path", "admission_digest",
    }
)


class QualifiedRemediationSuccessorLossError(ValueError):
    """The exact accepted admission is unavailable, malformed, or substituted."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _closed(value: Any, fields: set[str] | frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise QualifiedRemediationSuccessorLossError(f"{label} is malformed")
    return copy.deepcopy(dict(value))


def _oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or _OID.fullmatch(value) is None:
        raise QualifiedRemediationSuccessorLossError(f"{label} is malformed")
    return value


def _digest_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise QualifiedRemediationSuccessorLossError(f"{label} is malformed")
    return value


def verify_admission(value: Any) -> dict[str, Any]:
    """Verify the closed one-use accepted-main record without observing GitHub."""

    item = _closed(value, _RECORD_FIELDS, "qualified remediation loss admission")
    predecessor = _closed(
        item["predecessor"],
        {"publication_oid", "publication_digest", "head_sha", "tree_sha", "terminal_authority_digest"},
        "qualified remediation predecessor",
    )
    successor = _closed(
        item["successor"],
        {"head_sha", "tree_sha", "ordered_parent_shas", "base_ref", "base_sha"},
        "qualified remediation successor",
    )
    qualification = _closed(
        item["qualification"],
        {
            "id", "classification", "qualified_source_repository",
            "qualified_source_issue", "qualified_source_pull_request",
            "qualified_source_head_sha", "qualified_source_tree_sha",
            "provider_summary_head_sha",
            "reviewed_state_digest", "reviewed_feedback_digest",
        },
        "qualified remediation classification",
    )
    for field in ("publication_oid", "head_sha", "tree_sha"):
        _oid(predecessor[field], f"predecessor {field}")
    for field in ("publication_digest", "terminal_authority_digest"):
        _digest_value(predecessor[field], f"predecessor {field}")
    head = _oid(successor["head_sha"], "successor head")
    tree = _oid(successor["tree_sha"], "successor tree")
    parents = successor["ordered_parent_shas"]
    if (
        item["schema_version"] != "1.0"
        or item["kind"] != KIND
        or item["repository"] != "SecPal/.github"
        or item["delivery_issue"] != 956
        or item["pull_request"] != 957
        or item["accepted_main_at_classification"]
        != "14c5bcf19eaa9e144af5e9afa05f12f2c08648dc"
        or predecessor["publication_oid"]
        != "e8bb42d5bbb1837bc0fd3c7b18873ea91f17bbb2"
        or predecessor["publication_digest"]
        != "1237f43d9b2bb2e63c2648fe5f866f7837c502d3438be20567cb2003a5a9fd88"
        or predecessor["head_sha"]
        != "fd6e9ff07552cdbbd15373131a073d6bb5357936"
        or predecessor["tree_sha"]
        != "16784bf3473caa9f9d10106681ad12a03cd89040"
        or head != "14c8646aecd3555473cef58d59fc3cf441260baa"
        or tree != "391cec4156c7cbc735c28dccddaa3d6e937e74d0"
        or parents
        != [
            "fd6e9ff07552cdbbd15373131a073d6bb5357936",
            "14c5bcf19eaa9e144af5e9afa05f12f2c08648dc",
        ]
        or successor["base_ref"] != "main"
        or successor["base_sha"] != parents[1]
        or qualification
        != {
            "id": "e92cf027-a097-4853-a65c-5151577df509",
            "classification": KIND,
            "qualified_source_repository": item["repository"],
            "qualified_source_issue": item["delivery_issue"],
            "qualified_source_pull_request": item["pull_request"],
            "qualified_source_head_sha": head,
            "qualified_source_tree_sha": tree,
            "provider_summary_head_sha": "d017aec38b0f0c3c38ecf526a7ea011156636e57",
            "reviewed_state_digest": "769a646a244f0c4b816070cd6fa0f29f1cbdbe7e28ca4baf9a1a836ebb81de04",
            "reviewed_feedback_digest": "79d2f93b48468f7d0ec567093e6fda36857fa29604b5ac58364360760f20a489",
        }
        or item["transition_kind"] != "REMEDIATION_COMPLETED"
        or item["bounded_uses"] != 1
        or isinstance(item["bounded_uses"], bool)
        or item["historical_package_status"] != "UNAVAILABLE"
        or item["historical_integration_evidence_digest"] is not None
        or item["historical_validation_receipt_digest"] is not None
        or item["historical_bytes_reconstructed"] is not False
        or item["publication_branch"] != "refs/heads/secpal-lifecycle-publications"
        or item["signer_identity"] != "aroviqen@secpal.app"
        or item["policy_path"] != POLICY_PATH
        or item["registration_path"]
        != ".agents/skills/secpal-pr-review/references/repositories.json"
    ):
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation loss scope changed"
        )
    before = item["predecessor_state"]
    after = item["resulting_state"]
    expected_before = {
        "unrestricted_review_count": 1, "remediation_cycle_count": 1,
        "cycle_3_absent": True, "draft": False, "ready": True,
        "ready_transition_count": 1, "exceptional_recovery_count": 0,
        "exceptional_continuation_count": 0,
    }
    if before != expected_before or after != {**expected_before, "remediation_cycle_count": 2}:
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation lifecycle state changed"
        )
    inventory = item["stable_thread_inventory"]
    if (
        not isinstance(inventory, list)
        or len(inventory) != 12
        or tuple(
            entry.get("thread_id") for entry in inventory
            if isinstance(entry, dict)
        ) != EXPECTED_THREAD_IDS
        or len({entry.get("thread_id") for entry in inventory if isinstance(entry, dict)}) != 12
        or any(
            not isinstance(entry, dict)
            or set(entry) != {"thread_id", "resolved", "outdated"}
            or not isinstance(entry["thread_id"], str)
            or entry["resolved"] is not False
            or entry["outdated"] is not True
            for entry in inventory
        )
        or item["current_material_finding_ids"] != []
    ):
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation thread or finding inventory changed"
        )
    unsigned = {key: field for key, field in item.items() if key != "admission_digest"}
    if _digest_value(item["admission_digest"], "admission digest") != _digest(unsigned):
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation admission digest mismatch"
        )
    return item


@dataclass(frozen=True)
class QualifiedProviderBinding:
    """Expose only the exact provider head selected by accepted qualification."""

    admission_digest: str
    repository: str
    pull_request: int
    current_head_sha: str
    provider_head_sha: str

    def provider_head(
        self, *, repository: str, pull_request: int, current_head_sha: str
    ) -> str:
        if (
            repository != self.repository
            or pull_request != self.pull_request
            or current_head_sha != self.current_head_sha
        ):
            raise QualifiedRemediationSuccessorLossError(
                "qualified provider binding scope changed"
            )
        return self.provider_head_sha


def provider_binding(admission: Any) -> QualifiedProviderBinding:
    """Project the already-qualified provider source without new authority."""

    record = verify_admission(admission)
    return QualifiedProviderBinding(
        admission_digest=record["admission_digest"],
        repository=record["repository"],
        pull_request=record["pull_request"],
        current_head_sha=record["successor"]["head_sha"],
        provider_head_sha=record["qualification"]["provider_summary_head_sha"],
    )


def load_accepted_admission(repository: str, delivery_issue: int) -> dict[str, Any]:
    """Load the one accepted record for an exact delivery identity."""

    try:
        policy = json.loads((ROOT / POLICY_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation loss policy is unavailable"
        ) from exc
    records = policy.get("admissions") if isinstance(policy, dict) else None
    matches = [
        item for item in records or []
        if isinstance(item, dict)
        and item.get("repository") == repository
        and item.get("delivery_issue") == delivery_issue
    ]
    if policy.get("schema_version") != "1.0" or len(matches) != 1:
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation loss admission is unavailable or ambiguous"
        )
    return verify_admission(matches[0])


def verify_safety_binding(admission: Any, safety: Any) -> None:
    """Bind current safety to the exact successor, threads, and zero findings."""

    record = verify_admission(admission)
    if not isinstance(safety, Mapping):
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation current safety is malformed"
        )
    successor = record["successor"]
    reviewed = safety.get("reviewed_state")
    threads = reviewed.get("threads") if isinstance(reviewed, Mapping) else None
    observed = None
    if isinstance(threads, list):
        observed_by_id: dict[str, tuple[bool, bool]] = {}
        for item in threads:
            if (
                not isinstance(item, Mapping)
                or not isinstance(item.get("node_id"), str)
                or not isinstance(item.get("is_resolved"), bool)
                or not isinstance(item.get("is_outdated"), bool)
                or item["node_id"] in observed_by_id
            ):
                break
            observed_by_id[item["node_id"]] = (
                item["is_resolved"], item["is_outdated"]
            )
        else:
            observed = observed_by_id
    expected = {
        item["thread_id"]: (item["resolved"], item["outdated"])
        for item in record["stable_thread_inventory"]
    }
    material = [
        item.get("finding_id") for item in safety.get("feedback_findings", [])
        if isinstance(item, Mapping) and item.get("technically_blocking") is True
    ]
    if (
        safety.get("repository") != record["repository"]
        or safety.get("pull_request_number") != record["pull_request"]
        or safety.get("head_sha") != successor["head_sha"]
        or safety.get("tree_sha") != successor["tree_sha"]
        or safety.get("parent_shas") != successor["ordered_parent_shas"]
        or safety.get("expected_base_ref") != successor["base_ref"]
        or safety.get("expected_base_sha") != successor["base_sha"]
        or observed != expected
        or material != record["current_material_finding_ids"]
        or safety.get("reviewed_state_digest")
        != record["qualification"]["reviewed_state_digest"]
        or safety.get("reviewed_feedback_digest")
        != record["qualification"]["reviewed_feedback_digest"]
    ):
        raise QualifiedRemediationSuccessorLossError(
            "qualified remediation current safety changed"
        )
