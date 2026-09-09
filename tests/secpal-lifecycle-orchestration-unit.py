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
import tempfile
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
from scripts.secpal_pr_review import late_disposition

REPOSITORY = "SecPal/.github"
ISSUE = 692
PR = 800
REPLACEMENT_PR = 801
HEAD = "a" * 40
NEXT_HEAD = "b" * 40
LIFECYCLE = "lifecycle:" + "c" * 64


def current_lifecycle(
    *,
    ready: bool = True,
    ready_regressed: bool = False,
    exceptional_recoveries: int = 0,
    exceptional_continuations: int = 0,
    head_sha: str = HEAD,
    remediation_cycles: int = 2,
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
        delivery_issue=ISSUE,
        lifecycle_id=LIFECYCLE,
        initialization_evidence_digest="f" * 64,
        pull_request=PR,
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


def authenticated_provider_growth() -> tuple[
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
        pull_request_number=PR,
        head_sha=HEAD,
        base_ref="main",
        base_sha="0" * 40,
        pr_state="OPEN",
        feedback={
            "pull_request_reactions": [],
            "reviews": [
                {
                    "node_id": "PRR_PREDECESSOR",
                    "body_digest": "1" * 64,
                    "actor": reviewer,
                    "state": "COMMENTED",
                    "commit_oid": HEAD,
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
        f'{{"headSha":"{NEXT_HEAD}","status":"completed"}} -->\n'
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
            f"**Reviewed commit:** `{NEXT_HEAD[:10]}`"
        ),
        "IC_SECURITY_RESULT": (
            "### 🛡️ Codex Security Review\n\n"
            "No security issues were found in this pull request.\n\n"
            f"**Reviewed commit:** `{NEXT_HEAD[:10]}`"
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
            "commit_oid": NEXT_HEAD,
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
        pull_request_number=PR,
        head_sha=NEXT_HEAD,
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
    )
    evidence: dict[str, object] = {
        "schema_version": "1.0",
        "repository": REPOSITORY,
        "pull_request_number": PR,
        "predecessor_state_digest": predecessor.state_digest,
        "resulting_head_sha": NEXT_HEAD,
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
    def __init__(self, root: Path, *, historical_thread: bool = False):
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
        self.command = {"argv": ["python3", "-c", "import ast,pathlib; ast.parse(pathlib.Path('scripts/secpal_pr_review/fast_path.py').read_text())"],
                        "working_directory": ".", "purpose": "Hermetic complete validation"}
        entry.update(focused_validation=[], required_local_validation=[self.command], manual_gates=[])
        self.registry_document = {"repositories": [entry]}
        registry_path = root / ".agents/skills/secpal-pr-review/references/repositories.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_bytes(authority.canonical_json_bytes(self.registry_document))
        self.git("add", str(registry_path.relative_to(root)))
        (root / "unrelated.txt").write_text('"1.2"\n')
        self.git("add", "unrelated.txt")
        self.registry = fast_path.validation_registry_projection(entry)
        self.base = self.commit(self.tree(self.source(None, None)), "base")
        self.predecessor_source = self.source("1.2", "authenticated_resolution_delta")
        self.predecessor_tree = self.tree(self.predecessor_source)
        self.predecessor = self.commit(self.predecessor_tree, "predecessor", self.base)
        self.main = self.commit(self.tree(self.source("1.2", "reviewed_head_sha")), "accepted main", self.base)
        self.resulting_tree = self.tree(self.source("1.3", "authenticated_resolution_delta"))
        self.git("update-ref", "HEAD", self.predecessor)
        self.lifecycle, self.lifecycle_raw = self.native_lifecycle()
        self.observed = current_reader(self.lifecycle)(REPOSITORY, ISSUE)
        self.observed.serialized_lifecycle_evidence = self.lifecycle_raw
        self.reviewed, self.predecessor_safety = self.feedback(self.predecessor, "PRE")
        if historical_thread:
            self.add_historical_thread()
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
        declaration = "{\n" + "".join(f"    {key!r}: frozenset({{{', '.join(repr(item) for item in sorted(value))}}}),\n" for key, value in fields.items()) + "}"
        return (f'READY_INTEGRATION_KIND = "TWO_PARENT_READY_INTEGRATION"\n'
                f"READY_INTEGRATION_KEYS_BY_VERSION = {declaration}\n"
                f"READY_INTEGRATION_ATTESTATION_BY_VERSION = {mappings!r}\n"
                "def normalize_ready_integration_evidence(value):\n"
                "    schema_version = value.get('schema_version')\n"
                "    expected_keys = READY_INTEGRATION_KEYS_BY_VERSION.get(schema_version)\n"
                "    if expected_keys is None or set(value) != expected_keys:\n"
                "        raise ValueError('invalid schema')\n"
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

    def add_historical_thread(self):
        feedback = copy.deepcopy(self.reviewed.feedback)
        feedback["threads"].append({
            "node_id": "PRRT_HISTORICAL", "is_resolved": False, "is_outdated": True,
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
                       "is_resolved": False, "is_outdated": True, "classification": "VALID_ACTIONABLE",
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


class LifecycleOrchestrationTests(TestCase):
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

                def fixed_remote(root, arguments, maximum):
                    if "fetch" in arguments:
                        self.assertEqual(arguments, ["-c", "fetch.fsckObjects=true", "fetch", "--no-tags", "origin", fixture.main, fixture.predecessor])
                        return original_git(root, ["fetch", "--no-tags", str(fixture.root), fixture.main, fixture.predecessor], maximum)
                    return original_git(root, arguments, maximum)

                with mock.patch.object(version_collision, "_git", side_effect=fixed_remote), mock.patch.object(
                    version_collision, "_observe_main", return_value=fixture.main,
                ), mock.patch.object(version_collision, "_require_accepted_issuer"):
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

    def test_collision_candidate_local_issuer_cannot_fetch_authority(self) -> None:
        from scripts.secpal_pr_review import version_collision

        with mock.patch.object(version_collision, "_observe_main", return_value="f" * 40), mock.patch.object(
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
        self.assertTrue({"1.1", "1.2"} <= set(live["versions"]))
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
                "successor classification decision is unsupported",
            ),
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
