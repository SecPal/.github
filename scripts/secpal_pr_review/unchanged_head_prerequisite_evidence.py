# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Exact #1048 prerequisite member of the detached late-disposition family."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import late_disposition
from . import unchanged_head_prerequisite as prerequisite


SCHEMA_VERSION = "1.8"
FINDING_PREFIX = "issue1048-external-prerequisite-"


def expected_signer() -> late_disposition.SignerIdentity:
    return late_disposition.SignerIdentity(
        "ssh", prerequisite.SIGNER_FINGERPRINT
    )


def facts_digest(facts: dict[str, Any]) -> str:
    return hashlib.sha256(late_disposition.canonical_json_bytes(facts)).hexdigest()


def thread_binding(case: prerequisite.Case, target: Any) -> dict[str, Any]:
    thread = target.thread
    if (
        thread.thread_id != case.thread_id
        or thread.is_resolved is not False
        or len(thread.comments) != 1
        or thread.comments[0].reply_to_id is not None
    ):
        raise prerequisite.PrerequisiteError("exact late thread has drifted")
    comment = thread.comments[0]
    replies: list[dict[str, Any]] = []
    return {
        "thread_id": case.thread_id,
        "top_level_comment_node_id": case.comment_node,
        "top_level_comment_database_id": case.comment_id,
        "finding_body_digest": comment.body_digest,
        "reply_state_digest": facts_digest(replies),
        "reply_count": 0,
        "is_resolved": False,
        "is_outdated": thread.is_outdated,
        "classification": "VALID_ACTIONABLE",
        "disposition": "CORRECTED_AND_VERIFIED",
        "technically_blocking": False,
        "technical_blockers": [],
    }


def classification_payload(
    case: prerequisite.Case, target: Any, facts: dict[str, Any]
) -> dict[str, Any]:
    if facts.get("case_id") != case.case_id:
        raise prerequisite.PrerequisiteError("source facts use another exact case")
    signer = expected_signer()
    return {
        "schema_version": "1.3",
        "kind": late_disposition.CLASSIFICATION_KIND,
        "repository": case.repository,
        "delivery_issue_number": case.delivery_issue,
        "pull_request_number": case.pull_request,
        "head_sha": case.head,
        "delivery_signer": {
            "format": signer.signature_format,
            "fingerprint": signer.fingerprint,
        },
        "authorized_purpose": late_disposition.CLASSIFICATION_PURPOSE,
        "finding_id": FINDING_PREFIX + case.case_id,
        "finding_evidence_digest": facts_digest(facts),
        "thread": thread_binding(case, target),
    }


def disposition_payload(
    case: prerequisite.Case,
    facts: dict[str, Any],
    classification: late_disposition.ClassificationEvidence,
) -> dict[str, Any]:
    source_digest = facts_digest(facts)
    if (
        facts.get("case_id") != case.case_id
        or classification.repository != case.repository
        or classification.delivery_issue_number != case.delivery_issue
        or classification.pull_request_number != case.pull_request
        or classification.head_sha != case.head
        or classification.signer != expected_signer()
        or classification.finding_id != FINDING_PREFIX + case.case_id
        or classification.finding_evidence_digest != source_digest
        or classification.thread.thread_id != case.thread_id
        or (classification.thread.classification,
            classification.thread.disposition)
        != ("VALID_ACTIONABLE", "CORRECTED_AND_VERIFIED")
        or classification.thread.technically_blocking is not False
    ):
        raise prerequisite.PrerequisiteError(
            "late classification is not bound to the exact prerequisite"
        )
    thread = asdict(classification.thread)
    thread["authorized_action"] = "RESOLVE_REVIEW_THREAD"
    signer = expected_signer()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": late_disposition.KIND,
        "repository": case.repository,
        "delivery_issue_number": case.delivery_issue,
        "pull_request_number": case.pull_request,
        "head_sha": case.head,
        "validated_tree_sha": case.tree,
        "external_prerequisite_evidence_digest": source_digest,
        "delivery_signer": {
            "format": signer.signature_format,
            "fingerprint": signer.fingerprint,
        },
        "authorized_action": "RESOLVE_EXACT_REVIEW_THREADS",
        "threads": [thread],
    }


def parse_exact_disposition(
    artifact_path: Path,
    signature_path: Path,
    *,
    case: prerequisite.Case,
    facts: dict[str, Any],
    classification: late_disposition.ClassificationEvidence,
) -> late_disposition.LateDispositionEvidence:
    """Require signed exact equality, not a generic schema-version downgrade."""

    canonical = late_disposition.verify_detached_signature(
        artifact_path,
        signature_path,
        expected_signer(),
    )
    try:
        payload = json.loads(
            canonical,
            parse_constant=late_disposition._reject_nonfinite,
            object_pairs_hook=late_disposition._reject_duplicate_object,
        )
    except (TypeError, ValueError) as exc:
        raise late_disposition.LateDispositionError(
            "exact prerequisite disposition is malformed"
        ) from exc
    expected = disposition_payload(case, facts, classification)
    if (
        not isinstance(payload, dict)
        or late_disposition.canonical_json_bytes(payload) != canonical
        or payload != expected
    ):
        raise late_disposition.LateDispositionError(
            "exact prerequisite disposition binding changed"
        )
    return late_disposition.LateDispositionEvidence(
        artifact_digest=hashlib.sha256(canonical).hexdigest(),
        canonical_payload=canonical,
        delivery_issue_number=case.delivery_issue,
        signer=expected_signer(),
        threads=(classification.thread,),
    )
