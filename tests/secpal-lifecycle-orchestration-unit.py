#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for finite delivery-lifecycle orchestration."""

from __future__ import annotations

import copy
import base64
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.secpal_pr_review import lifecycle_authority as authority
from scripts.secpal_pr_review import fast_path
from scripts.secpal_pr_review import lifecycle_orchestration as orchestration
from scripts.secpal_pr_review import lifecycle_publication as publication
from scripts.secpal_pr_review import late_disposition

REPOSITORY = "SecPal/.github"
ISSUE = 692
PR = 800
REPLACEMENT_PR = 801
HEAD = "a" * 40
NEXT_HEAD = "b" * 40
LIFECYCLE = "lifecycle:" + "c" * 64
PR_905_CORRECTION_AUTHORITY = {
    "reanchor_evidence_digest": "7" * 64,
    "material_finding_ids": [
        "PRRC_kwDOQFR1MM7td5Q8",
        "PRRC_kwDOQFR1MM7td5Rp",
        "PRRC_kwDOQFR1MM7td5SC",
        "PRRC_kwDOQFR1MM7td5Sd",
    ],
    "finding_source_digest": (
        "01b49bf34ee28ea224dfd7f73f690ac95867c429dcc2f6b1242652370e476e62"
    ),
}


def current_lifecycle(
    *,
    ready: bool = True,
    ready_regressed: bool = False,
    exceptional_recoveries: int = 0,
    exceptional_continuations: int = 0,
    head_sha: str = HEAD,
    remediation_cycles: int = 2,
    pull_request: int = PR,
    delivery_issue: int = ISSUE,
    lifecycle_id: str = LIFECYCLE,
) -> authority.VerifiedLifecycleAuthority:
    state = authority.initial_state()
    state.update(
        {
            "unrestricted_review_count": 1,
            "remediation_cycle_count": remediation_cycles,
            "draft": not ready,
            "ready": ready,
            "ready_transition_count": 1 if ready or ready_regressed else 0,
            "ready_history": (
                [
                    {
                        "sequence": 1,
                        "transition_kind": "DRAFT_TO_READY",
                        "event_authorization_digest": "d" * 64,
                    }
                ]
                if ready or ready_regressed
                else []
            ),
            "exceptional_recovery_count": exceptional_recoveries,
            "exceptional_recovery_history": [
                {
                    "sequence": 1,
                    "transition_kind": "EXCEPTIONAL_RECOVERY",
                    "event_authorization_digest": "9" * 64,
                }
            ][:exceptional_recoveries],
            "exceptional_continuation_count": exceptional_continuations,
            "exceptional_continuation_history": [
                {
                    "sequence": 1,
                    "transition_kind": "EXCEPTIONAL_CONTINUATION",
                    "event_authorization_digest": "8" * 64,
                }
            ][:exceptional_continuations],
        }
    )
    if ready_regressed:
        state["ready_history"].append(
            {
                "sequence": 2,
                "transition_kind": "READY_TO_DRAFT",
                "event_authorization_digest": "7" * 64,
            }
        )
    return authority.VerifiedLifecycleAuthority(
        authority_digest="e" * 64,
        repository=REPOSITORY,
        delivery_issue=delivery_issue,
        lifecycle_id=lifecycle_id,
        initialization_evidence_digest="f" * 64,
        pull_request=pull_request,
        head_sha=head_sha,
        state=state,
        authority_signer_identity="aroviqen@secpal.app",
    )


def current_reader(lifecycle: authority.VerifiedLifecycleAuthority):
    def read(repository: str, delivery_issue: int):
        if (repository, delivery_issue) != (REPOSITORY, ISSUE):
            raise AssertionError("unexpected lifecycle selection")
        return SimpleNamespace(
            publication_oid="1" * 40,
            publication_digest="2" * 64,
            lifecycle=copy.deepcopy(lifecycle),
        )

    return read


def fixture_authorization_digest(authorization_id: str) -> str:
    return authority.digest_json({"authorization_id": authorization_id})


def fixture_event_id(authorization_id: str) -> str:
    return "authorization:" + fixture_authorization_digest(authorization_id)


def fixture_authorization_verifier(value, _observed, _lifecycle):
    if not isinstance(value, dict):
        raise orchestration.LifecycleOrchestrationError(
            "user authorization requires canonical signed evidence"
        )
    item = copy.deepcopy(value)
    item["authorization_digest"] = fixture_authorization_digest(
        item["authorization_id"]
    )
    return item


def continuation_inputs() -> tuple[dict[str, object], dict[str, object]]:
    reviewed = fast_path.StableFeedbackState(
        repository=REPOSITORY,
        pull_request_number=PR,
        head_sha=HEAD,
        base_ref="main",
        base_sha="0" * 40,
        pr_state="OPEN",
        feedback={
            "pull_request_reactions": [],
            "reviews": [],
            "conversation_comments": [],
            "threads": [
                {
                    "node_id": "PRRT_CONTINUATION_1",
                    "is_resolved": False,
                    "is_outdated": True,
                    "comments": [
                        {
                            "node_id": "F-CONTINUATION-1",
                            "body_digest": "1" * 64,
                            "actor": {
                                "login": "reviewer",
                                "node_id": "ACTOR_1",
                                "database_id": 1,
                            },
                            "reply_to_id": None,
                            "reactions": [],
                        }
                    ],
                }
            ],
        },
    )
    eligibility = {
        "schema_version": "1.1",
        "repository": REPOSITORY,
        "pull_request_number": PR,
        "reviewed_head_sha": HEAD,
        "reviewed_state_digest": reviewed.state_digest,
        "eligible_threads": [
            {
                "thread_id": "PRRT_CONTINUATION_1",
                "classification": "VALID_ACTIONABLE",
                "disposition": "CORRECTED_AND_VERIFIED",
                "finding_ids": ["F-CONTINUATION-1"],
                "evidence_digest": "4" * 64,
                "follow_up": None,
            }
        ],
    }
    authorization = {
        "authorization_id": "user-continuation-1",
        "operation": "EXCEPTIONAL_CONTINUATION",
        "reason": "Correct one exact authenticated post-Recovery finding",
        "scope": {
            "pull_request": PR,
            "predecessor_head_sha": HEAD,
            "resulting_head_sha": NEXT_HEAD,
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "eligibility_evidence_digest": fast_path.digest_json(eligibility),
            "finding_ids": ["F-CONTINUATION-1"],
            "thread_ids": ["PRRT_CONTINUATION_1"],
        },
        "bounded_uses": 1,
    }
    request = {
        "event_kind": "CONTINUATION_COMMIT_PUSHED",
        "event_id": fixture_event_id("user-continuation-1"),
        "pull_request": PR,
        "head_sha": NEXT_HEAD,
        "replacement_pull_request": None,
        "classification": None,
        "follow_up": None,
        "authorization": authorization,
        "continuation_evidence": {
            "reviewed_state_evidence": reviewed.to_dict(),
            "eligibility_evidence": eligibility,
        },
    }
    return request, authorization


def feedback_successor(
    reviewed: fast_path.StableFeedbackState,
) -> fast_path.StableFeedbackState:
    feedback = copy.deepcopy(reviewed.feedback)
    for thread in feedback["threads"]:
        thread["is_outdated"] = True
    return fast_path.StableFeedbackState(
        repository=reviewed.repository,
        pull_request_number=reviewed.pull_request_number,
        head_sha=NEXT_HEAD,
        base_ref=reviewed.base_ref,
        base_sha=reviewed.base_sha,
        pr_state="OPEN",
        feedback=feedback,
    )


def authenticated_provider_growth(
    *,
    delivery_issue: int = ISSUE,
    pull_request: int = PR,
    predecessor_head_sha: str = HEAD,
    resulting_head_sha: str = NEXT_HEAD,
    base_sha: str = "0" * 40,
) -> tuple[
    fast_path.StableFeedbackState,
    fast_path.StableFeedbackState,
    dict[str, object],
]:
    provider = {
        "login": "chatgpt-codex-connector",
        "node_id": "BOT_CODEX",
        "database_id": 199175422,
    }
    requester = {
        "login": "delivery-user",
        "node_id": "USER_DELIVERY",
        "database_id": 7,
    }
    reviewer = {
        "login": "reviewer",
        "node_id": "USER_REVIEWER",
        "database_id": 8,
    }
    code_quality = {
        "login": "github-code-quality",
        "node_id": "BOT_CODE_QUALITY",
        "database_id": 223894421,
    }
    predecessor = fast_path.StableFeedbackState(
        repository=REPOSITORY,
        pull_request_number=pull_request,
        head_sha=predecessor_head_sha,
        base_ref="main",
        base_sha=base_sha,
        pr_state="OPEN",
        feedback={
            "pull_request_reactions": [],
            "reviews": [
                {
                    "node_id": "PRR_PREDECESSOR",
                    "body_digest": "1" * 64,
                    "actor": reviewer,
                    "state": "COMMENTED",
                    "commit_oid": predecessor_head_sha,
                    "reactions": [],
                }
            ],
            "conversation_comments": [
                {
                    "node_id": "IC_CODEX_SUMMARY",
                    "body_digest": "2" * 64,
                    "actor": provider,
                    "updated_at": "2026-09-08T20:00:00Z",
                    "reactions": [],
                }
            ],
            "threads": [
                {
                    "node_id": "PRRT_CONTINUATION_1",
                    "is_resolved": False,
                    "is_outdated": False,
                    "comments": [
                        {
                            "node_id": "F-CONTINUATION-1",
                            "body_digest": "3" * 64,
                            "actor": reviewer,
                            "reply_to_id": None,
                            "reactions": [
                                {
                                    "mutation_id": "REACTION_PREDECESSOR",
                                    "content": "THUMBS_UP",
                                    "actor": requester,
                                }
                            ],
                        },
                        {
                            "node_id": "PRRC_PREDECESSOR_REPLY",
                            "body_digest": "4" * 64,
                            "actor": requester,
                            "reply_to_id": "F-CONTINUATION-1",
                            "reactions": [],
                        },
                    ],
                }
            ],
        },
    )
    summary = (
        "<!-- codex-pull-request-review-summary -->\n"
        '<!-- codex-security-review:v1 '
        f'{{"headSha":"{resulting_head_sha}","status":"completed"}} -->\n'
        "| Review | Status | Commit | Review trigger |\n"
        "| --- | --- | --- | --- |\n"
        "| **Code Review** | **Completed** | head | manual |\n"
        "| **Security Review** | **Completed** | head | manual |"
    )
    current_feedback = copy.deepcopy(predecessor.feedback)
    current_feedback["pull_request_reactions"].append(
        {
            "mutation_id": "REACTION_CODEX_COMPLETE",
            "content": "THUMBS_UP",
            "actor": provider,
        }
    )
    current_feedback["conversation_comments"][0].update(
        body_digest=fast_path.digest_text(summary),
        updated_at="2026-09-08T22:00:00Z",
    )
    bodies = {
        "IC_CODE_REQUEST": "@codex review",
        "IC_SECURITY_REQUEST": "@codex security review",
        "IC_CODE_RESULT": (
            "Codex Review: Didn't find any major issues.\n\n"
            f"**Reviewed commit:** `{resulting_head_sha[:10]}`"
        ),
        "IC_SECURITY_RESULT": (
            "### 🛡️ Codex Security Review\n\n"
            "No security issues were found in this pull request.\n\n"
            f"**Reviewed commit:** `{resulting_head_sha[:10]}`"
        ),
    }
    for node_id, body in bodies.items():
        current_feedback["conversation_comments"].append(
            {
                "node_id": node_id,
                "body_digest": fast_path.digest_text(body),
                "actor": requester if "REQUEST" in node_id else provider,
                "updated_at": None,
                "reactions": [],
            }
        )
    current_feedback["reviews"].append(
        {
            "node_id": "PRR_RESULTING_HEAD",
            "body_digest": fast_path.digest_text(""),
            "actor": code_quality,
            "state": "COMMENTED",
            "commit_oid": resulting_head_sha,
            "reactions": [],
        }
    )
    current_feedback["threads"].append(
        {
            "node_id": "PRRT_RESULTING_HEAD",
            "is_resolved": False,
            "is_outdated": False,
            "comments": [
                {
                    "node_id": "PRRC_RESULTING_HEAD",
                    "body_digest": "a" * 64,
                    "actor": code_quality,
                    "reply_to_id": None,
                    "reactions": [],
                }
            ],
        }
    )
    current = fast_path.StableFeedbackState(
        repository=REPOSITORY,
        pull_request_number=pull_request,
        head_sha=resulting_head_sha,
        base_ref=predecessor.base_ref,
        base_sha=predecessor.base_sha,
        pr_state="OPEN",
        feedback=current_feedback,
    )
    transport = [
        ("CODEX_SUMMARY_UPDATE", "IC_CODEX_SUMMARY", summary),
        ("CODEX_REVIEW_REQUEST", "IC_CODE_REQUEST", bodies["IC_CODE_REQUEST"]),
        (
            "CODEX_SECURITY_REVIEW_REQUEST",
            "IC_SECURITY_REQUEST",
            bodies["IC_SECURITY_REQUEST"],
        ),
        (
            "CODEX_CODE_REVIEW_RESULT",
            "IC_CODE_RESULT",
            bodies["IC_CODE_RESULT"],
        ),
        (
            "CODEX_SECURITY_REVIEW_RESULT",
            "IC_SECURITY_RESULT",
            bodies["IC_SECURITY_RESULT"],
        ),
    ]
    classification = fast_path._seal_successor_classification(
        repository=REPOSITORY,
        delivery_issue_number=delivery_issue,
        pull_request_number=pull_request,
        head_sha=resulting_head_sha,
        finding_id="PRRC_RESULTING_HEAD",
        finding_evidence_digest="b" * 64,
        thread_id="PRRT_RESULTING_HEAD",
        top_level_comment_node_id="PRRC_RESULTING_HEAD",
        finding_body_digest="a" * 64,
        reply_count=0,
        is_resolved=False,
        is_outdated=False,
        classification="INVALID_FALSE_OR_MISLEADING",
        disposition="DISPROVEN_WITH_EVIDENCE",
        technically_blocking=False,
        technical_blockers=(),
        classification_evidence_digest="c" * 64,
        source_bindings=(("THREAD_COMMENT", "PRRC_RESULTING_HEAD", "a" * 64, "PRRT_RESULTING_HEAD"),),
    )
    evidence: dict[str, object] = {
        "schema_version": "1.0",
        "repository": REPOSITORY,
        "pull_request_number": pull_request,
        "predecessor_state_digest": predecessor.state_digest,
        "resulting_head_sha": resulting_head_sha,
        "resulting_state_digest": current.state_digest,
        "provider_transport": [
            {
                "role": role,
                "kind": "CONVERSATION_COMMENT",
                "node_id": node_id,
                "body": body,
            }
            for role, node_id, body in transport
        ]
        + [
            {
                "role": "CODEX_COMPLETION_REACTION",
                "kind": "PULL_REQUEST_REACTION",
                "node_id": "REACTION_CODEX_COMPLETE",
                "body": None,
            },
            {
                "role": "GITHUB_CODE_QUALITY_REVIEW",
                "kind": "REVIEW",
                "node_id": "PRR_RESULTING_HEAD",
                "body": None,
            }
        ],
        "successor_findings": [
            {
                "sources": [
                    {
                        "kind": "THREAD_COMMENT",
                        "node_id": "PRRC_RESULTING_HEAD",
                        "digest": "a" * 64,
                    }
                ],
                "classification_evidence": classification,
            }
        ],
    }
    return predecessor, current, evidence


def authenticated_provider_reaction_replacement() -> tuple[
    fast_path.StableFeedbackState,
    fast_path.StableFeedbackState,
    dict[str, object],
]:
    current_head = "46d09efb237f3e8c2e1f1066ba2b840a018ef889"
    rejected_head = "be511e420933eeffb289188f3620677bc7cb9f84"
    reviewed, current, evidence = authenticated_provider_growth(
        delivery_issue=894,
        pull_request=901,
        predecessor_head_sha=current_head,
        resulting_head_sha=rejected_head,
        base_sha="aa7d9e4485abbceed01136cd81fdbbd353f877bc",
    )
    reviewed.feedback["pull_request_reactions"].append(
        {
            "mutation_id": "REACTION_CODEX_PREDECESSOR_COMPLETE",
            "content": "THUMBS_UP",
            "actor": {
                "login": "chatgpt-codex-connector[bot]",
                "node_id": "BOT_CODEX",
                "database_id": 199175422,
            },
        }
    )
    current.feedback["pull_request_reactions"][0]["mutation_id"] = (
        "REA_lAHOQFR1MM8AAAABQu3eG84d1ZDA"
    )
    current.feedback["pull_request_reactions"][0]["actor"]["login"] = (
        "chatgpt-codex-connector[bot]"
    )
    completion_transport = next(
        item
        for item in evidence["provider_transport"]
        if item["role"] == "CODEX_COMPLETION_REACTION"
    )
    completion_transport["node_id"] = "REA_lAHOQFR1MM8AAAABQu3eG84d1ZDA"
    reviewed.refresh_digests()
    current.refresh_digests()
    safe = evidence["successor_findings"][0]["classification_evidence"]
    evidence["successor_findings"][0]["classification_evidence"] = (
        fast_path._seal_successor_classification(
            **{
                key: value
                for key, value in safe.__dict__.items()
                if key != "_verification_seal"
            }
            | {
                "classification": "IN_CONTRACT_DEFECT",
                "disposition": "CANDIDATE_REJECTED_BEFORE_PUBLICATION",
                "technically_blocking": True,
                "technical_blockers": ("P2",),
            }
        )
    )
    evidence["schema_version"] = "1.2"
    evidence["predecessor_state_digest"] = reviewed.state_digest
    evidence["resulting_state_digest"] = current.state_digest
    evidence["provider_completion_reaction_replacement"] = {
        "provider_login": "chatgpt-codex-connector",
        "reaction_content": "THUMBS_UP",
        "removed_reaction_id": "REACTION_CODEX_PREDECESSOR_COMPLETE",
        "replacement_reaction_id": "REA_lAHOQFR1MM8AAAABQu3eG84d1ZDA",
    }
    return reviewed, current, evidence


def authenticated_pr_905_classified_codex_review() -> tuple[
    fast_path.StableFeedbackState,
    fast_path.StableFeedbackState,
    dict[str, object],
]:
    """Reproduce the exact-head provider shape observed on PR #905."""

    predecessor_head = "46d09efb237f3e8c2e1f1066ba2b840a018ef889"
    resulting_head = "18a6d02d8c548a4a010fc93c5f8d09d89427f1b2"
    reviewed, _unused, _unused_evidence = authenticated_provider_growth(
        delivery_issue=894,
        pull_request=905,
        predecessor_head_sha=predecessor_head,
        resulting_head_sha=resulting_head,
        base_sha="da7d5f19a1ff4e65bfdbe7ad0a66e13f6172ada9",
    )
    copilot = {
        "login": "copilot-pull-request-reviewer",
        "node_id": "BOT_kgDOCnlnWA",
        "database_id": 175728472,
    }
    provider = {
        "login": "chatgpt-codex-connector",
        "node_id": "BOT_kgDOC98s_g",
        "database_id": 199175422,
    }
    requester = {
        "login": "aroviqen",
        "node_id": "U_kgDOD9_SfQ",
        "database_id": 266326653,
    }
    predecessor_summary = (
        "<!-- codex-pull-request-review-summary -->\n"
        '<!-- codex-security-review:v1 {"blockingSeverityThreshold":"P0",'
        f'"headSha":"{predecessor_head}","mergeGateEnabled":false,'
        '"pullRequestNumber":905,"repository":"SecPal/.github",'
        '"status":"completed"} -->\n'
        "## Codex Review Summary\n\n"
        "This comment shows the latest Codex review activity on this pull request.\n\n"
        "| Review | Status | Commit | Review trigger |\n"
        "| --- | --- | --- | --- |\n"
        "| 📝 **Code Review** | ✅ **Completed** "
        '<relative-time datetime="2026-09-11T09:02:46.182651Z">'
        "2026-09-11T09:02:46.182651Z</relative-time> | `46d09ef` | PR opened |\n"
        "| 🔒 **Security Review** | ✅ **Completed** "
        '<relative-time datetime="2026-09-11T09:05:44.125661Z">'
        "2026-09-11T09:05:44.125661Z</relative-time> | `46d09ef` | PR opened |\n"
        "\n\n\n<details> <summary>ℹ️ About Codex in GitHub</summary>\n<br/>\n\n"
        "[Your team has set up Codex to review pull requests in this repo]"
        "(https://chatgpt.com/codex/cloud/settings/general). Reviews are triggered when you\n"
        "- Open a pull request for review\n"
        "- Mark a draft as ready\n"
        '- Comment "@codex review" or "@codex security review".\n\n'
        "Codex reacts with 👀 while any review is running, comments if it has suggestions, "
        "and reacts with 👍 once all reviews finish with no findings.\n\n</details>"
    )
    reviewed.feedback = {
        "pull_request_reactions": [
            {
                "mutation_id": "REA_lAHOQFR1MM8AAAABQzMEUc4d1oLF",
                "content": "THUMBS_UP",
                "actor": {
                    "login": "chatgpt-codex-connector[bot]",
                    "node_id": "BOT_kgDOC98s_g",
                    "database_id": 199175422,
                },
            }
        ],
        "reviews": [],
        "conversation_comments": [
            {
                "node_id": "IC_kwDOQFR1MM8AAAABT7Fdrg",
                "body_digest": fast_path.digest_text(predecessor_summary),
                "actor": provider,
                "updated_at": "2026-09-11T09:05:45Z",
                "reactions": [],
            }
        ],
        "threads": [],
    }
    reviewed.refresh_digests()
    assert reviewed.state_digest == (
        "d76acca37ab79269f3ed7d36394696831e16be4160f88081c6a552d6ed6b6d3a"
    )
    summary = (
        "<!-- codex-pull-request-review-summary -->\n"
        '<!-- codex-security-review:v1 {"blockingSeverityThreshold":"P0",'
        f'"headSha":"{resulting_head}","mergeGateEnabled":false,'
        '"pullRequestNumber":905,"repository":"SecPal/.github",'
        '"status":"completed"} -->\n'
        "## Codex Review Summary\n\n"
        "This comment shows the latest Codex review activity on this pull request.\n\n"
        "| Review | Status | Commit | Review trigger |\n"
        "| --- | --- | --- | --- |\n"
        "| 📝 **Code Review** | ✅ **Completed** "
        '<relative-time datetime="2026-09-11T17:41:54.104406Z">'
        "2026-09-11T17:41:54.104406Z</relative-time> | `18a6d02` | Manual request |\n"
        "| 🔒 **Security Review** | ✅ **Completed** "
        '<relative-time datetime="2026-09-11T17:45:06.295720Z">'
        "2026-09-11T17:45:06.295720Z</relative-time> | `18a6d02` | Manual request |\n"
        "\n\n\n<details> <summary>ℹ️ About Codex in GitHub</summary>\n<br/>\n\n"
        "[Your team has set up Codex to review pull requests in this repo]"
        "(https://chatgpt.com/codex/cloud/settings/general). Reviews are triggered when you\n"
        "- Open a pull request for review\n"
        "- Mark a draft as ready\n"
        '- Comment "@codex review" or "@codex security review".\n\n'
        "Codex reacts with 👀 while any review is running, comments if it has suggestions, "
        "and reacts with 👍 once all reviews finish with no findings.\n\n</details>"
    )
    code_review = (
        "\n### 💡 Codex Review\n\n"
        "Here are some automated review suggestions for this pull request.\n\n"
        "**Reviewed commit:** `18a6d02d8c`\n    \n\n"
        "<details> <summary>ℹ️ About Codex in GitHub</summary>\n<br/>\n\n"
        "[Your team has set up Codex to review pull requests in this repo]"
        "(https://chatgpt.com/codex/cloud/settings/general). Reviews are triggered when you\n"
        "- Open a pull request for review\n"
        "- Mark a draft as ready\n"
        '- Comment "@codex review".\n\n'
        "If Codex has suggestions, it will comment; otherwise it will react with 👍.\n\n\n\n\n"
        'Codex can also answer questions or update the PR. Try commenting "@codex '
        'address that feedback".\n            \n</details>'
    )
    copilot_review = (
        "### 🟡 Changes recommended\n\n"
        "Unresolved critical and moderate security, validation, source-authentication, "
        "and resource-boundary findings remain.\n\n"
        "*Once you've addressed the issues Copilot identified, you can request another "
        "Copilot review.*\n\n"
        "<details>\n<summary>Pull request overview</summary>\n\n"
        "Adds authenticated evidence-version collision handling for Exceptional "
        "Continuation.\n\n"
        "**Changes:**\n"
        "- Adds collision detection and byte-only renumber validation.\n"
        "- Integrates lifecycle, provider-safety, and publication checks.\n"
        "- Adds regression tests and documentation updates.\n"
        "</details>\n\n"
        "<details>\n<summary>File summaries</summary>\n\n"
        "| File | Summary |\r\n"
        "|---|---|\r\n"
        "| `tests/secpal-lifecycle-orchestration-unit.py` | Collision regression "
        "coverage |\r\n"
        "| `scripts/secpal_pr_review/version_collision.py` | Collision authentication "
        "and source validation |\r\n"
        "| `scripts/secpal_pr_review/lifecycle_orchestration.py` | Lifecycle "
        "integration and publication |\r\n"
        "| `scripts/secpal_pr_review/fast_path.py` | Evidence and feedback validation "
        "|\r\n"
        "| `scripts/README.md` | Script documentation |\r\n"
        "| `docs/secpal-pr-review-workflow.md` | Workflow contract documentation |\r\n"
        "| `CHANGELOG.md` | Change record |\n"
        "</details>\n\n"
        "<details>\n<summary>Review details</summary>\n\n"
        "### Suppressed comments (3)\n\n"
        "**scripts/secpal_pr_review/version_collision.py:366**\n"
        "* These offsets mix character and byte units. `ast` columns and "
        "`verify_blob_renumber` positions are UTF-8 byte offsets, but `len(line)` "
        "counts characters; because fast_path.py contains emoji literals before "
        "these declarations (for example lines 129 and 136), every identity after "
        "them is shifted and an otherwise exact collision renumber is rejected. "
        "Build `starts` with the encoded byte length and add a non-ASCII regression.\n"
        "```\n        starts.append(starts[-1] + len(line))\n```\n"
        "**scripts/secpal_pr_review/version_collision.py:698**\n"
        "* The object-transfer limits below do not bound this acquisition: a plain "
        "`git fetch` of both tips downloads their entire reachable commit, tree, and "
        "blob history before `_import_successor` applies any limit. Every collision "
        "authentication can therefore incur unbounded network, disk, and CPU cost as "
        "the repository grows, and a large history can exhaust the runner before the "
        "fail-closed checks run. Use a bounded partial/shallow acquisition that still "
        "proves the unique merge base, or enforce a fetch-level resource limit and "
        "reject when it cannot be met.\n"
        "```\n        _git(root, [\"-c\", \"fetch.fsckObjects=true\", \"fetch\", "
        "\"--no-tags\", \"origin\", _oid(main), _oid(predecessor)], 4096)\n```\n"
        "**scripts/secpal_pr_review/version_collision.py:380**\n"
        "* The linked #894 contract says the OLD-to-NEW normalization permits no test "
        "or logic edits, but this condition explicitly authorizes any changed `tests/` "
        "or Markdown path that happens to be in delivery scope. Those files are only "
        "checked for byte-level renumbering, so this trigger can carry unrelated "
        "test/documentation changes that are outside the promised source-only "
        "correction. Reject non-owner paths here (or bind a narrower, explicitly "
        "contract-approved set).\n"
        "```\n    if any(change[\"path\"] != SOURCE_PATH and not (\n"
        "        change[\"path\"].startswith(\"tests/\") or "
        "change[\"path\"].endswith(\".md\")\n"
        "    ) for change in delta[\"changes\"]):\n"
        "        raise VersionCollisionError(\"version identity edit extends outside "
        "its implementation, tests or documentation\")\n```\n"
        "\n- **Files reviewed:** 7/7 changed files\n"
        "- **Comments generated:** 4\n"
        "- **Review effort level:** Lite\n"
        "</details>\n\n---\n\n"
        "💡 <a href=\"/SecPal/.github/new/main?filename=.github/skills/code-review/"
        "SKILL.md\" class=\"Link--inTextBlock\" target=\"_blank\" "
        "rel=\"noopener noreferrer\">Add a `code-review` agent skill</a> or configure "
        "MCP servers for context-aware, tailored reviews. <a "
        "href=\"https://docs.github.com/copilot/how-tos/use-copilot-agents/"
        "request-a-code-review/use-code-review?tool=webui#mcp-servers-and-agent-skills\" "
        "class=\"Link--inTextBlock\" target=\"_blank\" "
        "rel=\"noopener noreferrer\">Learn more in the docs.</a>"
    )
    security_result = (
        "### 🛡️ Codex Security Review\n\n"
        "Security review completed. No security issues were found in this pull request.\n\n"
        "**Reviewed commit:** `18a6d02d8c`\n\n"
        "[View security finding report]"
        "(https://chatgpt.com/codex/cloud/tasks/task_e_6aa43c276a7c83329053f601e2daaa25)\n\n"
        "_Only the user who started this review can view the report in Codex._\n\n"
        "<details> <summary>ℹ️ About Codex security reviews in GitHub</summary>\n<br/>\n\n"
        "This is an experimental Codex feature. Security reviews are triggered when:\n"
        '- You comment "@codex security review"\n'
        '- A regular code review gets triggered (for example, "@codex review" or when a PR '
        "is opened), and you’re opted in so security review runs alongside code review\n\n"
        "Once complete, Codex will leave suggestions, or a comment if no findings are found.\n\n\n"
        "</details>"
    )
    bodies = {
        "IC_kwDOQFR1MM8AAAABUBIbNg": "@codex review",
        "IC_kwDOQFR1MM8AAAABUBIcQw": "@codex security review",
        "IC_kwDOQFR1MM8AAAABUBQgbA": security_result,
    }
    current_feedback = copy.deepcopy(reviewed.feedback)
    current_feedback["pull_request_reactions"] = []
    current_feedback["conversation_comments"][0].update(
        body_digest=fast_path.digest_text(summary),
        updated_at="2026-09-11T17:45:08Z",
    )
    for node_id, body in bodies.items():
        current_feedback["conversation_comments"].append(
            {
                "node_id": node_id,
                "body_digest": fast_path.digest_text(body),
                "actor": requester if body.startswith("@codex") else provider,
                "updated_at": {
                    "IC_kwDOQFR1MM8AAAABUBIbNg": "2026-09-11T17:36:32Z",
                    "IC_kwDOQFR1MM8AAAABUBIcQw": "2026-09-11T17:36:33Z",
                    "IC_kwDOQFR1MM8AAAABUBQgbA": "2026-09-11T17:45:05Z",
                }[node_id],
                "reactions": [],
            }
        )
    current_feedback["reviews"].append(
        {
            "node_id": "PRR_kwDOQFR1MM8AAAABNJC0sw",
            "body_digest": fast_path.digest_text(copilot_review),
            "actor": copilot,
            "state": "COMMENTED",
            "commit_oid": predecessor_head,
            "reactions": [],
        }
    )
    current_feedback["reviews"].append(
        {
            "node_id": "PRR_kwDOQFR1MM8AAAABNNvsIA",
            "body_digest": fast_path.digest_text(code_review),
            "actor": provider,
            "state": "COMMENTED",
            "commit_oid": resulting_head,
            "reactions": [],
        }
    )
    predecessor_findings = (
        (
            "PRRT_kwDOQFR1MM6hZ8MN",
            "PRRC_kwDOQFR1MM7tresP",
            "1419657c315455ffa222846a87eb96c40c62e2323628df7f6b472bdd8bf22de9",
            False,
        ),
        (
            "PRRT_kwDOQFR1MM6hZ8NI",
            "PRRC_kwDOQFR1MM7treth",
            "0e24243b6326d58ee210cd4e64c61ed95d409c1f937abdb096c945321738e42b",
            True,
        ),
        (
            "PRRT_kwDOQFR1MM6hZ8Ny",
            "PRRC_kwDOQFR1MM7treub",
            "c421704ad8149bcecf0f58df9be2114897703bf92c029b65fe69fd75f6285790",
            True,
        ),
        (
            "PRRT_kwDOQFR1MM6hZ8OV",
            "PRRC_kwDOQFR1MM7trevL",
            "c0058e62442ec19a6a9cd4f35805106d0544c0eeb9b9797110933d7ef2ca3944",
            False,
        ),
    )
    predecessor_material = []
    for thread_id, comment_id, body_digest, is_outdated in predecessor_findings:
        current_feedback["threads"].append(
            {
                "node_id": thread_id,
                "is_resolved": False,
                "is_outdated": is_outdated,
                "comments": [
                    {
                        "node_id": comment_id,
                        "body_digest": body_digest,
                        "actor": copilot,
                        "reply_to_id": None,
                        "reactions": [],
                    }
                ],
            }
        )
        predecessor_material.append(
            {
                "correction_scope_digest": PR_905_CORRECTION_AUTHORITY[
                    "finding_source_digest"
                ],
                "thread_id": thread_id,
                "sources": [
                    {
                        "kind": "THREAD_COMMENT",
                        "node_id": comment_id,
                        "digest": body_digest,
                    }
                ],
            }
        )
    suggestions = (
        (
            "PRRT_kwDOQFR1MM6hk-YJ",
            "PRRC_kwDOQFR1MM7t72Mn",
            "6d2f2240da81d5b30595fa239d6989311bb0c1191fafcb861d7194472a45df3a",
        ),
        (
            "PRRT_kwDOQFR1MM6hk-YQ",
            "PRRC_kwDOQFR1MM7t72Mt",
            "1b914a1fea2d46bbe8bcf04b52f148fa38e8ff68dc339347b60e094e90ac097c",
        ),
    )
    findings = []
    for index, (thread_id, comment_id, body_digest) in enumerate(suggestions, 1):
        current_feedback["threads"].append(
            {
                "node_id": thread_id,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "node_id": comment_id,
                        "body_digest": body_digest,
                        "actor": provider,
                        "reply_to_id": None,
                        "reactions": [],
                    }
                ],
            }
        )
        source = {
            "kind": "THREAD_COMMENT",
            "node_id": comment_id,
            "digest": body_digest,
        }
        findings.append(
            {
                "sources": [source],
                "classification_evidence": fast_path._seal_successor_classification(
                    repository=REPOSITORY,
                    delivery_issue_number=894,
                    pull_request_number=905,
                    head_sha=resulting_head,
                    finding_id=comment_id,
                    finding_evidence_digest=f"{index + 1}" * 64,
                    thread_id=thread_id,
                    top_level_comment_node_id=comment_id,
                    finding_body_digest=body_digest,
                    reply_count=0,
                    is_resolved=False,
                    is_outdated=False,
                    classification="INVALID_FALSE_OR_MISLEADING",
                    disposition="DISPROVEN_WITH_EVIDENCE",
                    technically_blocking=False,
                    technical_blockers=(),
                    classification_evidence_digest=f"{index + 3}" * 64,
                    source_bindings=(
                        ("THREAD_COMMENT", comment_id, body_digest, thread_id),
                    ),
                ),
            }
        )
    current = fast_path.StableFeedbackState(
        repository=REPOSITORY,
        pull_request_number=905,
        head_sha=resulting_head,
        base_ref="main",
        base_sha=reviewed.base_sha,
        pr_state="OPEN",
        feedback=current_feedback,
    )
    evidence: dict[str, object] = {
        "schema_version": "1.2",
        "repository": REPOSITORY,
        "pull_request_number": 905,
        "predecessor_state_digest": reviewed.state_digest,
        "resulting_head_sha": resulting_head,
        "resulting_state_digest": current.state_digest,
        "provider_transport": [
            {
                "role": "CODEX_SUMMARY_UPDATE",
                "kind": "CONVERSATION_COMMENT",
                "node_id": "IC_kwDOQFR1MM8AAAABT7Fdrg",
                "body": summary,
            },
            {
                "role": "CODEX_REVIEW_REQUEST",
                "kind": "CONVERSATION_COMMENT",
                "node_id": "IC_kwDOQFR1MM8AAAABUBIbNg",
                "body": bodies["IC_kwDOQFR1MM8AAAABUBIbNg"],
            },
            {
                "role": "CODEX_SECURITY_REVIEW_REQUEST",
                "kind": "CONVERSATION_COMMENT",
                "node_id": "IC_kwDOQFR1MM8AAAABUBIcQw",
                "body": bodies["IC_kwDOQFR1MM8AAAABUBIcQw"],
            },
            {
                "role": "CODEX_REVIEW",
                "kind": "REVIEW",
                "node_id": "PRR_kwDOQFR1MM8AAAABNNvsIA",
                "body": code_review,
            },
            {
                "role": "CODEX_SECURITY_REVIEW_RESULT",
                "kind": "CONVERSATION_COMMENT",
                "node_id": "IC_kwDOQFR1MM8AAAABUBQgbA",
                "body": security_result,
            },
        ],
        "successor_findings": findings,
        "provider_completion_reaction_removal": {
            "provider_login": "chatgpt-codex-connector",
            "reaction_content": "THUMBS_UP",
            "removed_reaction_id": "REA_lAHOQFR1MM8AAAABQzMEUc4d1oLF",
        },
        "predecessor_provider_feedback": {
            "correction_authority": copy.deepcopy(PR_905_CORRECTION_AUTHORITY),
            "provider_transport": [
                {
                    "role": "COPILOT_PREDECESSOR_REVIEW",
                    "kind": "REVIEW",
                    "node_id": "PRR_kwDOQFR1MM8AAAABNJC0sw",
                    "body": copilot_review,
                }
            ],
            "material_findings": predecessor_material,
        },
    }
    assert current.state_digest == (
        "d54bbdf4afa66b90c3a1db0827d1546833e64cb4cdc1878984929ce507c3339d"
    )
    return reviewed, current, evidence


def verify_pr_905_successor(
    reviewed: fast_path.StableFeedbackState,
    current: fast_path.StableFeedbackState,
    evidence: dict[str, object],
) -> str | None:
    return fast_path.verify_reanchored_stable_feedback_successor(
        reviewed,
        current,
        resulting_head_sha=current.head_sha,
        successor_safety_evidence=evidence,
        predecessor_correction_authority=(
            fast_path._seal_predecessor_correction_authority(
                reanchor_evidence_digest=PR_905_CORRECTION_AUTHORITY[
                    "reanchor_evidence_digest"
                ],
                material_finding_ids=tuple(
                    PR_905_CORRECTION_AUTHORITY["material_finding_ids"]
                ),
                finding_source_digest=PR_905_CORRECTION_AUTHORITY[
                    "finding_source_digest"
                ],
            )
        ),
    )


def _provider_terminal_summary(head_sha: str) -> str:
    return (
        "<!-- codex-pull-request-review-summary -->\n"
        '<!-- codex-security-review:v1 '
        f'{{"headSha":"{head_sha}","status":"completed"}} -->\n'
        "| Review | Status | Commit | Review trigger |\n"
        "| --- | --- | --- | --- |\n"
        "| **Code Review** | **Completed** | head | manual |\n"
        "| **Security Review** | **Completed** | head | manual |"
    )


def _provider_feedback_response(
    state: fast_path.StableFeedbackState,
    *,
    transport_bodies: dict[str, str],
) -> dict[str, object]:
    """Recreate the provider's external GraphQL representation for one replay."""

    def actor(value):
        return {
            "login": value["login"],
            "id": value["node_id"],
            "databaseId": value["database_id"],
        }

    def reaction(value):
        return {
            "id": value["mutation_id"],
            "databaseId": 1,
            "content": value["content"],
            "user": actor(value["actor"]),
        }

    def reactions(values):
        return {
            "nodes": [reaction(item) for item in values],
            "pageInfo": {"hasNextPage": False},
        }

    reviews = []
    for item in state.feedback["reviews"]:
        body = transport_bodies.get(item["node_id"], item["node_id"])
        reviews.append(
            {
                "id": item["node_id"],
                "body": body,
                "author": actor(item["actor"]),
                "state": item["state"],
                "commit": {"oid": item["commit_oid"]},
                "reactions": reactions(item["reactions"]),
            }
        )
    comments = []
    for item in state.feedback["conversation_comments"]:
        body = transport_bodies.get(item["node_id"], item["node_id"])
        comments.append(
            {
                "id": item["node_id"],
                "body": body,
                "author": actor(item["actor"]),
                "updatedAt": item["updated_at"],
                "reactions": reactions(item["reactions"]),
            }
        )
    threads = []
    for thread in state.feedback["threads"]:
        comments_connection = []
        for item in thread["comments"]:
            comments_connection.append(
                {
                    "id": item["node_id"],
                    "body": transport_bodies.get(
                        item["node_id"], item["node_id"]
                    ),
                    "author": actor(item["actor"]),
                    "replyTo": (
                        None
                        if item["reply_to_id"] is None
                        else {"id": item["reply_to_id"]}
                    ),
                    "reactions": reactions(item["reactions"]),
                }
            )
        threads.append(
            {
                "id": thread["node_id"],
                "isResolved": thread["is_resolved"],
                "isOutdated": thread["is_outdated"],
                "comments": {
                    "nodes": comments_connection,
                    "pageInfo": {"hasNextPage": False},
                },
            }
        )
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "id": "PR_PROVIDER_REPLAY",
                    "headRefOid": state.head_sha,
                    "baseRefName": state.base_ref,
                    "baseRefOid": state.base_sha,
                    "state": state.pr_state,
                    "isDraft": False,
                    "reviewDecision": None,
                    "reactions": reactions(
                        state.feedback["pull_request_reactions"]
                    ),
                    "reviews": {
                        "nodes": reviews,
                        "pageInfo": {"hasNextPage": False},
                    },
                    "comments": {
                        "nodes": comments,
                        "pageInfo": {"hasNextPage": False},
                    },
                    "reviewThreads": {
                        "nodes": threads,
                        "pageInfo": {"hasNextPage": False},
                    },
                    "reviewRequests": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False},
                    },
                }
            }
        }
    }


class LifecycleOrchestrationTests(TestCase):
    def test_feedback_capture_uses_explicit_isolated_bounded_repository_root(
        self,
    ) -> None:
        request, _authorization = continuation_inputs()
        reviewed = request["continuation_evidence"]["reviewed_state_evidence"]

        def run(command, **kwargs):
            output = Path(command[command.index("--capture-reviewed-state") + 1])
            output.write_bytes(authority.canonical_json_bytes(reviewed))
            return SimpleNamespace(returncode=0)

        with mock.patch.object(
            orchestration.bootstrap_source_admission,
            "_run_isolated_python",
            side_effect=run,
        ) as call:
            captured = orchestration._capture_current_stable_feedback(
                REPOSITORY, PR
            )

        command = call.call_args.args[0]
        options = call.call_args.kwargs
        self.assertEqual(captured.state_digest, reviewed["state_digest"])
        self.assertIn("-I", command)
        self.assertIn("-B", command)
        root = str(REPO_ROOT.resolve())
        self.assertEqual(command[command.index("--repo-root") + 1], root)
        self.assertEqual(options["cwd"], REPO_ROOT.resolve())
        self.assertEqual(options["timeout"], 60)
        self.assertNotIn("PYTHONPATH", options["env"])
        self.assertNotIn("PYTHONHOME", options["env"])

        with (
            mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_run_isolated_python",
                side_effect=(
                    orchestration.bootstrap_source_admission.BootstrapSourceAdmissionError(
                        "isolated feedback process timed out"
                    )
                ),
            ),
            self.assertRaisesRegex(
                orchestration.LifecycleOrchestrationError,
                "could not be authenticated",
            ),
        ):
            orchestration._capture_current_stable_feedback(REPOSITORY, PR)

    def test_signed_user_authorization_binds_exact_current_publication(self) -> None:
        lifecycle = current_lifecycle()
        observed = current_reader(lifecycle)(REPOSITORY, ISSUE)
        raw = orchestration.create_user_authorization(
            authorization_id="user-ready-exact",
            repository=REPOSITORY,
            delivery_issue=ISSUE,
            lifecycle=lifecycle,
            publication_oid=observed.publication_oid,
            publication_digest=observed.publication_digest,
            operation="READY_TO_DRAFT",
            reason="Pause this exact PR for a separately stated reason",
            scope={"pull_request": PR, "head_sha": HEAD},
            signer_identity="aroviqen@secpal.app",
            signer=lambda _payload, _domain: {
                "format": "ssh",
                "signer_identity": "aroviqen@secpal.app",
                "value": "fixture-signature",
            },
        )
        with mock.patch.object(orchestration.authority, "_verify_signature"):
            verified = orchestration._verify_user_authorization(
                raw, observed, lifecycle
            )
            stale = copy.deepcopy(lifecycle)
            object.__setattr__(stale, "authority_digest", "9" * 64)
            with self.assertRaises(orchestration.LifecycleOrchestrationError):
                orchestration._verify_user_authorization(raw, observed, stale)

        self.assertEqual(verified["operation"], "READY_TO_DRAFT")
        self.assertEqual(verified["scope"], {"pull_request": PR, "head_sha": HEAD})

    def test_documented_repository_package_import_works_without_path_injection(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from scripts.secpal_pr_review import lifecycle_orchestration",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_public_orchestrator_rejects_caller_constructed_user_authorization(self) -> None:
        forged = {
            "authorization_id": "forged-ready",
            "operation": "READY_TO_DRAFT",
            "reason": "Caller-created values are not authenticated authority",
            "scope": {"pull_request": PR, "head_sha": HEAD},
            "bounded_uses": 1,
        }
        request = {
            "event_kind": "READY_TO_DRAFT",
            "event_id": "draft-regression-forged",
            "pull_request": PR,
            "head_sha": HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": forged,
        }
        with (
            mock.patch.object(
                orchestration.publication,
                "verify_current_lifecycle_authority",
                current_reader(current_lifecycle()),
            ),
            self.assertRaises(orchestration.LifecycleOrchestrationError),
        ):
            orchestration.orchestrate_event(REPOSITORY, ISSUE, request)

    def test_additional_review_requires_persistent_signed_consumption(self) -> None:
        self.assertIn(
            "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
            authority.TRANSITIONS,
        )
        before = current_lifecycle()
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "ADDITIONAL_REVIEW_AUTHORIZED",
                "event_id": "authorization:" + "6" * 64,
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": json.dumps({"signed": "fixture"}),
            },
            current_reader=current_reader(before),
            authorization_verifier=lambda *_args, **_kwargs: {
                "authorization_id": "user-review-persistent",
                "operation": "ADDITIONAL_REVIEW",
                "reason": "Assess this exact current head once",
                "scope": {
                    "pull_request": PR,
                    "head_sha": HEAD,
                },
                "bounded_uses": 1,
                "authorization_digest": "6" * 64,
            },
        )

        self.assertEqual(
            decision.lifecycle_transition,
            "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
        )
        self.assertTrue(decision.requires_authorization_publication)
        self.assertEqual(decision.authorization_digest, "6" * 64)

    def test_public_orchestrator_accepts_no_consumer_authority_sources(self) -> None:
        self.assertEqual(
            list(inspect.signature(orchestration.orchestrate_event).parameters),
            ["repository", "delivery_issue", "request"],
        )

    def test_review_event_is_bounded_evidence_not_a_lifecycle_transition(self) -> None:
        lifecycle = current_lifecycle()
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "REVIEW_EVENT_OBSERVED",
                "event_id": "review-9001",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": None,
            },
            current_reader=current_reader(lifecycle),
        )

        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertTrue(decision.ready_transition_already_performed)
        self.assertFalse(decision.request_review)
        self.assertFalse(decision.transition_to_draft)
        self.assertTrue(decision.stop_after_bounded_pass)

    def test_ready_recovery_requires_exact_bounded_authorization_and_stays_ready(self) -> None:
        lifecycle = current_lifecycle()
        request = {
            "event_kind": "RECOVERY_COMMIT_PUSHED",
            "event_id": fixture_event_id("user-recovery-1"),
            "pull_request": PR,
            "head_sha": NEXT_HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": None,
        }
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                request,
                current_reader=current_reader(lifecycle),
                authorization_verifier=fixture_authorization_verifier,
            )

        request["authorization"] = {
            "authorization_id": "user-recovery-1",
            "operation": "EXCEPTIONAL_RECOVERY",
            "reason": "Correct the exact material post-Ready finding F-1",
            "scope": {
                "pull_request": PR,
                "predecessor_head_sha": HEAD,
                "resulting_head_sha": NEXT_HEAD,
                "finding_ids": ["F-1"],
            },
            "bounded_uses": 1,
        }
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            request,
            current_reader=current_reader(lifecycle),
            authorization_verifier=fixture_authorization_verifier,
        )

        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_RECOVERY")
        self.assertEqual(decision.resulting_head_sha, NEXT_HEAD)
        self.assertTrue(decision.preserve_ready)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.requires_fresh_head_evidence)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)

    def test_exhausted_ready_recovery_can_select_one_authenticated_continuation(
        self,
    ) -> None:
        lifecycle = current_lifecycle(exceptional_recoveries=1)
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=PR,
            head_sha=HEAD,
            base_ref="main",
            base_sha="0" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [
                    {
                        "node_id": "PRRT_CONTINUATION_1",
                        "is_resolved": False,
                        "is_outdated": True,
                        "comments": [
                            {
                                "node_id": "F-CONTINUATION-1",
                                "body_digest": "1" * 64,
                                "actor": {
                                    "login": "reviewer",
                                    "node_id": "ACTOR_1",
                                    "database_id": 1,
                                },
                                "reply_to_id": None,
                                "reactions": [],
                            }
                        ],
                    }
                ],
            },
        )
        finding_ids = ["F-CONTINUATION-1"]
        thread_ids = ["PRRT_CONTINUATION_1"]
        eligibility = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "pull_request_number": PR,
            "reviewed_head_sha": HEAD,
            "reviewed_state_digest": reviewed.state_digest,
            "eligible_threads": [
                {
                    "thread_id": thread_ids[0],
                    "classification": "VALID_ACTIONABLE",
                    "disposition": "CORRECTED_AND_VERIFIED",
                    "finding_ids": finding_ids,
                    "evidence_digest": "4" * 64,
                    "follow_up": None,
                }
            ],
        }
        authorization_digest = "6" * 64
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "CONTINUATION_COMMIT_PUSHED",
                "event_id": f"authorization:{authorization_digest}",
                "pull_request": PR,
                "head_sha": NEXT_HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": json.dumps({"signed": "fixture"}),
                "continuation_evidence": {
                    "reviewed_state_evidence": reviewed.to_dict(),
                    "eligibility_evidence": eligibility,
                },
            },
            current_reader=current_reader(lifecycle),
            feedback_reader=lambda _repository, _pull_request: feedback_successor(
                reviewed
            ),
            authorization_verifier=lambda *_args, **_kwargs: {
                "authorization_id": "user-continuation-1",
                "operation": "EXCEPTIONAL_CONTINUATION",
                "reason": "Correct one exact authenticated post-Recovery finding",
                "scope": {
                    "pull_request": PR,
                    "predecessor_head_sha": HEAD,
                    "resulting_head_sha": NEXT_HEAD,
                    "reviewed_state_digest": reviewed.state_digest,
                    "reviewed_feedback_digest": reviewed.feedback_digest,
                    "eligibility_evidence_digest": fast_path.digest_json(eligibility),
                    "finding_ids": finding_ids,
                    "thread_ids": thread_ids,
                },
                "bounded_uses": 1,
                "authorization_digest": authorization_digest,
            },
        )

        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
        self.assertEqual(decision.exceptional_recoveries, 1)
        self.assertEqual(decision.exceptional_continuations, 0)
        self.assertEqual(decision.resulting_head_sha, NEXT_HEAD)
        self.assertTrue(decision.preserve_ready)
        self.assertFalse(decision.request_review)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)

    def test_rejected_candidate_reanchor_selects_existing_continuation_without_thread_authority(
        self,
    ) -> None:
        lifecycle = current_lifecycle(
            exceptional_recoveries=1,
            pull_request=REPLACEMENT_PR,
        )
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=REPLACEMENT_PR,
            head_sha=HEAD,
            base_ref="main",
            base_sha="0" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        current = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=REPLACEMENT_PR,
            head_sha=NEXT_HEAD,
            base_ref=reviewed.base_ref,
            base_sha=reviewed.base_sha,
            pr_state="OPEN",
            feedback=copy.deepcopy(reviewed.feedback),
        )
        eligibility = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "pull_request_number": REPLACEMENT_PR,
            "reviewed_head_sha": HEAD,
            "reviewed_state_digest": reviewed.state_digest,
            "eligible_threads": [],
        }
        reanchor = orchestration.VerifiedRejectedContinuationReanchor(
            evidence_digest="1" * 64,
            original_pull_request=PR,
            replacement_pull_request=REPLACEMENT_PR,
            rejected_candidate_head_sha="c" * 40,
            rejected_candidate_tree_sha="d" * 40,
            rejected_continuation_evidence_digest="8" * 64,
            rejected_validation_receipt_digest="2" * 64,
            rejected_final_attestation_digest="3" * 64,
            rejected_state_digest="4" * 64,
            replacement_state_digest=reviewed.state_digest,
            material_finding_ids=("F-REJECTED-1",),
            material_thread_ids=("PRRT_REJECTED_1",),
            finding_source_digest="5" * 64,
            provider_reaction_replacement_digest="9" * 64,
        )
        authorization = {
            "authorization_id": "user-reanchored-continuation-1",
            "operation": "EXCEPTIONAL_CONTINUATION",
            "reason": "Correct the exact rejected unpublished candidate findings",
            "scope": {
                "pull_request": REPLACEMENT_PR,
                "original_pull_request": PR,
                "predecessor_head_sha": HEAD,
                "resulting_head_sha": NEXT_HEAD,
                "continuation_tree_sha": "e" * 40,
                "reviewed_state_digest": reviewed.state_digest,
                "reviewed_feedback_digest": reviewed.feedback_digest,
                "eligibility_evidence_digest": fast_path.digest_json(eligibility),
                "finding_ids": ["F-REJECTED-1"],
                "thread_ids": [],
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
                "corrected_successor_state_digest": current.state_digest,
                "provider_reaction_replacement_digest": "9" * 64,
            },
            "bounded_uses": 1,
        }
        request = {
            "event_kind": "CONTINUATION_COMMIT_PUSHED",
            "event_id": fixture_event_id(authorization["authorization_id"]),
            "pull_request": REPLACEMENT_PR,
            "head_sha": NEXT_HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": authorization,
            "continuation_evidence": {
                "reviewed_state_evidence": reviewed.to_dict(),
                "eligibility_evidence": eligibility,
                "successor_safety_evidence": None,
                "reanchor_evidence": {"closed": "fixture"},
                "expected_signer": {
                    "kind": "SSH_PRINCIPAL",
                    "identity": "aroviqen@secpal.app",
                },
            },
        }

        classified_review_modes = []
        predecessor_correction_authorities = []

        def decide(
            candidate,
            *,
            reanchor_authority=reanchor,
            source_tree="e" * 40,
            predecessor_growth_digest=None,
        ):
            with (
                mock.patch.object(
                    orchestration,
                    "_authenticate_successor_safety_evidence",
                    side_effect=lambda _value, **kwargs: (
                        classified_review_modes.append(
                            kwargs["reanchored_classified_review"]
                        ),
                        predecessor_correction_authorities.append(
                            kwargs["predecessor_correction_authority"]
                        ),
                    )[-1],
                ),
                mock.patch.object(
                    fast_path,
                    "verify_reanchored_stable_feedback_successor",
                    return_value=predecessor_growth_digest,
                ),
            ):
                return orchestration._orchestrate_event(
                    REPOSITORY,
                    ISSUE,
                    candidate,
                    current_reader=current_reader(lifecycle),
                    feedback_reader=lambda *_args: current,
                    authorization_verifier=fixture_authorization_verifier,
                    reanchor_verifier=lambda *_args, **_kwargs: reanchor_authority,
                    source_commit_verifier=lambda *_args, **_kwargs: SimpleNamespace(
                        tree_sha=source_tree,
                    ),
                )

        decision = decide(request)

        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
        self.assertEqual(decision.resulting_pull_request, REPLACEMENT_PR)
        self.assertEqual(decision.resulting_head_sha, NEXT_HEAD)
        self.assertEqual(decision.exceptional_continuations, 0)
        self.assertFalse(decision.request_review)
        self.assertIs(classified_review_modes[-1], False)

        classified_request = copy.deepcopy(request)
        classified_request["continuation_evidence"]["successor_safety_evidence"] = {
            "schema_version": "1.1"
        }
        decision = decide(classified_request)
        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
        self.assertIs(classified_review_modes[-1], True)
        self.assertIs(predecessor_correction_authorities[-1], reanchor)

        predecessor_growth_request = copy.deepcopy(request)
        predecessor_growth_request["continuation_evidence"][
            "successor_safety_evidence"
        ] = {"schema_version": "1.2"}
        predecessor_growth_request["authorization"]["scope"][
            "predecessor_provider_growth_digest"
        ] = "a" * 64
        decision = decide(
            predecessor_growth_request,
            predecessor_growth_digest="a" * 64,
        )
        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
        self.assertIs(classified_review_modes[-1], True)
        self.assertIs(predecessor_correction_authorities[-1], reanchor)

        for field, replacement in (
            ("original_pull_request", PR + 10),
            ("continuation_tree_sha", "f" * 40),
            ("reanchor_evidence_digest", "f" * 64),
            ("rejected_candidate_head_sha", "f" * 40),
            ("rejected_candidate_tree_sha", "f" * 40),
            ("rejected_continuation_evidence_digest", "f" * 64),
            ("rejected_validation_receipt_digest", "f" * 64),
            ("rejected_final_attestation_digest", "f" * 64),
            ("rejected_state_digest", "f" * 64),
            ("replacement_state_digest", "f" * 64),
            ("finding_source_digest", "f" * 64),
            ("corrected_successor_state_digest", "f" * 64),
            ("provider_reaction_replacement_digest", "f" * 64),
            ("predecessor_provider_growth_digest", "f" * 64),
        ):
            changed = copy.deepcopy(request)
            changed["authorization"]["scope"][field] = replacement
            growth_digest = None
            if field == "predecessor_provider_growth_digest":
                changed = copy.deepcopy(predecessor_growth_request)
                changed["authorization"]["scope"][field] = replacement
                growth_digest = "a" * 64
            with self.subTest(field=field), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                decide(changed, predecessor_growth_digest=growth_digest)

        rejected_head_reused = orchestration.VerifiedRejectedContinuationReanchor(
            **{
                **reanchor.__dict__,
                "rejected_candidate_head_sha": NEXT_HEAD,
            }
        )
        with self.assertRaisesRegex(
            orchestration.LifecycleOrchestrationError,
            "rejected Continuation candidate",
        ):
            decide(request, reanchor_authority=rejected_head_reused)

        rejected_tree_reused = orchestration.VerifiedRejectedContinuationReanchor(
            **{
                **reanchor.__dict__,
                "rejected_candidate_tree_sha": "e" * 40,
            }
        )
        with self.assertRaisesRegex(
            orchestration.LifecycleOrchestrationError,
            "rejected Continuation candidate",
        ):
            decide(request, reanchor_authority=rejected_tree_reused)

    def test_clean_replacement_feedback_cannot_use_historical_material_continuation_path(
        self,
    ) -> None:
        lifecycle = current_lifecycle(
            exceptional_recoveries=1,
            pull_request=REPLACEMENT_PR,
        )
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=REPLACEMENT_PR,
            head_sha=HEAD,
            base_ref="main",
            base_sha="0" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        eligibility = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "pull_request_number": REPLACEMENT_PR,
            "reviewed_head_sha": HEAD,
            "reviewed_state_digest": reviewed.state_digest,
            "eligible_threads": [],
        }
        with self.assertRaisesRegex(
            orchestration.LifecycleOrchestrationError,
            "continuation finding evidence is invalid or stale",
        ):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                {
                    "event_kind": "CONTINUATION_COMMIT_PUSHED",
                    "event_id": fixture_event_id("no-old-pr-replay"),
                    "pull_request": REPLACEMENT_PR,
                    "head_sha": NEXT_HEAD,
                    "replacement_pull_request": None,
                    "classification": None,
                    "follow_up": None,
                    "authorization": {
                        "authorization_id": "no-old-pr-replay",
                        "operation": "EXCEPTIONAL_CONTINUATION",
                        "reason": "Historical finding replay must remain rejected",
                        "scope": {},
                        "bounded_uses": 1,
                    },
                    "continuation_evidence": {
                        "reviewed_state_evidence": reviewed.to_dict(),
                        "eligibility_evidence": eligibility,
                    },
                },
                current_reader=current_reader(lifecycle),
                feedback_reader=lambda *_args: reviewed,
                authorization_verifier=fixture_authorization_verifier,
            )

    def test_reanchor_authenticates_rebound_candidate_validation_and_material_sources(
        self,
    ) -> None:
        delivery_issue = 894
        original_pr = 901
        replacement_pr = 905
        historical_main = "aa7d9e4485abbceed01136cd81fdbbd353f877bc"
        protected_main = "da7d5f19a1ff4e65bfdbe7ad0a66e13f6172ada9"
        current_head = "46d09efb237f3e8c2e1f1066ba2b840a018ef889"
        current_tree = "1635cf7a27f1340c001c67c91999224c9cb577a7"
        rejected_head = "be511e420933eeffb289188f3620677bc7cb9f84"
        rejected_tree = "ea029f69a64f6b08145483018f7b1d0e7dec51b7"
        rejected_reviewed, rejected_state, rejected_safety = (
            authenticated_provider_reaction_replacement()
        )
        replacement_reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=replacement_pr,
            head_sha=current_head,
            base_ref=rejected_reviewed.base_ref,
            base_sha=protected_main,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        current_lifecycle_state = current_lifecycle(
            exceptional_recoveries=1,
            pull_request=replacement_pr,
            head_sha=current_head,
            delivery_issue=delivery_issue,
        )
        predecessor_lifecycle = authority.VerifiedLifecycleAuthority(
            authority_digest="6" * 64,
            repository=REPOSITORY,
            delivery_issue=delivery_issue,
            lifecycle_id=LIFECYCLE,
            initialization_evidence_digest=current_lifecycle_state.initialization_evidence_digest,
            pull_request=original_pr,
            head_sha=current_head,
            state=copy.deepcopy(current_lifecycle_state.state),
            authority_signer_identity=current_lifecycle_state.authority_signer_identity,
        )
        predecessor_publication = publication.VerifiedLifecyclePublication(
            "6" * 40,
            "7" * 64,
            "secpal-lifecycle-publications",
            "5" * 40,
            "4" * 40,
            predecessor_lifecycle,
        )
        observed = publication.VerifiedLifecyclePublication(
            "8" * 40,
            "9" * 64,
            "secpal-lifecycle-publications",
            "7" * 40,
            predecessor_publication.publication_oid,
            current_lifecycle_state,
        )
        rebound = publication.VerifiedLifecyclePublicationTransition(
            predecessor=predecessor_publication,
            successor=observed,
            event_id="authorization:rebound",
            event_digest="a" * 64,
            transition_kind="PR_REBOUND",
            event_signer_identity="aroviqen@secpal.app",
            pull_request=original_pr,
            predecessor_authority_digest=predecessor_lifecycle.authority_digest,
            predecessor_head_sha=current_head,
            resulting_head_sha=current_head,
            initialization_evidence_digest=(
                current_lifecycle_state.initialization_evidence_digest
            ),
        )
        rejected_eligibility = {"closed": "rejected eligibility fixture"}
        rejected_continuation = {"closed": "rejected Continuation fixture"}
        rejected_lifecycle_projection = {
            "unrestricted_reviews": 1,
            "remediation_cycles": 2,
            "cycle_3": False,
            "draft": False,
            "ready": True,
            "ready_transition_count": 1,
            "ready_history": copy.deepcopy(
                current_lifecycle_state.state["ready_history"]
            ),
            "exceptional_recovery_count": 1,
            "exceptional_recovery_history": copy.deepcopy(
                current_lifecycle_state.state["exceptional_recovery_history"]
            ),
            "exceptional_continuation_predecessor_count": 0,
            "exceptional_continuation_successor_count": 1,
        }
        normalized_rejected_continuation = {
            "eligibility_evidence_digest": "1" * 64,
            "authorization_id": "rejected-continuation-authorization",
            "delivery_issue_number": delivery_issue,
            "prior_ready_tree_sha": current_tree,
            "expected_signer": {
                "kind": "SSH_PRINCIPAL",
                "identity": "aroviqen@secpal.app",
            },
            "lifecycle": rejected_lifecycle_projection,
        }
        rejected_continuation_digest = fast_path.digest_json(
            normalized_rejected_continuation
        )
        receipt = {
            "receipt_digest": (
                "cea452a1f4eb4926233259b84bde1aab7"
                "167e59686dd4667818b5bd499ba6738"
            ),
            "manual_gate_evidence": [],
            "eligibility_evidence_digest": "1" * 64,
            "exceptional_continuation_evidence_digest": (
                rejected_continuation_digest
            ),
        }
        attestation = {"attestation_digest": "c" * 64}
        evidence = {
            "schema_version": "1.0",
            "kind": "REJECTED_EXCEPTIONAL_CONTINUATION_REANCHOR",
            "repository": REPOSITORY,
            "delivery_issue_number": delivery_issue,
            "original_pull_request_number": original_pr,
            "replacement_pull_request_number": replacement_pr,
            "lifecycle_id": LIFECYCLE,
            "current_publication_oid": observed.publication_oid,
            "current_publication_digest": observed.publication_digest,
            "current_authority_digest": current_lifecycle_state.authority_digest,
            "current_head_sha": current_head,
            "current_tree_sha": current_tree,
            "rebound_predecessor_publication_oid": (
                predecessor_publication.publication_oid
            ),
            "rebound_event_digest": rebound.event_digest,
            "rejected_candidate_head_sha": rejected_head,
            "rejected_candidate_tree_sha": rejected_tree,
            "rejected_candidate_expected_signer": {
                "kind": "SSH_PRINCIPAL",
                "identity": "aroviqen@secpal.app",
            },
            "rejected_continuation_evidence": rejected_continuation,
            "rejected_eligibility_evidence": rejected_eligibility,
            "rejected_reviewed_state_evidence": rejected_reviewed.to_dict(),
            "rejected_candidate_state_evidence": rejected_state.to_dict(),
            "rejected_successor_safety_evidence": {"signed": "fixture"},
            "rejected_validation_receipt": receipt,
            "rejected_final_attestation": attestation,
            "replacement_reviewed_state_evidence": replacement_reviewed.to_dict(),
        }
        source = SimpleNamespace(
            tree_sha=rejected_tree,
            signer_kind="SSH_PRINCIPAL",
            signer_identity="aroviqen@secpal.app",
            authentication_digest="f" * 64,
        )
        validation = SimpleNamespace(
            validation_receipt_digest=receipt["receipt_digest"],
            final_attestation_digest=attestation["attestation_digest"],
        )
        historical_registry_reader = mock.Mock(
            return_value=(
                {
                    "default_branch": "main",
                    "validation": [],
                    "manual_gates": [],
                },
                orchestration.bootstrap_source_admission.ProtectedMainFacts(
                    repository=REPOSITORY,
                    default_branch="main",
                    head_sha=protected_main,
                ),
            )
        )
        def authenticate_lineage(repository, ancestor, descendant):
            if repository != REPOSITORY or (ancestor, descendant) not in {
                (historical_main, protected_main),
                (protected_main, "f" * 40),
            }:
                raise orchestration.LifecycleOrchestrationError(
                    "unrelated accepted-main substitution"
                )

        accepted_main_lineage = mock.Mock(side_effect=authenticate_lineage)

        def verify(candidate, *, current=observed, rebound_value=rebound):
            def verify_attestation(value, **_kwargs):
                if value != attestation:
                    raise fast_path.SecurityBlocker("substituted attestation")
                return validation

            def normalize_continuation(value, **kwargs):
                if (
                    value != rejected_continuation
                    or kwargs.get("eligibility_evidence") != rejected_eligibility
                    or kwargs.get("reviewed_state") != rejected_reviewed
                    or kwargs.get("validated_tree_sha") != rejected_tree
                ):
                    raise fast_path.SecurityBlocker(
                        "substituted rejected Continuation evidence"
                    )
                return normalized_rejected_continuation

            with (
                mock.patch.object(
                    orchestration,
                    "_immutable_commit_tree",
                    side_effect=lambda _root, _repo, head: (
                        current_tree if head == current_head else rejected_tree
                    ),
                ),
                mock.patch.object(
                    orchestration,
                    "_authenticate_continuation_commit",
                    return_value=source,
                ),
                mock.patch.object(
                    orchestration,
                    "_immutable_commit_receipt",
                    return_value=receipt["receipt_digest"],
                ),
                mock.patch.object(
                    orchestration,
                    "_historical_validation_registry_authority",
                    new=historical_registry_reader,
                ),
                mock.patch.object(
                    orchestration,
                    "_authenticate_accepted_main_ancestor",
                    new=accepted_main_lineage,
                ),
                mock.patch.object(
                    fast_path,
                    "normalize_exceptional_continuation_evidence",
                    side_effect=normalize_continuation,
                ),
                mock.patch.object(
                    fast_path, "create_validation_receipt", return_value=receipt
                ),
                mock.patch.object(
                    fast_path,
                    "verify_validation_attestation",
                    side_effect=verify_attestation,
                ),
                mock.patch.object(
                    orchestration,
                    "_authenticate_rejected_successor_safety_evidence",
                    return_value=rejected_safety,
                ),
            ):
                return orchestration.verify_rejected_continuation_reanchor(
                    candidate,
                    observed=current,
                    repository_root=REPO_ROOT,
                    historical_reader=lambda *_args: rebound_value,
                )

        verified = verify(evidence)
        historical_registry_reader.assert_called_once_with(
            REPO_ROOT,
            REPOSITORY,
            historical_main,
        )
        historical_registry_reader.reset_mock()
        self.assertEqual(
            accepted_main_lineage.call_args_list,
            [
                mock.call(REPOSITORY, historical_main, protected_main),
            ],
        )
        accepted_main_lineage.reset_mock()

        self.assertEqual(verified.original_pull_request, original_pr)
        self.assertEqual(verified.replacement_pull_request, replacement_pr)
        self.assertEqual(verified.rejected_candidate_head_sha, rejected_head)
        self.assertEqual(
            verified.historical_accepted_main_base_sha,
            historical_main,
        )
        self.assertEqual(
            verified.current_protected_main_base_sha,
            protected_main,
        )
        self.assertRegex(
            verified.provider_reaction_replacement_digest or "",
            r"^[0-9a-f]{64}$",
        )
        self.assertEqual(verified.material_finding_ids, ("PRRC_RESULTING_HEAD",))
        self.assertEqual(verified.material_thread_ids, ("PRRT_RESULTING_HEAD",))
        self.assertEqual(
            verified.rejected_continuation_evidence_digest,
            rejected_continuation_digest,
        )
        self.assertRegex(verified.evidence_digest, r"^[0-9a-f]{64}$")

        same_base = copy.deepcopy(evidence)
        same_base_payload = copy.deepcopy(
            same_base["replacement_reviewed_state_evidence"]
        )
        same_base_payload["base_sha"] = historical_main
        same_base["replacement_reviewed_state_evidence"] = (
            fast_path.StableFeedbackState.from_payload(
                same_base_payload
            ).to_dict()
        )
        same_base_verified = verify(same_base)
        self.assertIsNone(same_base_verified.historical_accepted_main_base_sha)
        self.assertIsNone(same_base_verified.current_protected_main_base_sha)
        self.assertNotEqual(
            same_base_verified.evidence_digest,
            verified.evidence_digest,
        )

        caller_trust = copy.deepcopy(evidence)
        caller_trust["trusted_replacement_base_sha"] = protected_main
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            verify(caller_trust)

        registry, protected_facts = historical_registry_reader.return_value
        historical_registry_reader.return_value = (
            registry,
            orchestration.bootstrap_source_admission.ProtectedMainFacts(
                repository="SecPal/api",
                default_branch=protected_facts.default_branch,
                head_sha=protected_facts.head_sha,
            ),
        )
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            verify(evidence)
        historical_registry_reader.return_value = (registry, protected_facts)

        later_protected_main = "f" * 40
        historical_registry_reader.return_value = (
            registry,
            orchestration.bootstrap_source_admission.ProtectedMainFacts(
                repository=REPOSITORY,
                default_branch=protected_facts.default_branch,
                head_sha=later_protected_main,
            ),
        )
        accepted_main_lineage.reset_mock()
        later_verified = verify(evidence)
        self.assertEqual(
            later_verified.current_protected_main_base_sha,
            protected_main,
        )
        self.assertEqual(later_verified.evidence_digest, verified.evidence_digest)
        def signed_scope(reanchor):
            return orchestration._continuation_authorization_scope(
                orchestration.VerifiedContinuationFindingAuthority(
                    reviewed_state_digest=replacement_reviewed.state_digest,
                    reviewed_feedback_digest=(
                        replacement_reviewed.feedback_digest
                    ),
                    eligibility_evidence_digest="d" * 64,
                    finding_ids=reanchor.material_finding_ids,
                    thread_ids=(),
                    reanchor=reanchor,
                    continuation_tree_sha="e" * 40,
                    corrected_successor_state_digest="f" * 64,
                ),
                pull_request=replacement_pr,
                predecessor_head_sha=current_head,
                resulting_head_sha="9" * 40,
            )

        self.assertEqual(signed_scope(later_verified), signed_scope(verified))
        self.assertEqual(
            accepted_main_lineage.call_args_list,
            [
                mock.call(REPOSITORY, historical_main, protected_main),
                mock.call(REPOSITORY, protected_main, later_protected_main),
            ],
        )
        historical_registry_reader.return_value = (registry, protected_facts)

        for field, replacement in (
            ("repository", "SecPal/api"),
            ("delivery_issue_number", ISSUE + 1),
            ("original_pull_request_number", original_pr + 10),
            ("replacement_pull_request_number", replacement_pr + 10),
            ("current_publication_oid", "f" * 40),
            ("current_publication_digest", "f" * 64),
            ("current_authority_digest", "f" * 64),
            ("current_head_sha", "f" * 40),
            ("current_tree_sha", "f" * 40),
            ("rebound_predecessor_publication_oid", "f" * 40),
            ("rebound_event_digest", "f" * 64),
            ("rejected_candidate_head_sha", "f" * 40),
            ("rejected_candidate_tree_sha", "f" * 40),
        ):
            changed = copy.deepcopy(evidence)
            changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                verify(changed)

        changed_receipt = copy.deepcopy(evidence)
        changed_receipt["rejected_validation_receipt"]["receipt_digest"] = "f" * 64
        changed_attestation = copy.deepcopy(evidence)
        changed_attestation["rejected_final_attestation"]["attestation_digest"] = (
            "f" * 64
        )
        changed_continuation = copy.deepcopy(evidence)
        changed_continuation["rejected_continuation_evidence"] = {
            "closed": "substituted Continuation"
        }
        changed_base = copy.deepcopy(evidence)
        replacement_payload = copy.deepcopy(
            changed_base["replacement_reviewed_state_evidence"]
        )
        replacement_payload["base_sha"] = "f" * 40
        changed_base["replacement_reviewed_state_evidence"] = (
            fast_path.StableFeedbackState.from_payload(replacement_payload).to_dict()
        )
        for label, changed in (
            ("receipt", changed_receipt),
            ("attestation", changed_attestation),
            ("Continuation", changed_continuation),
            ("base", changed_base),
        ):
            with self.subTest(label=label), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                verify(changed)

        for field, replacement in (
            ("delivery_issue_number", ISSUE + 1),
            ("prior_ready_tree_sha", "f" * 40),
            (
                "expected_signer",
                {
                    "kind": "SSH_PRINCIPAL",
                    "identity": "different@secpal.app",
                },
            ),
            ("lifecycle", {**rejected_lifecycle_projection, "ready": False}),
        ):
            original = normalized_rejected_continuation[field]
            normalized_rejected_continuation[field] = replacement
            with self.subTest(continuation_field=field), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                verify(evidence)
            normalized_rejected_continuation[field] = original

        consumed_lifecycle = current_lifecycle(
            exceptional_recoveries=1,
            exceptional_continuations=1,
            pull_request=replacement_pr,
            head_sha=current_head,
            delivery_issue=delivery_issue,
        )
        consumed_current = publication.VerifiedLifecyclePublication(
            observed.publication_oid,
            observed.publication_digest,
            observed.publication_branch,
            observed.journal_predecessor_oid,
            observed.predecessor_publication_oid,
            consumed_lifecycle,
        )
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            verify(evidence, current=consumed_current)

        published_lifecycle = authority.VerifiedLifecycleAuthority(
            authority_digest=current_lifecycle_state.authority_digest,
            repository=REPOSITORY,
            delivery_issue=delivery_issue,
            lifecycle_id=LIFECYCLE,
            initialization_evidence_digest=(
                current_lifecycle_state.initialization_evidence_digest
            ),
            pull_request=replacement_pr,
            head_sha=rejected_head,
            state=copy.deepcopy(current_lifecycle_state.state),
            authority_signer_identity=(
                current_lifecycle_state.authority_signer_identity
            ),
        )
        published_current = publication.VerifiedLifecyclePublication(
            observed.publication_oid,
            observed.publication_digest,
            observed.publication_branch,
            observed.journal_predecessor_oid,
            observed.predecessor_publication_oid,
            published_lifecycle,
        )
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            verify(evidence, current=published_current)

        wrong_rebound = publication.VerifiedLifecyclePublicationTransition(
            **{
                **rebound.__dict__,
                "transition_kind": "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
            }
        )
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            verify(evidence, rebound_value=wrong_rebound)

    def test_historical_validation_registry_requires_accepted_main_ancestor(
        self,
    ) -> None:
        protected_main = "da7d5f19a1ff4e65bfdbe7ad0a66e13f6172ada9"
        historical_main = "aa7d9e4485abbceed01136cd81fdbbd353f877bc"
        registry = {
            "default_branch": "main",
            "validation": [],
            "manual_gates": [],
        }
        actions = SimpleNamespace(
            _prior_delivery_registry_binding=mock.Mock(return_value=registry)
        )
        facts = SimpleNamespace(
            repository=REPOSITORY,
            default_branch="main",
            head_sha=protected_main,
        )

        def comparison(*, status="ahead", merge_base=historical_main):
            payload = json.dumps(
                {
                    "status": status,
                    "behind_by": 0,
                    "merge_base_sha": merge_base,
                }
            ).encode()
            return subprocess.CompletedProcess([], 0, payload, b"")

        with (
            mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_observe_protected_main",
                return_value=object(),
            ),
            mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_normalize_protected_main",
                return_value=facts,
            ),
            mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_run_bootstrap_gh",
                return_value=comparison(),
            ) as compare_reader,
            mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_load_actions_helper",
                return_value=actions,
            ),
        ):
            self.assertEqual(
                orchestration._historical_validation_registry_binding(
                    REPO_ROOT,
                    REPOSITORY,
                    historical_main,
                ),
                registry,
            )
        compare_reader.assert_called_once()
        compare_command = compare_reader.call_args.args[0]
        self.assertIn(
            f"repos/{REPOSITORY}/compare/{historical_main}...{protected_main}",
            compare_command,
        )
        self.assertNotIn(".head_commit.sha", compare_command[-1])

        for result in (
            comparison(status="diverged"),
            comparison(merge_base="1" * 40),
            subprocess.CompletedProcess([], 1, b"{}", b"failure"),
        ):
            with (
                mock.patch.object(
                    orchestration.bootstrap_source_admission,
                    "_observe_protected_main",
                    return_value=object(),
                ),
                mock.patch.object(
                    orchestration.bootstrap_source_admission,
                    "_normalize_protected_main",
                    return_value=facts,
                ),
                mock.patch.object(
                    orchestration.bootstrap_source_admission,
                    "_run_bootstrap_gh",
                    return_value=result,
                ),
                mock.patch.object(
                    orchestration.bootstrap_source_admission,
                    "_load_actions_helper",
                    return_value=actions,
                ),
                self.assertRaises(orchestration.LifecycleOrchestrationError),
            ):
                orchestration._historical_validation_registry_binding(
                    REPO_ROOT,
                    REPOSITORY,
                    historical_main,
                )

    def test_accepted_main_comparison_separates_observation_from_admission(
        self,
    ) -> None:
        ancestor = "aa7d9e4485abbceed01136cd81fdbbd353f877bc"
        descendant = "da7d5f19a1ff4e65bfdbe7ad0a66e13f6172ada9"
        result = subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                {
                    "status": "ahead",
                    "behind_by": 0,
                    "merge_base_sha": ancestor,
                }
            ).encode(),
            b"",
        )
        with mock.patch.object(
            orchestration.bootstrap_source_admission,
            "_run_bootstrap_gh",
            return_value=result,
        ) as compare_reader:
            observed = orchestration._observe_accepted_main_comparison(
                REPOSITORY,
                ancestor,
                descendant,
            )

        self.assertEqual(
            observed,
            orchestration.AcceptedMainComparisonFacts(
                status="ahead",
                behind_by=0,
                merge_base_sha=ancestor,
            ),
        )
        orchestration._require_accepted_main_ancestor(
            ancestor,
            descendant,
            observed,
        )
        compare_command = compare_reader.call_args.args[0]
        self.assertIn(
            f"repos/{REPOSITORY}/compare/{ancestor}...{descendant}",
            compare_command,
        )

        for facts in (
            orchestration.AcceptedMainComparisonFacts(
                status="diverged",
                behind_by=0,
                merge_base_sha=ancestor,
            ),
            orchestration.AcceptedMainComparisonFacts(
                status="ahead",
                behind_by=1,
                merge_base_sha=ancestor,
            ),
            orchestration.AcceptedMainComparisonFacts(
                status="ahead",
                behind_by=0,
                merge_base_sha="f" * 40,
            ),
        ):
            with self.subTest(facts=facts), self.assertRaises(
                orchestration.LifecycleOrchestrationError
            ):
                orchestration._require_accepted_main_ancestor(
                    ancestor,
                    descendant,
                    facts,
                )

    def test_reanchored_continuation_normalization_keeps_old_threads_diagnostic_only(
        self,
    ) -> None:
        reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY,
            pull_request_number=REPLACEMENT_PR,
            head_sha=HEAD,
            base_ref="main",
            base_sha="0" * 40,
            pr_state="OPEN",
            feedback={
                "pull_request_reactions": [],
                "reviews": [],
                "conversation_comments": [],
                "threads": [],
            },
        )
        eligibility = {
            "schema_version": "1.1",
            "repository": REPOSITORY,
            "pull_request_number": REPLACEMENT_PR,
            "reviewed_head_sha": HEAD,
            "reviewed_state_digest": reviewed.state_digest,
            "eligible_threads": [],
        }
        reanchor = orchestration.VerifiedRejectedContinuationReanchor(
            evidence_digest="1" * 64,
            original_pull_request=PR,
            replacement_pull_request=REPLACEMENT_PR,
            rejected_candidate_head_sha="c" * 40,
            rejected_candidate_tree_sha="d" * 40,
            rejected_continuation_evidence_digest="8" * 64,
            rejected_validation_receipt_digest="2" * 64,
            rejected_final_attestation_digest="3" * 64,
            rejected_state_digest="4" * 64,
            replacement_state_digest=reviewed.state_digest,
            material_finding_ids=("F-REJECTED-1",),
            material_thread_ids=("PRRT_REJECTED_1",),
            finding_source_digest="5" * 64,
        )
        lifecycle_projection = {
            "unrestricted_reviews": 1,
            "remediation_cycles": 2,
            "cycle_3": False,
            "draft": False,
            "ready": True,
            "ready_transition_count": 1,
            "ready_history": [
                {
                    "sequence": 1,
                    "transition_kind": "DRAFT_TO_READY",
                    "event_authorization_digest": "6" * 64,
                }
            ],
            "exceptional_recovery_count": 1,
            "exceptional_recovery_history": [
                {
                    "sequence": 1,
                    "transition_kind": "EXCEPTIONAL_RECOVERY",
                    "event_authorization_digest": "7" * 64,
                }
            ],
            "exceptional_continuation_predecessor_count": 0,
            "exceptional_continuation_successor_count": 1,
        }
        value = {
            "schema_version": "1.1",
            "kind": "READY_EXCEPTIONAL_CONTINUATION",
            "authorization_id": "reanchored-continuation-1",
            "repository": REPOSITORY,
            "delivery_issue_number": ISSUE,
            "pull_request_number": REPLACEMENT_PR,
            "prior_ready_head_sha": HEAD,
            "prior_ready_tree_sha": "a" * 40,
            "continuation_tree_sha": "b" * 40,
            "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "eligibility_evidence_digest": fast_path.digest_json(eligibility),
            "finding_ids": list(reanchor.material_finding_ids),
            "thread_ids": [],
            "expected_signer": {
                "kind": "SSH_PRINCIPAL",
                "identity": "aroviqen@secpal.app",
            },
            "lifecycle": lifecycle_projection,
            "reanchor": {
                field: (
                    list(getattr(reanchor, field))
                    if field in {"material_finding_ids", "material_thread_ids"}
                    else getattr(reanchor, field)
                )
                for field in fast_path.EXCEPTIONAL_CONTINUATION_REANCHOR_FIELDS
            },
        }

        normalized = fast_path.normalize_exceptional_continuation_evidence(
            value,
            repository=REPOSITORY,
            reviewed_state=reviewed,
            validated_tree_sha="b" * 40,
            eligibility_evidence=eligibility,
            reanchor_authority=reanchor,
        )

        self.assertEqual(normalized["finding_ids"], ["F-REJECTED-1"])
        self.assertEqual(normalized["thread_ids"], [])
        self.assertEqual(
            normalized["reanchor"]["material_thread_ids"],
            ["PRRT_REJECTED_1"],
        )
        advanced_reanchor = orchestration.VerifiedRejectedContinuationReanchor(
            **{
                **reanchor.__dict__,
                "historical_accepted_main_base_sha": (
                    "aa7d9e4485abbceed01136cd81fdbbd353f877bc"
                ),
                "current_protected_main_base_sha": (
                    "da7d5f19a1ff4e65bfdbe7ad0a66e13f6172ada9"
                ),
                "provider_reaction_replacement_digest": "9" * 64,
            }
        )
        advanced = copy.deepcopy(value)
        advanced["reanchor"] = {
            field: (
                list(getattr(advanced_reanchor, field))
                if field in {"material_finding_ids", "material_thread_ids"}
                else getattr(advanced_reanchor, field)
            )
            for field in fast_path.EXCEPTIONAL_CONTINUATION_REANCHOR_DRIFT_FIELDS
        }
        advanced_normalized = fast_path.normalize_exceptional_continuation_evidence(
            advanced,
            repository=REPOSITORY,
            reviewed_state=reviewed,
            validated_tree_sha="b" * 40,
            eligibility_evidence=eligibility,
            reanchor_authority=advanced_reanchor,
        )
        self.assertEqual(
            advanced_normalized["reanchor"][
                "historical_accepted_main_base_sha"
            ],
            "aa7d9e4485abbceed01136cd81fdbbd353f877bc",
        )
        for label, mutate in (
            (
                "unbound",
                lambda item: (
                    item["reanchor"].pop("historical_accepted_main_base_sha"),
                    item["reanchor"].pop("current_protected_main_base_sha"),
                ),
            ),
            (
                "substituted",
                lambda item: item["reanchor"].update(
                    current_protected_main_base_sha="f" * 40
                ),
            ),
            (
                "provider substituted",
                lambda item: item["reanchor"].update(
                    provider_reaction_replacement_digest="f" * 64
                ),
            ),
        ):
            changed_advanced = copy.deepcopy(advanced)
            mutate(changed_advanced)
            with self.subTest(advanced_base=label), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.normalize_exceptional_continuation_evidence(
                    changed_advanced,
                    repository=REPOSITORY,
                    reviewed_state=reviewed,
                    validated_tree_sha="b" * 40,
                    eligibility_evidence=eligibility,
                    reanchor_authority=advanced_reanchor,
                )
        changed = copy.deepcopy(value)
        changed["thread_ids"] = ["PRRT_REJECTED_1"]
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.normalize_exceptional_continuation_evidence(
                changed,
                repository=REPOSITORY,
                reviewed_state=reviewed,
                validated_tree_sha="b" * 40,
                eligibility_evidence=eligibility,
                reanchor_authority=reanchor,
            )

        collision = copy.deepcopy(value)
        collision.pop("reanchor")
        collision.pop("finding_ids")
        collision.pop("thread_ids")
        collision.update(
            authorization_id="collision-continuation-1",
            trigger="IMMUTABLE_EVIDENCE_VERSION_COLLISION",
            collision_digest="9" * 64,
        )
        normalized_collision = fast_path.normalize_exceptional_continuation_evidence(
            collision,
            repository=REPOSITORY,
            reviewed_state=reviewed,
            validated_tree_sha="b" * 40,
            eligibility_evidence=eligibility,
        )
        self.assertEqual(
            normalized_collision["trigger"],
            "IMMUTABLE_EVIDENCE_VERSION_COLLISION",
        )
        self.assertEqual(normalized_collision["collision_digest"], "9" * 64)

    def test_continuation_successor_accepts_authenticated_provider_growth(
        self,
    ) -> None:
        request, _authorization = continuation_inputs()
        reviewed = fast_path.verify_reviewed_state_evidence(
            request["continuation_evidence"]["reviewed_state_evidence"]
        )
        provider = {
            "login": "chatgpt-codex-connector",
            "node_id": "BOT_CODEX",
            "database_id": 199175422,
        }
        requester = {
            "login": "delivery-user",
            "node_id": "USER_DELIVERY",
            "database_id": 7,
        }
        code_quality = {
            "login": "github-code-quality",
            "node_id": "BOT_CODE_QUALITY",
            "database_id": 223894421,
        }
        reviewed.feedback["conversation_comments"].append(
            {
                "node_id": "IC_CODEX_SUMMARY",
                "body_digest": "4" * 64,
                "actor": provider,
                "updated_at": "2026-09-08T20:00:00Z",
                "reactions": [],
            }
        )
        reviewed.refresh_digests()
        current_feedback = copy.deepcopy(reviewed.feedback)
        current_feedback["reviews"].append(
            {
                "node_id": "PRR_RESULTING_HEAD",
                "body_digest": fast_path.digest_text(""),
                "actor": code_quality,
                "state": "COMMENTED",
                "commit_oid": NEXT_HEAD,
                "reactions": [],
            }
        )
        summary = (
            "<!-- codex-pull-request-review-summary -->\n"
            '<!-- codex-security-review:v1 '
            f'{{"headSha":"{NEXT_HEAD}","status":"completed"}} -->\n'
            "| Review | Status | Commit | Review trigger |\n"
            "| --- | --- | --- | --- |\n"
            "| **Code Review** | **Completed** | head | manual |\n"
            "| **Security Review** | **Completed** | head | manual |"
        )
        current_feedback["conversation_comments"][0].update(
            body_digest=fast_path.digest_text(summary),
            updated_at="2026-09-08T22:00:00Z",
        )
        transport_comments = (
            ("IC_CODE_REQUEST", "@codex review", requester),
            ("IC_SECURITY_REQUEST", "@codex security review", requester),
            (
                "IC_CODE_RESULT",
                "Codex Review: Didn't find any major issues.\n\n"
                f"**Reviewed commit:** `{NEXT_HEAD[:10]}`",
                provider,
            ),
            (
                "IC_SECURITY_RESULT",
                "### 🛡️ Codex Security Review\n\n"
                "No security issues were found in this pull request.\n\n"
                f"**Reviewed commit:** `{NEXT_HEAD[:10]}`",
                provider,
            ),
        )
        for node_id, body, actor in transport_comments:
            current_feedback["conversation_comments"].append(
                {
                    "node_id": node_id,
                    "body_digest": fast_path.digest_text(body),
                    "actor": actor,
                    "updated_at": None,
                    "reactions": [],
                }
            )
        current_feedback["threads"].append(
            {
                "node_id": "PRRT_RESULTING_HEAD",
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "node_id": "PRRC_RESULTING_HEAD",
                        "body_digest": "a" * 64,
                        "actor": code_quality,
                        "reply_to_id": None,
                        "reactions": [],
                    }
                ],
            }
        )
        current = fast_path.StableFeedbackState(
            repository=reviewed.repository,
            pull_request_number=reviewed.pull_request_number,
            head_sha=NEXT_HEAD,
            base_ref=reviewed.base_ref,
            base_sha=reviewed.base_sha,
            pr_state="OPEN",
            feedback=current_feedback,
        )

        fast_path.verify_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=NEXT_HEAD,
            authorized_thread_ids=["PRRT_CONTINUATION_1"],
            successor_safety_evidence={
                "schema_version": "1.0",
                "repository": REPOSITORY,
                "pull_request_number": PR,
                "predecessor_state_digest": reviewed.state_digest,
                "resulting_head_sha": NEXT_HEAD,
                "resulting_state_digest": current.state_digest,
                "provider_transport": [
                    {
                        "role": "CODEX_SUMMARY_UPDATE",
                        "kind": "CONVERSATION_COMMENT",
                        "node_id": "IC_CODEX_SUMMARY",
                        "body": summary,
                    },
                    {
                        "role": "CODEX_REVIEW_REQUEST",
                        "kind": "CONVERSATION_COMMENT",
                        "node_id": "IC_CODE_REQUEST",
                        "body": "@codex review",
                    },
                    {
                        "role": "CODEX_SECURITY_REVIEW_REQUEST",
                        "kind": "CONVERSATION_COMMENT",
                        "node_id": "IC_SECURITY_REQUEST",
                        "body": "@codex security review",
                    },
                    {
                        "role": "CODEX_CODE_REVIEW_RESULT",
                        "kind": "CONVERSATION_COMMENT",
                        "node_id": "IC_CODE_RESULT",
                        "body": "Codex Review: Didn't find any major issues.\n\n"
                        f"**Reviewed commit:** `{NEXT_HEAD[:10]}`",
                    },
                    {
                        "role": "CODEX_SECURITY_REVIEW_RESULT",
                        "kind": "CONVERSATION_COMMENT",
                        "node_id": "IC_SECURITY_RESULT",
                        "body": "### 🛡️ Codex Security Review\n\n"
                        "No security issues were found in this pull request.\n\n"
                        f"**Reviewed commit:** `{NEXT_HEAD[:10]}`",
                    },
                    {
                        "role": "GITHUB_CODE_QUALITY_REVIEW",
                        "kind": "REVIEW",
                        "node_id": "PRR_RESULTING_HEAD",
                        "body": None,
                    },
                ],
                "successor_findings": [
                    {
                        "sources": [
                            {
                                "kind": "THREAD_COMMENT",
                                "node_id": "PRRC_RESULTING_HEAD",
                                "digest": "a" * 64,
                            }
                        ],
                        "classification_evidence": fast_path._seal_successor_classification(
                            repository=REPOSITORY,
                            delivery_issue_number=ISSUE,
                            pull_request_number=PR,
                            head_sha=NEXT_HEAD,
                            finding_id="PRRC_RESULTING_HEAD",
                            finding_evidence_digest="b" * 64,
                            thread_id="PRRT_RESULTING_HEAD",
                            top_level_comment_node_id="PRRC_RESULTING_HEAD",
                            finding_body_digest="a" * 64,
                            reply_count=0,
                            is_resolved=False,
                            is_outdated=False,
                            classification="INVALID_FALSE_OR_MISLEADING",
                            disposition="DISPROVEN_WITH_EVIDENCE",
                            technically_blocking=False,
                            technical_blockers=(),
                            classification_evidence_digest="c" * 64,
                            source_bindings=(("THREAD_COMMENT", "PRRC_RESULTING_HEAD", "a" * 64, "PRRT_RESULTING_HEAD"),),
                        ),
                    }
                ],
            },
        )

    def test_continuation_provider_growth_reaches_orchestration_without_scope_expansion(
        self,
    ) -> None:
        reviewed, current, successor = authenticated_provider_growth()
        request, authorization = continuation_inputs()
        request["continuation_evidence"]["reviewed_state_evidence"] = (
            reviewed.to_dict()
        )
        eligibility = request["continuation_evidence"]["eligibility_evidence"]
        eligibility["reviewed_state_digest"] = reviewed.state_digest
        authorization["scope"].update(
            reviewed_state_digest=reviewed.state_digest,
            reviewed_feedback_digest=reviewed.feedback_digest,
            eligibility_evidence_digest=fast_path.digest_json(eligibility),
        )
        request["continuation_evidence"]["successor_safety_evidence"] = successor

        with mock.patch.object(
            orchestration,
            "_authenticate_successor_safety_evidence",
            return_value=successor,
        ):
            decision = orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                request,
                current_reader=current_reader(
                    current_lifecycle(exceptional_recoveries=1)
                ),
                feedback_reader=lambda _repository, _pull_request: current,
                authorization_verifier=fixture_authorization_verifier,
            )

        self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
        self.assertFalse(decision.request_review)
        self.assertEqual(
            authorization["scope"]["finding_ids"], ["F-CONTINUATION-1"]
        )
        self.assertNotIn("PRRC_RESULTING_HEAD", authorization["scope"]["finding_ids"])

    def test_successor_classification_uses_existing_detached_signature_authority(
        self,
    ) -> None:
        reviewed, current, prepared = authenticated_provider_growth()
        sealed = prepared["successor_findings"][0]["classification_evidence"]
        raw = copy.deepcopy(prepared)
        raw["classification_signer"] = {
            "kind": "SSH_PRINCIPAL",
            "identity": "aroviqen@secpal.app",
        }
        raw["successor_findings"] = [
            {
                "sources": copy.deepcopy(prepared["successor_findings"][0]["sources"]),
                "classification_artifact": base64.b64encode(b"{}\n").decode(),
                "classification_signature": base64.b64encode(b"signature").decode(),
            }
        ]
        verified = late_disposition.SuccessorClassificationEvidence(
            evidence_digest=sealed.classification_evidence_digest,
            repository=sealed.repository,
            delivery_issue_number=sealed.delivery_issue_number,
            pull_request_number=sealed.pull_request_number,
            head_sha=sealed.head_sha,
            finding_id=sealed.finding_id,
            finding_evidence_digest=sealed.finding_evidence_digest,
            thread=late_disposition.ThreadAuthorization(
                thread_id=sealed.thread_id,
                top_level_comment_node_id=sealed.top_level_comment_node_id,
                top_level_comment_database_id=1,
                finding_body_digest=sealed.finding_body_digest,
                reply_state_digest=fast_path.digest_json([]),
                reply_count=sealed.reply_count,
                is_resolved=False,
                is_outdated=sealed.is_outdated,
                classification=sealed.classification,
                disposition=sealed.disposition,
                technically_blocking=False,
                classification_evidence_digest=sealed.classification_evidence_digest,
            ),
            technical_blockers=(),
            predecessor_state_digest=reviewed.state_digest,
            resulting_state_digest=current.state_digest,
            sources=(("THREAD_COMMENT", "PRRC_RESULTING_HEAD", "a" * 64, "PRRT_RESULTING_HEAD"),),
        )
        with (
            mock.patch.object(
                orchestration,
                "_successor_classification_signer",
                return_value=late_disposition.SignerIdentity("ssh", "SHA256:fixture"),
            ),
            mock.patch.object(
                late_disposition,
                "parse_successor_classification_artifact",
                return_value=verified,
            ),
        ):
            authenticated = orchestration._authenticate_successor_safety_evidence(
                raw,
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                predecessor_state_digest=reviewed.state_digest,
                resulting_head_sha=NEXT_HEAD,
                resulting_state_digest=current.state_digest,
            )
        self.assertIsInstance(
            authenticated["successor_findings"][0]["classification_evidence"],
            fast_path.VerifiedSuccessorClassification,
        )

        reanchored_raw = copy.deepcopy(raw)
        reanchored_raw["schema_version"] = "1.1"
        with (
            mock.patch.object(
                orchestration,
                "_successor_classification_signer",
                return_value=late_disposition.SignerIdentity(
                    "ssh", "SHA256:fixture"
                ),
            ),
            mock.patch.object(
                late_disposition,
                "parse_successor_classification_artifact",
                return_value=verified,
            ) as reanchored_parser,
        ):
            reanchored_authenticated = (
                orchestration._authenticate_successor_safety_evidence(
                    reanchored_raw,
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_state_digest=reviewed.state_digest,
                    resulting_head_sha=NEXT_HEAD,
                    resulting_state_digest=current.state_digest,
                    reanchored_classified_review=True,
                )
            )
        reanchored_parser.assert_called_once()
        self.assertEqual(reanchored_authenticated["schema_version"], "1.1")
        with self.assertRaisesRegex(
            orchestration.LifecycleOrchestrationError,
            "unknown or missing fields",
        ):
            orchestration._authenticate_successor_safety_evidence(
                reanchored_raw,
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                predecessor_state_digest=reviewed.state_digest,
                resulting_head_sha=NEXT_HEAD,
                resulting_state_digest=current.state_digest,
            )

        _anchor, _live, complete_pr_905 = (
            authenticated_pr_905_classified_codex_review()
        )
        predecessor_growth_raw = copy.deepcopy(reanchored_raw)
        predecessor_growth_raw["schema_version"] = "1.2"
        predecessor_growth_raw["predecessor_provider_feedback"] = copy.deepcopy(
            complete_pr_905["predecessor_provider_feedback"]
        )
        predecessor_growth_raw["provider_completion_reaction_removal"] = (
            copy.deepcopy(
                complete_pr_905["provider_completion_reaction_removal"]
            )
        )
        reanchor_authority = orchestration.VerifiedRejectedContinuationReanchor(
            evidence_digest="7" * 64,
            original_pull_request=901,
            replacement_pull_request=905,
            rejected_candidate_head_sha="c" * 40,
            rejected_candidate_tree_sha="d" * 40,
            rejected_continuation_evidence_digest="1" * 64,
            rejected_validation_receipt_digest="2" * 64,
            rejected_final_attestation_digest="3" * 64,
            rejected_state_digest="4" * 64,
            replacement_state_digest="5" * 64,
            material_finding_ids=tuple(
                PR_905_CORRECTION_AUTHORITY["material_finding_ids"]
            ),
            material_thread_ids=tuple(
                f"PRRT_REJECTED_{index}" for index in range(1, 5)
            ),
            finding_source_digest=PR_905_CORRECTION_AUTHORITY[
                "finding_source_digest"
            ],
        )
        with (
            mock.patch.object(
                orchestration,
                "_successor_classification_signer",
                return_value=late_disposition.SignerIdentity(
                    "ssh", "SHA256:fixture"
                ),
            ),
            mock.patch.object(
                late_disposition,
                "parse_successor_classification_artifact",
                return_value=verified,
            ),
        ):
            predecessor_growth_authenticated = (
                orchestration._authenticate_successor_safety_evidence(
                    predecessor_growth_raw,
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_state_digest=reviewed.state_digest,
                    resulting_head_sha=NEXT_HEAD,
                    resulting_state_digest=current.state_digest,
                    reanchored_classified_review=True,
                    predecessor_correction_authority=reanchor_authority,
                )
            )
        self.assertEqual(
            predecessor_growth_authenticated["predecessor_provider_feedback"],
            complete_pr_905["predecessor_provider_feedback"],
        )

        wrong_correction = copy.deepcopy(predecessor_growth_raw)
        wrong_correction["predecessor_provider_feedback"]["correction_authority"][
            "finding_source_digest"
        ] = "f" * 64
        with self.assertRaisesRegex(
            orchestration.LifecycleOrchestrationError,
            "differs from re-anchor authority",
        ):
            orchestration._authenticate_successor_safety_evidence(
                wrong_correction,
                repository=REPOSITORY,
                delivery_issue=ISSUE,
                pull_request=PR,
                predecessor_state_digest=reviewed.state_digest,
                resulting_head_sha=NEXT_HEAD,
                resulting_state_digest=current.state_digest,
                reanchored_classified_review=True,
                predecessor_correction_authority=reanchor_authority,
            )

        rejected_raw = copy.deepcopy(raw)
        rejected_raw["schema_version"] = "1.1"
        material_thread = late_disposition.ThreadAuthorization(
            **{
                **verified.thread.__dict__,
                "classification": "IN_CONTRACT_DEFECT",
                "disposition": "CANDIDATE_REJECTED_BEFORE_PUBLICATION",
                "technically_blocking": True,
            }
        )
        material_verified = late_disposition.SuccessorClassificationEvidence(
            **{
                **verified.__dict__,
                "thread": material_thread,
                "technical_blockers": ("P2",),
            }
        )
        with (
            mock.patch.object(
                orchestration,
                "_successor_classification_signer",
                return_value=late_disposition.SignerIdentity(
                    "ssh", "SHA256:fixture"
                ),
            ),
            mock.patch.object(
                late_disposition,
                "parse_rejected_successor_classification_artifact",
                return_value=material_verified,
            ) as rejected_parser,
        ):
            rejected_authenticated = (
                orchestration._authenticate_rejected_successor_safety_evidence(
                    rejected_raw,
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_state_digest=reviewed.state_digest,
                    resulting_head_sha=NEXT_HEAD,
                    resulting_state_digest=current.state_digest,
                )
            )
        rejected_parser.assert_called_once()
        self.assertTrue(
            rejected_authenticated["successor_findings"][0][
                "classification_evidence"
            ].technically_blocking
        )

        replacement_raw = copy.deepcopy(rejected_raw)
        replacement_raw["schema_version"] = "1.2"
        replacement_raw["provider_completion_reaction_replacement"] = {
            "provider_login": "chatgpt-codex-connector",
            "reaction_content": "THUMBS_UP",
            "removed_reaction_id": "REACTION_CODEX_PREDECESSOR_COMPLETE",
            "replacement_reaction_id": "REA_lAHOQFR1MM8AAAABQu3eG84d1ZDA",
        }
        with (
            mock.patch.object(
                orchestration,
                "_successor_classification_signer",
                return_value=late_disposition.SignerIdentity(
                    "ssh", "SHA256:fixture"
                ),
            ),
            mock.patch.object(
                late_disposition,
                "parse_rejected_successor_classification_artifact",
                return_value=material_verified,
            ),
        ):
            replacement_authenticated = (
                orchestration._authenticate_rejected_successor_safety_evidence(
                    replacement_raw,
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_state_digest=reviewed.state_digest,
                    resulting_head_sha=NEXT_HEAD,
                    resulting_state_digest=current.state_digest,
                )
            )
        self.assertEqual(
            replacement_authenticated[
                "provider_completion_reaction_replacement"
            ]["removed_reaction_id"],
            "REACTION_CODEX_PREDECESSOR_COMPLETE",
        )

    def test_successor_classification_parser_binds_exact_sources_and_state(self) -> None:
        signer = late_disposition.SignerIdentity("ssh", "SHA256:fixture")
        artifact = {
            "schema_version": "1.2",
            "kind": "LATE_FEEDBACK_CLASSIFICATION",
            "repository": REPOSITORY,
            "delivery_issue_number": ISSUE,
            "pull_request_number": PR,
            "head_sha": NEXT_HEAD,
            "predecessor_state_digest": "1" * 64,
            "resulting_state_digest": "2" * 64,
            "delivery_signer": {
                "format": "ssh",
                "fingerprint": signer.fingerprint,
            },
            "authorized_purpose": "AUTHENTICATE_CONTINUATION_SUCCESSOR_SAFETY",
            "finding_id": "REA_SUCCESSOR",
            "finding_evidence_digest": "3" * 64,
            "thread": {
                "thread_id": None,
                "top_level_comment_node_id": None,
                "top_level_comment_database_id": None,
                "finding_body_digest": None,
                "reply_state_digest": fast_path.digest_json([]),
                "reply_count": 0,
                "is_resolved": None,
                "is_outdated": None,
                "classification": "INFORMATIONAL",
                "disposition": "NON_ACTIONABLE",
                "technically_blocking": False,
                "technical_blockers": [],
            },
            "sources": [
                {
                    "kind": "CONVERSATION_REACTION",
                    "node_id": "REA_SUCCESSOR",
                    "digest": "4" * 64,
                    "thread_id": None,
                }
            ],
        }
        canonical = late_disposition.canonical_json_bytes(artifact)
        with mock.patch.object(
            late_disposition, "verify_detached_signature", return_value=canonical
        ):
            verified = late_disposition.parse_successor_classification_artifact(
                Path("unused.json"),
                Path("unused.sig"),
                expected_signer=signer,
                repository=REPOSITORY,
                delivery_issue_number=ISSUE,
                pull_request_number=PR,
                head_sha=NEXT_HEAD,
                predecessor_state_digest="1" * 64,
                resulting_state_digest="2" * 64,
            )
        self.assertEqual(
            verified.sources,
            (("CONVERSATION_REACTION", "REA_SUCCESSOR", "4" * 64, None),),
        )

        changed = copy.deepcopy(artifact)
        changed["resulting_state_digest"] = "5" * 64
        with (
            mock.patch.object(
                late_disposition,
                "verify_detached_signature",
                return_value=late_disposition.canonical_json_bytes(changed),
            ),
            self.assertRaises(late_disposition.LateDispositionError),
        ):
            late_disposition.parse_successor_classification_artifact(
                Path("unused.json"),
                Path("unused.sig"),
                expected_signer=signer,
                repository=REPOSITORY,
                delivery_issue_number=ISSUE,
                pull_request_number=PR,
                head_sha=NEXT_HEAD,
                predecessor_state_digest="1" * 64,
                resulting_state_digest="2" * 64,
            )

    def test_rejected_successor_classification_uses_distinct_material_purpose(
        self,
    ) -> None:
        signer = late_disposition.SignerIdentity("ssh", "SHA256:fixture")
        artifact = {
            "schema_version": "1.3",
            "kind": "LATE_FEEDBACK_CLASSIFICATION",
            "repository": REPOSITORY,
            "delivery_issue_number": ISSUE,
            "pull_request_number": PR,
            "head_sha": NEXT_HEAD,
            "predecessor_state_digest": "1" * 64,
            "resulting_state_digest": "2" * 64,
            "delivery_signer": {
                "format": "ssh",
                "fingerprint": signer.fingerprint,
            },
            "authorized_purpose": "AUTHENTICATE_REJECTED_CONTINUATION_CANDIDATE",
            "finding_id": "F-MATERIAL-REJECTION",
            "finding_evidence_digest": "3" * 64,
            "thread": {
                "thread_id": "PRRT_REJECTED_1",
                "top_level_comment_node_id": "F-MATERIAL-REJECTION",
                "top_level_comment_database_id": 1,
                "finding_body_digest": "4" * 64,
                "reply_state_digest": fast_path.digest_json([]),
                "reply_count": 0,
                "is_resolved": False,
                "is_outdated": False,
                "classification": "IN_CONTRACT_DEFECT",
                "disposition": "CANDIDATE_REJECTED_BEFORE_PUBLICATION",
                "technically_blocking": True,
                "technical_blockers": ["P2"],
            },
            "sources": [
                {
                    "kind": "THREAD_COMMENT",
                    "node_id": "F-MATERIAL-REJECTION",
                    "digest": "4" * 64,
                    "thread_id": "PRRT_REJECTED_1",
                }
            ],
        }
        canonical = late_disposition.canonical_json_bytes(artifact)
        with mock.patch.object(
            late_disposition, "verify_detached_signature", return_value=canonical
        ):
            verified = (
                late_disposition.parse_rejected_successor_classification_artifact(
                    Path("unused.json"),
                    Path("unused.sig"),
                    expected_signer=signer,
                    repository=REPOSITORY,
                    delivery_issue_number=ISSUE,
                    pull_request_number=PR,
                    head_sha=NEXT_HEAD,
                    predecessor_state_digest="1" * 64,
                    resulting_state_digest="2" * 64,
                )
            )
        self.assertTrue(verified.thread.technically_blocking)
        self.assertEqual(verified.technical_blockers, ("P2",))

        with (
            mock.patch.object(
                late_disposition, "verify_detached_signature", return_value=canonical
            ),
            self.assertRaises(late_disposition.LateDispositionError),
        ):
            late_disposition.parse_successor_classification_artifact(
                Path("unused.json"),
                Path("unused.sig"),
                expected_signer=signer,
                repository=REPOSITORY,
                delivery_issue_number=ISSUE,
                pull_request_number=PR,
                head_sha=NEXT_HEAD,
                predecessor_state_digest="1" * 64,
                resulting_state_digest="2" * 64,
            )

        broadened = copy.deepcopy(artifact)
        broadened["thread"]["classification"] = "VALID_ACTIONABLE"
        broadened["thread"]["disposition"] = "CORRECTED_AND_VERIFIED"
        with (
            mock.patch.object(
                late_disposition,
                "verify_detached_signature",
                return_value=late_disposition.canonical_json_bytes(broadened),
            ),
            self.assertRaisesRegex(
                late_disposition.LateDispositionError,
                "rejected successor classification decision is unsupported",
            ),
        ):
            late_disposition.parse_rejected_successor_classification_artifact(
                Path("unused.json"),
                Path("unused.sig"),
                expected_signer=signer,
                repository=REPOSITORY,
                delivery_issue_number=ISSUE,
                pull_request_number=PR,
                head_sha=NEXT_HEAD,
                predecessor_state_digest="1" * 64,
                resulting_state_digest="2" * 64,
            )

        stale = copy.deepcopy(artifact)
        stale["thread"]["is_outdated"] = True
        with (
            mock.patch.object(
                late_disposition,
                "verify_detached_signature",
                return_value=late_disposition.canonical_json_bytes(stale),
            ),
            self.assertRaisesRegex(
                late_disposition.LateDispositionError,
                "rejected successor classification decision is unsupported",
            ),
        ):
            late_disposition.parse_rejected_successor_classification_artifact(
                Path("unused.json"),
                Path("unused.sig"),
                expected_signer=signer,
                repository=REPOSITORY,
                delivery_issue_number=ISSUE,
                pull_request_number=PR,
                head_sha=NEXT_HEAD,
                predecessor_state_digest="1" * 64,
                resulting_state_digest="2" * 64,
            )

    def test_authenticated_reaction_growth_preserves_predecessor_comment(self) -> None:
        reviewed, current, evidence = authenticated_provider_growth()
        comment = current.feedback["threads"][0]["comments"][0]
        reaction = {
            "mutation_id": "REA_SUCCESSOR_CLASSIFIED",
            "content": "THUMBS_UP",
            "actor": {
                "login": "reviewer",
                "node_id": "ACTOR_REVIEWER",
                "database_id": 2,
            },
        }
        comment["reactions"].append(reaction)
        current.refresh_digests()
        evidence["resulting_state_digest"] = current.state_digest
        evidence["successor_findings"].append(
            {
                "sources": [
                    {
                        "kind": "THREAD_COMMENT_REACTION",
                        "node_id": reaction["mutation_id"],
                        "digest": fast_path.digest_json(reaction),
                    }
                ],
                "classification_evidence": fast_path._seal_successor_classification(
                    repository=REPOSITORY,
                    delivery_issue_number=ISSUE,
                    pull_request_number=PR,
                    head_sha=NEXT_HEAD,
                    finding_id="REA_SUCCESSOR_CLASSIFIED",
                    finding_evidence_digest="d" * 64,
                    thread_id=None,
                    top_level_comment_node_id=None,
                    finding_body_digest=None,
                    reply_count=0,
                    is_resolved=None,
                    is_outdated=None,
                    classification="INFORMATIONAL",
                    disposition="NON_ACTIONABLE",
                    technically_blocking=False,
                    technical_blockers=(),
                    classification_evidence_digest="e" * 64,
                    source_bindings=(("THREAD_COMMENT_REACTION", "REA_SUCCESSOR_CLASSIFIED", fast_path.digest_json(reaction), "PRRT_CONTINUATION_1"),),
                ),
            }
        )
        fast_path.verify_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=NEXT_HEAD,
            authorized_thread_ids=["PRRT_CONTINUATION_1"],
            successor_safety_evidence=evidence,
        )

    def test_continuation_successor_growth_fails_closed_for_tampering_and_laundering(
        self,
    ) -> None:
        def reject(label: str, mutate) -> None:
            reviewed, current, evidence = authenticated_provider_growth()
            mutate(reviewed, current, evidence)
            reviewed.refresh_digests()
            current.refresh_digests()
            evidence["predecessor_state_digest"] = reviewed.state_digest
            evidence["resulting_state_digest"] = current.state_digest
            with self.subTest(label=label), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.verify_stable_feedback_successor(
                    reviewed,
                    current,
                    resulting_head_sha=NEXT_HEAD,
                    authorized_thread_ids=["PRRT_CONTINUATION_1"],
                    successor_safety_evidence=evidence,
                )

        def predecessor_thread_removed(_reviewed, current, _evidence):
            current.feedback["threads"] = current.feedback["threads"][1:]

        def predecessor_comment_changed(_reviewed, current, _evidence):
            current.feedback["threads"][0]["comments"][0]["body_digest"] = "f" * 64

        def predecessor_reply_removed(_reviewed, current, _evidence):
            current.feedback["threads"][0]["comments"] = current.feedback["threads"][0][
                "comments"
            ][:1]

        def predecessor_reaction_changed(_reviewed, current, _evidence):
            current.feedback["threads"][0]["comments"][0]["reactions"][0][
                "content"
            ] = "THUMBS_DOWN"

        def predecessor_review_substituted(_reviewed, current, _evidence):
            current.feedback["reviews"][0]["node_id"] = "PRR_EQUAL_LOOKING_REPLACEMENT"

        def predecessor_source_replaced(_reviewed, current, _evidence):
            current.feedback["threads"][0]["node_id"] = "PRRT_EQUAL_LOOKING_REPLACEMENT"

        def cross_head(_reviewed, current, evidence):
            current.head_sha = "7" * 40
            evidence["resulting_head_sha"] = current.head_sha

        def cross_pr(_reviewed, current, evidence):
            current.pull_request_number = PR + 1
            evidence["pull_request_number"] = current.pull_request_number

        def wrong_head_provider(_reviewed, current, _evidence):
            current.feedback["reviews"][-1]["commit_oid"] = "7" * 40

        def replace_summary(current, evidence, body):
            current.feedback["conversation_comments"][0]["body_digest"] = (
                fast_path.digest_text(body)
            )
            for transport in evidence["provider_transport"]:
                if transport["role"] == "CODEX_SUMMARY_UPDATE":
                    transport["body"] = body

        def malformed_summary(_reviewed, current, evidence):
            replace_summary(current, evidence, "malformed provider summary")

        def nonterminal_summary(_reviewed, current, evidence):
            body = evidence["provider_transport"][0]["body"].replace(
                '"status":"completed"', '"status":"running"'
            )
            replace_summary(current, evidence, body)

        def duplicate_provider(_reviewed, _current, evidence):
            evidence["provider_transport"].append(
                copy.deepcopy(evidence["provider_transport"][1])
            )

        def user_masquerades_as_provider(_reviewed, current, _evidence):
            next(
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == "IC_CODE_RESULT"
            )["actor"] = {
                    "login": "delivery-user",
                    "node_id": "USER_DELIVERY",
                    "database_id": 7,
                }

        def unclassified_provider_finding(_reviewed, _current, evidence):
            evidence["successor_findings"] = []

        def material_provider_finding(_reviewed, _current, evidence):
            original = evidence["successor_findings"][0]["classification_evidence"]
            evidence["successor_findings"][0]["classification_evidence"] = (
                fast_path._seal_successor_classification(
                    **{
                        key: value
                        for key, value in original.__dict__.items()
                        if key != "_verification_seal"
                    }
                    | {"technically_blocking": True, "technical_blockers": ("P1",)}
                )
            )

        def unauthenticated_safe_assertion(_reviewed, _current, evidence):
            evidence["successor_findings"][0]["classification_evidence"] = {
                "classification": "INVALID_FALSE_OR_MISLEADING",
                "disposition": "DISPROVEN_WITH_EVIDENCE",
                "technically_blocking": False,
                "evidence_digest": "b" * 64,
            }

        def deleted_request_actor(_reviewed, current, _evidence):
            next(
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == "IC_CODE_REQUEST"
            )["actor"] = {"login": None, "node_id": None, "database_id": None}

        def unrelated_concurrent_comment(_reviewed, current, _evidence):
            current.feedback["conversation_comments"].append(
                {
                    "node_id": "IC_UNRELATED",
                    "body_digest": "e" * 64,
                    "actor": {
                        "login": "unrelated-user",
                        "node_id": "USER_UNRELATED",
                        "database_id": 9,
                    },
                    "updated_at": None,
                    "reactions": [],
                }
            )

        for label, mutate in (
            ("predecessor thread removed", predecessor_thread_removed),
            ("predecessor comment body changed", predecessor_comment_changed),
            ("predecessor reply removed", predecessor_reply_removed),
            ("predecessor reaction changed", predecessor_reaction_changed),
            ("predecessor review substituted", predecessor_review_substituted),
            ("equal-looking predecessor replacement", predecessor_source_replaced),
            ("cross-head predecessor replay", cross_head),
            ("cross-PR predecessor replay", cross_pr),
            ("wrong-head provider review", wrong_head_provider),
            ("malformed provider summary", malformed_summary),
            ("nonterminal provider state", nonterminal_summary),
            ("duplicate provider evidence", duplicate_provider),
            ("user transport masquerade", user_masquerades_as_provider),
            ("unclassified provider finding", unclassified_provider_finding),
            ("material provider finding", material_provider_finding),
            ("unauthenticated safe classification", unauthenticated_safe_assertion),
            ("deleted review requester", deleted_request_actor),
            ("unrelated concurrent feedback", unrelated_concurrent_comment),
        ):
            reject(label, mutate)

    def test_ordinary_successor_preserves_safe_classification_family(self) -> None:
        reviewed, current, evidence = authenticated_provider_growth()
        original = evidence["successor_findings"][0]["classification_evidence"]
        evidence["successor_findings"][0]["classification_evidence"] = (
            fast_path._seal_successor_classification(
                **{
                    key: value
                    for key, value in original.__dict__.items()
                    if key != "_verification_seal"
                }
                | {
                    "classification": "DUPLICATE",
                    "disposition": "DUPLICATE_OF_CANONICAL",
                }
            )
        )

        fast_path.verify_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=NEXT_HEAD,
            authorized_thread_ids=["PRRT_CONTINUATION_1"],
            successor_safety_evidence=evidence,
        )

    def test_rejected_successor_safety_authenticates_only_complete_material_findings(
        self,
    ) -> None:
        reviewed, rejected, evidence = authenticated_provider_growth()
        safe = evidence["successor_findings"][0]["classification_evidence"]
        evidence["schema_version"] = "1.1"
        evidence["successor_findings"][0]["classification_evidence"] = (
            fast_path._seal_successor_classification(
                **{
                    key: value
                    for key, value in safe.__dict__.items()
                    if key != "_verification_seal"
                }
                | {
                    "classification": "IN_CONTRACT_DEFECT",
                    "disposition": "CANDIDATE_REJECTED_BEFORE_PUBLICATION",
                    "technically_blocking": True,
                    "technical_blockers": ("P2",),
                }
            )
        )

        material = fast_path.verify_rejected_stable_feedback_successor(
            reviewed,
            rejected,
            resulting_head_sha=NEXT_HEAD,
            rejected_successor_evidence=evidence,
        )

        self.assertEqual(material.finding_ids, ("PRRC_RESULTING_HEAD",))
        self.assertEqual(material.thread_ids, ("PRRT_RESULTING_HEAD",))
        self.assertEqual(
            material.source_bindings,
            (("THREAD_COMMENT", "PRRC_RESULTING_HEAD", "a" * 64, "PRRT_RESULTING_HEAD"),),
        )

        finding_state = copy.deepcopy(rejected)
        finding_evidence = copy.deepcopy(evidence)
        finding_state.feedback["conversation_comments"] = [
            item
            for item in finding_state.feedback["conversation_comments"]
            if item["node_id"] not in {"IC_CODE_RESULT", "IC_SECURITY_RESULT"}
        ]
        finding_evidence["provider_transport"] = [
            item
            for item in finding_evidence["provider_transport"]
            if item["role"]
            not in {"CODEX_CODE_REVIEW_RESULT", "CODEX_SECURITY_REVIEW_RESULT"}
        ]
        provider = {
            "login": "chatgpt-codex-connector",
            "node_id": "BOT_CODEX",
            "database_id": 3,
        }
        for node_id, heading in (
            ("PRR_CODE_FINDINGS", "### 💡 Codex Review"),
            ("PRR_SECURITY_FINDINGS", "### 🛡️ Codex Security Review"),
        ):
            body = (
                f"{heading}\n\nMaterial findings were emitted.\n\n"
                f"**Reviewed commit:** `{NEXT_HEAD[:10]}`"
            )
            finding_state.feedback["reviews"].append(
                {
                    "node_id": node_id,
                    "body_digest": fast_path.digest_text(body),
                    "actor": provider,
                    "state": "COMMENTED",
                    "commit_oid": NEXT_HEAD,
                    "reactions": [],
                }
            )
            finding_evidence["provider_transport"].append(
                {
                    "role": "CODEX_REVIEW",
                    "kind": "REVIEW",
                    "node_id": node_id,
                    "body": body,
                }
            )
        finding_state.refresh_digests()
        finding_evidence["resulting_state_digest"] = finding_state.state_digest
        finding_material = fast_path.verify_rejected_stable_feedback_successor(
            reviewed,
            finding_state,
            resulting_head_sha=NEXT_HEAD,
            rejected_successor_evidence=finding_evidence,
        )
        self.assertEqual(finding_material.finding_ids, material.finding_ids)

        review_body = next(
            item["body"]
            for item in finding_evidence["provider_transport"]
            if item["node_id"] == "PRR_CODE_FINDINGS"
        )
        review_source = (
            "REVIEW",
            "PRR_CODE_FINDINGS",
            fast_path.digest_text(review_body),
            None,
        )
        dual_role_evidence = copy.deepcopy(finding_evidence)
        dual_role_classification = dual_role_evidence["successor_findings"][0][
            "classification_evidence"
        ]
        dual_role_evidence["successor_findings"][0]["classification_evidence"] = (
            fast_path._seal_successor_classification(
                **{
                    key: value
                    for key, value in dual_role_classification.__dict__.items()
                    if key not in {"_verification_seal", "source_bindings"}
                },
                source_bindings=(
                    *dual_role_classification.source_bindings,
                    review_source,
                ),
            )
        )
        dual_role_evidence["successor_findings"][0]["sources"].append(
            {
                "kind": review_source[0],
                "node_id": review_source[1],
                "digest": review_source[2],
            }
        )
        fast_path.verify_rejected_stable_feedback_successor(
            reviewed,
            finding_state,
            resulting_head_sha=NEXT_HEAD,
            rejected_successor_evidence=dual_role_evidence,
        )

        shared_thread_state = copy.deepcopy(rejected)
        shared_thread_evidence = copy.deepcopy(evidence)
        root = shared_thread_evidence["successor_findings"][0][
            "classification_evidence"
        ]
        shared_thread_state.feedback["threads"][-1]["comments"].append(
            {
                "node_id": "PRRC_SECOND_FINDING",
                "body_digest": "d" * 64,
                "actor": {
                    "login": "github-code-quality",
                    "node_id": "BOT_CODE_QUALITY",
                    "database_id": 223894421,
                },
                "reply_to_id": "PRRC_RESULTING_HEAD",
                "reactions": [],
            }
        )
        shared_thread_evidence["successor_findings"][0][
            "classification_evidence"
        ] = fast_path._seal_successor_classification(
            **{
                key: value
                for key, value in root.__dict__.items()
                if key not in {"_verification_seal", "reply_count"}
            },
            reply_count=1,
        )
        shared_thread_evidence["successor_findings"].append(
            {
                "sources": [
                    {
                        "kind": "THREAD_COMMENT",
                        "node_id": "PRRC_SECOND_FINDING",
                        "digest": "d" * 64,
                    }
                ],
                "classification_evidence": fast_path._seal_successor_classification(
                    **{
                        key: value
                        for key, value in root.__dict__.items()
                        if key
                        not in {
                            "_verification_seal",
                            "finding_id",
                            "finding_evidence_digest",
                            "reply_count",
                            "classification_evidence_digest",
                            "source_bindings",
                        }
                    },
                    finding_id="F-SECOND-IN-SHARED-THREAD",
                    finding_evidence_digest="e" * 64,
                    reply_count=1,
                    classification_evidence_digest="f" * 64,
                    source_bindings=(
                        (
                            "THREAD_COMMENT",
                            "PRRC_SECOND_FINDING",
                            "d" * 64,
                            "PRRT_RESULTING_HEAD",
                        ),
                    ),
                ),
            }
        )
        shared_thread_state.refresh_digests()
        shared_thread_evidence["resulting_state_digest"] = (
            shared_thread_state.state_digest
        )
        shared_thread_material = fast_path.verify_rejected_stable_feedback_successor(
            reviewed,
            shared_thread_state,
            resulting_head_sha=NEXT_HEAD,
            rejected_successor_evidence=shared_thread_evidence,
        )
        self.assertEqual(
            shared_thread_material.thread_ids,
            ("PRRT_RESULTING_HEAD",),
        )

        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "material successor finding"
        ):
            fast_path.verify_stable_feedback_successor(
                reviewed,
                rejected,
                resulting_head_sha=NEXT_HEAD,
                authorized_thread_ids=["PRRT_RESULTING_HEAD"],
                successor_safety_evidence={**evidence, "schema_version": "1.0"},
            )

        for label, mutate in (
            ("non-material", None),
            (
                "unclassified",
                lambda item: item.update(successor_findings=[]),
            ),
            (
                "substituted source",
                lambda item: item["successor_findings"][0]["sources"][0].update(
                    digest="f" * 64
                ),
            ),
        ):
            changed = copy.deepcopy(evidence)
            if label == "non-material":
                classification = changed["successor_findings"][0][
                    "classification_evidence"
                ]
                changed["successor_findings"][0]["classification_evidence"] = (
                    fast_path._seal_successor_classification(
                        **{
                            key: value
                            for key, value in classification.__dict__.items()
                            if key != "_verification_seal"
                        }
                        | {
                            "technically_blocking": False,
                            "technical_blockers": (),
                        }
                    )
                )
            elif mutate is not None:
                mutate(changed)
            with self.subTest(label=label), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.verify_rejected_stable_feedback_successor(
                    reviewed,
                    rejected,
                    resulting_head_sha=NEXT_HEAD,
                    rejected_successor_evidence=changed,
                )

        missing_provider = copy.deepcopy(evidence)
        missing_provider["provider_transport"] = []
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "provider acquisition transport"
        ):
            fast_path.verify_rejected_stable_feedback_successor(
                reviewed,
                rejected,
                resulting_head_sha=NEXT_HEAD,
                rejected_successor_evidence=missing_provider,
            )
        with self.assertRaises(fast_path.SecurityBlocker):
            fast_path.verify_rejected_stable_feedback_successor(
                reviewed,
                rejected,
                resulting_head_sha=NEXT_HEAD,
                rejected_successor_evidence=None,
            )

    def test_reanchored_corrected_successor_keeps_exact_provider_safety_mandatory(
        self,
    ) -> None:
        reviewed, current, evidence = authenticated_provider_growth()
        fast_path.verify_reanchored_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=NEXT_HEAD,
            successor_safety_evidence=evidence,
        )

        missing_provider = copy.deepcopy(evidence)
        missing_provider["provider_transport"] = []
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "provider acquisition transport"
        ):
            fast_path.verify_reanchored_stable_feedback_successor(
                reviewed,
                current,
                resulting_head_sha=NEXT_HEAD,
                successor_safety_evidence=missing_provider,
            )

        material = copy.deepcopy(evidence)
        classification = material["successor_findings"][0][
            "classification_evidence"
        ]
        material["successor_findings"][0]["classification_evidence"] = (
            fast_path._seal_successor_classification(
                **{
                    key: value
                    for key, value in classification.__dict__.items()
                    if key != "_verification_seal"
                }
                | {
                    "technically_blocking": True,
                    "technical_blockers": ("P1",),
                }
            )
        )
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker, "material successor finding"
        ):
            fast_path.verify_reanchored_stable_feedback_successor(
                reviewed,
                current,
                resulting_head_sha=NEXT_HEAD,
                successor_safety_evidence=material,
            )

        unchanged_feedback = fast_path.StableFeedbackState(
            repository=reviewed.repository,
            pull_request_number=reviewed.pull_request_number,
            head_sha=NEXT_HEAD,
            base_ref=reviewed.base_ref,
            base_sha=reviewed.base_sha,
            pr_state="OPEN",
            feedback=copy.deepcopy(reviewed.feedback),
        )
        empty_provider = {
            "schema_version": "1.0",
            "repository": reviewed.repository,
            "pull_request_number": reviewed.pull_request_number,
            "predecessor_state_digest": reviewed.state_digest,
            "resulting_head_sha": NEXT_HEAD,
            "resulting_state_digest": unchanged_feedback.state_digest,
            "provider_transport": [],
            "successor_findings": [],
        }
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker,
            "provider acquisition transport",
        ):
            fast_path.verify_reanchored_stable_feedback_successor(
                reviewed,
                unchanged_feedback,
                resulting_head_sha=NEXT_HEAD,
                successor_safety_evidence=empty_provider,
            )

    def test_accepted_main_rejects_complete_pr_905_predecessor_feedback_delta(
        self,
    ) -> None:
        reviewed, current, evidence = authenticated_pr_905_classified_codex_review()
        evidence["schema_version"] = "1.1"
        evidence.pop("predecessor_provider_feedback")
        evidence.pop("provider_completion_reaction_removal")

        with self.assertRaisesRegex(
            fast_path.SecurityBlocker,
            "successor feedback contains an unauthenticated addition",
        ):
            fast_path.verify_reanchored_stable_feedback_successor(
                reviewed,
                current,
                resulting_head_sha=current.head_sha,
                successor_safety_evidence=evidence,
            )

    def test_reanchored_successor_accepts_pr_905_classified_codex_review(
        self,
    ) -> None:
        reviewed, current, evidence = authenticated_pr_905_classified_codex_review()
        self.assertEqual(
            next(
                item["body_digest"]
                for item in current.feedback["reviews"]
                if item["node_id"] == "PRR_kwDOQFR1MM8AAAABNNvsIA"
            ),
            "7641566780ebf61fdc73ae1d1f57f7098cd5bdad0d2157ae203fbb52af8f58da",
        )
        self.assertEqual(
            next(
                item["body_digest"]
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == "IC_kwDOQFR1MM8AAAABT7Fdrg"
            ),
            "223004c82862671eab1209a31be2673fba7d7ad62ee750ed182c444e56686f07",
        )
        self.assertEqual(
            next(
                item["body_digest"]
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == "IC_kwDOQFR1MM8AAAABUBQgbA"
            ),
            "84f16d17de54b5b8cb629e37d3d19a9d154c7784e1e91a46de3171e3405f3ff7",
        )

        predecessor_growth_digest = verify_pr_905_successor(
            reviewed, current, evidence
        )
        self.assertRegex(predecessor_growth_digest or "", r"^[0-9a-f]{64}$")
        with self.assertRaisesRegex(
            fast_path.SecurityBlocker,
            "correction authority is unauthenticated",
        ):
            fast_path.verify_reanchored_stable_feedback_successor(
                reviewed,
                current,
                resulting_head_sha=current.head_sha,
                successor_safety_evidence=evidence,
                predecessor_correction_authority=PR_905_CORRECTION_AUTHORITY,
            )

        informational = copy.deepcopy(evidence)
        classification = informational["successor_findings"][1][
            "classification_evidence"
        ]
        informational["successor_findings"][1]["classification_evidence"] = (
            fast_path._seal_successor_classification(
                **{
                    key: value
                    for key, value in classification.__dict__.items()
                    if key != "_verification_seal"
                }
                | {
                    "classification": "INFORMATIONAL",
                    "disposition": "NON_ACTIONABLE",
                }
            )
        )
        verify_pr_905_successor(reviewed, current, informational)

    def test_reanchored_classified_codex_review_fails_closed(self) -> None:
        def replace_classification(evidence, index, **updates):
            original = evidence["successor_findings"][index][
                "classification_evidence"
            ]
            evidence["successor_findings"][index]["classification_evidence"] = (
                fast_path._seal_successor_classification(
                    **{
                        key: value
                        for key, value in original.__dict__.items()
                        if key != "_verification_seal"
                    }
                    | updates
                )
            )

        def code_review(current, evidence):
            review = next(
                item
                for item in current.feedback["reviews"]
                if item["node_id"] == "PRR_kwDOQFR1MM8AAAABNNvsIA"
            )
            transport = next(
                item
                for item in evidence["provider_transport"]
                if item["role"] == "CODEX_REVIEW"
            )
            return review, transport

        def missing_finding(_current, evidence):
            evidence["successor_findings"].pop()

        def review_without_suggestions(current, evidence):
            current.feedback["threads"] = current.feedback["threads"][:-2]
            evidence["successor_findings"] = []

        def source_only_addition(current, evidence, *, provider):
            node_id = (
                "IC_OMITTED_PROVIDER_RESULT"
                if provider
                else "IC_NON_PROVIDER_ADDITION"
            )
            body = (
                "Codex Review: Didn't find any major issues.\n\n"
                "**Reviewed commit:** `18a6d02d8c`"
                if provider
                else "additional source"
            )
            actor = (
                {
                    "login": "chatgpt-codex-connector",
                    "node_id": "BOT_kgDOC98s_g",
                    "database_id": 199175422,
                }
                if provider
                else {
                    "login": "delivery-user",
                    "node_id": "USER_DELIVERY",
                    "database_id": 7,
                }
            )
            digest = fast_path.digest_text(body)
            current.feedback["conversation_comments"].append(
                {
                    "node_id": node_id,
                    "body_digest": digest,
                    "actor": actor,
                    "updated_at": None,
                    "reactions": [],
                }
            )
            evidence["successor_findings"].append(
                {
                    "sources": [
                        {
                            "kind": "CONVERSATION_COMMENT",
                            "node_id": node_id,
                            "digest": digest,
                        }
                    ],
                    "classification_evidence": (
                        fast_path._seal_successor_classification(
                            repository=REPOSITORY,
                            delivery_issue_number=894,
                            pull_request_number=905,
                            head_sha=current.head_sha,
                            finding_id=node_id,
                            finding_evidence_digest="8" * 64,
                            thread_id=None,
                            top_level_comment_node_id=None,
                            finding_body_digest=None,
                            reply_count=0,
                            is_resolved=None,
                            is_outdated=None,
                            classification="INFORMATIONAL",
                            disposition="NON_ACTIONABLE",
                            technically_blocking=False,
                            technical_blockers=(),
                            classification_evidence_digest="9" * 64,
                            source_bindings=(
                                (
                                    "CONVERSATION_COMMENT",
                                    node_id,
                                    digest,
                                    None,
                                ),
                            ),
                        )
                    ),
                }
            )

        def omitted_provider_non_thread_addition(current, evidence):
            source_only_addition(current, evidence, provider=True)

        def non_provider_classified_addition(current, evidence):
            source_only_addition(current, evidence, provider=False)

        def non_provider_thread_source(current, evidence):
            reply_id = "PRRC_NON_PROVIDER_REPLY"
            digest = fast_path.digest_text("requester reply")
            current.feedback["threads"][-2]["comments"].append(
                {
                    "node_id": reply_id,
                    "body_digest": digest,
                    "actor": {
                        "login": "delivery-user",
                        "node_id": "USER_DELIVERY",
                        "database_id": 7,
                    },
                    "reply_to_id": "PRRC_kwDOQFR1MM7t72Mn",
                    "reactions": [],
                }
            )
            evidence["successor_findings"][0]["sources"].append(
                {
                    "kind": "THREAD_COMMENT",
                    "node_id": reply_id,
                    "digest": digest,
                }
            )
            original = evidence["successor_findings"][0][
                "classification_evidence"
            ]
            replace_classification(
                evidence,
                0,
                reply_count=1,
                source_bindings=original.source_bindings
                + (
                    (
                        "THREAD_COMMENT",
                        reply_id,
                        digest,
                        "PRRT_kwDOQFR1MM6hk-YJ",
                    ),
                ),
            )

        def extra_invented_finding_source(_current, evidence):
            evidence["successor_findings"][0]["sources"].append(
                {
                    "kind": "THREAD_COMMENT",
                    "node_id": "PRRC_CALLER_INVENTED",
                    "digest": "f" * 64,
                }
            )

        def repeated_finding(_current, evidence):
            evidence["successor_findings"].append(
                copy.deepcopy(evidence["successor_findings"][0])
            )

        def nonterminal_review(current, evidence):
            review, _transport = code_review(current, evidence)
            review["state"] = "PENDING"

        def wrong_provider(current, evidence):
            review, _transport = code_review(current, evidence)
            review["actor"] = {
                "login": "delivery-user",
                "node_id": "USER_DELIVERY",
                "database_id": 7,
            }

        def stale_review(current, evidence):
            review, _transport = code_review(current, evidence)
            review["commit_oid"] = "7" * 40

        def tampered_review_body(_current, evidence):
            _review, transport = code_review(_current, evidence)
            transport["body"] += "\ntampered"

        def replaced_review_identity(_current, evidence):
            _review, transport = code_review(_current, evidence)
            transport["node_id"] = "PRR_REPLACED"

        def nonterminal_summary(current, evidence):
            summary = next(
                item
                for item in evidence["provider_transport"]
                if item["role"] == "CODEX_SUMMARY_UPDATE"
            )
            summary["body"] = summary["body"].replace(
                '"status":"completed"', '"status":"running"'
            )
            next(
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == summary["node_id"]
            )["body_digest"] = fast_path.digest_text(summary["body"])

        def missing_request(current, evidence):
            node_id = "IC_kwDOQFR1MM8AAAABUBIbNg"
            current.feedback["conversation_comments"] = [
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] != node_id
            ]
            evidence["provider_transport"] = [
                item
                for item in evidence["provider_transport"]
                if item["node_id"] != node_id
            ]

        def wrong_request_provenance(current, _evidence):
            next(
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == "IC_kwDOQFR1MM8AAAABUBIbNg"
            )["actor"] = {
                "login": "chatgpt-codex-connector",
                "node_id": "BOT_kgDOC98s_g",
                "database_id": 199175422,
            }

        def synthetic_no_finding(current, evidence):
            body = (
                "Codex Review: Didn't find any major issues.\n\n"
                "**Reviewed commit:** `18a6d02d8c`"
            )
            current.feedback["conversation_comments"].append(
                {
                    "node_id": "IC_SYNTHETIC_CODE_RESULT",
                    "body_digest": fast_path.digest_text(body),
                    "actor": {
                        "login": "chatgpt-codex-connector",
                        "node_id": "BOT_kgDOC98s_g",
                        "database_id": 199175422,
                    },
                    "updated_at": None,
                    "reactions": [],
                }
            )
            evidence["provider_transport"].append(
                {
                    "role": "CODEX_CODE_REVIEW_RESULT",
                    "kind": "CONVERSATION_COMMENT",
                    "node_id": "IC_SYNTHETIC_CODE_RESULT",
                    "body": body,
                }
            )

        def provider_completion_reaction(current, evidence):
            current.feedback["pull_request_reactions"].append(
                {
                    "mutation_id": "REACTION_SYNTHETIC_COMPLETE",
                    "content": "THUMBS_UP",
                    "actor": {
                        "login": "chatgpt-codex-connector",
                        "node_id": "BOT_kgDOC98s_g",
                        "database_id": 199175422,
                    },
                }
            )
            evidence["provider_transport"].append(
                {
                    "role": "CODEX_COMPLETION_REACTION",
                    "kind": "PULL_REQUEST_REACTION",
                    "node_id": "REACTION_SYNTHETIC_COMPLETE",
                    "body": None,
                }
            )

        def material_security_review(current, evidence):
            security_result_id = "IC_kwDOQFR1MM8AAAABUBQgbA"
            current.feedback["conversation_comments"] = [
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] != security_result_id
            ]
            evidence["provider_transport"] = [
                item
                for item in evidence["provider_transport"]
                if item["node_id"] != security_result_id
            ]
            body = (
                "\n### 🛡️ Codex Security Review\n\n"
                "Security finding.\n\n"
                "**Reviewed commit:** `18a6d02d8c`"
            )
            current.feedback["reviews"].append(
                {
                    "node_id": "PRR_SECURITY_FINDING",
                    "body_digest": fast_path.digest_text(body),
                    "actor": {
                        "login": "chatgpt-codex-connector",
                        "node_id": "BOT_kgDOC98s_g",
                        "database_id": 199175422,
                    },
                    "state": "COMMENTED",
                    "commit_oid": current.head_sha,
                    "reactions": [],
                }
            )
            evidence["provider_transport"].append(
                {
                    "role": "CODEX_REVIEW",
                    "kind": "REVIEW",
                    "node_id": "PRR_SECURITY_FINDING",
                    "body": body,
                }
            )

        def unclassified_late_addition(current, _evidence):
            current.feedback["threads"].append(
                {
                    "node_id": "PRRT_LATE_ADDITION",
                    "is_resolved": False,
                    "is_outdated": False,
                    "comments": [
                        {
                            "node_id": "PRRC_LATE_ADDITION",
                            "body_digest": "f" * 64,
                            "actor": {
                                "login": "chatgpt-codex-connector",
                                "node_id": "BOT_kgDOC98s_g",
                                "database_id": 199175422,
                            },
                            "reply_to_id": None,
                            "reactions": [],
                        }
                    ],
                }
            )

        def material_finding(_current, evidence):
            replace_classification(
                evidence,
                0,
                technically_blocking=True,
                technical_blockers=("P1",),
            )

        def actionable_finding(_current, evidence):
            replace_classification(
                evidence,
                0,
                classification="VALID_ACTIONABLE",
                disposition="CORRECTED_AND_VERIFIED",
            )

        def resolved_finding(current, evidence):
            current.feedback["threads"][-2]["is_resolved"] = True
            replace_classification(evidence, 0, is_resolved=True)

        def wrong_pr(current, evidence):
            current.pull_request_number = 906
            evidence["pull_request_number"] = 906

        def wrong_head(current, evidence):
            current.head_sha = "7" * 40
            evidence["resulting_head_sha"] = current.head_sha

        def wrong_predecessor_binding(_current, evidence):
            evidence["predecessor_state_digest"] = "f" * 64

        def missing_security(current, evidence):
            node_id = "IC_kwDOQFR1MM8AAAABUBQgbA"
            current.feedback["conversation_comments"] = [
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] != node_id
            ]
            evidence["provider_transport"] = [
                item
                for item in evidence["provider_transport"]
                if item["node_id"] != node_id
            ]

        def predecessor_review(current, evidence):
            review = next(
                item
                for item in current.feedback["reviews"]
                if item["node_id"] == "PRR_kwDOQFR1MM8AAAABNJC0sw"
            )
            transport = evidence["predecessor_provider_feedback"][
                "provider_transport"
            ][0]
            return review, transport

        def wrong_predecessor_head(current, evidence):
            review, _transport = predecessor_review(current, evidence)
            review["commit_oid"] = current.head_sha

        def ambiguous_predecessor_head(current, evidence):
            review, _transport = predecessor_review(current, evidence)
            review["commit_oid"] = None

        def wrong_predecessor_provider(current, evidence):
            review, _transport = predecessor_review(current, evidence)
            review["actor"] = {
                "login": "chatgpt-codex-connector",
                "node_id": "BOT_kgDOC98s_g",
                "database_id": 199175422,
            }

        def changed_predecessor_body(_current, evidence):
            _review, transport = predecessor_review(_current, evidence)
            transport["body"] += "\nsubstituted"

        def missing_predecessor_review(_current, evidence):
            evidence["predecessor_provider_feedback"]["provider_transport"] = []

        def predecessor_feedback_older_than_anchor(current, _evidence):
            review = next(
                item
                for item in current.feedback["reviews"]
                if item["node_id"] == "PRR_kwDOQFR1MM8AAAABNJC0sw"
            )
            reviewed.feedback["reviews"].append(copy.deepcopy(review))

        def wrong_removed_reaction(_current, evidence):
            evidence["provider_completion_reaction_removal"][
                "removed_reaction_id"
            ] = "REA_OTHER"

        def wrong_reaction_provider(_current, evidence):
            evidence["provider_completion_reaction_removal"][
                "provider_login"
            ] = "different-provider"

        def wrong_reaction_content(_current, evidence):
            evidence["provider_completion_reaction_removal"][
                "reaction_content"
            ] = "HEART"

        def retained_completion_reaction(current, _evidence):
            current.feedback["pull_request_reactions"] = copy.deepcopy(
                reviewed.feedback["pull_request_reactions"]
            )

        def extra_predecessor_review(_current, evidence):
            evidence["predecessor_provider_feedback"]["provider_transport"].append(
                copy.deepcopy(
                    evidence["predecessor_provider_feedback"]["provider_transport"][0]
                )
            )

        def omitted_predecessor_finding(_current, evidence):
            evidence["predecessor_provider_feedback"]["material_findings"].pop()

        def cross_head_thread(_current, evidence):
            evidence["predecessor_provider_feedback"]["material_findings"][0] = (
                copy.deepcopy(evidence["successor_findings"][0])
            )

        def cross_pr_predecessor_thread(_current, evidence):
            evidence["predecessor_provider_feedback"]["material_findings"][0][
                "thread_id"
            ] = "PRRT_OTHER_PULL_REQUEST"

        def false_safe_predecessor_finding(_current, evidence):
            finding = evidence["predecessor_provider_feedback"][
                "material_findings"
            ].pop()
            evidence["successor_findings"].append(
                {
                    "sources": finding["sources"],
                    "classification_evidence": copy.deepcopy(
                        evidence["successor_findings"][0]["classification_evidence"]
                    ),
                }
            )

        def candidate_self_trust(_current, evidence):
            evidence["predecessor_provider_feedback"]["correction_authority"].update(
                reanchor_evidence_digest=_current.head_sha + "0" * 24
            )

        def wrong_rejected_authority(_current, evidence):
            evidence["predecessor_provider_feedback"]["correction_authority"][
                "material_finding_ids"
            ][0] = "UNAUTHENTICATED_CORRECTION"

        def wrong_predecessor_correction_scope(_current, evidence):
            evidence["predecessor_provider_feedback"]["material_findings"][0][
                "correction_scope_digest"
            ] = "f" * 64

        def predecessor_thread_authority_expansion(_current, evidence):
            evidence["predecessor_provider_feedback"]["authorized_thread_ids"] = [
                "PRRT_kwDOQFR1MM6hZ8MN"
            ]

        for label, mutate in (
            ("review without suggestions", review_without_suggestions),
            (
                "omitted provider non-thread addition",
                omitted_provider_non_thread_addition,
            ),
            ("non-provider classified addition", non_provider_classified_addition),
            ("non-provider thread source", non_provider_thread_source),
            ("missing finding", missing_finding),
            ("caller-invented finding", extra_invented_finding_source),
            ("ambiguous repeated finding", repeated_finding),
            ("nonterminal Code Review", nonterminal_review),
            ("wrong provider", wrong_provider),
            ("stale reviewed commit", stale_review),
            ("review body substitution", tampered_review_body),
            ("provider review replacement", replaced_review_identity),
            ("fake terminal summary", nonterminal_summary),
            ("missing request provenance", missing_request),
            ("wrong request actor", wrong_request_provenance),
            ("synthetic no-finding result", synthetic_no_finding),
            ("provider completion reaction", provider_completion_reaction),
            ("material Security finding", material_security_review),
            ("omitted late provider addition", unclassified_late_addition),
            ("material finding", material_finding),
            ("VALID_ACTIONABLE", actionable_finding),
            ("resolved finding", resolved_finding),
            ("cross-PR replay", wrong_pr),
            ("cross-head replay", wrong_head),
            ("re-anchor predecessor mismatch", wrong_predecessor_binding),
            ("nonterminal Security result", missing_security),
            ("predecessor feedback on wrong head", wrong_predecessor_head),
            ("ambiguous predecessor reviewed head", ambiguous_predecessor_head),
            ("wrong predecessor provider", wrong_predecessor_provider),
            ("predecessor provider body mismatch", changed_predecessor_body),
            ("missing predecessor provider object", missing_predecessor_review),
            (
                "predecessor feedback older than anchor",
                predecessor_feedback_older_than_anchor,
            ),
            ("extra predecessor provider object", extra_predecessor_review),
            ("omitted material predecessor thread", omitted_predecessor_finding),
            ("cross-head thread substitution", cross_head_thread),
            ("cross-PR predecessor thread replay", cross_pr_predecessor_thread),
            ("false safe predecessor classification", false_safe_predecessor_finding),
            ("candidate-local correction trust", candidate_self_trust),
            ("wrong rejected-candidate authority", wrong_rejected_authority),
            (
                "wrong predecessor correction scope",
                wrong_predecessor_correction_scope,
            ),
            (
                "predecessor thread authority expansion",
                predecessor_thread_authority_expansion,
            ),
            ("wrong removed reaction", wrong_removed_reaction),
            ("wrong completion-reaction provider", wrong_reaction_provider),
            ("wrong completion-reaction content", wrong_reaction_content),
            ("retained predecessor completion reaction", retained_completion_reaction),
        ):
            reviewed, current, evidence = (
                authenticated_pr_905_classified_codex_review()
            )
            mutate(current, evidence)
            current.refresh_digests()
            evidence["resulting_state_digest"] = current.state_digest
            with self.subTest(label=label), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                verify_pr_905_successor(reviewed, current, evidence)

    def test_rejected_successor_accepts_exact_codex_completion_reaction_replacement(
        self,
    ) -> None:
        rejected_head = "be511e420933eeffb289188f3620677bc7cb9f84"
        reviewed, current, evidence = authenticated_provider_reaction_replacement()

        material = fast_path.verify_rejected_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=rejected_head,
            rejected_successor_evidence=evidence,
        )
        self.assertRegex(
            material.provider_reaction_replacement_digest or "",
            r"^[0-9a-f]{64}$",
        )

    def test_rejected_successor_replays_provider_reaction_replacement_from_graphql(
        self,
    ) -> None:
        rejected_head = "be511e420933eeffb289188f3620677bc7cb9f84"
        predecessor_model, current_model, evidence = (
            authenticated_provider_reaction_replacement()
        )
        current_bodies = {
            item["node_id"]: item["body"]
            for item in evidence["provider_transport"]
            if item["body"] is not None
        }
        current_bodies["PRR_RESULTING_HEAD"] = ""
        current_bodies["PRRC_RESULTING_HEAD"] = "provider finding"
        predecessor_bodies = {
            "IC_CODEX_SUMMARY": _provider_terminal_summary(
                predecessor_model.head_sha
            )
        }
        actions = orchestration.bootstrap_source_admission._load_actions_helper()
        registry = {
            "repository": REPOSITORY,
            "maximum_api_calls": 20,
            "maximum_threads": 20,
            "maximum_comments": 100,
            "maximum_reactions": 50,
            "maximum_items": 200,
        }

        def capture(model, bodies):
            runner = SimpleNamespace(
                run=mock.Mock(
                    return_value=_provider_feedback_response(
                        model,
                        transport_bodies=bodies,
                    )
                )
            )
            gateway = actions.FastPathGateway(
                REPO_ROOT,
                registry,
                github=actions.LiveGitHub(runner=runner),
            )
            captured = gateway.capture_stable_feedback(
                REPOSITORY,
                model.pull_request_number,
            )
            runner.run.assert_called_once()
            return fast_path.StableFeedbackState.from_payload(
                captured.to_dict()
            )

        reviewed = capture(predecessor_model, predecessor_bodies)
        current = capture(current_model, current_bodies)
        finding = next(
            comment
            for thread in current.feedback["threads"]
            if thread["node_id"] == "PRRT_RESULTING_HEAD"
            for comment in thread["comments"]
            if comment["node_id"] == "PRRC_RESULTING_HEAD"
        )
        finding_digest = finding["body_digest"]
        classification = evidence["successor_findings"][0][
            "classification_evidence"
        ]
        evidence["successor_findings"][0]["sources"][0]["digest"] = (
            finding_digest
        )
        evidence["successor_findings"][0]["classification_evidence"] = (
            fast_path._seal_successor_classification(
                **{
                    key: value
                    for key, value in classification.__dict__.items()
                    if key != "_verification_seal"
                }
                | {
                    "finding_body_digest": finding_digest,
                    "source_bindings": (
                        (
                            "THREAD_COMMENT",
                            "PRRC_RESULTING_HEAD",
                            finding_digest,
                            "PRRT_RESULTING_HEAD",
                        ),
                    ),
                }
            )
        )
        evidence["predecessor_state_digest"] = reviewed.state_digest
        evidence["resulting_state_digest"] = current.state_digest

        self.assertEqual(current.repository, reviewed.repository)
        self.assertEqual(
            current.pull_request_number,
            reviewed.pull_request_number,
        )
        self.assertEqual((reviewed.pr_state, current.pr_state), ("OPEN", "OPEN"))
        self.assertEqual(current.head_sha, rejected_head)
        self.assertNotEqual(current.head_sha, reviewed.head_sha)
        self.assertEqual(current.base_ref, reviewed.base_ref)
        self.assertEqual(current.base_sha, reviewed.base_sha)

        material = fast_path.verify_rejected_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=rejected_head,
            rejected_successor_evidence=evidence,
        )
        self.assertRegex(
            material.provider_reaction_replacement_digest or "",
            r"^[0-9a-f]{64}$",
        )

    def test_rejected_successor_rejects_completion_reaction_replacement_drift(
        self,
    ) -> None:
        resulting_head = "be511e420933eeffb289188f3620677bc7cb9f84"

        def reject(label, mutate, *, refresh_evidence=True):
            reviewed, current, evidence = (
                authenticated_provider_reaction_replacement()
            )
            mutate(reviewed, current, evidence)
            if refresh_evidence:
                reviewed.refresh_digests()
                current.refresh_digests()
                evidence["predecessor_state_digest"] = reviewed.state_digest
                evidence["resulting_state_digest"] = current.state_digest
            with self.subTest(label=label), self.assertRaises(
                fast_path.SecurityBlocker
            ):
                fast_path.verify_rejected_stable_feedback_successor(
                    reviewed,
                    current,
                    resulting_head_sha=resulting_head,
                    rejected_successor_evidence=evidence,
                )

        def arbitrary_deletion(reviewed, _current, _evidence):
            reviewed.feedback["pull_request_reactions"].append(
                {
                    "mutation_id": "REACTION_UNRELATED_PREDECESSOR",
                    "content": "HEART",
                    "actor": {
                        "login": "delivery-user",
                        "node_id": "USER_DELIVERY",
                        "database_id": 7,
                    },
                }
            )

        def removed_actor_substitution(reviewed, _current, _evidence):
            reviewed.feedback["pull_request_reactions"][-1]["actor"]["login"] = (
                "delivery-user"
            )

        def removed_content_substitution(reviewed, _current, _evidence):
            reviewed.feedback["pull_request_reactions"][-1]["content"] = "HEART"

        def replacement_actor_substitution(_reviewed, current, _evidence):
            current.feedback["pull_request_reactions"][0]["actor"]["login"] = (
                "different-provider"
            )

        def replacement_actor_identity_substitution(_reviewed, current, _evidence):
            current.feedback["pull_request_reactions"][0]["actor"]["node_id"] = (
                "BOT_DIFFERENT_PROVIDER"
            )

        def replacement_content_substitution(_reviewed, current, _evidence):
            current.feedback["pull_request_reactions"][0]["content"] = "HEART"

        def incomplete_transport(_reviewed, _current, evidence):
            evidence["provider_transport"] = [
                item
                for item in evidence["provider_transport"]
                if item["role"] != "CODEX_SECURITY_REVIEW_RESULT"
            ]

        def nonterminal_transport(_reviewed, current, evidence):
            summary = next(
                item
                for item in evidence["provider_transport"]
                if item["role"] == "CODEX_SUMMARY_UPDATE"
            )
            summary["body"] = summary["body"].replace(
                '"status":"completed"',
                '"status":"running"',
            )
            observed = next(
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == summary["node_id"]
            )
            observed["body_digest"] = fast_path.digest_text(summary["body"])

        def wrong_head_transport(_reviewed, current, evidence):
            result = next(
                item
                for item in evidence["provider_transport"]
                if item["role"] == "CODEX_CODE_REVIEW_RESULT"
            )
            result["body"] = result["body"].replace(
                resulting_head[:10],
                "f" * 10,
            )
            observed = next(
                item
                for item in current.feedback["conversation_comments"]
                if item["node_id"] == result["node_id"]
            )
            observed["body_digest"] = fast_path.digest_text(result["body"])

        def reaction_replay(reviewed, _current, _evidence):
            reviewed.feedback["pull_request_reactions"].append(
                {
                    "mutation_id": "REA_lAHOQFR1MM8AAAABQu3eG84d1ZDA",
                    "content": "THUMBS_UP",
                    "actor": {
                        "login": "chatgpt-codex-connector",
                        "node_id": "BOT_CODEX",
                        "database_id": 199175422,
                    },
                }
            )

        def unrelated_reaction_mutation(_reviewed, current, _evidence):
            current.feedback["threads"][0]["comments"][0]["reactions"][0][
                "content"
            ] = "THUMBS_DOWN"

        def unrelated_reaction_addition(_reviewed, current, _evidence):
            current.feedback["conversation_comments"][0]["reactions"].append(
                {
                    "mutation_id": "REACTION_UNRELATED_ADDITION",
                    "content": "HEART",
                    "actor": {
                        "login": "delivery-user",
                        "node_id": "USER_DELIVERY",
                        "database_id": 7,
                    },
                }
            )

        for label, mutate in (
            ("arbitrary reaction deletion", arbitrary_deletion),
            ("removed reaction actor substitution", removed_actor_substitution),
            ("removed reaction content substitution", removed_content_substitution),
            ("replacement provider substitution", replacement_actor_substitution),
            (
                "replacement actor identity substitution",
                replacement_actor_identity_substitution,
            ),
            (
                "replacement reaction type substitution",
                replacement_content_substitution,
            ),
            ("incomplete provider transport", incomplete_transport),
            ("nonterminal provider transport", nonterminal_transport),
            ("wrong-head provider result", wrong_head_transport),
            ("reaction replay", reaction_replay),
            ("unrelated reaction mutation", unrelated_reaction_mutation),
            ("unrelated reaction addition", unrelated_reaction_addition),
            (
                "caller provider substitution",
                lambda _r, _c, evidence: evidence[
                    "provider_completion_reaction_replacement"
                ].update(provider_login="different-provider"),
            ),
            (
                "caller reaction substitution",
                lambda _r, _c, evidence: evidence[
                    "provider_completion_reaction_replacement"
                ].update(reaction_content="HEART"),
            ),
            (
                "wrong PR evidence",
                lambda _r, _c, evidence: evidence.update(
                    pull_request_number=906
                ),
            ),
            (
                "wrong head evidence",
                lambda _r, _c, evidence: evidence.update(
                    resulting_head_sha="f" * 40
                ),
            ),
        ):
            reject(label, mutate)

    def test_reanchored_corrected_successor_accepts_first_terminal_summary(
        self,
    ) -> None:
        reviewed, current, evidence = authenticated_provider_growth()
        reviewed.feedback["conversation_comments"] = []
        reviewed.refresh_digests()
        evidence["predecessor_state_digest"] = reviewed.state_digest

        fast_path.verify_reanchored_stable_feedback_successor(
            reviewed,
            current,
            resulting_head_sha=NEXT_HEAD,
            successor_safety_evidence=evidence,
        )

    def test_continuation_event_fails_closed_for_state_identity_and_finding_drift(
        self,
    ) -> None:
        def reject(
            request: dict[str, object],
            lifecycle: authority.VerifiedLifecycleAuthority,
            reviewed: fast_path.StableFeedbackState,
        ) -> None:
            with self.assertRaises(orchestration.LifecycleOrchestrationError):
                orchestration._orchestrate_event(
                    REPOSITORY,
                    ISSUE,
                    request,
                    current_reader=current_reader(lifecycle),
                    feedback_reader=lambda _repository, _pull_request: reviewed,
                    authorization_verifier=fixture_authorization_verifier,
                )

        for label in (
            "recovery_zero",
            "recovery_over_limit",
            "continuation_used",
            "review_unexhausted",
            "remediation_unexhausted",
            "remediation_over_limit",
            "draft",
            "same_head",
            "candidate_not_pushed",
            "conflicting_pr_head",
            "wrong_result_authorization",
            "wrong_predecessor_authorization",
            "wrong_pr",
            "bounded_uses",
            "empty_findings",
            "invented_finding",
            "coordinated_invented_finding",
            "fully_coordinated_invention",
            "cross_head_feedback",
            "non_material_finding",
            "unrelated_thread",
        ):
            with self.subTest(label=label):
                request, authorization = continuation_inputs()
                predecessor_reviewed = fast_path.verify_reviewed_state_evidence(
                    request["continuation_evidence"]["reviewed_state_evidence"]
                )
                live_reviewed = (
                    predecessor_reviewed
                    if label == "candidate_not_pushed"
                    else feedback_successor(predecessor_reviewed)
                )
                if label == "conflicting_pr_head":
                    live_reviewed.head_sha = "7" * 40
                    live_reviewed.refresh_digests()
                lifecycle = current_lifecycle(exceptional_recoveries=1)
                if label == "recovery_zero":
                    lifecycle = current_lifecycle(exceptional_recoveries=0)
                elif label == "recovery_over_limit":
                    lifecycle.state["exceptional_recovery_count"] = 2
                elif label == "continuation_used":
                    lifecycle = current_lifecycle(
                        exceptional_recoveries=1, exceptional_continuations=1
                    )
                elif label == "review_unexhausted":
                    lifecycle.state["unrestricted_review_count"] = 0
                elif label == "remediation_unexhausted":
                    lifecycle.state["remediation_cycle_count"] = 1
                elif label == "remediation_over_limit":
                    lifecycle.state["remediation_cycle_count"] = 3
                elif label == "draft":
                    lifecycle = current_lifecycle(
                        ready=False, ready_regressed=True, exceptional_recoveries=1
                    )
                elif label == "same_head":
                    request["head_sha"] = HEAD
                elif label == "wrong_result_authorization":
                    authorization["scope"]["resulting_head_sha"] = "7" * 40
                elif label == "wrong_predecessor_authorization":
                    authorization["scope"]["predecessor_head_sha"] = "7" * 40
                elif label == "wrong_pr":
                    request["pull_request"] = PR + 1
                elif label == "bounded_uses":
                    authorization["bounded_uses"] = 2
                elif label == "empty_findings":
                    request["continuation_evidence"]["eligibility_evidence"][
                        "eligible_threads"
                    ] = []
                elif label == "invented_finding":
                    authorization["scope"]["finding_ids"] = ["F-INVENTED"]
                elif label == "coordinated_invented_finding":
                    eligibility = request["continuation_evidence"][
                        "eligibility_evidence"
                    ]
                    eligibility["eligible_threads"][0]["finding_ids"] = [
                        "F-INVENTED"
                    ]
                    authorization["scope"]["finding_ids"] = ["F-INVENTED"]
                    authorization["scope"][
                        "eligibility_evidence_digest"
                    ] = fast_path.digest_json(eligibility)
                elif label == "fully_coordinated_invention":
                    payload = request["continuation_evidence"][
                        "reviewed_state_evidence"
                    ]
                    payload["threads"][0]["comments"][0][
                        "node_id"
                    ] = "F-INVENTED"
                    invented_reviewed = fast_path.StableFeedbackState.from_payload(
                        payload
                    )
                    request["continuation_evidence"][
                        "reviewed_state_evidence"
                    ] = invented_reviewed.to_dict()
                    eligibility = request["continuation_evidence"][
                        "eligibility_evidence"
                    ]
                    eligibility["reviewed_state_digest"] = (
                        invented_reviewed.state_digest
                    )
                    eligibility["eligible_threads"][0]["finding_ids"] = [
                        "F-INVENTED"
                    ]
                    authorization["scope"].update(
                        reviewed_state_digest=invented_reviewed.state_digest,
                        reviewed_feedback_digest=invented_reviewed.feedback_digest,
                        eligibility_evidence_digest=fast_path.digest_json(
                            eligibility
                        ),
                        finding_ids=["F-INVENTED"],
                    )
                elif label == "cross_head_feedback":
                    payload = request["continuation_evidence"][
                        "reviewed_state_evidence"
                    ]
                    payload["head_sha"] = "7" * 40
                    changed = fast_path.StableFeedbackState.from_payload(payload)
                    request["continuation_evidence"][
                        "reviewed_state_evidence"
                    ] = changed.to_dict()
                elif label == "non_material_finding":
                    request["continuation_evidence"]["eligibility_evidence"][
                        "eligible_threads"
                    ][0]["classification"] = "INFORMATIONAL"
                    request["continuation_evidence"]["eligibility_evidence"][
                        "eligible_threads"
                    ][0]["disposition"] = "NON_ACTIONABLE"
                elif label == "unrelated_thread":
                    authorization["scope"]["thread_ids"] = ["PRRT_UNRELATED"]
                reject(request, lifecycle, live_reviewed)

    def test_bounded_normal_remediation_changes_ready_head_in_place(self) -> None:
        lifecycle = current_lifecycle(remediation_cycles=1)
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "REMEDIATION_COMMIT_PUSHED",
                "event_id": fixture_event_id("bounded-remediation-2"),
                "pull_request": PR,
                "head_sha": NEXT_HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": {
                    "authorization_id": "bounded-remediation-2",
                    "operation": "REMEDIATION_COMPLETED",
                    "reason": "Correct the exact authorized Cycle-2 findings",
                    "scope": {
                        "pull_request": PR,
                        "predecessor_head_sha": HEAD,
                        "resulting_head_sha": NEXT_HEAD,
                        "finding_ids": ["F-C2-1"],
                    },
                    "bounded_uses": 1,
                },
            },
            current_reader=current_reader(lifecycle),
            authorization_verifier=fixture_authorization_verifier,
        )

        self.assertEqual(decision.lifecycle_transition, "REMEDIATION_COMPLETED")
        self.assertEqual(decision.resulting_head_sha, NEXT_HEAD)
        self.assertTrue(decision.preserve_ready)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.requires_fresh_head_evidence)

    def test_replacement_rebinds_the_existing_exhausted_lifecycle(self) -> None:
        lifecycle = current_lifecycle()
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "PR_REPLACED",
                "event_id": fixture_event_id("user-replacement-1"),
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": REPLACEMENT_PR,
                "classification": None,
                "follow_up": None,
                "authorization": {
                    "authorization_id": "user-replacement-1",
                    "operation": "PR_REBOUND",
                    "reason": "Recover delivery on the canonical replacement PR",
                    "scope": {
                        "predecessor_pull_request": PR,
                        "replacement_pull_request": REPLACEMENT_PR,
                        "head_sha": HEAD,
                    },
                    "bounded_uses": 1,
                },
            },
            current_reader=current_reader(lifecycle),
            authorization_verifier=fixture_authorization_verifier,
        )

        self.assertEqual(decision.lifecycle_transition, "PR_REBOUND")
        self.assertEqual(decision.resulting_pull_request, REPLACEMENT_PR)
        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.cycle_3_absent)

    def test_ci_reopen_and_ready_integration_observations_create_no_cycle(self) -> None:
        lifecycle = current_lifecycle(exceptional_continuations=1)
        for event_kind in (
            "CI_OBSERVED",
            "PR_REOPENED",
            "READY_INTEGRATION_VALIDATED",
        ):
            with self.subTest(event_kind=event_kind):
                decision = orchestration._orchestrate_event(
                    REPOSITORY,
                    ISSUE,
                    {
                        "event_kind": event_kind,
                        "event_id": f"observation-{event_kind}",
                        "pull_request": PR,
                        "head_sha": HEAD,
                        "replacement_pull_request": None,
                        "classification": None,
                        "follow_up": None,
                        "authorization": None,
                    },
                    current_reader=current_reader(lifecycle),
                )
                self.assertIsNone(decision.lifecycle_transition)
                self.assertEqual(decision.remediation_cycles, 2)
                self.assertEqual(decision.exceptional_continuations, 1)
                self.assertFalse(decision.request_review)
                self.assertFalse(decision.transition_to_draft)
                self.assertFalse(decision.transition_to_ready)

    def test_material_post_ready_finding_blocks_without_cycle_three(self) -> None:
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "LATE_FEEDBACK_CLASSIFIED",
                "event_id": "finding-material-1",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": {
                    "classification": "IN_CONTRACT_DEFECT",
                    "technically_blocking": True,
                    "mechanically_blocking": True,
                    "timing": "AFTER_FREEZE",
                    "risk": ["P2", "INTEGRITY"],
                },
                "follow_up": None,
                "authorization": None,
            },
            current_reader=current_reader(current_lifecycle()),
        )

        self.assertTrue(decision.technically_blocking)
        self.assertTrue(decision.mechanically_blocking)
        self.assertFalse(decision.merge_ready)
        self.assertTrue(decision.explicit_recovery_required)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.cycle_3_absent)

    def test_authenticated_tracked_follow_up_is_not_reported_as_fixed(self) -> None:
        observed = []

        def verify(identity):
            observed.append(identity)
            return SimpleNamespace(identity=identity, open=True, structurally_complete=True)

        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "LATE_FEEDBACK_CLASSIFIED",
                "event_id": "finding-follow-up-1",
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": {
                    "classification": "NON_BLOCKING_FOLLOWUP",
                    "technically_blocking": False,
                    "mechanically_blocking": True,
                    "timing": "AFTER_FREEZE",
                    "risk": ["P3"],
                },
                "follow_up": {
                    "repository": "SecPal/.github",
                    "issue_number": 674,
                    "issue_url": "https://github.com/SecPal/.github/issues/674",
                },
                "authorization": None,
            },
            current_reader=current_reader(current_lifecycle()),
            follow_up_verifier=verify,
        )

        self.assertEqual(len(observed), 1)
        self.assertFalse(decision.technically_blocking)
        self.assertTrue(decision.mechanically_blocking)
        self.assertFalse(decision.resolution_eligible)
        self.assertTrue(decision.guarded_resolution_candidate)
        self.assertTrue(decision.authenticated_resolution_required)
        self.assertEqual(
            decision.resolution_meaning_if_applied,
            "SAFELY_DISPOSITIONED_TRACKED",
        )
        self.assertNotIn(
            decision.resolution_meaning_if_applied,
            {"FIXED", "IMPLEMENTED", "COMPLETED"},
        )

    def test_high_risk_finding_cannot_be_converted_to_follow_up(self) -> None:
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                {
                    "event_kind": "LATE_FEEDBACK_CLASSIFIED",
                    "event_id": "finding-security-1",
                    "pull_request": PR,
                    "head_sha": HEAD,
                    "replacement_pull_request": None,
                    "classification": {
                        "classification": "NON_BLOCKING_FOLLOWUP",
                        "technically_blocking": False,
                        "mechanically_blocking": True,
                        "timing": "AFTER_FREEZE",
                        "risk": ["SECURITY"],
                    },
                    "follow_up": {
                        "repository": "SecPal/.github",
                        "issue_number": 674,
                        "issue_url": "https://github.com/SecPal/.github/issues/674",
                    },
                    "authorization": None,
                },
                current_reader=current_reader(current_lifecycle()),
            )

    def test_ready_to_draft_requires_exact_user_reason_and_authorization(self) -> None:
        base = {
            "event_kind": "READY_TO_DRAFT",
            "event_id": fixture_event_id("user-draft-1"),
            "pull_request": PR,
            "head_sha": HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": None,
        }
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                base,
                current_reader=current_reader(current_lifecycle()),
                authorization_verifier=fixture_authorization_verifier,
            )
        base["authorization"] = {
            "authorization_id": "user-draft-1",
            "operation": "READY_TO_DRAFT",
            "reason": "Pause this exact PR for a user-controlled contract reassessment",
            "scope": {"pull_request": PR, "head_sha": HEAD},
            "bounded_uses": 1,
        }
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            base,
            current_reader=current_reader(current_lifecycle()),
            authorization_verifier=fixture_authorization_verifier,
        )
        self.assertEqual(decision.lifecycle_transition, "READY_TO_DRAFT")
        self.assertTrue(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)

    def test_ready_after_user_draft_regression_requires_separate_authorization(self) -> None:
        regressed = current_lifecycle(ready=False, ready_regressed=True)
        request = {
            "event_kind": "DRAFT_TO_READY",
            "event_id": fixture_event_id("user-ready-again-1"),
            "pull_request": PR,
            "head_sha": HEAD,
            "replacement_pull_request": None,
            "classification": None,
            "follow_up": None,
            "authorization": {
                "authorization_id": "user-ready-again-1",
                "operation": "DRAFT_TO_READY",
                "reason": "Resume this exact PR after the separately authorized pause",
                "scope": {"pull_request": PR, "head_sha": HEAD},
                "bounded_uses": 1,
            },
        }
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            request,
            current_reader=current_reader(regressed),
            authorization_verifier=fixture_authorization_verifier,
        )
        self.assertEqual(decision.lifecycle_transition, "DRAFT_TO_READY")
        self.assertEqual(decision.lifecycle_identity, LIFECYCLE)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertTrue(decision.transition_to_ready)

    def test_one_additional_review_is_authorized_without_counter_change(self) -> None:
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "ADDITIONAL_REVIEW_AUTHORIZED",
                "event_id": fixture_event_id("user-review-1"),
                "pull_request": PR,
                "head_sha": HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": {
                    "authorization_id": "user-review-1",
                    "operation": "ADDITIONAL_REVIEW",
                    "reason": "Assess the exact current head once after recovery",
                    "scope": {
                        "pull_request": PR,
                        "head_sha": HEAD,
                    },
                    "bounded_uses": 1,
                },
            },
            current_reader=current_reader(current_lifecycle()),
            authorization_verifier=fixture_authorization_verifier,
        )
        self.assertTrue(decision.additional_review_authorized)
        self.assertTrue(decision.stop_after_bounded_pass)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertEqual(
            decision.lifecycle_transition,
            "ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED",
        )
        self.assertTrue(decision.requires_authorization_publication)
        self.assertFalse(decision.request_review)

    def test_exhausted_exceptional_recovery_is_not_a_generic_escape_hatch(self) -> None:
        with self.assertRaises(orchestration.LifecycleOrchestrationError):
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                {
                    "event_kind": "RECOVERY_COMMIT_PUSHED",
                    "event_id": fixture_event_id("user-recovery-2"),
                    "pull_request": PR,
                    "head_sha": NEXT_HEAD,
                    "replacement_pull_request": None,
                    "classification": None,
                    "follow_up": None,
                    "authorization": {
                        "authorization_id": "user-recovery-2",
                        "operation": "EXCEPTIONAL_RECOVERY",
                        "reason": "Attempt a second bounded recovery",
                        "scope": {
                            "pull_request": PR,
                            "predecessor_head_sha": HEAD,
                            "resulting_head_sha": NEXT_HEAD,
                            "finding_ids": ["F-2"],
                        },
                        "bounded_uses": 1,
                    },
                },
                current_reader=current_reader(
                    current_lifecycle(exceptional_recoveries=1)
                ),
                authorization_verifier=fixture_authorization_verifier,
            )

    def test_automated_review_on_recovery_head_is_one_non_recursive_pass(self) -> None:
        recovered = current_lifecycle(
            exceptional_recoveries=1,
            head_sha=NEXT_HEAD,
        )
        decision = orchestration._orchestrate_event(
            REPOSITORY,
            ISSUE,
            {
                "event_kind": "REVIEW_EVENT_OBSERVED",
                "event_id": "configured-review-on-recovery-head",
                "pull_request": PR,
                "head_sha": NEXT_HEAD,
                "replacement_pull_request": None,
                "classification": None,
                "follow_up": None,
                "authorization": None,
            },
            current_reader=current_reader(recovered),
        )

        self.assertEqual(decision.head_sha, NEXT_HEAD)
        self.assertTrue(decision.ready)
        self.assertTrue(decision.ready_transition_already_performed)
        self.assertEqual(decision.exceptional_recoveries, 1)
        self.assertEqual(decision.unrestricted_reviews, 1)
        self.assertEqual(decision.remediation_cycles, 2)
        self.assertIsNone(decision.lifecycle_transition)
        self.assertFalse(decision.request_review)
        self.assertFalse(decision.transition_to_draft)
        self.assertFalse(decision.transition_to_ready)
        self.assertTrue(decision.stop_after_bounded_pass)


if __name__ == "__main__":
    main()
