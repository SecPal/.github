# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed one-use authority for an exact governance-only bootstrap amendment."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from . import lifecycle_authority as authority

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/governance-amendment-bootstrap.json"
REGISTRY_PATH = ".agents/skills/secpal-pr-review/references/repositories.json"
KIND = "SECPAL_GOVERNANCE_AMENDMENT_AUTHORIZATION"
DOMAIN = "secpal.governance-amendment-authorization/v1"
PURPOSE = "EXACT_ZERO_RECEIPT_PRE_ENROLLMENT_BOOTSTRAP"
EVIDENCE_STATE = "ABSENT_NEVER_ISSUED"
_VERIFIED = object()

AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "kind", "domain", "purpose", "repository",
    "delivery_issue", "pull_request", "pull_request_state", "qualified_source", "head_sha",
    "tree_sha", "ordered_parent_shas", "accepted_main_sha",
    "changed_files", "change_digest", "source_signature",
    "natural_ci", "independent_qualification", "current_validation",
    "feedback", "observed_pre_enrollment_history", "intended_state",
    "historical_evidence", "historical_absence_proof", "concepts",
    "human_authority_identity", "human_authorization_digest",
    "authorization_id", "bounded_uses", "signer_identity", "signature",
    "authorization_digest",
})
HISTORICAL_FIELDS = frozenset({
    "state", "validation_receipt_digest", "source_validation_evidence_digest",
    "final_attestation_digest", "bytes_reconstructed",
})
CHANGED_FILE_FIELDS = frozenset({"path", "blob_oid", "mode"})


class GovernanceAmendmentError(ValueError):
    """The amendment is malformed, stale, untrusted, or outside exact scope."""


class VerifiedGovernanceAmendment:
    """Opaque verified authority consumable only by Exact-State-Adoption v4."""

    __slots__ = ("authorization", "_seal")

    def __init__(self, authorization: dict[str, Any], seal: object) -> None:
        self.authorization = authorization
        self._seal = seal


def is_verified(value: Any) -> bool:
    return isinstance(value, VerifiedGovernanceAmendment) and value._seal is _VERIFIED


def historical_evidence() -> dict[str, Any]:
    return {
        "state": EVIDENCE_STATE,
        "validation_receipt_digest": None,
        "source_validation_evidence_digest": None,
        "final_attestation_digest": None,
        "bytes_reconstructed": False,
    }


def _load_policy() -> dict[str, Any]:
    try:
        value = json.loads((ROOT / POLICY_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceAmendmentError("governance amendment policy is unavailable") from exc
    records = value.get("amendments") if isinstance(value, dict) else None
    if value.get("schema_version") != "1.0" or not isinstance(records, list) or len(records) != 1:
        raise GovernanceAmendmentError("governance amendment policy is not singular")
    record = copy.deepcopy(records[0])
    try:
        registry = json.loads((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
        entries = [
            entry for entry in registry["repositories"]
            if entry.get("repository") == record.get("repository")
        ]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GovernanceAmendmentError("governance amendment registry is unavailable") from exc
    expected_registration = {
        "path": POLICY_PATH,
        "kind": KIND,
        "purpose": PURPOSE,
    }
    if (
        len(entries) != 1
        or entries[0].get("governance_amendment_policy") != expected_registration
    ):
        raise GovernanceAmendmentError(
            "governance amendment policy is not registered on accepted main"
        )
    return record


def _changed_files(value: Any, allowed_prefixes: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise GovernanceAmendmentError("governance amendment changed files are missing")
    result: list[dict[str, Any]] = []
    paths: list[str] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != CHANGED_FILE_FIELDS:
            raise GovernanceAmendmentError("governance amendment changed file is malformed")
        path = raw.get("path")
        if (
            not isinstance(path, str) or not path or path.startswith(("/", ".git/"))
            or ".." in Path(path).parts
            or not any(path == prefix or path.startswith(f"{prefix}/") for prefix in allowed_prefixes)
        ):
            raise GovernanceAmendmentError("governance amendment contains non-governance source")
        authority._require_oid(raw.get("blob_oid"), "governance amendment blob")
        if raw.get("mode") not in {"100644", "100755"}:
            raise GovernanceAmendmentError("governance amendment file mode is invalid")
        paths.append(path)
        result.append(copy.deepcopy(raw))
    if paths != sorted(set(paths)):
        raise GovernanceAmendmentError("governance amendment paths are not canonical")
    return result


def verify(value: Any) -> VerifiedGovernanceAmendment:
    """Verify one signed exact-scope authorization; perform no publication or write."""

    if not isinstance(value, Mapping) or set(value) != AUTHORIZATION_FIELDS:
        raise GovernanceAmendmentError("governance amendment authorization schema is not closed")
    item = copy.deepcopy(dict(value))
    policy = _load_policy()
    try:
        repository = authority._require_repository(item["repository"])
        issue = authority._require_positive_int(item["delivery_issue"], "delivery issue")
        pr = authority._require_positive_int(item["pull_request"], "pull request")
        head = authority._require_oid(item["head_sha"], "amendment head")
        tree = authority._require_oid(item["tree_sha"], "amendment tree")
        main = authority._require_oid(item["accepted_main_sha"], "accepted main")
        parents = item["ordered_parent_shas"]
        if not isinstance(parents, list) or not 1 <= len(parents) <= 2:
            raise GovernanceAmendmentError("governance amendment topology is invalid")
        parents = [authority._require_oid(parent, "amendment parent") for parent in parents]
        changed = _changed_files(item["changed_files"], policy["allowed_path_prefixes"])
        historical = authority._require_closed(
            item["historical_evidence"], HISTORICAL_FIELDS,
            "governance amendment historical evidence",
        )
        state = authority._validate_state(
            item["intended_state"], allow_adopted_observations=True
        )
        history = authority._normalize_observed_pre_enrollment_history(
            item["observed_pre_enrollment_history"], expected_head=head,
            intended_state=state, review_budget_consumption_admitted=True,
        )
        signature = authority._require_closed(
            item["source_signature"],
            frozenset({"signer_identity", "signature_evidence_digest", "verified"}),
            "governance amendment source signature",
        )
        ci = authority._require_closed(
            item["natural_ci"],
            frozenset({"head_sha", "workflow_identity", "result", "evidence_digest"}),
            "governance amendment natural CI",
        )
        absence = authority._require_closed(
            item["historical_absence_proof"],
            frozenset({
                "head_sha", "verification_authority", "history_digest",
                "artifact_audit_digest", "result",
            }),
            "governance amendment historical absence proof",
        )
        qualification = authority._require_closed(
            item["independent_qualification"],
            frozenset({"verifier_identity", "conversation_id", "head_sha", "tree_sha", "result", "qualification_digest"}),
            "governance amendment independent qualification",
        )
        validation = authority._require_closed(
            item["current_validation"],
            frozenset({"accepted_main_sha", "policy_digest", "command_set_digest", "result"}),
            "governance amendment current validation",
        )
        feedback = authority._require_closed(
            item["feedback"],
            frozenset({"state_digest", "feedback_digest", "thread_inventory_digest", "material_finding_ids"}),
            "governance amendment feedback",
        )
        qualified = authority._require_closed(
            item["qualified_source"],
            frozenset({
                "head_sha", "tree_sha", "ordered_parent_shas",
                "verifier_conversation_id", "verifier_workspace", "result",
                "material_finding_ids", "qualification_digest",
            }),
            "governance amendment qualified source",
        )
        qualified_identity = {
            "conversation_id": qualified["verifier_conversation_id"],
            "workspace": qualified["verifier_workspace"],
            "head_sha": qualified["head_sha"],
            "tree_sha": qualified["tree_sha"],
            "result": qualified["result"],
            "material_finding_ids": qualified["material_finding_ids"],
        }
        qualified_head = authority._require_oid(
            qualified["head_sha"], "qualified source head"
        )
        authority._require_oid(qualified["tree_sha"], "qualified source tree")
        if (
            not isinstance(qualified["ordered_parent_shas"], list)
            or not qualified["ordered_parent_shas"]
            or any(
                authority._require_oid(parent, "qualified source parent") is None
                for parent in qualified["ordered_parent_shas"]
            )
            or qualified["result"] != "PASS"
            or qualified["material_finding_ids"] != []
            or not isinstance(qualified["verifier_conversation_id"], str)
            or not qualified["verifier_conversation_id"]
            or not isinstance(qualified["verifier_workspace"], str)
            or not qualified["verifier_workspace"]
        ):
            raise GovernanceAmendmentError("qualified source is not exact and passing")
        for field in ("signature_evidence_digest",):
            authority._require_digest(signature[field], field)
        for source, fields in ((ci, ("evidence_digest",)), (qualification, ("qualification_digest",)), (validation, ("policy_digest", "command_set_digest")), (feedback, ("state_digest", "feedback_digest", "thread_inventory_digest")), (qualified, ("qualification_digest",))):
            for field in fields:
                authority._require_digest(source[field], field)
        for field in ("history_digest", "artifact_audit_digest"):
            authority._require_digest(absence[field], field)
    except (authority.LifecycleAuthorityError, KeyError, TypeError) as exc:
        raise GovernanceAmendmentError("governance amendment authorization is malformed") from exc
    expected_change_digest = authority.digest_json({
        "repository": repository, "delivery_issue": issue, "pull_request": pr,
        "head_sha": head, "tree_sha": tree, "ordered_parent_shas": parents,
        "accepted_main_sha": main, "changed_files": changed,
    })
    expected_human_authorization_digest = authority.digest_json({
        "authority_identity": policy["human_authority_identity"],
        "repository": repository,
        "delivery_issue": issue,
        "pull_request": pr,
        "purpose": PURPOSE,
        "qualified_source_digest": qualified["qualification_digest"],
        "accepted_main_sha": main,
        "decision": "APPROVED",
        "bounded_uses": 1,
    })
    if (
        item["schema_version"] != "1.0" or item["kind"] != KIND
        or item["domain"] != DOMAIN or item["purpose"] != PURPOSE
        or item["pull_request_state"] != "OPEN"
        or {"repository": repository, "delivery_issue": issue, "pull_request": pr}
        != {key: policy[key] for key in ("repository", "delivery_issue", "pull_request")}
        or qualified != policy["qualified_source"]
        or qualified["qualification_digest"] != authority.digest_json(
            qualified_identity
        )
        or main != policy["accepted_main_sha"]
        or item["change_digest"] != expected_change_digest
        or signature["signer_identity"] != policy["source_signer_identity"]
        or signature["verified"] is not True
        or ci["head_sha"] != head or ci["result"] != "PASS"
        or not isinstance(ci["workflow_identity"], str) or not ci["workflow_identity"]
        or qualification["head_sha"] != head or qualification["tree_sha"] != tree
        or qualification["result"] != "PASS"
        or validation["accepted_main_sha"] != main or validation["result"] != "PASS"
        or feedback["material_finding_ids"] != []
        or historical != historical_evidence()
        or absence["head_sha"] != head
        or absence["verification_authority"]
        != "PROTECTED_DELIVERY_HISTORY_AND_ARTIFACT_AUDIT"
        or absence["result"] != "NO_HISTORICAL_RECEIPT_ISSUED"
        or state != policy["intended_state"]
        or history != item["observed_pre_enrollment_history"]
        or item["concepts"] != policy["concepts"]
        or item["human_authority_identity"] != policy["human_authority_identity"]
        or item["human_authorization_digest"]
        != policy["human_authorization_digest"]
        or item["human_authorization_digest"]
        != expected_human_authorization_digest
        or item["authorization_id"] != policy["authorization_id"]
        or item["bounded_uses"] != 1 or isinstance(item["bounded_uses"], bool)
    ):
        raise GovernanceAmendmentError("governance amendment authorization scope changed")
    signer = authority._require_identity(item["signer_identity"], "amendment signer")
    signed = {key: copy.deepcopy(entry) for key, entry in item.items() if key != "authorization_digest"}
    digest = authority._require_digest(item["authorization_digest"], "amendment authorization")
    if digest != authority.digest_json(signed):
        raise GovernanceAmendmentError("governance amendment authorization digest mismatch")
    trust = authority._load_lifecycle_trust_policy(repository)
    try:
        authority._verify_signature(
            authority.canonical_json_bytes(authority._unsigned(item, "authorization_digest", "signature")),
            item["signature"], signer, DOMAIN, trust.legacy_adoption_signer_identities,
            authority._policy_signature_verifier(trust),
        )
    except authority.LifecycleAuthorityError as exc:
        raise GovernanceAmendmentError("governance amendment signature is invalid") from exc
    return VerifiedGovernanceAmendment(item, _VERIFIED)
