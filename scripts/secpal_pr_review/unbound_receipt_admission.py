# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact raw-receipt admission; historical bytes never acquire commit binding."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from . import lifecycle_authority as authority
from . import lifecycle_execution as execution
from . import lifecycle_publication as publication
from . import bootstrap_source_admission as transport
from . import governance_amendment as amendment
from . import validation_evidence_loss as loss
from . import fast_path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = "policies/exact-unbound-receipt-admission.json"
KIND = "SECPAL_EXACT_UNBOUND_RECEIPT_ADMISSION"
DOMAIN = "secpal.exact-unbound-receipt-admission/v1"
SUBJECT = fast_path.EXACT_UNBOUND_RECEIPT_SUBJECT
P1_THREAD = fast_path.EXACT_UNBOUND_RECEIPT_P1_THREAD
SOURCE_SIGNER = "aroviqen@secpal.app"
FIELDS = frozenset({
    *SUBJECT, "schema_version", "kind", "domain", "pull_request_state",
    "source_signer_identity", "commit_signature_evidence_digest",
    "accepted_main_sha", "policy_digest", "historical_evidence",
    "qualification_sha256", "qualification_authority_sha",
    "feedback", "observed_pre_enrollment_history", "intended_state",
    "current_validation", "adoption_timestamp", "admission_id", "bounded_uses",
    "blocking_material_finding_ids", "signer_identity", "signature", "admission_digest",
})


def normalize_receipt(
    raw: bytes, record: Mapping[str, Any], binding: dict[str, Any],
    reviewed: fast_path.StableFeedbackState,
) -> dict[str, Any]:
    """Pure normalization of exact retained bytes, not an attestation issuer."""
    if not isinstance(raw, bytes) or not raw or len(raw) > 65536:
        raise authority.LifecycleAuthorityError("raw receipt bytes are outside the bound")
    receipt = authority.loads_closed_json(raw)
    expected = fast_path.create_validation_receipt(
        repository=record["repository"], head_sha=record["head_sha"],
        validated_tree_sha=record["tree_sha"], registry=binding,
        command_set=binding["validation"], successful_result=True,
        reviewed_state=reviewed, manual_gate_evidence=receipt.get("manual_gate_evidence"),
    ) if isinstance(receipt, dict) else None
    if (
        receipt != expected
        or hashlib.sha256(raw).hexdigest() != record["raw_receipt_sha256"]
        or receipt["receipt_digest"] != record["raw_receipt_digest"]
        or receipt["registry_digest"] != record["receipt_registry_digest"]
        or receipt["command_set_digest"] != record["receipt_command_set_digest"]
        or reviewed.repository != record["repository"]
        or reviewed.pull_request_number != record["pull_request"]
        or reviewed.head_sha != record["head_sha"]
        or reviewed.state_digest != record["receipt_reviewed_state_digest"]
        or reviewed.feedback_digest != record["receipt_reviewed_feedback_digest"]
    ):
        raise authority.LifecycleAuthorityError("original raw receipt provenance changed")
    return fast_path.normalize_exact_state_adoption_historical_evidence({
        "state": "RAW_RECEIPT_PRESENT_BUT_UNBOUND",
        "validation_receipt_digest": None, "source_validation_evidence_digest": None,
        "final_attestation_digest": None, "bytes_reconstructed": False,
        "raw_receipt_sha256": record["raw_receipt_sha256"],
        "raw_receipt_digest": record["raw_receipt_digest"],
    })


def history() -> list[dict[str, Any]]:
    """The authenticated assessment consumes one review, never one per provider."""
    return [
        {"sequence": sequence, "kind": kind, "observed_at": occurred,
         "head_sha": SUBJECT["head_sha"], "reviewed_head_sha": reviewed}
        for sequence, kind, occurred, reviewed in (
            (1, "PR_CREATED_DRAFT", "2026-10-06T23:16:57Z", None),
            (2, "DRAFT_TO_READY_OBSERVED", "2026-10-06T23:25:00Z", None),
            (3, "REVIEW_SUBMITTED", "2026-10-06T23:26:31Z", SUBJECT["head_sha"]),
        )
    ]


def intended_state() -> dict[str, Any]:
    state = authority.initial_state()
    state.update(
        unrestricted_review_count=1, remediation_cycle_count=0,
        draft=False, ready=True, ready_transition_count=1,
        ready_history=[{"sequence": 1, "transition_kind": "DRAFT_TO_READY",
                        "observation_digest": authority.digest_json(history()[1])}],
    )
    return state


def _read_artifact(root: Path, relative: str) -> bytes:
    """Observe one bounded regular export file; never follow exported links."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(p in {".", ".."} for p in parts):
        raise authority.LifecycleAuthorityError("artifact escaped its export root")
    descriptors = []
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(descriptor)
        for part in parts[:-1]:
            descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
            descriptors.append(descriptor)
        item = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=descriptor)
        descriptors.append(item)
        info = os.fstat(item)
        limit = 2 * 1024 * 1024
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise authority.LifecycleAuthorityError("artifact is not a bounded regular file")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(item, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(item)
        if len(data) != info.st_size or any(
            getattr(info, field) != getattr(after, field)
            for field in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        ):
            raise authority.LifecycleAuthorityError("artifact changed during observation")
        return data
    except OSError as exc:
        raise authority.LifecycleAuthorityError("artifact is unavailable without following links") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _record(main: str) -> dict[str, Any]:
    record = authority.loads_closed_json(amendment._accepted_main_bytes(ROOT, main, POLICY_PATH))
    fields = {*SUBJECT, "schema_version", "source_signer_identity", "raw_receipt_sha256",
              "raw_receipt_digest", "receipt_registry_digest", "receipt_command_set_digest",
              "receipt_reviewed_state_digest", "receipt_reviewed_feedback_digest",
              "qualification_sha256", "qualification_authority_sha", "completed_state_digest",
              "completed_feedback_digest", "feedback"}
    record = authority._require_closed(record, fields, "exact unbound receipt policy")
    if record["schema_version"] != "1.0" or any(record.get(key) != value for key, value in SUBJECT.items()):
        raise authority.LifecycleAuthorityError("unbound receipt policy has no exact subject")
    if record.get("source_signer_identity") != SOURCE_SIGNER:
        raise authority.LifecycleAuthorityError("unbound receipt source signer changed")
    return record


def _verify_reviews(reviews: Any) -> None:
    """Authenticate the assessment chronology separately from feedback content."""
    if not isinstance(reviews, list) or len(reviews) != 2:
        raise authority.LifecycleAuthorityError("original assessment inventory changed")
    expected = [
        (5435617921, "PRR_kwDOQFR1MM8AAAABQ_zygQ", "chatgpt-codex-connector[bot]", "2026-10-06T23:26:31Z"),
        (5435621189, "PRR_kwDOQFR1MM8AAAABQ_z_RQ", "copilot-pull-request-reviewer[bot]", "2026-10-06T23:27:02Z"),
    ]
    for review, (identifier, node, actor, occurred) in zip(reviews, expected):
        if not isinstance(review, dict) or (
            review.get("id") != identifier or review.get("node_id") != node
            or review.get("user", {}).get("login") != actor
            or review.get("state") != "COMMENTED" or review.get("submitted_at") != occurred
            or review.get("commit_id") != SUBJECT["head_sha"]
        ):
            raise authority.LifecycleAuthorityError("original assessment identity or chronology changed")


def _verify_document(value: Any) -> dict[str, Any]:
    """Verify immutable signed facts; later remediation does not rewrite history."""
    doc = copy.deepcopy(authority._require_closed(value, FIELDS, "unbound receipt admission"))
    if (
        any(doc[key] != val for key, val in SUBJECT.items())
        or doc["schema_version"] != "1.0" or doc["kind"] != KIND or doc["domain"] != DOMAIN
        or doc["pull_request_state"] != "OPEN"
        or doc["source_signer_identity"] != SOURCE_SIGNER
        or doc["blocking_material_finding_ids"] != [P1_THREAD]
        or type(doc["bounded_uses"]) is not int or doc["bounded_uses"] != 1
        or doc["admission_id"] != "exact-unbound-receipt:SecPal/.github:1154:1156"
        or doc["intended_state"] != intended_state()
        or doc["observed_pre_enrollment_history"] != history()
    ):
        raise authority.LifecycleAuthorityError("unbound receipt admission scope or finite history changed")
    record = _record(authority._require_oid(doc["accepted_main_sha"], "admission epoch"))
    historical = fast_path.normalize_exact_state_adoption_historical_evidence(doc["historical_evidence"])
    if (
        historical["state"] != "RAW_RECEIPT_PRESENT_BUT_UNBOUND"
        or historical["raw_receipt_sha256"] != record["raw_receipt_sha256"]
        or historical["raw_receipt_digest"] != record["raw_receipt_digest"]
        or doc["policy_digest"] != authority.digest_json(record)
        or doc["qualification_sha256"] != record["qualification_sha256"]
        or doc["qualification_authority_sha"] != record["qualification_authority_sha"]
        or doc["feedback"] != record["feedback"]
    ):
        raise authority.LifecycleAuthorityError("unbound receipt provenance differs from registered source")
    safety = authority._require_closed(doc["current_validation"], frozenset({
        "accepted_main_sha", "policy_digest", "command_set_digest", "result",
    }), "unbound receipt current safety")
    if safety["result"] != "PASS" or safety["accepted_main_sha"] != doc["accepted_main_sha"]:
        raise authority.LifecycleAuthorityError("unbound receipt requires independent current safety")
    for field in ("policy_digest", "command_set_digest"):
        authority._require_digest(safety[field], field)
    authority._normalize_observed_pre_enrollment_history(
        doc["observed_pre_enrollment_history"], expected_head=SUBJECT["head_sha"],
        intended_state=doc["intended_state"],
    )
    if authority._parse_adoption_timestamp(doc["adoption_timestamp"], "admission time") < authority._parse_adoption_timestamp(history()[-1]["observed_at"], "last historical observation"):
        raise authority.LifecycleAuthorityError("unbound receipt admission cannot be backdated")
    authority._require_digest(doc["commit_signature_evidence_digest"], "source signature")
    signed = {key: val for key, val in doc.items() if key != "admission_digest"}
    if authority.digest_json(signed) != doc["admission_digest"]:
        raise authority.LifecycleAuthorityError("unbound receipt admission digest changed")
    policy = authority._load_lifecycle_trust_policy(SUBJECT["repository"])
    authority._verify_signature(
        authority.canonical_json_bytes(authority._unsigned(doc, "admission_digest", "signature")),
        doc["signature"], doc["signer_identity"], DOMAIN,
        policy.legacy_adoption_signer_identities, authority._policy_signature_verifier(policy),
    )
    return doc


def _observe(main: str) -> dict[str, Any]:
    """Read live provider/source/journal facts using the existing trusted adapters."""
    helper = transport._load_actions_helper()
    record = _record(main)
    pull = loss._gh_json("repos/SecPal/.github/pulls/1156")
    commits = loss._gh_json("repos/SecPal/.github/pulls/1156/commits")
    _verify_reviews(loss._gh_json("repos/SecPal/.github/pulls/1156/reviews"))
    chronology = loss._normalize_chronology(loss._observe_chronology(SUBJECT["repository"], 1156), SUBJECT["repository"], 1156)
    entry = helper.select_repository(helper.load_registry(), SUBJECT["repository"])
    state = helper.FastPathGateway(ROOT, entry).capture_stable_feedback(SUBJECT["repository"], 1156)
    feedback = amendment._live_feedback(SUBJECT["repository"], 1156, SUBJECT["head_sha"])
    if (
        pull.get("state") != "open" or pull.get("draft") is not False
        or pull.get("number") != 1156 or pull.get("head", {}).get("sha") != SUBJECT["head_sha"]
        or pull.get("head", {}).get("repo", {}).get("full_name") != SUBJECT["repository"]
        or pull.get("base", {}).get("repo", {}).get("full_name") != SUBJECT["repository"]
        or pull.get("base", {}).get("ref") != "main"
        or pull.get("created_at") != history()[0]["observed_at"]
        or f"Fixes #1154" not in pull.get("body", "")
        or record["raw_receipt_digest"] not in pull.get("body", "")
        or len(commits) != 1 or commits[0].get("sha") != SUBJECT["head_sha"]
        or commits[0].get("commit", {}).get("tree", {}).get("sha") != SUBJECT["tree_sha"]
        or [p.get("sha") for p in commits[0].get("parents", [])] != [SUBJECT["parent_sha"]]
        or commits[0].get("commit", {}).get("verification", {}).get("verified") is not True
        or len(chronology) != 1 or chronology[0].kind != "ready_for_review"
        or chronology[0].occurred_at != history()[1]["observed_at"]
        or feedback != record["feedback"]
        or state.state_digest != record["completed_state_digest"]
        or state.feedback_digest != record["completed_feedback_digest"]
        or [(v["node_id"], v["is_resolved"], v["is_outdated"]) for v in state.feedback["threads"]] != [(P1_THREAD, False, False)]
    ):
        raise authority.LifecycleAuthorityError("original delivery/provider facts changed")
    if loss._optional_validation_receipt_trailer(ROOT, SUBJECT["head_sha"]) is not None:
        raise authority.LifecycleAuthorityError("raw receipt classification conflicts with source trailer")
    trust = authority._load_lifecycle_trust_policy(SUBJECT["repository"])
    signature = loss._commit_signature(ROOT, SUBJECT["head_sha"], SOURCE_SIGNER, trust)
    publication.verify_pre_enrollment_absence(SUBJECT["repository"], 1154)
    return {"feedback": feedback, "commit_signature_evidence_digest": signature}


def acquire(artifact_root: Path) -> dict[str, Any]:
    """Read-only exact qualification with independently executed current safety."""
    helper = transport._load_actions_helper()
    main = helper._require_accepted_main_bridge_source(SUBJECT["repository"])
    record = _record(main)
    before = _observe(main)
    raw = _read_artifact(artifact_root, ".context/issue1154/canonical-receipt.json")
    draft_raw = _read_artifact(artifact_root, ".context/issue1154/draft-feedback.json")
    draft = fast_path.StableFeedbackState.from_payload(authority.loads_closed_json(draft_raw))
    registry = authority.loads_closed_json(amendment._accepted_main_bytes(ROOT, SUBJECT["head_sha"], amendment.REGISTRY_PATH))
    entry = helper.select_repository(registry, SUBJECT["repository"])
    binding = fast_path.validation_registry_projection(entry)
    historical = normalize_receipt(raw, record, binding, draft)
    qualification = _read_artifact(artifact_root, ".context/adoption1154/qualification-report.json")
    if hashlib.sha256(qualification).hexdigest() != record["qualification_sha256"]:
        raise authority.LifecycleAuthorityError("retained qualification bytes changed")
    report = authority.loads_closed_json(qualification)
    if (
        report.get("ACCEPTED_MAIN") != record["qualification_authority_sha"]
        or report.get("QUALIFIED_SOURCE_HEAD") != SUBJECT["head_sha"]
        or report.get("QUALIFIED_SOURCE_TREE") != SUBJECT["tree_sha"]
        or report.get("FINITE_LIFECYCLE_STATE", {}).get("remediation_commits") != 0
        or report.get("FINITE_LIFECYCLE_STATE", {}).get("bounded_completed_assessments") != 1
        or report.get("FINITE_LIFECYCLE_STATE", {}).get("unresolved_material_thread") != P1_THREAD
    ):
        raise authority.LifecycleAuthorityError("qualification subject or consumed budget changed")
    current_validation = amendment._bound_current_validation(
        ROOT, SUBJECT["repository"], main,
        target_head_sha=SUBJECT["head_sha"], target_tree_sha=SUBJECT["tree_sha"],
    )
    if before != _observe(main):
        raise authority.LifecycleAuthorityError("source facts changed during current safety")
    helper._require_accepted_main_bridge_source(SUBJECT["repository"], expected_main=main)
    return {
        **SUBJECT, **before, "schema_version": "1.0", "kind": KIND, "domain": DOMAIN,
        "pull_request_state": "OPEN", "source_signer_identity": SOURCE_SIGNER,
        "accepted_main_sha": main, "policy_digest": authority.digest_json(record),
        "historical_evidence": historical, "qualification_sha256": record["qualification_sha256"],
        "qualification_authority_sha": record["qualification_authority_sha"],
        "observed_pre_enrollment_history": history(), "intended_state": intended_state(),
        "current_validation": current_validation,
        "adoption_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "admission_id": "exact-unbound-receipt:SecPal/.github:1154:1156", "bounded_uses": 1,
        "blocking_material_finding_ids": [P1_THREAD],
    }


def issue(artifact_root: Path) -> dict[str, Any]:
    """Sign admitted current facts with the existing adoption role, once per journal."""
    fields = acquire(artifact_root)
    identity, signer = execution._production_legacy_adoption_signer(SUBJECT["repository"])
    fields["signer_identity"] = identity
    signed = {**fields, "signature": dict(signer(authority.canonical_json_bytes(fields), DOMAIN))}
    document = {**signed, "admission_digest": authority.digest_json(signed)}
    return _verify_document(document)


def reauthenticate_for_publication(value: Any) -> None:
    """Recheck live safety predicates before the existing one-use enrollment CAS."""
    doc = _verify_document(value)
    helper = transport._load_actions_helper()
    main = helper._require_accepted_main_bridge_source(SUBJECT["repository"])
    if main != doc["accepted_main_sha"] or _observe(main) != {
        "feedback": doc["feedback"],
        "commit_signature_evidence_digest": doc["commit_signature_evidence_digest"],
    }:
        raise authority.LifecycleAuthorityError("unbound receipt publication facts changed")
