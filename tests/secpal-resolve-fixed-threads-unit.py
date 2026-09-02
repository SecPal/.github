#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Sequence
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/secpal-resolve-fixed-threads.py"
SPEC = importlib.util.spec_from_file_location("secpal_resolve_fixed_threads", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from secpal_work_graph import acceptance_criteria as work_graph_acceptance_criteria  # noqa: E402
from secpal_work_graph import github as work_graph_github  # noqa: E402
from secpal_work_graph import model as work_graph_model  # noqa: E402


class FakeGh:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, arguments: Sequence[str]) -> dict[str, Any]:
        self.calls.append(list(arguments))
        if not self.responses:
            raise AssertionError("unexpected gh call")
        return self.responses.pop(0)


class FakeGit:
    def __init__(
        self,
        *,
        expected_head: str,
        reviewed_head: str,
        tree: str,
        receipt_digest: str,
        repository: str = "SecPal/api",
        signature_valid: bool = True,
        signature_format: str = "ssh",
        signer_fingerprint: str = "SHA256:fixtureDeliverySigner",
        signing_key: str = "/tmp/fixture-signing-key",
        second_parent: str | None = None,
        integration_digest: str | None = None,
    ) -> None:
        self.expected_head = expected_head
        self.reviewed_head = reviewed_head
        self.tree = tree
        self.receipt_digest = receipt_digest
        self.repository = repository
        self.signature_valid = signature_valid
        self.signature_format = signature_format
        self.signer_fingerprint = signer_fingerprint
        self.signing_key = signing_key
        self.second_parent = second_parent
        self.integration_digest = integration_digest
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        repository_root: Path,
        arguments: Sequence[str],
        *,
        allow_failure: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        del repository_root, allow_failure
        call = tuple(arguments)
        self.calls.append(call)
        if call == ("remote", "get-url", "origin"):
            stdout = f"https://github.com/{self.repository}.git\n"
        elif call == ("rev-parse", "HEAD"):
            stdout = f"{self.expected_head}\n"
        elif call == ("rev-parse", f"{self.expected_head}^{{tree}}"):
            stdout = f"{self.tree}\n"
        elif call == ("rev-list", "--parents", "-n", "1", self.expected_head):
            parents = f"{self.reviewed_head}"
            if self.second_parent is not None:
                parents += f" {self.second_parent}"
            stdout = f"{self.expected_head} {parents}\n"
        elif call[0:2] == ("show", "-s"):
            stdout = (
                f"{self.integration_digest}\n"
                if "SecPal-Integration-Evidence" in call[2]
                else f"{self.receipt_digest}\n"
            )
        elif call == ("cat-file", "commit", self.expected_head):
            signature_label = (
                "SSH SIGNATURE"
                if self.signature_format == "ssh"
                else "PGP SIGNATURE"
            )
            stdout = (
                f"tree {self.tree}\nparent {self.reviewed_head}\n"
                + (
                    f"parent {self.second_parent}\n"
                    if self.second_parent is not None
                    else ""
                )
                +
                f"gpgsig -----BEGIN {signature_label}-----\n signature\n"
                f" -----END {signature_label}-----\n\nmessage\n"
            )
        elif call == ("verify-commit", "--raw", self.expected_head):
            if not self.signature_valid:
                return subprocess.CompletedProcess(call, 1, "", "bad signature")
            if self.signature_format == "ssh":
                stdout = (
                    'Good "git" signature for fixture with ED25519 key '
                    f"{self.signer_fingerprint}\n"
                )
            else:
                stdout = f"[GNUPG:] VALIDSIG {self.signer_fingerprint} 2026-01-01\n"
        elif call == ("config", "--global", "--get", "gpg.format"):
            stdout = f"{self.signature_format}\n"
        elif call == ("config", "--global", "--get", "user.signingkey"):
            stdout = f"{self.signing_key}\n"
        else:
            raise AssertionError(f"unexpected git call: {call}")
        return subprocess.CompletedProcess(call, 0, stdout, "")


def resolve_response(thread_id: str) -> dict[str, Any]:
    return {
        "data": {
            "resolveReviewThread": {
                "thread": {"id": thread_id, "isResolved": True}
            }
        }
    }


def target_response(
    thread_id: str,
    *,
    head: str = "a" * 40,
    repository: str = "SecPal/api",
    number: int = 123,
    state: str = "OPEN",
    resolved: bool = False,
    outdated: bool = False,
    comments: list[tuple[str, str, str | None]] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "data": {
            "node": {
                "__typename": "PullRequestReviewThread",
                "id": thread_id,
                "isResolved": resolved,
                "isOutdated": outdated,
                "pullRequest": {
                    "number": number,
                    "state": state,
                    "headRefOid": head,
                    "repository": {"nameWithOwner": repository},
                },
                "comments": {
                    "nodes": [
                        {
                            "id": comment_id,
                            "databaseId": index,
                            "body": body,
                            "replyTo": (
                                {"id": reply_to_id}
                                if reply_to_id is not None
                                else None
                            ),
                        }
                        for index, (comment_id, body, reply_to_id) in enumerate(
                            comments or [], start=1001
                        )
                    ],
                    "pageInfo": {
                        "hasNextPage": has_next_page,
                        "endCursor": end_cursor,
                    },
                },
            }
        }
    }


def work_graph_issue_response(
    number: int,
    *,
    blocked_by: tuple[int, ...] = (),
    labels_have_next_page: bool = False,
) -> Any:
    def references(numbers: tuple[int, ...]) -> list[dict[str, Any]]:
        return [
            {"number": item, "repository": {"nameWithOwner": "SecPal/api"}}
            for item in numbers
        ]

    issue = {
        "number": number,
        "title": f"Issue {number}",
        "url": f"https://github.com/SecPal/api/issues/{number}",
        "state": "OPEN",
        "stateReason": None,
        "body": "## Acceptance Criteria\n\n- [ ] Tracked responsibility",
        "repository": {"nameWithOwner": "SecPal/api"},
        "parent": None,
        "labels": {
            "nodes": [],
            "pageInfo": {
                "hasNextPage": labels_have_next_page,
                "endCursor": "labels-next" if labels_have_next_page else None,
            },
        },
        "subIssues": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
        "blockedBy": {
            "nodes": references(blocked_by),
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
        "blocking": {"totalCount": 0},
        "closedByPullRequestsReferences": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }
    return work_graph_github.GraphQLResponse(
        {"repository": {"issue": issue}},
        (),
    )


def work_graph_page_response(
    connection: str,
    *,
    has_next_page: bool,
    end_cursor: str | None,
) -> Any:
    return work_graph_github.GraphQLResponse(
        {
            "repository": {
                "issue": {
                    connection: {
                        "nodes": [],
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                    }
                }
            }
        },
        (),
    )


def expected_thread_state(
    thread_id: str,
    comments: list[tuple[str, str, str | None]] | None = None,
    *,
    resolved: bool = False,
    outdated: bool = False,
) -> Any:
    states = [
        MODULE.ThreadCommentState(
            comment_id=comment_id,
            database_id=None,
            body_digest=MODULE._body_digest(body),
            reply_to_id=reply_to_id,
        )
        for comment_id, body, reply_to_id in (comments or [])
    ]
    return MODULE.ExpectedThreadState(
        thread_id=thread_id,
        is_resolved=resolved,
        is_outdated=outdated,
        comments=tuple(sorted(states, key=lambda item: item.comment_id)),
    )


def resolve_threads(
    repository: str,
    number: int,
    expected_head: str,
    thread_ids: Sequence[str],
    *,
    apply: bool,
    runner: Any = MODULE._run_gh,
    reviewed_comments: dict[str, list[tuple[str, str, str | None]]] | None = None,
    expected_targets: dict[str, Any] | None = None,
    eligibility_manifest: dict[str, Any] | None = None,
    follow_up_verifier: Any = MODULE.verify_live_follow_up,
    recovery_bound: bool = False,
    recovery_authority: bool = True,
) -> dict[str, Any]:
    immutable_thread_ids = tuple(thread_ids)
    if expected_targets is None:
        comments_by_thread = reviewed_comments or {}
        expected_targets = {
            thread_id: expected_thread_state(
                thread_id,
                comments_by_thread.get(thread_id),
            )
            for thread_id in immutable_thread_ids
        }
    reviewed_head = "b" * 40 if expected_head != "b" * 40 else "a" * 40
    feedback = {
        "pull_request_reactions": [],
        "reviews": [],
        "conversation_comments": [],
        "threads": [
            {
                "node_id": thread_id,
                "is_resolved": expected_targets[thread_id].is_resolved,
                "is_outdated": expected_targets[thread_id].is_outdated,
                "comments": [
                    {
                        "node_id": comment.comment_id,
                        "body_digest": comment.body_digest,
                        "actor": {
                            "login": "reviewer",
                            "node_id": "USER_reviewer",
                            "database_id": 7,
                        },
                        "reply_to_id": comment.reply_to_id,
                        "reactions": [],
                    }
                    for comment in expected_targets[thread_id].comments
                ],
            }
            for thread_id in immutable_thread_ids
        ],
    }
    feedback["threads"].sort(key=lambda item: item["node_id"])
    identity = {
        "repository": repository,
        "pull_request_number": number,
        "head_sha": reviewed_head,
        "base_ref": "main",
        "base_sha": "9" * 40,
        "pr_state": "OPEN",
    }
    reviewed = {
        "schema_version": "1.0",
        **identity,
        **feedback,
        "feedback_digest": MODULE._digest_json(feedback),
        "state_digest": MODULE._digest_json({**identity, "feedback": feedback}),
    }
    if eligibility_manifest is None:
        eligibility_manifest = {
            "schema_version": "1.1",
            "repository": repository,
            "pull_request_number": number,
            "reviewed_head_sha": reviewed_head,
            "reviewed_state_digest": reviewed["state_digest"],
            "eligible_threads": [
                {
                    "thread_id": thread_id,
                    "classification": "VALID_ACTIONABLE",
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "finding_ids": [f"finding-{index}"],
                    "evidence_digest": f"{index:x}" * 64,
                    "follow_up": None,
                }
                for index, thread_id in enumerate(immutable_thread_ids, start=1)
            ],
        }
    else:
        eligibility_manifest = copy.deepcopy(eligibility_manifest)
        eligibility_manifest["repository"] = repository
        eligibility_manifest["pull_request_number"] = number
        eligibility_manifest["reviewed_head_sha"] = reviewed_head
        eligibility_manifest["reviewed_state_digest"] = reviewed[
            "state_digest"
        ]
    eligibility_digest = MODULE._digest_json(eligibility_manifest)
    if recovery_bound:
        _receipt, attestation = recovery_validation_payloads(
            reviewed,
            eligibility_digest,
            expected_head=expected_head,
        )
    else:
        attestation = validation_attestation_payload(
            reviewed,
            eligibility_digest,
            expected_head=expected_head,
        )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        reviewed_path = root / "reviewed.json"
        validation_path = root / "validation.json"
        eligibility_path = root / "eligibility.json"
        recovery_path = root / "recovery.json"
        recovery_authorization_path = root / "recovery-authorization.json"
        reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
        validation_path.write_text(json.dumps(attestation), encoding="utf-8")
        eligibility_path.write_text(
            json.dumps(eligibility_manifest),
            encoding="utf-8",
        )
        recovery_path.write_text("{}", encoding="utf-8")
        recovery_authorization_path.write_text(
            "fixture signed authorization", encoding="utf-8"
        )
        git = FakeGit(
            expected_head=expected_head,
            reviewed_head=reviewed_head,
            tree=attestation["validated_tree_sha"],
            receipt_digest=attestation["validation_receipt_digest"],
            repository=repository,
        )
        with (
            mock.patch.object(MODULE, "_run_git", git),
            mock.patch.object(MODULE, "_run_gh", runner),
            mock.patch.object(
                MODULE,
                "verify_live_follow_up",
                follow_up_verifier,
            ),
            mock.patch.object(
                MODULE.lifecycle_orchestration,
                "verify_exceptional_recovery_authority",
                return_value=mock.Mock(recovery_digest="9" * 64),
            ),
        ):
            return MODULE.resolve_threads(
                repository,
                number,
                expected_head,
                immutable_thread_ids,
                apply=apply,
                repository_root=root,
                reviewed_state_path=reviewed_path,
                expected_reviewed_state_digest=reviewed["state_digest"],
                validation_evidence_path=validation_path,
                eligibility_evidence_path=eligibility_path,
                **(
                    {
                        "exceptional_recovery_delivery_issue": 790,
                        "exceptional_recovery_evidence_path": recovery_path,
                        "exceptional_recovery_authorization_path": (
                            recovery_authorization_path
                        ),
                    }
                    if recovery_bound and recovery_authority
                    else {}
                ),
            )


def reviewed_state_payload(
    thread_id: str,
    comments: list[tuple[str, str, str | None]],
    *,
    resolved: bool = False,
    outdated: bool = False,
) -> dict[str, Any]:
    feedback = {
        "pull_request_reactions": [],
        "reviews": [],
        "conversation_comments": [],
        "threads": [
            {
                "node_id": thread_id,
                "is_resolved": resolved,
                "is_outdated": outdated,
                "comments": [
                    {
                        "node_id": comment_id,
                        "body_digest": MODULE._body_digest(body),
                        "actor": {
                            "login": "reviewer",
                            "node_id": "USER_reviewer",
                            "database_id": 7,
                        },
                        "reply_to_id": reply_to_id,
                        "reactions": [],
                    }
                    for comment_id, body, reply_to_id in comments
                ],
            }
        ],
    }
    identity = {
        "repository": "SecPal/api",
        "pull_request_number": 123,
        "head_sha": "a" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "pr_state": "OPEN",
    }
    return {
        "schema_version": "1.0",
        **identity,
        **feedback,
        "feedback_digest": MODULE._digest_json(feedback),
        "state_digest": MODULE._digest_json({**identity, "feedback": feedback}),
    }


def validation_attestation_payload(
    reviewed: dict[str, Any],
    eligibility_evidence_digest: str = "e" * 64,
    *,
    expected_head: str = "c" * 40,
) -> dict[str, Any]:
    binding = MODULE._validation_registry_binding(
        MODULE._load_repository_entry(reviewed["repository"])
    )
    manual_gate_evidence = [
        {
            "gate": gate,
            "satisfied": True,
            "evidence": f"Verified integration evidence {index}",
        }
        for index, gate in enumerate(binding["manual_gates"], start=1)
    ]
    receipt_fields = {
        "schema_version": "1.0",
        "kind": "VALIDATION_RECEIPT",
        "repository": reviewed["repository"],
        "head_sha": reviewed["head_sha"],
        "validated_tree_sha": "f" * 40,
        "registry_digest": MODULE._digest_json(binding),
        "command_set_digest": MODULE._digest_json(binding["validation"]),
        "successful_result": True,
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "manual_gate_evidence": manual_gate_evidence,
        "eligibility_evidence_digest": eligibility_evidence_digest,
    }
    fields = {
        "schema_version": "1.0",
        "repository": reviewed["repository"],
        "head_sha": expected_head,
        "registry_digest": MODULE._digest_json(binding),
        "command_set_digest": MODULE._digest_json(binding["validation"]),
        "successful_result": True,
        "reviewed_head_sha": reviewed["head_sha"],
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "validated_tree_sha": "f" * 40,
        "validation_receipt_digest": MODULE._digest_json(receipt_fields),
        "manual_gate_evidence": manual_gate_evidence,
        "eligibility_evidence_digest": eligibility_evidence_digest,
    }
    return {**fields, "attestation_digest": MODULE._digest_json(fields)}


def recovery_validation_payloads(
    reviewed: dict[str, Any],
    eligibility_evidence_digest: str,
    *,
    expected_head: str = "c" * 40,
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = MODULE._validation_registry_binding(
        MODULE._load_repository_entry(reviewed["repository"])
    )
    stable = MODULE.fast_path.StableFeedbackState.from_payload(reviewed)
    receipt = MODULE.fast_path.create_validation_receipt(
        repository=reviewed["repository"],
        head_sha=reviewed["head_sha"],
        validated_tree_sha="f" * 40,
        registry=binding,
        command_set=binding["validation"],
        successful_result=True,
        reviewed_state=stable,
        manual_gate_evidence=[
            {
                "gate": gate,
                "satisfied": True,
                "evidence": f"Verified recovery evidence {index}",
            }
            for index, gate in enumerate(binding["manual_gates"], start=1)
        ],
        eligibility_evidence_digest=eligibility_evidence_digest,
        exceptional_recovery_evidence_digest="9" * 64,
    )
    attestation = MODULE.fast_path.create_validation_attestation(
        repository=reviewed["repository"],
        head_sha=expected_head,
        registry=binding,
        command_set=binding["validation"],
        successful_result=True,
        reviewed_state=stable,
        validation_receipt=receipt,
    )
    return receipt, attestation


def integration_validation_payloads(
    reviewed: dict[str, Any], eligibility_digest: str, *, expected_head: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    binding = MODULE._validation_registry_binding(
        MODULE._load_repository_entry(reviewed["repository"])
    )
    stable = MODULE.fast_path.StableFeedbackState.from_payload(reviewed)
    tree = "f" * 40
    integration = {
        "schema_version": "1.1",
        "kind": "TWO_PARENT_READY_INTEGRATION",
        "authorization_id": "ready-integration-authorization-001",
        "repository": reviewed["repository"],
        "delivery_issue_number": 673,
        "pull_request_number": reviewed["pull_request_number"],
        "prior_delivery_head_sha": reviewed["head_sha"],
        "prior_authority_digest": "a" * 64,
        "prior_authority_tag_object_sha": "1" * 40,
        "target_base": {
            "ref": reviewed["base_ref"],
            "authorized_sha": reviewed["base_sha"],
            "observed_sha": reviewed["base_sha"],
        },
        "ordered_parent_shas": [reviewed["head_sha"], reviewed["base_sha"]],
        "validated_tree_sha": tree,
        "mechanical_merge_tree_sha": tree,
        "mechanical_conflict_paths": [],
        "manual_conflict_resolution_delta": [],
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "validation_execution": {
            "registry_digest": MODULE.fast_path.digest_json(binding),
            "command_set_digest": MODULE.fast_path.digest_json(
                binding["validation"]
            ),
        },
        "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": "fixture"},
        "eligibility": {
            "eligible": True,
            "lifecycle_identity": "delivery-lifecycle-001",
            "draft_before": False,
            "draft_after": False,
            "ready_before": True,
            "ready_after": True,
            "ready_transition": False,
            "review_requested": False,
            "unrestricted_reviews_before": 1,
            "unrestricted_reviews_after": 1,
            "remediation_cycles_before": 2,
            "remediation_cycles_after": 2,
            "exceptional_recoveries_before": 1,
            "exceptional_recoveries_after": 1,
            "exceptional_continuations_before": 0,
            "exceptional_continuations_after": 0,
            "cycle_3": False,
        },
    }
    receipt = MODULE.fast_path.create_validation_receipt(
        repository=reviewed["repository"],
        head_sha=reviewed["head_sha"],
        validated_tree_sha=tree,
        registry=binding,
        command_set=binding["validation"],
        successful_result=True,
        reviewed_state=stable,
        manual_gate_evidence=[
            {
                "gate": gate,
                "satisfied": True,
                "evidence": f"Verified integration evidence {index}",
            }
            for index, gate in enumerate(binding["manual_gates"], start=1)
        ],
        eligibility_evidence_digest=eligibility_digest,
        integration_evidence_digest=MODULE.fast_path.digest_json(integration),
    )
    attestation = MODULE.fast_path.create_ready_integration_attestation(
        repository=reviewed["repository"],
        head_sha=expected_head,
        registry=binding,
        command_set=binding["validation"],
        reviewed_state=stable,
        validation_receipt=receipt,
        integration_evidence=integration,
    )
    return integration, receipt, attestation


def validation_receipt_payload(reviewed: dict[str, Any]) -> dict[str, Any]:
    binding = MODULE._validation_registry_binding(
        MODULE._load_repository_entry(reviewed["repository"])
    )
    manual_gate_evidence = [
        {
            "gate": gate,
            "satisfied": True,
            "evidence": f"Verified integration evidence {index}",
        }
        for index, gate in enumerate(binding["manual_gates"], start=1)
    ]
    fields = {
        "schema_version": "1.0",
        "kind": "VALIDATION_RECEIPT",
        "repository": reviewed["repository"],
        "head_sha": reviewed["head_sha"],
        "validated_tree_sha": "f" * 40,
        "registry_digest": MODULE._digest_json(binding),
        "command_set_digest": MODULE._digest_json(binding["validation"]),
        "successful_result": True,
        "reviewed_state_digest": reviewed["state_digest"],
        "reviewed_feedback_digest": reviewed["feedback_digest"],
        "manual_gate_evidence": manual_gate_evidence,
    }
    return {**fields, "receipt_digest": MODULE._digest_json(fields)}


def eligibility_payload(
    reviewed: dict[str, Any],
    thread_ids: Sequence[str],
) -> dict[str, Any]:
    fields = {
        "schema_version": "1.1",
        "repository": reviewed["repository"],
        "pull_request_number": reviewed["pull_request_number"],
        "reviewed_head_sha": reviewed["head_sha"],
        "reviewed_state_digest": reviewed["state_digest"],
        "eligible_threads": [
            {
                "thread_id": thread_id,
                "classification": "VALID_ACTIONABLE",
                "disposition": "CORRECTED_AND_VERIFIED",
                "finding_ids": [f"finding-{index}"],
                "evidence_digest": f"{index:x}" * 64,
                "follow_up": None,
            }
            for index, thread_id in enumerate(thread_ids, start=1)
        ],
    }
    return fields


def late_disposition_payload(
    attestation: dict[str, Any],
    *,
    thread_id: str = "PRRT_LATE_NON_BLOCKING",
    comment_id: str = "PRRC_LATE_FINDING",
    comment_database_id: int = 1001,
    body: str = "The reported recovery behavior is not present.",
    replies: list[tuple[str, int, str, str]] | None = None,
    delivery_issue: int = 724,
    pull_request: int = 123,
    repository: str = "SecPal/api",
    signer_format: str = "ssh",
    signer_fingerprint: str = "SHA256:fixtureDeliverySigner",
    classification: str = "INVALID_FALSE_OR_MISLEADING",
    disposition: str = "DISPROVEN_WITH_EVIDENCE",
) -> dict[str, Any]:
    reply_state = [
        {
            "node_id": node_id,
            "database_id": database_id,
            "body_digest": MODULE._body_digest(reply_body),
            "reply_to_id": reply_to_id,
        }
        for node_id, database_id, reply_body, reply_to_id in (replies or [])
    ]
    return {
        "schema_version": MODULE.late_disposition.schema_version_for_decision(
            classification, disposition
        ),
        "kind": "LATE_FEEDBACK_DISPOSITION",
        "repository": repository,
        "delivery_issue_number": delivery_issue,
        "pull_request_number": pull_request,
        "head_sha": attestation["head_sha"],
        "validated_tree_sha": attestation["validated_tree_sha"],
        "validation_receipt_digest": attestation[
            "validation_receipt_digest"
        ],
        "validation_attestation_digest": attestation["attestation_digest"],
        "final_eligibility_evidence_digest": attestation[
            "eligibility_evidence_digest"
        ],
        "delivery_signer": {
            "format": signer_format,
            "fingerprint": signer_fingerprint,
        },
        "authorized_action": "RESOLVE_EXACT_REVIEW_THREADS",
        "threads": [
            {
                "thread_id": thread_id,
                "top_level_comment_node_id": comment_id,
                "top_level_comment_database_id": comment_database_id,
                "finding_body_digest": MODULE._body_digest(body),
                "reply_state_digest": MODULE._digest_json(reply_state),
                "reply_count": len(reply_state),
                "is_resolved": False,
                "is_outdated": False,
                "classification": classification,
                "disposition": disposition,
                "technically_blocking": False,
                "classification_evidence_digest": "d" * 64,
                "authorized_action": "RESOLVE_REVIEW_THREAD",
            }
        ],
    }


def write_authenticated_resolution_inputs(
    directory: str,
    thread_ids: Sequence[str],
    *,
    manifest: dict[str, Any] | None = None,
    eligibility_thread_ids: Sequence[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], FakeGit]:
    reviewed = reviewed_state_payload(thread_ids[0], [])
    if len(thread_ids) > 1:
        reviewed["threads"] = [
            {
                "node_id": thread_id,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [],
            }
            for thread_id in thread_ids
        ]
        feedback = {
            key: reviewed[key]
            for key in (
                "pull_request_reactions",
                "reviews",
                "conversation_comments",
                "threads",
            )
        }
        reviewed["feedback_digest"] = MODULE._digest_json(feedback)
        identity = {
            key: reviewed[key]
            for key in (
                "repository",
                "pull_request_number",
                "head_sha",
                "base_ref",
                "base_sha",
                "pr_state",
            )
        }
        reviewed["state_digest"] = MODULE._digest_json(
            {**identity, "feedback": feedback}
        )
    eligibility = manifest or eligibility_payload(
        reviewed,
        thread_ids if eligibility_thread_ids is None else eligibility_thread_ids,
    )
    eligibility_digest = MODULE._digest_json(eligibility)
    attestation = validation_attestation_payload(
        reviewed,
        eligibility_digest,
    )
    root = Path(directory)
    (root / "reviewed.json").write_text(
        json.dumps(reviewed),
        encoding="utf-8",
    )
    (root / "validation.json").write_text(
        json.dumps(attestation),
        encoding="utf-8",
    )
    (root / "eligibility.json").write_text(
        json.dumps(eligibility),
        encoding="utf-8",
    )
    git = FakeGit(
        expected_head=attestation["head_sha"],
        reviewed_head=reviewed["head_sha"],
        tree=attestation["validated_tree_sha"],
        receipt_digest=attestation["validation_receipt_digest"],
    )
    return reviewed, attestation, eligibility, git


def run_late_resolution_fixture(
    directory: str,
    *,
    artifact_mutator: Any | None = None,
    live_comments: list[tuple[str, str, str | None]] | None = None,
    live_head: str | None = None,
    live_outdated: bool = False,
    live_resolved: bool = False,
    live_thread_id: str = "PRRT_LATE_NON_BLOCKING",
    final_reviewed_thread_id: str = "PRRT_FINAL_KNOWN",
    final_eligibility_thread_ids: Sequence[str] | None = None,
    apply: bool = True,
    signature_error: Exception | None = None,
    classification: str = "INVALID_FALSE_OR_MISLEADING",
    disposition: str = "DISPROVEN_WITH_EVIDENCE",
) -> tuple[dict[str, Any], FakeGh, FakeGit]:
    root = Path(directory)
    reviewed, attestation, _eligibility, git = (
        write_authenticated_resolution_inputs(
            directory,
            [final_reviewed_thread_id],
            eligibility_thread_ids=final_eligibility_thread_ids,
        )
    )
    body = "The reported recovery behavior is not present."
    artifact = late_disposition_payload(
        attestation,
        body=body,
        classification=classification,
        disposition=disposition,
    )
    classification = {
        "schema_version": artifact["schema_version"],
        "kind": "LATE_FEEDBACK_CLASSIFICATION",
        "repository": "SecPal/api",
        "delivery_issue_number": 724,
        "pull_request_number": 123,
        "head_sha": attestation["head_sha"],
        "delivery_signer": {
            "format": "ssh",
            "fingerprint": "SHA256:fixtureDeliverySigner",
        },
        "authorized_purpose": "AUTHORIZE_LATE_FEEDBACK_DISPOSITION",
        "finding_id": "LF-LATE-1",
        "finding_evidence_digest": "c" * 64,
        "thread": {
            key: value
            for key, value in artifact["threads"][0].items()
            if key
            not in {"classification_evidence_digest", "authorized_action"}
        },
    }
    classification["thread"]["technical_blockers"] = []
    classification_path = root / "late-classification.json"
    classification_signature_path = root / "late-classification.json.sig"
    classification_path.write_bytes(
        MODULE.late_disposition.canonical_json_bytes(classification)
    )
    classification_signature_path.write_text(
        "fixture classification signature", encoding="utf-8"
    )
    artifact["threads"][0]["classification_evidence_digest"] = hashlib.sha256(
        classification_path.read_bytes()
    ).hexdigest()
    if artifact_mutator is not None:
        artifact_mutator(artifact)
    artifact_path = root / "late-disposition.json"
    signature_path = root / "late-disposition.json.sig"
    artifact_path.write_bytes(MODULE.late_disposition.canonical_json_bytes(artifact))
    signature_path.write_text("fixture signature", encoding="utf-8")
    comments = live_comments or [("PRRC_LATE_FINDING", body, None)]
    response = target_response(
        live_thread_id,
        head=live_head or attestation["head_sha"],
        outdated=live_outdated,
        resolved=live_resolved,
        comments=comments,
    )
    responses = [response]
    if apply:
        responses.extend(
            [response, response, response, response, resolve_response(live_thread_id)]
        )
    github = FakeGh(responses)

    def verify_signature(
        artifact_value: Path,
        _signature_value: Path,
        _expected_signer: Any,
        **_kwargs: Any,
    ) -> bytes:
        if signature_error is not None:
            raise signature_error
        return artifact_value.read_bytes()

    with (
        mock.patch.object(MODULE, "_run_git", git),
        mock.patch.object(MODULE, "_run_gh", github),
        mock.patch.object(
            MODULE.late_disposition,
            "verify_detached_signature",
            side_effect=verify_signature,
        ),
    ):
        result = MODULE.resolve_late_disposition_threads(
            "SecPal/api",
            724,
            123,
            attestation["head_sha"],
            ("PRRT_LATE_NON_BLOCKING",),
            apply=apply,
            repository_root=root,
            final_reviewed_state_path=root / "reviewed.json",
            expected_final_reviewed_state_digest=reviewed["state_digest"],
            final_validation_evidence_path=root / "validation.json",
            final_eligibility_evidence_path=root / "eligibility.json",
            late_classification_evidence_path=classification_path,
            late_classification_signature_path=classification_signature_path,
            late_disposition_evidence_path=artifact_path,
            late_disposition_signature_path=signature_path,
        )
    return result, github, git


def run_late_classification_origin_fixture(
    directory: str,
    *,
    reviewed_thread_id: str,
    eligibility_thread_ids: Sequence[str],
    technically_blocking: bool = False,
    technical_blockers: Sequence[str] = (),
    target_thread_id: str = "PRRT_LATE_ORIGIN_TARGET",
    target_database_id: Any = 1001,
    artifact_signer: mock.Mock | None = None,
    classification: str = "INVALID_FALSE_OR_MISLEADING",
    disposition: str = "DISPROVEN_WITH_EVIDENCE",
) -> tuple[dict[str, Any], mock.Mock]:
    root = Path(directory)
    delivery = root / "delivery"
    output = root / "output"
    delivery.mkdir()
    output.mkdir()
    body = "Exact independently classified non-blocking finding."
    reviewed = reviewed_state_payload(
        reviewed_thread_id,
        [(f"PRRC_ROOT_{reviewed_thread_id}", body, None)],
    )
    eligibility = eligibility_payload(reviewed, eligibility_thread_ids)
    attestation = validation_attestation_payload(
        reviewed,
        MODULE._digest_json(eligibility),
    )
    (delivery / "reviewed.json").write_text(
        json.dumps(reviewed), encoding="utf-8"
    )
    (delivery / "validation.json").write_text(
        json.dumps(attestation), encoding="utf-8"
    )
    (delivery / "eligibility.json").write_text(
        json.dumps(eligibility), encoding="utf-8"
    )
    git = FakeGit(
        expected_head=attestation["head_sha"],
        reviewed_head=reviewed["head_sha"],
        tree=attestation["validated_tree_sha"],
        receipt_digest=attestation["validation_receipt_digest"],
    )
    response = target_response(
        target_thread_id,
        head=attestation["head_sha"],
        comments=[("PRRC_LATE_ORIGIN_ROOT", body, None)],
    )
    response["data"]["node"]["comments"]["nodes"][0]["databaseId"] = (
        target_database_id
    )
    github = FakeGh([response, response])
    def sign(
        artifact: dict[str, Any],
        artifact_output: Path,
        signature_output: Path,
        **_kwargs: Any,
    ) -> None:
        artifact_output.write_bytes(
            MODULE.late_disposition.canonical_json_bytes(artifact)
        )
        signature_output.write_text("fixture signature", encoding="utf-8")

    signer = artifact_signer or mock.Mock(side_effect=sign)
    with (
        mock.patch.object(MODULE, "_run_git", git),
        mock.patch.object(MODULE, "_run_gh", github),
        mock.patch.object(MODULE, "_late_signing_key", return_value="/fixture/key"),
        mock.patch.object(MODULE.late_disposition, "sign_artifact", signer),
    ):
        result = MODULE.create_late_classification_artifact(
            "SecPal/api",
            724,
            123,
            attestation["head_sha"],
            repository_root=delivery,
            final_reviewed_state_path=delivery / "reviewed.json",
            expected_final_reviewed_state_digest=reviewed["state_digest"],
            final_validation_evidence_path=delivery / "validation.json",
            final_eligibility_evidence_path=delivery / "eligibility.json",
            thread_id=target_thread_id,
            finding_id="LF-LATE-ORIGIN",
            finding_evidence_digest=hashlib.sha256(body.encode()).hexdigest(),
            classification=classification,
            disposition=disposition,
            technically_blocking=technically_blocking,
            technical_blockers=technical_blockers,
            output_path=output / "classification.json",
            signature_output_path=output / "classification.sig",
        )
    return result, signer


class ResolveFixedThreadsTests(TestCase):
    def test_lifecycle_helper_import_ignores_repository_root_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical_package = root / "scripts/secpal_pr_review"
            shadow_package = root / "secpal_pr_review"
            canonical_package.mkdir(parents=True)
            shadow_package.mkdir()
            (canonical_package / "__init__.py").write_text("", encoding="utf-8")
            (canonical_package / "lifecycle_orchestration.py").write_text(
                'ORIGIN = "canonical"\n', encoding="utf-8"
            )
            marker = root / "shadow-executed"
            (shadow_package / "__init__.py").write_text("", encoding="utf-8")
            (shadow_package / "lifecycle_orchestration.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            module_names = (
                "secpal_pr_review",
                "secpal_pr_review.lifecycle_orchestration",
            )
            loaded_modules = {
                name: sys.modules.get(name) for name in module_names
            }
            original_path = list(sys.path)
            try:
                for name in module_names:
                    sys.modules.pop(name, None)
                with mock.patch.object(MODULE, "REPOSITORY_ROOT", root):
                    loaded = MODULE._load_lifecycle_orchestration_helper()
                self.assertEqual(loaded.ORIGIN, "canonical")
                self.assertEqual(
                    Path(loaded.__file__).resolve(),
                    (canonical_package / "lifecycle_orchestration.py").resolve(),
                )
                self.assertFalse(marker.exists())
                self.assertEqual(sys.path, original_path)
            finally:
                for name in module_names:
                    sys.modules.pop(name, None)
                for name, loaded in loaded_modules.items():
                    if loaded is not None:
                        sys.modules[name] = loaded
                sys.path[:] = original_path

    def test_recovery_bound_source_requires_independent_recovery_authority(
        self,
    ) -> None:
        thread_id = "PRRT_RECOVERY_AUTHORITY"
        current = FakeGh(
            [target_response(thread_id, head="c" * 40, outdated=True)]
        )

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "Recovery-bound source evidence requires canonical Recovery authority",
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "c" * 40,
                [thread_id],
                apply=False,
                runner=current,
                expected_targets={
                    thread_id: expected_thread_state(thread_id, outdated=True)
                },
                recovery_bound=True,
                recovery_authority=False,
            )

        self.assertEqual(current.calls, [])

    def test_ordinary_attestation_requires_eligibility_digest_before_indexing(
        self,
    ) -> None:
        thread_id = "PRRT_ELIGIBILITY_OMISSION"
        reviewed = reviewed_state_payload(thread_id, [])
        registry = MODULE._validation_registry_binding(
            MODULE._load_repository_entry(reviewed["repository"])
        )
        stable = MODULE.fast_path.StableFeedbackState.from_payload(reviewed)
        gates = [
            {
                "gate": gate,
                "satisfied": True,
                "evidence": f"Verified omission fixture {index}",
            }
            for index, gate in enumerate(registry["manual_gates"], start=1)
        ]
        receipt = MODULE.fast_path.create_validation_receipt(
            repository=reviewed["repository"],
            head_sha=reviewed["head_sha"],
            validated_tree_sha="f" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=stable,
            manual_gate_evidence=gates,
            eligibility_evidence_digest=None,
        )
        attestation = MODULE.fast_path.create_validation_attestation(
            repository=reviewed["repository"],
            head_sha="c" * 40,
            registry=registry,
            command_set=registry["validation"],
            successful_result=True,
            reviewed_state=stable,
            validation_receipt=receipt,
        )
        self.assertNotIn("eligibility_evidence_digest", attestation)
        eligibility = eligibility_payload(reviewed, (thread_id,))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed_path = root / "reviewed.json"
            attestation_path = root / "attestation.json"
            eligibility_path = root / "eligibility.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            attestation_path.write_text(
                json.dumps(attestation), encoding="utf-8"
            )
            eligibility_path.write_text(
                json.dumps(eligibility), encoding="utf-8"
            )
            stderr = StringIO()
            fake = FakeGh([])
            with redirect_stdout(StringIO()), redirect_stderr(stderr), mock.patch.object(
                MODULE, "_run_gh", fake
            ):
                exit_code = MODULE.main(
                    [
                        "--repo",
                        "SecPal/api",
                        "--pr",
                        "123",
                        "--repo-root",
                        str(root),
                        "--expected-head",
                        "c" * 40,
                        "--reviewed-state",
                        str(reviewed_path),
                        "--expected-reviewed-state-digest",
                        reviewed["state_digest"],
                        "--validation-evidence",
                        str(attestation_path),
                        "--eligibility-evidence",
                        str(eligibility_path),
                        "--thread-id",
                        thread_id,
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "ERROR: validation evidence eligibility digest is missing or malformed",
            stderr.getvalue(),
        )
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertEqual(fake.calls, [])

    def test_ordinary_attestation_rejects_malformed_eligibility_digest(self) -> None:
        thread_id = "PRRT_ELIGIBILITY_MALFORMED"
        reviewed_payload = reviewed_state_payload(thread_id, [])
        attestation = validation_attestation_payload(reviewed_payload)
        attestation["eligibility_evidence_digest"] = "not-a-digest"
        fields = {
            key: value
            for key, value in attestation.items()
            if key != "attestation_digest"
        }
        attestation["attestation_digest"] = MODULE._digest_json(fields)
        reviewed = mock.Mock(
            head_sha=reviewed_payload["head_sha"],
            state_digest=reviewed_payload["state_digest"],
            feedback_digest=reviewed_payload["feedback_digest"],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attestation.json"
            path.write_text(json.dumps(attestation), encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "validation evidence eligibility digest is missing or malformed",
            ):
                MODULE.load_validation_evidence(
                    path,
                    reviewed_payload["repository"],
                    attestation["head_sha"],
                    reviewed,
                )

    def test_validation_evidence_rejects_duplicate_recovery_binding(self) -> None:
        thread_id = "PRRT_RECOVERY_DUPLICATE"
        reviewed_payload = reviewed_state_payload(thread_id, [])
        eligibility = eligibility_payload(reviewed_payload, (thread_id,))
        _receipt, attestation = recovery_validation_payloads(
            reviewed_payload,
            MODULE._digest_json(eligibility),
        )
        canonical = json.dumps(attestation, separators=(",", ":"))
        binding = (
            '"exceptional_recovery_evidence_digest":"' + "9" * 64 + '"'
        )
        duplicate = binding + "," + binding
        self.assertEqual(canonical.count(binding), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed_path = root / "reviewed.json"
            attestation_path = root / "attestation.json"
            reviewed_path.write_text(json.dumps(reviewed_payload), encoding="utf-8")
            attestation_path.write_text(
                canonical.replace(binding, duplicate), encoding="utf-8"
            )
            reviewed = MODULE.load_reviewed_state(
                reviewed_path,
                reviewed_payload["repository"],
                reviewed_payload["pull_request_number"],
                reviewed_payload["state_digest"],
                (thread_id,),
            )
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "validation evidence is unavailable or malformed",
            ):
                MODULE.load_validation_evidence(
                    attestation_path,
                    reviewed_payload["repository"],
                    attestation["head_sha"],
                    reviewed,
                )

    def test_recovery_authority_consumer_cross_binds_shared_verifier(self) -> None:
        thread_id = "PRRT_RECOVERY_CONSUMER"
        reviewed_payload = reviewed_state_payload(thread_id, [])
        eligibility_payload_value = eligibility_payload(
            reviewed_payload, (thread_id,)
        )
        eligibility_digest = MODULE._digest_json(eligibility_payload_value)
        _receipt, attestation = recovery_validation_payloads(
            reviewed_payload, eligibility_digest
        )
        reviewed = MODULE.ReviewedState(
            head_sha=reviewed_payload["head_sha"],
            state_digest=reviewed_payload["state_digest"],
            feedback_digest=reviewed_payload["feedback_digest"],
            targets={},
            thread_ids=frozenset({thread_id}),
            payload=reviewed_payload,
        )
        validation = MODULE.ValidationEvidence(
            kind="attestation",
            evidence_digest=attestation["attestation_digest"],
            validated_tree_sha=attestation["validated_tree_sha"],
            validation_receipt_digest=attestation[
                "validation_receipt_digest"
            ],
            eligibility_evidence_digest=eligibility_digest,
            attestation=attestation,
        )
        eligibility = MODULE.EligibilityEvidence(
            eligibility_digest,
            MODULE._canonical_json_bytes(eligibility_payload_value),
            (thread_id,),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recovery_path = root / "recovery.json"
            authorization_path = root / "authorization.json"
            recovery_path.write_text('{"schema_version":"1.0"}', encoding="utf-8")
            authorization_path.write_bytes(b"signed authorization")
            verifier = mock.Mock(
                return_value=mock.Mock(recovery_digest="9" * 64)
            )
            with mock.patch.object(
                MODULE.lifecycle_orchestration,
                "verify_exceptional_recovery_authority",
                verifier,
            ):
                MODULE.verify_recovery_bound_source_authority(
                    validation,
                    reviewed,
                    eligibility,
                    repository_root=root,
                    repository=reviewed_payload["repository"],
                    delivery_issue=790,
                    pull_request=reviewed_payload["pull_request_number"],
                    resulting_head_sha=attestation["head_sha"],
                    recovery_evidence_path=recovery_path,
                    recovery_authorization_path=authorization_path,
                )

        verifier.assert_called_once_with(
            {"schema_version": "1.0"},
            orchestration_authorization=b"signed authorization",
            reviewed_state_evidence=reviewed_payload,
            eligibility_evidence=eligibility_payload_value,
            repository_root=root,
            repository=reviewed_payload["repository"],
            delivery_issue=790,
            pull_request=reviewed_payload["pull_request_number"],
            resulting_head_sha=attestation["head_sha"],
        )

    def test_recovery_authority_consumer_rejects_substituted_digest(self) -> None:
        validation = MODULE.ValidationEvidence(
            kind="attestation",
            evidence_digest="1" * 64,
            validated_tree_sha="2" * 40,
            validation_receipt_digest="3" * 64,
            eligibility_evidence_digest="4" * 64,
            attestation={"exceptional_recovery_evidence_digest": "9" * 64},
        )
        reviewed = MODULE.ReviewedState(
            head_sha="5" * 40,
            state_digest="6" * 64,
            feedback_digest="7" * 64,
            targets={},
            thread_ids=frozenset(),
            payload={},
        )
        eligibility_payload_value = {}
        eligibility = MODULE.EligibilityEvidence(
            MODULE._digest_json(eligibility_payload_value),
            MODULE._canonical_json_bytes(eligibility_payload_value),
            (),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recovery_path = root / "recovery.json"
            authorization_path = root / "authorization.json"
            recovery_path.write_text("{}", encoding="utf-8")
            authorization_path.write_bytes(b"signed authorization")
            with (
                mock.patch.object(
                    MODULE.lifecycle_orchestration,
                    "verify_exceptional_recovery_authority",
                    return_value=mock.Mock(recovery_digest="8" * 64),
                ),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "substituted Recovery authority",
                ),
            ):
                MODULE.verify_recovery_bound_source_authority(
                    validation,
                    reviewed,
                    eligibility,
                    repository_root=root,
                    repository="SecPal/api",
                    delivery_issue=790,
                    pull_request=123,
                    resulting_head_sha="a" * 40,
                    recovery_evidence_path=recovery_path,
                    recovery_authorization_path=authorization_path,
                )

    def test_recovery_bound_attestation_uses_canonical_source_verifier(self) -> None:
        thread_id = "PRRT_RECOVERY_BOUND"
        reviewed_payload = reviewed_state_payload(
            thread_id,
            [("PRRC_RECOVERY_BOUND", "Corrected recovery finding.", None)],
            outdated=True,
        )
        eligibility = eligibility_payload(reviewed_payload, (thread_id,))
        receipt, attestation = recovery_validation_payloads(
            reviewed_payload,
            MODULE._digest_json(eligibility),
        )
        binding = MODULE._validation_registry_binding(
            MODULE._load_repository_entry(reviewed_payload["repository"])
        )
        stable = MODULE.fast_path.StableFeedbackState.from_payload(reviewed_payload)
        MODULE.fast_path.verify_validation_attestation(
            attestation,
            repository=reviewed_payload["repository"],
            head_sha=attestation["head_sha"],
            registry=binding,
            command_set=binding["validation"],
            reviewed_state=stable,
            commit_parent_sha=reviewed_payload["head_sha"],
            commit_tree_sha=receipt["validated_tree_sha"],
            commit_validation_receipt_digest=receipt["receipt_digest"],
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed_path = root / "reviewed.json"
            attestation_path = root / "attestation.json"
            reviewed_path.write_text(json.dumps(reviewed_payload), encoding="utf-8")
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            reviewed = MODULE.load_reviewed_state(
                reviewed_path,
                reviewed_payload["repository"],
                reviewed_payload["pull_request_number"],
                reviewed_payload["state_digest"],
                (thread_id,),
            )
            validation = MODULE.load_validation_evidence(
                attestation_path,
                reviewed_payload["repository"],
                attestation["head_sha"],
                reviewed,
            )

        self.assertEqual(validation.attestation, attestation)
        self.assertEqual(validation.validation_receipt, receipt)

    def test_recovery_bound_attestation_rejects_digest_binding_drift(self) -> None:
        thread_id = "PRRT_RECOVERY_BINDING"
        reviewed_payload = reviewed_state_payload(thread_id, [])
        eligibility = eligibility_payload(reviewed_payload, (thread_id,))
        _receipt, attestation = recovery_validation_payloads(
            reviewed_payload,
            MODULE._digest_json(eligibility),
        )
        mutations = {
            "missing": None,
            "substituted": "8" * 64,
            "malformed": "not-a-digest",
        }
        for label, digest in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                changed = copy.deepcopy(attestation)
                if digest is None:
                    changed.pop("exceptional_recovery_evidence_digest")
                else:
                    changed["exceptional_recovery_evidence_digest"] = digest
                fields = {
                    key: value
                    for key, value in changed.items()
                    if key != "attestation_digest"
                }
                changed["attestation_digest"] = MODULE._digest_json(fields)
                root = Path(directory)
                reviewed_path = root / "reviewed.json"
                attestation_path = root / "attestation.json"
                reviewed_path.write_text(
                    json.dumps(reviewed_payload), encoding="utf-8"
                )
                attestation_path.write_text(json.dumps(changed), encoding="utf-8")
                reviewed = MODULE.load_reviewed_state(
                    reviewed_path,
                    reviewed_payload["repository"],
                    reviewed_payload["pull_request_number"],
                    reviewed_payload["state_digest"],
                    (thread_id,),
                )
                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "validation evidence is invalid or stale",
                ):
                    MODULE.load_validation_evidence(
                        attestation_path,
                        reviewed_payload["repository"],
                        attestation["head_sha"],
                        reviewed,
                    )

    def test_recovery_bound_source_keeps_current_outdated_target_independent(
        self,
    ) -> None:
        thread_id = "PRRT_RECOVERY_OUTDATED"
        comment = ("PRRC_RECOVERY_OUTDATED", "Exact current target.", None)
        current = FakeGh(
            [
                target_response(
                    thread_id,
                    head="c" * 40,
                    comments=[comment],
                    outdated=True,
                )
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "c" * 40,
            [thread_id],
            apply=False,
            runner=current,
            expected_targets={
                thread_id: expected_thread_state(
                    thread_id,
                    [comment],
                    outdated=True,
                )
            },
            recovery_bound=True,
        )

        self.assertEqual(result["pending"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(current.calls), 1)

    def test_unresolved_target_accepts_monotonic_post_fix_outdated_drift(
        self,
    ) -> None:
        thread_id = "PRRT_GENERIC_POST_FIX_OUTDATED"
        comment_id = "PRRC_GENERIC_POST_FIX_OUTDATED"
        body = "The exact authenticated source correction is present."
        reviewed = expected_thread_state(
            thread_id,
            [(comment_id, body, None)],
            resolved=False,
            outdated=False,
        )
        current = MODULE.ThreadState(
            thread_id=thread_id,
            is_resolved=False,
            is_outdated=True,
            comments=(
                MODULE.ThreadCommentState(
                    comment_id=comment_id,
                    database_id=1001,
                    body_digest=MODULE._body_digest(body),
                    reply_to_id=None,
                ),
            ),
        )

        self.assertEqual(
            MODULE._classify_reviewed_target(current, reviewed),
            "ACTIONABLE",
        )

    def test_resolved_target_composes_with_monotonic_post_fix_outdated_drift(
        self,
    ) -> None:
        reviewed = expected_thread_state(
            "PRRT_OUTDATED_DRIFT",
            [("PRRC_OUTDATED_DRIFT", "Keep outdated state bound.", None)],
            resolved=False,
            outdated=False,
        )
        current = MODULE.ThreadState(
            thread_id="PRRT_OUTDATED_DRIFT",
            is_resolved=True,
            is_outdated=True,
            comments=(
                MODULE.ThreadCommentState(
                    comment_id="PRRC_OUTDATED_DRIFT",
                    database_id=1,
                    body_digest=MODULE._body_digest("Keep outdated state bound."),
                    reply_to_id=None,
                ),
            ),
        )

        self.assertEqual(
            MODULE._classify_reviewed_target(current, reviewed),
            "ALREADY_SATISFIED",
        )

    def test_target_classification_allows_only_directional_outdated_drift(
        self,
    ) -> None:
        thread_id = "PRRT_OUTDATED_CLASSIFICATION"
        comment_id = "PRRC_OUTDATED_CLASSIFICATION"
        body = "Preserve the reviewed target state."

        def current(*, resolved: bool, outdated: bool) -> Any:
            return MODULE.ThreadState(
                thread_id=thread_id,
                is_resolved=resolved,
                is_outdated=outdated,
                comments=(
                    MODULE.ThreadCommentState(
                        comment_id=comment_id,
                        database_id=1,
                        body_digest=MODULE._body_digest(body),
                        reply_to_id=None,
                    ),
                ),
            )

        cases = (
            (False, False, False, False, "ACTIONABLE"),
            (False, False, False, True, "ACTIONABLE"),
            (False, False, True, False, "ALREADY_SATISFIED"),
            (False, False, True, True, "ALREADY_SATISFIED"),
            (False, True, False, True, "ACTIONABLE"),
            (False, True, False, False, "INCOMPATIBLE_DRIFT"),
            (False, True, True, True, "ALREADY_SATISFIED"),
            (False, True, True, False, "INCOMPATIBLE_DRIFT"),
            (True, False, False, False, "INCOMPATIBLE_DRIFT"),
            (True, False, True, False, "ALREADY_SATISFIED"),
            (True, False, True, True, "ALREADY_SATISFIED"),
            (True, True, False, True, "INCOMPATIBLE_DRIFT"),
            (True, True, False, False, "INCOMPATIBLE_DRIFT"),
            (True, True, True, True, "ALREADY_SATISFIED"),
            (True, True, True, False, "INCOMPATIBLE_DRIFT"),
        )
        for (
            reviewed_resolved,
            reviewed_outdated,
            current_resolved,
            current_outdated,
            expected,
        ) in cases:
            reviewed = expected_thread_state(
                thread_id,
                [(comment_id, body, None)],
                resolved=reviewed_resolved,
                outdated=reviewed_outdated,
            )
            with self.subTest(
                reviewed_resolved=reviewed_resolved,
                reviewed_outdated=reviewed_outdated,
                current_resolved=current_resolved,
                current_outdated=current_outdated,
            ):
                self.assertEqual(
                    MODULE._classify_reviewed_target(
                        current(
                            resolved=current_resolved,
                            outdated=current_outdated,
                        ),
                        reviewed,
                    ),
                    expected,
                )

    def test_target_classification_rejects_non_boolean_outdated_state(self) -> None:
        thread_id = "PRRT_MALFORMED_OUTDATED_CLASSIFICATION"
        reviewed_comment = MODULE.ThreadCommentState(
            comment_id="PRRC_MALFORMED_OUTDATED_CLASSIFICATION",
            database_id=None,
            body_digest=MODULE._body_digest("Reject malformed metadata."),
            reply_to_id=None,
        )
        current_comment = MODULE.ThreadCommentState(
            comment_id="PRRC_MALFORMED_OUTDATED_CLASSIFICATION",
            database_id=1,
            body_digest=MODULE._body_digest("Reject malformed metadata."),
            reply_to_id=None,
        )
        valid_reviewed = MODULE.ExpectedThreadState(
            thread_id=thread_id,
            is_resolved=False,
            is_outdated=False,
            comments=(reviewed_comment,),
        )
        self.assertEqual(
            MODULE.validate_expected_targets(
                (thread_id,), {thread_id: valid_reviewed}
            ),
            {thread_id: valid_reviewed},
        )
        for reviewed_outdated, current_outdated in (
            (False, None),
            (False, "true"),
            (False, 1),
            (None, True),
            ("false", True),
            (0, True),
        ):
            reviewed = MODULE.ExpectedThreadState(
                thread_id=thread_id,
                is_resolved=False,
                is_outdated=reviewed_outdated,
                comments=(reviewed_comment,),
            )
            current = MODULE.ThreadState(
                thread_id=thread_id,
                is_resolved=False,
                is_outdated=current_outdated,
                comments=(current_comment,),
            )
            with self.subTest(
                reviewed_outdated=reviewed_outdated,
                current_outdated=current_outdated,
            ):
                self.assertEqual(
                    MODULE._classify_reviewed_target(current, reviewed),
                    "INCOMPATIBLE_DRIFT",
                )

    def test_integration_evidence_is_normalized_before_receipt_reconstruction(
        self,
    ) -> None:
        thread_id = "PRRT_INTEGRATION_NORMALIZATION"
        reviewed = reviewed_state_payload(
            thread_id,
            [("PRRC_INTEGRATION_NORMALIZATION", "Normalize evidence.", None)],
        )
        eligibility = eligibility_payload(reviewed, (thread_id,))
        integration, receipt, attestation = integration_validation_payloads(
            reviewed,
            MODULE._digest_json(eligibility),
            expected_head="c" * 40,
        )
        raw_integration = copy.deepcopy(integration)
        raw_integration["prior_delivery_head_sha"] = reviewed["head_sha"].upper()
        raw_integration["ordered_parent_shas"][0] = reviewed["head_sha"].upper()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed_path = root / "reviewed.json"
            attestation_path = root / "attestation.json"
            integration_path = root / "integration.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            integration_path.write_text(
                json.dumps(raw_integration), encoding="utf-8"
            )
            state = MODULE.load_reviewed_state(
                reviewed_path,
                "SecPal/api",
                123,
                reviewed["state_digest"],
                (thread_id,),
            )
            validation = MODULE.load_validation_evidence(
                attestation_path,
                "SecPal/api",
                "c" * 40,
                state,
                integration_path,
            )

        self.assertEqual(validation.integration_evidence, integration)
        self.assertEqual(validation.validation_receipt, receipt)

    def test_malformed_integration_parent_list_fails_during_evidence_loading(
        self,
    ) -> None:
        thread_id = "PRRT_INTEGRATION_PARENT_SHAPE"
        reviewed = reviewed_state_payload(
            thread_id,
            [("PRRC_INTEGRATION_PARENT_SHAPE", "Validate parents.", None)],
        )
        eligibility = eligibility_payload(reviewed, (thread_id,))
        integration, _receipt, attestation = integration_validation_payloads(
            reviewed,
            MODULE._digest_json(eligibility),
            expected_head="c" * 40,
        )
        integration["ordered_parent_shas"] = None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed_path = root / "reviewed.json"
            attestation_path = root / "attestation.json"
            integration_path = root / "integration.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            integration_path.write_text(json.dumps(integration), encoding="utf-8")
            state = MODULE.load_reviewed_state(
                reviewed_path,
                "SecPal/api",
                123,
                reviewed["state_digest"],
                (thread_id,),
            )
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "integration validation evidence is invalid or stale",
            ):
                MODULE.load_validation_evidence(
                    attestation_path,
                    "SecPal/api",
                    "c" * 40,
                    state,
                    integration_path,
                )

    def test_historical_ready_integration_attestation_cannot_authorize_resolution(
        self,
    ) -> None:
        reviewed = reviewed_state_payload(
            "PRRT_HISTORICAL_INTEGRATION",
            [("PRRC_HISTORICAL_INTEGRATION", "Historical finding.", None)],
        )
        payload = {
            "schema_version": "1.1",
            "kind": "READY_INTEGRATION_VALIDATION_ATTESTATION",
            "head_sha": "c" * 40,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            reviewed_path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            state = MODULE.load_reviewed_state(
                reviewed_path,
                "SecPal/api",
                123,
                reviewed["state_digest"],
                ("PRRT_HISTORICAL_INTEGRATION",),
            )
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "historical Ready integration attestation is not resolution authority",
            ):
                MODULE.load_validation_evidence(
                    path,
                    "SecPal/api",
                    "c" * 40,
                    state,
                    Path(directory) / "integration.json",
                )

    def test_eligibility_bound_ready_integration_authorizes_exact_thread(self) -> None:
        thread_id = "PRRT_INTEGRATION_ELIGIBLE"
        comment = ("PRRC_INTEGRATION_ROOT", "Intentional protocol body.", None)
        reviewed = reviewed_state_payload(thread_id, [comment])
        eligibility = eligibility_payload(reviewed, (thread_id,))
        eligibility_digest = MODULE._digest_json(eligibility)
        head = "c" * 40
        integration, receipt, attestation = integration_validation_payloads(
            reviewed, eligibility_digest, expected_head=head
        )
        github = FakeGh(
            [
                target_response(
                    thread_id,
                    head=head,
                    comments=[comment],
                )
            ]
        )
        git = FakeGit(
            expected_head=head,
            reviewed_head=reviewed["head_sha"],
            second_parent=reviewed["base_sha"],
            tree=attestation["validated_tree_sha"],
            receipt_digest=receipt["receipt_digest"],
            integration_digest=MODULE.fast_path.digest_json(integration),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("reviewed.json", reviewed),
                ("validation.json", attestation),
                ("eligibility.json", eligibility),
                ("integration.json", integration),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            with (
                mock.patch.object(MODULE, "_run_git", git),
                mock.patch.object(MODULE, "_run_gh", github),
            ):
                result = MODULE.resolve_threads(
                    "SecPal/api",
                    123,
                    head,
                    (thread_id,),
                    apply=False,
                    repository_root=root,
                    reviewed_state_path=root / "reviewed.json",
                    expected_reviewed_state_digest=reviewed["state_digest"],
                    validation_evidence_path=root / "validation.json",
                    eligibility_evidence_path=root / "eligibility.json",
                    integration_evidence_path=root / "integration.json",
                )

        self.assertEqual(result["pending"], [thread_id])
        self.assertEqual(result["status"], "success")

    def test_late_classification_rejects_missing_or_malformed_root_database_id(
        self,
    ) -> None:
        signer = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "top-level comment database ID is unavailable",
            ):
                run_late_classification_origin_fixture(
                    directory,
                    reviewed_thread_id="PRRT_FINAL_KNOWN",
                    eligibility_thread_ids=(),
                    target_database_id=None,
                    artifact_signer=signer,
                )
        signer.assert_not_called()

        for database_id in (0, -1, True, "1001"):
            signer = mock.Mock()
            with (
                self.subTest(database_id=database_id),
                tempfile.TemporaryDirectory() as directory,
            ):
                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "target thread comment identity is incomplete",
                ):
                    run_late_classification_origin_fixture(
                        directory,
                        reviewed_thread_id="PRRT_FINAL_KNOWN",
                        eligibility_thread_ids=(),
                        target_database_id=database_id,
                        artifact_signer=signer,
                    )
                signer.assert_not_called()

    def test_post_freeze_accepts_reviewed_but_ineligible_informational_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, signer = run_late_classification_origin_fixture(
                directory,
                reviewed_thread_id="PRRT_LATE_ORIGIN_TARGET",
                eligibility_thread_ids=(),
                classification="INFORMATIONAL",
                disposition="NON_ACTIONABLE",
            )
        self.assertEqual(result["status"], "LATE_CLASSIFICATION_AUTHENTICATED")
        self.assertEqual(result["origin"], "REVIEWED_BUT_INELIGIBLE")
        signer.assert_called_once()

    def test_cycle2_late_origin_rejects_commit_bound_eligible_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "already has commit-bound eligibility",
            ):
                run_late_classification_origin_fixture(
                    directory,
                    reviewed_thread_id="PRRT_LATE_ORIGIN_TARGET",
                    eligibility_thread_ids=("PRRT_LATE_ORIGIN_TARGET",),
                )

    def test_cycle2_late_origin_rejects_incoherent_final_evidence_pair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "final eligibility references a thread absent from final reviewed state",
            ):
                run_late_classification_origin_fixture(
                    directory,
                    reviewed_thread_id="PRRT_FINAL_KNOWN",
                    eligibility_thread_ids=("PRRT_LATE_ORIGIN_TARGET",),
                )

    def test_cycle2_late_origin_accepts_target_absent_from_both_final_sets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, signer = run_late_classification_origin_fixture(
                directory,
                reviewed_thread_id="PRRT_FINAL_KNOWN",
                eligibility_thread_ids=(),
            )
        self.assertEqual(result["status"], "LATE_CLASSIFICATION_AUTHENTICATED")
        signer.assert_called_once()

    def test_post_freeze_accepts_absent_informational_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, signer = run_late_classification_origin_fixture(
                directory,
                reviewed_thread_id="PRRT_FINAL_KNOWN",
                eligibility_thread_ids=(),
                classification="INFORMATIONAL",
                disposition="NON_ACTIONABLE",
            )
        self.assertEqual(result["origin"], "ABSENT_FROM_BOTH")
        signer.assert_called_once()

    def test_post_freeze_decision_authority_is_closed_and_origin_derived(
        self,
    ) -> None:
        invalid = (
            "INVALID_FALSE_OR_MISLEADING",
            "DISPROVEN_WITH_EVIDENCE",
        )
        informational = ("INFORMATIONAL", "NON_ACTIONABLE")
        self.assertEqual(
            MODULE.late_disposition.POST_FREEZE_DECISIONS,
            frozenset({invalid, informational}),
        )
        self.assertEqual(
            MODULE.late_disposition.POST_FREEZE_ORIGIN_DECISIONS,
            {
                "REVIEWED_BUT_INELIGIBLE": frozenset({informational}),
                "ABSENT_FROM_BOTH": frozenset({invalid, informational}),
            },
        )
        self.assertEqual(
            MODULE.late_disposition.SCHEMA_VERSION_DECISIONS,
            {
                "1.0": frozenset({invalid}),
                "1.1": frozenset({informational}),
            },
        )
        self.assertEqual(
            MODULE.late_disposition.schema_version_for_decision(*invalid),
            "1.0",
        )
        self.assertEqual(
            MODULE.late_disposition.schema_version_for_decision(*informational),
            "1.1",
        )

        self.assertNotIn(
            "NON_BLOCKING",
            {
                value
                for decision in MODULE.late_disposition.POST_FREEZE_DECISIONS
                for value in decision
            },
        )

    def test_post_freeze_rejects_arbitrary_decisions_before_signing(self) -> None:
        decisions = (
            ("VALID_ACTIONABLE", "CORRECTED_AND_VERIFIED"),
            ("INFORMATIONAL", "PENDING"),
            ("ARBITRARY", "NON_ACTIONABLE"),
        )
        for classification, disposition in decisions:
            signer = mock.Mock()
            with (
                self.subTest(
                    classification=classification,
                    disposition=disposition,
                ),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "decision is unsupported",
                ),
            ):
                run_late_classification_origin_fixture(
                    directory,
                    reviewed_thread_id="PRRT_FINAL_KNOWN",
                    eligibility_thread_ids=(),
                    classification=classification,
                    disposition=disposition,
                    artifact_signer=signer,
                )
            signer.assert_not_called()

    def test_post_freeze_rejects_all_technical_blockers_before_signing(
        self,
    ) -> None:
        for blocker in sorted(MODULE.late_disposition.TECHNICAL_BLOCKERS):
            signer = mock.Mock()
            with (
                self.subTest(blocker=blocker),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "decision is unsupported",
                ),
            ):
                run_late_classification_origin_fixture(
                    directory,
                    reviewed_thread_id="PRRT_FINAL_KNOWN",
                    eligibility_thread_ids=(),
                    classification="INFORMATIONAL",
                    disposition="NON_ACTIONABLE",
                    technically_blocking=True,
                    technical_blockers=(blocker,),
                    artifact_signer=signer,
                )
            signer.assert_not_called()

    def test_cycle2_disposition_reverifies_authenticated_final_origin(self) -> None:
        cases = (
            (
                "pre-existing",
                "PRRT_LATE_NON_BLOCKING",
                (),
                "unsupported for origin REVIEWED_BUT_INELIGIBLE",
            ),
            (
                "commit-bound",
                "PRRT_LATE_NON_BLOCKING",
                ("PRRT_LATE_NON_BLOCKING",),
                "already has commit-bound eligibility",
            ),
            (
                "incoherent",
                "PRRT_FINAL_KNOWN",
                ("PRRT_LATE_NON_BLOCKING",),
                "final eligibility references a thread absent",
            ),
        )
        for label, reviewed_thread, eligible_threads, error in cases:
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory() as directory,
                tempfile.TemporaryDirectory() as output_directory,
            ):
                root = Path(directory)
                output = Path(output_directory)
                reviewed, attestation, _eligibility, git = (
                    write_authenticated_resolution_inputs(
                        directory,
                        [reviewed_thread],
                        eligibility_thread_ids=eligible_threads,
                    )
                )
                classification = late_disposition_payload(attestation)["threads"][0]
                classification_path = output / "classification.json"
                classification_path.write_bytes(
                    MODULE.late_disposition.canonical_json_bytes(
                        {
                            "thread": {
                                "thread_id": classification["thread_id"]
                            }
                        }
                    )
                )
                with (
                    mock.patch.object(MODULE, "_run_git", git),
                    mock.patch.object(
                        MODULE.late_disposition,
                        "parse_classification_artifact",
                        return_value=mock.Mock(
                            thread=mock.Mock(
                                classification="INVALID_FALSE_OR_MISLEADING",
                                disposition="DISPROVEN_WITH_EVIDENCE",
                            )
                        ),
                    ),
                    self.assertRaisesRegex(MODULE.ResolutionError, error),
                ):
                    MODULE.create_late_disposition_artifact(
                        "SecPal/api",
                        724,
                        123,
                        attestation["head_sha"],
                        repository_root=root,
                        final_reviewed_state_path=root / "reviewed.json",
                        expected_final_reviewed_state_digest=reviewed["state_digest"],
                        final_validation_evidence_path=root / "validation.json",
                        final_eligibility_evidence_path=root / "eligibility.json",
                        classification_evidence_path=classification_path,
                        classification_signature_path=output / "classification.sig",
                        output_path=output / "late.json",
                        signature_output_path=output / "late.sig",
                    )

    def test_cycle2_resolver_reverifies_authenticated_final_origin(self) -> None:
        cases = (
            (
                "pre-existing",
                "PRRT_LATE_NON_BLOCKING",
                (),
                "unsupported for origin REVIEWED_BUT_INELIGIBLE",
            ),
            (
                "commit-bound",
                "PRRT_LATE_NON_BLOCKING",
                ("PRRT_LATE_NON_BLOCKING",),
                "already has commit-bound eligibility",
            ),
            (
                "incoherent",
                "PRRT_FINAL_KNOWN",
                ("PRRT_LATE_NON_BLOCKING",),
                "final eligibility references a thread absent",
            ),
        )
        for label, reviewed_thread, eligible_threads, error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(MODULE.ResolutionError, error):
                    run_late_resolution_fixture(
                        directory,
                        final_reviewed_thread_id=reviewed_thread,
                        final_eligibility_thread_ids=eligible_threads,
                    )

    def test_cycle2_final_eligibility_substitution_blocks_every_consumer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed, attestation, eligibility, git = (
                write_authenticated_resolution_inputs(
                    directory,
                    ["PRRT_FINAL_KNOWN"],
                    eligibility_thread_ids=(),
                )
            )
            substituted = copy.deepcopy(eligibility)
            substituted["pull_request_number"] = 124
            (root / "eligibility.json").write_text(
                json.dumps(substituted), encoding="utf-8"
            )
            with (
                mock.patch.object(MODULE, "_run_git", git),
                self.assertRaisesRegex(
                    MODULE.ResolutionError, "eligibility evidence is not authenticated"
                ),
            ):
                MODULE.create_late_classification_artifact(
                    "SecPal/api",
                    724,
                    123,
                    attestation["head_sha"],
                    repository_root=root,
                    final_reviewed_state_path=root / "reviewed.json",
                    expected_final_reviewed_state_digest=reviewed["state_digest"],
                    final_validation_evidence_path=root / "validation.json",
                    final_eligibility_evidence_path=root / "eligibility.json",
                    thread_id="PRRT_LATE_NON_BLOCKING",
                    finding_id="LF-LATE-ORIGIN",
                    finding_evidence_digest="c" * 64,
                    classification="INVALID_FALSE_OR_MISLEADING",
                    disposition="DISPROVEN_WITH_EVIDENCE",
                    technically_blocking=False,
                    technical_blockers=(),
                    output_path=root / "classification.json",
                    signature_output_path=root / "classification.sig",
                )

    def test_cycle2_final_artifact_drift_after_classification_blocks_consumers(
        self,
    ) -> None:
        for label in ("eligibility", "reviewed state"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result, _signer = run_late_classification_origin_fixture(
                    directory,
                    reviewed_thread_id="PRRT_FINAL_KNOWN",
                    eligibility_thread_ids=(),
                )
                self.assertEqual(
                    result["status"], "LATE_CLASSIFICATION_AUTHENTICATED"
                )
                delivery = root / "delivery"
                output = root / "output"
                reviewed = json.loads(
                    (delivery / "reviewed.json").read_text(encoding="utf-8")
                )
                if label == "eligibility":
                    eligibility = json.loads(
                        (delivery / "eligibility.json").read_text(encoding="utf-8")
                    )
                    eligibility["pull_request_number"] = 124
                    (delivery / "eligibility.json").write_text(
                        json.dumps(eligibility), encoding="utf-8"
                    )
                    error = "eligibility evidence is not authenticated"
                else:
                    reviewed["threads"].append(copy.deepcopy(reviewed["threads"][0]))
                    (delivery / "reviewed.json").write_text(
                        json.dumps(reviewed), encoding="utf-8"
                    )
                    error = "reviewed feedback state digest is invalid"
                arguments = {
                    "repository_root": delivery,
                    "final_reviewed_state_path": delivery / "reviewed.json",
                    "expected_final_reviewed_state_digest": reviewed["state_digest"],
                    "final_validation_evidence_path": delivery / "validation.json",
                    "final_eligibility_evidence_path": delivery / "eligibility.json",
                }
                with self.assertRaisesRegex(MODULE.ResolutionError, error):
                    MODULE.create_late_disposition_artifact(
                        "SecPal/api",
                        724,
                        123,
                        "c" * 40,
                        **arguments,
                        classification_evidence_path=output / "classification.json",
                        classification_signature_path=output / "classification.sig",
                        output_path=output / "disposition.json",
                        signature_output_path=output / "disposition.sig",
                    )
                with self.assertRaisesRegex(MODULE.ResolutionError, error):
                    MODULE.resolve_late_disposition_threads(
                        "SecPal/api",
                        724,
                        123,
                        "c" * 40,
                        ("PRRT_LATE_ORIGIN_TARGET",),
                        apply=False,
                        **arguments,
                        late_classification_evidence_path=(
                            output / "classification.json"
                        ),
                        late_classification_signature_path=(
                            output / "classification.sig"
                        ),
                        late_disposition_evidence_path=output / "disposition.json",
                        late_disposition_signature_path=output / "disposition.sig",
                    )

    def test_cycle2_final_boundary_rejects_eligibility_binding_and_shape_drift(
        self,
    ) -> None:
        cases = (
            ("repository", lambda value: value.update(repository="Other/repo")),
            ("pull request", lambda value: value.update(pull_request_number=124)),
            ("reviewed head", lambda value: value.update(reviewed_head_sha="b" * 40)),
            (
                "reviewed state",
                lambda value: value.update(reviewed_state_digest="9" * 64),
            ),
            ("schema", lambda value: value.update(schema_version="2.0")),
            (
                "duplicate thread",
                lambda value: value["eligible_threads"].append(
                    copy.deepcopy(value["eligible_threads"][0])
                ),
            ),
        )
        for label, mutate in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                reviewed, _attestation, eligibility, _git = (
                    write_authenticated_resolution_inputs(
                        directory,
                        ["PRRT_FINAL_KNOWN"],
                    )
                )
                mutate(eligibility)
                attestation = validation_attestation_payload(
                    reviewed,
                    MODULE._digest_json(eligibility),
                )
                (root / "eligibility.json").write_text(
                    json.dumps(eligibility), encoding="utf-8"
                )
                (root / "validation.json").write_text(
                    json.dumps(attestation), encoding="utf-8"
                )
                with self.assertRaises(MODULE.ResolutionError):
                    MODULE.load_final_feedback_boundary(
                        repository="SecPal/api",
                        number=123,
                        expected_head=attestation["head_sha"],
                        final_reviewed_state_path=root / "reviewed.json",
                        expected_final_reviewed_state_digest=reviewed["state_digest"],
                        final_validation_evidence_path=root / "validation.json",
                        final_eligibility_evidence_path=root / "eligibility.json",
                    )

    def test_cycle2_final_boundary_rejects_duplicate_or_changed_reviewed_membership(
        self,
    ) -> None:
        for label, authenticate_change in (
            ("duplicate", True),
            ("changed without digest", False),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                reviewed, attestation, _eligibility, _git = (
                    write_authenticated_resolution_inputs(
                        directory,
                        ["PRRT_FINAL_KNOWN"],
                        eligibility_thread_ids=(),
                    )
                )
                reviewed["threads"].append(copy.deepcopy(reviewed["threads"][0]))
                if authenticate_change:
                    feedback = {
                        key: reviewed[key]
                        for key in (
                            "pull_request_reactions",
                            "reviews",
                            "conversation_comments",
                            "threads",
                        )
                    }
                    reviewed["feedback_digest"] = MODULE._digest_json(feedback)
                    reviewed["state_digest"] = MODULE._digest_json(
                        {
                            "repository": reviewed["repository"],
                            "pull_request_number": reviewed["pull_request_number"],
                            "head_sha": reviewed["head_sha"],
                            "base_ref": reviewed["base_ref"],
                            "base_sha": reviewed["base_sha"],
                            "pr_state": reviewed["pr_state"],
                            "feedback": feedback,
                        }
                    )
                (root / "reviewed.json").write_text(
                    json.dumps(reviewed), encoding="utf-8"
                )
                with self.assertRaises(MODULE.ResolutionError):
                    MODULE.load_final_feedback_boundary(
                        repository="SecPal/api",
                        number=123,
                        expected_head=attestation["head_sha"],
                        final_reviewed_state_path=root / "reviewed.json",
                        expected_final_reviewed_state_digest=reviewed["state_digest"],
                        final_validation_evidence_path=root / "validation.json",
                        final_eligibility_evidence_path=root / "eligibility.json",
                    )

    def test_cycle2_reviewed_loader_retains_and_validates_complete_membership(
        self,
    ) -> None:
        reviewed = reviewed_state_payload("PRRT_FIRST", [])
        reviewed["threads"].append(
            {
                "node_id": "PRRT_SECOND",
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "node_id": "PRRC_SECOND_REPLY",
                        "body_digest": "c" * 64,
                        "actor": {
                            "login": "reviewer",
                            "node_id": "USER_reviewer",
                            "database_id": 7,
                        },
                        "reply_to_id": "PRRC_MISSING_ROOT",
                        "reactions": [],
                    }
                ],
            }
        )
        feedback = {
            key: reviewed[key]
            for key in (
                "pull_request_reactions",
                "reviews",
                "conversation_comments",
                "threads",
            )
        }
        reviewed["feedback_digest"] = MODULE._digest_json(feedback)
        reviewed["state_digest"] = MODULE._digest_json(
            {
                "repository": reviewed["repository"],
                "pull_request_number": reviewed["pull_request_number"],
                "head_sha": reviewed["head_sha"],
                "base_ref": reviewed["base_ref"],
                "base_sha": reviewed["base_sha"],
                "pr_state": reviewed["pr_state"],
                "feedback": feedback,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(reviewed), encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "reviewed target comment state is malformed",
            ):
                MODULE.load_reviewed_state(
                    path,
                    "SecPal/api",
                    123,
                    reviewed["state_digest"],
                    (),
                )

    def test_cycle2_final_boundary_rejects_duplicate_eligibility_json_keys(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed, attestation, eligibility, _git = (
                write_authenticated_resolution_inputs(
                    directory,
                    ["PRRT_FINAL_KNOWN"],
                    eligibility_thread_ids=(),
                )
            )
            canonical = MODULE._canonical_json_bytes(eligibility).decode("utf-8")
            duplicate = canonical.replace(
                '"schema_version":"1.1"',
                '"schema_version":"1.1","schema_version":"1.1"',
                1,
            )
            (root / "eligibility.json").write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "eligibility evidence is unavailable or malformed",
            ):
                MODULE.load_final_feedback_boundary(
                    repository="SecPal/api",
                    number=123,
                    expected_head=attestation["head_sha"],
                    final_reviewed_state_path=root / "reviewed.json",
                    expected_final_reviewed_state_digest=reviewed["state_digest"],
                    final_validation_evidence_path=root / "validation.json",
                    final_eligibility_evidence_path=root / "eligibility.json",
                )

    def test_cycle2_genuine_late_origin_reaches_guarded_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, github, _git = run_late_resolution_fixture(
                directory,
                apply=False,
                final_reviewed_thread_id="PRRT_FINAL_KNOWN",
                final_eligibility_thread_ids=(),
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["pending"], ["PRRT_LATE_NON_BLOCKING"])
        self.assertEqual(len(github.calls), 1)

    def test_post_freeze_informational_resolution_accepts_both_derived_origins(
        self,
    ) -> None:
        cases = (
            ("PRRT_LATE_NON_BLOCKING", "REVIEWED_BUT_INELIGIBLE"),
            ("PRRT_FINAL_KNOWN", "ABSENT_FROM_BOTH"),
        )
        for reviewed_thread, expected_origin in cases:
            with (
                self.subTest(origin=expected_origin),
                tempfile.TemporaryDirectory() as directory,
            ):
                result, github, _git = run_late_resolution_fixture(
                    directory,
                    apply=False,
                    final_reviewed_thread_id=reviewed_thread,
                    final_eligibility_thread_ids=(),
                    classification="INFORMATIONAL",
                    disposition="NON_ACTIONABLE",
                )
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["origin"], expected_origin)
            self.assertEqual(len(github.calls), 1)

    def test_post_freeze_v1_disposition_cannot_gain_informational_meaning(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "late-disposition thread is ineligible",
            ),
        ):
            run_late_resolution_fixture(
                directory,
                apply=False,
                classification="INFORMATIONAL",
                disposition="NON_ACTIONABLE",
                artifact_mutator=lambda value: value.update(
                    {"schema_version": "1.0"}
                ),
            )

    def test_post_push_late_feedback_deadlock_requires_detached_authority(
        self,
    ) -> None:
        final_thread = "PRRT_FINAL_KNOWN"
        late_thread = "PRRT_LATE_NON_BLOCKING"
        with tempfile.TemporaryDirectory() as directory:
            reviewed, attestation, _eligibility, git = (
                write_authenticated_resolution_inputs(directory, [final_thread])
            )
            root = Path(directory)
            late_manifest = eligibility_payload(reviewed, [late_thread])
            late_manifest_path = root / "late-eligibility.json"
            late_manifest_path.write_text(
                json.dumps(late_manifest), encoding="utf-8"
            )

            with (
                mock.patch.object(MODULE, "_run_git", git),
                mock.patch.object(
                    MODULE,
                    "_run_gh",
                    side_effect=AssertionError(
                        "commit-bound rejection must precede GitHub access"
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    f"target thread is absent from reviewed feedback: {late_thread}",
                ):
                    MODULE.resolve_threads(
                        reviewed["repository"],
                        reviewed["pull_request_number"],
                        attestation["head_sha"],
                        (late_thread,),
                        apply=True,
                        repository_root=root,
                        reviewed_state_path=root / "reviewed.json",
                        expected_reviewed_state_digest=reviewed["state_digest"],
                        validation_evidence_path=root / "validation.json",
                        eligibility_evidence_path=late_manifest_path,
                    )

        self.assertTrue(
            hasattr(MODULE, "resolve_late_disposition_threads"),
            "#724 needs a detached authenticated path without a delivery commit",
        )

    def test_authenticated_post_push_late_feedback_resolves_without_tree_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, github, git = run_late_resolution_fixture(directory)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resolved"], ["PRRT_LATE_NON_BLOCKING"])
        self.assertEqual(
            result["eligibility_path"], "authenticated_late_disposition"
        )
        self.assertEqual(
            result["lifecycle_consumption"],
            {
                "unrestricted_reviews": 0,
                "remediation_cycles": 0,
                "delivery_commits": 0,
                "pushes": 0,
                "ready_transitions": 0,
            },
        )
        self.assertEqual(
            sum(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in github.calls
            ),
            1,
        )
        self.assertFalse(
            any(call and call[0] in {"commit", "push"} for call in git.calls)
        )

    def test_creator_authenticates_fresh_exact_late_thread_without_commit(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as key_directory,
            tempfile.TemporaryDirectory() as output_directory,
        ):
            root = Path(directory)
            reviewed, attestation, _eligibility, git = (
                write_authenticated_resolution_inputs(
                    directory,
                    ["PRRT_LATE_NON_BLOCKING"],
                    eligibility_thread_ids=(),
                )
            )
            signing_key = Path(key_directory) / "signing-key"
            signing_key.write_text("fixture", encoding="utf-8")
            git.signing_key = str(signing_key)
            classification_path = Path(output_directory) / "classification.json"
            classification_signature_path = (
                Path(output_directory) / "classification.sig"
            )
            artifact_path = Path(output_directory) / "late.json"
            signature_path = Path(output_directory) / "late.sig"
            response = target_response(
                "PRRT_LATE_NON_BLOCKING",
                head=attestation["head_sha"],
                comments=[
                    (
                        "PRRC_LATE_FINDING",
                        "The reported recovery behavior is not present.",
                        None,
                    )
                ],
            )
            github = FakeGh([response, response, response, response])
            finding_digest = hashlib.sha256(
                b"The reported recovery behavior is not present."
            ).hexdigest()
            classification_authorization = (
                MODULE.late_disposition.ClassificationEvidence(
                    evidence_digest="d" * 64,
                    canonical_payload=b"{}\n",
                    repository="SecPal/api",
                    delivery_issue_number=724,
                    pull_request_number=123,
                    head_sha=attestation["head_sha"],
                    signer=MODULE.late_disposition.SignerIdentity(
                        "ssh", "SHA256:fixtureDeliverySigner"
                    ),
                    finding_id="LF-LATE-1",
                    finding_evidence_digest="c" * 64,
                    thread=MODULE.late_disposition.ThreadAuthorization(
                        thread_id="PRRT_LATE_NON_BLOCKING",
                        top_level_comment_node_id="PRRC_LATE_FINDING",
                        top_level_comment_database_id=1001,
                        finding_body_digest=finding_digest,
                        reply_state_digest=MODULE._digest_json([]),
                        reply_count=0,
                        is_resolved=False,
                        is_outdated=False,
                        classification="INFORMATIONAL",
                        disposition="NON_ACTIONABLE",
                        technically_blocking=False,
                        classification_evidence_digest="d" * 64,
                    ),
                    technical_blockers=(),
                )
            )

            def sign(
                artifact: dict[str, Any],
                artifact_output: Path,
                signature_output: Path,
                **_kwargs: Any,
            ) -> None:
                artifact_output.write_bytes(
                    MODULE.late_disposition.canonical_json_bytes(artifact)
                )
                signature_output.write_text("signed", encoding="utf-8")

            with (
                mock.patch.object(MODULE, "_run_git", git),
                mock.patch.object(MODULE, "_run_gh", github),
                mock.patch.object(
                    MODULE.late_disposition, "sign_artifact", side_effect=sign
                ),
                mock.patch.object(
                    MODULE.late_disposition,
                    "read_signing_configuration",
                    return_value=("ssh", str(signing_key)),
                ),
                mock.patch.object(
                    MODULE.late_disposition,
                    "parse_classification_artifact",
                    return_value=classification_authorization,
                ),
                mock.patch.object(
                    MODULE.late_disposition,
                    "os_account_home",
                    return_value=Path(key_directory),
                ),
            ):
                classification_result = (
                    MODULE.create_late_classification_artifact(
                        "SecPal/api",
                        724,
                        123,
                        attestation["head_sha"],
                        repository_root=root,
                        final_reviewed_state_path=root / "reviewed.json",
                        expected_final_reviewed_state_digest=(
                            reviewed["state_digest"]
                        ),
                        final_validation_evidence_path=root / "validation.json",
                        final_eligibility_evidence_path=root / "eligibility.json",
                        thread_id="PRRT_LATE_NON_BLOCKING",
                        finding_id="LF-LATE-1",
                        finding_evidence_digest="c" * 64,
                        classification="INFORMATIONAL",
                        disposition="NON_ACTIONABLE",
                        technically_blocking=False,
                        technical_blockers=(),
                        output_path=classification_path,
                        signature_output_path=classification_signature_path,
                    )
                )
                result = MODULE.create_late_disposition_artifact(
                    "SecPal/api",
                    724,
                    123,
                    attestation["head_sha"],
                    repository_root=root,
                    final_reviewed_state_path=root / "reviewed.json",
                    expected_final_reviewed_state_digest=reviewed["state_digest"],
                    final_validation_evidence_path=root / "validation.json",
                    final_eligibility_evidence_path=root / "eligibility.json",
                    classification_evidence_path=classification_path,
                    classification_signature_path=classification_signature_path,
                    output_path=artifact_path,
                    signature_output_path=signature_path,
                )

            classification_artifact = json.loads(
                classification_path.read_text(encoding="utf-8")
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(
                classification_result["status"],
                "LATE_CLASSIFICATION_AUTHENTICATED",
            )
            self.assertEqual(
                classification_result["origin"],
                "REVIEWED_BUT_INELIGIBLE",
            )
            self.assertEqual(
                result["origin"],
                "REVIEWED_BUT_INELIGIBLE",
            )
            self.assertEqual(
                classification_artifact["thread"]["technical_blockers"], []
            )
            self.assertEqual(result["status"], "LATE_DISPOSITION_AUTHENTICATED")
            self.assertFalse(result["delivery_tree_changed"])
            self.assertEqual(
                artifact["validation_attestation_digest"],
                attestation["attestation_digest"],
            )
            self.assertEqual(
                artifact["threads"][0]["top_level_comment_database_id"], 1001
            )
            self.assertEqual(
                artifact["threads"][0]["classification_evidence_digest"],
                classification_authorization.evidence_digest,
            )
            self.assertFalse(
                any(call and call[0] in {"commit", "push"} for call in git.calls)
            )

    def test_late_disposition_live_state_drift_blocks_before_mutation(self) -> None:
        cases = {
            "changed head": {
                "live_head": "e" * 40,
                "error": "pull request head changed",
            },
            "changed top-level comment": {
                "live_comments": [
                    ("PRRC_LATE_FINDING", "changed finding text", None)
                ],
                "error": "differs from authenticated late disposition",
            },
            "new material reply": {
                "live_comments": [
                    (
                        "PRRC_LATE_FINDING",
                        "The reported recovery behavior is not present.",
                        None,
                    ),
                    (
                        "PRRC_NEW_REPLY",
                        "new material evidence",
                        "PRRC_LATE_FINDING",
                    ),
                ],
                "error": "differs from authenticated late disposition",
            },
            "removed reply": {
                "artifact_mutator": lambda value: value["threads"][0].update(
                    {
                        "reply_state_digest": MODULE._digest_json(
                            [
                                {
                                    "node_id": "PRRC_REMOVED_REPLY",
                                    "database_id": 1002,
                                    "body_digest": MODULE._body_digest(
                                        "previous material reply"
                                    ),
                                    "reply_to_id": "PRRC_LATE_FINDING",
                                }
                            ]
                        ),
                        "reply_count": 1,
                    }
                ),
                "error": "does not match authenticated classification evidence",
            },
            "different top-level identity": {
                "live_comments": [
                    (
                        "PRRC_SUBSTITUTED",
                        "The reported recovery behavior is not present.",
                        None,
                    )
                ],
                "error": "differs from authenticated late disposition",
            },
            "different top-level database identity": {
                "artifact_mutator": lambda value: value["threads"][0].update(
                    {"top_level_comment_database_id": 9999}
                ),
                "error": "does not match authenticated classification evidence",
            },
            "incompatible outdated state": {
                "live_outdated": True,
                "error": "differs from authenticated late disposition",
            },
            "changed resolved state": {
                "live_resolved": True,
                "error": "differs from authenticated late disposition",
            },
            "different thread": {
                "live_thread_id": "PRRT_SUBSTITUTED",
                "error": "pull request identity is incomplete",
            },
        }
        for label, case in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(MODULE.ResolutionError, case["error"]):
                    run_late_resolution_fixture(
                        directory,
                        artifact_mutator=case.get("artifact_mutator"),
                        live_head=case.get("live_head"),
                        live_outdated=case.get("live_outdated", False),
                        live_resolved=case.get("live_resolved", False),
                        live_comments=case.get("live_comments"),
                        live_thread_id=case.get(
                            "live_thread_id", "PRRT_LATE_NON_BLOCKING"
                        ),
                    )

    def test_late_disposition_binding_and_policy_drift_blocks_before_github(
        self,
    ) -> None:
        mutations = {
            "repository replay": lambda value: value.update(
                {"repository": "SecPal/other"}
            ),
            "PR replay": lambda value: value.update(
                {"pull_request_number": 124}
            ),
            "issue replay": lambda value: value.update(
                {"delivery_issue_number": 725}
            ),
            "head replay": lambda value: value.update({"head_sha": "e" * 40}),
            "receipt substituted": lambda value: value.update(
                {"validation_receipt_digest": "e" * 64}
            ),
            "attestation substituted": lambda value: value.update(
                {"validation_attestation_digest": "e" * 64}
            ),
            "validated tree substituted": lambda value: value.update(
                {"validated_tree_sha": "e" * 40}
            ),
            "final eligibility substituted": lambda value: value.update(
                {"final_eligibility_evidence_digest": "e" * 64}
            ),
            "artifact claims another trust anchor": lambda value: value[
                "delivery_signer"
            ].update({"fingerprint": "SHA256:attackerChosen"}),
            "classification changed": lambda value: value["threads"][0].update(
                {"classification": "INFORMATIONAL"}
            ),
            "disposition changed": lambda value: value["threads"][0].update(
                {"disposition": "NON_ACTIONABLE"}
            ),
            "technically blocking": lambda value: value["threads"][0].update(
                {"technically_blocking": True}
            ),
            "classification evidence substituted": lambda value: value[
                "threads"
            ][0].update({"classification_evidence_digest": "e" * 64}),
            "action substituted": lambda value: value["threads"][0].update(
                {"authorized_action": "RESOLVE_ANY_THREAD"}
            ),
            "unsupported field": lambda value: value.update({"query": "*"}),
            "unsupported version": lambda value: value.update(
                {"schema_version": "2.0"}
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(MODULE.ResolutionError):
                    run_late_resolution_fixture(
                        directory,
                        artifact_mutator=mutation,
                    )

    def test_post_freeze_runtime_payloads_match_canonical_schemas(self) -> None:
        reviewed = reviewed_state_payload("PRRT_FINAL_KNOWN", [])
        attestation = validation_attestation_payload(reviewed)
        decisions = (
            ("INVALID_FALSE_OR_MISLEADING", "DISPROVEN_WITH_EVIDENCE"),
            ("INFORMATIONAL", "NON_ACTIONABLE"),
        )
        for classification, disposition in decisions:
            late_payload = late_disposition_payload(
                attestation,
                classification=classification,
                disposition=disposition,
            )
            classification_thread = {
                key: value
                for key, value in late_payload["threads"][0].items()
                if key
                not in {"classification_evidence_digest", "authorized_action"}
            }
            classification_thread["technical_blockers"] = []
            classification_payload = {
                "schema_version": late_payload["schema_version"],
                "kind": "LATE_FEEDBACK_CLASSIFICATION",
                "repository": "SecPal/api",
                "delivery_issue_number": 724,
                "pull_request_number": 123,
                "head_sha": attestation["head_sha"],
                "delivery_signer": {
                    "format": "ssh",
                    "fingerprint": "SHA256:fixtureDeliverySigner",
                },
                "authorized_purpose": "AUTHORIZE_LATE_FEEDBACK_DISPOSITION",
                "finding_id": "LF-LATE-SCHEMA",
                "finding_evidence_digest": "c" * 64,
                "thread": classification_thread,
            }
            with self.subTest(
                classification=classification,
                disposition=disposition,
            ):
                MODULE.evidence.validate_against_authoritative_schema(
                    classification_payload,
                    ROOT
                    / ".agents/skills/secpal-pr-review/references/late-classification.schema.json",
                    "late classification evidence",
                )
                MODULE.evidence.validate_against_authoritative_schema(
                    late_payload,
                    ROOT
                    / ".agents/skills/secpal-pr-review/references/late-disposition.schema.json",
                    "late-disposition evidence",
                )

    def test_late_disposition_alternate_valid_signer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "signer does not match final delivery signer",
            ):
                run_late_resolution_fixture(
                    directory,
                    signature_error=MODULE.late_disposition.LateDispositionError(
                        "late-disposition signer does not match final delivery signer"
                    ),
                )

    def test_late_disposition_rejects_multi_thread_authority(self) -> None:
        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "exactly one review thread",
        ):
            MODULE.resolve_late_disposition_threads(
                "SecPal/api",
                724,
                123,
                "a" * 40,
                ("PRRT_FIRST", "PRRT_SECOND"),
                apply=True,
                repository_root="unread",
                final_reviewed_state_path="unread",
                expected_final_reviewed_state_digest="b" * 64,
                final_validation_evidence_path="unread",
                final_eligibility_evidence_path="unread",
                late_classification_evidence_path="unread",
                late_classification_signature_path="unread",
                late_disposition_evidence_path="unread",
                late_disposition_signature_path="unread",
            )

    def test_detached_ssh_signature_is_hermetic_and_signer_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".config").mkdir()
            (root / ".gnupg").mkdir(mode=0o700)
            environment = MODULE.late_disposition.signing_environment(
                account_home=root
            )
            first_key = root / "first"
            second_key = root / "second"
            for key in (first_key, second_key):
                subprocess.run(
                    [
                        "/usr/bin/ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        str(key),
                    ],
                    check=True,
                    env=environment,
                    capture_output=True,
                )

            def fingerprint(key: Path) -> str:
                result = subprocess.run(
                    ["/usr/bin/ssh-keygen", "-lf", f"{key}.pub", "-E", "sha256"],
                    check=True,
                    env=environment,
                    capture_output=True,
                    text=True,
                )
                return result.stdout.split()[1]

            first_signer = MODULE.late_disposition.SignerIdentity(
                "ssh", fingerprint(first_key)
            )
            second_signer = MODULE.late_disposition.SignerIdentity(
                "ssh", fingerprint(second_key)
            )
            artifact = root / "artifact.json"
            signature = root / "artifact.sig"
            MODULE.late_disposition.sign_artifact(
                {"schema_version": "fixture", "value": 1},
                artifact,
                signature,
                signer=first_signer,
                signing_key=str(first_key),
                environment=environment,
            )
            MODULE.late_disposition.verify_detached_signature(
                artifact, signature, first_signer, environment=environment
            )
            original_artifact = artifact.read_bytes()
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "does not match final delivery signer",
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact, signature, second_signer, environment=environment
                )
            artifact.write_bytes(
                MODULE.late_disposition.canonical_json_bytes(
                    {"schema_version": "fixture", "value": 2}
                )
            )
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "SSH signature is invalid",
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact, signature, first_signer, environment=environment
                )
            artifact.write_bytes(original_artifact)
            signature.write_bytes(b"corrupted signature")
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "SSH signature is invalid",
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact, signature, first_signer, environment=environment
                )

    def test_detached_openpgp_signature_is_hermetic_and_signer_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".config").mkdir()
            gnupg = root / ".gnupg"
            gnupg.mkdir(mode=0o700)
            environment = MODULE.late_disposition.signing_environment(
                account_home=root
            )
            subprocess.run(
                [
                    "/usr/bin/gpg",
                    "--batch",
                    "--no-tty",
                    "--passphrase",
                    "",
                    "--quick-generate-key",
                    "SecPal Fixture <fixture@example.invalid>",
                    "ed25519",
                    "sign",
                    "0",
                ],
                check=True,
                env=environment,
                capture_output=True,
            )
            keys = subprocess.run(
                ["/usr/bin/gpg", "--batch", "--with-colons", "--list-secret-keys"],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            ).stdout
            fingerprint = next(
                line.split(":")[9]
                for line in keys.splitlines()
                if line.startswith("fpr:")
            )
            signer = MODULE.late_disposition.SignerIdentity(
                "openpgp", fingerprint
            )
            artifact = root / "artifact.json"
            signature = root / "artifact.asc"
            MODULE.late_disposition.sign_artifact(
                {"schema_version": "fixture", "value": 1},
                artifact,
                signature,
                signer=signer,
                signing_key=fingerprint,
                environment=environment,
            )
            MODULE.late_disposition.verify_detached_signature(
                artifact, signature, signer, environment=environment
            )
            alternate = MODULE.late_disposition.SignerIdentity(
                "openpgp", "A" * len(fingerprint)
            )
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "does not match final delivery signer",
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact, signature, alternate, environment=environment
                )

    def test_detached_artifact_rejects_missing_signature_and_duplicate_keys(
        self,
    ) -> None:
        signer = MODULE.late_disposition.SignerIdentity(
            "ssh", "SHA256:fixtureDeliverySigner"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.json"
            artifact.write_bytes(b'{"schema_version":"1.0","schema_version":"1.0"}\n')
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "malformed",
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact, root / "missing.sig", signer
                )
            artifact.write_bytes(
                MODULE.late_disposition.canonical_json_bytes(
                    {"schema_version": "1.0"}
                )
            )
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "signature is unavailable",
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact, root / "missing.sig", signer
                )

    def test_detached_signing_environment_ignores_repository_overrides(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.dict(
                os.environ,
                {
                    "HOME": "/repository/controlled",
                    "XDG_CONFIG_HOME": "/repository/controlled/xdg",
                    "GNUPGHOME": "/repository/controlled/gnupg",
                    "GIT_CONFIG_GLOBAL": "/repository/controlled/gitconfig",
                    "GIT_CONFIG_KEY_0": "gpg.program",
                    "LD_PRELOAD": "/repository/controlled/library",
                    "SSH_AUTH_SOCK": "/repository/controlled/agent",
                    "PATH": "/repository/controlled/bin",
                },
                clear=False,
            ):
                environment = MODULE.late_disposition.signing_environment(
                    account_home=root
                )

        self.assertEqual(environment["HOME"], str(root))
        self.assertEqual(environment["XDG_CONFIG_HOME"], str(root / ".config"))
        self.assertEqual(environment["GNUPGHOME"], str(root / ".gnupg"))
        self.assertEqual(
            environment["PATH"], MODULE.late_disposition.TRUSTED_COMMAND_PATH
        )
        for key in (
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_KEY_0",
            "LD_PRELOAD",
            "SSH_AUTH_SOCK",
        ):
            self.assertNotIn(key, environment)

    def test_detached_verification_rejects_evidence_toctou(self) -> None:
        signer = MODULE.late_disposition.SignerIdentity(
            "ssh", "SHA256:fixtureDeliverySigner"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.json"
            signature = root / "artifact.sig"
            artifact.write_bytes(
                MODULE.late_disposition.canonical_json_bytes({"value": 1})
            )
            signature.write_text("signature", encoding="utf-8")

            def mutate(*_args: Any, **_kwargs: Any) -> Any:
                artifact.write_bytes(
                    MODULE.late_disposition.canonical_json_bytes({"value": 2})
                )
                return subprocess.CompletedProcess(
                    (),
                    0,
                    b'Good "fixture" signature with ED25519 key '
                    b"SHA256:fixtureDeliverySigner\n",
                    b"",
                )

            with (
                mock.patch.object(
                    MODULE.late_disposition,
                    "_trusted_executable",
                    return_value="/usr/bin/ssh-keygen",
                ),
                mock.patch.object(
                    MODULE.late_disposition,
                    "_run_signature_command",
                    side_effect=mutate,
                ),
            ):
                verified = MODULE.late_disposition.verify_detached_signature(
                    artifact,
                    signature,
                    signer,
                    environment={"PATH": "/usr/bin"},
                )
            self.assertEqual(
                verified,
                MODULE.late_disposition.canonical_json_bytes({"value": 1}),
            )

    def test_cycle1_r1_unsigned_classification_assertions_have_no_authority(
        self,
    ) -> None:
        payload = {
            "schema_version": "1.0",
            "threads": [
                {
                    "thread_id": "PRRT_arbitraryCallerDecision",
                    "classification": "INVALID_FALSE_OR_MISLEADING",
                    "disposition": "DISPROVEN_WITH_EVIDENCE",
                    "technically_blocking": False,
                    "classification_evidence_digest": "0" * 64,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "classification.json"
            path.write_bytes(MODULE._canonical_json_bytes(payload))
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "signature is unavailable",
            ):
                MODULE.late_disposition.parse_classification_artifact(
                    path,
                    Path(directory) / "missing.sig",
                    expected_signer=MODULE.late_disposition.SignerIdentity(
                        "ssh", "SHA256:fixtureDeliverySigner"
                    ),
                    repository="SecPal/api",
                    delivery_issue_number=724,
                    pull_request_number=123,
                    head_sha="a" * 40,
                    thread_id="PRRT_arbitraryCallerDecision",
                )

    def test_cycle1_r1_authenticated_classification_is_exact_and_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".config").mkdir()
            (root / ".gnupg").mkdir(mode=0o700)
            environment = MODULE.late_disposition.signing_environment(
                account_home=root
            )
            key = root / "classification-key"
            alternate_key = root / "alternate-key"
            for key_path in (key, alternate_key):
                subprocess.run(
                    [
                        "/usr/bin/ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        str(key_path),
                    ],
                    check=True,
                    env=environment,
                    capture_output=True,
                )

            def fingerprint(key_path: Path) -> str:
                return subprocess.run(
                    [
                        "/usr/bin/ssh-keygen",
                        "-lf",
                        f"{key_path}.pub",
                        "-E",
                        "sha256",
                    ],
                    check=True,
                    env=environment,
                    capture_output=True,
                    text=True,
                ).stdout.split()[1]

            signer = MODULE.late_disposition.SignerIdentity(
                "ssh", fingerprint(key)
            )
            alternate = MODULE.late_disposition.SignerIdentity(
                "ssh", fingerprint(alternate_key)
            )
            artifact = root / "classification.json"
            signature = root / "classification.sig"
            body_digest = hashlib.sha256(b"exact finding").hexdigest()
            reply_digest = MODULE._digest_json([])
            payload = {
                "schema_version": "1.0",
                "kind": "LATE_FEEDBACK_CLASSIFICATION",
                "repository": "SecPal/api",
                "delivery_issue_number": 724,
                "pull_request_number": 123,
                "head_sha": "a" * 40,
                "delivery_signer": {
                    "format": "ssh",
                    "fingerprint": signer.fingerprint,
                },
                "authorized_purpose": "AUTHORIZE_LATE_FEEDBACK_DISPOSITION",
                "finding_id": "LF-LATE-1",
                "finding_evidence_digest": "c" * 64,
                "thread": {
                    "thread_id": "PRRT_exactLateFinding",
                    "top_level_comment_node_id": "PRRC_exactRoot",
                    "top_level_comment_database_id": 1001,
                    "finding_body_digest": body_digest,
                    "reply_state_digest": reply_digest,
                    "reply_count": 0,
                    "is_resolved": False,
                    "is_outdated": False,
                    "classification": "INVALID_FALSE_OR_MISLEADING",
                    "disposition": "DISPROVEN_WITH_EVIDENCE",
                    "technically_blocking": False,
                    "technical_blockers": [],
                },
            }
            MODULE.evidence.validate_against_authoritative_schema(
                payload,
                ROOT
                / ".agents/skills/secpal-pr-review/references/late-classification.schema.json",
                "late classification evidence",
            )

            def sign(value: dict[str, Any], key_path: Path, identity: Any) -> None:
                MODULE.late_disposition.sign_artifact(
                    value,
                    artifact,
                    signature,
                    signer=identity,
                    signing_key=str(key_path),
                    environment=environment,
                    signature_namespace=(
                        MODULE.late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE
                    ),
                )

            def parse() -> Any:
                return MODULE.late_disposition.parse_classification_artifact(
                    artifact,
                    signature,
                    expected_signer=signer,
                    repository="SecPal/api",
                    delivery_issue_number=724,
                    pull_request_number=123,
                    head_sha="a" * 40,
                    thread_id="PRRT_exactLateFinding",
                    signature_environment=environment,
                )

            sign(payload, key, signer)
            evidence = parse()
            self.assertEqual(
                evidence.evidence_digest,
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
            informational_payload = copy.deepcopy(payload)
            informational_payload["thread"]["classification"] = "INFORMATIONAL"
            informational_payload["thread"]["disposition"] = "NON_ACTIONABLE"
            sign(informational_payload, key, signer)
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "not resolution-eligible",
            ):
                parse()
            informational_payload["schema_version"] = "1.1"
            sign(informational_payload, key, signer)
            informational_evidence = parse()
            self.assertEqual(
                informational_evidence.thread.classification,
                "INFORMATIONAL",
            )
            self.assertEqual(
                informational_evidence.thread.disposition,
                "NON_ACTIONABLE",
            )

            exact_live = MODULE.ThreadState(
                thread_id="PRRT_exactLateFinding",
                is_resolved=False,
                is_outdated=False,
                comments=(
                    MODULE.ThreadCommentState(
                        comment_id="PRRC_exactRoot",
                        database_id=1001,
                        body_digest=body_digest,
                        reply_to_id=None,
                    ),
                ),
            )
            self.assertTrue(
                MODULE._matches_late_authorization(exact_live, evidence.thread)
            )

            substitutions = (
                ("repository", "Other/repository"),
                ("delivery_issue_number", 725),
                ("pull_request_number", 124),
                ("head_sha", "b" * 40),
            )
            for field, value in substitutions:
                changed = copy.deepcopy(payload)
                changed[field] = value
                sign(changed, key, signer)
                with self.subTest(field=field), self.assertRaises(
                    MODULE.late_disposition.LateDispositionError
                ):
                    parse()
            for field, value in (
                ("thread_id", "PRRT_otherLateFinding"),
                ("classification", "VALID_ACTIONABLE"),
                ("disposition", "CORRECTED_AND_VERIFIED"),
            ):
                changed = copy.deepcopy(payload)
                changed["thread"][field] = value
                sign(changed, key, signer)
                with self.subTest(thread_field=field), self.assertRaises(
                    MODULE.late_disposition.LateDispositionError
                ):
                    parse()
            for blocker in (
                "P1",
                "P2",
                "SECURITY",
                "AUTHENTICATION",
                "INTEGRITY",
                "FAIL_OPEN",
            ):
                changed = copy.deepcopy(payload)
                changed["thread"]["technically_blocking"] = True
                changed["thread"]["technical_blockers"] = [blocker]
                sign(changed, key, signer)
                with self.subTest(blocker=blocker), self.assertRaisesRegex(
                    MODULE.late_disposition.LateDispositionError,
                    "not resolution-eligible",
                ):
                    parse()

            changed = copy.deepcopy(payload)
            changed["thread"]["top_level_comment_node_id"] = "PRRC_otherRoot"
            sign(changed, key, signer)
            root_substitution = parse()
            self.assertFalse(
                MODULE._matches_late_authorization(
                    exact_live, root_substitution.thread
                )
            )
            changed = copy.deepcopy(payload)
            changed["thread"]["top_level_comment_database_id"] = 1002
            sign(changed, key, signer)
            database_substitution = parse()
            self.assertFalse(
                MODULE._matches_late_authorization(
                    exact_live, database_substitution.thread
                )
            )
            changed = copy.deepcopy(payload)
            changed["thread"]["finding_body_digest"] = "f" * 64
            changed["thread"]["reply_state_digest"] = "e" * 64
            sign(changed, key, signer)
            state_substitution = parse()
            self.assertFalse(
                MODULE._matches_late_authorization(
                    exact_live, state_substitution.thread
                )
            )

            alternate_payload = copy.deepcopy(payload)
            alternate_payload["delivery_signer"]["fingerprint"] = (
                alternate.fingerprint
            )
            sign(alternate_payload, alternate_key, alternate)
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "signer does not match final delivery signer",
            ):
                parse()

    def test_cycle1_r2_openpgp_verifies_captured_bytes_not_mutable_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".config").mkdir()
            (root / ".gnupg").mkdir(mode=0o700)
            environment = MODULE.late_disposition.signing_environment(
                account_home=root
            )
            subprocess.run(
                [
                    "/usr/bin/gpg",
                    "--batch",
                    "--no-tty",
                    "--passphrase",
                    "",
                    "--quick-generate-key",
                    "SecPal Cycle 1 <cycle1@example.invalid>",
                    "ed25519",
                    "sign",
                    "0",
                ],
                check=True,
                env=environment,
                capture_output=True,
            )
            keys = subprocess.run(
                ["/usr/bin/gpg", "--batch", "--with-colons", "--list-secret-keys"],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            ).stdout
            fingerprint = next(
                line.split(":")[9]
                for line in keys.splitlines()
                if line.startswith("fpr:")
            )
            signer = MODULE.late_disposition.SignerIdentity(
                "openpgp", fingerprint
            )
            artifact = root / "artifact.json"
            signature = root / "artifact.asc"
            MODULE.late_disposition.sign_artifact(
                {"schema_version": "fixture", "value": "signed-B"},
                artifact,
                signature,
                signer=signer,
                signing_key=fingerprint,
                environment=environment,
            )
            signed_b = artifact.read_bytes()
            unsigned_a = MODULE.late_disposition.canonical_json_bytes(
                {"schema_version": "fixture", "value": "unsigned-A"}
            )
            artifact.write_bytes(unsigned_a)
            original_run = MODULE.late_disposition._run_signature_command

            def race_artifact(
                executable: str,
                arguments: Sequence[str],
                *,
                environment: dict[str, str],
                stdin: bytes | None = None,
            ) -> Any:
                if "--verify" in arguments:
                    artifact.write_bytes(signed_b)
                    try:
                        return original_run(
                            executable,
                            arguments,
                            environment=environment,
                            stdin=stdin,
                        )
                    finally:
                        artifact.write_bytes(unsigned_a)
                return original_run(
                    executable,
                    arguments,
                    environment=environment,
                    stdin=stdin,
                )

            with (
                mock.patch.object(
                    MODULE.late_disposition,
                    "_run_signature_command",
                    side_effect=race_artifact,
                ),
                self.assertRaisesRegex(
                    MODULE.late_disposition.LateDispositionError,
                    "OpenPGP signature is invalid",
                ),
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact,
                    signature,
                    signer,
                    environment=environment,
                )
            classification_payload = {
                "kind": "LATE_FEEDBACK_CLASSIFICATION",
                "value": "openpgp",
            }
            MODULE.late_disposition.sign_artifact(
                classification_payload,
                artifact,
                signature,
                signer=signer,
                signing_key=fingerprint,
                environment=environment,
                signature_namespace=(
                    MODULE.late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE
                ),
            )
            self.assertEqual(
                MODULE.late_disposition.verify_detached_signature(
                    artifact,
                    signature,
                    signer,
                    environment=environment,
                    signature_namespace=(
                        MODULE.late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE
                    ),
                ),
                MODULE.late_disposition.canonical_json_bytes(
                    classification_payload
                ),
            )

    def test_cycle1_r2_ssh_verifies_captured_signature_not_mutable_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".config").mkdir()
            (root / ".gnupg").mkdir(mode=0o700)
            environment = MODULE.late_disposition.signing_environment(
                account_home=root
            )
            key = root / "key"
            subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ],
                check=True,
                env=environment,
                capture_output=True,
            )
            fingerprint = subprocess.run(
                ["/usr/bin/ssh-keygen", "-lf", f"{key}.pub", "-E", "sha256"],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            ).stdout.split()[1]
            signer = MODULE.late_disposition.SignerIdentity("ssh", fingerprint)
            artifact_a = root / "a.json"
            signature_a = root / "a.sig"
            artifact_b = root / "b.json"
            signature_b = root / "b.sig"
            MODULE.late_disposition.sign_artifact(
                {"value": "A"},
                artifact_a,
                signature_a,
                signer=signer,
                signing_key=str(key),
                environment=environment,
            )
            MODULE.late_disposition.sign_artifact(
                {"value": "B"},
                artifact_b,
                signature_b,
                signer=signer,
                signing_key=str(key),
                environment=environment,
            )
            valid_for_a = signature_a.read_bytes()
            restored_signature = signature_b.read_bytes()
            signature_a.write_bytes(restored_signature)
            original_run = MODULE.late_disposition._run_signature_command

            def race_signature(
                executable: str,
                arguments: Sequence[str],
                *,
                environment: dict[str, str],
                stdin: bytes | None = None,
            ) -> Any:
                if "check-novalidate" in arguments:
                    signature_a.write_bytes(valid_for_a)
                    try:
                        return original_run(
                            executable,
                            arguments,
                            environment=environment,
                            stdin=stdin,
                        )
                    finally:
                        signature_a.write_bytes(restored_signature)
                return original_run(
                    executable,
                    arguments,
                    environment=environment,
                    stdin=stdin,
                )

            with (
                mock.patch.object(
                    MODULE.late_disposition,
                    "_run_signature_command",
                    side_effect=race_signature,
                ),
                self.assertRaisesRegex(
                    MODULE.late_disposition.LateDispositionError,
                    "SSH signature is invalid",
                ),
            ):
                MODULE.late_disposition.verify_detached_signature(
                    artifact_a,
                    signature_a,
                    signer,
                    environment=environment,
                )

    def test_cycle1_r2_verification_uses_only_initial_regular_file_capture(
        self,
    ) -> None:
        signer = MODULE.late_disposition.SignerIdentity(
            "ssh", "SHA256:fixtureDeliverySigner"
        )
        for mutation in ("replace", "remove"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact = root / "artifact.json"
                signature = root / "artifact.sig"
                canonical = MODULE.late_disposition.canonical_json_bytes(
                    {"value": "captured"}
                )
                artifact.write_bytes(canonical)
                signature.write_bytes(b"captured-signature")

                def mutate_originals(*_args: Any, **_kwargs: Any) -> Any:
                    if mutation == "replace":
                        artifact.write_bytes(
                            MODULE.late_disposition.canonical_json_bytes(
                                {"value": "replacement"}
                            )
                        )
                        signature.write_bytes(b"replacement-signature")
                    else:
                        artifact.unlink()
                        signature.unlink()
                    return subprocess.CompletedProcess(
                        (),
                        0,
                        b'Good "fixture" signature with ED25519 key '
                        b"SHA256:fixtureDeliverySigner\n",
                        b"",
                    )

                with (
                    mock.patch.object(
                        MODULE.late_disposition,
                        "_trusted_executable",
                        return_value="/usr/bin/ssh-keygen",
                    ),
                    mock.patch.object(
                        MODULE.late_disposition,
                        "_run_signature_command",
                        side_effect=mutate_originals,
                    ),
                ):
                    verified = MODULE.late_disposition.verify_detached_signature(
                        artifact,
                        signature,
                        signer,
                        environment={"PATH": "/usr/bin"},
                    )
                self.assertEqual(verified, canonical)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_artifact = root / "real.json"
            real_signature = root / "real.sig"
            real_artifact.write_bytes(
                MODULE.late_disposition.canonical_json_bytes({"value": 1})
            )
            real_signature.write_bytes(b"signature")
            artifact_link = root / "artifact.json"
            signature_link = root / "artifact.sig"
            artifact_link.symlink_to(real_artifact)
            signature_link.symlink_to(real_signature)
            for artifact, signature in (
                (artifact_link, real_signature),
                (real_artifact, signature_link),
            ):
                with self.assertRaisesRegex(
                    MODULE.late_disposition.LateDispositionError,
                    "unavailable",
                ):
                    MODULE.late_disposition.verify_detached_signature(
                        artifact,
                        signature,
                        signer,
                        environment={"PATH": "/usr/bin"},
                    )

    def test_cycle1_r3_atomic_output_is_bound_to_validated_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            repository = root / "delivery-repository"
            outside.mkdir(mode=0o700)
            repository.mkdir(mode=0o700)
            parent = root / "session"
            parent.symlink_to(outside, target_is_directory=True)
            target = parent / "late.json"
            original_replace = os.replace

            def race_parent(
                source: Any, destination: Any, **kwargs: Any
            ) -> None:
                parent.unlink()
                parent.symlink_to(repository, target_is_directory=True)
                original_replace(source, destination, **kwargs)

            with mock.patch.object(
                MODULE.late_disposition.os,
                "replace",
                side_effect=race_parent,
            ):
                MODULE.late_disposition._atomic_write(target, b"evidence")

            self.assertFalse((repository / "late.json").exists())
            self.assertEqual((outside / "late.json").read_bytes(), b"evidence")

    def test_cycle1_r3_output_containment_rejects_aliases_and_unsafe_targets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            outside = root / "outside"
            repository.mkdir(mode=0o700)
            outside.mkdir(mode=0o700)
            repository_alias = root / "repository-alias"
            repository_alias.symlink_to(repository, target_is_directory=True)
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "outside the delivery repository",
            ):
                MODULE.late_disposition._atomic_write(
                    repository_alias / "late.json",
                    b"evidence",
                    repository_root=repository,
                )
            existing_target = outside / "existing-target"
            existing_target.write_bytes(b"preserve")
            unsafe_output = outside / "late.json"
            unsafe_output.symlink_to(existing_target)
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "unsafe output",
            ):
                MODULE.late_disposition._atomic_write(
                    unsafe_output,
                    b"evidence",
                    repository_root=repository,
                )
            self.assertEqual(existing_target.read_bytes(), b"preserve")

            signer = MODULE.late_disposition.SignerIdentity(
                "ssh", "SHA256:fixtureDeliverySigner"
            )
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "outputs must differ",
            ):
                MODULE.late_disposition.sign_artifact(
                    {"value": "same-output"},
                    outside / "same.json",
                    outside / "same.json",
                    signer=signer,
                    signing_key="/unused",
                    environment={"PATH": "/usr/bin"},
                    repository_root=repository,
                )

            traversal = outside / ".." / "repository" / "late.json"
            with self.assertRaisesRegex(
                MODULE.late_disposition.LateDispositionError,
                "outside the delivery repository",
            ):
                MODULE.late_disposition._atomic_write(
                    traversal,
                    b"evidence",
                    repository_root=repository,
                )

    def test_cycle1_r3_two_outputs_and_failure_cleanup_stay_descriptor_bound(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            repository = root / "repository"
            outside.mkdir(mode=0o700)
            repository.mkdir(mode=0o700)
            parent = root / "session"
            parent.symlink_to(outside, target_is_directory=True)
            artifact = MODULE.late_disposition._open_bound_output(
                parent / "artifact.json", repository_root=repository
            )
            signature = MODULE.late_disposition._open_bound_output(
                parent / "artifact.sig", repository_root=repository
            )
            try:
                MODULE.late_disposition._atomic_write_bound(
                    artifact, b"artifact"
                )
                parent.unlink()
                parent.symlink_to(repository, target_is_directory=True)
                MODULE.late_disposition._atomic_write_bound(
                    signature, b"signature"
                )
            finally:
                signature.close()
                artifact.close()
            self.assertEqual((outside / "artifact.json").read_bytes(), b"artifact")
            self.assertEqual((outside / "artifact.sig").read_bytes(), b"signature")
            self.assertEqual(list(repository.iterdir()), [])

            parent.unlink()
            parent.symlink_to(outside, target_is_directory=True)
            original_replace = os.replace

            def fail_after_parent_swap(
                source: Any, destination: Any, **kwargs: Any
            ) -> None:
                parent.unlink()
                parent.symlink_to(repository, target_is_directory=True)
                raise OSError("simulated final replacement failure")

            with (
                mock.patch.object(
                    MODULE.late_disposition.os,
                    "replace",
                    side_effect=fail_after_parent_swap,
                ),
                self.assertRaisesRegex(OSError, "simulated"),
            ):
                MODULE.late_disposition._atomic_write(
                    parent / "failed.json",
                    b"evidence",
                    repository_root=repository,
                )
            self.assertFalse((outside / "failed.json").exists())
            self.assertFalse((repository / "failed.json").exists())
            self.assertFalse(
                any(path.name.startswith(".failed.json.") for path in outside.iterdir())
            )
            self.assertIs(os.replace, original_replace)

    def test_programmatic_apply_refuses_caller_constructed_authorization(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        manifest = {
            "schema_version": "1.1",
            "repository": "SecPal/api",
            "pull_request_number": 123,
            "reviewed_head_sha": "b" * 40,
            "reviewed_state_digest": "c" * 64,
            "eligible_threads": [
                {
                    "thread_id": thread_id,
                    "classification": "VALID_ACTIONABLE",
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "finding_ids": ["D1-forged-substitution"],
                    "evidence_digest": "f" * 64,
                    "follow_up": None,
                }
            ],
        }
        canonical_payload = MODULE._canonical_json_bytes(manifest)
        eligibility_digest = hashlib.sha256(canonical_payload).hexdigest()
        forged = MODULE.EligibilityEvidence(
            eligibility_digest,
            canonical_payload,
            (thread_id,),
        )
        fake = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
                resolve_response(thread_id),
            ]
        )
        verifier = mock.Mock()

        try:
            result = MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (thread_id,),
                apply=True,
                expected_targets={thread_id: expected_thread_state(thread_id)},
                reviewed_state_digest=manifest["reviewed_state_digest"],
                validation_evidence_digest="d" * 64,
                eligibility_evidence_digest=eligibility_digest,
                eligibility_evidence=forged,
                follow_up_verifier=verifier,
                runner=fake,
            )
        except MODULE.ResolutionError as exc:
            self.assertRegex(str(exc), "authenticated mutation boundary")
        else:
            self.fail(
                "unsafe caller-constructed apply succeeded: "
                f"github_calls={len(fake.calls)}, resolved={result['resolved']}"
            )

        self.assertEqual(fake.calls, [])
        verifier.assert_not_called()

    def test_authenticated_programmatic_apply_uses_the_cli_evidence_chain(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        with tempfile.TemporaryDirectory() as directory:
            reviewed, attestation, _eligibility, git = (
                write_authenticated_resolution_inputs(directory, (thread_id,))
            )
            fake = FakeGh(
                [
                    target_response(thread_id, head=attestation["head_sha"]),
                    target_response(thread_id, head=attestation["head_sha"]),
                    target_response(thread_id, head=attestation["head_sha"]),
                    resolve_response(thread_id),
                ]
            )
            verifier = mock.Mock()

            with (
                mock.patch.object(MODULE, "_run_git", git),
                mock.patch.object(MODULE, "_run_gh", fake),
                mock.patch.object(MODULE, "verify_live_follow_up", verifier),
            ):
                result = MODULE.resolve_threads(
                    "SecPal/api",
                    123,
                    attestation["head_sha"],
                    (thread_id,),
                    apply=True,
                    repository_root=directory,
                    reviewed_state_path=Path(directory) / "reviewed.json",
                    expected_reviewed_state_digest=reviewed["state_digest"],
                    validation_evidence_path=Path(directory) / "validation.json",
                    eligibility_evidence_path=Path(directory) / "eligibility.json",
                )

        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(len(fake.calls), 4)
        self.assertGreaterEqual(len(git.calls), 7)
        verifier.assert_not_called()

    def test_authenticated_programmatic_apply_rejects_cross_bound_evidence(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        cases = (
            "eligibility digest",
            "eligibility reviewed head",
            "attestation reviewed state",
            "fix parent",
            "receipt trailer",
            "eligibility repository",
            "eligibility pull request",
            "eligibility thread set",
            "tracked disposition substitution",
        )
        for label in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                reviewed, attestation, eligibility, git = (
                    write_authenticated_resolution_inputs(directory, (thread_id,))
                )
                if label == "eligibility digest":
                    eligibility["eligible_threads"][0]["evidence_digest"] = "9" * 64
                elif label == "eligibility reviewed head":
                    eligibility["reviewed_head_sha"] = "b" * 40
                    attestation = validation_attestation_payload(
                        reviewed,
                        MODULE._digest_json(eligibility),
                    )
                elif label == "attestation reviewed state":
                    attestation["reviewed_state_digest"] = "9" * 64
                elif label == "fix parent":
                    git.reviewed_head = "b" * 40
                elif label == "receipt trailer":
                    git.receipt_digest = "9" * 64
                elif label == "eligibility repository":
                    eligibility["repository"] = "SecPal/contracts"
                    attestation = validation_attestation_payload(
                        reviewed,
                        MODULE._digest_json(eligibility),
                    )
                elif label == "eligibility pull request":
                    eligibility["pull_request_number"] = 124
                    attestation = validation_attestation_payload(
                        reviewed,
                        MODULE._digest_json(eligibility),
                    )
                elif label == "eligibility thread set":
                    eligibility["eligible_threads"][0]["thread_id"] = (
                        "PRRT_exampleOther"
                    )
                    attestation = validation_attestation_payload(
                        reviewed,
                        MODULE._digest_json(eligibility),
                    )
                else:
                    trusted = copy.deepcopy(eligibility)
                    trusted["eligible_threads"][0].update(
                        classification="OUTSIDE_PR_SCOPE",
                        disposition="TRACKED_AS_FOLLOW_UP",
                        follow_up={
                            "repository": "SecPal/api",
                            "issue_number": 456,
                            "issue_url": "https://github.com/SecPal/api/issues/456",
                        },
                    )
                    attestation = validation_attestation_payload(
                        reviewed,
                        MODULE._digest_json(trusted),
                    )
                Path(directory, "eligibility.json").write_text(
                    json.dumps(eligibility),
                    encoding="utf-8",
                )
                Path(directory, "validation.json").write_text(
                    json.dumps(attestation),
                    encoding="utf-8",
                )
                if label != "receipt trailer":
                    git.receipt_digest = attestation[
                        "validation_receipt_digest"
                    ]
                fake = FakeGh([])

                with (
                    mock.patch.object(MODULE, "_run_git", git),
                    mock.patch.object(MODULE, "_run_gh", fake),
                    self.assertRaises(MODULE.ResolutionError),
                ):
                    MODULE.resolve_threads(
                        "SecPal/api",
                        123,
                        attestation["head_sha"],
                        (thread_id,),
                        apply=True,
                        repository_root=directory,
                        reviewed_state_path=Path(directory) / "reviewed.json",
                        expected_reviewed_state_digest=reviewed["state_digest"],
                        validation_evidence_path=Path(directory) / "validation.json",
                        eligibility_evidence_path=Path(directory) / "eligibility.json",
                    )

                self.assertEqual(fake.calls, [])

    def test_apply_requires_canonical_eligibility_before_github_access(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
                resolve_response(thread_id),
            ]
        )
        verifier = mock.Mock()

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "authenticated mutation boundary",
        ):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (thread_id,),
                apply=True,
                expected_targets={thread_id: expected_thread_state(thread_id)},
                reviewed_state_digest="c" * 64,
                validation_evidence_digest="d" * 64,
                eligibility_evidence_digest="e" * 64,
                eligibility_evidence=None,
                follow_up_verifier=verifier,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])
        verifier.assert_not_called()

    def test_apply_refuses_mismatched_or_malformed_canonical_eligibility(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        canonical_payload = MODULE._canonical_json_bytes(payload)
        cases = {
            "digest mismatch": MODULE.EligibilityEvidence(
                "f" * 64,
                canonical_payload,
                (thread_id,),
            ),
            "malformed payload": MODULE.EligibilityEvidence(
                hashlib.sha256(b"{}").hexdigest(),
                b"{}",
                (thread_id,),
            ),
        }
        for label, eligibility in cases.items():
            fake = FakeGh([])
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "authenticated|eligibility evidence",
                ),
            ):
                MODULE.resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    (thread_id,),
                    apply=True,
                    expected_targets={
                        thread_id: expected_thread_state(thread_id)
                    },
                    reviewed_state_digest=payload["reviewed_state_digest"],
                    validation_evidence_digest="d" * 64,
                    eligibility_evidence_digest=eligibility.evidence_digest,
                    eligibility_evidence=eligibility,
                    runner=fake,
                )
            self.assertEqual(fake.calls, [])

    def test_preflight_rejects_insufficient_thread_budget_before_first_write(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh([target_response(first), target_response(second)])
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=3,
            maximum_comments=20,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "thread limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [first, second],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 2)

    def test_changed_target_comments_block_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        initial = [("PRRC_root", "original", None)]
        changed_comment_sets = [
            [("PRRC_root", "edited", None)],
            [
                ("PRRC_root", "original", None),
                ("PRRC_reply", "new reply", "PRRC_root"),
            ],
            [("PRRC_root", "original", "PRRC_other")],
            [],
        ]

        for changed in changed_comment_sets:
            with self.subTest(changed=changed):
                fake = FakeGh(
                    [
                        target_response(thread_id, comments=initial),
                        target_response(thread_id, comments=changed),
                        target_response(thread_id, comments=changed),
                    ]
                )

                result = resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    [thread_id],
                    apply=True,
                    runner=fake,
                    reviewed_comments={thread_id: initial},
                )

                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["resolved"], [])
                self.assertEqual(result["failed"][0]["phase"], "recheck")
                self.assertIn(
                    "target thread changed",
                    result["failed"][0]["error"],
                )
                self.assertEqual(len(fake.calls), 3)

    def test_changed_outdated_state_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, outdated=False),
                target_response(thread_id, outdated=True),
                target_response(thread_id, outdated=True),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertIn("target thread changed", result["failed"][0]["error"])
        self.assertEqual(len(fake.calls), 3)

    def test_preflight_rejects_insufficient_comment_budget_before_first_write(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        comments = [
            ("PRRC_root", "root", None),
            ("PRRC_reply", "reply", "PRRC_root"),
        ]
        fake = FakeGh([target_response(thread_id, comments=comments)])
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=20,
            maximum_comments=3,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "comment limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                reviewed_comments={thread_id: comments},
            )

        self.assertEqual(len(fake.calls), 1)

    def test_preflight_rejects_insufficient_api_budget_before_first_write(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id)])
        limits = mock.Mock(
            maximum_api_calls=2,
            maximum_threads=20,
            maximum_comments=20,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "API call limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

    def test_preflight_uses_observed_sparse_page_counts_before_first_write(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh(
            [
                target_response(
                    first,
                    comments=[("PRRC_first", "first", None)],
                    has_next_page=True,
                    end_cursor="initial-first-page",
                ),
                target_response(first),
                target_response(second),
                target_response(
                    first,
                    comments=[("PRRC_first", "first", None)],
                    has_next_page=True,
                    end_cursor="recheck-first-page",
                ),
                target_response(first),
                resolve_response(first),
                target_response(second),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=7,
            maximum_threads=20,
            maximum_comments=20,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(
                MODULE.ResolutionError,
                "API call limit cannot cover",
            ),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [first, second],
                apply=True,
                runner=fake,
                reviewed_comments={
                    first: [("PRRC_first", "first", None)],
                },
            )

        self.assertEqual(len(fake.calls), 3)

    def test_target_comment_pagination_is_stable_across_recheck(self) -> None:
        thread_id = "PRRT_exampleOne"
        first_page = [
            (f"PRRC_comment{index}", f"body {index}", None)
            for index in range(100)
        ]
        second_page = [("PRRC_comment100", "body 100", "PRRC_comment0")]
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="initial-1",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="recheck-1",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="recheck-2",
                ),
                target_response(thread_id, comments=second_page),
                resolve_response(thread_id),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=10,
            maximum_comments=400,
        )

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=limits,
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                reviewed_comments={thread_id: [*first_page, *second_page]},
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(len(fake.calls), 7)
        self.assertIn("commentsAfter=initial-1", fake.calls[1])
        self.assertIn("commentsAfter=recheck-1", fake.calls[3])
        self.assertIn("commentsAfter=recheck-2", fake.calls[5])

    def test_second_recheck_projection_detects_earlier_page_edit(self) -> None:
        thread_id = "PRRT_exampleOne"
        first_page = [
            (f"PRRC_comment{index}", f"body {index}", None)
            for index in range(100)
        ]
        second_page = [("PRRC_comment100", "body 100", "PRRC_comment0")]
        edited_first_page = [
            (
                comment_id,
                "edited during pagination" if index == 0 else body,
                reply_to_id,
            )
            for index, (comment_id, body, reply_to_id) in enumerate(first_page)
        ]
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="initial",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=first_page,
                    has_next_page=True,
                    end_cursor="recheck-first-pass",
                ),
                target_response(thread_id, comments=second_page),
                target_response(
                    thread_id,
                    comments=edited_first_page,
                    has_next_page=True,
                    end_cursor="recheck-second-pass",
                ),
                target_response(thread_id, comments=second_page),
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=20,
            maximum_comments=500,
        )

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=limits,
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                reviewed_comments={thread_id: [*first_page, *second_page]},
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertIn("changed while rechecking", result["failed"][0]["error"])
        self.assertEqual(len(fake.calls), 6)

    def test_reviewed_comment_state_mismatch_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        reviewed = [("PRRC_root", "reviewed body", None)]
        changed = [("PRRC_root", "new unseen body", None)]
        fake = FakeGh([target_response(thread_id, comments=changed)])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "differs from reviewed feedback",
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                expected_targets={
                    thread_id: expected_thread_state(thread_id, reviewed),
                },
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

    def test_callable_rejects_duplicate_thread_ids_before_reading(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "must be unique"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id, thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_request_requires_immutable_thread_id_tuple(self) -> None:
        with self.assertRaisesRegex(MODULE.ResolutionError, "immutable tuple"):
            MODULE.validate_request(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_exampleOne"],
                False,
            )

    def test_callable_rejects_malformed_request_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "positive"):
            resolve_threads(
                "SecPal/api",
                0,
                "not-an-oid",
                ["not-a-thread"],
                apply=False,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_callable_rejects_non_boolean_apply_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "apply must be boolean"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_exampleOne"],
                apply="yes",
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_unregistered_repository_is_rejected_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(MODULE.ResolutionError, "unsupported repository"):
            resolve_threads(
                "Example/unregistered",
                123,
                "a" * 40,
                ["PRRT_exampleOne"],
                apply=True,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_repository_registry_must_match_authoritative_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "repositories.json"
            registry.write_text(
                json.dumps(
                    {
                        "repositories": [
                            {
                                "repository": "SecPal/api",
                                "maximum_api_calls": 200,
                                "maximum_threads": 500,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(MODULE, "REGISTRY_PATH", registry),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "registry is invalid",
                ),
            ):
                MODULE.load_repository_limits("SecPal/api")

    def test_registry_contract_keeps_resolution_ci_independent(self) -> None:
        registry = json.loads(MODULE.REGISTRY_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            registry["fixed_thread_resolution"],
            MODULE.FIXED_THREAD_RESOLUTION_CONTRACT,
        )
        self.assertEqual(
            registry["fixed_thread_resolution"]["allowed_github_operations"],
            [
                "READ_NAMED_REVIEW_THREAD",
                "READ_AUTHENTICATED_FOLLOW_UP_WORK_GRAPH",
                "AUTHENTICATE_LIFECYCLE_PUBLICATION_PROTECTION",
                "RESOLVE_NAMED_REVIEW_THREAD",
            ],
        )
        self.assertIn(
            "BRANCH_PROTECTION",
            registry["fixed_thread_resolution"]["prohibited_hosted_reads"],
        )
        self.assertIn(
            "MERGE_READINESS",
            registry["fixed_thread_resolution"]["prohibited_hosted_reads"],
        )

    def test_resolver_rejects_registry_without_resolution_contract(self) -> None:
        registry = json.loads(MODULE.REGISTRY_PATH.read_text(encoding="utf-8"))
        registry.pop("fixed_thread_resolution")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repositories.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with (
                mock.patch.object(MODULE, "REGISTRY_PATH", path),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "fixed-thread resolution registry contract is invalid",
                ),
            ):
                MODULE.load_repository_limits("SecPal/.github")

    def test_dry_run_reads_once_and_does_not_mutate(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id)])

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=False,
            runner=fake,
        )

        self.assertEqual(result["pending"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(fake.calls), 1)
        query_argument = next(
            argument
            for argument in fake.calls[0]
            if argument.startswith("query=")
        )
        for expected_fragment in (
            "pullRequest",
            "isOutdated",
            "comments(first: 100",
            "body",
            "replyTo",
        ):
            self.assertIn(expected_fragment, query_argument)

    def test_commit_bound_target_accepts_nullable_database_id(self) -> None:
        thread_id = "PRRT_nullableDatabaseId"
        comments = [("PRRC_nullableRoot", "Exact reviewed body.", None)]
        response = target_response(thread_id, comments=comments)
        response["data"]["node"]["comments"]["nodes"][0]["databaseId"] = None
        fake = FakeGh([response])

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=False,
            runner=fake,
            reviewed_comments={thread_id: comments},
        )

        self.assertEqual(result["pending"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(fake.calls), 1)

    def test_commit_bound_target_rejects_malformed_database_id(self) -> None:
        thread_id = "PRRT_malformedDatabaseId"
        comments = [("PRRC_malformedRoot", "Exact reviewed body.", None)]
        for database_id in (0, -1, True, "1001"):
            with self.subTest(database_id=database_id):
                response = target_response(thread_id, comments=comments)
                response["data"]["node"]["comments"]["nodes"][0][
                    "databaseId"
                ] = database_id
                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "target thread comment identity is incomplete",
                ):
                    resolve_threads(
                        "SecPal/api",
                        123,
                        "a" * 40,
                        [thread_id],
                        apply=False,
                        runner=FakeGh([response]),
                        reviewed_comments={thread_id: comments},
                    )

    def test_late_ssh_signing_key_requires_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            account_home = root / "account"
            repository = root / "repository"
            account_home.mkdir(mode=0o700)
            repository.mkdir(mode=0o700)
            (account_home / ".config").mkdir()
            (account_home / ".gnupg").mkdir(mode=0o700)
            environment = MODULE.late_disposition.signing_environment(
                account_home=account_home
            )
            regular_key = account_home / "key"
            subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(regular_key),
                ],
                check=True,
                env=environment,
                capture_output=True,
            )
            fingerprint = subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-lf",
                    f"{regular_key}.pub",
                    "-E",
                    "sha256",
                ],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            ).stdout.split()[1]
            signer = MODULE.late_disposition.SignerIdentity("ssh", fingerprint)
            key_alias = account_home / "key-alias"
            key_alias.symlink_to(regular_key)
            key_directory = account_home / "key-directory"
            key_directory.mkdir(mode=0o700)
            key_socket = account_home / "key-socket"
            socket_handle = socket.socket(socket.AF_UNIX)
            socket_handle.bind(str(key_socket))
            key_socket.chmod(0o600)

            def select(
                path: Path,
                repository_root: Path = repository,
                *,
                uid: int | None = None,
            ) -> str:
                with (
                    mock.patch.object(
                        MODULE.late_disposition,
                        "read_signing_configuration",
                        return_value=("ssh", str(path)),
                    ),
                    mock.patch.object(
                        MODULE.late_disposition,
                        "os_account_home",
                        return_value=account_home,
                    ),
                ):
                    if uid is None:
                        return MODULE._late_signing_key(signer, repository_root)
                    with mock.patch.object(MODULE.os, "getuid", return_value=uid):
                        return MODULE._late_signing_key(signer, repository_root)

            try:
                for accepted in (regular_key, key_alias):
                    with self.subTest(accepted=accepted.name):
                        self.assertEqual(select(accepted), str(accepted))
                for rejected in (key_directory, key_socket):
                    with (
                        self.subTest(rejected=rejected.name),
                        self.assertRaisesRegex(
                            MODULE.ResolutionError,
                            "regular file",
                        ),
                    ):
                        select(rejected)
                output = account_home / "evidence"
                output.mkdir(mode=0o700)
                artifact = output / "artifact.json"
                signature = output / "artifact.sig"
                MODULE.late_disposition.sign_artifact(
                    {"kind": "LATE_FEEDBACK_CLASSIFICATION"},
                    artifact,
                    signature,
                    signer=signer,
                    signing_key=str(regular_key),
                    environment=environment,
                    signature_namespace=(
                        MODULE.late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE
                    ),
                )
                MODULE.late_disposition.verify_detached_signature(
                    artifact,
                    signature,
                    signer,
                    environment=environment,
                    signature_namespace=(
                        MODULE.late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE
                    ),
                )

                delivery_repository = account_home / "delivery"
                delivery_repository.mkdir(mode=0o700)
                repository_key = delivery_repository / "key"
                repository_key.write_bytes(b"fixture key")
                repository_key.chmod(0o600)
                with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        "OS-account controlled",
                ):
                    select(repository_key, delivery_repository)

                for mode in (0o620, 0o602):
                    regular_key.chmod(mode)
                    with (
                        self.subTest(mode=oct(mode)),
                        self.assertRaisesRegex(
                            MODULE.ResolutionError,
                            "OS-account controlled",
                        ),
                    ):
                        select(regular_key)
                regular_key.chmod(0o600)
                with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        "OS-account controlled",
                ):
                    select(regular_key, uid=os.getuid() + 1)
            finally:
                socket_handle.close()

    def test_apply_resolves_each_open_target_once(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
                target_response(second),
                target_response(second),
                resolve_response(second),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [first, second])
        self.assertEqual(len(fake.calls), 8)

    def test_tracked_follow_up_is_verified_before_final_target_recheck(self) -> None:
        thread_id = "PRRT_exampleOne"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        fake = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
                resolve_response(thread_id),
            ]
        )
        verifier = mock.Mock()

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            eligibility_manifest=manifest,
            follow_up_verifier=verifier,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(
            result["tracked_follow_up_dispositions"],
            [
                {
                    "thread_id": thread_id,
                    "technically_blocking": False,
                    "mechanically_blocking": False,
                    "resolution_meaning": "SAFELY_DISPOSITIONED_TRACKED",
                }
            ],
        )
        verifier.assert_called_once_with(identity, mock.ANY)
        self.assertEqual(len(fake.calls), 4)

        refused = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
            ]
        )
        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            eligibility_manifest=manifest,
            follow_up_verifier=mock.Mock(
                side_effect=MODULE.ResolutionError("follow-up issue is closed")
            ),
            runner=refused,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"][0]["phase"], "follow-up")
        self.assertEqual(len(refused.calls), 1)

    def test_tracked_follow_up_rechecks_target_after_verification(self) -> None:
        thread_id = "PRRT_exampleOne"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        drifted = False
        mutation_calls = 0

        def runner(arguments: Sequence[str]) -> dict[str, Any]:
            nonlocal mutation_calls
            query = next(
                argument.removeprefix("query=")
                for argument in arguments
                if argument.startswith("query=")
            )
            if query == MODULE.TARGET_QUERY:
                return target_response(
                    thread_id,
                    head="b" * 40 if drifted else "a" * 40,
                )
            if query == MODULE.RESOLVE_MUTATION:
                mutation_calls += 1
                return resolve_response(thread_id)
            raise AssertionError("unexpected GraphQL document")

        def verifier(_identity: Any, *_args: Any) -> None:
            nonlocal drifted
            drifted = True

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            eligibility_manifest=manifest,
            follow_up_verifier=verifier,
            runner=runner,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(mutation_calls, 0)

    def test_resolution_succeeds_for_every_hosted_check_condition_without_reading_it(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        for condition in ("PENDING", "FAILED", None, "OMITTED"):
            with self.subTest(condition=condition):
                responses = [
                    target_response(thread_id),
                    target_response(thread_id),
                    target_response(thread_id),
                    resolve_response(thread_id),
                ]
                if condition != "OMITTED":
                    for response in responses[:3]:
                        response["data"]["node"]["pullRequest"][
                            "hostedChecks"
                        ] = condition
                fake = FakeGh(responses)

                result = resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    [thread_id],
                    apply=True,
                    runner=fake,
                )

                self.assertEqual(result["resolved"], [thread_id])
                serialized_calls = "\n".join(" ".join(call) for call in fake.calls)
                for prohibited in (
                    "checkSuites",
                    "statusCheckRollup",
                    "mergeable",
                    "mergeStateStatus",
                    "branchProtectionRule",
                    "codeScanningAlerts",
                    "workflowRuns",
                ):
                    self.assertNotIn(prohibited, serialized_calls)

    def test_already_resolved_target_is_idempotent(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, resolved=True),
                target_response(thread_id, resolved=True),
                target_response(thread_id, resolved=True),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
            expected_targets={
                thread_id: expected_thread_state(thread_id, resolved=True),
            },
        )

        self.assertEqual(result["already_resolved"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertEqual(len(fake.calls), 3)

    def test_outdated_drift_already_resolved_target_receives_no_second_write(
        self,
    ) -> None:
        thread_id = "PRRT_postFixAlreadyResolved"
        fake = FakeGh(
            [
                target_response(thread_id, resolved=True, outdated=True),
                target_response(thread_id, resolved=True, outdated=True),
                target_response(thread_id, resolved=True, outdated=True),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
            expected_targets={
                thread_id: expected_thread_state(
                    thread_id,
                    resolved=False,
                    outdated=False,
                ),
            },
        )

        self.assertEqual(result["already_resolved"], [thread_id])
        self.assertEqual(result["resolved"], [])
        self.assertFalse(
            any(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in fake.calls
            )
        )

    def test_resolved_postcondition_still_requires_exact_comment_state(self) -> None:
        thread_id = "PRRT_exampleOne"
        reviewed = [
            ("PRRC_root", "reviewed body", None),
            ("PRRC_reply", "reviewed reply", "PRRC_root"),
        ]
        cases = {
            "substituted top-level comment": [
                ("PRRC_other", "reviewed body", None),
                ("PRRC_reply", "reviewed reply", "PRRC_other"),
            ],
            "changed finding body": [
                ("PRRC_root", "changed body", None),
                ("PRRC_reply", "reviewed reply", "PRRC_root"),
            ],
            "material new reply": [
                *reviewed,
                ("PRRC_newReply", "new reply", "PRRC_root"),
            ],
            "edited reply": [
                ("PRRC_root", "reviewed body", None),
                ("PRRC_reply", "edited reply", "PRRC_root"),
            ],
            "reparented reply": [
                ("PRRC_root", "reviewed body", None),
                ("PRRC_reply", "reviewed reply", None),
            ],
            "deleted reply": [reviewed[0]],
        }
        for label, live_comments in cases.items():
            fake = FakeGh(
                [
                    target_response(
                        thread_id,
                        resolved=True,
                        outdated=True,
                        comments=live_comments,
                    )
                ]
            )
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "differs from reviewed feedback",
                ),
            ):
                resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    (thread_id,),
                    apply=True,
                    expected_targets={
                        thread_id: expected_thread_state(
                            thread_id,
                            reviewed,
                        )
                    },
                    runner=fake,
                )
            self.assertEqual(len(fake.calls), 1)
            self.assertFalse(
                any(
                    f"query={MODULE.RESOLVE_MUTATION}" in call
                    for call in fake.calls
                )
            )

    def test_already_resolved_tracked_follow_up_is_reverified_before_safe_report(self) -> None:
        thread_id = "PRRT_exampleTrackedResolved"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        expected = expected_thread_state(thread_id, resolved=True)
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, [], resolved=True),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        verifier = mock.Mock(
            side_effect=MODULE.ResolutionError("follow-up issue is closed")
        )
        fake = FakeGh([target_response(thread_id, resolved=True)])

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected},
            eligibility_manifest=manifest,
            follow_up_verifier=verifier,
            runner=fake,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"][0]["phase"], "follow-up")
        self.assertEqual(
            result["tracked_follow_up_dispositions"],
            [
                {
                    "thread_id": thread_id,
                    "technically_blocking": False,
                    "mechanically_blocking": True,
                    "resolution_meaning": "SAFELY_DISPOSITIONED_TRACKED",
                }
            ],
        )
        verifier.assert_called_once_with(identity, mock.ANY)

    def test_follow_up_budget_loss_reserves_the_entire_unattempted_suffix(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        manifest = eligibility_payload(
            reviewed_state_payload(first, []),
            (first, second),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
            ]
        )

        def consume_follow_up_capacity(_identity: Any, budget: Any) -> None:
            for _ in range(3):
                MODULE._consume_api_call(budget)

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=MODULE.RepositoryLimits(10, 100, 100),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (first, second),
                apply=True,
                expected_targets={
                    first: expected_thread_state(first),
                    second: expected_thread_state(second),
                },
                eligibility_manifest=manifest,
                follow_up_verifier=consume_follow_up_capacity,
                runner=fake,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(result["unattempted"], [second])
        self.assertFalse(
            any(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in fake.calls
            )
        )
        self.assertEqual(len(fake.calls), 2)

    def test_future_tracked_minimum_is_reserved_before_first_write(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        manifest = eligibility_payload(
            reviewed_state_payload(first, []),
            (first, second),
        )
        for issue_number, item in enumerate(
            manifest["eligible_threads"], start=123
        ):
            item.update(
                classification="OUTSIDE_PR_SCOPE",
                disposition="TRACKED_AS_FOLLOW_UP",
                follow_up={
                    "repository": "SecPal/api",
                    "issue_number": issue_number,
                    "issue_url": (
                        f"https://github.com/SecPal/api/issues/{issue_number}"
                    ),
                },
            )
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
            ]
        )

        def consume_minimum_follow_up_read(_identity: Any, budget: Any) -> None:
            MODULE._consume_api_call(budget)

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=MODULE.RepositoryLimits(9, 100, 100),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (first, second),
                apply=True,
                expected_targets={
                    first: expected_thread_state(first),
                    second: expected_thread_state(second),
                },
                eligibility_manifest=manifest,
                follow_up_verifier=consume_minimum_follow_up_read,
                runner=fake,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(result["unattempted"], [second])
        self.assertFalse(
            any(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in fake.calls
            )
        )
        self.assertEqual(len(fake.calls), 2)

    def test_future_tracked_minimum_counts_every_remaining_tracked_thread(
        self,
    ) -> None:
        thread_ids = (
            "PRRT_exampleOne",
            "PRRT_exampleTwo",
            "PRRT_exampleThree",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_ids[0], []), thread_ids
        )
        for issue_number, item in enumerate(
            manifest["eligible_threads"], start=123
        ):
            item.update(
                classification="OUTSIDE_PR_SCOPE",
                disposition="TRACKED_AS_FOLLOW_UP",
                follow_up={
                    "repository": "SecPal/api",
                    "issue_number": issue_number,
                    "issue_url": (
                        f"https://github.com/SecPal/api/issues/{issue_number}"
                    ),
                },
            )
        fake = FakeGh([target_response(item) for item in thread_ids])

        def consume_minimum_follow_up_read(_identity: Any, budget: Any) -> None:
            MODULE._consume_api_call(budget)

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=MODULE.RepositoryLimits(13, 100, 100),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                thread_ids,
                apply=True,
                expected_targets={
                    item: expected_thread_state(item) for item in thread_ids
                },
                eligibility_manifest=manifest,
                follow_up_verifier=consume_minimum_follow_up_read,
                runner=fake,
            )

        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["unattempted"], list(thread_ids[1:]))
        self.assertEqual(len(fake.calls), 3)

    def test_future_tracked_minimum_ignores_non_tracked_suffix_items(self) -> None:
        thread_ids = (
            "PRRT_exampleOne",
            "PRRT_exampleTwo",
            "PRRT_exampleThree",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_ids[0], []), thread_ids
        )
        manifest["eligible_threads"][1].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        fake = FakeGh([target_response(item) for item in thread_ids])

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=MODULE.RepositoryLimits(12, 100, 100),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                thread_ids,
                apply=True,
                expected_targets={
                    item: expected_thread_state(item) for item in thread_ids
                },
                eligibility_manifest=manifest,
                runner=fake,
            )

        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["unattempted"], list(thread_ids[1:]))
        self.assertEqual(len(fake.calls), 3)

    def test_future_tracked_minimum_allows_a_sufficient_batch(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        manifest = eligibility_payload(
            reviewed_state_payload(first, []), (first, second)
        )
        for issue_number, item in enumerate(
            manifest["eligible_threads"], start=123
        ):
            item.update(
                classification="OUTSIDE_PR_SCOPE",
                disposition="TRACKED_AS_FOLLOW_UP",
                follow_up={
                    "repository": "SecPal/api",
                    "issue_number": issue_number,
                    "issue_url": (
                        f"https://github.com/SecPal/api/issues/{issue_number}"
                    ),
                },
            )
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
                target_response(second),
                target_response(second),
                resolve_response(second),
            ]
        )

        def consume_minimum_follow_up_read(_identity: Any, budget: Any) -> None:
            MODULE._consume_api_call(budget)

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=MODULE.RepositoryLimits(10, 100, 100),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (first, second),
                apply=True,
                expected_targets={
                    first: expected_thread_state(first),
                    second: expected_thread_state(second),
                },
                eligibility_manifest=manifest,
                follow_up_verifier=consume_minimum_follow_up_read,
                runner=fake,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resolved"], [first, second])
        self.assertEqual(len(fake.calls), 8)

    def test_unknown_follow_up_growth_retains_structured_partial_failure(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        manifest = eligibility_payload(
            reviewed_state_payload(first, []), (first, second)
        )
        for issue_number, item in enumerate(
            manifest["eligible_threads"], start=123
        ):
            item.update(
                classification="OUTSIDE_PR_SCOPE",
                disposition="TRACKED_AS_FOLLOW_UP",
                follow_up={
                    "repository": "SecPal/api",
                    "issue_number": issue_number,
                    "issue_url": (
                        f"https://github.com/SecPal/api/issues/{issue_number}"
                    ),
                },
            )
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
            ]
        )
        follow_up_reads = 0

        def consume_variable_follow_up_reads(_identity: Any, budget: Any) -> None:
            nonlocal follow_up_reads
            count = 1 if follow_up_reads == 0 else 3
            follow_up_reads += 1
            for _ in range(count):
                MODULE._consume_api_call(budget)

        with mock.patch.object(
            MODULE,
            "load_repository_limits",
            return_value=MODULE.RepositoryLimits(11, 100, 100),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (first, second),
                apply=True,
                expected_targets={
                    first: expected_thread_state(first),
                    second: expected_thread_state(second),
                },
                eligibility_manifest=manifest,
                follow_up_verifier=consume_variable_follow_up_reads,
                runner=fake,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [first])
        self.assertEqual(result["failed"][0]["thread_id"], second)
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(result["unattempted"], [])
        self.assertEqual(len(fake.calls), 5)

    def test_follow_up_suffix_reservation_covers_thread_and_comment_limits(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        manifest = eligibility_payload(
            reviewed_state_payload(first, []),
            (first, second),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        cases = {
            "thread": (
                MODULE.RepositoryLimits(20, 6, 100),
                [],
                MODULE._consume_thread,
            ),
            "comment": (
                MODULE.RepositoryLimits(20, 100, 6),
                [("PRRC_root", "review body", None)],
                MODULE._consume_comment,
            ),
        }
        for label, (limits, comments, consume) in cases.items():
            fake = FakeGh(
                [
                    target_response(first, comments=comments),
                    target_response(second, comments=comments),
                    target_response(first, comments=comments),
                    target_response(first, comments=comments),
                    resolve_response(first),
                ]
            )

            def consume_follow_up_capacity(
                _identity: Any,
                budget: Any,
                consume: Any = consume,
            ) -> None:
                consume(budget)

            with (
                self.subTest(label=label),
                mock.patch.object(
                    MODULE,
                    "load_repository_limits",
                    return_value=limits,
                ),
            ):
                result = resolve_threads(
                    "SecPal/api",
                    123,
                    "a" * 40,
                    (first, second),
                    apply=True,
                    expected_targets={
                        first: expected_thread_state(first, comments),
                        second: expected_thread_state(second, comments),
                    },
                    eligibility_manifest=manifest,
                    follow_up_verifier=consume_follow_up_capacity,
                    runner=fake,
                )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["resolved"], [])
            self.assertEqual(result["unattempted"], [second])
            self.assertFalse(
                any(
                    f"query={MODULE.RESOLVE_MUTATION}" in call
                    for call in fake.calls
                )
            )
            self.assertEqual(len(fake.calls), 2)

    def test_initially_resolved_target_is_rechecked_before_success(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, resolved=True),
                target_response(thread_id, resolved=False),
                target_response(thread_id, resolved=False),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
            expected_targets={
                thread_id: expected_thread_state(thread_id, resolved=True),
            },
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["already_resolved"], [])
        self.assertEqual(result["failed"][0]["thread_id"], thread_id)
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(len(fake.calls), 3)

    def test_cli_requires_reviewed_state_digest_and_validation_evidence(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.parse_args(
                [
                    "--repo",
                    "SecPal/api",
                    "--pr",
                    "123",
                    "--expected-head",
                    "a" * 40,
                    "--reviewed-state",
                    "reviewed.json",
                    "--thread-id",
                    "PRRT_exampleOne",
                ]
            )

    def test_cycle2_late_cli_requires_distinct_final_eligibility_artifact(
        self,
    ) -> None:
        arguments = [
            "--repo",
            "SecPal/api",
            "--pr",
            "123",
            "--repo-root",
            "/delivery",
            "--expected-head",
            "a" * 40,
            "--reviewed-state",
            "reviewed.json",
            "--expected-reviewed-state-digest",
            "b" * 64,
            "--validation-evidence",
            "attestation.json",
            "--delivery-issue",
            "724",
            "--late-classification-evidence",
            "classification.json",
            "--late-classification-signature",
            "classification.sig",
            "--late-disposition-evidence",
            "disposition.json",
            "--late-disposition-signature",
            "disposition.sig",
            "--thread-id",
            "PRRT_exampleOne",
        ]
        with self.assertRaises(SystemExit):
            MODULE.parse_args(arguments)
        parsed = MODULE.parse_args(
            [
                *arguments,
                "--final-eligibility-evidence",
                "final-eligibility.json",
            ]
        )
        self.assertEqual(
            parsed.final_eligibility_evidence,
            "final-eligibility.json",
        )
        with self.assertRaises(SystemExit):
            MODULE.parse_args(
                [
                    *arguments,
                    "--final-eligibility-evidence",
                    "final-eligibility.json",
                    "--eligibility-evidence",
                    "ordinary-eligibility.json",
                ]
            )

    def test_recovery_authority_cli_requires_exact_closed_input_set(self) -> None:
        arguments = [
            "--repo",
            "SecPal/api",
            "--pr",
            "123",
            "--repo-root",
            "/delivery",
            "--expected-head",
            "a" * 40,
            "--reviewed-state",
            "reviewed.json",
            "--expected-reviewed-state-digest",
            "b" * 64,
            "--validation-evidence",
            "attestation.json",
            "--eligibility-evidence",
            "eligibility.json",
            "--thread-id",
            "PRRT_exampleOne",
        ]
        with self.assertRaises(SystemExit):
            MODULE.parse_args(
                [
                    *arguments,
                    "--delivery-issue",
                    "790",
                    "--exceptional-recovery-evidence",
                    "recovery.json",
                ]
            )
        parsed = MODULE.parse_args(
            [
                *arguments,
                "--delivery-issue",
                "790",
                "--exceptional-recovery-evidence",
                "recovery.json",
                "--exceptional-recovery-authorization",
                "authorization.json",
            ]
        )
        self.assertEqual(parsed.delivery_issue, 790)
        self.assertEqual(parsed.exceptional_recovery_evidence, "recovery.json")
        self.assertEqual(
            parsed.exceptional_recovery_authorization, "authorization.json"
        )
        with self.assertRaises(SystemExit):
            MODULE.parse_args(
                [
                    *arguments,
                    "--integration-evidence",
                    "integration.json",
                    "--delivery-issue",
                    "790",
                    "--exceptional-recovery-evidence",
                    "recovery.json",
                    "--exceptional-recovery-authorization",
                    "authorization.json",
                ]
            )

    def test_callable_requires_validation_binding_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "authenticated mutation boundary",
        ):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ("PRRT_exampleOne",),
                apply=True,
                expected_targets={
                    "PRRT_exampleOne": expected_thread_state(
                        "PRRT_exampleOne"
                    ),
                },
                reviewed_state_digest="c" * 64,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_callable_requires_reviewed_target_state_before_reading(self) -> None:
        fake = FakeGh([])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "authenticated mutation boundary",
        ):
            MODULE.resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ("PRRT_exampleOne",),
                apply=True,
                reviewed_state_digest="c" * 64,
                validation_evidence_digest="d" * 64,
                eligibility_evidence_digest="e" * 64,
                runner=fake,
            )

        self.assertEqual(fake.calls, [])

    def test_reviewed_state_loader_binds_target_comment_digests(self) -> None:
        thread_id = "PRRT_exampleOne"
        comments = [("PRRC_root", "reviewed body", None)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(
                json.dumps(reviewed_state_payload(thread_id, comments)),
                encoding="utf-8",
            )

            reviewed = MODULE.load_reviewed_state(
                path,
                "SecPal/api",
                123,
                reviewed_state_payload(thread_id, comments)["state_digest"],
                (thread_id,),
            )

        self.assertEqual(
            reviewed.targets[thread_id],
            expected_thread_state(thread_id, comments),
        )

    def test_reviewed_state_loader_binds_resolution_state(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(
            thread_id,
            [("PRRC_root", "reviewed body", None)],
            resolved=True,
            outdated=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            reviewed = MODULE.load_reviewed_state(
                path,
                "SecPal/api",
                123,
                payload["state_digest"],
                (thread_id,),
            )

        self.assertEqual(
            reviewed.targets[thread_id],
            expected_thread_state(
                thread_id,
                [("PRRC_root", "reviewed body", None)],
                resolved=True,
                outdated=True,
            ),
        )

    def test_reopened_thread_after_reviewed_capture_blocks_before_mutation(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, resolved=False)])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "differs from reviewed feedback",
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                expected_targets={
                    thread_id: expected_thread_state(thread_id, resolved=True),
                },
            )

        self.assertEqual(len(fake.calls), 1)

    def test_outdated_change_after_reviewed_capture_remains_actionable(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, outdated=True),
                target_response(thread_id, outdated=True),
                target_response(thread_id, outdated=True),
                resolve_response(thread_id),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [thread_id])
        self.assertEqual(len(fake.calls), 4)

    def test_outdated_state_regression_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, outdated=False)])

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "differs from reviewed feedback",
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
                expected_targets={
                    thread_id: expected_thread_state(thread_id, outdated=True),
                },
            )

        self.assertEqual(len(fake.calls), 1)

    def test_reviewed_state_digest_drift_blocks_before_validation_or_github(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "does not match the captured digest",
            ):
                MODULE.load_reviewed_state(
                    path,
                    "SecPal/api",
                    123,
                    "0" * 64,
                    (thread_id,),
                )

    def test_validation_attestation_binds_fix_head_and_reviewed_state(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attestation.json"
            path.write_text(json.dumps(attestation), encoding="utf-8")

            digest = MODULE.load_validation_evidence(
                path,
                "SecPal/api",
                "c" * 40,
                reviewed,
            )

        self.assertEqual(
            digest.evidence_digest,
            attestation["attestation_digest"],
        )

    def test_attestation_rejects_forged_receipt_and_missing_manual_gates(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        for mutation in ("receipt", "eligibility", "gates", "secret"):
            with self.subTest(mutation=mutation):
                changed = dict(attestation)
                if mutation == "receipt":
                    changed["validation_receipt_digest"] = "0" * 64
                elif mutation == "eligibility":
                    changed["eligibility_evidence_digest"] = "0" * 64
                else:
                    changed["manual_gate_evidence"] = (
                        []
                        if mutation == "gates"
                        else [
                            {
                                **attestation["manual_gate_evidence"][0],
                                "evidence": "Authorization: Bearer secret",
                            },
                            *attestation["manual_gate_evidence"][1:],
                        ]
                    )
                fields = {
                    key: value
                    for key, value in changed.items()
                    if key != "attestation_digest"
                }
                changed["attestation_digest"] = MODULE._digest_json(fields)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "attestation.json"
                    path.write_text(json.dumps(changed), encoding="utf-8")

                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        "validation evidence is invalid or stale",
                    ):
                        MODULE.load_validation_evidence(
                            path,
                            "SecPal/api",
                            "c" * 40,
                            reviewed,
                        )

    def test_validation_evidence_head_drift_blocks(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attestation.json"
            path.write_text(json.dumps(attestation), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "validation evidence does not match the fix commit",
            ):
                MODULE.load_validation_evidence(
                    path,
                    "SecPal/api",
                    "b" * 40,
                    reviewed,
                )

    def test_validation_receipt_cannot_authorize_no_change_resolution(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        receipt = validation_receipt_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "authenticated fix-commit attestation",
            ):
                MODULE.load_validation_evidence(
                    path,
                    "SecPal/api",
                    "a" * 40,
                    reviewed,
                )

    def test_local_commit_binding_rejects_tree_parent_and_trailer_drift(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "attestation.json"
            evidence_path.write_text(json.dumps(attestation), encoding="utf-8")
            validation = MODULE.load_validation_evidence(
                evidence_path,
                "SecPal/api",
                "c" * 40,
                reviewed,
            )
            cases = {
                "tree": {"tree": "0" * 40},
                "parent": {"reviewed_head": "0" * 40},
                "trailer": {"receipt_digest": "0" * 64},
            }
            for expected_error, changes in cases.items():
                with self.subTest(expected_error=expected_error):
                    fake = FakeGit(
                        expected_head="c" * 40,
                        reviewed_head=changes.get(
                            "reviewed_head", reviewed.head_sha
                        ),
                        tree=changes.get("tree", attestation["validated_tree_sha"]),
                        receipt_digest=changes.get(
                            "receipt_digest",
                            attestation["validation_receipt_digest"],
                        ),
                    )
                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        expected_error,
                    ):
                        MODULE.verify_local_fix_commit(
                            Path(directory),
                            "SecPal/api",
                            "c" * 40,
                            reviewed,
                            validation,
                            runner=fake,
                        )

    def test_local_commit_binding_rejects_wrong_origin_and_invalid_signature(
        self,
    ) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        attestation = validation_attestation_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "attestation.json"
            evidence_path.write_text(json.dumps(attestation), encoding="utf-8")
            validation = MODULE.load_validation_evidence(
                evidence_path,
                "SecPal/api",
                "c" * 40,
                reviewed,
            )
            cases = {
                "origin": {"repository": "SecPal/frontend"},
                "signature": {"signature_valid": False},
            }
            for expected_error, changes in cases.items():
                with self.subTest(expected_error=expected_error):
                    fake = FakeGit(
                        expected_head="c" * 40,
                        reviewed_head=reviewed.head_sha,
                        tree=attestation["validated_tree_sha"],
                        receipt_digest=attestation[
                            "validation_receipt_digest"
                        ],
                        **changes,
                    )
                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        expected_error,
                    ):
                        MODULE.verify_local_fix_commit(
                            Path(directory),
                            "SecPal/api",
                            "c" * 40,
                            reviewed,
                            validation,
                            runner=fake,
                        )

    def test_local_commit_binding_rejects_an_unknown_evidence_kind(self) -> None:
        reviewed = mock.Mock(head_sha="a" * 40)
        validation = MODULE.ValidationEvidence(
            kind="caller-constructed",
            evidence_digest="d" * 64,
            validated_tree_sha="f" * 40,
            validation_receipt_digest="e" * 64,
            eligibility_evidence_digest="f" * 64,
        )
        fake = mock.Mock()
        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "validation evidence binding",
        ):
            MODULE.verify_local_fix_commit(
                Path("."),
                "SecPal/api",
                "c" * 40,
                reviewed,
                validation,
                runner=fake,
            )
        fake.assert_not_called()

    def test_missing_validation_evidence_blocks_before_github(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        reviewed = mock.Mock(
            head_sha=payload["head_sha"],
            state_digest=payload["state_digest"],
            feedback_digest=payload["feedback_digest"],
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "validation evidence is unavailable",
            ):
                MODULE.load_validation_evidence(
                    Path(directory) / "missing-attestation.json",
                    "SecPal/api",
                    "a" * 40,
                    reviewed,
                )

    def test_eligibility_manifest_binds_every_requested_thread(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        payload = reviewed_state_payload(first, [])
        payload["threads"].append(
            {
                "node_id": second,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [],
            }
        )
        feedback = {
            key: payload[key]
            for key in (
                "pull_request_reactions",
                "reviews",
                "conversation_comments",
                "threads",
            )
        }
        payload["feedback_digest"] = MODULE._digest_json(feedback)
        identity = {
            key: payload[key]
            for key in (
                "repository",
                "pull_request_number",
                "head_sha",
                "base_ref",
                "base_sha",
                "pr_state",
            )
        }
        payload["state_digest"] = MODULE._digest_json(
            {**identity, "feedback": feedback}
        )
        manifest = eligibility_payload(payload, (first, second))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            evidence_digest = MODULE.load_eligibility_evidence(
                path,
                "SecPal/api",
                123,
                payload["head_sha"],
                payload["state_digest"],
                (first, second),
                authenticated_evidence_digest=MODULE._digest_json(manifest),
            )

        self.assertEqual(
            evidence_digest.evidence_digest,
            MODULE._digest_json(manifest),
        )

    def test_eligibility_rejects_caller_selected_target_set(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        third = "PRRT_exampleThree"
        reviewed = reviewed_state_payload(first, [])
        manifest = eligibility_payload(reviewed, (first, second))
        cases = {
            "omitted": (second,),
            "added": (first, second, third),
            "duplicated": (first, first, second),
            "reordered": (second, first),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            for label, caller_targets in cases.items():
                with (
                    self.subTest(label=label),
                    self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        "cover requested threads exactly",
                    ),
                ):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        reviewed["head_sha"],
                        reviewed["state_digest"],
                        caller_targets,
                        authenticated_evidence_digest=MODULE._digest_json(
                            manifest
                        ),
                    )

    def test_authenticated_v1_0_legacy_eligibility_remains_readable(self) -> None:
        thread_id = "PRRT_exampleOne"
        reviewed = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(reviewed, (thread_id,))
        manifest["schema_version"] = "1.0"
        del manifest["eligible_threads"][0]["follow_up"]
        original_digest = MODULE._digest_json(manifest)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            evidence = MODULE.load_eligibility_evidence(
                path,
                "SecPal/api",
                123,
                reviewed["head_sha"],
                reviewed["state_digest"],
                (thread_id,),
                authenticated_evidence_digest=original_digest,
            )

        self.assertEqual(evidence.evidence_digest, original_digest)
        self.assertEqual(
            hashlib.sha256(evidence.canonical_payload).hexdigest(),
            original_digest,
        )

    def test_authenticated_v1_0_legacy_apply_uses_no_follow_up_reader(self) -> None:
        thread_id = "PRRT_exampleOne"
        reviewed = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(reviewed, (thread_id,))
        manifest["schema_version"] = "1.0"
        del manifest["eligible_threads"][0]["follow_up"]
        fake = FakeGh(
            [
                target_response(thread_id),
                target_response(thread_id),
                target_response(thread_id),
                resolve_response(thread_id),
            ]
        )
        verifier = mock.Mock()

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (thread_id,),
            apply=True,
            expected_targets={thread_id: expected_thread_state(thread_id)},
            eligibility_manifest=manifest,
            follow_up_verifier=verifier,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [thread_id])
        verifier.assert_not_called()

    def test_v1_0_eligibility_refuses_tracked_and_follow_up_shapes(self) -> None:
        thread_id = "PRRT_exampleOne"
        reviewed = reviewed_state_payload(thread_id, [])
        base = eligibility_payload(reviewed, (thread_id,))
        base["schema_version"] = "1.0"
        cases = {
            "tracked disposition": {
                **base["eligible_threads"][0],
                "classification": "OUTSIDE_PR_SCOPE",
                "disposition": "TRACKED_AS_FOLLOW_UP",
            },
            "follow-up field": base["eligible_threads"][0],
        }
        del cases["tracked disposition"]["follow_up"]
        for label, item in cases.items():
            manifest = {**base, "eligible_threads": [item]}
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "eligibility evidence thread",
                ):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        reviewed["head_sha"],
                        reviewed["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(manifest),
                    )

    def test_ineligible_or_unlisted_thread_blocks_before_github(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(payload, (thread_id,))
        cases = {
            "unlisted": [],
            "unsafe disposition": [
                {
                    **manifest["eligible_threads"][0],
                    "disposition": "UNRESOLVED_VALID_FINDING",
                }
            ],
        }
        for label, threads in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                changed = {**manifest, "eligible_threads": threads}
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(changed), encoding="utf-8")

                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "eligibility evidence",
                ):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        payload["head_sha"],
                        payload["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(
                            changed
                        ),
                    )

    def test_tracked_follow_up_eligibility_is_exact_and_authenticated(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(payload, (thread_id,))
        manifest["schema_version"] = "1.1"
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            evidence = MODULE.load_eligibility_evidence(
                path,
                "SecPal/api",
                123,
                payload["head_sha"],
                payload["state_digest"],
                (thread_id,),
                authenticated_evidence_digest=MODULE._digest_json(manifest),
            )
        self.assertEqual(evidence.evidence_digest, MODULE._digest_json(manifest))
        self.assertEqual(
            MODULE._tracked_follow_ups_from_payload(
                evidence.canonical_payload,
                repository="SecPal/api",
                number=123,
                reviewed_head_sha=payload["head_sha"],
                reviewed_state_digest=payload["state_digest"],
                thread_ids=(thread_id,),
            )[
                thread_id
            ].issue_number,
            123,
        )

        changed = copy.deepcopy(manifest)
        changed["eligible_threads"][0]["follow_up"] = {
            "repository": "SecPal/api",
            "issue_number": 124,
            "issue_url": "https://github.com/SecPal/api/issues/124",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.ResolutionError, "not authenticated"
            ):
                MODULE.load_eligibility_evidence(
                    path,
                    "SecPal/api",
                    123,
                    payload["head_sha"],
                    payload["state_digest"],
                    (thread_id,),
                    authenticated_evidence_digest=MODULE._digest_json(manifest),
                )

    def test_tracked_follow_up_identity_fails_closed_when_malformed(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        base = eligibility_payload(payload, (thread_id,))
        base["schema_version"] = "1.1"
        base["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
        )
        cases = {
            "missing": None,
            "malformed repository": {
                "repository": "SecPal",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
            "non-positive number": {
                "repository": "SecPal/api",
                "issue_number": 0,
                "issue_url": "https://github.com/SecPal/api/issues/0",
            },
            "pull URL": {
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/pull/123",
            },
            "wrong owner": {
                "repository": "SecPal/frontend",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
            "wrong number": {
                "repository": "SecPal/api",
                "issue_number": 124,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        }
        for label, follow_up in cases.items():
            manifest = copy.deepcopy(base)
            if follow_up is not None:
                manifest["eligible_threads"][0]["follow_up"] = follow_up
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.ResolutionError, "follow-up"):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        payload["head_sha"],
                        payload["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(manifest),
                    )

        duplicate = copy.deepcopy(base)
        duplicate["eligible_threads"][0]["follow_up"] = {
            "repository": "SecPal/api",
            "issue_number": 123,
            "issue_url": "https://github.com/SecPal/api/issues/123",
        }
        serialized = json.dumps(duplicate).replace(
            '"issue_number": 123',
            '"issue_number": 122, "issue_number": 123',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(serialized, encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ResolutionError, "malformed"):
                MODULE.load_eligibility_evidence(
                    path,
                    "SecPal/api",
                    123,
                    payload["head_sha"],
                    payload["state_digest"],
                    (thread_id,),
                    authenticated_evidence_digest=MODULE._digest_json(duplicate),
                )

    def test_live_follow_up_requires_open_structurally_complete_exact_issue(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        failures = {
            "missing": MODULE.ResolutionError("follow-up is inaccessible"),
            "closed": MODULE.LiveFollowUpState(
                identity, False, True, False, False, True
            ),
            "structurally incomplete": MODULE.LiveFollowUpState(
                identity, True, False, False, False, True
            ),
            "identity mismatch": MODULE.LiveFollowUpState(
                MODULE.FollowUpIdentity(
                    repository="SecPal/frontend",
                    issue_number=123,
                    issue_url="https://github.com/SecPal/frontend/issues/123",
                ),
                True,
                True,
                False,
                False,
                True,
            ),
        }
        for label, result in failures.items():
            def reader(_identity: Any, result: Any = result) -> Any:
                if isinstance(result, Exception):
                    raise result
                return result

            with self.subTest(label=label), self.assertRaisesRegex(
                MODULE.ResolutionError, "follow-up"
            ):
                MODULE.verify_live_follow_up(identity, state_reader=reader)

        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                MODULE.verify_live_follow_up(
                    identity,
                    state_reader=lambda _identity, blocked=blocked: MODULE.LiveFollowUpState(
                        identity,
                        True,
                        True,
                        blocked,
                        False,
                        True,
                    ),
                )

    def test_guarded_follow_up_binds_trusted_markdown_parser_context(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        state = MODULE.LiveFollowUpState(identity, True, True, False, False, True)
        parser_environment = {"PATH": "/usr/bin:/bin"}
        hostile_environment = {
            "PATH": "/workspace-controlled/bin",
            "NODE_OPTIONS": "--require=/workspace-controlled/preload.js",
            "NODE_PATH": "/workspace-controlled/modules",
        }

        def resolve_executable(name: str) -> str:
            self.assertEqual(name, "gh")
            return "/usr/bin/gh"

        with (
            mock.patch.dict(os.environ, hostile_environment, clear=True),
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                side_effect=resolve_executable,
            ),
            mock.patch.object(
                MODULE,
                "_resolve_trusted_markdown_node",
                return_value="/usr/bin/node",
            ),
            mock.patch.object(
                MODULE,
                "_markdown_parser_environment",
                return_value=parser_environment,
            ),
            mock.patch.object(
                MODULE.follow_up,
                "read_live_follow_up",
                return_value=state,
            ) as reader,
        ):
            observed = MODULE._read_authenticated_follow_up(
                identity,
                MODULE.InvocationBudget(10, 100, 100),
            )

        self.assertEqual(observed, state)
        self.assertEqual(reader.call_args.kwargs["node_executable"], "/usr/bin/node")
        self.assertEqual(
            reader.call_args.kwargs["parser_environment"],
            parser_environment,
        )
        self.assertNotIn("NODE_OPTIONS", parser_environment)
        self.assertNotIn("NODE_PATH", parser_environment)
        self.assertNotEqual(parser_environment["PATH"], hostile_environment["PATH"])

    def test_trusted_markdown_node_ignores_hostile_path_and_node_options(self) -> None:
        with (
            tempfile.TemporaryDirectory() as trusted_directory,
            tempfile.TemporaryDirectory() as hostile_directory,
        ):
            trusted_node = Path(trusted_directory) / "node"
            hostile_node = Path(hostile_directory) / "node"
            for executable in (trusted_node, hostile_node):
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o700)
            hostile_environment = {
                "PATH": hostile_directory,
                "NODE_OPTIONS": "--require=/workspace/preload.js",
                "NODE_PATH": "/workspace/modules",
                "NPM_CONFIG_NODE_OPTIONS": "--import=/workspace/import.mjs",
            }
            with (
                mock.patch.object(
                    MODULE.evidence,
                    "TRUSTED_COMMAND_DIRECTORIES",
                    (Path(trusted_directory),),
                ),
                mock.patch.object(
                    MODULE.evidence,
                    "TRUSTED_COMMAND_PATH",
                    trusted_directory,
                ),
                mock.patch.dict(os.environ, hostile_environment, clear=True),
            ):
                resolved = MODULE._resolve_trusted_markdown_node()
                environment = MODULE._markdown_parser_environment()

        self.assertEqual(resolved, str(trusted_node.resolve()))
        self.assertTrue(Path(resolved).is_absolute())
        self.assertEqual(environment, {"PATH": trusted_directory})
        self.assertNotIn("NODE_OPTIONS", environment)
        self.assertNotIn("NODE_PATH", environment)
        self.assertNotIn("NPM_CONFIG_NODE_OPTIONS", environment)

    def test_guarded_follow_up_fails_when_trusted_node_is_unavailable(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )

        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE,
                "_resolve_trusted_markdown_node",
                side_effect=MODULE.ResolutionError(
                    "trusted Markdown parser is unavailable"
                ),
            ),
            mock.patch.object(MODULE.follow_up, "read_live_follow_up") as reader,
            self.assertRaisesRegex(MODULE.ResolutionError, "trusted Markdown parser"),
        ):
            MODULE._read_authenticated_follow_up(
                identity,
                MODULE.InvocationBudget(10, 100, 100),
            )
        reader.assert_not_called()

    def test_live_follow_up_rejects_canonical_malformed_and_incomplete_graphs(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        key = "SecPal/api#123"
        malformed = work_graph_model.build_snapshot(
            [
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=123,
                    url=identity.issue_url,
                    parent=key,
                    has_acceptance_criteria=True,
                )
            ]
        )
        incomplete = work_graph_model.build_snapshot(
            [
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=123,
                    url=identity.issue_url,
                    children=("SecPal/api#124",),
                    has_acceptance_criteria=True,
                )
            ]
        )
        for label, snapshot in (
            ("malformed", malformed),
            ("incomplete", incomplete),
        ):
            with (
                self.subTest(label=label),
                mock.patch.object(
                    work_graph_github,
                    "load_snapshot",
                    return_value=(snapshot, key),
                ),
                self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "malformed|incomplete",
                ),
            ):
                MODULE.verify_live_follow_up(
                    identity,
                    state_reader=lambda exact: MODULE.follow_up.read_live_follow_up(
                        exact
                    ),
                )

    def test_live_follow_up_rejects_canonical_structural_malformations(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )

        def node(number: int, **overrides: Any) -> Any:
            values = {
                "repository": "SecPal/api",
                "number": number,
                "has_acceptance_criteria": True,
            }
            values.update(overrides)
            return work_graph_model.Node(**values)

        root = "SecPal/api#123"
        shared = "SecPal/api#125"
        multiple_parents = work_graph_model.build_snapshot(
            [
                node(123, url=identity.issue_url, children=("SecPal/api#124",)),
                node(124, parent=root, children=(shared, shared)),
                node(125, parent="SecPal/api#124"),
            ]
        )

        sub_issue_children = tuple(
            f"SecPal/api#{number}"
            for number in range(
                200,
                200 + work_graph_model.MAX_SUB_ISSUES_PER_PARENT + 1,
            )
        )
        sub_issue_limit = work_graph_model.build_snapshot(
            [
                node(123, url=identity.issue_url, children=sub_issue_children),
                *(
                    node(number, parent=root)
                    for number in range(
                        200,
                        200 + work_graph_model.MAX_SUB_ISSUES_PER_PARENT + 1,
                    )
                ),
            ]
        )

        depth = work_graph_model.MAX_NESTING_DEPTH + 1
        nested_nodes = [node(123, url=identity.issue_url, children=("SecPal/api#300",))]
        nested_nodes.extend(
            node(
                300 + offset,
                parent=root if offset == 0 else f"SecPal/api#{299 + offset}",
                children=(f"SecPal/api#{301 + offset}",) if offset < depth - 1 else (),
            )
            for offset in range(depth)
        )
        nesting_limit = work_graph_model.build_snapshot(nested_nodes)

        dependency_numbers = range(
            400,
            400 + work_graph_model.MAX_DEPENDENCIES_PER_TYPE + 1,
        )
        dependency_limit = work_graph_model.build_snapshot(
            [
                node(
                    123,
                    url=identity.issue_url,
                    blocked_by=tuple(f"SecPal/api#{number}" for number in dependency_numbers),
                ),
                *(node(number, state="CLOSED", state_reason="completed") for number in dependency_numbers),
            ]
        )
        dependency_cycle = work_graph_model.build_snapshot(
            [
                node(
                    123,
                    url=identity.issue_url,
                    blocked_by=("SecPal/api#124",),
                ),
                node(124, blocked_by=(root,)),
            ]
        )

        for label, snapshot in (
            ("multiple parents", multiple_parents),
            ("sub-issue limit", sub_issue_limit),
            ("nesting limit", nesting_limit),
            ("dependency limit", dependency_limit),
            ("dependency cycle", dependency_cycle),
        ):
            with (
                self.subTest(label=label),
                mock.patch.object(
                    work_graph_github,
                    "load_snapshot",
                    return_value=(snapshot, root),
                ),
                self.assertRaisesRegex(MODULE.ResolutionError, "malformed"),
            ):
                MODULE.verify_live_follow_up(
                    identity,
                    state_reader=lambda exact: MODULE.follow_up.read_live_follow_up(exact),
                )

    def test_live_follow_up_accepts_canonically_valid_blocked_issue(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        root = "SecPal/api#123"
        snapshot = work_graph_model.build_snapshot(
            [
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=123,
                    url=identity.issue_url,
                    blocked_by=("SecPal/api#124",),
                    has_acceptance_criteria=True,
                ),
                work_graph_model.Node(
                    repository="SecPal/api",
                    number=124,
                    has_acceptance_criteria=True,
                ),
            ]
        )
        with mock.patch.object(
            work_graph_github,
            "load_snapshot",
            return_value=(snapshot, root),
        ):
            state = MODULE.verify_live_follow_up(
                identity,
                state_reader=lambda exact: MODULE.follow_up.read_live_follow_up(exact),
            )
        self.assertTrue(state.blocked)
        self.assertFalse(state.malformed)
        self.assertTrue(state.graph_complete)

    def test_follow_up_traversal_and_pagination_share_invocation_budget(self) -> None:
        thread_id = "PRRT_exampleOne"
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        manifest = eligibility_payload(
            reviewed_state_payload(thread_id, []),
            (thread_id,),
        )
        manifest["eligible_threads"][0].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up=identity.to_dict(),
        )
        cases = {
            "traversal": [
                work_graph_issue_response(123, blocked_by=(124,)),
                work_graph_issue_response(124, blocked_by=(125,)),
                work_graph_issue_response(125, blocked_by=(126,)),
                work_graph_issue_response(126),
            ],
            "pagination": [
                work_graph_issue_response(123, labels_have_next_page=True),
                work_graph_page_response(
                    "labels",
                    has_next_page=True,
                    end_cursor="labels-next-2",
                ),
                work_graph_page_response(
                    "labels",
                    has_next_page=True,
                    end_cursor="labels-next-3",
                ),
                work_graph_page_response(
                    "labels",
                    has_next_page=False,
                    end_cursor=None,
                ),
            ],
        }
        for label, responses in cases.items():
            with self.subTest(label=label):
                adapter = work_graph_github.GitHubReadAdapter(max_nodes=10)
                adapter.query = mock.Mock(side_effect=responses)
                target_runner = FakeGh(
                    [
                        target_response(thread_id),
                        target_response(thread_id),
                        target_response(thread_id),
                        resolve_response(thread_id),
                    ]
                )
                live_verifier = MODULE.verify_live_follow_up

                def verifier(
                    exact: Any,
                    budget: Any,
                    adapter: Any = adapter,
                ) -> Any:
                    return live_verifier(
                        exact,
                        budget=budget,
                        state_reader=lambda expected: MODULE.follow_up.read_live_follow_up(
                            expected,
                            adapter=adapter,
                            query_consumer=MODULE._consume_api_call,
                            query_context=budget,
                        ),
                    )

                with mock.patch.object(
                    MODULE,
                    "load_repository_limits",
                    return_value=MODULE.RepositoryLimits(4, 100, 100),
                ):
                    result = resolve_threads(
                        "SecPal/api",
                        123,
                        "a" * 40,
                        (thread_id,),
                        apply=True,
                        expected_targets={
                            thread_id: expected_thread_state(thread_id)
                        },
                        eligibility_manifest=manifest,
                        follow_up_verifier=verifier,
                        runner=target_runner,
                    )

                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failed"][0]["phase"], "follow-up")
                self.assertEqual(result["resolved"], [])
                self.assertEqual(len(target_runner.calls), 1)

    def test_valid_follow_up_query_consumes_shared_invocation_budget(self) -> None:
        identity = MODULE.FollowUpIdentity(
            repository="SecPal/api",
            issue_number=123,
            issue_url="https://github.com/SecPal/api/issues/123",
        )
        adapter = work_graph_github.GitHubReadAdapter(max_nodes=10)
        adapter.query = mock.Mock(return_value=work_graph_issue_response(123))
        budget = MODULE.InvocationBudget(10, 100, 100)

        with mock.patch.object(
            work_graph_acceptance_criteria,
            "parse",
            return_value=[work_graph_acceptance_criteria.StructuralBody(True, ())],
        ):
            state = MODULE.follow_up.read_live_follow_up(
                identity,
                adapter=adapter,
                query_consumer=MODULE._consume_api_call,
                query_context=budget,
            )

        self.assertEqual(budget.api_calls, 1)
        self.assertTrue(state.open)
        self.assertTrue(state.structurally_complete)
        self.assertFalse(state.malformed)
        self.assertTrue(state.graph_complete)
        MODULE.verify_live_follow_up(identity, state_reader=lambda _exact: state)

    def test_eligibility_manifest_rejects_rehashed_binding_drift(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        manifest = eligibility_payload(payload, (thread_id,))
        cases = {
            "repository": "SecPal/frontend",
            "pull_request_number": 124,
            "reviewed_head_sha": "b" * 40,
            "reviewed_state_digest": "0" * 64,
        }
        for field, value in cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                changed = {**manifest, field: value}
                path = Path(directory) / "eligibility.json"
                path.write_text(json.dumps(changed), encoding="utf-8")

                with self.assertRaisesRegex(
                    MODULE.ResolutionError,
                    "eligibility evidence binding",
                ):
                    MODULE.load_eligibility_evidence(
                        path,
                        "SecPal/api",
                        123,
                        payload["head_sha"],
                        payload["state_digest"],
                        (thread_id,),
                        authenticated_evidence_digest=MODULE._digest_json(
                            changed
                        ),
                    )

    def test_eligibility_manifest_rejects_caller_rehashed_decision(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(thread_id, [])
        trusted = eligibility_payload(payload, (thread_id,))
        changed = copy.deepcopy(trusted)
        changed["eligible_threads"][0]["finding_ids"] = ["unaddressed-finding"]
        changed["eligible_threads"][0]["evidence_digest"] = "f" * 64

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eligibility.json"
            path.write_text(json.dumps(changed), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "eligibility evidence is not authenticated",
            ):
                MODULE.load_eligibility_evidence(
                    path,
                    "SecPal/api",
                    123,
                    payload["head_sha"],
                    payload["state_digest"],
                    (thread_id,),
                    authenticated_evidence_digest=MODULE._digest_json(trusted),
                )

    def test_nonfinite_reviewed_state_is_reported_without_traceback(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with (
                self.subTest(constant=constant),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / "reviewed.json"
                path.write_text(
                    f'{{"pull_request_number": {constant}}}',
                    encoding="utf-8",
                )
                stderr = StringIO()

                with mock.patch("sys.stderr", stderr):
                    exit_code = MODULE.main(
                        [
                            "--repo",
                            "SecPal/api",
                            "--pr",
                            "123",
                            "--repo-root",
                            ".",
                            "--expected-head",
                            "a" * 40,
                            "--reviewed-state",
                            str(path),
                            "--expected-reviewed-state-digest",
                            "c" * 64,
                            "--validation-evidence",
                            "attestation.json",
                            "--eligibility-evidence",
                            "eligibility.json",
                            "--thread-id",
                            "PRRT_exampleOne",
                        ]
                    )

                self.assertEqual(exit_code, 1)
                self.assertIn(
                    "ERROR: reviewed feedback state is unavailable or malformed",
                    stderr.getvalue(),
                )
                self.assertNotIn("Traceback", stderr.getvalue())

    def test_reviewed_state_loader_rejects_tampered_feedback(self) -> None:
        thread_id = "PRRT_exampleOne"
        payload = reviewed_state_payload(
            thread_id,
            [("PRRC_root", "reviewed body", None)],
        )
        payload["threads"][0]["comments"][0]["body_digest"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "digest is invalid",
            ):
                MODULE.load_reviewed_state(
                    path,
                    "SecPal/api",
                    123,
                    payload["state_digest"],
                    (thread_id,),
                )

    def test_head_mismatch_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, head="b" * 40)])

        with self.assertRaisesRegex(MODULE.ResolutionError, "head changed"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_head_change_after_initial_read_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(thread_id, head="a" * 40),
                target_response(thread_id, head="b" * 40),
                target_response(thread_id, head="b" * 40),
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [thread_id],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [])
        self.assertEqual(result["failed"][0]["thread_id"], thread_id)
        self.assertIn("head changed", result["failed"][0]["error"])
        self.assertEqual(len(fake.calls), 3)

    def test_missing_target_blocks_before_mutation(self) -> None:
        fake = FakeGh([{"data": {"node": None}}])

        with self.assertRaisesRegex(MODULE.ResolutionError, "does not belong"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                ["PRRT_missingThread"],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_target_from_another_pull_request_is_rejected(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, number=124)])

        with self.assertRaisesRegex(MODULE.ResolutionError, "does not belong"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )

        self.assertEqual(len(fake.calls), 1)

    def test_closed_pull_request_blocks_before_mutation(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh([target_response(thread_id, state="CLOSED")])

        with self.assertRaisesRegex(MODULE.ResolutionError, "not open"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=True,
                runner=fake,
            )
        self.assertEqual(len(fake.calls), 1)

    def test_reads_only_requested_target_nodes(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        fake = FakeGh([target_response(first), target_response(second)])

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second],
            apply=False,
            runner=fake,
        )

        self.assertEqual(result["pending"], [first, second])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn(f"threadId={first}", fake.calls[0])
        self.assertIn(f"threadId={second}", fake.calls[1])

    def test_comment_budget_is_shared_across_target_reads(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=[
                        ("PRRC_one", "one", None),
                        ("PRRC_two", "two", None),
                        ("PRRC_three", "three", None),
                    ],
                )
            ]
        )
        limits = mock.Mock(
            maximum_api_calls=20,
            maximum_threads=20,
            maximum_comments=2,
        )

        with (
            mock.patch.object(
                MODULE,
                "load_repository_limits",
                return_value=limits,
            ),
            self.assertRaisesRegex(MODULE.ResolutionError, "comment limit"),
        ):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
                reviewed_comments={
                    thread_id: [
                        ("PRRC_one", "one", None),
                        ("PRRC_two", "two", None),
                        ("PRRC_three", "three", None),
                    ],
                },
            )

    def test_repeated_comment_identity_across_pages_fails_closed(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=[("PRRC_repeated", "first", None)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
                target_response(
                    thread_id,
                    comments=[("PRRC_repeated", "second", None)],
                ),
            ]
        )

        with self.assertRaisesRegex(MODULE.ResolutionError, "repeated comment"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
            )

    def test_repeated_comment_cursor_fails_closed(self) -> None:
        thread_id = "PRRT_exampleOne"
        fake = FakeGh(
            [
                target_response(
                    thread_id,
                    comments=[("PRRC_one", "one", None)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
                target_response(
                    thread_id,
                    comments=[("PRRC_two", "two", None)],
                    has_next_page=True,
                    end_cursor="cursor-1",
                ),
            ]
        )

        with self.assertRaisesRegex(MODULE.ResolutionError, "did not advance"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
            )

    def test_missing_page_info_fails_closed_even_when_target_is_found(self) -> None:
        thread_id = "PRRT_exampleOne"
        response = target_response(thread_id)
        del response["data"]["node"]["comments"]["pageInfo"]
        fake = FakeGh([response])

        with self.assertRaisesRegex(MODULE.ResolutionError, "pagination is missing"):
            resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [thread_id],
                apply=False,
                runner=fake,
            )

    def test_partial_failure_reports_applied_failed_and_unattempted(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        third = "PRRT_exampleThree"
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(third),
                target_response(first),
                target_response(first),
                resolve_response(first),
                target_response(second),
                target_response(second),
                {"errors": [{"message": "mutation failed"}]},
            ]
        )

        result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            [first, second, third],
            apply=True,
            runner=fake,
        )

        self.assertEqual(result["resolved"], [first])
        self.assertEqual(
            result["failed"],
            [
                {
                    "thread_id": second,
                    "phase": "mutation",
                    "write_result": "unknown",
                    "error": "GitHub GraphQL request failed",
                }
            ],
        )
        self.assertEqual(result["unattempted"], [third])
        self.assertEqual(result["status"], "failed")

    def test_partial_batch_reinvocation_authenticates_resolved_prefix(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        eligibility = eligibility_payload(
            reviewed_state_payload(first, []),
            (first, second),
        )
        eligibility["eligible_threads"][1].update(
            classification="INVALID_FALSE_OR_MISLEADING",
            disposition="DISPROVEN_WITH_EVIDENCE",
        )
        partial = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(first),
                target_response(first),
                resolve_response(first),
                target_response(second),
                target_response(second, head="c" * 40),
            ]
        )

        first_result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (first, second),
            apply=True,
            eligibility_manifest=eligibility,
            runner=partial,
        )

        self.assertEqual(first_result["status"], "failed")
        self.assertEqual(first_result["resolved"], [first])
        self.assertEqual(first_result["failed"][0]["thread_id"], second)
        self.assertEqual(first_result["failed"][0]["phase"], "recheck")
        self.assertEqual(first_result["failed"][0]["write_result"], "not_attempted")

        repeated = FakeGh(
            [
                target_response(first, resolved=True),
                target_response(second),
                target_response(first, resolved=True),
                target_response(first, resolved=True),
                target_response(second),
                target_response(second),
                resolve_response(second),
            ]
        )

        repeated_result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (first, second),
            apply=True,
            eligibility_manifest=eligibility,
            runner=repeated,
        )

        self.assertEqual(repeated_result["status"], "success")
        self.assertEqual(repeated_result["already_resolved"], [first])
        self.assertEqual(repeated_result["resolved"], [second])
        self.assertEqual(len(repeated.calls), 7)
        self.assertEqual(
            sum(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in repeated.calls
            ),
            1,
        )

        duplicate = FakeGh(
            [
                target_response(first, resolved=True),
                target_response(second, resolved=True),
                target_response(first, resolved=True),
                target_response(first, resolved=True),
                target_response(second, resolved=True),
                target_response(second, resolved=True),
            ]
        )

        duplicate_result = resolve_threads(
            "SecPal/api",
            123,
            "a" * 40,
            (first, second),
            apply=True,
            eligibility_manifest=eligibility,
            runner=duplicate,
        )

        self.assertEqual(duplicate_result["status"], "success")
        self.assertEqual(duplicate_result["already_resolved"], [first, second])
        self.assertEqual(duplicate_result["resolved"], [])
        self.assertFalse(
            any(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in duplicate.calls
            )
        )

    def test_follow_up_operational_error_uses_structured_partial_failure(
        self,
    ) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        third = "PRRT_exampleThree"
        manifest = eligibility_payload(
            reviewed_state_payload(first, []),
            (first, second, third),
        )
        manifest["eligible_threads"][1].update(
            classification="OUTSIDE_PR_SCOPE",
            disposition="TRACKED_AS_FOLLOW_UP",
            follow_up={
                "repository": "SecPal/api",
                "issue_number": 123,
                "issue_url": "https://github.com/SecPal/api/issues/123",
            },
        )
        fake = FakeGh(
            [
                target_response(first),
                target_response(second),
                target_response(third),
                target_response(first),
                target_response(first),
                resolve_response(first),
            ]
        )

        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE,
                "_resolve_trusted_markdown_node",
                return_value="/usr/bin/node",
            ),
            mock.patch.object(
                work_graph_github,
                "load_snapshot",
                side_effect=TypeError("malformed canonical adapter response"),
            ),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                (first, second, third),
                apply=True,
                expected_targets={
                    first: expected_thread_state(first),
                    second: expected_thread_state(second),
                    third: expected_thread_state(third),
                },
                eligibility_manifest=manifest,
                runner=fake,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["resolved"], [first])
        self.assertEqual(
            result["failed"],
            [
                {
                    "thread_id": second,
                    "phase": "follow-up",
                    "write_result": "not_attempted",
                    "error": "follow-up issue could not be read safely",
                }
            ],
        )
        self.assertEqual(result["unattempted"], [third])
        self.assertEqual(
            sum(
                f"query={MODULE.RESOLVE_MUTATION}" in call
                for call in fake.calls
            ),
            1,
        )

    def test_main_emits_partial_report_and_returns_nonzero(self) -> None:
        report = {
            "repository": "SecPal/api",
            "pull_request_number": 123,
            "head_sha": "a" * 40,
            "mode": "apply",
            "status": "failed",
            "already_resolved": [],
            "pending": [],
            "resolved": ["PRRT_exampleOne"],
            "failed": [
                {
                    "thread_id": "PRRT_exampleTwo",
                    "error": "GitHub GraphQL request failed",
                }
            ],
            "unattempted": [],
        }
        output = StringIO()
        reviewed = MODULE.ReviewedState(
            head_sha="a" * 40,
            state_digest="c" * 64,
            feedback_digest="e" * 64,
            targets={
                "PRRT_exampleOne": expected_thread_state("PRRT_exampleOne"),
            },
            thread_ids=frozenset({"PRRT_exampleOne"}),
        )
        with (
            mock.patch.object(MODULE, "resolve_threads", return_value=report) as resolver,
            redirect_stdout(output),
        ):
            returncode = MODULE.main(
                [
                    "--repo",
                    "SecPal/api",
                    "--pr",
                    "123",
                    "--repo-root",
                    ".",
                    "--expected-head",
                    "a" * 40,
                    "--reviewed-state",
                    "reviewed.json",
                    "--expected-reviewed-state-digest",
                    "c" * 64,
                    "--validation-evidence",
                    "attestation.json",
                    "--eligibility-evidence",
                    "eligibility.json",
                    "--thread-id",
                    "PRRT_exampleOne",
                ]
            )

        self.assertEqual(returncode, 1)
        self.assertEqual(json.loads(output.getvalue()), report)
        resolver.assert_called_once_with(
            "SecPal/api",
            123,
            "a" * 40,
            ("PRRT_exampleOne",),
            apply=False,
            repository_root=".",
            reviewed_state_path="reviewed.json",
            expected_reviewed_state_digest="c" * 64,
            validation_evidence_path="attestation.json",
            eligibility_evidence_path="eligibility.json",
        )

    def test_run_gh_uses_trusted_absolute_executable_and_environment(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr="",
        )
        trusted_environment = {
            "PATH": "/usr/bin:/bin",
            "GH_HOST": "github.com",
            "GH_PAGER": "cat",
        }
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value=trusted_environment,
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            arguments = [
                *MODULE.GH_GRAPHQL_PREFIX,
                "-f",
                f"query={MODULE.TARGET_QUERY}",
            ]
            self.assertEqual(MODULE._run_gh(arguments), {})

        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/gh", *arguments],
        )
        self.assertEqual(run.call_args.kwargs["env"], trusted_environment)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_graphql_explicitly_pins_github_host(self) -> None:
        fake = FakeGh([{"data": {}}])
        budget = MODULE.InvocationBudget(
            maximum_api_calls=1,
            maximum_threads=1,
            maximum_comments=1,
        )

        self.assertEqual(MODULE._graphql(MODULE.TARGET_QUERY, {}, fake, budget), {})

        self.assertEqual(
            fake.calls[0][:4],
            ["api", "--hostname", "github.com", "graphql"],
        )

    def test_graphql_rejects_documents_outside_the_allowlist(self) -> None:
        fake = FakeGh([])
        budget = MODULE.InvocationBudget(
            maximum_api_calls=1,
            maximum_threads=1,
            maximum_comments=1,
        )

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "outside the GraphQL document allowlist",
        ):
            MODULE._graphql("mutation { mergePullRequest }", {}, fake, budget)

        self.assertEqual(fake.calls, [])
        self.assertEqual(budget.api_calls, 0)

    def test_run_gh_rejects_commands_outside_pinned_graphql_surface(self) -> None:
        with mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "outside the allowed GraphQL surface",
            ):
                MODULE._run_gh(["pr", "merge", "591"])

        run.assert_not_called()

    def test_run_gh_rejects_unapproved_graphql_documents(self) -> None:
        with mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "outside the GraphQL document allowlist",
            ):
                MODULE._run_gh(
                    [
                        *MODULE.GH_GRAPHQL_PREFIX,
                        "-f",
                        "query=mutation { mergePullRequest }",
                    ]
                )

        run.assert_not_called()

    def test_run_gh_translates_process_launch_failure(self) -> None:
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value={"PATH": "/usr/bin:/bin"},
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                side_effect=OSError("executable disappeared"),
            ),
        ):
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "process launch failed",
            ):
                MODULE._run_gh(
                    [
                        *MODULE.GH_GRAPHQL_PREFIX,
                        "-f",
                        f"query={MODULE.TARGET_QUERY}",
                    ]
                )

    def test_run_gh_redacts_failure_diagnostic(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="token=supersecret",
        )
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value={"PATH": "/usr/bin:/bin"},
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=completed,
            ),
        ):
            with self.assertRaises(MODULE.ResolutionError) as raised:
                MODULE._run_gh(
                    [
                        *MODULE.GH_GRAPHQL_PREFIX,
                        "-f",
                        f"query={MODULE.TARGET_QUERY}",
                    ]
                )

        self.assertIn("[REDACTED]", str(raised.exception))
        self.assertNotIn("supersecret", str(raised.exception))

    def test_process_launch_failure_after_resolution_preserves_report(self) -> None:
        first = "PRRT_exampleOne"
        second = "PRRT_exampleTwo"
        third = "PRRT_exampleThree"

        def completed(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )

        process_results: list[object] = [
            completed(target_response(first)),
            completed(target_response(second)),
            completed(target_response(third)),
            completed(target_response(first)),
            completed(target_response(first)),
            completed(resolve_response(first)),
            OSError("executable disappeared"),
        ]
        with (
            mock.patch.object(
                MODULE.evidence,
                "resolve_trusted_executable",
                return_value="/usr/bin/gh",
            ),
            mock.patch.object(
                MODULE.evidence,
                "command_environment",
                return_value={"PATH": "/usr/bin:/bin"},
            ),
            mock.patch.object(
                MODULE.subprocess,
                "run",
                side_effect=process_results,
            ),
        ):
            result = resolve_threads(
                "SecPal/api",
                123,
                "a" * 40,
                [first, second, third],
                apply=True,
            )

        self.assertEqual(result["resolved"], [first])
        self.assertEqual(result["failed"][0]["thread_id"], second)
        self.assertEqual(result["failed"][0]["phase"], "recheck")
        self.assertEqual(result["failed"][0]["write_result"], "not_attempted")
        self.assertEqual(result["unattempted"], [third])
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    main()
