# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Closed one-use authority for an exact governance-only bootstrap amendment."""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping

from . import lifecycle_authority as authority
from . import lifecycle_execution as execution
from . import lifecycle_publication as publication

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/governance-amendment-bootstrap.json"
REGISTRY_PATH = ".agents/skills/secpal-pr-review/references/repositories.json"
KIND = "SECPAL_GOVERNANCE_AMENDMENT_AUTHORIZATION"
DOMAIN = "secpal.governance-amendment-authorization/v1"
PURPOSE = "EXACT_ZERO_RECEIPT_PRE_ENROLLMENT_BOOTSTRAP"
EVIDENCE_STATE = "ABSENT_NEVER_ISSUED"
_VERIFIED = object()
_ISSUANCE_VERIFIED = object()
ACCEPTED_MAIN_REF = "refs/heads/main"
CONSUMPTION_DOMAIN = "secpal.governance-amendment-consumption/v1"
CONSUMPTION_KIND = "SECPAL_GOVERNANCE_AMENDMENT_CONSUMPTION"
LIVE_OBSERVATION_VERSION = "github-git-live-observation/v1"
ROOT_AUTHORIZATION_DOMAIN = "secpal.governance-amendment-root-authorization/v1"
ROOT_AUTHORIZATION_KIND = "SECPAL_GOVERNANCE_AMENDMENT_ROOT_AUTHORIZATION"
HUMAN_AUTHORITY_IDENTITY = "SecPal human architecture authority for issue 960"
SOURCE_SIGNER_IDENTITY = "aroviqen@secpal.app"
GOVERNANCE_EXACT_PATHS = frozenset({
    "scripts/secpal-pr-review-actions.py",
    "scripts/secpal-resolve-fixed-threads.py",
})
GOVERNANCE_PATH_PREFIXES = [
    ".agents/skills/secpal-pr-review/references",
    "CHANGELOG.md",
    "docs",
    "policies",
    "scripts/README.md",
    "scripts/secpal-pr-review-actions.py",
    "scripts/secpal-resolve-fixed-threads.py",
    "scripts/secpal_pr_review",
    "tests",
]
APPROVED_CONCEPTS = [
    "GOVERNANCE_AMENDMENT", "ABSENT_NEVER_ISSUED", "EXACT_STATE_ADOPTION",
]

AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "kind", "domain", "purpose", "repository",
    "delivery_issue", "pull_request", "pull_request_state", "qualified_source", "head_sha",
    "tree_sha", "ordered_parent_shas", "accepted_main_sha",
    "governance_path_prefixes", "root_authorization",
    "changed_files", "change_digest", "source_signature", "source_commits",
    "natural_ci", "independent_qualification", "current_validation",
    "feedback", "observed_pre_enrollment_history", "intended_state",
    "historical_evidence", "historical_absence_proof", "concepts",
    "architecture_necessity",
    "human_authority_identity", "human_authorization_digest",
    "authorization_id", "bounded_uses", "signer_identity", "signature",
    "authorization_digest",
})
HISTORICAL_FIELDS = frozenset({
    "state", "validation_receipt_digest", "source_validation_evidence_digest",
    "final_attestation_digest", "bytes_reconstructed",
})
CHANGED_FILE_FIELDS = frozenset({"path", "blob_oid", "mode"})
SOURCE_COMMIT_FIELDS = frozenset({
    "oid", "signer_identity", "signature_evidence_digest",
})
ROOT_AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "kind", "domain", "repository", "delivery_issue",
    "pull_request", "head_sha", "tree_sha", "accepted_main_sha", "purpose",
    "governance_path_prefixes", "human_authority_identity",
    "human_authorization_digest", "authorized_facts_digest", "bounded_uses",
    "signer_identity", "signature", "authorization_digest",
})
ISSUANCE_FACT_FIELDS = AUTHORIZATION_FIELDS - {
    "root_authorization", "signer_identity", "signature",
    "authorization_digest",
}
OBSERVATION_INPUT_FIELDS = frozenset({
    "pull_request", "accepted_main_sha", "qualified_source",
    "independent_qualification", "current_validation",
    "observed_pre_enrollment_history", "intended_state",
    "historical_evidence", "historical_absence_proof",
    "architecture_necessity", "human_authority_identity",
    "human_authorization_digest", "authorization_id", "bounded_uses",
})


class GovernanceAmendmentError(ValueError):
    """The amendment is malformed, stale, untrusted, or outside exact scope."""


class VerifiedGovernanceAmendment:
    """Opaque exact amendment authority."""

    __slots__ = ("authorization", "_seal")

    def __init__(self, authorization: dict[str, Any], seal: object) -> None:
        self.authorization = authorization
        self._seal = seal


class VerifiedGovernanceAmendmentIssuance:
    """Facts independently authenticated by the maintained root boundary."""

    __slots__ = ("facts", "inputs", "_seal")

    def __init__(
        self, facts: dict[str, Any], inputs: dict[str, Any], seal: object,
    ) -> None:
        self.facts = facts
        self.inputs = inputs
        self._seal = seal


def is_verified_issuance(value: Any) -> bool:
    return (
        isinstance(value, VerifiedGovernanceAmendmentIssuance)
        and value._seal is _ISSUANCE_VERIFIED
    )


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


def canonical_change_facts(
    *, repository: str, delivery_issue: int, pull_request: int,
    head_sha: str, tree_sha: str, ordered_parent_shas: list[str],
    accepted_main_sha: str, changed_files: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the sole canonical input to the governance change digest."""

    return {
        "repository": repository,
        "delivery_issue": delivery_issue,
        "pull_request": pull_request,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "ordered_parent_shas": copy.deepcopy(ordered_parent_shas),
        "accepted_main_sha": accepted_main_sha,
        "changed_files": copy.deepcopy(changed_files),
    }


def change_digest(**facts: Any) -> str:
    """Digest exact scope using maintained canonical JSON, including newline."""

    return authority.digest_json(canonical_change_facts(**facts))


def source_commit_evidence(
    oid: str, signer_identity: str, accepted_main_sha: str,
) -> dict[str, str]:
    fields = {
        "oid": oid,
        "signer_identity": signer_identity,
        "accepted_main_sha": accepted_main_sha,
        "verification": "BOUND_ACCEPTED_MAIN_KEY",
    }
    return {
        "oid": oid,
        "signer_identity": signer_identity,
        "signature_evidence_digest": authority.digest_json(fields),
    }


def _authorization_facts(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in item.items()
        if key not in {
            "root_authorization", "signer_identity", "signature",
            "authorization_digest",
        }
    }


def _verify_root_authorization(
    item: Mapping[str, Any], repository: str, accepted_main_sha: str,
    *, authenticate_signature: bool,
) -> dict[str, Any]:
    root = authority._require_closed(
        item.get("root_authorization"), ROOT_AUTHORIZATION_FIELDS,
        "governance amendment root authorization",
    )
    signed = {
        key: copy.deepcopy(value)
        for key, value in root.items()
        if key != "authorization_digest"
    }
    expected_human_digest = authority.digest_json({
        "authority_identity": HUMAN_AUTHORITY_IDENTITY,
        "repository": repository,
        "delivery_issue": item["delivery_issue"],
        "pull_request": item["pull_request"],
        "purpose": PURPOSE,
        "qualified_source_digest": item["qualified_source"][
            "qualification_digest"
        ],
        "accepted_main_sha": accepted_main_sha,
        "decision": "APPROVED",
        "bounded_uses": 1,
    })
    if (
        root["schema_version"] != "1.0"
        or root["kind"] != ROOT_AUTHORIZATION_KIND
        or root["domain"] != ROOT_AUTHORIZATION_DOMAIN
        or root["repository"] != repository
        or root["delivery_issue"] != item["delivery_issue"]
        or root["pull_request"] != item["pull_request"]
        or root["head_sha"] != item["head_sha"]
        or root["tree_sha"] != item["tree_sha"]
        or root["accepted_main_sha"] != accepted_main_sha
        or root["purpose"] != PURPOSE
        or root["governance_path_prefixes"] != GOVERNANCE_PATH_PREFIXES
        or root["human_authority_identity"] != HUMAN_AUTHORITY_IDENTITY
        or root["human_authorization_digest"] != expected_human_digest
        or root["authorized_facts_digest"]
        != authority.digest_json(_authorization_facts(item))
        or root["bounded_uses"] != 1
        or isinstance(root["bounded_uses"], bool)
        or root["authorization_digest"] != authority.digest_json(signed)
    ):
        raise GovernanceAmendmentError(
            "governance amendment root authorization scope changed"
        )
    signer = authority._require_identity(
        root["signer_identity"], "governance amendment root signer"
    )
    if authenticate_signature:
        trust = _accepted_trust_policy(repository, accepted_main_sha)
        try:
            authority._verify_signature(
                authority.canonical_json_bytes(
                    authority._unsigned(
                        root, "authorization_digest", "signature"
                    )
                ),
                root["signature"], signer, ROOT_AUTHORIZATION_DOMAIN,
                trust.authority_signer_identities,
                authority._policy_signature_verifier(trust),
            )
        except authority.LifecycleAuthorityError as exc:
            raise GovernanceAmendmentError(
                "governance amendment root authorization is untrusted"
            ) from exc
    return copy.deepcopy(root)


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
            or not any(
                path == prefix
                or (
                    prefix not in GOVERNANCE_EXACT_PATHS
                    and path.startswith(f"{prefix}/")
                )
                for prefix in allowed_prefixes
            )
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


def _verify(
    value: Any, *, authenticate_signature: bool
) -> VerifiedGovernanceAmendment:

    if not isinstance(value, Mapping) or set(value) != AUTHORIZATION_FIELDS:
        raise GovernanceAmendmentError("governance amendment authorization schema is not closed")
    item = copy.deepcopy(dict(value))
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
        root_authorization = _verify_root_authorization(
            item, repository, main,
            authenticate_signature=authenticate_signature,
        )
        changed = _changed_files(
            item["changed_files"], item["governance_path_prefixes"]
        )
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
        raw_source_commits = item["source_commits"]
        if not isinstance(raw_source_commits, list) or not raw_source_commits:
            raise GovernanceAmendmentError(
                "governance amendment source commit range is missing"
            )
        source_commits = [
            authority._require_closed(
                entry, SOURCE_COMMIT_FIELDS,
                "governance amendment source commit",
            )
            for entry in raw_source_commits
        ]
        for entry in source_commits:
            authority._require_oid(entry["oid"], "governance source commit")
            authority._require_identity(
                entry["signer_identity"], "governance source commit signer"
            )
            authority._require_digest(
                entry["signature_evidence_digest"],
                "governance source commit signature evidence",
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
        necessity = authority._require_closed(
            item["architecture_necessity"],
            frozenset({
                "existing_authority_result", "smaller_nonrecursive_extension",
                "recursive_self_bootstrap", "evidence_digest",
            }),
            "governance amendment architecture necessity",
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
        authority._require_digest(
            necessity["evidence_digest"], "architecture necessity evidence"
        )
    except (authority.LifecycleAuthorityError, KeyError, TypeError) as exc:
        raise GovernanceAmendmentError("governance amendment authorization is malformed") from exc
    expected_change_digest = change_digest(
        repository=repository, delivery_issue=issue, pull_request=pr,
        head_sha=head, tree_sha=tree, ordered_parent_shas=parents,
        accepted_main_sha=main, changed_files=changed,
    )
    expected_human_authorization_digest = authority.digest_json({
        "authority_identity": HUMAN_AUTHORITY_IDENTITY,
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
        or qualified["qualification_digest"] != authority.digest_json(
            qualified_identity
        )
        or qualified_head == head
        or item["governance_path_prefixes"] != GOVERNANCE_PATH_PREFIXES
        or item["change_digest"] != expected_change_digest
        or signature["signer_identity"] != SOURCE_SIGNER_IDENTITY
        or signature["verified"] is not True
        or signature["signature_evidence_digest"] != authority.digest_json({
            "source_commits": source_commits,
            "accepted_main_sha": main,
        })
        or source_commits[-1]["oid"] != head
        or any(
            entry["signer_identity"] != SOURCE_SIGNER_IDENTITY
            for entry in source_commits
        )
        or source_commits != [
            source_commit_evidence(
                entry["oid"], SOURCE_SIGNER_IDENTITY, main
            )
            for entry in source_commits
        ]
        or len({entry["oid"] for entry in source_commits})
        != len(source_commits)
        or ci["head_sha"] != head or ci["result"] != "PASS"
        or not isinstance(ci["workflow_identity"], str) or not ci["workflow_identity"]
        or qualification["head_sha"] != head or qualification["tree_sha"] != tree
        or qualification["result"] != "PASS"
        or qualification["qualification_digest"] != authority.digest_json({
            "verifier_identity": qualification["verifier_identity"],
            "conversation_id": qualification["conversation_id"],
            "head_sha": head,
            "tree_sha": tree,
            "result": "PASS",
        })
        or validation["accepted_main_sha"] != main or validation["result"] != "PASS"
        or feedback["material_finding_ids"] != []
        or historical != historical_evidence()
        or absence["head_sha"] != head
        or absence["verification_authority"]
        != "PROTECTED_DELIVERY_HISTORY_AND_ARTIFACT_AUDIT"
        or absence["result"] != "NO_HISTORICAL_RECEIPT_ISSUED"
        or necessity["existing_authority_result"] != "INSUFFICIENT"
        or necessity["smaller_nonrecursive_extension"] != "NONE"
        or necessity["recursive_self_bootstrap"] != "PROVEN"
        or history != item["observed_pre_enrollment_history"]
        or item["concepts"] != APPROVED_CONCEPTS
        or item["human_authority_identity"] != HUMAN_AUTHORITY_IDENTITY
        or item["human_authorization_digest"]
        != expected_human_authorization_digest
        or item["authorization_id"]
        != f"governance-amendment:{repository}:{issue}:{pr}"
        or item["bounded_uses"] != 1 or isinstance(item["bounded_uses"], bool)
        or root_authorization["authorized_facts_digest"]
        != authority.digest_json(_authorization_facts(item))
    ):
        raise GovernanceAmendmentError("governance amendment authorization scope changed")
    signer = authority._require_identity(item["signer_identity"], "amendment signer")
    signed = {
        key: copy.deepcopy(entry)
        for key, entry in item.items()
        if key != "authorization_digest"
    }
    digest = authority._require_digest(item["authorization_digest"], "amendment authorization")
    if digest != authority.digest_json(signed):
        raise GovernanceAmendmentError("governance amendment authorization digest mismatch")
    if authenticate_signature:
        trust = _accepted_trust_policy(repository, main)
        try:
            authority._verify_signature(
                authority.canonical_json_bytes(
                    authority._unsigned(
                        item, "authorization_digest", "signature"
                    )
                ),
                item["signature"], signer, DOMAIN, trust.legacy_adoption_signer_identities,
                authority._policy_signature_verifier(trust),
            )
        except authority.LifecycleAuthorityError as exc:
            raise GovernanceAmendmentError("governance amendment signature is invalid") from exc
    return VerifiedGovernanceAmendment(item, _VERIFIED)


def verify(value: Any) -> VerifiedGovernanceAmendment:
    """Verify one signed exact-scope authorization; perform no publication or write."""

    return _verify(value, authenticate_signature=True)


def authenticate_issuance(
    repository: str,
    delivery_issue: int,
    inputs: Mapping[str, Any],
) -> VerifiedGovernanceAmendmentIssuance:
    """Produce and seal exact live facts from narrow external inputs."""

    supplied = copy.deepcopy(dict(inputs)) if isinstance(inputs, Mapping) else None
    if supplied is None or set(supplied) != OBSERVATION_INPUT_FIELDS:
        raise GovernanceAmendmentError(
            "governance amendment observation inputs are not closed"
        )
    actual = produce_observation(repository, delivery_issue, supplied)
    if set(actual) != ISSUANCE_FACT_FIELDS:
        raise GovernanceAmendmentError("amendment issuance facts are not closed")
    return VerifiedGovernanceAmendmentIssuance(
        actual, supplied, _ISSUANCE_VERIFIED
    )


def issue(value: VerifiedGovernanceAmendmentIssuance) -> dict[str, Any]:
    """Issue exactly one root-signed authorization from authenticated facts."""

    if not is_verified_issuance(value):
        raise GovernanceAmendmentError("canonical authenticated issuance is required")
    facts = copy.deepcopy(value.facts)
    repository = authority._require_repository(facts["repository"])
    current = produce_observation(
        repository, facts["delivery_issue"], value.inputs
    )
    if current != facts:
        raise GovernanceAmendmentError(
            "amendment issuance facts changed before signing"
        )
    trust = _accepted_trust_policy(repository, facts["accepted_main_sha"])
    root_identity, root_signer = execution._policy_role_signer(
        trust,
        trust.authority_signer_identities,
        "authority signer role",
        allow_routine_default=False,
    )
    identity, signer = execution._policy_role_signer(
        trust,
        trust.legacy_adoption_signer_identities,
        "legacy-adoption signer role",
        allow_routine_default=False,
    )
    root_fields = {
        "schema_version": "1.0",
        "kind": ROOT_AUTHORIZATION_KIND,
        "domain": ROOT_AUTHORIZATION_DOMAIN,
        "repository": facts["repository"],
        "delivery_issue": facts["delivery_issue"],
        "pull_request": facts["pull_request"],
        "head_sha": facts["head_sha"],
        "tree_sha": facts["tree_sha"],
        "accepted_main_sha": facts["accepted_main_sha"],
        "purpose": facts["purpose"],
        "governance_path_prefixes": copy.deepcopy(
            facts["governance_path_prefixes"]
        ),
        "human_authority_identity": facts["human_authority_identity"],
        "human_authorization_digest": facts["human_authorization_digest"],
        "authorized_facts_digest": authority.digest_json(facts),
        "bounded_uses": 1,
        "signer_identity": root_identity,
    }
    probe_root_signed = {
        **root_fields,
        "signature": {
            "format": "ssh", "signer_identity": root_identity,
            "value": "scope-validation-probe",
        },
    }
    probe_root = {
        **probe_root_signed,
        "authorization_digest": authority.digest_json(probe_root_signed),
    }
    probe_fields = {
        **facts,
        "root_authorization": probe_root,
        "signer_identity": identity,
    }
    probe_signed = {
        **probe_fields,
        "signature": {
            "format": "ssh", "signer_identity": identity,
            "value": "scope-validation-probe",
        },
    }
    _validate_unsigned_scope({
        **probe_signed,
        "authorization_digest": authority.digest_json(probe_signed),
    })
    root_signed = {
        **root_fields,
        "signature": root_signer(
            authority.canonical_json_bytes(root_fields),
            ROOT_AUTHORIZATION_DOMAIN,
        ),
    }
    root_authorization = {
        **root_signed,
        "authorization_digest": authority.digest_json(root_signed),
    }
    fields = {
        **facts,
        "root_authorization": root_authorization,
        "signer_identity": identity,
    }
    signature = signer(authority.canonical_json_bytes(fields), DOMAIN)
    signed = {**fields, "signature": signature}
    document = {**signed, "authorization_digest": authority.digest_json(signed)}
    return verify(document).authorization


def _validate_unsigned_scope(item: Mapping[str, Any]) -> None:
    """Run the closed verifier up to its root-signature boundary."""

    _verify(item, authenticate_signature=False)


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    extra_environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return publication._run_git(
            root,
            arguments,
            input_bytes=input_bytes,
            extra_environment=extra_environment,
        )
    except publication.LifecyclePublicationError as exc:
        raise GovernanceAmendmentError(
            "trusted amendment Git operation failed"
        ) from exc


def _github_json(arguments: list[str], label: str) -> Any:
    result = publication._run_gh(arguments)
    if result.returncode != 0:
        raise GovernanceAmendmentError(f"live {label} is unavailable")
    try:
        return json.loads(
            result.stdout,
            object_pairs_hook=publication._reject_duplicate_pairs,
        )
    except (
        UnicodeDecodeError, json.JSONDecodeError,
        publication.LifecyclePublicationError,
    ) as exc:
        raise GovernanceAmendmentError(f"live {label} is malformed") from exc


def _live_pull_request(repository: str, pull_request: int) -> dict[str, Any]:
    value = _github_json(
        [
            "api", "--hostname", "github.com",
            f"repos/{repository}/pulls/{pull_request}",
        ],
        "governance amendment pull request",
    )
    try:
        return {
            "number": value["number"], "state": value["state"],
            "draft": value["draft"], "merged": value["merged"],
            "head_sha": value["head"]["sha"],
            "head_repository": value["head"]["repo"]["full_name"],
            "base_sha": value["base"]["sha"],
            "base_ref": value["base"]["ref"],
            "base_repository": value["base"]["repo"]["full_name"],
        }
    except (KeyError, TypeError) as exc:
        raise GovernanceAmendmentError(
            "live governance amendment pull request is incomplete"
        ) from exc


def _live_issue(repository: str, delivery_issue: int) -> dict[str, Any]:
    value = _github_json(
        [
            "api", "--hostname", "github.com",
            f"repos/{repository}/issues/{delivery_issue}",
        ],
        "governance amendment issue",
    )
    try:
        return {"number": value["number"], "state": value["state"]}
    except (KeyError, TypeError) as exc:
        raise GovernanceAmendmentError(
            "live governance amendment issue is incomplete"
        ) from exc


def _live_ci(repository: str, head_sha: str) -> dict[str, Any]:
    checks = _github_json(
        [
            "api", "--hostname", "github.com",
            f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100",
        ],
        "governance amendment checks",
    )
    statuses = _github_json(
        [
            "api", "--hostname", "github.com",
            f"repos/{repository}/commits/{head_sha}/status",
        ],
        "governance amendment statuses",
    )
    try:
        runs = sorted(
            ({
                "name": item["name"], "status": item["status"],
                "conclusion": item["conclusion"], "head_sha": item["head_sha"],
            } for item in checks["check_runs"]),
            key=lambda item: (
                item["name"], item["status"], str(item["conclusion"])
            ),
        )
        contexts = sorted(
            ({
                "context": item["context"], "state": item["state"],
                "sha": item["sha"],
            } for item in statuses["statuses"]),
            key=lambda item: item["context"],
        )
    except (KeyError, TypeError) as exc:
        raise GovernanceAmendmentError(
            "live governance amendment CI is incomplete"
        ) from exc
    if (
        not runs or len(runs) >= 100
        or any(
            run["head_sha"] != head_sha or run["status"] != "completed"
            or run["conclusion"] not in {"success", "skipped"}
            for run in runs
        )
        or statuses.get("state") not in {"success", "pending"}
        or (statuses.get("state") == "pending" and contexts)
        or any(
            status["state"] != "success"
            or status["sha"] not in {None, head_sha}
            for status in contexts
        )
    ):
        raise GovernanceAmendmentError(
            "live governance amendment CI is not terminal and passing"
        )
    evidence = {"checks": runs, "statuses": contexts}
    return {
        "head_sha": head_sha,
        "workflow_identity": LIVE_OBSERVATION_VERSION,
        "result": "PASS",
        "evidence_digest": authority.digest_json(evidence),
    }


def _live_feedback(repository: str, pull_request: int, head_sha: str) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){pullRequest(number:$number){"
        "reviewThreads(first:100){nodes{id isResolved isOutdated comments(first:100)"
        "{nodes{body path author{login}} pageInfo{hasNextPage}}} pageInfo{hasNextPage}}"
        "reviews(first:100){nodes{state commit{oid} author{login}} pageInfo{hasNextPage}}"
        "}}}}"
    )
    value = _github_json(
        [
            "api", "--hostname", "github.com", "graphql",
            "-f", f"query={query}", "-f", f"owner={owner}",
            "-f", f"name={name}", "-F", f"number={pull_request}",
        ],
        "governance amendment feedback",
    )
    try:
        observed = value["data"]["repository"]["pullRequest"]
        threads = observed["reviewThreads"]
        reviews = observed["reviews"]
        if (
            value.get("errors") or threads["pageInfo"]["hasNextPage"]
            or reviews["pageInfo"]["hasNextPage"]
            or any(
                item["comments"]["pageInfo"]["hasNextPage"]
                for item in threads["nodes"]
            )
        ):
            raise GovernanceAmendmentError(
                "live governance amendment feedback is incomplete"
            )
        thread_nodes = sorted(threads["nodes"], key=lambda item: item["id"])
        review_nodes = sorted(
            reviews["nodes"],
            key=lambda item: (
                (item.get("author") or {}).get("login") or "",
                item["state"], (item.get("commit") or {}).get("oid") or "",
            ),
        )
    except (KeyError, TypeError) as exc:
        raise GovernanceAmendmentError(
            "live governance amendment feedback is malformed"
        ) from exc
    material = [item["id"] for item in thread_nodes if not item["isResolved"]]
    material.extend(
        "review:" + authority.digest_json(item)
        for item in review_nodes if item["state"] == "CHANGES_REQUESTED"
    )
    inventory = {"threads": thread_nodes}
    return {
        "state_digest": authority.digest_json({
            "head_sha": head_sha, "pull_request": pull_request,
        }),
        "feedback_digest": authority.digest_json({
            **inventory, "reviews": review_nodes,
        }),
        "thread_inventory_digest": authority.digest_json(inventory),
        "material_finding_ids": material,
    }


def _accepted_trust_policy(repository: str, accepted_main_sha: str):
    main = authority._require_oid(accepted_main_sha, "accepted main")
    result = _run_git(ROOT.resolve(), ["show", f"{main}:{REGISTRY_PATH}"])
    if result.returncode != 0:
        raise GovernanceAmendmentError(
            "accepted-main lifecycle trust policy is unavailable"
        )
    try:
        return authority._parse_lifecycle_trust_policy(result.stdout, repository)
    except authority.LifecycleAuthorityError as exc:
        raise GovernanceAmendmentError(
            "accepted-main lifecycle trust policy is invalid"
        ) from exc


def _git_oid(root: Path, expression: str) -> str:
    result = _run_git(root, ["rev-parse", "--verify", expression])
    value = result.stdout.decode("ascii", "strict").strip() if result.returncode == 0 else ""
    try:
        return authority._require_oid(value, "amendment Git identity")
    except authority.LifecycleAuthorityError as exc:
        raise GovernanceAmendmentError("amendment Git identity is unavailable") from exc


def _source_commit_range(
    root: Path, accepted_main_sha: str, head_sha: str,
) -> list[str]:
    ancestry = _run_git(
        root, ["merge-base", "--is-ancestor", accepted_main_sha, head_sha]
    )
    result = _run_git(
        root,
        [
            "rev-list", "--reverse", "--topo-order",
            f"{accepted_main_sha}..{head_sha}",
        ],
    )
    commits = (
        result.stdout.decode("ascii", "strict").splitlines()
        if result.returncode == 0 else []
    )
    if ancestry.returncode != 0 or ancestry.stdout or not commits:
        raise GovernanceAmendmentError(
            "governance amendment source ancestry is not exact"
        )
    return [
        authority._require_oid(commit, "governance source commit")
        for commit in commits
    ]


def _git_changed_files(
    root: Path, accepted_main_sha: str, head_sha: str,
) -> list[dict[str, Any]]:
    result = _run_git(
        root,
        [
            "diff-tree", "--no-commit-id", "--name-only", "-r",
            accepted_main_sha, head_sha,
        ],
    )
    paths = (
        sorted(result.stdout.decode("utf-8", "strict").splitlines())
        if result.returncode == 0 else []
    )
    changed: list[dict[str, Any]] = []
    for path in paths:
        listing = _run_git(root, ["ls-tree", head_sha, "--", path])
        try:
            metadata, observed_path = listing.stdout.decode(
                "utf-8", "strict"
            ).rstrip("\n").split("\t", 1)
            mode, kind, oid = metadata.split()
        except ValueError as exc:
            raise GovernanceAmendmentError(
                "live governance amendment path identity is malformed"
            ) from exc
        if (
            listing.returncode != 0 or observed_path != path or kind != "blob"
        ):
            raise GovernanceAmendmentError(
                "live governance amendment path identity changed"
            )
        changed.append({"path": path, "blob_oid": oid, "mode": mode})
    return _changed_files(changed, GOVERNANCE_PATH_PREFIXES)


def produce_observation(
    repository: str, delivery_issue: int, authenticated_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently rebuild every live fact before maintained signing."""

    if not isinstance(authenticated_inputs, Mapping):
        raise GovernanceAmendmentError(
            "governance amendment root inputs are missing"
        )
    inputs = copy.deepcopy(dict(authenticated_inputs))
    if set(inputs) != OBSERVATION_INPUT_FIELDS:
        raise GovernanceAmendmentError(
            "governance amendment root inputs are not closed"
        )
    root = ROOT.resolve()
    accepted_main = authority._require_oid(
        inputs["accepted_main_sha"], "accepted main"
    )
    trust = _accepted_trust_policy(repository, accepted_main)
    remote = trust.publication_remote_url
    if _observe_remote_main(root, remote) != accepted_main:
        raise GovernanceAmendmentError(
            "protected main changed before live observation"
        )
    pull_request = authority._require_positive_int(
        inputs["pull_request"], "pull request"
    )
    pull = _live_pull_request(repository, pull_request)
    issue = _live_issue(repository, delivery_issue)
    if (
        pull != {
            "number": pull_request, "state": "open", "draft": True,
            "merged": False,
            "head_sha": inputs["independent_qualification"]["head_sha"],
            "head_repository": repository, "base_sha": accepted_main,
            "base_ref": "main", "base_repository": repository,
        }
        or issue != {"number": delivery_issue, "state": "open"}
    ):
        raise GovernanceAmendmentError(
            "live governance amendment delivery identity or state changed"
        )
    head = authority._require_oid(pull["head_sha"], "amendment head")
    tree = _git_oid(root, head + "^{tree}")
    parents_result = _run_git(root, ["show", "-s", "--format=%P", head])
    parents = (
        parents_result.stdout.decode("ascii", "strict").strip().split()
        if parents_result.returncode == 0 else []
    )
    parents = [
        authority._require_oid(parent, "amendment parent")
        for parent in parents
    ]
    changed = _git_changed_files(root, accepted_main, head)
    commits = _source_commit_range(root, accepted_main, head)
    for commit in commits:
        _verify_commit_against_accepted_trust(
            root, commit, SOURCE_SIGNER_IDENTITY, trust
        )
    source_commits = [
        source_commit_evidence(commit, SOURCE_SIGNER_IDENTITY, accepted_main)
        for commit in commits
    ]
    qualification = copy.deepcopy(inputs["independent_qualification"])
    if (
        not isinstance(qualification, dict)
        or qualification.get("head_sha") != head
        or qualification.get("tree_sha") != tree
        or qualification.get("result") != "PASS"
        or qualification.get("qualification_digest")
        != authority.digest_json({
            "verifier_identity": qualification.get("verifier_identity"),
            "conversation_id": qualification.get("conversation_id"),
            "head_sha": head, "tree_sha": tree, "result": "PASS",
        })
    ):
        raise GovernanceAmendmentError(
            "independent exact-source qualification is invalid"
        )
    observed = {
        "schema_version": "1.0", "kind": KIND, "domain": DOMAIN,
        "purpose": PURPOSE, "repository": repository,
        "delivery_issue": delivery_issue, "pull_request": pull_request,
        "pull_request_state": "OPEN",
        "qualified_source": copy.deepcopy(inputs["qualified_source"]),
        "head_sha": head,
        "tree_sha": tree,
        "ordered_parent_shas": parents,
        "accepted_main_sha": accepted_main,
        "governance_path_prefixes": copy.deepcopy(GOVERNANCE_PATH_PREFIXES),
        "changed_files": changed,
        "change_digest": change_digest(
            repository=repository, delivery_issue=delivery_issue,
            pull_request=pull_request, head_sha=head, tree_sha=tree,
            ordered_parent_shas=parents, accepted_main_sha=accepted_main,
            changed_files=changed,
        ),
        "source_signature": {
            "signer_identity": SOURCE_SIGNER_IDENTITY,
            "signature_evidence_digest": authority.digest_json({
                "source_commits": source_commits,
                "accepted_main_sha": accepted_main,
            }),
            "verified": True,
        },
        "source_commits": source_commits,
        "natural_ci": _live_ci(repository, head),
        "independent_qualification": qualification,
        "current_validation": copy.deepcopy(inputs["current_validation"]),
        "feedback": _live_feedback(repository, pull_request, head),
        "observed_pre_enrollment_history": copy.deepcopy(
            inputs["observed_pre_enrollment_history"]
        ),
        "intended_state": copy.deepcopy(inputs["intended_state"]),
        "historical_evidence": copy.deepcopy(inputs["historical_evidence"]),
        "historical_absence_proof": copy.deepcopy(
            inputs["historical_absence_proof"]
        ),
        "concepts": copy.deepcopy(APPROVED_CONCEPTS),
        "architecture_necessity": copy.deepcopy(
            inputs["architecture_necessity"]
        ),
        "human_authority_identity": inputs["human_authority_identity"],
        "human_authorization_digest": inputs["human_authorization_digest"],
        "authorization_id": inputs["authorization_id"],
        "bounded_uses": inputs["bounded_uses"],
    }
    return observed


def _verify_commit_against_accepted_trust(
    root: Path, commit_oid: str, signer_identity: str,
    trust: authority.LifecycleTrustPolicy,
) -> None:
    oid = authority._require_oid(commit_oid, "amendment signed commit")
    identity = authority._require_identity(
        signer_identity, "amendment commit signer"
    )
    signer = trust.signers.get(identity)
    if signer is None or not signer.ssh_public_keys:
        raise GovernanceAmendmentError(
            "amendment signer has no accepted-main SSH key"
        )
    with tempfile.TemporaryDirectory(
        prefix="secpal-governance-amendment-signers-"
    ) as directory:
        allowed = Path(directory) / "allowed-signers"
        allowed.write_text(
            "".join(f"{identity} {key}\n" for key in signer.ssh_public_keys),
            encoding="utf-8",
        )
        allowed.chmod(0o600)
        result = _run_git(
            root,
            [
                "-c", f"gpg.ssh.allowedSignersFile={allowed}",
                "verify-commit", "--raw", oid,
            ],
        )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    principals = re.findall(
        r'(?m)^Good "git" signature for ([^\r\n]+) with ', output
    )
    if result.returncode != 0 or principals != [identity]:
        raise GovernanceAmendmentError(
            "amendment commit is not signed by an accepted-main key"
        )


def _remote_url(repository: str, accepted_main_sha: str) -> str:
    trust = _accepted_trust_policy(repository, accepted_main_sha)
    value = trust.publication_remote_url
    if not isinstance(value, str) or not value:
        raise GovernanceAmendmentError("maintained repository remote is unavailable")
    return value


def _push_credentials(repository: str, accepted_main_sha: str):
    policy = _accepted_trust_policy(repository, accepted_main_sha)
    return publication._isolated_repository(policy, write=True)


def _push_protected_main(
    root: Path, remote: str, merge_oid: str, repository: str,
    accepted_main_sha: str,
) -> None:
    with _push_credentials(
        repository, accepted_main_sha
    ) as (_, credential_environment):
        pushed = _run_git(
            root,
            ["push", "--porcelain", remote, f"{merge_oid}:{ACCEPTED_MAIN_REF}"],
            extra_environment=credential_environment,
        )
    if pushed.returncode != 0:
        raise GovernanceAmendmentError(
            "protected main changed during amendment compare-and-swap"
        )


def _observe_remote_main(root: Path, remote: str) -> str:
    result = _run_git(root, ["ls-remote", remote, ACCEPTED_MAIN_REF])
    fields = (
        result.stdout.decode("ascii", "strict").strip().split()
        if result.returncode == 0
        else []
    )
    if len(fields) != 2 or fields[1] != ACCEPTED_MAIN_REF:
        raise GovernanceAmendmentError("protected main cannot be authenticated")
    return authority._require_oid(fields[0], "protected main")


def _consumption_record(authorization: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version": "1.0",
        "kind": CONSUMPTION_KIND,
        "domain": CONSUMPTION_DOMAIN,
        "repository": authorization["repository"],
        "delivery_issue": authorization["delivery_issue"],
        "pull_request": authorization["pull_request"],
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["authorization_digest"],
        "accepted_main_sha": authorization["accepted_main_sha"],
        "head_sha": authorization["head_sha"],
        "tree_sha": authorization["tree_sha"],
        "ordered_parent_shas": copy.deepcopy(authorization["ordered_parent_shas"]),
        "change_digest": authorization["change_digest"],
        "operation": "EXACT_PROTECTED_MAIN_GOVERNANCE_AMENDMENT",
        "bounded_uses": 1,
    }
    return {**fields, "consumption_digest": authority.digest_json(fields)}


def _merge_message(authorization: Mapping[str, Any], consumption: Mapping[str, Any]) -> bytes:
    encoded = base64.b64encode(authority.canonical_json_bytes(authorization)).decode("ascii")
    encoded_consumption = base64.b64encode(
        authority.canonical_json_bytes(consumption)
    ).decode("ascii")
    return (
        "Governance amendment for "
        f"#{authorization['delivery_issue']} (#{authorization['pull_request']})\n\n"
        f"SecPal-Governance-Amendment-Authorization: {encoded}\n"
        f"SecPal-Governance-Amendment-Digest: {authorization['authorization_digest']}\n"
        f"SecPal-Governance-Amendment-Consumption: {encoded_consumption}\n"
        f"SecPal-Governance-Amendment-Consumption-Digest: {consumption['consumption_digest']}\n"
    ).encode("utf-8")


def _observation_inputs(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(item[key]) for key in OBSERVATION_INPUT_FIELDS
    }


def _authenticate_execution(
    verified: VerifiedGovernanceAmendment, root: Path, remote: str
) -> None:
    item = verified.authorization
    expected_facts = {
        key: copy.deepcopy(value)
        for key, value in item.items()
        if key not in {
            "root_authorization", "signer_identity", "signature",
            "authorization_digest",
        }
    }
    current_facts = produce_observation(
        item["repository"], item["delivery_issue"],
        _observation_inputs(item),
    )
    if current_facts != expected_facts:
        raise GovernanceAmendmentError(
            "live amendment prerequisites changed before consumption"
        )
    if _observe_remote_main(root, remote) != item["accepted_main_sha"]:
        raise GovernanceAmendmentError("protected main changed before amendment consumption")
    if _git_oid(root, item["head_sha"] + "^{tree}") != item["tree_sha"]:
        raise GovernanceAmendmentError("amendment tree changed")
    parents = _run_git(root, ["show", "-s", "--format=%P", item["head_sha"]])
    observed_parents = (
        parents.stdout.decode("ascii", "strict").strip().split()
        if parents.returncode == 0
        else []
    )
    if observed_parents != item["ordered_parent_shas"]:
        raise GovernanceAmendmentError("amendment parents changed")
    trust = _accepted_trust_policy(
        item["repository"], item["accepted_main_sha"]
    )
    commits = _source_commit_range(
        root, item["accepted_main_sha"], item["head_sha"]
    )
    if commits != [entry["oid"] for entry in item["source_commits"]]:
        raise GovernanceAmendmentError("amendment source commit range changed")
    for commit, evidence in zip(commits, item["source_commits"], strict=True):
        _verify_commit_against_accepted_trust(
            root, commit, evidence["signer_identity"], trust,
        )
    changed = _run_git(
        root,
        [
            "diff-tree", "--no-commit-id", "--name-only", "-r",
            item["accepted_main_sha"], item["head_sha"],
        ],
    )
    paths = (
        sorted(changed.stdout.decode("utf-8", "strict").splitlines())
        if changed.returncode == 0
        else []
    )
    if paths != [entry["path"] for entry in item["changed_files"]]:
        raise GovernanceAmendmentError("amendment path set changed")
    for entry in item["changed_files"]:
        listing = _run_git(
            root, ["ls-tree", item["head_sha"], "--", entry["path"]]
        )
        expected = (
            f"{entry['mode']} blob {entry['blob_oid']}\t{entry['path']}\n"
        ).encode("utf-8")
        if listing.returncode != 0 or listing.stdout != expected:
            raise GovernanceAmendmentError("amendment changed-file identity changed")
    # A prior accepted-main occurrence is the immutable replay ledger.
    log = _run_git(root, ["log", "--format=%B%x00", item["accepted_main_sha"]])
    if item["authorization_digest"].encode("ascii") in log.stdout:
        raise GovernanceAmendmentError("governance amendment authorization was already consumed")


def execute(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Consume once by a signed, two-parent, fast-forward main adoption."""

    verified = verify(value)
    item = verified.authorization
    root = ROOT.resolve()
    remote = _remote_url(item["repository"], item["accepted_main_sha"])
    _authenticate_execution(verified, root, remote)
    consumption = _consumption_record(item)
    message = _merge_message(item, consumption)
    commit = _run_git(
        root,
        [
            "commit-tree", "-S", item["tree_sha"],
            "-p", item["accepted_main_sha"], "-p", item["head_sha"],
        ],
        input_bytes=message,
    )
    merge_oid = commit.stdout.decode("ascii", "strict").strip() if commit.returncode == 0 else ""
    try:
        authority._require_oid(merge_oid, "amendment merge commit")
    except authority.LifecycleAuthorityError as exc:
        raise GovernanceAmendmentError(
            "signed amendment merge commit could not be created"
        ) from exc
    trust = _accepted_trust_policy(
        item["repository"], item["accepted_main_sha"]
    )
    _verify_commit_against_accepted_trust(
        root, merge_oid, item["source_signature"]["signer_identity"], trust,
    )
    if (
        _git_oid(root, merge_oid + "^{tree}") != item["tree_sha"]
        or _run_git(
            root, ["show", "-s", "--format=%P", merge_oid]
        ).stdout.decode("ascii", "strict").strip().split()
        != [item["accepted_main_sha"], item["head_sha"]]
        or _run_git(
            root, ["show", "-s", "--format=%B", merge_oid]
        ).stdout.rstrip(b"\n") + b"\n" != message
    ):
        raise GovernanceAmendmentError("local amendment commit verification failed")
    _push_protected_main(
        root, remote, merge_oid, item["repository"], item["accepted_main_sha"]
    )
    if _observe_remote_main(root, remote) != merge_oid:
        raise GovernanceAmendmentError("accepted amendment read-back changed identity")
    fetched = _run_git(root, ["fetch", "--quiet", "--no-tags", remote, merge_oid])
    if fetched.returncode != 0:
        raise GovernanceAmendmentError("accepted amendment cannot be read back")
    if (
        _git_oid(root, merge_oid + "^{tree}") != item["tree_sha"]
        or _run_git(
            root, ["show", "-s", "--format=%P", merge_oid]
        ).stdout.decode("ascii", "strict").strip().split()
        != [item["accepted_main_sha"], item["head_sha"]]
        or _run_git(
            root, ["show", "-s", "--format=%B", merge_oid]
        ).stdout.rstrip(b"\n") + b"\n" != message
    ):
        raise GovernanceAmendmentError("accepted amendment immutable read-back failed")
    return {
        "status": "CONSUMED",
        "authorization_id": item["authorization_id"],
        "authorization_digest": item["authorization_digest"],
        "consumption_digest": consumption["consumption_digest"],
        "merge_commit_sha": merge_oid,
        "accepted_main_sha": merge_oid,
        "head_sha": item["head_sha"],
        "tree_sha": item["tree_sha"],
        "bounded_uses_consumed": 1,
    }
