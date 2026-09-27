# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authenticate one accepted-main legacy-enrolled package-loss fact."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from . import bootstrap_source_admission as transport
from . import fast_path
from . import lifecycle_authority as authority
from . import lifecycle_publication as publication
from . import validation_evidence_loss


KIND = "SECPAL_LEGACY_ENROLLED_PACKAGE_LOSS_AUTHENTICATION"
DOMAIN = "secpal.legacy-enrolled-package-loss-authentication/v1"
ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/legacy-enrolled-package-loss.json"
REGISTRY_PATH = ".agents/skills/secpal-pr-review/references/repositories.json"
REGISTRY_SCHEMA_PATH = (
    ".agents/skills/secpal-pr-review/references/repositories.schema.json"
)
_VERIFIED = object()

RECORD_FIELDS = frozenset({
    "schema_version", "kind", "repository", "delivery_issue", "pull_request",
    "lifecycle_id", "historical_proof_mode", "proof_version",
    "current_publication_oid", "current_publication_digest", "head_sha",
    "tree_sha", "parent_sha", "source_signer_identity",
    "commit_signature_evidence_digest", "historical_provider_summary_digest",
    "evidence_time_registry_digest",
    "historical_command_set_digest", "source_validation_evidence_digest",
    "historical_validation_receipt_digest",
    "historical_final_attestation_digest", "source_history",
    "persistence_contract", "historical_package_status",
    "historical_bytes_reconstructed", "package_store_survey_digest",
    "record_digest",
})
HISTORY_FIELDS = frozenset({"head_sha", "tree_sha", "parent_sha"})
PERSISTENCE_FIELDS = frozenset({
    "historical_output_scope", "local_package_directory",
    "artifact_basenames", "maintained_durable_stores",
    "unsurveyed_maintained_stores", "retained_local_store",
})
EXPECTED_DURABLE_STORES = [
    "DELIVERY_SOURCE_HISTORY",
    "PROTECTED_LIFECYCLE_PUBLICATION",
]
CURRENT_SAFETY_OPERATION = "READY_INTEGRATION_PRIOR_AUTHORITY"


@dataclass(frozen=True)
class ProviderObservation:
    """Bounded provider bytes captured before semantic admission."""

    pull_request: bytes
    issue: bytes
    commit: bytes
    chronology: validation_evidence_loss.ChronologyObservation


@dataclass(frozen=True)
class ProviderFacts:
    pull_request: dict[str, Any]
    issue: dict[str, Any]
    commit: dict[str, Any]
    chronology: tuple[validation_evidence_loss.ChronologyEvent, ...]


@dataclass(frozen=True)
class VerifiedLegacyEnrolledPackageLoss:
    canonical_authentication: dict[str, Any]
    _verification_seal: object


@dataclass(frozen=True)
class VerifiedLegacyProviderHeadBinding:
    repository: str
    delivery_issue: int
    pull_request: int
    lifecycle_id: str
    current_head_sha: str
    provider_head_sha: str
    current_authority_digest: str
    current_publication_oid: str
    current_publication_digest: str
    adoption_proof_digest: str
    historical_provider_summary_digest: str

    def _reauthenticate(self) -> None:
        _main, record, _entry = _accepted_policy(
            self.repository, self.delivery_issue
        )
        current = publication.verify_current_lifecycle_authority(
            self.repository, self.delivery_issue
        )
        authenticated = _provider_head_binding(current, record)
        if authenticated != self:
            raise fast_path.SecurityBlocker(
                "legacy enrolled provider-head binding is stale or substituted"
            )

    def provider_head(
        self, *, repository: str, pull_request: int, current_head_sha: str,
    ) -> str:
        if (
            repository != self.repository
            or pull_request != self.pull_request
            or current_head_sha != self.current_head_sha
        ):
            raise fast_path.SecurityBlocker(
                "legacy enrolled provider-head binding is stale or substituted"
            )
        self._reauthenticate()
        return self.provider_head_sha

    def verify_historical_provider_summary(
        self,
        *,
        body: Any,
        repository: str,
        pull_request: int,
        current_head_sha: str,
    ) -> None:
        """Admit the exact pre-dual-review provider summary, never a new review."""

        if (
            repository != self.repository
            or pull_request != self.pull_request
            or current_head_sha != self.current_head_sha
            or not isinstance(body, str)
            or len(body.encode("utf-8")) > 64 * 1024
            or fast_path.digest_text(body)
            != self.historical_provider_summary_digest
        ):
            raise fast_path.SecurityBlocker(
                "legacy enrolled provider summary is stale or substituted"
            )
        code_rows = [
            line for line in body.splitlines() if "**Code Review**" in line
        ]
        security_rows = [
            line for line in body.splitlines() if "**Security Review**" in line
        ]
        if (
            body.count(fast_path.CODEX_REVIEW_SUMMARY_MARKER) != 1
            or len(code_rows) != 1
            or security_rows
            or "✅ **Completed**" not in code_rows[0]
            or f"`{self.provider_head_sha[:7]}`" not in code_rows[0]
        ):
            raise fast_path.SecurityBlocker(
                "legacy enrolled provider summary is invalid"
            )
        self._reauthenticate()


def _gh_projection(endpoint: str, projection: str, label: str) -> bytes:
    try:
        result = transport._run_bootstrap_gh([
            "api", "--hostname", "github.com", endpoint, "--jq", projection,
        ])
    except transport.BootstrapSourceAdmissionError as exc:
        raise authority.LifecycleAuthorityError(
            f"legacy package-loss {label} acquisition failed"
        ) from exc
    if result.returncode != 0:
        raise authority.LifecycleAuthorityError(
            f"legacy package-loss {label} acquisition failed"
        )
    return bytes(result.stdout)


def _observe_provider(record: Mapping[str, Any]) -> ProviderObservation:
    """Observe only the exact live identities needed by this authentication."""

    repository = record["repository"]
    pull_request = record["pull_request"]
    return ProviderObservation(
        pull_request=_gh_projection(
            f"repos/{repository}/pulls/{pull_request}",
            (
                '{"number":.number,"state":.state,"draft":.draft,'
                '"head_sha":.head.sha,"head_repository":.head.repo.full_name,'
                '"base_repository":.base.repo.full_name,"base_ref":.base.ref,'
                '"merged":(.merged_at!=null)}'
            ),
            "pull-request",
        ),
        issue=_gh_projection(
            f"repos/{repository}/issues/{record['delivery_issue']}",
            '{"number":.number,"state":.state}',
            "issue",
        ),
        commit=_gh_projection(
            f"repos/{repository}/commits/{record['head_sha']}",
            (
                '{"sha":.sha,"tree_sha":.commit.tree.sha,'
                '"parents":[.parents[].sha],'
                '"verified":.commit.verification.verified}'
            ),
            "commit",
        ),
        chronology=validation_evidence_loss._observe_chronology(
            repository, pull_request
        ),
    )


def _closed_provider_document(raw: bytes, fields: set[str], label: str) -> dict[str, Any]:
    return copy.deepcopy(
        authority._require_closed(
            authority.loads_closed_json(raw), fields, label,
        )
    )


def _normalize_provider(
    observation: ProviderObservation, record: Mapping[str, Any],
) -> ProviderFacts:
    """Purely normalize bounded provider representations into canonical facts."""

    if not isinstance(observation, ProviderObservation):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss provider observation is malformed"
        )
    pull_request = _closed_provider_document(
        observation.pull_request,
        {
            "number", "state", "draft", "head_sha", "head_repository",
            "base_repository", "base_ref", "merged",
        },
        "legacy package-loss pull request",
    )
    issue = _closed_provider_document(
        observation.issue, {"number", "state"}, "legacy package-loss issue"
    )
    commit = _closed_provider_document(
        observation.commit,
        {"sha", "tree_sha", "parents", "verified"},
        "legacy package-loss commit",
    )
    chronology = validation_evidence_loss._normalize_chronology(
        observation.chronology, record["repository"], record["pull_request"]
    )
    return ProviderFacts(pull_request, issue, commit, chronology)


def _admit_provider(facts: ProviderFacts, record: Mapping[str, Any]) -> None:
    """Admit only the exact live open Ready delivery and immutable commit."""

    if not isinstance(facts, ProviderFacts):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss provider facts are not normalized"
        )
    target = facts.pull_request
    issue = facts.issue
    commit = facts.commit
    ready = [item for item in facts.chronology if item.kind == "ready_for_review"]
    draft = [item for item in facts.chronology if item.kind == "convert_to_draft"]
    if (
        target.get("number") != record["pull_request"]
        or str(target.get("state", "")).upper() != "OPEN"
        or target.get("draft") is not False
        or target.get("merged") is not False
        or target.get("head_sha") != record["head_sha"]
        or target.get("head_repository") != record["repository"]
        or target.get("base_repository") != record["repository"]
        or target.get("base_ref") != "main"
        or issue.get("number") != record["delivery_issue"]
        or str(issue.get("state", "")).upper() != "OPEN"
        or commit.get("sha") != record["head_sha"]
        or commit.get("tree_sha") != record["tree_sha"]
        or commit.get("parents") != [record["parent_sha"]]
        or commit.get("verified") is not True
        or len(ready) != 1
        or draft
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss live delivery identity or Ready history changed"
        )


def _validate_persistence_contract(value: Any) -> dict[str, Any]:
    contract = copy.deepcopy(
        authority._require_closed(
            value, PERSISTENCE_FIELDS, "legacy package persistence contract"
        )
    )
    artifacts = contract["artifact_basenames"]
    if (
        contract["historical_output_scope"]
        != "CALLER_SELECTED_GITIGNORED_LOCAL_SESSION"
        or contract["local_package_directory"] != ".context/"
        or not isinstance(artifacts, list)
        or artifacts != sorted(artifacts)
        or len(artifacts) != len(set(artifacts))
        or any(
            not isinstance(item, str)
            or PurePosixPath(item).name != item
            or not item.endswith(".json")
            for item in artifacts
        )
        or contract["maintained_durable_stores"] != EXPECTED_DURABLE_STORES
        or contract["unsurveyed_maintained_stores"] != []
        or contract["retained_local_store"] != "NO_MAINTAINED_RETAINED_STORE"
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package persistence boundary is incomplete or ambiguous"
        )
    return contract


def _validate_record(value: Any) -> dict[str, Any]:
    record = copy.deepcopy(
        authority._require_closed(value, RECORD_FIELDS, "legacy package-loss record")
    )
    if (
        record["schema_version"] != "1.0"
        or record["kind"] != KIND
        or record["repository"] != "SecPal/.github"
        or record["historical_proof_mode"] != "exact_state_adoption"
        or record["proof_version"] != "1.0"
        or record["historical_package_status"] != "UNAVAILABLE"
        or record["historical_bytes_reconstructed"] is not False
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss record cannot backdate or reconstruct authority"
        )
    authority._require_repository(record["repository"])
    for field in ("delivery_issue", "pull_request"):
        authority._require_positive_int(record[field], field)
    for field in (
        "current_publication_oid", "head_sha", "tree_sha", "parent_sha",
    ):
        authority._require_oid(record[field], field)
    for field in (
        "current_publication_digest", "commit_signature_evidence_digest",
        "historical_provider_summary_digest",
        "evidence_time_registry_digest", "historical_command_set_digest",
        "source_validation_evidence_digest",
        "historical_validation_receipt_digest",
        "historical_final_attestation_digest", "package_store_survey_digest",
        "record_digest",
    ):
        authority._require_digest(record[field], field)
    for field in ("lifecycle_id", "source_signer_identity"):
        authority._require_identity(record[field], field)
    history = record["source_history"]
    if not isinstance(history, list) or not history:
        raise authority.LifecycleAuthorityError(
            "legacy package source history is unavailable"
        )
    normalized_history: list[dict[str, str]] = []
    for index, raw in enumerate(history):
        item = copy.deepcopy(
            authority._require_closed(raw, HISTORY_FIELDS, "legacy package source")
        )
        for field in HISTORY_FIELDS:
            authority._require_oid(item[field], field)
        if index and item["parent_sha"] != normalized_history[-1]["head_sha"]:
            raise authority.LifecycleAuthorityError(
                "legacy package source history topology is invalid"
            )
        normalized_history.append(item)
    if (
        normalized_history[-1]["head_sha"] != record["head_sha"]
        or normalized_history[-1]["tree_sha"] != record["tree_sha"]
        or normalized_history[-1]["parent_sha"] != record["parent_sha"]
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package source history tip changed"
        )
    record["source_history"] = normalized_history
    record["persistence_contract"] = _validate_persistence_contract(
        record["persistence_contract"]
    )
    unsigned = {key: item for key, item in record.items() if key != "record_digest"}
    if authority.digest_json(unsigned) != record["record_digest"]:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss policy record digest changed"
        )
    return record


def _accepted_policy(
    repository: str, delivery_issue: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Select the sole exact record from clean authenticated protected main."""

    if repository != "SecPal/.github":
        raise authority.LifecycleAuthorityError(
            "legacy package-loss repository is not maintained"
        )
    authority._require_positive_int(delivery_issue, "legacy package-loss issue")
    branch = _closed_provider_document(
        _gh_projection(
            "repos/SecPal/.github/branches/main",
            '{"sha":.commit.sha,"protected":.protected}',
            "protected-main",
        ),
        {"sha", "protected"},
        "legacy package-loss protected main",
    )
    main = authority._require_oid(branch["sha"], "protected main")
    commit = validation_evidence_loss._accepted_main_commit_metadata(main)
    if branch["protected"] is not True or commit != {"sha": main, "verified": True}:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss policy requires authenticated protected main"
        )
    if (
        transport._git_text(ROOT, ["rev-parse", "HEAD"]).strip() != main
        or transport._git_text(
            ROOT, ["status", "--porcelain=v2", "--untracked-files=all"]
        )
    ):
        raise authority.LifecycleAuthorityError(
            "candidate-local legacy package-loss self-authentication is forbidden"
        )
    trusted_paths = {
        POLICY_PATH,
        REGISTRY_PATH,
        REGISTRY_SCHEMA_PATH,
        "scripts/secpal-pr-review-actions.py",
        "scripts/secpal_pr_review/fast_path.py",
        "scripts/secpal_pr_review/legacy_enrolled_package_loss.py",
        "scripts/secpal_pr_review/lifecycle_authority.py",
        "scripts/secpal_pr_review/lifecycle_publication.py",
    }
    for relative in sorted(trusted_paths):
        actual = transport._git_text(
            ROOT, ["hash-object", "--no-filters", relative]
        ).strip()
        expected = transport._git_text(
            ROOT, ["rev-parse", f"{main}:{relative}"]
        ).strip()
        if actual != expected:
            raise authority.LifecycleAuthorityError(
                "accepted-main legacy package-loss code or policy changed"
            )
    policy = authority.loads_closed_json((ROOT / POLICY_PATH).read_bytes())
    if (
        not isinstance(policy, dict)
        or set(policy) != {"schema_version", "authentications"}
        or policy["schema_version"] != "1.0"
        or not isinstance(policy["authentications"], list)
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss policy is malformed"
        )
    matches = [
        item for item in policy["authentications"]
        if isinstance(item, dict)
        and item.get("repository") == repository
        and item.get("delivery_issue") == delivery_issue
    ]
    if len(matches) != 1:
        raise authority.LifecycleAuthorityError(
            "no unique accepted-main legacy package-loss authentication"
        )
    record = _validate_record(matches[0])
    registry = fast_path.validate_repository_registry_structure(
        authority.loads_closed_json((ROOT / REGISTRY_PATH).read_bytes())
    )
    entries = [
        item for item in registry["repositories"]
        if item.get("repository") == repository
    ]
    if len(entries) != 1:
        raise authority.LifecycleAuthorityError(
            "current repository admission is ambiguous"
        )
    return main, record, copy.deepcopy(entries[0])


def _proof_bundle(current: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = getattr(current, "serialized_lifecycle_evidence", None)
    if raw is None:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss CURRENT lifecycle evidence is unavailable"
        )
    bundle = authority.loads_closed_json(raw)
    try:
        proof = bundle["exact_state_adoption_proof"]
        verified = authority.verify_exact_state_adoption_proof(proof)
    except (KeyError, TypeError, authority.LifecycleAuthorityError) as exc:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss adoption proof is invalid"
        ) from exc
    if verified != current.lifecycle:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss adoption proof differs from CURRENT"
        )
    return bundle, proof


def _admit_current(
    current: Any, record: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle, proof = _proof_bundle(current)
    state = current.lifecycle.state
    ready_history = state.get("ready_history") if isinstance(state, dict) else None
    source_heads = []
    for item in proof.get("observed_pre_enrollment_history", []):
        head = item.get("head_sha") if isinstance(item, dict) else None
        if head not in source_heads:
            source_heads.append(head)
    expected_support = {
        record["commit_signature_evidence_digest"],
        record["source_validation_evidence_digest"],
        record["historical_validation_receipt_digest"],
        record["historical_final_attestation_digest"],
        proof.get("observed_history_digest"),
    }
    if (
        proof.get("schema_version") != "1.0"
        or proof.get("proof_version") != "1.0"
        or proof.get("historical_proof_mode") != "exact_state_adoption"
        or proof.get("repository") != record["repository"]
        or proof.get("delivery_issue") != record["delivery_issue"]
        or proof.get("pull_request") != record["pull_request"]
        or proof.get("head_sha") != record["head_sha"]
        or proof.get("tree_sha") != record["tree_sha"]
        or proof.get("commit_signature_evidence_digest")
        != record["commit_signature_evidence_digest"]
        or proof.get("source_validation_evidence_digest")
        != record["source_validation_evidence_digest"]
        or proof.get("validation_receipt_digest")
        != record["historical_validation_receipt_digest"]
        or proof.get("adoption_source_evidence_digest")
        != record["historical_final_attestation_digest"]
        or not expected_support.issubset(set(proof.get("supporting_evidence_digests", [])))
        or [item["head_sha"] for item in record["source_history"]] != source_heads
        or proof.get("ordinary_lifecycle_events") != []
        or proof.get("head_advanced_count") != 0
        or bundle.get("transition_authorizations") != []
        or bundle.get("authority_chain") != []
        or current.publication_oid != record["current_publication_oid"]
        or current.publication_digest != record["current_publication_digest"]
        or current.predecessor_publication_oid is not None
        or current.lifecycle.repository != record["repository"]
        or current.lifecycle.delivery_issue != record["delivery_issue"]
        or current.lifecycle.pull_request != record["pull_request"]
        or current.lifecycle.lifecycle_id != record["lifecycle_id"]
        or current.lifecycle.head_sha != record["head_sha"]
        or current.lifecycle.tree_sha != record["tree_sha"]
        or current.lifecycle.historical_proof_mode != "exact_state_adoption"
        or current.lifecycle.authority_digest != proof.get("proof_digest")
        or state.get("draft") is not False
        or state.get("ready") is not True
        or state.get("unrestricted_review_count") != 1
        or isinstance(state.get("unrestricted_review_count"), bool)
        or state.get("remediation_cycle_count") != 2
        or isinstance(state.get("remediation_cycle_count"), bool)
        or state.get("ready_transition_count") != 1
        or isinstance(state.get("ready_transition_count"), bool)
        or not isinstance(ready_history, list)
        or len(ready_history) != 1
        or set(ready_history[0])
        != {"sequence", "transition_kind", "observation_digest"}
        or ready_history[0].get("sequence") != 1
        or ready_history[0].get("transition_kind") != "DRAFT_TO_READY"
        or state.get("exceptional_recovery_count") != 0
        or state.get("exceptional_recovery_history") != []
        or state.get("exceptional_continuation_count") != 0
        or state.get("exceptional_continuation_history") != []
        or state.get("cycle_3_absent") is not True
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss CURRENT or historical authority changed"
        )
    authority._require_digest(
        ready_history[0]["observation_digest"], "legacy Ready observation"
    )
    return bundle, proof


def _provider_head_binding(
    current: Any, record: Mapping[str, Any]
) -> VerifiedLegacyProviderHeadBinding:
    _bundle, proof = _proof_bundle(current)
    history = proof.get("observed_pre_enrollment_history")
    reviews = [
        item for item in history or []
        if isinstance(item, dict) and item.get("kind") == "REVIEW_SUBMITTED"
    ]
    if (
        not isinstance(history, list)
        or len(reviews) != 1
        or reviews[0].get("reviewed_head_sha") is None
    ):
        raise fast_path.SecurityBlocker(
            "legacy enrolled provider-head authority is unavailable"
        )
    return VerifiedLegacyProviderHeadBinding(
        repository=current.lifecycle.repository,
        delivery_issue=current.lifecycle.delivery_issue,
        pull_request=current.lifecycle.pull_request,
        lifecycle_id=current.lifecycle.lifecycle_id,
        current_head_sha=current.lifecycle.head_sha,
        provider_head_sha=authority._require_oid(
            reviews[0]["reviewed_head_sha"], "legacy reviewed head"
        ),
        current_authority_digest=current.lifecycle.authority_digest,
        current_publication_oid=current.publication_oid,
        current_publication_digest=current.publication_digest,
        adoption_proof_digest=proof["proof_digest"],
        historical_provider_summary_digest=record[
            "historical_provider_summary_digest"
        ],
    )


def _git_text(root: Path, arguments: list[str], label: str) -> str:
    try:
        return transport._git_text(root, arguments)
    except transport.BootstrapSourceAdmissionError as exc:
        raise authority.LifecycleAuthorityError(
            f"legacy package-loss {label} is unavailable"
        ) from exc


def _survey_package_stores(
    repository_root: Path, record: Mapping[str, Any], current: Any,
) -> dict[str, Any]:
    """Survey every maintained durable store; local scratch has no retained store."""

    try:
        root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss source repository is unavailable"
        ) from exc
    if not root.is_dir():
        raise authority.LifecycleAuthorityError(
            "legacy package-loss source repository is unavailable"
        )
    origin = _git_text(root, ["remote", "get-url", "origin"], "source origin")
    if fast_path._central_remote_repository(origin) != record["repository"]:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss source repository identity changed"
        )
    artifacts = set(record["persistence_contract"]["artifact_basenames"])
    for expected in record["source_history"]:
        head = expected["head_sha"]
        tree = _git_text(root, ["rev-parse", f"{head}^{{tree}}"], "source tree").strip()
        parents = _git_text(
            root, ["rev-list", "--parents", "-n", "1", head], "source topology"
        ).split()
        paths = _git_text(
            root, ["ls-tree", "-r", "--name-only", head], "source tree listing"
        ).splitlines()
        ignored = _git_text(
            root, ["show", f"{head}:.gitignore"], "source persistence contract"
        ).splitlines()
        if (
            tree != expected["tree_sha"]
            or parents != [head, expected["parent_sha"]]
            or ".context/" not in ignored
            or any(
                path.startswith(".context/")
                or PurePosixPath(path).name in artifacts
                for path in paths
            )
        ):
            raise authority.LifecycleAuthorityError(
                "historical package bytes exist or a maintained store is unsurveyed"
            )
    survey = {
        "repository": record["repository"],
        "delivery_issue": record["delivery_issue"],
        "pull_request": record["pull_request"],
        "current_publication": {
            "object_oid": current.publication_oid,
            "publication_digest": current.publication_digest,
        },
        "historical_companion_digests": {
            "source_validation_evidence_digest": record[
                "source_validation_evidence_digest"
            ],
            "historical_validation_receipt_digest": record[
                "historical_validation_receipt_digest"
            ],
            "historical_final_attestation_digest": record[
                "historical_final_attestation_digest"
            ],
        },
        "source_history": copy.deepcopy(record["source_history"]),
        "persistence_contract": copy.deepcopy(record["persistence_contract"]),
        "result": "UNAVAILABLE",
        "historical_bytes_reconstructed": False,
    }
    if authority.digest_json(survey) != record["package_store_survey_digest"]:
        raise authority.LifecycleAuthorityError(
            "legacy package store survey identity changed"
        )
    return survey


def _current_safety(
    *, accepted_main: str, entry: Mapping[str, Any], record: Mapping[str, Any],
    reviewed: Any,
) -> dict[str, Any]:
    binding = fast_path.validation_registry_binding(entry)
    if (
        reviewed.repository != record["repository"]
        or reviewed.pull_request_number != record["pull_request"]
        or reviewed.head_sha != record["head_sha"]
        or reviewed.pr_state != "OPEN"
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss current reviewed state changed"
        )
    facts = {
        "accepted_main_sha": accepted_main,
        "repository_admission_digest": fast_path.digest_json(binding),
        "current_command_set_digest": fast_path.digest_json(binding["validation"]),
        "current_signature_policy_digest": fast_path.digest_json(
            binding["signature_policy"]
        ),
        "source_signer_identity": record["source_signer_identity"],
        "ready_prior_authority_schema_version": "1.2",
        "ready_integration_schema_version": "1.2",
        "operation": CURRENT_SAFETY_OPERATION,
        "trust_source": "AUTHENTICATED_PROTECTED_MAIN",
        "integration_transition": "HEAD_ADVANCED",
        "reviewed_state_digest": reviewed.state_digest,
        "reviewed_feedback_digest": reviewed.feedback_digest,
        "thread_resolution_authority": 0,
        "recovery_consumed": False,
        "successful_result": True,
    }
    return {**facts, "current_safety_digest": authority.digest_json(facts)}


def _assemble(
    *, accepted_main: str, record: Mapping[str, Any], current: Any,
    proof: Mapping[str, Any], store_survey: Mapping[str, Any],
    current_safety: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version": "1.0",
        "kind": KIND,
        "domain": DOMAIN,
        "authority_temporality": "AUTHENTICATED_NOW_NOT_HISTORICAL",
        "repository": record["repository"],
        "delivery_issue": record["delivery_issue"],
        "pull_request": record["pull_request"],
        "lifecycle_id": record["lifecycle_id"],
        "historical_proof_mode": record["historical_proof_mode"],
        "proof_version": record["proof_version"],
        "adoption_proof_digest": proof["proof_digest"],
        "adoption_authorization_id": proof["authorization"]["authorization_id"],
        "adoption_authorization_digest": proof["authorization_digest"],
        "current_authority_digest": current.lifecycle.authority_digest,
        "current_publication_oid": current.publication_oid,
        "current_publication_digest": current.publication_digest,
        "head_sha": record["head_sha"],
        "tree_sha": record["tree_sha"],
        "parent_sha": record["parent_sha"],
        "source_signer_identity": record["source_signer_identity"],
        "commit_signature_evidence_digest": record[
            "commit_signature_evidence_digest"
        ],
        "historical_provider_summary_digest": record[
            "historical_provider_summary_digest"
        ],
        "evidence_time_registry_digest": record[
            "evidence_time_registry_digest"
        ],
        "historical_command_set_digest": record[
            "historical_command_set_digest"
        ],
        "source_validation_evidence_digest": record[
            "source_validation_evidence_digest"
        ],
        "historical_validation_receipt_digest": record[
            "historical_validation_receipt_digest"
        ],
        "historical_final_attestation_digest": record[
            "historical_final_attestation_digest"
        ],
        "observed_history_digest": proof["observed_history_digest"],
        "intended_state_digest": proof["intended_state_digest"],
        "head_advanced_count": proof["head_advanced_count"],
        "head_advanced_history_digest": proof["head_advanced_history_digest"],
        "accepted_main_sha": accepted_main,
        "loss_policy_record_digest": record["record_digest"],
        "package_store_survey_digest": authority.digest_json(store_survey),
        "historical_package_status": "UNAVAILABLE",
        "historical_bytes_reconstructed": False,
        "current_safety": copy.deepcopy(current_safety),
        "thread_resolution_authority": 0,
        "recovery_consumed": False,
    }
    return {**fields, "authentication_digest": authority.digest_json(fields)}


def authenticate(
    repository: str, delivery_issue: int, repository_root: Path,
) -> VerifiedLegacyEnrolledPackageLoss:
    """Authenticate loss now without creating or backdating lifecycle authority."""

    accepted_main, record, entry = _accepted_policy(repository, delivery_issue)
    current = publication.verify_current_lifecycle_authority(repository, delivery_issue)
    _bundle, proof = _admit_current(current, record)
    facts = _normalize_provider(_observe_provider(record), record)
    _admit_provider(facts, record)
    fast_path.load_immutable_delivery_registry_binding(
        repository=repository,
        delivery_head_sha=record["head_sha"],
        expected_registry_digest=record["evidence_time_registry_digest"],
        expected_command_set_digest=record["historical_command_set_digest"],
    )
    trust = authority._load_lifecycle_trust_policy(repository)
    try:
        signature_evidence_digest = validation_evidence_loss._source_signature(
            repository_root, record, trust
        )
    except transport.BootstrapSourceAdmissionError as exc:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss source signature evidence is unavailable"
        ) from exc
    if signature_evidence_digest != record["commit_signature_evidence_digest"]:
        raise authority.LifecycleAuthorityError(
            "legacy package-loss source signature evidence changed"
        )
    store_survey = _survey_package_stores(repository_root, record, current)
    provider_binding = _provider_head_binding(current, record)
    helper = transport._load_actions_helper()
    gateway = helper.FastPathGateway(
        repository_root,
        entry,
        ready_source_provider_binding=provider_binding,
    )
    reviewed = gateway.capture_stable_feedback(
        repository, record["pull_request"]
    )
    safety = _current_safety(
        accepted_main=accepted_main,
        entry=entry,
        record=record,
        reviewed=reviewed,
    )
    final_facts = _normalize_provider(_observe_provider(record), record)
    _admit_provider(final_facts, record)
    final_reviewed = gateway.capture_stable_feedback(
        repository, record["pull_request"]
    )
    final_current = publication.verify_current_lifecycle_authority(
        repository, delivery_issue
    )
    _admit_current(final_current, record)
    final_main, final_record, final_entry = _accepted_policy(
        repository, delivery_issue
    )
    if (
        final_facts != facts
        or final_reviewed != reviewed
        or final_current.publication_oid != current.publication_oid
        or final_current.publication_digest != current.publication_digest
        or final_current.lifecycle != current.lifecycle
        or final_main != accepted_main
        or final_record != record
        or fast_path.validation_registry_binding(final_entry)
        != fast_path.validation_registry_binding(entry)
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss authority changed during authentication"
        )
    authentication = _assemble(
        accepted_main=accepted_main,
        record=record,
        current=current,
        proof=proof,
        store_survey=store_survey,
        current_safety=safety,
    )
    return VerifiedLegacyEnrolledPackageLoss(authentication, _VERIFIED)


def verified_binding(value: Any) -> dict[str, Any]:
    if (
        type(value) is not VerifiedLegacyEnrolledPackageLoss
        or value._verification_seal is not _VERIFIED
    ):
        raise authority.LifecycleAuthorityError(
            "legacy package loss requires verifier-derived authority"
        )
    fields = copy.deepcopy(value.canonical_authentication)
    digest = fields.pop("authentication_digest", None)
    if digest != authority.digest_json(fields):
        raise authority.LifecycleAuthorityError(
            "legacy package-loss authentication digest changed"
        )
    return copy.deepcopy(value.canonical_authentication)
