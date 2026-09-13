#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Regression coverage for finite delivery-lifecycle orchestration."""

from __future__ import annotations

import ast
import copy
import base64
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import zlib
from dataclasses import replace
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
REAL_894_MERGE_BASE = "aa7d9e4485abbceed01136cd81fdbbd353f877bc"
REAL_894_MERGE_SIDE_PARENT = "7bcb9e622b608742707dbe9ff8cbaebfb561c7cd"


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


class CollisionCompositionFixture:
    def __init__(
        self,
        root: Path,
        *,
        historical_thread: bool = False,
        historical_thread_resolved: bool = False,
        validation_harness: bool = False,
        validation_prerequisite_on_predecessor_only: bool = False,
        validation_prerequisite_unconsumed_bytes: int = 0,
    ):
        from scripts.secpal_pr_review import version_collision

        self.root = root
        self.identity = "aroviqen@secpal.app"
        self.key = root / "signing-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True)
        public = self.key.with_suffix(".pub").read_text().strip()
        self.git("init", "--quiet")
        self.git("remote", "add", "origin", "https://github.com/SecPal/.github.git")
        for key, value in {
            "user.name": "Fixture", "user.email": self.identity, "gpg.format": "ssh",
            "user.signingkey": str(self.key), "gpg.ssh.allowedSignersFile": str(root / "allowed-signers"),
        }.items():
            self.git("config", key, value)
        (root / "allowed-signers").write_text(self.identity + " " + public + "\n")
        original = authority._load_lifecycle_trust_policy(REPOSITORY)
        self.policy = replace(original, signers={
            **original.signers, self.identity: authority.TrustedSigner(self.identity, (public,), ()),
        })
        registry = json.loads(authority._TRUST_REGISTRY.read_bytes())
        entry = next(item for item in registry["repositories"] if item["repository"] == REPOSITORY)
        self.command = {
            "argv": (
                ["python3", "-m", "unittest", "tests/secpal-pr-review-actions-unit.py"]
                if validation_harness
                else ["python3", "-c", "import ast,pathlib; ast.parse(pathlib.Path('scripts/secpal_pr_review/fast_path.py').read_text())"]
            ),
            "working_directory": ".",
            "purpose": "Hermetic complete validation",
        }
        commands = [self.command]
        if validation_harness:
            commands.append({
                "argv": [
                    "python3", "-m", "unittest",
                    "tests/secpal-resolve-fixed-threads-unit.py",
                ],
                "working_directory": ".",
                "purpose": "Hermetic resolver validation",
            })
        entry.update(
            focused_validation=[],
            required_local_validation=commands,
            manual_gates=[],
        )
        registry["repositories"] = [entry]
        self.registry_document = registry
        registry_path = root / ".agents/skills/secpal-pr-review/references/repositories.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_bytes(authority.canonical_json_bytes(self.registry_document))
        self.git("add", str(registry_path.relative_to(root)))
        if validation_harness:
            schema_path = root / version_collision.TRUST_REGISTRY_SCHEMA_PATH
            schema_path.write_bytes(
                authority._TRUST_REGISTRY.with_name(
                    "repositories.schema.json"
                ).read_bytes()
            )
            action_fixtures = b'''import unittest

def validate(**_values):
    return None

class CurrentIdentityFixtures(unittest.TestCase):
    def test_parent2_preservation_cannot_delete_parent1_only_work(self):
        validate(schema_version="1.2")

    def test_parent2_preservation_uses_exact_new_attestation_versions(self):
        validate(schema_version="1.2")

    def test_ready_integration_accepts_authenticated_current_ready_histories(self):
        validate(schema_version="1.2")

    def test_ready_integration_authenticates_exact_parent2_preservation(self):
        validate(schema_version="1.2")
        validate(schema_version="1.2")

    def test_ready_integration_mixes_conflict_and_parent2_preservation(self):
        validate(schema_version="1.2")
        validate(schema_version="1.2")

    def test_ready_integration_v12_delta_uses_registered_item_limit_before_git_work(self):
        validate(schema_version="1.2")
        validate(schema_version="1.2")

def historical_v12_fixture():
    return "1.2"
'''
            resolver_fixtures = b'''import unittest

def validate(**_values):
    return None

class CurrentIdentityFixtures(unittest.TestCase):
    def test_eligibility_bound_ready_integration_authorizes_exact_thread(self):
        validate(schema_version="1.2")
'''
            for relative, content in {
                version_collision.COLLISION_AUTHORITY_PATH: b"# collision authority\n",
                version_collision.EXACT_SOURCE_SAFETY_PATH: b"# source safety\n",
                version_collision.VALIDATION_ACTIONS_PATH: (
                    b"def _verify_integration_tree_delta(_root, evidence, _tree):\n"
                    b"    schema_version = evidence['schema_version']\n"
                    b"    if schema_version not in {'1.1', '1.2'}:\n"
                    b"        raise ValueError('unsupported')\n"
                ),
                "package.json": (
                    Path(__file__).resolve().parents[1] / "package.json"
                ).read_bytes(),
                "package-lock.json": (
                    Path(__file__).resolve().parents[1] / "package-lock.json"
                ).read_bytes(),
                "tests/secpal-pr-review-actions-unit.py": action_fixtures,
                "tests/secpal-resolve-fixed-threads-unit.py": resolver_fixtures,
            }.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                if relative == version_collision.VALIDATION_ACTIONS_PATH:
                    path.chmod(0o755)
            self.git(
                "add",
                version_collision.TRUST_REGISTRY_SCHEMA_PATH,
                version_collision.COLLISION_AUTHORITY_PATH,
                version_collision.EXACT_SOURCE_SAFETY_PATH,
                version_collision.VALIDATION_ACTIONS_PATH,
                "package.json",
                "package-lock.json",
                "tests/secpal-pr-review-actions-unit.py",
                "tests/secpal-resolve-fixed-threads-unit.py",
            )
            if validation_prerequisite_unconsumed_bytes:
                historical_unconsumed = root / "historical-unconsumed.bin"
                historical_unconsumed.write_bytes(
                    b"x" * validation_prerequisite_unconsumed_bytes
                )
                self.git("add", "historical-unconsumed.bin")
            validation_prerequisite = self.commit(
                self.git("write-tree"), "validation prerequisite"
            )
            if validation_prerequisite_unconsumed_bytes:
                self.git("rm", "--cached", "--quiet", "historical-unconsumed.bin")
                historical_unconsumed.unlink()
            bundle_path = root / version_collision.COLLISION_VALIDATION_BUNDLE_PATHS[0]
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            bundle_path.write_bytes(
                b"# v2 git bundle\n-"
                + validation_prerequisite.encode("ascii")
                + b" validation prerequisite\n"
                + validation_prerequisite.encode("ascii")
                + b" refs/heads/validation-fixture\n\nPACKx"
            )
            snapshot_path = (
                root / version_collision.COLLISION_VALIDATION_SNAPSHOT_PATHS[0]
            )
            snapshot_path.write_bytes(
                b'P21_BASELINE="'
                + validation_prerequisite.encode("ascii")
                + b'"\n'
            )
            snapshot_path.chmod(0o755)
            self.validation_prerequisite = validation_prerequisite
            self.bundle_blob_oid = self.git(
                "hash-object",
                version_collision.COLLISION_VALIDATION_BUNDLE_PATHS[0],
            )
            self.snapshot_blob_oid = self.git(
                "hash-object",
                version_collision.COLLISION_VALIDATION_SNAPSHOT_PATHS[0],
            )
            self.validation_required_blob = self.git(
                "rev-parse",
                validation_prerequisite
                + ":"
                + version_collision.COLLISION_AUTHORITY_PATH,
            )
            self.git(
                "add",
                version_collision.COLLISION_VALIDATION_BUNDLE_PATHS[0],
                version_collision.COLLISION_VALIDATION_SNAPSHOT_PATHS[0],
            )
        else:
            validation_prerequisite = None
        (root / "unrelated.txt").write_text('"1.2"\n')
        self.git("add", "unrelated.txt")
        self.registry = fast_path.validation_registry_projection(entry)
        self.base = self.commit(
            self.tree(self.source(None, None)),
            "base",
            *(
                [validation_prerequisite]
                if validation_prerequisite
                and not validation_prerequisite_on_predecessor_only
                else []
            ),
        )
        self.predecessor_source = self.source("1.2", "authenticated_resolution_delta")
        self.predecessor_tree = self.tree(self.predecessor_source)
        self.predecessor = self.commit(
            self.predecessor_tree,
            "predecessor",
            self.base,
            *(
                [validation_prerequisite]
                if validation_prerequisite_on_predecessor_only
                and validation_prerequisite
                else []
            ),
        )
        self.main = self.commit(self.tree(self.source("1.2", "reviewed_head_sha")), "accepted main", self.base)
        self.resulting_tree = self.tree(self.source("1.3", "authenticated_resolution_delta"))
        self.git("update-ref", "HEAD", self.predecessor)
        self.lifecycle, self.lifecycle_raw = self.native_lifecycle()
        self.observed = current_reader(self.lifecycle)(REPOSITORY, ISSUE)
        self.observed.serialized_lifecycle_evidence = self.lifecycle_raw
        self.reviewed, self.predecessor_safety = self.feedback(self.predecessor, "PRE")
        if historical_thread:
            self.add_historical_thread(resolved=historical_thread_resolved)
        self.eligibility = {"schema_version": "1.1", "repository": REPOSITORY,
                            "pull_request_number": PR, "reviewed_head_sha": self.predecessor,
                            "reviewed_state_digest": self.reviewed.state_digest, "eligible_threads": []}
        proof = version_collision._derive_collision_tree(
            root, repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
            predecessor_head=self.predecessor, resulting_tree=self.resulting_tree, protected_main=self.main,
        )
        state = self.lifecycle.state
        self.document = {
            "schema_version": "1.1", "kind": "READY_EXCEPTIONAL_CONTINUATION",
            "trigger": version_collision.TRIGGER, "collision_digest": fast_path.digest_json(proof),
            "authorization_id": "version-collision-fixture", "repository": REPOSITORY,
            "delivery_issue_number": ISSUE, "pull_request_number": PR,
            "prior_ready_head_sha": self.predecessor, "prior_ready_tree_sha": self.predecessor_tree,
            "continuation_tree_sha": self.resulting_tree, "reviewed_state_digest": self.reviewed.state_digest,
            "reviewed_feedback_digest": self.reviewed.feedback_digest,
            "eligibility_evidence_digest": fast_path.digest_json(self.eligibility),
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": self.identity},
            "lifecycle": {"unrestricted_reviews": 1, "remediation_cycles": 2, "cycle_3": False,
                          "draft": False, "ready": True, "ready_transition_count": 1,
                          "ready_history": state["ready_history"], "exceptional_recovery_count": 1,
                          "exceptional_recovery_history": state["exceptional_recovery_history"],
                          "exceptional_continuation_predecessor_count": 0, "exceptional_continuation_successor_count": 1},
        }
        completed = subprocess.run(self.command["argv"], cwd=root, check=False)
        if completed.returncode != 0 or self.git("write-tree") != self.resulting_tree:
            raise AssertionError("hermetic Complete Validation did not preserve the frozen tree")
        self.receipt = fast_path.create_validation_receipt(
            repository=REPOSITORY, head_sha=self.predecessor, validated_tree_sha=self.resulting_tree,
            registry=self.registry, command_set=self.registry["validation"], successful_result=True,
            reviewed_state=self.reviewed, manual_gate_evidence=[],
            eligibility_evidence_digest=fast_path.digest_json(self.eligibility),
            exceptional_continuation_evidence_digest=fast_path.digest_json(self.document),
        )
        self.resulting = self.commit(self.resulting_tree,
            "renumber\n\nSecPal-Validation-Receipt: " + self.receipt["receipt_digest"], self.predecessor)
        self.attestation = fast_path.create_validation_attestation(
            repository=REPOSITORY, head_sha=self.resulting, registry=self.registry,
            command_set=self.registry["validation"], successful_result=True,
            reviewed_state=self.reviewed, validation_receipt=self.receipt,
        )
        self.current, self.successor_safety = self.feedback(self.resulting, "POST", self.reviewed)
        self.evidence = {
            "schema_version": "1.1", "trigger": version_collision.TRIGGER, "repository_root": str(root),
            "reviewed_state_evidence": self.reviewed.to_dict(), "eligibility_evidence": self.eligibility,
            "continuation_document": self.document, "predecessor_safety_evidence": self.predecessor_safety,
            "successor_safety_evidence": self.successor_safety, "validation_attestation": self.attestation,
        }

    def git(self, *arguments: str, data: bytes | None = None) -> str:
        return subprocess.run(["git", "-C", str(self.root), *arguments], input=data,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode().strip()

    def tree(self, source: bytes) -> str:
        from scripts.secpal_pr_review import version_collision

        path = self.root / version_collision.SOURCE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
        self.git("add", version_collision.SOURCE_PATH)
        return self.git("write-tree")

    def commit(self, tree: str, message: str, *parents: str) -> str:
        arguments = ["commit-tree", "-S", tree, "-m", message]
        for parent in parents:
            arguments.extend(["-p", parent])
        return self.git(*arguments)

    def native_lifecycle(self):
        initialization = authority.create_delivery_initialization(
            repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
            initial_head_sha=self.base, validation_receipt_digest="1" * 64,
            final_attestation_digest="2" * 64, signer_identity=self.identity, signer=self.sign,
        )
        lifecycle = authority.delivery_initialization_lifecycle_id(initialization["initialization_digest"])
        events, snapshots = [], []
        head = None
        for transition, resulting in (
            ("INITIALIZED_DRAFT", self.base), ("UNRESTRICTED_REVIEW_CONSUMED", self.base),
            ("REMEDIATION_COMPLETED", "1" * 40), ("REMEDIATION_COMPLETED", "2" * 40),
            ("DRAFT_TO_READY", "2" * 40), ("EXCEPTIONAL_RECOVERY", self.predecessor),
        ):
            event = authority.create_transition_authorization(
                event_id=f"genesis:{initialization['initialization_digest']}" if not events else f"fixture-event-{len(events)}",
                repository=REPOSITORY, delivery_issue=ISSUE, lifecycle_id=lifecycle, pull_request=PR,
                predecessor_authority_digest=snapshots[-1]["authority_digest"] if snapshots else None,
                predecessor_head_sha=head, resulting_head_sha=resulting, transition_kind=transition,
                replacement_pull_request=None, initialization_evidence_digest=initialization["initialization_digest"],
                signer_identity=self.identity, signer=self.sign,
            )
            snapshot = authority.issue_lifecycle_authority(
                predecessor_chain=snapshots, transition_authorizations=events, authorization=event,
                signer_identity=self.identity, authority_signer=self.sign,
                accepted_event_signers=self.policy.transition_signer_identities,
                accepted_authority_signers=self.policy.authority_signer_identities,
                signature_verifier=authority._policy_signature_verifier(self.policy),
            )
            events.append(event)
            snapshots.append(snapshot)
            head = resulting
        raw = authority.serialize_lifecycle_evidence(
            delivery_initialization=initialization, transition_authorizations=events, authority_chain=snapshots,
        )
        with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=self.policy):
            verified = authority._verify_lifecycle_authority_for_journal(raw, admitted_initialization=initialization)
        return verified, raw

    @staticmethod
    def source(version: str | None, field: str | None) -> bytes:
        fields = {"1.1": {"kind", "schema_version", "manual_conflict_resolution_delta"}}
        mappings = {("1.1", False): ("1.1", "READY_INTEGRATION_VALIDATION_ATTESTATION"),
                    ("1.1", True): ("1.2", "ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION")}
        if version is not None:
            fields[version] = {"kind", "schema_version", field}
            for bound, number in ((False, "1.3"), (True, "1.4")):
                mappings[(version, bound)] = (number, "AUTHENTICATED_RESOLUTION_ATTESTATION")
        limit_guard = "" if version is None else (
            f"    if schema_version == {version!r}:\n"
            "        limits = registry.get('limits') if isinstance(registry, dict) else None\n"
            "        maximum_items = limits.get('maximum_items') if isinstance(limits, dict) else None\n"
            "        if (\n"
            "            isinstance(maximum_items, bool)\n"
            "            or not isinstance(maximum_items, int)\n"
            "            or maximum_items < 1\n"
            "        ):\n"
            "            raise SecurityBlocker('registered integration item limit is invalid')\n"
            "        if isinstance(raw_delta, list) and len(raw_delta) > maximum_items:\n"
            "            raise SecurityBlocker('Ready integration delta exceeds the registered item limit')\n"
        )
        declaration = "{\n" + "".join(f"    {key!r}: frozenset({{{', '.join(repr(item) for item in sorted(value))}}}),\n" for key, value in fields.items()) + "}"
        return (f'READY_INTEGRATION_KIND = "TWO_PARENT_READY_INTEGRATION"\n'
                f"READY_INTEGRATION_KEYS_BY_VERSION = {declaration}\n"
                f"READY_INTEGRATION_ATTESTATION_BY_VERSION = {mappings!r}\n"
                "def normalize_ready_integration_evidence(value):\n"
                "    schema_version = value.get('schema_version')\n"
                "    expected_keys = READY_INTEGRATION_KEYS_BY_VERSION.get(schema_version)\n"
                "    if expected_keys is None or set(value) != expected_keys:\n"
                "        raise ValueError('invalid schema')\n"
                f"{limit_guard}"
                "    return value\n"
                "def create_ready_integration_attestation(normalized, eligibility_bound):\n"
                "    attestation_version, attestation_kind = READY_INTEGRATION_ATTESTATION_BY_VERSION[(normalized['schema_version'], eligibility_bound)]\n"
                "    return {'schema_version': attestation_version, 'kind': attestation_kind}\n").encode()

    def feedback(self, head: str, prefix: str, prior=None):
        provider = {"login": "chatgpt-codex-connector", "node_id": "CODEX", "database_id": 199175422}
        requester = {"login": "fixture-user", "node_id": "USER", "database_id": 7}
        summary = ('<!-- codex-pull-request-review-summary -->\n<!-- codex-security-review:v1 '
                   f'{{"headSha":"{head}","status":"completed"}} -->\n'
                   '| Review | Status | Commit | Review trigger |\n| --- | --- | --- | --- |\n'
                   '| **Code Review** | **Completed** | head | manual |\n'
                   '| **Security Review** | **Completed** | head | manual |')
        rows = [
            ("CODEX_SUMMARY_UPDATE", "SUMMARY", summary),
            ("CODEX_REVIEW_REQUEST", prefix + "_CODE_REQUEST", "@codex review"),
            ("CODEX_SECURITY_REVIEW_REQUEST", prefix + "_SECURITY_REQUEST", "@codex security review"),
            ("CODEX_CODE_REVIEW_RESULT", prefix + "_CODE_RESULT", f"Codex Review: Didn't find any major issues.\n**Reviewed commit:** `{head[:10]}`"),
            ("CODEX_SECURITY_REVIEW_RESULT", prefix + "_SECURITY_RESULT", f"No security issues were found in this pull request.\n**Reviewed commit:** `{head[:10]}`"),
        ]
        feedback = copy.deepcopy(prior.feedback) if prior else {"pull_request_reactions": [], "reviews": [], "conversation_comments": [], "threads": []}
        feedback["conversation_comments"] = [item for item in feedback["conversation_comments"] if item["node_id"] != "SUMMARY"]
        for role, node, body in rows:
            feedback["conversation_comments"].append({
                "node_id": node, "body_digest": fast_path.digest_text(body),
                "actor": requester if role.endswith("REQUEST") else provider,
                "updated_at": None, "reactions": [],
            })
        state = fast_path.StableFeedbackState(repository=REPOSITORY, pull_request_number=PR,
            head_sha=head, base_ref="main", base_sha=self.base, pr_state="OPEN", feedback=feedback)
        safety = {"schema_version": "1.0", "repository": REPOSITORY, "pull_request_number": PR,
                  "predecessor_state_digest": prior.state_digest if prior else state.state_digest,
                  "resulting_head_sha": head, "resulting_state_digest": state.state_digest,
                  "provider_transport": [{"role": role, "kind": "CONVERSATION_COMMENT", "node_id": node, "body": body} for role, node, body in rows],
                  "successor_findings": [], "classification_signer": {"kind": "SSH_PRINCIPAL", "identity": self.identity}}
        return state, safety

    def collision_reader(self, **arguments):
        from scripts.secpal_pr_review import version_collision
        import hashlib

        proof = version_collision._derive_collision_from_git(
            arguments["repository_root"], repository=arguments["repository"], delivery_issue=arguments["delivery_issue"],
            pull_request=arguments["pull_request"], predecessor_head=arguments["predecessor_head"],
            resulting_head=arguments["resulting_head"], protected_main=self.main,
        )
        raw = authority.canonical_json_bytes(proof)
        return version_collision.VerifiedVersionCollision(raw, version_collision._CollisionSeal(hashlib.sha256(raw).hexdigest()))

    def registry_reader(self, main: str) -> bytes:
        if main != self.main:
            raise AssertionError("registry read is not bound to protected main")
        return self.git("show", main + ":.agents/skills/secpal-pr-review/references/repositories.json").encode()

    def sign(self, payload: bytes, domain: str):
        signed = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(self.key), "-n", domain],
                                input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return {"format": "ssh", "signer_identity": self.identity, "value": signed.stdout.decode()}

    def add_historical_thread(self, *, resolved: bool = False):
        feedback = copy.deepcopy(self.reviewed.feedback)
        feedback["threads"].append({
            "node_id": "PRRT_HISTORICAL", "is_resolved": resolved, "is_outdated": True,
            "comments": [{"node_id": "PRRC_HISTORICAL", "body_digest": "a" * 64,
                          "actor": {"login": "reviewer", "node_id": "REVIEWER", "database_id": 99},
                          "reply_to_id": None, "reactions": []}],
        })
        self.reviewed = fast_path.StableFeedbackState(
            repository=REPOSITORY, pull_request_number=PR, head_sha=self.predecessor,
            base_ref="main", base_sha=self.base, pr_state="OPEN", feedback=feedback,
        )
        self.predecessor_safety.update(predecessor_state_digest=self.reviewed.state_digest,
                                       resulting_state_digest=self.reviewed.state_digest)
        fingerprint = orchestration._ssh_public_key_fingerprint(self.policy.signers[self.identity].ssh_public_keys[0])
        artifact = {
            "schema_version": "1.3", "kind": "LATE_FEEDBACK_CLASSIFICATION",
            "repository": REPOSITORY, "delivery_issue_number": ISSUE, "pull_request_number": PR,
            "head_sha": self.predecessor, "delivery_signer": {"format": "ssh", "fingerprint": fingerprint},
            "authorized_purpose": late_disposition.CLASSIFICATION_PURPOSE,
            "finding_id": "PRRC_HISTORICAL", "finding_evidence_digest": "b" * 64,
            "thread": {"thread_id": "PRRT_HISTORICAL", "top_level_comment_node_id": "PRRC_HISTORICAL",
                       "top_level_comment_database_id": 77, "finding_body_digest": "a" * 64,
                       "reply_state_digest": fast_path.digest_json([]), "reply_count": 0,
                       "is_resolved": resolved, "is_outdated": True, "classification": "VALID_ACTIONABLE",
                       "disposition": "CORRECTED_AND_VERIFIED", "technically_blocking": False, "technical_blockers": []},
        }
        raw = late_disposition.canonical_json_bytes(artifact)
        signature = self.sign(raw, late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE)["value"].encode()
        self.predecessor_safety["historical_thread_classifications"] = [{
            "thread_id": "PRRT_HISTORICAL", "classification_artifact": base64.b64encode(raw).decode(),
            "classification_signature": base64.b64encode(signature).decode(),
        }]

    def request(self):
        scope, _, _ = orchestration._collision_scope(
            self.evidence, observed=self.observed, resulting_head=self.resulting, collision_reader=self.collision_reader,
        )
        return self.authorized_request(scope)

    def authorized_request(self, scope, **overrides):
        arguments = dict(
            authorization_id=self.document["authorization_id"], repository=REPOSITORY, delivery_issue=ISSUE,
            lifecycle=self.lifecycle, publication_oid=self.observed.publication_oid,
            publication_digest=self.observed.publication_digest, operation="EXCEPTIONAL_CONTINUATION",
            reason="Renumber the independently authenticated immutable version collision",
            scope=scope, signer_identity=self.identity, signer=self.sign,
        )
        arguments.update(overrides)
        authorization = orchestration.create_user_authorization(**arguments)
        parsed = authority.loads_closed_json(authorization)
        return {"event_kind": "CONTINUATION_COMMIT_PUSHED", "event_id": "authorization:" + parsed["authorization_digest"],
                "pull_request": PR, "head_sha": self.resulting, "replacement_pull_request": None,
                "classification": None, "follow_up": None, "authorization": authorization,
                "continuation_evidence": copy.deepcopy(self.evidence)}
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
    for index, (thread_id, comment_id, body_digest, is_outdated) in enumerate(
        predecessor_findings
    ):
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
                "correction_finding_id": PR_905_CORRECTION_AUTHORITY[
                    "material_finding_ids"
                ][index],
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
    @staticmethod
    def _issue786_closed_source(root: Path) -> Path:
        """Construct the fixed accepted-main/candidate object universe."""

        source = root / "issue786-closed-source"
        source.mkdir()
        subprocess.run(
            ["git", "-C", str(source), "init", "--quiet"], check=True,
        )
        # The fixture proves source-object-database immutability, so suppress
        # Git's environment-dependent background maintenance before either
        # local transport can schedule it.
        for key, value in (
            ("maintenance.auto", "false"),
            ("gc.auto", "0"),
            ("fetch.writeCommitGraph", "false"),
        ):
            subprocess.run(
                ["git", "-C", str(source), "config", key, value], check=True,
            )
        subprocess.run(
            [
                "git", "-C", str(source), "fetch", "--quiet", "--no-tags",
                str(Path(__file__).resolve().parents[1]),
                "471739a201f483c2e5c26eb5955527907d415eff",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(source), "fetch", "--quiet", "--no-tags",
                str(
                    Path(__file__).resolve().parent
                    / "fixtures/secpal-pr-review-actions/issue786-collision-head.bundle"
                ),
                "refs/remotes/origin/pr-789:refs/heads/issue786",
            ],
            check=True,
        )
        for oid in (
            "471739a201f483c2e5c26eb5955527907d415eff",
            "62b023f8e2807d0077b291e7af9a280888f1076c",
            "833eef2afc063ae777e7e2b64b2f252e3fe1e49e",
        ):
            completed = subprocess.run(
                ["git", "-C", str(source), "cat-file", "-t", oid],
                env={"GIT_NO_LAZY_FETCH": "1"},
                check=True,
                capture_output=True,
                text=True,
            )
            if completed.stdout.strip() != "commit":
                raise AssertionError("closed fixture authority is not a commit")
        if (source / ".git/objects/info/alternates").exists():
            raise AssertionError("closed fixture unexpectedly uses object alternates")
        if subprocess.run(
            ["git", "-C", str(source), "config", "--get-regexp", "^remote\\."],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0:
            raise AssertionError("closed fixture unexpectedly retains a remote")
        return source

    @staticmethod
    def _git_object_database_snapshot(root: Path) -> tuple[tuple[str, str], ...]:
        objects = root / ".git/objects"
        return tuple(
            (
                path.relative_to(objects).as_posix(),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted(objects.rglob("*"))
            if path.is_file()
        )

    def test_issue786_full_historical_closure_reproduces_accepted_bound(
        self,
    ) -> None:
        from contextlib import contextmanager
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        @contextmanager
        def no_dependencies(_root: Path):
            yield {}

        observed_before_historical = []

        def transfer_full_historical_closure(
            importer, prerequisites, _required_objects, _required_paths,
        ):
            accounting = importer.accounting()
            observed_before_historical.append(accounting)
            for commit in prerequisites:
                importer.transfer(
                    commit,
                    "commit",
                    category=version_collision.HISTORICAL_PREREQUISITE_TREES,
                )
                importer.transfer(
                    importer.commit_trees[commit],
                    "tree",
                    category=version_collision.HISTORICAL_PREREQUISITE_TREES,
                )

        with tempfile.TemporaryDirectory() as directory:
            source = self._issue786_closed_source(Path(directory))
            derived = "fa4b8626c75a109cefa24beec1095bb7abf1580f"
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(source), "cat-file", "-e", derived],
                    env={"GIT_NO_LAZY_FETCH": "1"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode,
                0,
            )
            before = self._git_object_database_snapshot(source)
            complete_validation_reached = False
            with (
                mock.patch.object(
                    version_collision,
                    "_authenticate_installed_collision_issuer",
                    return_value="471739a201f483c2e5c26eb5955527907d415eff",
                ),
                mock.patch.object(
                    version_collision,
                    "_observe_main",
                    return_value="471739a201f483c2e5c26eb5955527907d415eff",
                ),
                mock.patch.object(
                    version_collision, "_require_current_collision_predecessor",
                ),
                mock.patch.object(version_collision, "_require_accepted_issuer"),
                mock.patch.object(
                    exact_source_safety,
                    "_collision_validation_dependencies",
                    no_dependencies,
                ),
                mock.patch.object(
                    version_collision,
                    "_transfer_validation_object_requirements",
                    side_effect=transfer_full_historical_closure,
                ),
                mock.patch.object(
                    version_collision, "MAX_IMPORTED_BYTES", 8 * 1024 * 1024,
                ),
                mock.patch.object(
                    version_collision, "IMPORT_CATEGORY_BYTE_LIMITS", {},
                ),
                self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "source object closure exceeds the byte bound",
                ),
            ):
                with version_collision.collision_complete_validation(
                    repository=REPOSITORY,
                    delivery_issue=786,
                    pull_request=789,
                    predecessor_head=(
                        "62b023f8e2807d0077b291e7af9a280888f1076c"
                    ),
                    resulting_tree=derived,
                    repository_root=source,
                ):
                    complete_validation_reached = True

            self.assertFalse(complete_validation_reached)
            self.assertEqual(len(observed_before_historical), 1)
            accounting = observed_before_historical[0]
            self.assertEqual(accounting["total_unique_bytes"], 7_973_066)
            self.assertEqual(
                accounting["total_unique_bytes"]
                - accounting["bytes_by_category"][
                    version_collision.DERIVED_RENUMBER_OBJECTS
                ],
                7_867_055,
            )
            self.assertEqual(self._git_object_database_snapshot(source), before)
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(source), "cat-file", "-e", derived],
                    env={"GIT_NO_LAZY_FETCH": "1"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode,
                0,
            )

    def test_issue786_minimal_validation_closure_is_exact_and_deduplicated(
        self,
    ) -> None:
        from contextlib import contextmanager
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        @contextmanager
        def no_dependencies(_root: Path):
            yield {}

        with tempfile.TemporaryDirectory() as directory:
            source = self._issue786_closed_source(Path(directory))
            before = self._git_object_database_snapshot(source)
            with (
                mock.patch.object(
                    version_collision,
                    "_authenticate_installed_collision_issuer",
                    return_value="471739a201f483c2e5c26eb5955527907d415eff",
                ),
                mock.patch.object(
                    version_collision,
                    "_observe_main",
                    return_value="471739a201f483c2e5c26eb5955527907d415eff",
                ),
                mock.patch.object(
                    version_collision, "_require_current_collision_predecessor",
                ),
                mock.patch.object(version_collision, "_require_accepted_issuer"),
                mock.patch.object(
                    exact_source_safety,
                    "_collision_validation_dependencies",
                    no_dependencies,
                ),
            ):
                with version_collision.collision_complete_validation(
                    repository=REPOSITORY,
                    delivery_issue=786,
                    pull_request=789,
                    predecessor_head=(
                        "62b023f8e2807d0077b291e7af9a280888f1076c"
                    ),
                    resulting_tree=(
                        "fa4b8626c75a109cefa24beec1095bb7abf1580f"
                    ),
                    repository_root=source,
                ) as execution:
                    accounting = execution.object_accounting
                    collision = execution.collision.to_dict()
                    self.assertEqual(
                        collision["resulting_tree"],
                        "fa4b8626c75a109cefa24beec1095bb7abf1580f",
                    )
                    self.assertEqual(collision["occupied_version"], "1.2")
                    self.assertEqual(collision["free_version"], "1.3")
                    for command in (
                        [
                            "python3",
                            "tests/secpal-pr-review-actions-unit.py",
                            (
                                "FastPathTests."
                                "test_prior_771_resolved_tree_accepts_"
                                "authenticated_separator_lines"
                            ),
                        ],
                        ["./tests/secpal-pr-review-skill-policy.sh"],
                    ):
                        completed = subprocess.run(
                            command,
                            cwd=execution.execution_root,
                            stdin=subprocess.DEVNULL,
                            capture_output=True,
                            check=False,
                        )
                        self.assertEqual(
                            completed.returncode,
                            0,
                            completed.stderr.decode(errors="replace"),
                        )
                    execution.verify_execution_root()

            self.assertEqual(accounting["total_unique_objects"], 1_004)
            self.assertEqual(accounting["total_unique_bytes"], 10_286_316)
            self.assertEqual(
                accounting["source_bytes_before_historical_prerequisites"],
                7_867_055,
            )
            self.assertEqual(
                accounting["unique_bytes_before_historical_prerequisites"],
                7_973_066,
            )
            self.assertEqual(
                accounting["bytes_required_by_historical_prerequisites"],
                2_313_250,
            )
            self.assertEqual(
                accounting["final_minimal_required_bytes"], 10_286_316,
            )
            self.assertEqual(accounting["duplicate_oid_references"], 818)
            self.assertEqual(
                accounting["bytes_by_category"],
                {
                    version_collision.HISTORY_COMMIT_OBJECTS: 883_335,
                    version_collision.STRUCTURAL_TREE_OBJECTS: 55_948,
                    version_collision.OWNER_SOURCE_BLOBS: 476_338,
                    version_collision.DERIVED_RENUMBER_OBJECTS: 106_011,
                    version_collision.CANDIDATE_VALIDATION_TREE_CLOSURE: (
                        5_891_218
                    ),
                    version_collision.ACCEPTED_HARNESS_BLOBS: 521_869,
                    version_collision.VALIDATION_DEPENDENCY_BLOBS: 0,
                    version_collision.HISTORICAL_PREREQUISITE_TREES: (
                        2_313_250
                    ),
                    version_collision.OTHER: 38_347,
                },
            )
            self.assertEqual(
                accounting["objects_by_category"],
                {
                    version_collision.HISTORY_COMMIT_OBJECTS: 500,
                    version_collision.STRUCTURAL_TREE_OBJECTS: 69,
                    version_collision.OWNER_SOURCE_BLOBS: 3,
                    version_collision.DERIVED_RENUMBER_OBJECTS: 4,
                    version_collision.CANDIDATE_VALIDATION_TREE_CLOSURE: 357,
                    version_collision.ACCEPTED_HARNESS_BLOBS: 3,
                    version_collision.VALIDATION_DEPENDENCY_BLOBS: 0,
                    version_collision.HISTORICAL_PREREQUISITE_TREES: 67,
                    version_collision.OTHER: 1,
                },
            )
            # Full historical recursion was unnecessary (4,009,524 bytes fell
            # to 2,313,250), yet the minimal closure still exceeds 8 MiB.
            # Therefore the authenticated root-cause decision is BOTH.
            self.assertLess(2_313_250, 4_009_524)
            self.assertGreater(
                accounting["final_minimal_required_bytes"], 8 * 1024 * 1024,
            )
            self.assertEqual(
                sum(accounting["bytes_by_category"].values()),
                accounting["total_unique_bytes"],
            )
            self.assertEqual(
                sum(accounting["objects_by_category"].values()),
                accounting["total_unique_objects"],
            )
            self.assertTrue(
                all(
                    item["references"] >= len(item["memberships"])
                    for item in accounting["object_memberships"]
                )
            )
            self.assertEqual(self._git_object_database_snapshot(source), before)

    def test_collision_preparation_recomputes_tree_absent_from_closed_source(
        self,
    ) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixture"
            fixture_root.mkdir()
            fixture = CollisionCompositionFixture(fixture_root)
            source = root / "closed-source"
            source.mkdir()
            subprocess.run(
                ["git", "-C", str(source), "init", "--quiet"], check=True,
            )
            importer = version_collision._BoundedObjectImporter(
                fixture.root, source,
            )
            importer.import_histories_and_merge_base(
                fixture.main, fixture.predecessor,
            )
            for tree in set(importer.commit_trees.values()):
                importer.transfer(tree, "tree")

            def object_snapshot() -> tuple[tuple[str, str], ...]:
                objects = source / ".git/objects"
                return tuple(
                    (path.relative_to(objects).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
                    for path in sorted(objects.rglob("*"))
                    if path.is_file()
                )

            absent = subprocess.run(
                [
                    "git", "-C", str(source), "cat-file", "-e",
                    fixture.resulting_tree + "^{tree}",
                ],
                env={"GIT_NO_LAZY_FETCH": "1"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            self.assertNotEqual(absent.returncode, 0)
            before = object_snapshot()
            with (
                mock.patch.object(
                    version_collision,
                    "_authenticate_installed_collision_issuer",
                    return_value=fixture.main,
                ),
                mock.patch.object(
                    version_collision,
                    "_require_current_collision_predecessor",
                    return_value=fixture.observed,
                ),
                mock.patch.object(
                    version_collision, "_observe_main", return_value=fixture.main,
                ),
            ):
                present = version_collision.prepare_collision_tree(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=fixture.predecessor,
                    resulting_tree=fixture.resulting_tree,
                    repository_root=fixture.root,
                ).to_dict()
                with mock.patch.object(
                    version_collision._BoundedObjectImporter,
                    "materialize_derived",
                    side_effect=AssertionError(
                        "wrong expectation reached derived materialization"
                    ),
                ) as materialize:
                    with self.assertRaisesRegex(
                        version_collision.VersionCollisionError,
                        "recomputed collision tree",
                    ):
                        version_collision.prepare_collision_tree(
                            repository=REPOSITORY,
                            delivery_issue=ISSUE,
                            pull_request=PR,
                            predecessor_head=fixture.predecessor,
                            resulting_tree="f" * 40,
                            repository_root=source,
                        )
                    materialize.assert_not_called()
                collision = version_collision.prepare_collision_tree(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=fixture.predecessor,
                    resulting_tree=fixture.resulting_tree,
                    repository_root=source,
                ).to_dict()

            self.assertEqual(collision, present)
            self.assertEqual(collision["resulting_tree"], fixture.resulting_tree)
            self.assertEqual(collision["free_version"], "1.3")
            self.assertEqual(
                len(collision["delta"]["changes"][0]["replacement_offsets"]),
                4,
            )
            self.assertEqual(object_snapshot(), before)
            self.assertNotEqual(
                subprocess.run(
                    [
                        "git", "-C", str(source), "cat-file", "-e",
                        fixture.resulting_tree + "^{tree}",
                    ],
                    env={"GIT_NO_LAZY_FETCH": "1"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode,
                0,
            )

    def test_collision_complete_validation_uses_closed_accepted_harness(
        self,
    ) -> None:
        from contextlib import contextmanager
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        @contextmanager
        def no_dependencies(_root: Path):
            yield {}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixture"
            fixture_root.mkdir()
            fixture = CollisionCompositionFixture(
                fixture_root, validation_harness=True,
            )
            source = root / "closed-source"
            source.mkdir()
            subprocess.run(
                ["git", "-C", str(source), "init", "--quiet"], check=True,
            )
            importer = version_collision._BoundedObjectImporter(
                fixture.root, source,
            )
            importer.import_histories_and_merge_base(
                fixture.main, fixture.predecessor,
            )
            for tree in set(importer.commit_trees.values()):
                importer.transfer(tree, "tree")
            objects = source / ".git/objects"
            before = tuple(
                (
                    path.relative_to(objects).as_posix(),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in sorted(objects.rglob("*"))
                if path.is_file()
            )
            self.assertNotEqual(
                subprocess.run(
                    [
                        "git", "-C", str(source), "cat-file", "-e",
                        fixture.resulting_tree + "^{tree}",
                    ],
                    env={"GIT_NO_LAZY_FETCH": "1"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode,
                0,
            )
            with (
                mock.patch.object(
                    version_collision,
                    "_authenticate_installed_collision_issuer",
                    return_value=fixture.main,
                ),
                mock.patch.object(
                    version_collision,
                    "_require_current_collision_predecessor",
                    return_value=fixture.observed,
                ),
                mock.patch.object(
                    version_collision, "_observe_main", return_value=fixture.main,
                ),
                mock.patch.object(version_collision, "_require_accepted_issuer"),
                mock.patch.object(
                    authority, "_load_lifecycle_trust_policy",
                    return_value=fixture.policy,
                ),
                mock.patch.object(
                    exact_source_safety,
                    "_collision_validation_dependencies",
                    no_dependencies,
                ),
                mock.patch.dict(
                    version_collision.COLLISION_VALIDATION_BUNDLE_BASE_OBJECTS,
                    {
                        fixture.bundle_blob_oid: (
                            ("blob", fixture.validation_required_blob),
                        ),
                    },
                ),
                mock.patch.dict(
                    version_collision.COLLISION_VALIDATION_SNAPSHOT_PREREQUISITE_PATHS,
                    {
                        fixture.snapshot_blob_oid: (
                            version_collision.COLLISION_AUTHORITY_PATH,
                        ),
                    },
                ),
                mock.patch.object(
                    version_collision,
                    "_BoundedObjectImporter",
                    side_effect=version_collision._BoundedObjectImporter,
                ) as importer_factory,
            ):
                with version_collision.collision_complete_validation(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=fixture.predecessor,
                    resulting_tree=fixture.resulting_tree,
                    repository_root=source,
                ) as execution:
                    profile = execution.registry_binding[
                        "collision_validation_authority"
                    ]
                    projected = execution.execution_root / (
                        "tests/secpal-pr-review-actions-unit.py"
                    )
                    self.assertEqual(
                        sum(
                            len(item["current_identity_offsets"])
                            for item in profile["validation_projection_sources"]
                        ),
                        10,
                    )
                    self.assertEqual(
                        profile["registry"]["source_commit"], fixture.base,
                    )
                    self.assertEqual(
                        profile["validation_command_set"],
                        execution.registry_binding["validation"],
                    )
                    self.assertEqual(projected.read_bytes().count(b'"1.3"'), 9)
                    self.assertIn(
                        b'def historical_v12_fixture():\n    return "1.2"',
                        projected.read_bytes(),
                    )
                    self.assertIn(
                        b"{'1.1', '1.2', \"1.3\"}",
                        (
                            execution.execution_root
                            / version_collision.VALIDATION_ACTIONS_PATH
                        ).read_bytes(),
                    )
                    self.assertEqual(
                        subprocess.run(
                            [
                                "git", "-C", str(execution.execution_root),
                                "rev-parse", "HEAD",
                            ],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                        fixture.predecessor,
                    )
                    self.assertEqual(
                        (execution.execution_root / version_collision.SOURCE_PATH).read_bytes(),
                        fixture.source("1.3", "authenticated_resolution_delta"),
                    )
                    absent_result = (
                        execution.collision.to_dict(), copy.deepcopy(profile)
                    )
                    absent_commands = tuple(
                        subprocess.run(
                            command["argv"],
                            cwd=execution.execution_root,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        ).returncode
                        for command in profile["validation_command_set"]
                    )
                with version_collision.collision_complete_validation(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=fixture.predecessor,
                    resulting_tree=fixture.resulting_tree,
                    repository_root=fixture.root,
                ) as execution:
                    present_profile = execution.registry_binding[
                        "collision_validation_authority"
                    ]
                    present_result = (
                        execution.collision.to_dict(), copy.deepcopy(present_profile)
                    )
                    present_commands = tuple(
                        subprocess.run(
                            command["argv"],
                            cwd=execution.execution_root,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        ).returncode
                        for command in present_profile["validation_command_set"]
                    )
                self.assertEqual(absent_result, present_result)
                self.assertEqual(absent_commands, present_commands)
                self.assertEqual(absent_commands, (0, 0))
                self.assertEqual(importer_factory.call_count, 2)
            self.assertEqual(
                tuple(
                    (
                        path.relative_to(objects).as_posix(),
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                    for path in sorted(objects.rglob("*"))
                    if path.is_file()
                ),
                before,
            )
            self.assertNotEqual(
                subprocess.run(
                    [
                        "git", "-C", str(source), "cat-file", "-e",
                        fixture.resulting_tree + "^{tree}",
                    ],
                    env={"GIT_NO_LAZY_FETCH": "1"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode,
                0,
            )

    def test_collision_validation_prerequisite_requires_protected_main_history(
        self,
    ) -> None:
        from contextlib import contextmanager
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        @contextmanager
        def no_dependencies(_root: Path):
            yield {}

        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory) / "fixture"
            fixture_root.mkdir()
            fixture = CollisionCompositionFixture(
                fixture_root,
                validation_harness=True,
                validation_prerequisite_on_predecessor_only=True,
            )
            with (
                mock.patch.object(
                    version_collision,
                    "_authenticate_installed_collision_issuer",
                    return_value=fixture.main,
                ),
                mock.patch.object(
                    version_collision,
                    "_require_current_collision_predecessor",
                    return_value=fixture.observed,
                ),
                mock.patch.object(
                    version_collision, "_observe_main", return_value=fixture.main,
                ),
                mock.patch.object(version_collision, "_require_accepted_issuer"),
                mock.patch.object(
                    authority,
                    "_load_lifecycle_trust_policy",
                    return_value=fixture.policy,
                ),
                mock.patch.object(
                    exact_source_safety,
                    "_collision_validation_dependencies",
                    no_dependencies,
                ),
                mock.patch.dict(
                    version_collision.COLLISION_VALIDATION_BUNDLE_BASE_OBJECTS,
                    {
                        fixture.bundle_blob_oid: (
                            ("blob", fixture.validation_required_blob),
                        ),
                    },
                ),
                mock.patch.dict(
                    version_collision.COLLISION_VALIDATION_SNAPSHOT_PREREQUISITE_PATHS,
                    {
                        fixture.snapshot_blob_oid: (
                            version_collision.COLLISION_AUTHORITY_PATH,
                        ),
                    },
                ),
                self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "outside protected-main history",
                ),
            ):
                with version_collision.collision_complete_validation(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=fixture.predecessor,
                    resulting_tree=fixture.resulting_tree,
                    repository_root=fixture.root,
                ):
                    pass

    def test_collision_validation_omits_unconsumed_historical_blobs(self) -> None:
        from contextlib import contextmanager
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        @contextmanager
        def no_dependencies(_root: Path):
            yield {}

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(
                Path(directory),
                validation_harness=True,
                validation_prerequisite_unconsumed_bytes=(
                    version_collision.MAX_BLOB_BYTES + 1
                ),
            )
            with (
                mock.patch.object(
                    version_collision,
                    "_authenticate_installed_collision_issuer",
                    return_value=fixture.main,
                ),
                mock.patch.object(
                    version_collision,
                    "_require_current_collision_predecessor",
                    return_value=fixture.observed,
                ),
                mock.patch.object(
                    version_collision, "_observe_main", return_value=fixture.main,
                ),
                mock.patch.object(version_collision, "_require_accepted_issuer"),
                mock.patch.object(
                    authority,
                    "_load_lifecycle_trust_policy",
                    return_value=fixture.policy,
                ),
                mock.patch.object(
                    exact_source_safety,
                    "_collision_validation_dependencies",
                    no_dependencies,
                ),
                mock.patch.dict(
                    version_collision.COLLISION_VALIDATION_BUNDLE_BASE_OBJECTS,
                    {
                        fixture.bundle_blob_oid: (
                            ("blob", fixture.validation_required_blob),
                        ),
                    },
                ),
                mock.patch.dict(
                    version_collision.COLLISION_VALIDATION_SNAPSHOT_PREREQUISITE_PATHS,
                    {
                        fixture.snapshot_blob_oid: (
                            version_collision.COLLISION_AUTHORITY_PATH,
                        ),
                    },
                ),
            ):
                with version_collision.collision_complete_validation(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=fixture.predecessor,
                    resulting_tree=fixture.resulting_tree,
                    repository_root=fixture.root,
                ) as execution:
                    dependencies = execution.registry_binding[
                        "collision_validation_authority"
                    ]["validation_object_dependencies"]
                    self.assertEqual(len(dependencies), 2)
                    self.assertTrue(dependencies[0]["required_objects"])
                    self.assertTrue(dependencies[1]["required_paths"])

    def test_collision_validation_requirements_are_closed_issuer_authority(
        self,
    ) -> None:
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        prerequisite = "a" * 40
        bundle_source = (
            b"# v2 git bundle\n-"
            + prerequisite.encode("ascii")
            + b" prerequisite\n"
            + prerequisite.encode("ascii")
            + b" refs/heads/fixture\n\nPACKx"
        )
        with self.assertRaisesRegex(
            version_collision.VersionCollisionError,
            "object requirements are unavailable",
        ):
            version_collision._validation_object_requirements(
                version_collision.COLLISION_VALIDATION_BUNDLE_PATHS[0],
                "f" * 40,
                bundle_source,
            )
        with self.assertRaisesRegex(
            version_collision.VersionCollisionError,
            "snapshot requirements are unavailable",
        ):
            version_collision._validation_object_requirements(
                version_collision.COLLISION_VALIDATION_SNAPSHOT_PATHS[0],
                "f" * 40,
                b'P21_BASELINE="' + prerequisite.encode("ascii") + b'"\n',
            )
        self.assertEqual(
            version_collision.MAX_IMPORTED_BYTES,
            exact_source_safety._COLLISION_MAX_AGGREGATE_BYTES,
        )
        self.assertEqual(
            version_collision.MAX_CANDIDATE_VALIDATION_BYTES,
            exact_source_safety._COLLISION_MAX_CANDIDATE_BYTES,
        )
        self.assertEqual(
            version_collision.MAX_HISTORICAL_PREREQUISITE_BYTES,
            exact_source_safety._COLLISION_MAX_HISTORICAL_BYTES,
        )

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            for root in (source, destination):
                root.mkdir()
                subprocess.run(
                    ["git", "-C", str(root), "init", "--quiet"],
                    check=True,
                )
            oid = subprocess.run(
                ["git", "-C", str(source), "hash-object", "-w", "--stdin"],
                input=b"object",
                check=True,
                capture_output=True,
            ).stdout.decode().strip()
            importer = version_collision._BoundedObjectImporter(
                source, destination,
            )
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "accounting category is unsupported",
            ):
                importer.transfer(oid, "blob", category="CALLER_SELECTED")
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "requirements are ambiguous",
            ):
                version_collision._transfer_validation_object_requirements(
                    importer,
                    (prerequisite,),
                    (("blob", oid), ("blob", oid)),
                    (),
                )

    def test_collision_importer_rechecks_consumed_source_object_bytes(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            source.mkdir()
            destination.mkdir()
            subprocess.run(
                ["git", "-C", str(source), "init", "--quiet"], check=True,
            )
            subprocess.run(
                ["git", "-C", str(destination), "init", "--quiet"], check=True,
            )
            oid = subprocess.run(
                ["git", "-C", str(source), "hash-object", "-w", "--stdin"],
                input=b"trusted",
                check=True,
                capture_output=True,
            ).stdout.decode().strip()
            importer = version_collision._BoundedObjectImporter(
                source, destination,
            )
            importer.transfer(oid, "blob")
            count_before = subprocess.run(
                ["git", "-C", str(source), "count-objects", "-v"],
                check=True,
                capture_output=True,
            ).stdout
            object_path = source / ".git" / "objects" / oid[:2] / oid[2:]
            object_path.chmod(0o644)
            object_path.write_bytes(zlib.compress(b"blob 7\0changed"))
            count_after = subprocess.run(
                ["git", "-C", str(source), "count-objects", "-v"],
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual(count_before, count_after)
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "source object.*changed",
            ):
                importer.verify_source_objects_unchanged()

    def test_collision_source_snapshot_binds_refs(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "--quiet"], check=True,
            )
            oid = subprocess.run(
                ["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                input=b"unrelated",
                check=True,
                capture_output=True,
            ).stdout.decode().strip()
            before = version_collision._source_repository_state(root)
            subprocess.run(
                ["git", "-C", str(root), "update-ref", "refs/tags/untrusted", oid],
                check=True,
            )
            self.assertNotEqual(
                version_collision._source_repository_state(root), before,
            )

    def test_collision_validation_rehashes_candidate_tree_after_execution(
        self,
    ) -> None:
        from scripts.secpal_pr_review import exact_source_safety

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "--quiet"], check=True,
            )
            candidate = root / "candidate.txt"
            candidate.write_bytes(b"a" * (70 * 1024))
            candidate.chmod(0o644)
            subprocess.run(
                ["git", "-C", str(root), "add", "--", "candidate.txt"],
                check=True,
            )
            tree = subprocess.run(
                ["git", "-C", str(root), "write-tree"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            blob = subprocess.run(
                ["git", "-C", str(root), "hash-object", "candidate.txt"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            arguments = (
                root,
                tree,
                {"candidate.txt": ("100644", blob)},
                {},
                {},
                [],
                tree,
                exact_source_safety._collision_git_state(root),
            )
            exact_source_safety._verify_collision_validation_root(*arguments)
            object_path = root / ".git" / "objects" / tree[:2] / tree[2:]
            object_path.chmod(0o644)
            object_path.write_bytes(zlib.compress(b"tree 0\0"))
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(root), "cat-file", "-t", tree],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "tree",
            )
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError, "object.*identity",
            ):
                exact_source_safety._verify_collision_validation_root(*arguments)

    def test_collision_validation_rejects_private_git_state_mutation(self) -> None:
        from scripts.secpal_pr_review import exact_source_safety

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "--quiet"], check=True,
            )
            state = exact_source_safety._collision_git_state(root)
            (root / ".git" / "HEAD").write_text(
                "ref: refs/heads/untrusted\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError,
                "private Git state",
            ):
                exact_source_safety._require_collision_git_state(root, state)

    def test_collision_fixture_projection_keeps_historical_versions_pinned(
        self,
    ) -> None:
        from scripts.secpal_pr_review import exact_source_safety

        source = b'''class CurrentIdentityFixtures:
    def test_parent2_preservation_cannot_delete_parent1_only_work(self):
        validate(schema_version="1.2")
    def test_parent2_preservation_uses_exact_new_attestation_versions(self):
        validate(schema_version="1.2")
    def test_ready_integration_accepts_authenticated_current_ready_histories(self):
        validate(schema_version="1.2")
    def test_ready_integration_authenticates_exact_parent2_preservation(self):
        validate(schema_version="1.2")
        validate(schema_version="1.2")
    def test_ready_integration_mixes_conflict_and_parent2_preservation(self):
        validate(schema_version="1.2")
        validate(schema_version="1.2")
    def test_ready_integration_v12_delta_uses_registered_item_limit_before_git_work(self):
        validate(schema_version="1.2")
        validate(schema_version="1.2")

def historical_v12_fixture():
    return "1.2"
'''
        projected, offsets = (
            exact_source_safety._project_collision_current_identity_fixtures(
                "tests/secpal-pr-review-actions-unit.py",
                source,
                occupied_version="1.2",
                implementation_identity="1.3",
            )
        )
        self.assertEqual(len(offsets), 9)
        self.assertIn(
            b'def historical_v12_fixture():\n    return "1.2"', projected,
        )
        self.assertEqual(projected.count(b'"1.3"'), 9)
        for changed in (
            source.replace(
                b"test_parent2_preservation_uses_exact_new_attestation_versions",
                b"renamed_fixture",
            ),
            source.replace(b'"1.2"', b'"1.3"', 1),
        ):
            with self.assertRaises(authority.LifecycleAuthorityError):
                exact_source_safety._project_collision_current_identity_fixtures(
                    "tests/secpal-pr-review-actions-unit.py",
                    changed,
                    occupied_version="1.2",
                    implementation_identity="1.3",
                )

    def test_collision_importer_recomputes_real_non_descendant_merge_side_base(
        self,
    ) -> None:
        """Mirror the real #894 topology without importing its delivery authority."""

        from scripts.secpal_pr_review import version_collision

        self.assertEqual(
            (REAL_894_MERGE_BASE, REAL_894_MERGE_SIDE_PARENT),
            (
                "aa7d9e4485abbceed01136cd81fdbbd353f877bc",
                "7bcb9e622b608742707dbe9ff8cbaebfb561c7cd",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            source.mkdir()
            destination.mkdir()

            def git(root: Path, *arguments: str, data: bytes | None = None) -> str:
                return subprocess.run(
                    ["git", "-C", str(root), *arguments],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                ).stdout.decode().strip()

            git(source, "init", "--quiet")
            git(destination, "init", "--quiet")
            git(source, "config", "user.name", "Collision Fixture")
            git(source, "config", "user.email", "collision-fixture@secpal.test")
            tree = git(source, "mktree", data=b"")

            def commit(message: str, *parents: str) -> str:
                arguments = ["commit-tree", tree, "-m", message]
                for parent in parents:
                    arguments.extend(("-p", parent))
                return git(source, *arguments)

            base = commit("authenticated common base")
            main = commit("protected main", base)
            unrelated_root = commit("merge-side root")
            merge_side = commit("merge-side parent", unrelated_root)
            predecessor = commit("legitimate merge", base, merge_side)
            self.assertEqual(git(source, "merge-base", "--all", main, predecessor), base)
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(source), "merge-base", "--is-ancestor", base, merge_side],
                    check=False,
                ).returncode,
                0,
            )

            importer = version_collision._BoundedObjectImporter(source, destination)
            derived = importer.import_histories_and_merge_base(main, predecessor)
            self.assertEqual(derived, base)
            self.assertEqual(
                git(destination, "merge-base", "--all", main, predecessor),
                base,
            )

    def test_collision_importer_rejects_ambiguous_unreachable_and_excessive_history(
        self,
    ) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            subprocess.run(["git", "-C", str(source), "init", "--quiet"], check=True)

            def git(*arguments: str, data: bytes | None = None) -> str:
                return subprocess.run(
                    ["git", "-C", str(source), *arguments],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                ).stdout.decode().strip()

            git("config", "user.name", "Collision Fixture")
            git("config", "user.email", "collision-fixture@secpal.test")

            tree = git("mktree", data=b"")

            def commit(message: str, *parents: str) -> str:
                arguments = ["commit-tree", tree, "-m", message]
                for parent in parents:
                    arguments.extend(("-p", parent))
                return git(*arguments)

            left = commit("left root")
            right = commit("right root")
            ambiguous_left = commit("left merge", left, right)
            ambiguous_right = commit("right merge", right, left)
            deep = commit("depth one", left)
            deeper = commit("depth two", deep)
            fanout = commit("fanout", left, right, deep)

            for label, first, second, limits, message in (
                ("ambiguous", ambiguous_left, ambiguous_right, {}, "unique merge base"),
                ("unreachable", left, right, {}, "unique merge base"),
                ("depth", deeper, left, {"MAX_COMMIT_DEPTH": 1}, "history depth"),
                ("fanout", fanout, left, {"MAX_PARENT_FANOUT": 2}, "parent fanout"),
                ("bytes", deep, left, {"MAX_IMPORTED_BYTES": 1}, "byte bound"),
            ):
                with self.subTest(label=label), tempfile.TemporaryDirectory() as target:
                    destination = Path(target)
                    subprocess.run(["git", "-C", str(destination), "init", "--quiet"], check=True)
                    patches = [mock.patch.object(version_collision, name, value) for name, value in limits.items()]
                    for active in patches:
                        active.start()
                    try:
                        with self.assertRaisesRegex(version_collision.VersionCollisionError, message):
                            version_collision._BoundedObjectImporter(
                                source, destination,
                            ).import_histories_and_merge_base(first, second)
                    finally:
                        for active in reversed(patches):
                            active.stop()

    def test_collision_importer_acquires_only_required_tree_blobs(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            source.mkdir()
            destination.mkdir()

            def git(root: Path, *arguments: str, data: bytes | None = None) -> str:
                return subprocess.run(
                    ["git", "-C", str(root), *arguments],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                ).stdout.decode().strip()

            git(source, "init", "--quiet")
            git(destination, "init", "--quiet")
            wanted = git(source, "hash-object", "-w", "--stdin", data=b'owner = "1.2"\n')
            unrelated = git(
                source,
                "hash-object",
                "-w",
                "--stdin",
                data=b"x" * (version_collision.MAX_BLOB_BYTES + 1),
            )
            subtree = git(
                source,
                "mktree",
                "-z",
                data=(
                    f"100644 blob {wanted}\tfast_path.py\0"
                    f"100644 blob {unrelated}\tunrelated.bin\0"
                ).encode(),
            )
            tree = git(
                source,
                "mktree",
                "-z",
                data=f"040000 tree {subtree}\tsecpal_pr_review\0".encode(),
            )
            importer = version_collision._BoundedObjectImporter(source, destination)
            importer.transfer(tree, "tree", import_blobs=False)
            importer.transfer_path(
                tree,
                "secpal_pr_review/fast_path.py",
            )
            self.assertIn(wanted, importer.imported)
            self.assertNotIn(unrelated, importer.imported)
            self.assertEqual(
                git(destination, "cat-file", "blob", wanted),
                'owner = "1.2"',
            )

    def test_collision_importer_accounts_unique_oids_across_semantic_phases(
        self,
    ) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            for root in (source, destination):
                root.mkdir()
                subprocess.run(
                    ["git", "-C", str(root), "init", "--quiet"], check=True,
                )
            payload = b"one physical object"
            oid = subprocess.run(
                ["git", "-C", str(source), "hash-object", "-w", "--stdin"],
                input=payload,
                check=True,
                capture_output=True,
            ).stdout.decode().strip()
            importer = version_collision._BoundedObjectImporter(
                source, destination,
            )
            importer.transfer(
                oid,
                "blob",
                category=version_collision.HISTORY_COMMIT_OBJECTS,
            )
            importer.transfer(
                oid,
                "blob",
                category=version_collision.OTHER,
            )
            importer.materialize_derived("blob", oid, payload)

            accounting = importer.accounting()
            self.assertEqual(accounting["total_unique_objects"], 1)
            self.assertEqual(accounting["total_unique_bytes"], len(payload))
            self.assertEqual(accounting["duplicate_oid_references"], 2)
            self.assertEqual(
                accounting["bytes_by_category"],
                {
                    category: (
                        len(payload)
                        if category == version_collision.HISTORY_COMMIT_OBJECTS
                        else 0
                    )
                    for category in version_collision.IMPORT_CATEGORIES
                },
            )
            self.assertEqual(
                accounting["objects_by_category"][
                    version_collision.HISTORY_COMMIT_OBJECTS
                ],
                1,
            )
            self.assertEqual(
                accounting["semantic_bytes_by_category"],
                {
                    category: (
                        len(payload)
                        if category in {
                            version_collision.HISTORY_COMMIT_OBJECTS,
                            version_collision.DERIVED_RENUMBER_OBJECTS,
                            version_collision.OTHER,
                        }
                        else 0
                    )
                    for category in version_collision.IMPORT_CATEGORIES
                },
            )
            self.assertEqual(
                accounting["object_memberships"],
                [
                    {
                        "oid": oid,
                        "kind": "blob",
                        "bytes": len(payload),
                        "memberships": [
                            version_collision.HISTORY_COMMIT_OBJECTS,
                            version_collision.DERIVED_RENUMBER_OBJECTS,
                            version_collision.OTHER,
                        ],
                        "attributed_category": (
                            version_collision.HISTORY_COMMIT_OBJECTS
                        ),
                        "references": 3,
                    }
                ],
            )

    def test_collision_importer_accepts_maxima_and_rejects_max_plus_one(
        self,
    ) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            subprocess.run(
                ["git", "-C", str(source), "init", "--quiet"], check=True,
            )

            def git(*arguments: str, data: bytes | None = None) -> str:
                return subprocess.run(
                    ["git", "-C", str(source), *arguments],
                    input=data,
                    check=True,
                    capture_output=True,
                ).stdout.decode().strip()

            def importer(label: str):
                destination = root / label
                destination.mkdir()
                subprocess.run(
                    ["git", "-C", str(destination), "init", "--quiet"],
                    check=True,
                )
                return version_collision._BoundedObjectImporter(
                    source, destination,
                )

            blob_at_max = git("hash-object", "-w", "--stdin", data=b"1234")
            blob_plus_one = git(
                "hash-object", "-w", "--stdin", data=b"12345",
            )
            another_blob = git("hash-object", "-w", "--stdin", data=b"x")

            with (
                mock.patch.object(version_collision, "MAX_IMPORTED_BYTES", 4),
                mock.patch.object(
                    version_collision, "IMPORT_CATEGORY_BYTE_LIMITS", {},
                ),
            ):
                bounded = importer("global-bytes")
                bounded.transfer(blob_at_max, "blob")
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError, "byte bound",
                ):
                    bounded.transfer(another_blob, "blob")

            with mock.patch.object(version_collision, "MAX_IMPORTED_OBJECTS", 1):
                bounded = importer("objects")
                bounded.transfer(blob_at_max, "blob")
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError, "closure.*bound",
                ):
                    bounded.transfer(another_blob, "blob")

            with mock.patch.object(version_collision, "MAX_BLOB_BYTES", 4):
                bounded = importer("blob-size")
                bounded.transfer(blob_at_max, "blob")
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "object exceeds the bound",
                ):
                    bounded.transfer(blob_plus_one, "blob")

            for index, category in enumerate((
                version_collision.CANDIDATE_VALIDATION_TREE_CLOSURE,
                version_collision.HISTORICAL_PREREQUISITE_TREES,
            )):
                with self.subTest(category=category), mock.patch.object(
                    version_collision,
                    "IMPORT_CATEGORY_BYTE_LIMITS",
                    {category: 4},
                ):
                    bounded = importer(f"class-{index}")
                    bounded.transfer(
                        blob_at_max, "blob", category=category,
                    )
                    with self.assertRaisesRegex(
                        version_collision.VersionCollisionError, "byte bound",
                    ):
                        bounded.transfer(
                            another_blob, "blob", category=category,
                        )

            empty = git("mktree", data=b"")
            tree_depth_one = git(
                "mktree", "-z",
                data=f"040000 tree {empty}\tleaf\0".encode(),
            )
            tree_depth_two = git(
                "mktree", "-z",
                data=f"040000 tree {tree_depth_one}\tmiddle\0".encode(),
            )
            with mock.patch.object(version_collision, "MAX_TREE_DEPTH", 1):
                importer("tree-depth-max").transfer(tree_depth_one, "tree")
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError, "closure.*bound",
                ):
                    importer("tree-depth-plus-one").transfer(
                        tree_depth_two, "tree",
                    )

            git("config", "user.name", "Collision Fixture")
            git("config", "user.email", "collision-fixture@secpal.test")

            def commit(message: str, *parents: str) -> str:
                arguments = ["commit-tree", empty, "-m", message]
                for parent in parents:
                    arguments.extend(("-p", parent))
                return git(*arguments)

            commit_zero = commit("depth zero")
            commit_one = commit("depth one", commit_zero)
            commit_two = commit("depth two", commit_one)
            with mock.patch.object(version_collision, "MAX_IMPORTED_COMMITS", 2):
                importer("commit-count-max").history(commit_one)
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "history count",
                ):
                    importer("commit-count-plus-one").history(commit_two)
            with mock.patch.object(version_collision, "MAX_COMMIT_DEPTH", 1):
                importer("commit-depth-max").history(commit_one)
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "history depth",
                ):
                    importer("commit-depth-plus-one").history(commit_two)

            second_parent = commit("second parent")
            third_parent = commit("third parent")
            fanout_at_max = commit(
                "fanout max", commit_zero, second_parent,
            )
            fanout_plus_one = commit(
                "fanout plus one", commit_zero, second_parent, third_parent,
            )
            with mock.patch.object(version_collision, "MAX_PARENT_FANOUT", 2):
                importer("fanout-max").history(fanout_at_max)
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError, "parent fanout",
                ):
                    importer("fanout-plus-one").history(fanout_plus_one)

    def test_collision_importer_enforces_depth_for_cached_tree_objects(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            source.mkdir()
            destination.mkdir()
            for root in (source, destination):
                subprocess.run(
                    ["git", "-C", str(root), "init", "--quiet"], check=True
                )

            leaf = subprocess.run(
                ["git", "-C", str(source), "mktree"],
                input=b"",
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.decode().strip()
            parent = subprocess.run(
                ["git", "-C", str(source), "mktree", "-z"],
                input=f"040000 tree {leaf}\tcached\0".encode(),
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.decode().strip()
            importer = version_collision._BoundedObjectImporter(
                source, destination
            )
            importer.transfer(leaf, "tree", import_blobs=False)
            with mock.patch.object(version_collision, "MAX_TREE_DEPTH", 0):
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError, "object closure"
                ):
                    importer.transfer(parent, "tree", import_blobs=False)

    def test_collision_owner_model_matches_maintained_ready_declarations(self) -> None:
        from scripts.secpal_pr_review import version_collision

        source = Path(fast_path.__file__).read_bytes()
        text = source.decode("utf-8", errors="strict")
        module = ast.parse(text)
        starts = [0]
        for line in source.splitlines(keepends=True):
            starts.append(starts[-1] + len(line))
        identities = [
            node
            for function in module.body
            if isinstance(function, ast.FunctionDef)
            and function.name in {
                "normalize_ready_integration_evidence",
                "create_ready_integration_attestation",
            }
            for node in ast.walk(function)
            if isinstance(node, ast.Constant) and node.value == "1.2"
        ]
        positions = sorted(
            starts[node.lineno - 1] + node.col_offset + 1 for node in identities
        )
        self.assertEqual(len(positions), 5)
        delta = {
            "changes": [{
                "path": version_collision.SOURCE_PATH,
                "replacement_offsets": [[position, position] for position in positions],
            }]
        }
        version_collision._verify_owner_renumber(source, "1.2", delta)

        partial = copy.deepcopy(delta)
        partial["changes"][0]["replacement_offsets"].pop()
        with self.assertRaisesRegex(
            version_collision.VersionCollisionError,
            "owning dispatch",
        ):
            version_collision._verify_owner_renumber(source, "1.2", partial)

        changed_operator = source.replace(
            b'    if schema_version == "1.2":\n'
            b'        normalized["reviewed_head_sha"] = reviewed_head\n',
            b'    if schema_version != "1.2":\n'
            b'        normalized["reviewed_head_sha"] = reviewed_head\n',
            1,
        )
        with self.assertRaisesRegex(
            version_collision.VersionCollisionError,
            "dispatch is incomplete",
        ):
            version_collision._verify_owner_renumber(
                changed_operator, "1.2", delta,
            )

    def test_collision_inventory_rejects_declaration_mutation(self) -> None:
        from scripts.secpal_pr_review import version_collision

        source = Path(fast_path.__file__).read_bytes()
        mutations = (
            b'\nREADY_INTEGRATION_V12_KEYS |= {"attacker"}\n',
            b'\nREADY_INTEGRATION_V12_KEYS.add("attacker")\n',
            b'\nREADY_INTEGRATION_V12_KEYS["attacker"] = "value"\n',
            b'\nglobals()["READY_INTEGRATION_V12_KEYS"] = frozenset()\n',
            b'\nimport os as READY_INTEGRATION_V12_KEYS\n',
            b'\ndef READY_INTEGRATION_V12_KEYS():\n    return frozenset()\n',
            b'\ndef shadow(READY_INTEGRATION_V12_KEYS):\n    return None\n',
            b'\nshadow = lambda READY_INTEGRATION_V12_KEYS: None\n',
            b'\nalias = READY_INTEGRATION_V12_KEYS\n',
            b'\nfrozenset = attacker_controlled\n',
            b'\nsetattr(module, "READY_INTEGRATION_V12_KEYS", attacker_controlled)\n',
            b'\nbuiltins.frozenset = attacker_controlled\n',
            b'\n__builtins__["frozenset"] = attacker_controlled\n',
            b'\nname = "READY_INTEGRATION_V12_KEYS"\nglobals()[name] = frozenset()\n',
            b'\nglobals().update({"READY_INTEGRATION_V12_KEYS": frozenset()})\n',
            b'\nnormalize_ready_integration_evidence = lambda value: value\n',
            b'\ndict.__setitem__(READY_INTEGRATION_KEYS_BY_VERSION, "9.9", frozenset())\n',
            b'\nmutate((READY_INTEGRATION_KEYS_BY_VERSION, "9.9"))\n',
            b'\nmodule.__dict__.update({"normalize_ready_integration_evidence": lambda value: value})\n',
            b'\nindirect = lambda: READY_INTEGRATION_KEYS_BY_VERSION\n',
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "declaration",
                ):
                    version_collision.inventory_from_source(source + mutation)

    def test_collision_python_token_parser_normalizes_recursion_failure(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with mock.patch.object(
            version_collision.ast, "parse", side_effect=RecursionError
        ):
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "Python version token source is malformed",
            ):
                version_collision._verify_python_version_tokens(
                    b"# 1.2\n", (2,), "1.2"
                )

    def test_collision_owner_accepts_the_maintained_v12_limit_gate(self) -> None:
        from scripts.secpal_pr_review import version_collision

        source = CollisionCompositionFixture.source(
            "1.2", "authenticated_resolution_delta"
        )
        successor, derived_positions = version_collision._derive_owner_renumber(
            source, "1.2", "1.3"
        )
        positions = version_collision.verify_blob_renumber(
            source, successor, "1.2", "1.3"
        )
        self.assertEqual(positions, derived_positions)
        self.assertEqual(len(positions), 4)
        delta = {
            "changes": [{
                "path": version_collision.SOURCE_PATH,
                "replacement_offsets": [list(pair) for pair in positions],
            }]
        }

        version_collision._verify_owner_renumber(source, "1.2", delta)

    def test_collision_issuer_verifies_exact_accepted_source_bytes(self) -> None:
        from scripts.secpal_pr_review import exact_source_safety, version_collision

        main = "a" * 40

        def git(_root, arguments, _maximum):
            if arguments == ["rev-parse", "HEAD"]:
                return (main + "\n").encode()
            if arguments == ["status", "--porcelain=v1", "--untracked-files=normal"]:
                return b""
            raise AssertionError(arguments)

        with mock.patch.object(version_collision, "_git", side_effect=git), mock.patch.object(
            exact_source_safety,
            "verify_source_bytes",
            side_effect=authority.LifecycleAuthorityError(
                "validation mutated immutable source bytes"
            ),
        ) as verify:
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "accepted-main source bytes",
            ):
                version_collision._require_accepted_issuer(main)
        verify.assert_called_once_with(Path(version_collision.__file__).resolve().parents[2], main)

    def test_collision_source_safety_detects_hidden_index_substitution(self) -> None:
        from scripts.secpal_pr_review import exact_source_safety

        for index_flag in (None, "--assume-unchanged", "--skip-worktree"):
            with self.subTest(index_flag=index_flag), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(
                    ["git", "-C", str(root), "init", "--quiet"], check=True
                )
                source = root / "source.py"
                source.write_text('authority = "accepted"\n', encoding="utf-8")
                subprocess.run(
                    ["git", "-C", str(root), "add", "source.py"], check=True
                )
                tree = subprocess.run(
                    ["git", "-C", str(root), "write-tree"],
                    stdout=subprocess.PIPE,
                    check=True,
                ).stdout.decode().strip()
                if index_flag is not None:
                    subprocess.run(
                        [
                            "git", "-C", str(root), "update-index",
                            index_flag, "source.py",
                        ],
                        check=True,
                    )
                source.write_text('authority = "substituted"\n', encoding="utf-8")

                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError,
                    "immutable source bytes",
                ):
                    exact_source_safety.verify_source_bytes(root, tree)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "--quiet"], check=True
            )
            source = root / "source.py"
            source.write_text('authority = "accepted"\n', encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "source.py"], check=True
            )
            tree = subprocess.run(
                ["git", "-C", str(root), "write-tree"],
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.decode().strip()
            source.unlink()
            source.symlink_to("missing-source.py")
            with self.assertRaisesRegex(
                authority.LifecycleAuthorityError,
                "symlink",
            ):
                exact_source_safety.verify_source_bytes(root, tree)

    def test_collision_public_entry_gates_current_before_source_acquisition(self) -> None:
        from scripts.secpal_pr_review import lifecycle_publication, version_collision

        order = []
        with mock.patch.object(
            version_collision,
            "_authenticate_installed_collision_issuer",
            side_effect=lambda: order.append("source") or "a" * 40,
            create=True,
        ) as source_authentication, mock.patch.object(
            lifecycle_publication,
            "verify_current_lifecycle_authority",
            side_effect=lambda *_args: (
                order.append("CURRENT"),
                (_ for _ in ()).throw(
                    lifecycle_publication.LifecyclePublicationError(
                        "CURRENT unavailable"
                    )
                ),
            )[1],
        ), mock.patch.object(
            version_collision,
            "_authenticated_source_checkout",
            side_effect=AssertionError("source acquisition preceded CURRENT"),
        ) as checkout:
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "CURRENT",
            ):
                version_collision.prepare_collision_tree(
                    repository=REPOSITORY,
                    delivery_issue=ISSUE,
                    pull_request=PR,
                    predecessor_head=HEAD,
                    resulting_tree="a" * 40,
                    repository_root=REPO_ROOT,
                )
        source_authentication.assert_called_once_with()
        checkout.assert_not_called()
        self.assertEqual(order, ["source", "CURRENT"])

    def test_collision_python_tests_reject_executable_version_dispatch(self) -> None:
        from scripts.secpal_pr_review import version_collision

        rejected = (
            b'if "1.2" == "1.3":\n    dangerous()\n',
            b'assert {"expected": "1.2"} == {"expected": "1.2"}\n',
            b'assertEqual("1.2", Trigger())\n',
            b'assertEqual(Trigger(), "1.2")\n',
            b'result = callable_value("1.2")\n',
            b'result = owner.value == "1.2"\n',
            b'result = "1.2" in attacker_controlled\n',
        )
        for source in rejected:
            with self.subTest(source=source):
                successor = source.replace(b"1.2", b"1.3")
                positions = version_collision.verify_blob_renumber(
                    source, successor, "1.2", "1.3",
                )
                with self.assertRaisesRegex(
                    version_collision.VersionCollisionError,
                    "test version token",
                ):
                    version_collision._verify_python_test_renumber(
                        source, successor, positions, "1.2", "1.3",
                    )

    def test_collision_python_tests_admit_only_provably_inert_expectations(self) -> None:
        from scripts.secpal_pr_review import version_collision

        admitted = (
            (
                b'# maintained expected schema: 1.2\nassert current\n',
                b'# maintained expected schema: 1.3\nassert current\n',
            ),
        )
        for predecessor, successor in admitted:
            with self.subTest(predecessor=predecessor):
                positions = version_collision.verify_blob_renumber(
                    predecessor, successor, "1.2", "1.3",
                )
                version_collision._verify_python_test_renumber(
                    predecessor, successor, positions, "1.2", "1.3",
                )

        predecessor = b'assert "1.2" == "1.3"\n'
        successor = b'assert "1.3" == "1.3"\n'
        with self.assertRaisesRegex(
            version_collision.VersionCollisionError,
            "test version token",
        ):
            version_collision._verify_python_test_renumber(
                predecessor,
                successor,
                version_collision.verify_blob_renumber(
                    predecessor, successor, "1.2", "1.3",
                ),
                "1.2",
                "1.3",
            )

    def test_collision_tree_enforces_the_registered_test_boundary(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*arguments: str, data: bytes | None = None) -> str:
                return subprocess.run(
                    ["git", "-C", str(root), *arguments],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                ).stdout.decode().strip()

            def test_tree(source: bytes, path: str = "test_collision.py") -> str:
                blob = git("hash-object", "-w", "--stdin", data=source)
                subtree = git(
                    "mktree", "-z",
                    data=f"100644 blob {blob}\t{path}\0".encode(),
                )
                return git(
                    "mktree", "-z",
                    data=f"040000 tree {subtree}\ttests\0".encode(),
                )

            git("init", "--quiet")
            for predecessor in (
                b'if "1.2" == "1.3":\n    dangerous()\n',
                b'assertEqual("1.2", Trigger())\n',
                b'assertEqual(Trigger(), "1.2")\n',
            ):
                with self.subTest(predecessor=predecessor):
                    with self.assertRaisesRegex(
                        version_collision.VersionCollisionError,
                        "test version token",
                    ):
                        version_collision.verify_tree_renumber(
                            root,
                            test_tree(predecessor),
                            test_tree(predecessor.replace(b"1.2", b"1.3")),
                            occupied_version="1.2",
                            free_version="1.3",
                            source_scope=frozenset({"tests/test_collision.py"}),
                            authorized_paths=("tests/test_collision.py",),
                        )

            assertion = b'assert {"expected": "1.2"} == {"expected": "1.2"}\n'
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "test version token",
            ):
                version_collision.verify_tree_renumber(
                    root,
                    test_tree(assertion),
                    test_tree(assertion.replace(b"1.2", b"1.3")),
                    occupied_version="1.2",
                    free_version="1.3",
                    source_scope=frozenset({"tests/test_collision.py"}),
                    authorized_paths=("tests/test_collision.py",),
                )

            comment = b'# maintained expected schema: 1.2\nassert current\n'
            evidence = version_collision.verify_tree_renumber(
                root,
                test_tree(comment),
                test_tree(comment.replace(b"1.2", b"1.3")),
                occupied_version="1.2",
                free_version="1.3",
                source_scope=frozenset({"tests/test_collision.py"}),
                authorized_paths=("tests/test_collision.py",),
            )
            self.assertEqual(evidence["changed_paths"], ["tests/test_collision.py"])

            shell = b'if [ "1.2" = "1.3" ]; then dangerous; fi\n'
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "provably inert profile",
            ):
                version_collision.verify_tree_renumber(
                    root,
                    test_tree(shell, "test_collision.sh"),
                    test_tree(shell.replace(b"1.2", b"1.3"), "test_collision.sh"),
                    occupied_version="1.2",
                    free_version="1.3",
                    source_scope=frozenset({"tests/test_collision.sh"}),
                    authorized_paths=("tests/test_collision.sh",),
                )

    def test_collision_python_rejects_interpolated_version_expressions(self) -> None:
        from scripts.secpal_pr_review import version_collision

        for source in (
            b"value = f'{1.2}'\n",
            b'value = f"{1.2:.2f}"\n',
            b'value = f"literal 1.2"\n',
            b'value = f"{\'1.2\'}"\n',
            '# coding: latin-1\nx = \'ééé\'; y = f"{\'1.2\'}"\n'.encode(),
        ):
            with self.subTest(source=source):
                offsets = tuple(pair[0] for pair in version_collision.verify_blob_renumber(
                    source, source.replace(b"1.2", b"1.3"), "1.2", "1.3",
                ))
                with self.assertRaisesRegex(version_collision.VersionCollisionError, "Python version token"):
                    version_collision._verify_python_version_tokens(source, offsets, "1.2")

    def test_collision_requires_complete_owner_version_identity_change(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            guard = b'    if schema_version == "1.2":\n        value["authenticated_resolution_delta"]\n'
            before = fixture.source("1.2", "authenticated_resolution_delta").replace(b"    return value\n", guard + b"    return value\n")
            partial = fixture.source("1.3", "authenticated_resolution_delta").replace(b"    return value\n", guard + b"    return value\n")
            predecessor = fixture.commit(fixture.tree(before), "candidate version-selected check", fixture.base)

            def derive(source):
                resulting = fixture.commit(fixture.tree(source), "renumber", predecessor)
                return version_collision._derive_collision_from_git(
                    fixture.root, repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
                    predecessor_head=predecessor, resulting_head=resulting, protected_main=fixture.main,
                )

            with self.assertRaisesRegex(version_collision.VersionCollisionError, "version identity"):
                derive(partial)
            complete = partial.replace(b'schema_version == "1.2"', b'schema_version == "1.3"')
            with self.assertRaisesRegex(
                version_collision.VersionCollisionError,
                "custom dispatch",
            ):
                derive(complete)
            before += b'other_domain = "1.2"\n'
            predecessor = fixture.commit(fixture.tree(before), "candidate with unrelated version", fixture.base)
            with self.assertRaisesRegex(version_collision.VersionCollisionError, "version identity"):
                derive(complete + b'other_domain = "1.3"\n')
            runtime = fixture.root / "helper.py"
            runtime.write_text('other_domain = "1.2"\n')
            fixture.git("add", "helper.py")
            predecessor = fixture.commit(fixture.tree(before), "candidate with another runtime source", fixture.base)
            runtime.write_text('other_domain = "1.3"\n')
            fixture.git("add", "helper.py")
            with self.assertRaisesRegex(version_collision.VersionCollisionError, "version identity"):
                derive(complete + b'other_domain = "1.2"\n')

    def test_collision_preserves_authenticated_corrected_predecessor_threads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory), historical_thread=True)
            with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=fixture.policy), mock.patch.object(
                orchestration.bootstrap_source_admission, "_read_protected_main_registry", side_effect=fixture.registry_reader,
            ):
                request = fixture.request()
                decision = orchestration._orchestrate_event(
                    REPOSITORY, ISSUE, request, current_reader=lambda *_args: fixture.observed,
                    feedback_reader=lambda *_args: fixture.current, collision_reader=fixture.collision_reader,
                )
                self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
                self.assertFalse(decision.resolution_eligible)
                self.assertEqual(fixture.current.feedback["threads"], fixture.reviewed.feedback["threads"])
                self.assertEqual(fixture.eligibility["eligible_threads"], [])
                changed = copy.deepcopy(request)
                changed["continuation_evidence"]["predecessor_safety_evidence"].pop("historical_thread_classifications")
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    orchestration._orchestrate_event(
                        REPOSITORY, ISSUE, changed, current_reader=lambda *_args: fixture.observed,
                        feedback_reader=lambda *_args: fixture.current, collision_reader=fixture.collision_reader,
                    )
                changed = copy.deepcopy(request)
                changed["continuation_evidence"]["successor_safety_evidence"]["historical_thread_classifications"] = copy.deepcopy(
                    fixture.predecessor_safety["historical_thread_classifications"]
                )
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    orchestration._orchestrate_event(
                        REPOSITORY, ISSUE, changed, current_reader=lambda *_args: fixture.observed,
                        feedback_reader=lambda *_args: fixture.current, collision_reader=fixture.collision_reader,
                    )

    def test_collision_preserves_authenticated_resolved_predecessor_threads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(
                Path(directory),
                historical_thread=True,
                historical_thread_resolved=True,
            )
            with mock.patch.object(
                authority,
                "_load_lifecycle_trust_policy",
                return_value=fixture.policy,
            ):
                scope, reviewed, _validation = orchestration._collision_scope(
                    fixture.evidence,
                    observed=fixture.observed,
                    resulting_head=fixture.resulting,
                    collision_reader=fixture.collision_reader,
                )
            self.assertEqual(
                scope["predecessor_safety_digest"],
                fast_path.digest_json(fixture.predecessor_safety),
            )
            self.assertTrue(reviewed.feedback["threads"][0]["is_resolved"])

    def test_collision_reuses_authenticated_local_registry_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            with mock.patch.object(
                authority,
                "_load_lifecycle_trust_policy",
                return_value=fixture.policy,
            ), mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_read_protected_main_registry",
                side_effect=AssertionError("network registry read is forbidden"),
            ) as network_registry:
                scope, _reviewed, _validation = orchestration._collision_scope(
                    fixture.evidence,
                    observed=fixture.observed,
                    resulting_head=fixture.resulting,
                    collision_reader=fixture.collision_reader,
                )
            self.assertEqual(scope["collision"]["protected_main"], fixture.main)
            network_registry.assert_not_called()

    def test_collision_rejects_predecessor_before_source_acquisition(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            evidence = copy.deepcopy(fixture.evidence)
            evidence["predecessor_safety_evidence"] = None
            with mock.patch.object(
                version_collision,
                "_authenticated_source_checkout",
                side_effect=AssertionError("source acquisition ran"),
            ) as acquisition:
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    orchestration._collision_scope(
                        evidence,
                        observed=fixture.observed,
                        resulting_head=fixture.resulting,
                        collision_reader=version_collision.authenticate_collision_source,
                    )
            acquisition.assert_not_called()

    def test_collision_import_ignores_caller_graph_and_checks_object_hashes(self) -> None:
        from scripts.secpal_pr_review import version_collision
        import hashlib
        import zlib

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "source").mkdir()
            fixture = CollisionCompositionFixture(Path(directory) / "source")
            destination = Path(directory) / "isolated"
            destination.mkdir()
            subprocess.run(["git", "clone", "--no-local", "--no-checkout", str(fixture.root), str(destination)],
                           check=True, capture_output=True)
            (fixture.root / ".git/info/grafts").write_text(fixture.resulting + "\n", encoding="ascii")
            version_collision._import_successor(fixture.root, destination, fixture.resulting, fixture.predecessor)
            topology = version_collision._git(destination, ["rev-list", "--parents", "-n", "1", fixture.resulting], 256)
            self.assertEqual(topology.decode().split(), [fixture.resulting, fixture.predecessor])
            known_source = fixture.git("rev-parse", fixture.predecessor + ":" + version_collision.SOURCE_PATH)
            known_text = fixture.git("rev-parse", fixture.predecessor + ":unrelated.txt")
            excessive = fixture.git("mktree", "-z", data=(
                f"100644 blob {known_source}\ta\0" + f"100644 blob {known_text}\tb\0"
            ).encode())
            with mock.patch.object(version_collision, "MAX_IMPORTED_OBJECTS", 2):
                with self.assertRaisesRegex(version_collision.VersionCollisionError, "object closure"):
                    version_collision._import_successor(
                        fixture.root, destination, None, fixture.predecessor, resulting_tree=excessive,
                    )
            original = version_collision._git(fixture.root, ["cat-file", "commit", fixture.resulting], 65536)
            forged = original + b"extra bytes\n"
            object_bytes = b"commit " + str(len(forged)).encode() + b"\0" + forged
            self.assertNotEqual(hashlib.sha1(object_bytes).hexdigest(), fixture.resulting)
            object_path = fixture.root / ".git/objects" / fixture.resulting[:2] / fixture.resulting[2:]
            object_path.chmod(0o600)
            object_path.write_bytes(zlib.compress(object_bytes))
            with self.assertRaisesRegex(version_collision.VersionCollisionError, "object hash"):
                version_collision._import_successor(fixture.root, destination, fixture.resulting, fixture.predecessor)

    def test_collision_real_signed_composition_reaches_existing_transition(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution, lifecycle_publication, version_collision

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=fixture.policy), mock.patch.object(
                orchestration.bootstrap_source_admission, "_read_protected_main_registry", side_effect=fixture.registry_reader,
            ):
                request = fixture.request()
                decision = orchestration._orchestrate_event(
                    REPOSITORY, ISSUE, request, current_reader=lambda *_args: fixture.observed,
                    feedback_reader=lambda *_args: fixture.current, collision_reader=fixture.collision_reader,
                )
                self.assertEqual(decision.lifecycle_transition, "EXCEPTIONAL_CONTINUATION")
                self.assertTrue(decision.preserve_ready)
                self.assertFalse(decision.resolution_eligible)
                self.assertEqual(decision.resulting_head_sha, fixture.resulting)
                self.assertEqual(decision.exceptional_continuations, 0)
                signed = authority.loads_closed_json(request["authorization"])
                self.assertNotIn("finding_ids", signed["scope"])
                self.assertNotIn("thread_ids", signed["scope"])
                self.assertEqual(signed["scope"]["collision"]["free_version"], "1.3")
                self.assertEqual(signed["scope"]["collision"]["delta"]["changed_paths"], ["scripts/secpal_pr_review/fast_path.py"])
                historical = copy.deepcopy(request)
                historical["continuation_evidence"] = {
                    "reviewed_state_evidence": fixture.reviewed.to_dict(),
                    "eligibility_evidence": fixture.eligibility,
                }
                with self.assertRaises(orchestration.LifecycleOrchestrationError) as rejected:
                    orchestration._orchestrate_event(
                        REPOSITORY, ISSUE, historical, current_reader=lambda *_args: fixture.observed,
                        feedback_reader=lambda *_args: fixture.current,
                    )
                self.assertIn("requires material corrected findings", str(rejected.exception.__cause__))
                original_git = version_collision._git
                git_arguments = []

                def bounded_local(root, arguments, maximum):
                    git_arguments.append(tuple(arguments))
                    if "fetch" in arguments:
                        raise AssertionError("collision source attempted network acquisition")
                    return original_git(root, arguments, maximum)

                with mock.patch.object(version_collision, "_git", side_effect=bounded_local), mock.patch.object(
                    version_collision, "_observe_main", return_value=fixture.main,
                ), mock.patch.object(version_collision, "_require_accepted_issuer"), mock.patch.object(
                    lifecycle_publication,
                    "verify_current_lifecycle_authority",
                    return_value=fixture.observed,
                ):
                    prepared = version_collision.prepare_collision_tree(
                        repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
                        predecessor_head=fixture.predecessor, resulting_tree=fixture.resulting_tree,
                        repository_root=fixture.root,
                    )
                    self.assertNotIn("resulting_head", prepared.to_dict())
                    self.assertEqual(fast_path.digest_json(prepared.to_dict()), fixture.document["collision_digest"])
                    isolated = orchestration._orchestrate_event(
                        REPOSITORY, ISSUE, request, current_reader=lambda *_args: fixture.observed,
                        feedback_reader=lambda *_args: fixture.current,
                    )
                    self.assertEqual(isolated, decision)
                    self.assertFalse(any("fetch" in arguments for arguments in git_arguments))
                    evidence = copy.deepcopy(fixture.evidence)
                    evidence["successor_safety_evidence"] = None
                    with mock.patch.object(lifecycle_publication, "verify_current_lifecycle_authority", return_value=fixture.observed), mock.patch.object(
                        orchestration, "_capture_current_stable_feedback", return_value=fixture.reviewed,
                    ), mock.patch.object(lifecycle_execution, "_read_live_github", return_value=lifecycle_execution.LivePullRequest(
                        REPOSITORY, PR, "OPEN", fixture.predecessor, False,
                    )), mock.patch.object(lifecycle_execution, "_policy_role_signer", return_value=(fixture.identity, fixture.sign)):
                        issued = orchestration.issue_collision_continuation_authorization(
                            repository=REPOSITORY, delivery_issue=ISSUE, authorization_id=fixture.document["authorization_id"],
                            reason="Exact independent version collision", resulting_head=fixture.resulting, evidence=evidence,
                        )
                        verified = orchestration._verify_user_authorization(issued, fixture.observed, fixture.lifecycle)
                        self.assertEqual(verified["scope"], signed["scope"])
                        self.assertEqual(verified["bounded_uses"], 1)
                        self.assertEqual(verified["schema_version"], "1.0")
                    with mock.patch.object(version_collision, "_observe_main", side_effect=[fixture.main, "f" * 40]):
                        with self.assertRaisesRegex(version_collision.VersionCollisionError, "drifted"):
                            version_collision.prepare_collision_tree(
                                repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
                                predecessor_head=fixture.predecessor, resulting_tree=fixture.resulting_tree, repository_root=fixture.root,
                            )

    def test_collision_historical_readback_authenticates_zero_thread_authority(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution, lifecycle_publication

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            policy_patch = mock.patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=fixture.policy,
            )
            policy_patch.start()
            self.addCleanup(policy_patch.stop)
            registry_patch = mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_read_protected_main_registry",
                side_effect=fixture.registry_reader,
            )
            registry_patch.start()
            self.addCleanup(registry_patch.stop)
            scope, _, validation = orchestration._collision_scope(
                fixture.evidence,
                observed=fixture.observed,
                resulting_head=fixture.resulting,
                collision_reader=fixture.collision_reader,
            )
            request = fixture.authorized_request(scope)
            signed_authorization = authority.loads_closed_json(request["authorization"])
            signers = lifecycle_execution.SigningAuthorities(
                fixture.identity,
                fixture.sign,
                fixture.identity,
                fixture.sign,
                fixture.identity,
                fixture.sign,
            )
            with mock.patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=fixture.policy,
            ):
                successor_raw = lifecycle_execution._append_successor_evidence(
                    fixture.observed,
                    signed_authorization,
                    signers,
                    resulting_head_sha=fixture.resulting,
                    current_head_evidence=validation,
                )
                parsed = authority.loads_closed_json(successor_raw)
                event = parsed["transition_authorizations"][-1]
                initialization = authority.loads_closed_json(
                    fixture.lifecycle_raw
                )["delivery_initialization"]
                successor_lifecycle = authority._verify_lifecycle_authority_for_journal(
                    successor_raw,
                    admitted_initialization=initialization,
                )
                successor_publication = SimpleNamespace(
                    publication_oid="e" * 40,
                    publication_digest="f" * 64,
                    lifecycle=successor_lifecycle,
                    serialized_lifecycle_evidence=successor_raw,
                )
                transition = lifecycle_publication.VerifiedLifecyclePublicationTransition(
                    predecessor=fixture.observed,
                    successor=successor_publication,
                    event_id=event["event_id"],
                    event_digest=event["event_digest"],
                    transition_kind=event["transition_kind"],
                    event_signer_identity=event["signer_identity"],
                    pull_request=event["pull_request"],
                    predecessor_authority_digest=event[
                        "predecessor_authority_digest"
                    ],
                    predecessor_head_sha=event["predecessor_head_sha"],
                    resulting_head_sha=event["resulting_head_sha"],
                    initialization_evidence_digest=event[
                        "initialization_evidence_digest"
                    ],
                )
                with mock.patch.object(
                    lifecycle_publication,
                    "_verify_historical_lifecycle_transition",
                    return_value=transition,
                ):
                    verified = orchestration.verify_collision_continuation_authority(
                        fixture.document,
                        orchestration_authorization=request["authorization"],
                        reviewed_state_evidence=fixture.reviewed.to_dict(),
                        eligibility_evidence=fixture.eligibility,
                        repository_root=fixture.root,
                        repository=REPOSITORY,
                        delivery_issue=ISSUE,
                        pull_request=PR,
                        resulting_head_sha=fixture.resulting,
                    )

            self.assertEqual(verified.finding_ids, ())
            self.assertEqual(verified.thread_ids, ())
            self.assertEqual(
                verified.continuation_digest,
                fast_path.digest_json(fixture.document),
            )

    def test_collision_candidate_local_issuer_cannot_fetch_authority(self) -> None:
        from scripts.secpal_pr_review import lifecycle_publication, version_collision

        with mock.patch.object(
            lifecycle_publication,
            "verify_current_lifecycle_authority",
            side_effect=current_reader(current_lifecycle(exceptional_recoveries=1)),
        ), mock.patch.object(version_collision, "_observe_main", return_value="f" * 40), mock.patch.object(
            version_collision, "_import_successor", side_effect=AssertionError("candidate reached source import"),
        ) as imported:
            with self.assertRaisesRegex(version_collision.VersionCollisionError, "accepted-main tooling"):
                version_collision.authenticate_collision_source(
                    repository=REPOSITORY, delivery_issue=ISSUE, pull_request=PR,
                    predecessor_head=HEAD, resulting_head=NEXT_HEAD, repository_root=REPO_ROOT,
                )
            imported.assert_not_called()

    def test_collision_publication_consumes_existing_signed_chain_once(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution, lifecycle_publication, version_collision

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            current = [fixture.observed]
            original = orchestration._orchestrate_event
            signers = lifecycle_execution.SigningAuthorities(
                fixture.identity, fixture.sign, fixture.identity, fixture.sign, fixture.identity, fixture.sign,
            )

            def execute(repository, issue, request, **kwargs):
                kwargs.update(current_reader=lambda *_args: current[0],
                              feedback_reader=lambda *_args: fixture.current, collision_reader=fixture.collision_reader)
                return original(repository, issue, request, **kwargs)

            def advance(raw, **kwargs):
                self.assertEqual(kwargs["signer_identity"], fixture.identity)
                initialization = authority.loads_closed_json(fixture.lifecycle_raw)["delivery_initialization"]
                verified = authority._verify_lifecycle_authority_for_journal(raw, admitted_initialization=initialization)
                self.assertEqual(verified.state["exceptional_continuation_count"], 1)
                for key, value in fixture.lifecycle.state.items():
                    if key not in {"exceptional_continuation_count", "exceptional_continuation_history"}:
                        self.assertEqual(verified.state[key], value)
                current[0] = SimpleNamespace(publication_oid="c" * 40, publication_digest="d" * 64,
                                             lifecycle=verified, serialized_lifecycle_evidence=raw)
                return current[0]

            with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=fixture.policy), mock.patch.object(
                orchestration.bootstrap_source_admission, "_read_protected_main_registry", side_effect=fixture.registry_reader,
            ), mock.patch.object(lifecycle_publication, "verify_current_lifecycle_authority", side_effect=lambda *_args: current[0]), mock.patch.object(
                orchestration, "_orchestrate_event", side_effect=execute,
            ), mock.patch.object(lifecycle_execution, "_production_signing_authorities", return_value=signers), mock.patch.object(
                lifecycle_execution, "_read_live_github", return_value=SimpleNamespace(
                    repository=REPOSITORY, pull_request=PR, head_sha=fixture.resulting, state="OPEN", draft=False),
            ), mock.patch.object(orchestration, "_capture_current_stable_feedback", return_value=fixture.current), mock.patch.object(
                version_collision, "_observe_main", return_value=fixture.main,
            ), mock.patch.object(lifecycle_publication, "advance_current_terminal", side_effect=advance) as publication_write:
                request = fixture.request()
                result = orchestration.publish_collision_continuation(REPOSITORY, ISSUE, request)
                self.assertEqual(result.lifecycle.head_sha, fixture.resulting)
                self.assertEqual(result.lifecycle.lifecycle_id, fixture.lifecycle.lifecycle_id)
                self.assertEqual(result.lifecycle.pull_request, PR)
                publication_write.assert_called_once()
                with self.assertRaises(orchestration.LifecycleOrchestrationError):
                    orchestration.publish_collision_continuation(REPOSITORY, ISSUE, request)
                publication_write.assert_called_once()

    def test_collision_publication_rechecks_main_after_final_feedback_capture(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution, lifecycle_publication, version_collision

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            original = orchestration._orchestrate_event
            feedback_captured = [False]

            def execute(repository, issue, request, **kwargs):
                kwargs.update(
                    current_reader=lambda *_args: fixture.observed,
                    feedback_reader=lambda *_args: fixture.current,
                    collision_reader=fixture.collision_reader,
                )
                return original(repository, issue, request, **kwargs)

            def capture(*_args):
                feedback_captured[0] = True
                return fixture.current

            def observe_main():
                return "f" * 40 if feedback_captured[0] else fixture.main

            with mock.patch.object(
                authority, "_load_lifecycle_trust_policy", return_value=fixture.policy,
            ), mock.patch.object(
                orchestration.bootstrap_source_admission,
                "_read_protected_main_registry",
                side_effect=fixture.registry_reader,
            ), mock.patch.object(
                lifecycle_publication,
                "verify_current_lifecycle_authority",
                return_value=fixture.observed,
            ), mock.patch.object(
                orchestration, "_orchestrate_event", side_effect=execute,
            ), mock.patch.object(
                lifecycle_execution,
                "_production_signing_authorities",
                return_value=lifecycle_execution.SigningAuthorities(
                    fixture.identity,
                    fixture.sign,
                    fixture.identity,
                    fixture.sign,
                    fixture.identity,
                    fixture.sign,
                ),
            ), mock.patch.object(
                lifecycle_execution,
                "_read_live_github",
                return_value=SimpleNamespace(
                    repository=REPOSITORY,
                    pull_request=PR,
                    head_sha=fixture.resulting,
                    state="OPEN",
                    draft=False,
                ),
            ), mock.patch.object(
                orchestration, "_capture_current_stable_feedback", side_effect=capture,
            ), mock.patch.object(
                version_collision, "_observe_main", side_effect=observe_main,
            ), mock.patch.object(
                lifecycle_publication,
                "advance_current_terminal",
                side_effect=AssertionError("stale protected main reached publication"),
            ) as publication_write:
                with self.assertRaisesRegex(
                    orchestration.LifecycleOrchestrationError,
                    "drifted",
                ):
                    orchestration.publish_collision_continuation(
                        REPOSITORY, ISSUE, fixture.request(),
                    )
                publication_write.assert_not_called()

    def test_collision_successor_provider_failures_cannot_publish(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution, lifecycle_publication

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            live = [fixture.current]
            original = orchestration._orchestrate_event

            def execute(repository, issue, request, **kwargs):
                kwargs.update(current_reader=lambda *_args: fixture.observed,
                              feedback_reader=lambda *_args: live[0], collision_reader=fixture.collision_reader)
                return original(repository, issue, request, **kwargs)

            with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=fixture.policy), mock.patch.object(
                orchestration.bootstrap_source_admission, "_read_protected_main_registry", side_effect=fixture.registry_reader,
            ), mock.patch.object(lifecycle_publication, "verify_current_lifecycle_authority", return_value=fixture.observed), mock.patch.object(
                orchestration, "_orchestrate_event", side_effect=execute,
            ), mock.patch.object(lifecycle_execution, "_append_successor_evidence", side_effect=AssertionError("unsafe provider reached signing")) as append, mock.patch.object(
                lifecycle_publication, "advance_current_terminal", side_effect=AssertionError("unsafe provider reached publication"),
            ) as publish:
                request = fixture.request()
                for label in ("missing", "nonterminal", "spoofed", "unclassified", "signed material", "signed unsafe"):
                    with self.subTest(label=label):
                        changed = copy.deepcopy(request)
                        safety = changed["continuation_evidence"]["successor_safety_evidence"]
                        feedback = copy.deepcopy(fixture.current.feedback)
                        if label == "missing":
                            changed["continuation_evidence"]["successor_safety_evidence"] = None
                        elif label == "nonterminal":
                            summary = safety["provider_transport"][0]
                            summary["body"] = summary["body"].replace("completed", "in_progress").replace("Completed", "In progress")
                            next(item for item in feedback["conversation_comments"] if item["node_id"] == "SUMMARY")["body_digest"] = fast_path.digest_text(summary["body"])
                        elif label == "spoofed":
                            next(item for item in feedback["conversation_comments"] if item["node_id"] == "SUMMARY")["actor"]["login"] = "spoofed-provider"
                        else:
                            feedback["conversation_comments"].append({
                                "node_id": "UNSAFE_SOURCE", "body_digest": "a" * 64,
                                "actor": {"login": "reviewer", "node_id": "REVIEWER", "database_id": 99},
                                "updated_at": None, "reactions": [],
                            })
                        live[0] = fast_path.StableFeedbackState(
                            repository=REPOSITORY, pull_request_number=PR, head_sha=fixture.resulting,
                            base_ref="main", base_sha=fixture.base, pr_state="OPEN", feedback=feedback,
                        )
                        if safety is not None:
                            safety["resulting_state_digest"] = live[0].state_digest
                        if label.startswith("signed"):
                            signer = orchestration._successor_classification_signer(REPOSITORY, safety["classification_signer"])
                            artifact = {
                                "schema_version": "1.2", "kind": "LATE_FEEDBACK_CLASSIFICATION",
                                "repository": REPOSITORY, "delivery_issue_number": ISSUE, "pull_request_number": PR,
                                "head_sha": fixture.resulting, "predecessor_state_digest": fixture.reviewed.state_digest,
                                "resulting_state_digest": live[0].state_digest,
                                "delivery_signer": {"format": "ssh", "fingerprint": signer.fingerprint},
                                "authorized_purpose": "AUTHENTICATE_CONTINUATION_SUCCESSOR_SAFETY",
                                "finding_id": "UNSAFE_SOURCE", "finding_evidence_digest": "b" * 64,
                                "thread": {"thread_id": None, "top_level_comment_node_id": None,
                                           "top_level_comment_database_id": None, "finding_body_digest": None,
                                           "reply_state_digest": fast_path.digest_json([]), "reply_count": 0,
                                           "is_resolved": None, "is_outdated": None,
                                           "classification": "INFORMATIONAL" if label == "signed material" else "VALID_ACTIONABLE",
                                           "disposition": "NON_ACTIONABLE" if label == "signed material" else "CORRECTED_AND_VERIFIED",
                                           "technically_blocking": label == "signed material",
                                           "technical_blockers": [sorted(late_disposition.TECHNICAL_BLOCKERS)[0]] if label == "signed material" else []},
                                "sources": [{"kind": "CONVERSATION_COMMENT", "node_id": "UNSAFE_SOURCE", "digest": "a" * 64, "thread_id": None}],
                            }
                            raw = late_disposition.canonical_json_bytes(artifact)
                            signature = fixture.sign(raw, late_disposition.CLASSIFICATION_SIGNATURE_NAMESPACE)["value"].encode()
                            safety["successor_findings"] = [{
                                "sources": [{"kind": "CONVERSATION_COMMENT", "node_id": "UNSAFE_SOURCE", "digest": "a" * 64}],
                                "classification_artifact": base64.b64encode(raw).decode(),
                                "classification_signature": base64.b64encode(signature).decode(),
                            }]
                        with self.assertRaises(orchestration.LifecycleOrchestrationError):
                            orchestration.publish_collision_continuation(REPOSITORY, ISSUE, changed)
                        append.assert_not_called()
                        publish.assert_not_called()

    def test_collision_fail_closed_matrix_never_reaches_publication(self) -> None:
        from scripts.secpal_pr_review import lifecycle_execution, lifecycle_publication, version_collision

        with tempfile.TemporaryDirectory() as directory:
            fixture = CollisionCompositionFixture(Path(directory))
            observed = [fixture.observed]
            live = [fixture.current]
            original = orchestration._orchestrate_event

            def execute(repository, issue, request, **kwargs):
                kwargs.update(current_reader=lambda *_args: observed[0],
                              feedback_reader=lambda *_args: live[0], collision_reader=fixture.collision_reader)
                return original(repository, issue, request, **kwargs)

            with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=fixture.policy), mock.patch.object(
                orchestration.bootstrap_source_admission, "_read_protected_main_registry", side_effect=fixture.registry_reader,
            ), mock.patch.object(lifecycle_publication, "verify_current_lifecycle_authority", side_effect=lambda *_args: observed[0]), mock.patch.object(
                orchestration, "_orchestrate_event", side_effect=execute,
            ), mock.patch.object(lifecycle_execution, "_append_successor_evidence", side_effect=AssertionError("negative reached successor signing")) as append, mock.patch.object(
                lifecycle_publication, "advance_current_terminal", side_effect=AssertionError("negative reached protected publication"),
            ) as publish:
                request = fixture.request()
                scope = authority.loads_closed_json(request["authorization"])["scope"]
                cases = []

                def add(label, value):
                    cases.append((label, value, fixture.observed))

                for field, value in (("pull_request", PR + 1), ("head_sha", fixture.predecessor),
                                     ("authorization", {}), ("replacement_pull_request", PR + 1)):
                    add(field, {**copy.deepcopy(request), field: value})
                for field, value in (("inventory", {}), ("free_version", "1.4"), ("occupied_version", "1.1"),
                                     ("successor_safety_evidence", None)):
                    changed = copy.deepcopy(request)
                    changed["continuation_evidence"][field] = value
                    add(field, changed)
                for field, value in (("trigger", "OTHER"), ("prior_ready_head_sha", "e" * 40),
                                     ("prior_ready_tree_sha", "e" * 40), ("collision_digest", "f" * 64),
                                     ("continuation_tree_sha", "e" * 40), ("finding_ids", ["FAKE"]),
                                     ("thread_ids", ["PRRT_FAKE"])):
                    changed = copy.deepcopy(request)
                    changed["continuation_evidence"]["continuation_document"][field] = value
                    add("document " + field, changed)
                for field, value in (("inventory_digest", "f" * 64), ("protected_main", fixture.base),
                                     ("protected_main_tree", fixture.resulting_tree), ("version_family", "OTHER"),
                                     ("occupied_version", "1.1"), ("free_version", "1.2"), ("free_version", "1.4"),
                                     ("delivery_scope", ["unrelated.py"]), ("resulting_head", "e" * 40),
                                     ("resulting_tree", "e" * 40), ("predecessor_tree", "e" * 40)):
                    changed_scope = copy.deepcopy(scope)
                    changed_scope["collision"][field] = value
                    add("signed collision " + field + " " + str(value), fixture.authorized_request(changed_scope))
                for field, value in (("changed_paths", ["unrelated.py"]), ("source_delta_digest", "e" * 64),
                                     ("changes", [])):
                    changed_scope = copy.deepcopy(scope)
                    changed_scope["collision"]["delta"][field] = value
                    add("signed delta " + field, fixture.authorized_request(changed_scope))
                for field, value in (("repository", "SecPal/other"), ("delivery_issue", ISSUE + 1),
                                     ("publication_oid", "f" * 40), ("publication_digest", "e" * 64),
                                     ("authorization_id", "another-authorization")):
                    add("signed outer " + field, fixture.authorized_request(copy.deepcopy(scope), **{field: value}))
                wrong_signer = "unauthorized@example.test"
                add("wrong signer", fixture.authorized_request(copy.deepcopy(scope), signer_identity=wrong_signer,
                    signer=lambda payload, domain: {**fixture.sign(payload, domain), "signer_identity": wrong_signer}))
                for field, value in (("ready", False), ("draft", True), ("unrestricted_review_count", 0),
                                     ("remediation_cycle_count", 1), ("exceptional_recovery_count", 0),
                                     ("exceptional_continuation_count", 1), ("cycle_3_absent", False)):
                    current = copy.deepcopy(fixture.observed)
                    current.lifecycle.state[field] = value
                    cases.append(("lifecycle " + field, copy.deepcopy(request), current))
                for field, value in (("lifecycle_id", "another-lifecycle"), ("authority_digest", "b" * 64),
                                     ("head_sha", "f" * 40)):
                    current = copy.deepcopy(fixture.observed)
                    current.lifecycle = replace(current.lifecycle, **{field: value})
                    cases.append(("CURRENT " + field, copy.deepcopy(request), current))
                for field, value in (("provider_transport", []), ("successor_findings", [{"sources": [], "classification_artifact": "e30=", "classification_signature": "eA=="}])):
                    changed = copy.deepcopy(request)
                    changed["continuation_evidence"]["successor_safety_evidence"][field] = value
                    add("successor " + field, changed)
                for field in ("predecessor_safety_evidence", "successor_safety_evidence"):
                    changed = copy.deepcopy(request)
                    changed["continuation_evidence"][field]["resulting_head_sha"] = "f" * 40
                    add("cross-head " + field, changed)
                for field, value in (("successful_result", False), ("head_sha", fixture.predecessor),
                                     ("validated_tree_sha", fixture.predecessor_tree),
                                     ("exceptional_continuation_evidence_digest", "f" * 64)):
                    changed = copy.deepcopy(request)
                    changed["continuation_evidence"]["validation_attestation"][field] = value
                    add("attestation " + field, changed)
                for label, source in (
                    ("whitespace", fixture.source("1.3", "authenticated_resolution_delta") + b" "),
                    ("comment wording", fixture.source("1.3", "authenticated_resolution_delta") + b"\n# changed comment\n"),
                    ("test logic", fixture.source("1.3", "authenticated_resolution_delta") + b"\nassert False\n"),
                    ("implementation logic", fixture.source("1.3", "authenticated_resolution_delta").replace(b"return value", b"return None")),
                    ("non-UTF8", fixture.source("1.3", "authenticated_resolution_delta") + b"\xff"),
                    ("oversized", fixture.source("1.3", "authenticated_resolution_delta") + b" " * version_collision.MAX_BLOB_BYTES),
                    ("retained occupied", fixture.predecessor_source),
                    ("skip lowest", fixture.source("1.4", "authenticated_resolution_delta")),
                ):
                    head = fixture.commit(fixture.tree(source), label, fixture.predecessor)
                    add(label, {**copy.deepcopy(request), "head_sha": head})
                for label, parents in (("multi-parent", (fixture.predecessor, fixture.base)), ("wrong parent", (fixture.base,))):
                    head = fixture.commit(fixture.resulting_tree, label, *parents)
                    add(label, {**copy.deepcopy(request), "head_sha": head})
                blob = fixture.git("hash-object", "-w", "--stdin", data=b'"1.3"\n')
                for label in ("addition", "deletion", "rename", "mode change", "object type", "outside delivery scope"):
                    fixture.git("read-tree", fixture.resulting_tree)
                    if label in {"deletion", "rename"}:
                        fixture.git("update-index", "--force-remove", version_collision.SOURCE_PATH)
                    if label in {"addition", "rename", "outside delivery scope"}:
                        path = "unrelated.txt" if label == "outside delivery scope" else "new.txt"
                        fixture.git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + path)
                    if label in {"mode change", "object type"}:
                        mode = "100755" if label == "mode change" else "120000"
                        source_blob = fixture.git("rev-parse", fixture.resulting_tree + ":" + version_collision.SOURCE_PATH)
                        fixture.git("update-index", "--cacheinfo", mode + "," + source_blob + "," + version_collision.SOURCE_PATH)
                    head = fixture.commit(fixture.git("write-tree"), label, fixture.predecessor)
                    add(label, {**copy.deepcopy(request), "head_sha": head})
                for label, changed, current in cases:
                    with self.subTest(label=label):
                        append.reset_mock()
                        publish.reset_mock()
                        observed[0] = current
                        with self.assertRaises((orchestration.LifecycleOrchestrationError, authority.LifecycleAuthorityError)):
                            orchestration.publish_collision_continuation(REPOSITORY, ISSUE, changed)
                        append.assert_not_called()
                        publish.assert_not_called()
                self.assertGreaterEqual(len(cases), 50)

    def test_historical_continuation_rejects_clean_feedback_without_collision_authority(self) -> None:
        request, authorization = continuation_inputs()
        reviewed = fast_path.verify_reviewed_state_evidence(
            request["continuation_evidence"]["reviewed_state_evidence"]
        )
        clean = fast_path.StableFeedbackState(
            repository=reviewed.repository,
            pull_request_number=reviewed.pull_request_number,
            head_sha=reviewed.head_sha,
            base_ref=reviewed.base_ref,
            base_sha=reviewed.base_sha,
            pr_state=reviewed.pr_state,
            feedback={**copy.deepcopy(reviewed.feedback), "threads": []},
        )
        eligibility = request["continuation_evidence"]["eligibility_evidence"]
        eligibility["reviewed_state_digest"] = clean.state_digest
        eligibility["eligible_threads"] = []
        request["continuation_evidence"]["reviewed_state_evidence"] = clean.to_dict()
        authorization["scope"].update(
            reviewed_state_digest=clean.state_digest,
            reviewed_feedback_digest=clean.feedback_digest,
            eligibility_evidence_digest=fast_path.digest_json(eligibility),
            finding_ids=[],
            thread_ids=[],
        )
        with self.assertRaises(orchestration.LifecycleOrchestrationError) as caught:
            orchestration._orchestrate_event(
                REPOSITORY,
                ISSUE,
                request,
                current_reader=current_reader(current_lifecycle(exceptional_recoveries=1)),
                feedback_reader=lambda _repository, _pull_request: feedback_successor(clean),
                authorization_verifier=fixture_authorization_verifier,
            )
        self.assertIn("requires material corrected findings", str(caught.exception.__cause__))

    def test_mechanical_renumber_preserves_every_other_byte(self) -> None:
        from scripts.secpal_pr_review import version_collision

        before = b'old = "1.2"\nunchanged = "1.2"\n'
        after = b'old = "1.3"\nunchanged = "1.2"\n'
        positions = version_collision.verify_blob_renumber(before, after, "1.2", "1.3")
        self.assertEqual(positions, ((7, 7),))
        self.assertEqual(
            version_collision.verify_blob_renumber(b'"1.9" "1.9"', b'"1.10" "1.10"', "1.9", "1.10"),
            ((1, 1), (7, 8)),
        )

    def test_version_inventory_reads_accepted_source_without_execution(self) -> None:
        from scripts.secpal_pr_review import version_collision

        source = b'''READY_INTEGRATION_KIND = "TWO_PARENT_READY_INTEGRATION"
READY_INTEGRATION_KEYS = frozenset({"kind", "schema_version"})
READY_INTEGRATION_V12_KEYS = READY_INTEGRATION_KEYS | {"reviewed_head_sha"}
def normalize_ready_integration_evidence(value):
    schema_version = value.get("schema_version")
    expected_keys = READY_INTEGRATION_V12_KEYS if schema_version == "1.2" else READY_INTEGRATION_KEYS
    if schema_version not in {"1.1", "1.2"} or set(value) != expected_keys:
        raise ValueError("invalid")
    return value
def create_ready_integration_attestation(normalized, eligibility_bound):
    fields = {"schema_version": "1.2" if eligibility_bound else "1.1",
              "kind": "ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION" if eligibility_bound else "READY_INTEGRATION_VALIDATION_ATTESTATION"}
    return fields
'''
        inventory = version_collision.inventory_from_source(source)
        self.assertEqual(inventory["kind"], "TWO_PARENT_READY_INTEGRATION")
        self.assertEqual(list(inventory["versions"]), ["1.1", "1.2"])
        self.assertIn("reviewed_head_sha", inventory["versions"]["1.2"]["fields"])
        self.assertNotIn("reviewed_head_sha", inventory["versions"]["1.1"]["fields"])
        for version in inventory["versions"].values():
            self.assertEqual([item["version"] for item in version["attestations"]], ["1.1", "1.2"])
        self.assertEqual(
            inventory,
            version_collision.inventory_from_source(source + b'\nraise RuntimeError("must not execute")\n'),
        )
        for changed in (
            source.replace(b'READY_INTEGRATION_KIND = "TWO_PARENT_READY_INTEGRATION"',
                           b'READY_INTEGRATION_KIND = "OTHER"'),
            source + b'\nREADY_INTEGRATION_V12_KEYS = frozenset()\n',
            source.replace(b'READY_INTEGRATION_V12_KEYS = READY_INTEGRATION_KEYS | {"reviewed_head_sha"}',
                           b'READY_INTEGRATION_V12_KEYS = malicious()'),
            b'\xff',
        ):
            with self.assertRaises(version_collision.VersionCollisionError):
                version_collision.inventory_from_source(changed)
        live = version_collision.inventory_from_source(Path(fast_path.__file__).read_bytes())
        self.assertEqual(live["kind"], version_collision.FAMILY_KIND)
        self.assertLessEqual({"1.1", "1.2"}, set(live["versions"]))
        for version in ("1.1", "1.2"):
            self.assertEqual(live["versions"][version]["attestations"], inventory["versions"][version]["attestations"])

    def test_collision_derivation_rejects_same_semantics_and_preserves_mappings(self) -> None:
        from scripts.secpal_pr_review import version_collision

        ordinary = {"fields": ["kind", "schema_version"], "attestations": [
            {"eligibility_bound": False, "version": "1.1", "kind": "ordinary"},
            {"eligibility_bound": True, "version": "1.2", "kind": "bound"},
        ]}
        existing = {"kind": version_collision.FAMILY_KIND,
                    "versions": {"1.1": ordinary}, "implementation_digest": "a" * 64}
        accepted = copy.deepcopy(existing)
        accepted["versions"]["1.2"] = {**ordinary, "fields": ["kind", "schema_version", "reviewed_head"]}
        candidate = copy.deepcopy(existing)
        candidate["versions"]["1.2"] = {**ordinary, "fields": ["kind", "schema_version", "resolution"]}
        successor = copy.deepcopy(existing)
        successor["versions"]["1.3"] = candidate["versions"]["1.2"]
        proof = version_collision.derive_collision(existing, accepted, candidate, successor)
        self.assertEqual(proof["occupied_version"], "1.2")
        self.assertEqual(proof["free_version"], "1.3")
        for label, base, main, prior, resulting in (
            ("absent", existing, existing, candidate, successor),
            ("same", existing, candidate, candidate, successor),
            ("not introduced", candidate, accepted, candidate, successor),
            ("wrong family", existing, {**accepted, "kind": "OTHER"}, candidate, successor),
            ("not lowest", existing, accepted, candidate, {**successor, "versions": {"1.1": ordinary, "1.4": candidate["versions"]["1.2"]}}),
            ("wrong mapping", existing, accepted, candidate, {**successor, "versions": {"1.1": ordinary, "1.3": ordinary}}),
        ):
            with self.subTest(label=label):
                with self.assertRaises(version_collision.VersionCollisionError):
                    version_collision.derive_collision(base, main, prior, resulting)

    def test_collision_clean_feedback_gate_requires_complete_terminal_transport(self) -> None:
        _, current, safety = authenticated_provider_growth()
        provider_logins = {"chatgpt-codex-connector", "github-code-quality"}
        transport_keys = {(item["kind"], item["node_id"]) for item in safety["provider_transport"]}
        feedback = copy.deepcopy(current.feedback)
        feedback["threads"] = []
        feedback["reviews"] = [item for item in feedback["reviews"]
                               if item["actor"]["login"] in provider_logins]
        feedback["conversation_comments"] = [item for item in feedback["conversation_comments"]
                                             if ("CONVERSATION_COMMENT", item["node_id"]) in transport_keys]
        clean = fast_path.StableFeedbackState(
            repository=current.repository, pull_request_number=current.pull_request_number,
            head_sha=current.head_sha, base_ref=current.base_ref, base_sha=current.base_sha,
            pr_state=current.pr_state, feedback=feedback,
        )
        proof = {**copy.deepcopy(safety), "predecessor_state_digest": clean.state_digest,
                 "resulting_state_digest": clean.state_digest, "successor_findings": []}
        fast_path.verify_clean_feedback_gate(clean, proof)
        for changed in (
            {**proof, "provider_transport": []},
            {**proof, "resulting_head_sha": HEAD},
            {**proof, "provider_transport": proof["provider_transport"][1:]},
            {**proof, "successor_findings": [{"sources": [], "classification_evidence": {}}]},
        ):
            with self.assertRaises(fast_path.SecurityBlocker):
                fast_path.verify_clean_feedback_gate(clean, changed)
        secret = copy.deepcopy(proof)
        secret["provider_transport"][0]["body"] += "\nAuthorization: Bearer fixture-secret"
        with self.assertRaisesRegex(fast_path.SecurityBlocker, "secret-like"):
            fast_path.verify_clean_feedback_gate(clean, secret)

    def test_collision_continuation_version_binds_receipt_without_thread_authority(self) -> None:
        request, _ = continuation_inputs()
        reviewed = fast_path.verify_reviewed_state_evidence(request["continuation_evidence"]["reviewed_state_evidence"])
        eligibility = request["continuation_evidence"]["eligibility_evidence"]
        eligibility["eligible_threads"] = []
        state = current_lifecycle(exceptional_recoveries=1).state
        document = {
            "schema_version": "1.1", "kind": "READY_EXCEPTIONAL_CONTINUATION",
            "trigger": "IMMUTABLE_EVIDENCE_VERSION_COLLISION", "collision_digest": "a" * 64,
            "authorization_id": "collision-authorization", "repository": REPOSITORY,
            "delivery_issue_number": ISSUE, "pull_request_number": PR,
            "prior_ready_head_sha": HEAD, "prior_ready_tree_sha": "c" * 40,
            "continuation_tree_sha": "d" * 40, "reviewed_state_digest": reviewed.state_digest,
            "reviewed_feedback_digest": reviewed.feedback_digest,
            "eligibility_evidence_digest": fast_path.digest_json(eligibility),
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": "aroviqen@secpal.app"},
            "lifecycle": {
                "unrestricted_reviews": 1, "remediation_cycles": 2, "cycle_3": False,
                "draft": False, "ready": True, "ready_transition_count": 1,
                "ready_history": state["ready_history"], "exceptional_recovery_count": 1,
                "exceptional_recovery_history": state["exceptional_recovery_history"],
                "exceptional_continuation_predecessor_count": 0,
                "exceptional_continuation_successor_count": 1,
            },
        }
        self.assertEqual(document, fast_path.normalize_exceptional_continuation_evidence(
            document, repository=REPOSITORY, reviewed_state=reviewed,
            validated_tree_sha="d" * 40, eligibility_evidence=eligibility,
        ))
        for changed in (
            {**document, "schema_version": "1.0"}, {**document, "finding_ids": []},
            {**document, "thread_ids": []}, {**document, "trigger": "MATERIAL_FEEDBACK"},
            {**document, "collision_digest": "not-a-digest"},
        ):
            with self.assertRaises(fast_path.SecurityBlocker):
                fast_path.normalize_exceptional_continuation_evidence(
                    changed, repository=REPOSITORY, reviewed_state=reviewed,
                    validated_tree_sha="d" * 40, eligibility_evidence=eligibility,
                )

    def test_collision_orchestration_requires_closed_authenticated_composition(self) -> None:
        request, _ = continuation_inputs()
        request["continuation_evidence"] = {
            "schema_version": "1.1", "trigger": "IMMUTABLE_EVIDENCE_VERSION_COLLISION",
        }
        with self.assertRaisesRegex(orchestration.LifecycleOrchestrationError, "collision continuation evidence"):
            orchestration._orchestrate_event(
                REPOSITORY, ISSUE, request,
                current_reader=current_reader(current_lifecycle(exceptional_recoveries=1)),
                authorization_verifier=fixture_authorization_verifier,
            )

    def test_mechanical_renumber_rejects_unrelated_edits_and_invalid_tokens(self) -> None:
        from scripts.secpal_pr_review import version_collision

        cases = [
            (b'"1.2"', b'"1.3" ', "1.2", "1.3"),
            (b'"1.2"\n', b'"1.3"\r\n', "1.2", "1.3"),
            (b'"1.2" # before', b'"1.3" # after', "1.2", "1.3"),
            (b'"1.2"; assert True', b'"1.3"; assert False', "1.2", "1.3"),
            (b'"1.2"; allow=False', b'"1.3"; allow=True', "1.2", "1.3"),
            (b'"11.2"', b'"11.3"', "1.2", "1.3"),
            (b'"1.20"', b'"1.30"', "1.2", "1.3"),
            (b'"1.2.0"', b'"1.3.0"', "1.2", "1.3"),
            (b'"1.2"\xff', b'"1.3"\xff', "1.2", "1.3"),
            (b'"1.2"\x00', b'"1.3"\x00', "1.2", "1.3"),
            (b'"1.2"', b'"1.2"', "1.2", "1.3"),
            (b'"1.3"', b'"1.2"', "1.3", "1.2"),
            (b'"1.2"', b'"2.0"', "1.2", "2.0"),
            (b'"01.2"', b'"1.3"', "01.2", "1.3"),
        ]
        for before, after, occupied, free in cases:
            with self.subTest(before=before, after=after):
                with self.assertRaises(version_collision.VersionCollisionError):
                    version_collision.verify_blob_renumber(before, after, occupied, free)

    def test_mechanical_renumber_enforces_bounds(self) -> None:
        from scripts.secpal_pr_review import version_collision

        for before, after in (
            (b'"1.2" ' * (version_collision.MAX_REPLACEMENTS + 1),
             b'"1.3" ' * (version_collision.MAX_REPLACEMENTS + 1)),
            (b'"1.2"' + b' ' * version_collision.MAX_BLOB_BYTES,
             b'"1.3"' + b' ' * version_collision.MAX_BLOB_BYTES),
        ):
            with self.assertRaises(version_collision.VersionCollisionError):
                version_collision.verify_blob_renumber(before, after, "1.2", "1.3")

    def test_mechanical_tree_delta_uses_actual_git_objects_and_exact_scope(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*arguments: str, data: bytes | None = None) -> bytes:
                return subprocess.run(
                    ["git", "-C", str(root), *arguments], input=data,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                ).stdout.strip()

            git("init", "--quiet")
            old_blob = git("hash-object", "-w", "--stdin", data=b'"1.2"\n').decode()
            new_blob = git("hash-object", "-w", "--stdin", data=b'"1.3"\n').decode()

            def tree(records: list[tuple[str, str, str]]) -> str:
                data = b"".join(
                    f"{mode} blob {blob}\t{path}\0".encode()
                    for mode, blob, path in records
                )
                return git("mktree", "-z", data=data).decode()

            predecessor = tree([("100644", old_blob, "schema.py")])
            successor = tree([("100644", new_blob, "schema.py")])
            evidence = version_collision.verify_tree_renumber(
                root, predecessor, successor, occupied_version="1.2",
                free_version="1.3", source_scope=frozenset({"schema.py"}),
                authorized_paths=("schema.py",),
            )
            self.assertEqual(evidence["changed_paths"], ["schema.py"])
            self.assertEqual(evidence["changes"][0]["predecessor_blob"], old_blob)
            self.assertEqual(evidence["changes"][0]["resulting_blob"], new_blob)
            old_numeric = git("hash-object", "-w", "--stdin", data=b'version = "1.2"\nthreshold = 1.2\n').decode()
            new_numeric = git("hash-object", "-w", "--stdin", data=b'version = "1.3"\nthreshold = 1.3\n').decode()
            with self.assertRaisesRegex(version_collision.VersionCollisionError, "Python version token"):
                version_collision.verify_tree_renumber(
                    root, tree([("100644", old_numeric, "schema.py")]), tree([("100644", new_numeric, "schema.py")]),
                    occupied_version="1.2", free_version="1.3", source_scope=frozenset({"schema.py"}), authorized_paths=("schema.py",),
                )
            self.assertEqual(
                evidence["source_delta_digest"],
                fast_path.digest_json({
                    key: value for key, value in evidence.items()
                    if key != "source_delta_digest"
                }),
            )
            for resulting_tree, scope, paths in (
                (successor, frozenset(), ("schema.py",)),
                (successor, frozenset({"schema.py"}), ()),
                (successor, frozenset({"schema.py"}), ("other.py",)),
                (successor, frozenset({"schema.py"}), ("schema.py", "schema.py")),
                (tree([]), frozenset({"schema.py"}), ("schema.py",)),
                (tree([("100644", new_blob, "other.py")]),
                 frozenset({"schema.py", "other.py"}), ("other.py", "schema.py")),
                (tree([("100755", new_blob, "schema.py")]),
                 frozenset({"schema.py"}), ("schema.py",)),
                (tree([("120000", new_blob, "schema.py")]),
                 frozenset({"schema.py"}), ("schema.py",)),
                (tree([("100644", new_blob, "schema.py"), ("100644", new_blob, "extra.py")]),
                 frozenset({"schema.py", "extra.py"}), ("extra.py", "schema.py")),
            ):
                with self.subTest(resulting_tree=resulting_tree, paths=paths, scope=scope):
                    with self.assertRaises(version_collision.VersionCollisionError):
                        version_collision.verify_tree_renumber(
                            root, predecessor, resulting_tree, occupied_version="1.2",
                            free_version="1.3", source_scope=scope, authorized_paths=paths,
                        )

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

        def non_utf8_predecessor_body(_current, evidence):
            _review, transport = predecessor_review(_current, evidence)
            transport["body"] = "\ud800"

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

        def malformed_predecessor_source_identity(_current, evidence):
            evidence["predecessor_provider_feedback"]["material_findings"][0][
                "sources"
            ][0]["node_id"] = []

        def extra_material_predecessor_finding(current, evidence):
            thread_id = "PRRT_EXTRA_PREDECESSOR"
            comment_id = "PRRC_EXTRA_PREDECESSOR"
            body_digest = fast_path.digest_text("extra predecessor defect")
            current.feedback["threads"].append(
                {
                    "node_id": thread_id,
                    "is_resolved": False,
                    "is_outdated": False,
                    "comments": [
                        {
                            "node_id": comment_id,
                            "body_digest": body_digest,
                            "actor": {
                                "login": "copilot-pull-request-reviewer",
                                "node_id": "BOT_kgDOCnlnWA",
                                "database_id": 175728472,
                            },
                            "reply_to_id": None,
                            "reactions": [],
                        }
                    ],
                }
            )
            evidence["predecessor_provider_feedback"]["material_findings"].append(
                {
                    "correction_finding_id": "UNAUTHENTICATED_CORRECTION",
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
                "correction_finding_id"
            ] = "UNAUTHENTICATED_CORRECTION"

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
            ("non-UTF-8 predecessor provider body", non_utf8_predecessor_body),
            ("missing predecessor provider object", missing_predecessor_review),
            (
                "predecessor feedback older than anchor",
                predecessor_feedback_older_than_anchor,
            ),
            ("extra predecessor provider object", extra_predecessor_review),
            ("omitted material predecessor thread", omitted_predecessor_finding),
            (
                "malformed predecessor source identity",
                malformed_predecessor_source_identity,
            ),
            (
                "extra material predecessor finding",
                extra_material_predecessor_finding,
            ),
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
