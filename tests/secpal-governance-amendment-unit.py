#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import replace
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock

from tests.secpal_actions_fixture import load_actions
actions_owner = load_actions()

from scripts.secpal_pr_review import governance_amendment as amendment
from scripts.secpal_pr_review import fast_path
from scripts.secpal_pr_review import lifecycle_authority as authority

SIGNER = "lifecycle-legacy-adoption@secpal.app"
SOURCE = "aroviqen@secpal.app"
ROOT_SIGNER = SOURCE
HEAD = "a" * 40
TREE = "b" * 40
PARENT = "c" * 40
FULL_CANDIDATE_PATHS = [
    ".agents/skills/secpal-pr-review/references/contract.md",
    ".agents/skills/secpal-pr-review/references/repositories.json",
    ".agents/skills/secpal-pr-review/references/repositories.schema.json",
    "CHANGELOG.md",
    "docs/secpal-pr-review-workflow.md",
    "policies/governance-amendment-bootstrap.json",
    "policies/governance-amendment-bootstrap.json.license",
    "policies/qualified-remediation-successor-evidence-loss.json",
    "policies/qualified-remediation-successor-evidence-loss.json.license",
    "scripts/README.md",
    "scripts/secpal-pr-review-actions.py",
    "scripts/secpal-resolve-fixed-threads.py",
    "scripts/sync-required-checks.sh",
    "scripts/secpal_pr_review/fast_path.py",
    "scripts/secpal_pr_review/governance_amendment.py",
    "scripts/secpal_pr_review/lifecycle_authority.py",
    "scripts/secpal_pr_review/qualified_remediation_successor_loss.py",
    "tests/secpal-governance-amendment-unit.py",
    "tests/secpal-lifecycle-authority-unit.py",
    "tests/secpal-pr-review-actions-unit.py",
    "tests/secpal-pr-review-static-policy.py",
    "tests/secpal-qualified-remediation-successor-loss-unit.py",
    "tests/secpal-resolve-fixed-threads-unit.py",
]


def ready_ci_fixtures(
    head: str, base: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ready_at = "2026-09-18T12:00:00Z"
    events = [{
        "id": 9601, "event": "ready_for_review", "created_at": ready_at,
        "actor": {"login": "aroviqen"},
    }]
    runs = [{
        "id": 9700 + index, "name": name, "event": "pull_request_target",
        "status": "completed", "conclusion": "success", "head_sha": head,
        "created_at": "2026-09-18T12:00:01Z",
        "run_started_at": "2026-09-18T12:00:02Z",
        "pull_requests": [{
            "number": 961,
            "head": {"sha": head},
            "base": {"sha": base},
        }],
    } for index, name in enumerate(sorted(amendment.READY_WORKFLOW_NAMES))]
    return events, runs


def feedback_response(
    arguments: list[str], head: str, threads: list[dict[str, object]],
    reviews: list[dict[str, object]], comments: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    query = next(item[6:] for item in arguments if item.startswith("query="))
    page = {"hasNextPage": False, "endCursor": None}
    pull: dict[str, object] = {"headRefOid": head}
    value: dict[str, object] = {
        "data": {"repository": {"pullRequest": pull}},
    }
    if "reviewThreads(first:" in query:
        pull["reviewThreads"] = {"nodes": threads, "pageInfo": page}
    elif "reviews(first:" in query:
        pull["reviews"] = {"nodes": reviews, "pageInfo": page}
    elif "comments(first:" in query and "node(id:$thread)" not in query:
        pull["comments"] = {"nodes": comments or [], "pageInfo": page}
    elif "node(id:$thread)" in query:
        value["data"]["node"] = {"comments": {"nodes": [], "pageInfo": page}}
    else:
        raise AssertionError(query)
    return value


def signer(payload: bytes, domain: str) -> dict[str, str]:
    return {
        "format": "ssh", "signer_identity": SIGNER,
        "value": hashlib.sha256(domain.encode() + payload).hexdigest(),
    }


def verifier(payload: bytes, signature: dict[str, str], identity: str, domain: str) -> authority.VerifiedSignature:
    if signature != signer(payload, domain) or identity != SIGNER:
        raise authority.LifecycleAuthorityError("bad fixture signature")
    return authority.VerifiedSignature(identity, "ssh")


def root_signer(payload: bytes, domain: str) -> dict[str, str]:
    return {
        "format": "ssh", "signer_identity": ROOT_SIGNER,
        "value": hashlib.sha256(domain.encode() + payload).hexdigest(),
    }


def root_verifier(payload: bytes, signature: dict[str, str], identity: str, domain: str) -> authority.VerifiedSignature:
    if signature != root_signer(payload, domain) or identity != ROOT_SIGNER:
        raise authority.LifecycleAuthorityError("bad root fixture signature")
    return authority.VerifiedSignature(identity, "ssh")


def signature_verifier(
    payload: bytes, signature: dict[str, str], identity: str, domain: str
) -> authority.VerifiedSignature:
    if identity == ROOT_SIGNER:
        return root_verifier(payload, signature, identity, domain)
    return verifier(payload, signature, identity, domain)


def state() -> dict[str, object]:
    value = authority.initial_state()
    value.update(unrestricted_review_count=1, remediation_cycle_count=1)
    return value


def history() -> list[dict[str, object]]:
    return [
        {"sequence": 1, "kind": "PR_CREATED_DRAFT", "observed_at": "2026-09-18T10:00:00Z", "head_sha": PARENT, "reviewed_head_sha": None},
        {"sequence": 2, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-09-18T11:00:00Z", "head_sha": HEAD, "reviewed_head_sha": None},
    ]


def proposed_policy() -> dict[str, object]:
    return json.loads(
        (Path(__file__).parents[1] / amendment.POLICY_PATH).read_text()
    )["amendments"][0]


def authorization(
    *, head: str = HEAD, tree: str = TREE, parent: str = PARENT,
    accepted_main: str | None = None,
    changed: list[dict[str, str]] | None = None,
    source_oids: list[str] | None = None,
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    policy = policy or proposed_policy()
    accepted_main = accepted_main or str(policy["accepted_main_sha"])
    qualified = policy["qualified_source"]
    changed = changed or [
        {"path": "policies/governance-amendment-bootstrap.json", "blob_oid": "d" * 40, "mode": "100644"},
        {"path": "scripts/secpal_pr_review/governance_amendment.py", "blob_oid": "e" * 40, "mode": "100644"},
    ]
    value = {
        "schema_version": "1.0", "kind": amendment.KIND, "domain": amendment.DOMAIN,
        "purpose": amendment.PURPOSE, "repository": "SecPal/.github",
        "delivery_issue": 960, "pull_request": 961, "pull_request_state": "OPEN",
        "qualified_source": qualified, "head_sha": head, "tree_sha": tree,
        "ordered_parent_shas": [parent],
        "accepted_main_sha": accepted_main,
        "changed_files": changed, "change_digest": "",
        "governance_path_prefixes": policy["allowed_path_prefixes"],
        "source_commits": [
            amendment.source_commit_evidence(oid, SOURCE, accepted_main)
            for oid in (source_oids or [head])
        ],
        "natural_ci": {"head_sha": head, "workflow_identity": "pull-request-ci", "result": "PASS", "evidence_digest": "2" * 64},
        "independent_qualification": {
            "verifier_identity": "verifier",
            "conversation_id": "new-verifier",
            "head_sha": head, "tree_sha": tree, "result": "PASS",
            "qualification_digest": authority.digest_json({
                "verifier_identity": "verifier",
                "conversation_id": "new-verifier",
                "head_sha": head, "tree_sha": tree, "result": "PASS",
            }),
        },
        "current_validation": {"accepted_main_sha": accepted_main, "policy_digest": "4" * 64, "command_set_digest": "5" * 64, "result": "PASS"},
        "feedback": {"state_digest": "6" * 64, "feedback_digest": "7" * 64, "thread_inventory_digest": "8" * 64, "material_finding_ids": []},
        "observed_pre_enrollment_history": [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT", "observed_at": "2026-09-18T10:00:00Z", "head_sha": parent, "reviewed_head_sha": None},
            {"sequence": 2, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-09-18T11:00:00Z", "head_sha": head, "reviewed_head_sha": None},
        ], "intended_state": state(),
        "historical_evidence": amendment.historical_evidence(),
        "historical_absence_proof": {
            "head_sha": head,
            "verification_authority": "PROTECTED_DELIVERY_HISTORY_AND_ARTIFACT_AUDIT",
            "history_digest": "9" * 64,
            "artifact_audit_digest": "a" * 64,
            "result": "NO_HISTORICAL_RECEIPT_ISSUED",
        },
        "architecture_necessity": {
            "existing_authority_result": "INSUFFICIENT",
            "smaller_nonrecursive_extension": "NONE",
            "recursive_self_bootstrap": "PROVEN",
            "evidence_digest": "b" * 64,
        },
        "concepts": policy["concepts"],
        "human_authority_identity": policy["human_authority_identity"],
        "human_authorization_digest": policy["human_authorization_digest"],
        "authorization_id": policy["authorization_id"],
        "bounded_uses": 1, "root_authorization": {},
        "signer_identity": SIGNER, "signature": {},
        "authorization_digest": "",
    }
    value["source_signature"] = {
        "signer_identity": SOURCE,
        "range_signature_evidence_digest": (
            amendment.source_signature_binding_digest(
                value["source_commits"], accepted_main
            )
        ),
        "verified": True,
    }
    return reseal(value)


def reseal(value: dict[str, object]) -> dict[str, object]:
    value = copy.deepcopy(value)
    value["change_digest"] = amendment.change_digest(
        repository=value["repository"],
        delivery_issue=value["delivery_issue"],
        pull_request=value["pull_request"],
        head_sha=value["head_sha"],
        tree_sha=value["tree_sha"],
        ordered_parent_shas=value["ordered_parent_shas"],
        accepted_main_sha=value["accepted_main_sha"],
        changed_files=value["changed_files"],
    )
    facts = {
        key: copy.deepcopy(item) for key, item in value.items()
        if key not in {
            "root_authorization", "signer_identity", "signature",
            "authorization_digest",
        }
    }
    root_fields = {
        "schema_version": "1.0",
        "kind": amendment.ROOT_AUTHORIZATION_KIND,
        "domain": amendment.ROOT_AUTHORIZATION_DOMAIN,
        "repository": value["repository"],
        "delivery_issue": value["delivery_issue"],
        "pull_request": value["pull_request"],
        "accepted_main_sha": value["accepted_main_sha"],
        "head_sha": value["head_sha"],
        "tree_sha": value["tree_sha"],
        "purpose": value["purpose"],
        "governance_path_prefixes": value["governance_path_prefixes"],
        "human_authority_identity": value["human_authority_identity"],
        "human_authorization_digest": value["human_authorization_digest"],
        "authorized_facts_digest": authority.digest_json(facts),
        "bounded_uses": 1,
        "signer_identity": ROOT_SIGNER,
    }
    root_signed = {
        **root_fields,
        "signature": root_signer(
            authority.canonical_json_bytes(root_fields),
            amendment.ROOT_AUTHORIZATION_DOMAIN,
        ),
    }
    value["root_authorization"] = {
        **root_signed,
        "authorization_digest": authority.digest_json(root_signed),
    }
    unsigned = {key: copy.deepcopy(item) for key, item in value.items() if key not in {"authorization_digest", "signature"}}
    value["signature"] = signer(authority.canonical_json_bytes(unsigned), amendment.DOMAIN)
    signed = {key: copy.deepcopy(item) for key, item in value.items() if key != "authorization_digest"}
    value["authorization_digest"] = authority.digest_json(signed)
    return value


def observation_inputs(value: dict[str, object]) -> dict[str, object]:
    return {
        key: copy.deepcopy(value[key])
        for key in amendment.ISSUANCE_INPUT_FIELDS
    }


def reviewed_authorization() -> dict[str, object]:
    value = authorization()
    value["delivery_issue"] = 1053
    value["pull_request"] = 1055
    value["governance_path_prefixes"] = amendment.REVIEWED_READY_PATH_PREFIXES
    value["human_authority_identity"] = amendment.REVIEWED_READY_AUTHORITY_IDENTITY
    value["authorization_id"] = "governance-amendment:SecPal/.github:1053:1055"
    value["current_validation"]["accepted_main_sha"] = "d" * 40
    qualified = value["qualified_source"]
    qualified.update(head_sha=HEAD, tree_sha=TREE,
                     material_finding_ids=["finding-thread"])
    qualified["qualification_digest"] = authority.digest_json({
        "conversation_id": qualified["verifier_conversation_id"],
        "workspace": qualified["verifier_workspace"],
        "head_sha": HEAD, "tree_sha": TREE,
        "result": "PASS", "material_finding_ids": ["finding-thread"],
    })
    value["feedback"]["material_finding_ids"] = ["finding-thread"]
    observed = [
        {"sequence": 1, "kind": "PR_CREATED_DRAFT",
         "observed_at": "2026-09-18T10:00:00Z", "head_sha": HEAD,
         "reviewed_head_sha": None},
        {"sequence": 2, "kind": "DRAFT_TO_READY_OBSERVED",
         "observed_at": "2026-09-18T10:30:00Z", "head_sha": HEAD,
         "reviewed_head_sha": None},
        {"sequence": 3, "kind": "REVIEW_SUBMITTED",
         "observed_at": "2026-09-18T11:00:00Z", "head_sha": HEAD,
         "reviewed_head_sha": HEAD},
    ]
    value["observed_pre_enrollment_history"] = observed
    value["intended_state"] = authority.initial_state()
    value["intended_state"].update(
        unrestricted_review_count=1, draft=False, ready=True,
        ready_transition_count=1,
        ready_history=[{
            "sequence": 1, "transition_kind": "DRAFT_TO_READY",
            "observation_digest": authority.digest_json(observed[1]),
        }],
    )
    value["human_authorization_digest"] = authority.digest_json({
        "authority_identity": value["human_authority_identity"],
        "repository": value["repository"], "delivery_issue": 1053,
        "pull_request": 1055, "purpose": amendment.PURPOSE,
        "qualified_source_digest": qualified["qualification_digest"],
        "accepted_main_sha": value["accepted_main_sha"],
        "decision": "APPROVED", "bounded_uses": 1,
    })
    return reseal(value)


class GovernanceAmendmentTests(TestCase):
    @contextmanager
    def ready_prior_root(self):
        """Authenticated signed v4 root; only external observations are replaced."""
        from scripts.secpal_pr_review import lifecycle_publication as publication

        root = Path(__file__).resolve().parents[1]
        actions = load_actions()
        first, second = self.patches()
        with first, second, tempfile.TemporaryDirectory() as directory:
            self._ready_integration_commits = {}
            def integration_git(_root, argv, **_kwargs):
                if argv[:3] == ["remote", "get-url", "origin"]:
                    output = "https://github.com/SecPal/.github.git\n"
                elif argv[:2] == ["cat-file", "commit"]:
                    output = self._ready_integration_commits[argv[2]]
                elif argv[0] == "verify-commit":
                    output = f'Good "git" signature for {SOURCE} with ED25519 key SHA256:fixture\n'
                elif argv[0] == "merge-tree":
                    output = "f" * 40 + "\x00"
                elif argv[0] in {"diff", "diff-tree"}:
                    output = ""
                else:
                    raise AssertionError(argv)
                return subprocess.CompletedProcess(argv, 0, output, "")
            trust = replace(authority._load_lifecycle_trust_policy("SecPal/.github"),
                            transition_signer_identities=frozenset({SIGNER}),
                            authority_signer_identities=frozenset({SIGNER}))
            reviewed = publication.fast_path.StableFeedbackState(
                repository="SecPal/.github", pull_request_number=1055,
                head_sha=HEAD, base_ref="main", base_sha=PARENT, pr_state="OPEN",
                feedback={"pull_request_reactions": [], "reviews": [],
                          "conversation_comments": [], "threads": [{
                              "node_id": "finding-thread", "is_resolved": False,
                              "is_outdated": False, "comments": [{
                                  "node_id": "finding-comment", "body_digest": "1" * 64,
                                  "actor": {"login": "reviewer", "node_id": "reviewer-id", "database_id": 1},
                                  "reply_to_id": None, "reactions": [],
                              }],
                          }]},
            )
            registered = reviewed_authorization()
            registered["feedback"].update(
                state_digest=reviewed.state_digest, feedback_digest=reviewed.feedback_digest,
                thread_inventory_digest=authority.digest_json(reviewed.feedback["threads"]),
            )
            lifecycle, bundle = self.zero_receipt_root(amendment_authorization=reseal(registered))
            current = publication.VerifiedLifecyclePublication(
                "3" * 40, "4" * 64, "refs/heads/secpal-lifecycle-publications",
                None, None, lifecycle, authority.canonical_json_bytes(bundle),
            )
            with (
                mock.patch.object(actions, "_load_lifecycle_publication_helpers",
                                  return_value=(authority, publication)),
                mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=trust),
                mock.patch.object(publication.fast_path, "_run_integration_commit_git", side_effect=integration_git),
                mock.patch.object(actions, "_require_accepted_main_bridge_source",
                                  return_value="9" * 40),
                mock.patch.object(publication, "verify_current_lifecycle_authority",
                                  return_value=current),
                mock.patch.object(actions, "_verified_prior_delivery_commit",
                                  return_value={"parent_sha": PARENT,
                                                "parent_shas": [PARENT],
                                                "tree_sha": TREE,
                                                "signer": {"kind": "SSH_PRINCIPAL", "identity": SOURCE}}),
            ):
                yield actions, publication, current, bundle, Path(directory), reviewed

    def derive_ready_root(self, actions, current, candidate):
        return actions._derive_exact_state_adoption_ready_prior_authority(
            repository_root=candidate, repository="SecPal/.github",
            delivery_issue=1053, pull_request=1055,
            binding={"default_branch": "main", "signature_policy": {"accepted_formats": ["ssh"]}},
        )

    def integration_package(self, publication, current, manifest, candidate, reviewed, *, head="e" * 40):
        """Exercise canonical typed evidence, receipt, attestation and commit admission."""
        fp = publication.fast_path
        registry = {"default_branch": "main", "manual_gates": [], "validation": [],
                    "signature_policy": {"accepted_formats": ["ssh"]}}
        eligibility = {
            "eligible": True, "lifecycle_identity": current.lifecycle.lifecycle_id,
            "draft_before": False, "draft_after": False, "ready_before": True,
            "ready_after": True, "ready_transition": False, "review_requested": False,
            "cycle_3": False,
        }
        for field, state_field in (
            ("unrestricted_reviews", "unrestricted_review_count"),
            ("remediation_cycles", "remediation_cycle_count"),
            ("exceptional_recoveries", "exceptional_recovery_count"),
            ("exceptional_continuations", "exceptional_continuation_count"),
        ):
            eligibility[field + "_before"] = eligibility[field + "_after"] = current.lifecycle.state[state_field]
        integration = {
            "schema_version": "1.1", "kind": "TWO_PARENT_READY_INTEGRATION",
            "authorization_id": "fixture:ready-integration:" + head,
            "repository": current.lifecycle.repository,
            "delivery_issue_number": current.lifecycle.delivery_issue,
            "pull_request_number": current.lifecycle.pull_request,
            "prior_delivery_head_sha": current.lifecycle.head_sha,
            "prior_authority_digest": fp.digest_json(manifest),
            "prior_authority_tag_object_sha": ("5" if current.lifecycle.head_sha == HEAD else "6") * 40,
            "target_base": {"ref": "main", "authorized_sha": "9" * 40, "observed_sha": "9" * 40},
            "ordered_parent_shas": [current.lifecycle.head_sha, "9" * 40],
            "validated_tree_sha": "f" * 40, "mechanical_merge_tree_sha": "f" * 40,
            "mechanical_conflict_paths": [], "manual_conflict_resolution_delta": [],
            "reviewed_state_digest": reviewed.state_digest, "reviewed_feedback_digest": reviewed.feedback_digest,
            "validation_execution": {"registry_digest": fp.digest_json(registry), "command_set_digest": fp.digest_json([])},
            "expected_signer": {"kind": "SSH_PRINCIPAL", "identity": SOURCE},
            "eligibility": eligibility,
        }
        if current.lifecycle.head_sha != reviewed.head_sha:
            integration.update(schema_version="1.2", reviewed_head_sha=reviewed.head_sha)
        integration = fp.normalize_ready_integration_evidence(
            integration, repository=current.lifecycle.repository, reviewed_state=reviewed,
            registry=registry, validated_tree_sha="f" * 40,
        )
        receipt = fp.create_validation_receipt(
            repository=current.lifecycle.repository, head_sha=current.lifecycle.head_sha,
            validated_tree_sha="f" * 40, registry=registry, command_set=[],
            successful_result=True, reviewed_state=reviewed, manual_gate_evidence=[],
            integration_evidence_digest=fp.digest_json(integration),
        )
        attestation = fp.create_ready_integration_attestation(
            repository=current.lifecycle.repository, head_sha=head,
            registry=registry, command_set=[], reviewed_state=reviewed,
            validation_receipt=receipt, integration_evidence=integration,
        )
        outputs = [
            "https://github.com/SecPal/.github.git\n",
            "tree " + "f" * 40 + "\n" + "".join("parent " + p + "\n" for p in integration["ordered_parent_shas"])
            + "gpgsig -----BEGIN SSH SIGNATURE-----\n\n",
            f'Good "git" signature for {SOURCE} with ED25519 key SHA256:fixture\n',
            "f" * 40 + "\x00", "",
        ]
        self._ready_integration_commits[head] = outputs[1]
        with mock.patch.object(fp, "_run_integration_commit_git",
                               side_effect=[subprocess.CompletedProcess([], 0, output, "") for output in outputs]):
            validation = fp.verify_ready_integration_attestation(
                attestation, repository=current.lifecycle.repository, head_sha=head,
                registry=registry, command_set=[], reviewed_state=reviewed,
                validation_receipt=receipt, integration_evidence=integration,
                commit_parent_shas=integration["ordered_parent_shas"], commit_tree_sha="f" * 40,
                commit_validation_receipt_digest=receipt["receipt_digest"],
                commit_integration_evidence_digest=fp.digest_json(integration),
                repository_root=candidate, signature_policy=registry["signature_policy"],
            )
        return integration, validation, registry

    @contextmanager
    def prior_tag_observation(self, actions, manifest, *, forged=False, wrong_signer=False, additional=()):
        tags = {}
        refs = {}
        for item in (manifest, *additional):
            oid = ("5" if item["prior_delivery_head_sha"] == HEAD else "6") * 40
            refs[actions._canonical_ready_prior_authority_tag_ref(item)] = oid
            tags[oid] = (f"object {item['prior_delivery_head_sha']}\ntype commit\ntag fixture\ntagger fixture\n\n"
                         f"SecPal-Prior-Authority: {'0' * 64 if forged else actions.fast_path.digest_json(item)}\n")
        def git(_root, argv, **_kwargs):
            if argv[0] == "rev-parse":
                output = refs[argv[1].removesuffix("^{tag}")]
            elif argv[:2] == ["cat-file", "-t"]:
                output = "tag"
            elif argv[0] == "verify-tag":
                identity = "wrong@example.test" if wrong_signer else SOURCE
                output = f'Good "git" signature for {identity} with ED25519 key SHA256:fixture\n'
            else:
                output = tags[argv[2]]
            return subprocess.CompletedProcess(argv, 0, output, "")
        with mock.patch.object(actions, "_run_attestation_git", side_effect=git), mock.patch.object(
            actions, "_commit_validation_receipt_digest", return_value=None,
        ):
            yield

    def test_direct_v4_ready_root_supplies_prior_authority_with_open_findings(self):
        with self.ready_prior_root() as (actions, _publication, current, bundle, candidate, _reviewed):
            original = copy.deepcopy(current)
            manifest = actions._derive_exact_state_adoption_ready_prior_authority(
                repository_root=candidate, repository=current.lifecycle.repository,
                delivery_issue=current.lifecycle.delivery_issue,
                pull_request=current.lifecycle.pull_request,
                binding={"default_branch": "main", "signature_policy": {"accepted_formats": ["ssh"]}},
            )
            self.assertEqual(current, original)
            self.assertEqual(manifest["schema_version"], "1.2")
            self.assertEqual(manifest["source_authority_mode"],
                             "EXACT_STATE_ADOPTION_V4_GOVERNANCE_AMENDMENT_ROOT")
            self.assertNotIn("recovery_publication", manifest)
            self.assertIsNone(manifest["prior_validation_receipt_digest"])
            self.assertIsNone(manifest["prior_final_attestation_digest"])
            self.assertEqual(manifest["source_authority"]["historical_evidence"],
                             amendment.historical_evidence())
            self.assertEqual(manifest["lifecycle"]["remediation_cycles"], 0)
            self.assertEqual(manifest["lifecycle"]["ready_history"],
                             current.lifecycle.state["ready_history"])
            self.assertEqual(manifest["source_authority"]["feedback"]["material_finding_ids"],
                             ["finding-thread"])
            self.assertEqual(manifest["source_authority"]["adoption_source_evidence_digest"],
                             current.lifecycle.adoption_source_evidence_digest)
            self.assertEqual(actions.fast_path.normalize_ready_integration_prior_authority(manifest),
                             manifest)

    def test_v4_ready_root_rejects_proof_and_historical_substitution(self):
        with self.ready_prior_root() as (actions, publication, current, bundle, candidate, _reviewed):
            mutations = {
                "wrong version": lambda p: p.update(proof_version="3.0"),
                "wrong schema": lambda p: p.update(schema_version="3.0"),
                "missing amendment": lambda p: p.pop("governance_amendment_authorization"),
                "forged amendment": lambda p: p["governance_amendment_authorization"]["signature"].update(value="forged"),
                "registration": lambda p: p["governance_amendment_authorization"]["current_validation"].update(accepted_main_sha="f" * 40),
                "registered source": lambda p: p["governance_amendment_authorization"]["qualified_source"].update(head_sha="f" * 40),
                "PR replay": lambda p: p.update(pull_request=1056),
                "Issue replay": lambda p: p.update(delivery_issue=1054),
                "repository replay": lambda p: p.update(repository="SecPal/other"),
                "head": lambda p: p.update(head_sha="f" * 40),
                "tree": lambda p: p.update(tree_sha="f" * 40),
                "lifecycle": lambda p: p.update(lifecycle_id="other-lifecycle"),
                "state": lambda p: p["intended_state"].update(remediation_cycle_count=1),
                "history": lambda p: p["observed_pre_enrollment_history"].pop(),
                "Ready history": lambda p: p["intended_state"]["ready_history"][0].update(observation_digest="f" * 64),
                "adoption source": lambda p: p.update(adoption_source_evidence_digest="f" * 64),
                "reconstructed": lambda p: p["historical_evidence"].update(bytes_reconstructed=True),
                "current safety as history": lambda p: p["historical_evidence"].update(validation_receipt_digest="f" * 64),
                "adoption as history": lambda p: p["historical_evidence"].update(final_attestation_digest=p["authorization_digest"]),
            }
            for field in ("validation_receipt_digest", "source_validation_evidence_digest", "final_attestation_digest"):
                mutations[field] = lambda p, field=field: p["historical_evidence"].update(**{field: "f" * 64})
            for label, mutate in mutations.items():
                changed = copy.deepcopy(bundle)
                mutate(changed["exact_state_adoption_proof"])
                substituted = replace(current, serialized_lifecycle_evidence=authority.canonical_json_bytes(changed))
                with self.subTest(label=label), mock.patch.object(
                    publication, "verify_current_lifecycle_authority", return_value=substituted,
                ), self.assertRaises(actions.fast_path.SecurityBlocker):
                    self.derive_ready_root(actions, substituted, candidate)

    def test_v4_ready_root_rejects_nonroot_and_current_source_drift(self):
        with self.ready_prior_root() as (actions, publication, current, bundle, candidate, _reviewed):
            alternatives = [replace(current, predecessor_publication_oid="f" * 40)]
            for field in ("transition_authorizations", "authority_chain"):
                changed = copy.deepcopy(bundle)
                changed[field].append({})
                alternatives.append(replace(current, serialized_lifecycle_evidence=authority.canonical_json_bytes(changed)))
            for field, value in {
                "repository": "SecPal/other", "delivery_issue": 1054, "pull_request": 1056,
                "head_sha": "f" * 40, "tree_sha": "f" * 40, "lifecycle_id": "other-lifecycle",
                "authority_digest": "f" * 64, "adoption_source_evidence_digest": None,
                "validation_receipt_digest": "f" * 64, "source_validation_evidence_digest": "f" * 64,
            }.items():
                alternatives.append(replace(current, lifecycle=replace(current.lifecycle, **{field: value})))
            for changed in alternatives:
                with self.subTest(changed=changed), mock.patch.object(
                    publication, "verify_current_lifecycle_authority", return_value=changed,
                ), self.assertRaises(actions.fast_path.SecurityBlocker):
                    self.derive_ready_root(actions, changed, candidate)
            with mock.patch.object(actions, "_verified_prior_delivery_commit", return_value={
                "parent_sha": PARENT, "parent_shas": [PARENT], "tree_sha": TREE,
                "signer": {"kind": "SSH_PRINCIPAL", "identity": "wrong@example.test"},
            }), self.assertRaises(actions.fast_path.SecurityBlocker):
                self.derive_ready_root(actions, current, candidate)
            with mock.patch.object(actions, "_require_accepted_main_bridge_source",
                                   side_effect=actions.fast_path.SecurityBlocker("candidate-local")), self.assertRaises(actions.fast_path.SecurityBlocker):
                self.derive_ready_root(actions, current, candidate)

    def test_v4_ready_root_manifest_cannot_select_or_fabricate_authority(self):
        with self.ready_prior_root() as (actions, _publication, current, _bundle, candidate, _reviewed):
            manifest = self.derive_ready_root(actions, current, candidate)
            for field, value in {
                "source_authority_mode": "EXACT_STATE_ADOPTION_V3",
                "prior_validation_receipt_digest": "f" * 64,
                "prior_final_attestation_digest": "f" * 64,
                "recovery_publication": {},
            }.items():
                changed = {**manifest, field: value}
                with self.subTest(field=field), self.assertRaises(actions.fast_path.SecurityBlocker):
                    actions.fast_path.normalize_ready_integration_prior_authority(changed)
            for location, field, value in (
                ("publication", "object_oid", "f" * 40),
                ("publication", "publication_digest", "f" * 64),
                ("source_authority", "registration_tip_sha", "f" * 40),
                ("source_authority", "registered_source_digest", "f" * 64),
                ("source_authority", "adoption_authorization_digest", "f" * 64),
                ("lifecycle", "remediation_cycles", 1),
            ):
                changed = copy.deepcopy(manifest)
                changed[location][field] = value
                with self.subTest(field=field), self.assertRaises(actions.fast_path.SecurityBlocker):
                    actions._require_exact_adopted_ready_manifest(changed, manifest)
            changed = copy.deepcopy(manifest)
            changed["source_authority"]["feedback"]["material_finding_ids"] = []
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                actions._require_exact_adopted_ready_manifest(changed, manifest)

    def test_v4_root_admits_typed_integration_and_preserves_lifecycle_and_findings(self):
        with self.ready_prior_root() as (actions, publication, current, bundle, candidate, reviewed):
            manifest = self.derive_ready_root(actions, current, candidate)
            integration, validation, registry = self.integration_package(
                publication, current, manifest, candidate, reviewed,
            )
            path = candidate / "authority.json"
            path.write_text(json.dumps(manifest))
            arguments = SimpleNamespace(
                repo=current.lifecycle.repository, delivery_issue=current.lifecycle.delivery_issue,
                prior_authority=str(path), prior_authority_tag_ref=actions._canonical_ready_prior_authority_tag_ref(manifest),
                expected_prior_authority_signer=SOURCE,
            )
            with self.prior_tag_observation(actions, manifest):
                self.assertEqual(actions._verify_ready_integration_prior_authority(
                    arguments=arguments, repository_root=candidate, binding=registry,
                    integration_evidence=integration, live_observation=None,
                    reviewed_state=reviewed,
                ), manifest)
                actions._verify_ready_integration_published_authority(manifest, integration, published=current)
            for option in ("forged", "wrong_signer"):
                with self.subTest(option=option), self.prior_tag_observation(actions, manifest, **{option: True}), self.assertRaises(actions.fast_path.SecurityBlocker):
                    actions._verify_ready_integration_prior_authority(
                        arguments=arguments, repository_root=candidate, binding=registry,
                        integration_evidence=integration, live_observation=None,
                        reviewed_state=reviewed,
                    )
            for parents in ([HEAD], ["9" * 40, HEAD], [HEAD, PARENT, "9" * 40]):
                generic = {**integration, "ordered_parent_shas": parents}
                with self.subTest(parents=parents), self.assertRaises(publication.fast_path.SecurityBlocker):
                    publication.fast_path.normalize_ready_integration_evidence(
                        generic, repository=current.lifecycle.repository, reviewed_state=reviewed,
                        registry=registry, validated_tree_sha="f" * 40,
                    )
            self.assertTrue(publication.fast_path.is_verified_validation_evidence(validation))
            event = authority.create_transition_authorization(
                event_id="fixture:head-advanced", repository=current.lifecycle.repository,
                delivery_issue=current.lifecycle.delivery_issue, lifecycle_id=current.lifecycle.lifecycle_id,
                pull_request=current.lifecycle.pull_request,
                predecessor_authority_digest=current.lifecycle.authority_digest,
                predecessor_head_sha=current.lifecycle.head_sha, resulting_head_sha=validation.head_sha,
                transition_kind="HEAD_ADVANCED", replacement_pull_request=None,
                initialization_evidence_digest=current.lifecycle.initialization_evidence_digest,
                signer_identity=SIGNER, signer=signer,
            )
            snapshot = authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=current.serialized_lifecycle_evidence,
                authorization=event, signer_identity=SIGNER, authority_signer=signer,
                current_head_evidence=validation,
            )
            successor_raw = authority.serialize_exact_state_adoption_evidence(
                exact_state_adoption_proof=bundle["exact_state_adoption_proof"],
                transition_authorizations=[event], authority_chain=[snapshot],
            )
            successor = replace(
                current, publication_oid="8" * 40, publication_digest="7" * 64,
                predecessor_publication_oid=current.publication_oid,
                lifecycle=authority._verify_lifecycle_authority_for_journal(successor_raw),
                serialized_lifecycle_evidence=successor_raw,
            )
            self.assertEqual(successor.lifecycle.state, current.lifecycle.state)
            self.assertEqual(publication.fast_path.verified_ready_integration_review_context(validation)[0].feedback,
                             reviewed.feedback)
            transition = SimpleNamespace(
                predecessor=current, successor=successor, transition_kind="HEAD_ADVANCED",
                predecessor_authority_digest=current.lifecycle.authority_digest,
                predecessor_head_sha=current.lifecycle.head_sha, resulting_head_sha=successor.lifecycle.head_sha,
                initialization_evidence_digest=current.lifecycle.initialization_evidence_digest,
            )
            from scripts.secpal_pr_review import bootstrap_source_admission as transport
            with (
                self.prior_tag_observation(actions, manifest),
                mock.patch.object(publication, "_verify_historical_lifecycle_transition", return_value=transition),
                mock.patch.object(transport, "_load_actions_helper", return_value=actions),
                mock.patch.object(publication, "_authenticate_provider_integration_verifier"),
            ):
                self.assertEqual(publication.verify_ready_integration_predecessor(successor, validation, manifest)[0], current)
                from scripts.secpal_pr_review import lifecycle_orchestration as orchestration
                remediation_reviewed, _eligibility = orchestration._ready_integration_remediation_predecessor_context(
                    successor, validation, manifest,
                )
                self.assertEqual(remediation_reviewed.feedback, reviewed.feedback)
                chained = publication.verify_ready_integration_prior_authority(successor, ((validation, manifest),))
                self.assertEqual(json.loads(chained.manifest_json)["prior_delivery_head_sha"], successor.lifecycle.head_sha)
                provider = publication.derive_ready_source_recovery_provider_binding(
                    successor, ready_integrations=((validation, manifest),),
                )
                self.assertEqual(provider.provider_head_sha, current.lifecycle.head_sha)
            second_manifest = json.loads(chained.manifest_json)
            _integration2, validation2, _registry2 = self.integration_package(
                publication, successor, second_manifest, candidate, reviewed, head="6" * 40,
            )
            event2 = authority.create_transition_authorization(
                event_id="fixture:second-head-advanced", repository=successor.lifecycle.repository,
                delivery_issue=successor.lifecycle.delivery_issue, lifecycle_id=successor.lifecycle.lifecycle_id,
                pull_request=successor.lifecycle.pull_request,
                predecessor_authority_digest=successor.lifecycle.authority_digest,
                predecessor_head_sha=successor.lifecycle.head_sha, resulting_head_sha=validation2.head_sha,
                transition_kind="HEAD_ADVANCED", replacement_pull_request=None,
                initialization_evidence_digest=successor.lifecycle.initialization_evidence_digest,
                signer_identity=SIGNER, signer=signer,
            )
            snapshot2 = authority.issue_exact_state_adoption_successor_authority(
                serialized_adoption_evidence=successor.serialized_lifecycle_evidence,
                authorization=event2, signer_identity=SIGNER, authority_signer=signer,
                current_head_evidence=validation2,
            )
            second_raw = authority.serialize_exact_state_adoption_evidence(
                exact_state_adoption_proof=bundle["exact_state_adoption_proof"],
                transition_authorizations=[event, event2], authority_chain=[snapshot, snapshot2],
            )
            second = replace(successor, publication_oid="a" * 40, publication_digest="b" * 64,
                             predecessor_publication_oid=successor.publication_oid,
                             lifecycle=authority._verify_lifecycle_authority_for_journal(second_raw),
                             serialized_lifecycle_evidence=second_raw)
            transition2 = SimpleNamespace(
                predecessor=successor, successor=second, transition_kind="HEAD_ADVANCED",
                predecessor_authority_digest=successor.lifecycle.authority_digest,
                predecessor_head_sha=successor.lifecycle.head_sha, resulting_head_sha=second.lifecycle.head_sha,
                initialization_evidence_digest=successor.lifecycle.initialization_evidence_digest,
            )
            def historical(_repository, _issue, oid, **_kwargs):
                return {current.publication_oid: transition, successor.publication_oid: transition2}[oid]
            with (
                self.prior_tag_observation(actions, manifest, additional=(second_manifest,)),
                mock.patch.object(publication, "_verify_historical_lifecycle_transition", side_effect=historical),
                mock.patch.object(transport, "_load_actions_helper", return_value=actions),
                mock.patch.object(publication, "_authenticate_provider_integration_verifier"),
            ):
                packages = ((validation, manifest), (validation2, second_manifest))
                later = publication.verify_ready_integration_prior_authority(second, packages)
                self.assertEqual(json.loads(later.manifest_json)["prior_delivery_head_sha"], second.lifecycle.head_sha)
                self.assertEqual(second.lifecycle.state, current.lifecycle.state)
                provider = publication.derive_ready_source_recovery_provider_binding(second, ready_integrations=packages)
                self.assertEqual(provider.provider_head_sha, HEAD)
                self.assertEqual(len(provider.head_advanced_event_digests), 2)
            omitted = {**integration, "reviewed_feedback_digest": "0" * 64}
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                actions._verify_ready_integration_lifecycle_authority(manifest, omitted, reviewed_state=reviewed)
            for field in ("remediation_cycles_after", "unrestricted_reviews_after"):
                drift = copy.deepcopy(integration)
                drift["eligibility"][field] += 1
                with self.subTest(field=field), self.assertRaises(actions.fast_path.SecurityBlocker):
                    actions._verify_ready_integration_lifecycle_authority(manifest, drift, reviewed_state=reviewed)
            fresh = publication.fast_path.StableFeedbackState.from_payload(reviewed.to_dict())
            fresh.feedback["conversation_comments"].append({
                "node_id": "new-comment", "body_digest": "8" * 64,
                "actor": {"login": "operator", "node_id": "operator-id", "database_id": 2},
                "reply_to_id": None, "reactions": [],
            })
            fresh.refresh_digests()
            changed_feedback = {**integration, "reviewed_state_digest": fresh.state_digest,
                                "reviewed_feedback_digest": fresh.feedback_digest}
            actions._verify_ready_integration_lifecycle_authority(manifest, changed_feedback, reviewed_state=fresh)
            fresh.feedback["threads"] = []
            fresh.refresh_digests()
            changed_feedback.update(reviewed_state_digest=fresh.state_digest, reviewed_feedback_digest=fresh.feedback_digest)
            with self.assertRaises(actions.fast_path.SecurityBlocker):
                actions._verify_ready_integration_lifecycle_authority(manifest, changed_feedback, reviewed_state=fresh)

    def test_target_work_graph_failure_is_bound_to_native_prerequisite(self) -> None:
        statuses = [{
            "context": "Work-Graph PR Gate", "state": "failure",
            "sha": HEAD,
            "description": "Current canonical work-graph evidence blocked delivery",
        }]
        graph = {"data": {"repository": {"issue": {"blockedBy": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [{"number": 1059, "state": "OPEN"}],
        }}}}}
        with mock.patch.object(amendment, "_github_json", return_value=graph):
            proof = amendment._reviewed_target_work_graph_blocker(
                "SecPal/.github", 1053, HEAD, statuses
            )
        self.assertEqual(proof["blocking_issue"], 1059)
        changed = copy.deepcopy(statuses)
        changed[0]["description"] = "tests failed"
        with mock.patch.object(amendment, "_github_json", return_value=graph):
            with self.assertRaises(amendment.GovernanceAmendmentError):
                amendment._reviewed_target_work_graph_blocker(
                    "SecPal/.github", 1053, HEAD, changed
                )

    def test_reviewed_ready_history_uses_one_complete_provider_phase(self) -> None:
        response = {"data": {"repository": {"pullRequest": {
            "createdAt": "2026-10-02T10:50:21Z", "headRefOid": HEAD,
            "timelineItems": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [
                    {"__typename": "PullRequestCommit", "commit": {"oid": HEAD}},
                    {"__typename": "ReadyForReviewEvent",
                     "createdAt": "2026-10-02T10:55:08Z"},
                    {"__typename": "PullRequestReview", "id": "R1",
                     "state": "COMMENTED", "submittedAt": "2026-10-02T10:59:59Z",
                     "commit": {"oid": HEAD}},
                    {"__typename": "PullRequestReview", "id": "R2",
                     "state": "COMMENTED", "submittedAt": "2026-10-02T11:02:47Z",
                     "commit": {"oid": HEAD}},
                ],
            },
        }}}}
        with mock.patch.object(amendment, "_github_json", return_value=response):
            history = amendment._live_reviewed_ready_history(
                "SecPal/.github", 1055, HEAD
            )
        self.assertEqual([item["kind"] for item in history], [
            "PR_CREATED_DRAFT", "DRAFT_TO_READY_OBSERVED", "REVIEW_SUBMITTED",
        ])
        self.assertEqual(history[-1]["reviewed_head_sha"], HEAD)
        poisoned = copy.deepcopy(response)
        poisoned["data"]["repository"]["pullRequest"]["timelineItems"]["nodes"][3]["commit"]["oid"] = PARENT
        with mock.patch.object(amendment, "_github_json", return_value=poisoned):
            with self.assertRaises(amendment.GovernanceAmendmentError):
                amendment._live_reviewed_ready_history(
                    "SecPal/.github", 1055, HEAD
                )

    def test_reviewed_ready_policy_is_selected_only_from_accepted_main(self) -> None:
        original = proposed_policy()
        value = authorization()
        record = copy.deepcopy(original)
        record["delivery_issue"] = 1053
        record["pull_request"] = 1055
        record["allowed_path_prefixes"] = amendment.REVIEWED_READY_PATH_PREFIXES
        record["accepted_main_sha"] = PARENT
        record["qualified_source"] = copy.deepcopy(value["qualified_source"])
        record["qualified_source"].update(
            head_sha=HEAD, tree_sha=TREE, ordered_parent_shas=[PARENT],
            material_finding_ids=["finding-thread"],
        )
        qualified = record["qualified_source"]
        qualified["qualification_digest"] = authority.digest_json({
            "conversation_id": qualified["verifier_conversation_id"],
            "workspace": qualified["verifier_workspace"],
            "head_sha": HEAD, "tree_sha": TREE,
            "result": "PASS", "material_finding_ids": ["finding-thread"],
        })
        observed = [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT",
             "observed_at": "2026-09-18T10:00:00Z", "head_sha": HEAD,
             "reviewed_head_sha": None},
            {"sequence": 2, "kind": "DRAFT_TO_READY_OBSERVED",
             "observed_at": "2026-09-18T10:30:00Z", "head_sha": HEAD,
             "reviewed_head_sha": None},
            {"sequence": 3, "kind": "REVIEW_SUBMITTED",
             "observed_at": "2026-09-18T11:00:00Z", "head_sha": HEAD,
             "reviewed_head_sha": HEAD},
        ]
        record["observed_pre_enrollment_history"] = observed
        record["feedback"] = {
            "state_digest": "1" * 64, "feedback_digest": "2" * 64,
            "thread_inventory_digest": "3" * 64,
            "material_finding_ids": ["finding-thread"],
        }
        state = authority.initial_state()
        state.update(unrestricted_review_count=1, draft=False, ready=True,
                     ready_transition_count=1, ready_history=[{
                         "sequence": 1, "transition_kind": "DRAFT_TO_READY",
                         "observation_digest": authority.digest_json(observed[1]),
                     }])
        record["intended_state"] = state
        record["human_authority_identity"] = amendment.REVIEWED_READY_AUTHORITY_IDENTITY
        record["human_authorization_digest"] = authority.digest_json({
            "authority_identity": record["human_authority_identity"],
            "repository": "SecPal/.github", "delivery_issue": 1053,
            "pull_request": 1055, "purpose": amendment.PURPOSE,
            "qualified_source_digest": qualified["qualification_digest"],
            "accepted_main_sha": PARENT, "decision": "APPROVED",
            "bounded_uses": 1,
        })
        record["authorization_id"] = "governance-amendment:SecPal/.github:1053:1055"
        registry = {"schema_version": "1.0", "repositories": [{
            "repository": "SecPal/.github",
            "governance_amendment_policy": {
                "path": amendment.POLICY_PATH, "kind": amendment.KIND,
                "purpose": amendment.PURPOSE,
            },
        }]}
        policy = {"schema_version": "1.0", "amendments": [original, record]}
        accepted = "d" * 40

        def read(_root, arguments):
            revision, path = arguments[1].split(":", 1)
            self.assertEqual(revision, accepted)
            payload = registry if path == amendment.REGISTRY_PATH else policy
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())

        with mock.patch.object(amendment, "_run_git", side_effect=read), mock.patch.object(
            amendment, "_git_oid", return_value=TREE
        ):
            self.assertEqual(amendment._registered_bootstrap_policy(
                Path("."), HEAD, "SecPal/.github", 1053, 1055, PARENT,
                registration_sha=accepted,
            ), record)
            policy["amendments"][0]["authorization_id"] = "changed"
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError,
                "original governance registration changed",
            ):
                amendment._registered_bootstrap_policy(
                    Path("."), HEAD, "SecPal/.github", 1053, 1055, PARENT,
                    registration_sha=accepted,
                )

    def test_reviewed_ready_registration_preserves_material_feedback(self) -> None:
        value = authorization()
        value["delivery_issue"] = 1053
        value["pull_request"] = 1055
        value["governance_path_prefixes"] = amendment.REVIEWED_READY_PATH_PREFIXES
        value["human_authority_identity"] = amendment.REVIEWED_READY_AUTHORITY_IDENTITY
        value["authorization_id"] = "governance-amendment:SecPal/.github:1053:1055"
        reviewed = value["qualified_source"]
        reviewed["head_sha"] = HEAD
        reviewed["tree_sha"] = TREE
        reviewed["material_finding_ids"] = ["finding-thread"]
        reviewed["qualification_digest"] = authority.digest_json({
            "conversation_id": reviewed["verifier_conversation_id"],
            "workspace": reviewed["verifier_workspace"],
            "head_sha": HEAD, "tree_sha": TREE,
            "result": "PASS", "material_finding_ids": ["finding-thread"],
        })
        value["feedback"]["material_finding_ids"] = ["finding-thread"]
        observed = [
            {"sequence": 1, "kind": "PR_CREATED_DRAFT",
             "observed_at": "2026-09-18T10:00:00Z", "head_sha": HEAD,
             "reviewed_head_sha": None},
            {"sequence": 2, "kind": "DRAFT_TO_READY_OBSERVED",
             "observed_at": "2026-09-18T10:30:00Z", "head_sha": HEAD,
             "reviewed_head_sha": None},
            {"sequence": 3, "kind": "REVIEW_SUBMITTED",
             "observed_at": "2026-09-18T11:00:00Z", "head_sha": HEAD,
             "reviewed_head_sha": HEAD},
        ]
        value["observed_pre_enrollment_history"] = observed
        value["intended_state"] = authority.initial_state()
        value["intended_state"].update(
            unrestricted_review_count=1, draft=False, ready=True,
            ready_transition_count=1,
            ready_history=[{
                "sequence": 1, "transition_kind": "DRAFT_TO_READY",
                "observation_digest": authority.digest_json(observed[1]),
            }],
        )
        value["human_authorization_digest"] = authority.digest_json({
            "authority_identity": value["human_authority_identity"],
            "repository": value["repository"], "delivery_issue": 1053,
            "pull_request": 1055, "purpose": amendment.PURPOSE,
            "qualified_source_digest": reviewed["qualification_digest"],
            "accepted_main_sha": value["accepted_main_sha"],
            "decision": "APPROVED", "bounded_uses": 1,
        })
        value = reseal(value)
        first, second = self.patches()
        with first, second:
            verified = amendment.verify(value)
        self.assertEqual(
            verified.authorization["feedback"]["material_finding_ids"],
            ["finding-thread"],
        )
        for findings in ([], ["other-thread"],
                         ["finding-thread", "other-thread"],
                         ["finding-thread", "finding-thread"]):
            changed = copy.deepcopy(value)
            changed["feedback"]["material_finding_ids"] = findings
            changed = reseal(changed)
            with first, second:
                with self.assertRaises(amendment.GovernanceAmendmentError):
                    amendment.verify(changed)
        native = copy.deepcopy(value)
        native["observed_pre_enrollment_history"] = [
            item for item in native["observed_pre_enrollment_history"]
            if item["kind"] != "REVIEW_SUBMITTED"
        ]
        native = reseal(native)
        with first, second:
            with self.assertRaises(amendment.GovernanceAmendmentError):
                amendment.verify(native)

    def test_original_amendment_cannot_replace_budget_admission_with_review(self) -> None:
        value = authorization()
        value["observed_pre_enrollment_history"] = [
            history()[0],
            {
                "sequence": 2, "kind": "REVIEW_SUBMITTED",
                "observed_at": "2026-09-18T10:30:00Z",
                "head_sha": PARENT, "reviewed_head_sha": PARENT,
            },
            {**history()[1], "sequence": 3},
        ]
        value = reseal(value)
        first, second = self.patches()
        with first, second, self.assertRaises(
            amendment.GovernanceAmendmentError
        ):
            amendment.verify(value)

    def test_consumption_planner_has_one_safe_path_without_new_decision(self) -> None:
        self.assertEqual(
            amendment.consumption_plan(),
            {
                "schema_version": "1.0",
                "operation": "GOVERNANCE_AMENDMENT_CONSUMPTION",
                "merge_method": "SQUASH",
                "protected_ref_write": "GITHUB_PULL_REQUEST_MERGE",
                "provider_atomic_base_precondition": (
                    "STRICT_REQUIRED_STATUS_CHECKS"
                ),
                "direct_push": False,
                "force": False,
                "branch_protection_bypass": False,
                "decision_required": False,
            },
        )

    def test_reviewed_amendment_consumes_from_registration_tip(self) -> None:
        reviewed = authorization()
        reviewed["delivery_issue"] = 1053
        reviewed["pull_request"] = 1055
        reviewed["current_validation"]["accepted_main_sha"] = "d" * 40
        consumption = amendment._consumption_record(reviewed)
        self.assertEqual(
            consumption["accepted_main_sha"], reviewed["accepted_main_sha"]
        )
        self.assertEqual(consumption["resulting_parent_sha"], "d" * 40)
        original = authorization()
        self.assertEqual(
            amendment._consumption_record(original)["resulting_parent_sha"],
            original["accepted_main_sha"],
        )

    def test_reviewed_issuance_and_signatures_use_current_registration_trust(self) -> None:
        reviewed = reviewed_authorization()
        facts = {
            key: copy.deepcopy(value) for key, value in reviewed.items()
            if key not in {
                "root_authorization", "signer_identity", "signature",
                "authorization_digest",
            }
        }
        trust = SimpleNamespace(
            authority_signer_identities=frozenset({ROOT_SIGNER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
        )
        current = reviewed["current_validation"]["accepted_main_sha"]

        def current_trust(_repository, main):
            self.assertEqual(main, current)
            return trust

        def role_signer(_trust, identities, _label, **_kwargs):
            return ((ROOT_SIGNER, root_signer)
                    if identities == trust.authority_signer_identities
                    else (SIGNER, signer))

        with mock.patch.object(
            amendment, "produce_observation", return_value=facts,
        ), mock.patch.object(
            amendment, "_accepted_trust_policy", side_effect=current_trust,
        ), mock.patch.object(
            amendment.execution, "_policy_role_signer", side_effect=role_signer,
        ), mock.patch.object(
            authority, "_policy_signature_verifier", return_value=signature_verifier,
        ):
            sealed = amendment.authenticate_issuance(
                "SecPal/.github", 1053, observation_inputs(reviewed),
            )
            issued = amendment.issue(sealed)
            amendment.verify(issued)

    def test_reviewed_registration_tip_revocation_rejects_old_signers(self) -> None:
        reviewed = reviewed_authorization()
        current = reviewed["current_validation"]["accepted_main_sha"]
        historical = reviewed["accepted_main_sha"]

        def policy(_repository, main):
            if main == historical:
                return SimpleNamespace(
                    authority_signer_identities=frozenset({ROOT_SIGNER}),
                    legacy_adoption_signer_identities=frozenset({SIGNER}),
                )
            self.assertEqual(main, current)
            return SimpleNamespace(
                authority_signer_identities=frozenset(),
                legacy_adoption_signer_identities=frozenset(),
            )

        with mock.patch.object(
            amendment, "_accepted_trust_policy", side_effect=policy,
        ), mock.patch.object(
            authority, "_policy_signature_verifier", return_value=signature_verifier,
        ), self.assertRaises(amendment.GovernanceAmendmentError):
            amendment.verify(reviewed)

    @contextmanager
    def reviewed_live_observation(self):
        """Historical PR metadata and maintained registration are distinct."""
        value = reviewed_authorization()
        historical = value["accepted_main_sha"]
        current = value["current_validation"]["accepted_main_sha"]
        value["ordered_parent_shas"] = [historical]
        value["qualified_source"]["ordered_parent_shas"] = [historical]
        value = reseal(value)
        record = {
            key: copy.deepcopy(value[key]) for key in (
                "repository", "delivery_issue", "pull_request", "qualified_source",
                "accepted_main_sha", "concepts", "human_authority_identity",
                "human_authorization_digest", "authorization_id", "intended_state",
                "feedback", "observed_pre_enrollment_history",
            )
        }
        record.update(source_signer_identity=SOURCE,
                      allowed_path_prefixes=amendment.REVIEWED_READY_PATH_PREFIXES)
        policy = {"schema_version": "1.0", "amendments": [proposed_policy(), record]}
        registry = {"schema_version": "1.0", "repositories": [{
            "repository": "SecPal/.github", "governance_amendment_policy": {
                "path": amendment.POLICY_PATH, "kind": amendment.KIND,
                "purpose": amendment.PURPOSE,
            },
        }]}
        pull = {
            "number": 1055, "state": "open", "draft": False, "merged": False,
            "head_repository": "SecPal/.github", "head_sha": HEAD,
            "base_sha": historical, "base_ref": "main",
            "base_repository": "SecPal/.github",
        }
        trust = SimpleNamespace(
            publication_remote_url="maintained-remote",
            authority_signer_identities=frozenset({ROOT_SIGNER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
        )
        base_trust = SimpleNamespace(publication_remote_url="maintained-remote")

        def git(_root, arguments):
            if arguments[0] == "merge-base":
                self.assertEqual(arguments, [
                    "merge-base", "--is-ancestor", historical, current,
                ])
                return SimpleNamespace(returncode=0, stdout=b"")
            if arguments[:3] == ["show", "-s", "--format=%P"]:
                return SimpleNamespace(returncode=0, stdout=historical.encode())
            self.assertEqual(arguments[0], "show")
            revision, path = arguments[1].split(":", 1)
            self.assertEqual(revision, current)
            document = registry if path == amendment.REGISTRY_PATH else policy
            return SimpleNamespace(returncode=0, stdout=json.dumps(document).encode())

        def accepted_trust(_repository, main):
            self.assertIn(main, (historical, current))
            return base_trust if main == historical else trust

        def role_signer(selected, identities, _label, **_kwargs):
            self.assertIs(selected, trust)
            return ((ROOT_SIGNER, root_signer)
                    if identities == trust.authority_signer_identities
                    else (SIGNER, signer))

        patches = {
            "_accepted_trust_policy": {"side_effect": accepted_trust},
            "_observe_remote_main": {"return_value": current},
            "_run_git": {"side_effect": git},
            "_live_pull_request": {"return_value": pull},
            "_live_issue": {"return_value": {"number": 1053, "state": "open"}},
            "_git_oid": {"return_value": TREE},
            "_git_changed_files": {"return_value": value["changed_files"]},
            "_source_commit_range": {"return_value": [HEAD]},
            "_verify_commit_against_accepted_trust": {},
            "_live_ci": {"return_value": value["natural_ci"]},
            "_live_ready_ci": {"return_value": value["natural_ci"]},
            "_bound_current_validation": {"return_value": value["current_validation"]},
            "_observe_historical_absence": {"return_value": (
                value["historical_evidence"], value["historical_absence_proof"],
            )},
            "_live_feedback": {"return_value": value["feedback"]},
            "_live_reviewed_ready_history": {
                "return_value": value["observed_pre_enrollment_history"],
            },
        }
        with ExitStack() as stack:
            calls = {name: stack.enter_context(mock.patch.object(
                amendment, name, **options,
            )) for name, options in patches.items()}
            stack.enter_context(mock.patch.object(
                amendment.execution, "_policy_role_signer", side_effect=role_signer,
            ))
            stack.enter_context(mock.patch.object(
                authority, "_policy_signature_verifier", return_value=signature_verifier,
            ))
            yield value, pull, policy, calls, trust

    def test_reviewed_historical_pr_base_issues_with_current_registration_and_v4_root(self):
        with self.reviewed_live_observation() as (value, pull, _policy, calls, trust):
            historical = value["accepted_main_sha"]
            current = value["current_validation"]["accepted_main_sha"]
            self.assertNotEqual(historical, current)
            self.assertEqual(pull["base_sha"], historical)
            sealed = amendment.authenticate_issuance(
                "SecPal/.github", 1053, observation_inputs(value),
            )
            issued = amendment.issue(sealed)
            self.assertTrue(amendment.is_verified(amendment.verify(issued)))
            self.assertEqual(issued["accepted_main_sha"], historical)
            self.assertEqual(amendment._consumption_base(issued), current)
            calls["_verify_commit_against_accepted_trust"].assert_called_with(
                amendment.ROOT.resolve(), HEAD, SOURCE, trust,
            )
            calls["_bound_current_validation"].assert_called_with(
                amendment.ROOT.resolve(), "SecPal/.github", current,
                target_head_sha=HEAD, target_tree_sha=TREE,
            )
            calls["_live_ci"].assert_called_with(
                "SecPal/.github", HEAD, current, delivery_issue=1053,
            )
            calls["_live_ready_ci"].assert_called_with(
                "SecPal/.github", 1055, HEAD, historical, value["natural_ci"],
            )
            root, bundle = self.zero_receipt_root(amendment_authorization=issued)
            self.assertEqual(authority.recovered_adoption_root_historical_evidence(
                root, bundle, None,
            ), amendment.historical_evidence())
            self.assertTrue(root.state["ready"])
            self.assertIsNone(root.validation_receipt_digest)

    def test_reviewed_pr_base_platform_fact_can_advance_independently(self):
        with self.reviewed_live_observation() as (value, pull, _policy, calls, _trust):
            historical = value["accepted_main_sha"]
            current = value["current_validation"]["accepted_main_sha"]
            pull["base_sha"] = current
            issued = amendment.issue(amendment.authenticate_issuance(
                "SecPal/.github", 1053, observation_inputs(value),
            ))
            self.assertEqual(pull["base_sha"], current)
            self.assertEqual(issued["accepted_main_sha"], historical)
            self.assertEqual(amendment._consumption_base(issued), current)
            calls["_live_ready_ci"].assert_called_with(
                "SecPal/.github", 1055, HEAD, historical, value["natural_ci"],
            )

    def test_reviewed_pr_base_platform_fact_rejects_malformed_metadata(self):
        for observed in (None, True, "not-a-sha", "f" * 39):
            with self.subTest(observed=observed), self.reviewed_live_observation() as fixture:
                value, pull, _policy, _calls, _trust = fixture
                pull["base_sha"] = observed
                with self.assertRaises(amendment.GovernanceAmendmentError):
                    amendment.authenticate_issuance(
                        "SecPal/.github", 1053, observation_inputs(value),
                    )

    def test_reviewed_historical_pr_base_rejects_identity_and_authority_substitution(self):
        for field, replacement in (
            ("base_ref", "other"), ("base_repository", "other/repository"),
            ("head_repository", "other/repository"), ("number", 1056),
            ("head_sha", "f" * 40), ("draft", True), ("state", "closed"),
            ("merged", True),
        ):
            with self.subTest(field=field), self.reviewed_live_observation() as fixture:
                value, pull, _policy, _calls, _trust = fixture
                pull[field] = replacement
                with self.assertRaises(amendment.GovernanceAmendmentError):
                    amendment.authenticate_issuance(
                        "SecPal/.github", 1053, observation_inputs(value),
                    )
        for failure in ("issue", "unavailable", "ancestry", "registration", "tree",
                        "caller main", "stale registration"):
            with self.subTest(failure=failure), self.reviewed_live_observation() as fixture:
                value, _pull, policy, calls, _trust = fixture
                if failure == "issue":
                    calls["_live_issue"].return_value = {"number": 1054, "state": "open"}
                elif failure == "unavailable":
                    calls["_observe_remote_main"].side_effect = amendment.GovernanceAmendmentError(
                        "protected main cannot be authenticated"
                    )
                elif failure == "ancestry":
                    calls["_run_git"].side_effect = None
                    calls["_run_git"].return_value = SimpleNamespace(returncode=1)
                elif failure == "registration":
                    policy["amendments"] = policy["amendments"][:1]
                elif failure == "tree":
                    calls["_git_oid"].return_value = "f" * 40
                elif failure == "caller main":
                    value["current_main_sha"] = "f" * 40
                else:
                    policy["amendments"][1]["accepted_main_sha"] = "f" * 40
                inputs = observation_inputs(value)
                if failure == "caller main":
                    inputs["current_main_sha"] = value["current_main_sha"]
                with self.assertRaises(amendment.GovernanceAmendmentError):
                    amendment.authenticate_issuance("SecPal/.github", 1053, inputs)

    def test_reviewed_registration_change_rejects_issuance_and_consumption(self):
        with self.reviewed_live_observation() as (value, _pull, _policy, calls, _trust):
            sealed = amendment.authenticate_issuance(
                "SecPal/.github", 1053, observation_inputs(value),
            )
            calls["_bound_current_validation"].return_value = {
                **value["current_validation"], "accepted_main_sha": "f" * 40,
            }
            with self.assertRaisesRegex(amendment.GovernanceAmendmentError,
                                        "facts changed before signing"):
                amendment.issue(sealed)
            calls["_bound_current_validation"].return_value = value["current_validation"]
            verified = amendment.verify(amendment.issue(sealed))
            calls["_observe_remote_main"].side_effect = [
                value["current_validation"]["accepted_main_sha"], "f" * 40,
            ]
            with self.assertRaisesRegex(amendment.GovernanceAmendmentError,
                                        "protected main changed before amendment consumption"):
                amendment._authenticate_execution(
                    verified, amendment.ROOT.resolve(), "maintained-remote",
                )

    def patches(self, trust: object | None = None):
        trust = trust or SimpleNamespace(
            authority_signer_identities=frozenset({ROOT_SIGNER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
            signers={},
        )
        return (
            mock.patch.object(
                amendment, "_accepted_trust_policy",
                return_value=trust,
            ),
            mock.patch.object(
                authority, "_policy_signature_verifier",
                return_value=signature_verifier,
            ),
        )

    def zero_receipt_root(self, **scope):
        amendment_authorization = scope.get(
            "amendment_authorization", reviewed_authorization(),
        )
        evidence = authority._assemble_exact_state_adoption_evidence(
            repository=scope.get("repository", amendment_authorization["repository"]),
            delivery_issue=scope.get("delivery_issue", amendment_authorization["delivery_issue"]),
            pull_request=scope.get("pull_request", amendment_authorization["pull_request"]),
            head_sha=HEAD, tree_sha=TREE, pull_request_state="OPEN",
            commit_signature_evidence_digest="1" * 64,
            validation_receipt_digest=None,
            source_validation_evidence_digest=None,
            adoption_source_evidence_digest=amendment_authorization[
                "authorization_digest"
            ],
            observed_pre_enrollment_history=amendment_authorization[
                "observed_pre_enrollment_history"
            ],
            intended_state=amendment_authorization["intended_state"],
            adoption_timestamp="2026-09-18T12:00:00Z",
            supporting_evidence_digests=[
                amendment_authorization["authorization_digest"]
            ],
            governance_amendment_authorization=amendment_authorization,
        )
        adoption_authorization = authority.create_exact_state_adoption_authorization(
            adoption_evidence=evidence, authorization_id="fixture:zero-root",
            bounded_uses=1, signer_identity=SIGNER, signer=signer,
        )
        proof = authority.create_exact_state_adoption_proof(
            adoption_evidence=evidence, authorization=adoption_authorization,
            signer_identity=SIGNER, signer=signer,
        )
        return (
            authority.verify_exact_state_adoption_proof(proof),
            json.loads(authority.serialize_exact_state_adoption_evidence(
                exact_state_adoption_proof=proof,
            )),
        )

    def test_v4_governance_amendment_zero_receipt_root(self) -> None:
        first, second = self.patches()
        with first, second:
            current, bundle = self.zero_receipt_root()
            historical = authority.recovered_adoption_root_historical_evidence(
                current, bundle, None,
            )
        self.assertEqual(historical, amendment.historical_evidence())
        self.assertTrue(current.state["ready"])
        self.assertEqual(current.state["ready_transition_count"], 1)
        self.assertIsNone(current.validation_receipt_digest)
        self.assertIsNone(current.source_validation_evidence_digest)

    def test_v4_zero_receipt_root_rejects_successors_and_replay(self) -> None:
        first, second = self.patches()
        with first, second:
            current, bundle = self.zero_receipt_root()
            mutations = {
                "caller-selected mode": lambda b: b.update(root_mode="v4"),
                "transition suffix": lambda b: b["transition_authorizations"].append({}),
                "authority suffix": lambda b: b["authority_chain"].append({}),
                "wrong root kind": lambda b: b.update(kind="ordinary"),
                "wrong enrollment": lambda b: b.update(enrollment_mode="NATIVE"),
                "wrong root version": lambda b: b.update(schema_version="4.0"),
                "wrong root domain": lambda b: b.update(domain="candidate-local"),
            }
            for label, mutate in mutations.items():
                changed = copy.deepcopy(bundle)
                mutate(changed)
                with self.subTest(label=label), self.assertRaises(
                    authority.LifecycleAuthorityError
                ):
                    authority.recovered_adoption_root_historical_evidence(
                        current, changed, None,
                    )
            for field, value in {
                "repository": "example/other", "delivery_issue": 999,
                "pull_request": 998, "head_sha": "e" * 40,
                "tree_sha": "f" * 40, "lifecycle_id": "other-lifecycle",
                "authority_digest": "7" * 64,
                "validation_receipt_digest": "8" * 64,
                "source_validation_evidence_digest": "9" * 64,
                "state": authority.initial_state(),
                "historical_proof_mode": "native",
            }.items():
                with self.subTest(field=field), self.assertRaises(
                    authority.LifecycleAuthorityError
                ):
                    authority.recovered_adoption_root_historical_evidence(
                        replace(current, **{field: value}), bundle, None,
                    )
            with self.assertRaises(authority.LifecycleAuthorityError):
                authority.recovered_adoption_root_historical_evidence(
                    current, bundle, "e" * 40,
                )

    def test_v4_zero_receipt_root_rejects_amendment_cross_delivery_replay(self) -> None:
        first, second = self.patches()
        with first, second:
            for field, value in {"delivery_issue": 999, "pull_request": 998}.items():
                with self.subTest(field=field):
                    current, bundle = self.zero_receipt_root(**{field: value})
                    with self.assertRaises(authority.LifecycleAuthorityError):
                        authority.recovered_adoption_root_historical_evidence(
                            current, bundle, None,
                        )

    def test_v4_zero_receipt_root_requires_independent_exact_proof(self) -> None:
        first, second = self.patches()
        with first, second:
            current, bundle = self.zero_receipt_root()
            mutations = {
                "malformed version": lambda p: p.update(proof_version="4"),
                "unverified amendment": lambda p: p[
                    "governance_amendment_authorization"
                ]["signature"].update(value="substituted"),
                "missing amendment": lambda p: p.pop("governance_amendment_authorization"),
                "substituted intended state": lambda p: p["intended_state"].update(ready=False),
                "PRESENT": lambda p: p["historical_evidence"].update(state="PRESENT"),
                "UNAVAILABLE": lambda p: p["historical_evidence"].update(state="UNAVAILABLE"),
                "reconstructed": lambda p: p["historical_evidence"].update(bytes_reconstructed=True),
            }
            for field in (
                "validation_receipt_digest", "source_validation_evidence_digest",
                "final_attestation_digest",
            ):
                mutations[field] = lambda p, field=field: p["historical_evidence"].update(
                    **{field: "8" * 64}
                )
            for label, mutate in mutations.items():
                changed = copy.deepcopy(bundle)
                mutate(changed["exact_state_adoption_proof"])
                with self.subTest(label=label), mock.patch.object(
                    authority, "verify_exact_state_adoption_proof",
                    wraps=authority.verify_exact_state_adoption_proof,
                ) as verify, self.assertRaises(authority.LifecycleAuthorityError):
                    authority.recovered_adoption_root_historical_evidence(
                        current, changed, None,
                    )
                verify.assert_called_once_with(changed["exact_state_adoption_proof"])
            with mock.patch.object(
                amendment, "_accepted_trust_policy",
                side_effect=amendment.GovernanceAmendmentError("candidate-local authority"),
            ), self.assertRaises(authority.LifecycleAuthorityError):
                authority.recovered_adoption_root_historical_evidence(
                    current, bundle, None,
                )

    def test_v4_current_safety_receipt_is_not_historical_evidence(self) -> None:
        first, second = self.patches()
        with first, second:
            current, bundle = self.zero_receipt_root()
            reviewed = fast_path.StableFeedbackState(
                repository=current.repository, pull_request_number=current.pull_request,
                head_sha=HEAD, base_ref="main", base_sha=PARENT, pr_state="OPEN",
                feedback={"pull_request_reactions": [], "reviews": [],
                          "conversation_comments": [], "threads": []},
            )
            registry = {"manual_gates": [], "validation": [],
                        "limits": {"maximum_items": 10000}}
            receipt = fast_path.create_validation_receipt(
                repository=current.repository, head_sha=HEAD, validated_tree_sha=TREE,
                registry=registry, command_set=[], successful_result=True,
                reviewed_state=reviewed, manual_gate_evidence=[],
            )
            safety = fast_path.derive_ready_source_recovery_safety_facts(
                tooling_authority_main="9" * 40, repository=current.repository,
                pull_request_number=current.pull_request, head_sha=HEAD, tree_sha=TREE,
                parent_shas=[PARENT], expected_base_ref="main", expected_base_sha=PARENT,
                reviewed_state=reviewed, review_decision="NONE", feedback_findings=[],
                fresh_validation_receipt=receipt, registry=registry, command_set=[],
            )
            scope = dict(
                current_lifecycle=current, current_publication_oid="3" * 40,
                current_publication_digest="4" * 64,
                current_lifecycle_evidence=bundle, predecessor_publication_oid=None,
            )
            document = authority._sign_ready_source_recovery_authorization(
                **scope, recovery_safety_facts=safety,
                commit_signature_evidence={
                    "oid": HEAD, "source": "USER", "signer_identity": SOURCE,
                    "local_signature": {"verified": True, "state": "valid", "format": "ssh"},
                    "github_verification": {"verified": True, "reason": "valid"},
                },
                historical_validation_receipt_digest=None,
                historical_final_attestation_digest=None,
                historical_evidence_loss_proof_digest="7" * 64,
                authorization_id="fixture:current-safety", bounded_uses=1,
                expected_commit_signer={"kind": "SSH_PRINCIPAL", "identity": SOURCE},
                signer_identity=SOURCE, signer=root_signer,
            )
            authority.verify_ready_source_recovery_authorization(document, **scope)
            self.assertEqual(document["fresh_validation_receipt_digest"], receipt["receipt_digest"])
            self.assertIsNone(document["historical_validation_receipt_digest"])
            self.assertIsNone(document["historical_final_attestation_digest"])
            self.assertEqual(
                authority.recovered_adoption_root_historical_evidence(current, bundle, None),
                amendment.historical_evidence(),
            )

    def hermetic_repository(
        self, directory: str, *, attacker_intermediate: bool,
        base_receipt: bool = False,
    ) -> dict[str, object]:
        root, remote = Path(directory) / "work", Path(directory) / "remote.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
        subprocess.run(["git", "init", "--quiet", "-b", "main", str(root)], check=True)

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", "-C", str(root), *args], check=True,
                stdout=subprocess.PIPE, text=True,
            ).stdout.strip()

        git("config", "user.name", "SecPal Test")
        git("config", "user.email", "test@secpal.invalid")
        trusted, attacker = Path(directory) / "trusted", Path(directory) / "attacker"
        for key in (trusted, attacker):
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                check=True,
            )
        allowed = Path(directory) / "allowed-signers"
        allowed.write_text(
            "".join(
                f"{SOURCE} {key.with_suffix('.pub').read_text()}"
                for key in (trusted, attacker)
            ),
            encoding="utf-8",
        )
        git("config", "gpg.format", "ssh")
        git("config", "user.signingkey", str(trusted))
        git("config", "gpg.ssh.allowedSignersFile", str(allowed))
        git("config", "commit.gpgsign", "true")
        path = root / "scripts" / "secpal_pr_review" / "governance_amendment.py"
        path.parent.mkdir(parents=True)
        path.write_text("base\n", encoding="utf-8")
        git("add", ".")
        base_message = "base"
        if base_receipt:
            base_message += "\n\nSecPal-Validation-Receipt: " + "9" * 64
        git("commit", "-S", "-m", base_message)
        base = git("rev-parse", "HEAD")
        git("remote", "add", "origin", str(remote))
        git("push", "origin", "HEAD:main")
        git("switch", "-c", "candidate")
        source_oids: list[str] = []
        if attacker_intermediate:
            git("config", "user.signingkey", str(attacker))
            path.write_text("attacker intermediate\n", encoding="utf-8")
            git("commit", "-S", "-am", "attacker intermediate")
            source_oids.append(git("rev-parse", "HEAD"))
            git("config", "user.signingkey", str(trusted))
        path.write_text("trusted tip\n", encoding="utf-8")
        git("commit", "-S", "-am", "trusted tip")
        head = git("rev-parse", "HEAD")
        source_oids.append(head)
        return {
            "root": root, "remote": remote, "git": git,
            "path": path, "base": base, "head": head,
            "tree": git("rev-parse", "HEAD^{tree}"),
            "blob": git("rev-parse", f"HEAD:{path.relative_to(root)}"),
            "trusted": trusted, "attacker": attacker,
            "source_oids": source_oids,
        }

    def test_change_digest_matches_independent_canonical_oracle(self) -> None:
        value = authorization()
        facts = {
            key: value[key] for key in (
                "repository", "delivery_issue", "pull_request", "head_sha",
                "tree_sha", "ordered_parent_shas", "accepted_main_sha",
                "changed_files",
            )
        }
        oracle = hashlib.sha256(
            json.dumps(
                facts, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8") + b"\n"
        ).hexdigest()
        self.assertEqual(value["change_digest"], oracle)
        without_newline = hashlib.sha256(
            json.dumps(
                facts, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(value["change_digest"], without_newline)
        reordered = copy.deepcopy(facts)
        reordered["changed_files"].reverse()
        self.assertNotEqual(
            amendment.change_digest(**reordered), value["change_digest"]
        )

    def test_canonical_issue_consume_and_protected_main_read_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, remote = Path(directory) / "work", Path(directory) / "remote.git"
            subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
            subprocess.run(["git", "init", "--quiet", "-b", "main", str(root)], check=True)
            def git(*args: str) -> str:
                return subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
            git("config", "user.name", "SecPal Test")
            git("config", "user.email", "test@secpal.invalid")
            key = Path(directory) / "key"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
            allowed = Path(directory) / "allowed-signers"
            allowed.write_text(f"{SOURCE} {key.with_suffix('.pub').read_text()}")
            git("config", "gpg.format", "ssh"); git("config", "user.signingkey", str(key)); git("config", "gpg.ssh.allowedSignersFile", str(allowed)); git("config", "commit.gpgsign", "true")
            path = root / "base.txt"
            path.write_text("accepted base\n")
            git("add", "."); git("commit", "-S", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote)); git("push", "origin", "HEAD:main")
            git("switch", "-c", "candidate")
            policy = copy.deepcopy(proposed_policy())
            policy["accepted_main_sha"] = base
            policy["human_authorization_digest"] = authority.digest_json({
                "authority_identity": policy["human_authority_identity"],
                "repository": "SecPal/.github", "delivery_issue": 960,
                "pull_request": 961, "purpose": amendment.PURPOSE,
                "qualified_source_digest": policy["qualified_source"]["qualification_digest"],
                "accepted_main_sha": base, "decision": "APPROVED", "bounded_uses": 1,
            })
            midpoint = len(FULL_CANDIDATE_PATHS) // 2
            for sequence, paths in enumerate(
                (FULL_CANDIDATE_PATHS[:midpoint], FULL_CANDIDATE_PATHS[midpoint:]),
                start=1,
            ):
                for relative in paths:
                    candidate = root / relative
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    if relative == amendment.POLICY_PATH:
                        candidate.write_text(json.dumps({
                            "schema_version": "1.0", "amendments": [policy],
                        }), encoding="utf-8")
                    elif relative == amendment.REGISTRY_PATH:
                        candidate.write_text(json.dumps({
                            "schema_version": "1.0",
                            "repositories": [{
                                "repository": "SecPal/.github",
                                "governance_amendment_policy": {
                                    "path": amendment.POLICY_PATH,
                                    "kind": amendment.KIND,
                                    "purpose": amendment.PURPOSE,
                                },
                            }],
                        }), encoding="utf-8")
                    else:
                        candidate.write_text(f"candidate {relative}\n", encoding="utf-8")
                git("add", ".")
                git("commit", "-S", "-m", f"amendment part {sequence}")
            head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            source_oids = git(
                "rev-list", "--reverse", "--topo-order", f"{base}..{head}"
            ).splitlines()
            changed = []
            for relative in sorted(FULL_CANDIDATE_PATHS):
                mode, kind, blob = git("ls-tree", head, "--", relative).split(None, 2)[0:3]
                self.assertEqual(kind, "blob")
                changed.append({
                    "path": relative, "blob_oid": blob.split("\t", 1)[0],
                    "mode": mode,
                })
            raw = authorization(
                head=head, tree=tree, parent=source_oids[-2],
                accepted_main=base, changed=changed,
                source_oids=source_oids, policy=policy,
            )
            trusted_signer = authority.TrustedSigner(
                SOURCE,
                (key.with_suffix(".pub").read_text().strip(),),
                (),
            )
            trust = SimpleNamespace(
                authority_signer_identities=frozenset({ROOT_SIGNER}),
                legacy_adoption_signer_identities=frozenset({SIGNER}),
                signers={SOURCE: trusted_signer},
                publication_remote_url=str(remote),
            )
            checks = [{
                "name": "governance", "status": "completed",
                "conclusion": "success", "head_sha": head,
            }]
            statuses: list[dict[str, object]] = []
            ready_events, ready_runs = ready_ci_fixtures(head, base)
            threads: list[dict[str, object]] = []
            reviews = [{
                "id": "R_fixture", "body": "",
                "state": "COMMENTED", "commit": {"oid": head},
                "author": {"login": "review-bot"},
            }]
            pull = {
                "number": 961, "state": "open", "draft": False,
                "merged": False, "mergeable": True,
                "mergeable_state": "clean",
                "head": {"sha": head, "repo": {"full_name": "SecPal/.github"}},
                "base": {"sha": base, "ref": "main", "repo": {"full_name": "SecPal/.github"}},
            }
            squash: dict[str, str] = {}
            def github(arguments: list[str]):
                joined = " ".join(arguments)
                if "pulls/961/merge" in joined:
                    fields = {
                        item.split("=", 1)[0]: item.split("=", 1)[1]
                        for item in arguments if "=" in item
                    }
                    self.assertEqual(fields["sha"], head)
                    self.assertEqual(fields["merge_method"], "squash")
                    self.assertNotIn("force", joined)
                    rendered = (
                        fields["commit_title"] + "\n\n"
                        + fields["commit_message"]
                    )
                    created = subprocess.run(
                        ["git", "-C", str(root), "commit-tree", tree, "-p", base],
                        input=rendered + "\n", text=True,
                        check=True, stdout=subprocess.PIPE,
                    ).stdout.strip()
                    git("push", "origin", f"{created}:main")
                    squash.update(oid=created, message=rendered)
                    value = {"merged": True, "sha": created}
                elif squash and f"commits/{squash['oid']}" in joined:
                    value = {
                        "sha": squash["oid"],
                        "parents": [{"sha": base}],
                        "commit": {
                            "tree": {"sha": tree},
                            "message": squash["message"],
                            "verification": {"verified": True, "reason": "valid"},
                        },
                    }
                elif "pulls/961" in joined:
                    value = pull
                elif "issues/960" in joined:
                    value = {"number": 960, "state": "open"}
                elif "issues/961/events" in joined:
                    value = ready_events
                elif "actions/runs" in joined:
                    value = {
                        "total_count": len(ready_runs),
                        "workflow_runs": ready_runs,
                    }
                elif "check-runs" in joined:
                    value = {"total_count": len(checks), "check_runs": checks}
                elif "/status" in joined:
                    value = {
                        "sha": head, "state": "success",
                        "total_count": len(statuses),
                        "statuses": statuses,
                    }
                elif "graphql" in arguments:
                    value = feedback_response(arguments, head, threads, reviews)
                else:
                    raise AssertionError(arguments)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(value).encode(), b""
                )

            first, second = self.patches(trust)
            signer_factory = mock.Mock()
            def role_signer(_trust, identities, _label, **_kwargs):
                if identities == trust.authority_signer_identities:
                    return ROOT_SIGNER, root_signer
                return SIGNER, signer
            signer_factory.side_effect = role_signer

            signature_policy = {
                "accepted_formats": ["ssh"],
                "require_github_verified": True,
            }
            required_policy = {
                "strict": True,
                "checks": [{"context": "governance", "app_id": None}],
            }
            with mock.patch.object(amendment, "ROOT", root), mock.patch.object(amendment.publication, "_run_gh", side_effect=github), mock.patch.object(authority, "_load_delivery_signature_policy", return_value=signature_policy), first, second, mock.patch.object(amendment.execution, "_policy_role_signer", signer_factory), mock.patch.object(amendment, "_live_required_check_policy", return_value=required_policy), mock.patch.object(amendment, "_bound_current_validation", return_value=raw["current_validation"]), mock.patch.object(amendment, "_observe_historical_absence", return_value=(raw["historical_evidence"], raw["historical_absence_proof"])):
                inputs = observation_inputs(raw)
                pull["draft"] = True
                with self.assertRaisesRegex(
                    amendment.GovernanceAmendmentError,
                    "delivery identity or state changed",
                ):
                    authority.authenticate_governance_amendment_issuance(
                        "SecPal/.github", 960, inputs
                    )
                pull["draft"] = False
                saved_ready_runs = list(ready_runs)
                ready_runs.clear()
                with self.assertRaisesRegex(
                    amendment.GovernanceAmendmentError,
                    "Ready CI is not terminal and passing",
                ):
                    authority.authenticate_governance_amendment_issuance(
                        "SecPal/.github", 960, inputs
                    )
                ready_runs.extend(saved_ready_runs)
                authenticated = authority.authenticate_governance_amendment_issuance("SecPal/.github", 960, inputs)
                observed = authenticated.facts
                self.assertEqual(
                    [item["path"] for item in observed["changed_files"]],
                    sorted(FULL_CANDIDATE_PATHS),
                )
                oracle_facts = {
                    key: observed[key] for key in (
                        "repository", "delivery_issue", "pull_request",
                        "head_sha", "tree_sha", "ordered_parent_shas",
                        "accepted_main_sha", "changed_files",
                    )
                }
                oracle = hashlib.sha256(
                    json.dumps(
                        oracle_facts, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False,
                    ).encode("utf-8") + b"\n"
                ).hexdigest()
                self.assertEqual(observed["change_digest"], oracle)
                self.assertEqual(
                    [item["oid"] for item in observed["source_commits"]],
                    source_oids,
                )
                self.assertEqual(
                    observed["source_signature"][
                        "range_signature_evidence_digest"
                    ],
                    amendment.source_signature_binding_digest(
                        observed["source_commits"], base
                    ),
                )
                issued = authority.issue_governance_amendment_authorization(authenticated)
                amendment.verify(issued)
                head_evidence = {
                    "oid": head, "source": "USER",
                    "local_signature": {
                        "verified": True, "state": "valid", "format": "ssh",
                    },
                    "github_verification": {
                        "verified": True, "reason": "valid",
                    },
                }
                changed_head = copy.deepcopy(head_evidence)
                changed_head["oid"] = source_oids[-2]
                with self.assertRaisesRegex(
                    authority.LifecycleAuthorityError,
                    "changed identity",
                ):
                    authority.authenticate_exact_state_adoption_external_evidence(
                        repository="SecPal/.github", delivery_issue=960,
                        pull_request=961, head_sha=head, tree_sha=tree,
                        pull_request_state="OPEN",
                        commit_signature_evidence=changed_head,
                        validation_evidence=None,
                        observed_pre_enrollment_history=raw[
                            "observed_pre_enrollment_history"
                        ],
                        intended_state=raw["intended_state"],
                        governance_amendment_authorization=issued,
                    )
                external = authority.authenticate_exact_state_adoption_external_evidence(
                    repository="SecPal/.github", delivery_issue=960,
                    pull_request=961, head_sha=head, tree_sha=tree,
                    pull_request_state="OPEN",
                    commit_signature_evidence=head_evidence,
                    validation_evidence=None,
                    observed_pre_enrollment_history=raw[
                        "observed_pre_enrollment_history"
                    ],
                    intended_state=raw["intended_state"],
                    governance_amendment_authorization=issued,
                )
                adoption = authority.create_exact_state_adoption_evidence(
                    verified_external_evidence=external,
                    adoption_timestamp="2026-09-18T12:00:00Z",
                )
                self.assertEqual(adoption["proof_version"], "4.0")
                self.assertEqual(
                    authority.exact_state_adoption_historical_evidence(adoption),
                    amendment.historical_evidence(),
                )
                result = authority.execute_governance_amendment(issued)
                self.assertEqual(result["status"], "CONSUMED")
                self.assertEqual(git("ls-remote", str(remote), "refs/heads/main").split()[0], result["merge_commit_sha"])
                self.assertEqual(git("show", "-s", "--format=%P", result["merge_commit_sha"]).split(), [base])
                self.assertEqual(git("rev-parse", f"{result['merge_commit_sha']}^{{tree}}"), tree)
                accepted_message = git("show", "-s", "--format=%B", result["merge_commit_sha"])
                self.assertIn(issued["authorization_digest"], accepted_message)
                self.assertEqual(result["merge_method"], "SQUASH")
                for fabricated in ("lifecycle CURRENT", "Ready transition", "validation receipt"):
                    self.assertNotIn(fabricated, accepted_message)
                with self.assertRaisesRegex(
                    amendment.GovernanceAmendmentError,
                    "protected main changed",
                ):
                    authority.execute_governance_amendment(issued)
            self.assertEqual(signer_factory.call_count, 2)

    def test_exact_governance_tools_do_not_admit_nearby_scripts(self) -> None:
        for path in (
            ".github/workflows/quality.yml",
            "scripts/secpal-provider-fallback.py",
        ):
            entry = [{"path": path, "blob_oid": "a" * 40, "mode": "100644"}]
            self.assertEqual(
                amendment._changed_files(
                    entry, amendment.REVIEWED_READY_PATH_PREFIXES
                ), entry,
            )
            with self.assertRaises(amendment.GovernanceAmendmentError):
                amendment._changed_files(entry, amendment.GOVERNANCE_PATH_PREFIXES)
        exact = [
            {
                "path": "scripts/secpal-pr-review-actions.py",
                "blob_oid": "a" * 40, "mode": "100755",
            },
            {
                "path": "scripts/secpal-resolve-fixed-threads.py",
                "blob_oid": "b" * 40, "mode": "100755",
            },
            {
                "path": "scripts/sync-required-checks.sh",
                "blob_oid": "c" * 40, "mode": "100755",
            },
        ]
        self.assertEqual(
            amendment._changed_files(exact, amendment.GOVERNANCE_PATH_PREFIXES),
            exact,
        )
        for path in (
            "scripts/secpal-pr-review-actions-helper.py",
            "scripts/secpal-resolve-fixed-threads.py/child",
            "scripts/unrelated-governance.py",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "non-governance source"
            ):
                amendment._changed_files(
                    [{"path": path, "blob_oid": "c" * 40, "mode": "100644"}],
                    amendment.GOVERNANCE_PATH_PREFIXES,
                )

    def test_source_range_rejects_intermediate_signature_substitution(self) -> None:
        value = authorization(source_oids=["7" * 40, HEAD])
        value["source_commits"][0]["signature_evidence_digest"] = "0" * 64
        value["source_signature"]["range_signature_evidence_digest"] = (
            amendment.source_signature_binding_digest(
                value["source_commits"], value["accepted_main_sha"]
            )
        )
        value = reseal(value)
        first, second = self.patches()
        with first, second, self.assertRaises(
            amendment.GovernanceAmendmentError
        ):
            amendment.verify(value)

    def test_issuer_requires_exact_root_observation_and_sealed_input(self) -> None:
        value = authorization()
        unsigned = {
            key: copy.deepcopy(item) for key, item in value.items()
            if key not in {
                "root_authorization", "signer_identity", "signature",
                "authorization_digest",
            }
        }
        inputs = observation_inputs(value)
        unclosed = {**inputs, "caller_asserted_live_head": "9" * 40}
        with mock.patch.object(amendment, "produce_observation") as producer:
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "not closed"
            ):
                authority.authenticate_governance_amendment_issuance(
                    "SecPal/.github", 960, unclosed
                )
        producer.assert_not_called()
        with self.assertRaisesRegex(
            amendment.GovernanceAmendmentError, "canonical authenticated"
        ):
            authority.issue_governance_amendment_authorization(unsigned)

        invalid = copy.deepcopy(unsigned)
        invalid["changed_files"].append({
            "path": "src/runtime.py", "blob_oid": "f" * 40,
            "mode": "100644",
        })
        root_signature = mock.Mock(side_effect=root_signer)
        legacy_signature = mock.Mock(side_effect=signer)
        trust = SimpleNamespace(
            authority_signer_identities=frozenset({ROOT_SIGNER}),
            legacy_adoption_signer_identities=frozenset({SIGNER}),
        )

        def role_signer(_trust, identities, _label, **_kwargs):
            if identities == trust.authority_signer_identities:
                return ROOT_SIGNER, root_signature
            return SIGNER, legacy_signature

        with mock.patch.object(
            amendment, "produce_observation", return_value=invalid
        ), mock.patch.object(
            amendment, "_accepted_trust_policy", return_value=trust
        ), mock.patch.object(
            amendment.execution, "_policy_role_signer", side_effect=role_signer
        ):
            authenticated = authority.authenticate_governance_amendment_issuance(
                "SecPal/.github", 960, inputs
            )
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "non-governance source"
            ):
                authority.issue_governance_amendment_authorization(authenticated)
        root_signature.assert_not_called()
        legacy_signature.assert_not_called()

    def test_public_observation_producer_rebuilds_live_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.hermetic_repository(
                directory, attacker_intermediate=False
            )
            policy = copy.deepcopy(proposed_policy())
            policy["accepted_main_sha"] = repo["base"]
            policy["human_authorization_digest"] = authority.digest_json({
                "authority_identity": policy["human_authority_identity"],
                "repository": "SecPal/.github", "delivery_issue": 960,
                "pull_request": 961, "purpose": amendment.PURPOSE,
                "qualified_source_digest": policy["qualified_source"]["qualification_digest"],
                "accepted_main_sha": repo["base"], "decision": "APPROVED",
                "bounded_uses": 1,
            })
            raw = authorization(
                head=repo["head"], tree=repo["tree"], parent=repo["base"],
                accepted_main=repo["base"], changed=[{
                    "path": str(repo["path"].relative_to(repo["root"])),
                    "blob_oid": repo["blob"], "mode": "100644",
                }], source_oids=repo["source_oids"], policy=policy,
            )
            inputs = observation_inputs(raw)
            facts = {
                key: copy.deepcopy(item) for key, item in raw.items()
                if key not in {
                    "root_authorization", "signer_identity", "signature",
                    "authorization_digest",
                }
            }
            checks = [{
                "name": "governance", "status": "completed",
                "conclusion": "success", "head_sha": repo["head"],
            }]
            statuses: list[dict[str, object]] = []
            ready_events, ready_runs = ready_ci_fixtures(
                repo["head"], repo["base"]
            )
            source_ci = {
                "head_sha": repo["head"],
                "workflow_identity": amendment.SOURCE_CI_VERSION,
                "result": "PASS",
                "evidence_digest": authority.digest_json({
                    "checks": checks, "statuses": statuses,
                    "required_check_policy": {
                        "strict": True,
                        "checks": [{"context": "governance", "app_id": None}],
                    },
                }),
            }
            ready_authority = {
                "operation": "DRAFT_TO_READY", "actor": "aroviqen",
                "event_id": ready_events[0]["id"],
                "head_sha": repo["head"],
                "accepted_main_sha": repo["base"],
                "source_ci_evidence_digest": source_ci["evidence_digest"],
            }
            facts["natural_ci"] = {
                "head_sha": repo["head"],
                "workflow_identity": amendment.LIVE_OBSERVATION_VERSION,
                "result": "PASS",
                "evidence_digest": authority.digest_json({
                    "source_ci_evidence_digest": source_ci["evidence_digest"],
                    "ready_event": {
                        "id": ready_events[0]["id"],
                        "event": ready_events[0]["event"],
                        "created_at": ready_events[0]["created_at"],
                        "actor": ready_events[0]["actor"]["login"],
                    },
                    "ready_workflow_run_history": sorted(
                        [{
                            key: run[key] for key in (
                                "id", "name", "event", "status", "conclusion",
                                "head_sha", "created_at", "run_started_at",
                            )
                        } | {"pull_requests": [{
                            "number": run["pull_requests"][0]["number"],
                            "head_sha": run["pull_requests"][0]["head"]["sha"],
                            "base_sha": run["pull_requests"][0]["base"]["sha"],
                        }]} for run in ready_runs],
                        key=lambda run: (
                            run["name"], run["created_at"], run["id"]
                        ),
                    ),
                    "ready_workflow_runs": sorted(
                        [{
                            key: run[key] for key in (
                                "id", "name", "event", "status", "conclusion",
                                "head_sha", "created_at", "run_started_at",
                            )
                        } | {"pull_requests": [{
                            "number": run["pull_requests"][0]["number"],
                            "head_sha": run["pull_requests"][0]["head"]["sha"],
                            "base_sha": run["pull_requests"][0]["base"]["sha"],
                        }]} for run in ready_runs],
                        key=lambda run: (
                            run["name"], run["created_at"], run["id"]
                        ),
                    ),
                    "ready_transition_authority": {
                        **ready_authority,
                        "authorization_digest": authority.digest_json(
                            ready_authority
                        ),
                    },
                }),
            }
            threads: list[dict[str, object]] = []
            reviews = [{
                "id": "R_fixture", "body": "",
                "state": "COMMENTED", "commit": {"oid": repo["head"]},
                "author": {"login": "review-bot"},
            }]
            facts["feedback"] = {
                "state_digest": authority.digest_json({
                    "head_sha": repo["head"], "pull_request": 961,
                }),
                "feedback_digest": authority.digest_json({
                    "threads": threads, "comments": [], "reviews": reviews,
                }),
                "thread_inventory_digest": authority.digest_json({
                    "threads": threads,
                }),
                "material_finding_ids": [],
            }
            facts["source_signature"] = {
                "signer_identity": SOURCE,
                "range_signature_evidence_digest": (
                    amendment.source_signature_binding_digest(
                        facts["source_commits"], repo["base"]
                    )
                ),
                "verified": True,
            }
            trusted_signer = authority.TrustedSigner(
                SOURCE,
                (repo["trusted"].with_suffix(".pub").read_text().strip(),),
                (),
            )
            trust = SimpleNamespace(
                authority_signer_identities=frozenset({ROOT_SIGNER}),
                legacy_adoption_signer_identities=frozenset({SIGNER}),
                signers={SOURCE: trusted_signer},
                publication_remote_url=str(repo["remote"]),
            )
            pull = {
                "number": 961, "state": "open", "draft": False,
                "merged": False,
                "head": {"sha": repo["head"], "repo": {"full_name": "SecPal/.github"}},
                "base": {"sha": repo["base"], "ref": "main", "repo": {"full_name": "SecPal/.github"}},
            }
            issue = {"number": 960, "state": "open"}
            def github(arguments: list[str]):
                joined = " ".join(arguments)
                if "pulls/961" in joined:
                    value = pull
                elif "issues/960" in joined:
                    value = issue
                elif "issues/961/events" in joined:
                    value = ready_events
                elif "actions/runs" in joined:
                    value = {
                        "total_count": len(ready_runs),
                        "workflow_runs": ready_runs,
                    }
                elif "check-runs" in joined:
                    value = {"total_count": len(checks), "check_runs": checks}
                elif "/status" in joined:
                    value = {
                        "sha": repo["head"], "state": "success",
                        "total_count": len(statuses),
                        "statuses": statuses,
                    }
                elif "graphql" in arguments:
                    value = feedback_response(
                        arguments, repo["head"], threads, reviews
                    )
                else:
                    raise AssertionError(arguments)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(value).encode(), b""
                )

            signer_factory = mock.Mock()
            first, second = self.patches(trust)
            with mock.patch.object(
                amendment, "ROOT", repo["root"]
            ), mock.patch.object(
                amendment.publication, "_run_gh", side_effect=github
            ), mock.patch.object(
                amendment.execution, "_policy_role_signer", signer_factory
            ), mock.patch.object(
                amendment, "_registered_bootstrap_policy",
                return_value=policy,
            ), mock.patch.object(
                amendment, "_live_required_check_policy",
                return_value={
                    "strict": True,
                    "checks": [{"context": "governance", "app_id": None}],
                },
            ), mock.patch.object(
                amendment, "_bound_current_validation",
                return_value=facts["current_validation"],
            ), mock.patch.object(
                amendment, "_observe_historical_absence",
                return_value=(
                    facts["historical_evidence"],
                    facts["historical_absence_proof"],
                ),
            ), first, second:
                observed = authority.observe_governance_amendment_issuance(
                    "SecPal/.github", 960, inputs
                )
                self.assertEqual(
                    observed,
                    {
                        key: value for key, value in facts.items()
                        if key != "independent_qualification"
                    },
                )
                mutations = {
                    "stale head": lambda value: value[
                        "independent_qualification"
                    ].update(head_sha="9" * 40),
                    "stale main": lambda value: value.update(
                        accepted_main_sha="9" * 40
                    ),
                    "caller-selected bootstrap source": lambda value: value[
                        "qualified_source"
                    ].update(head_sha="9" * 40),
                }
                for label, mutate in mutations.items():
                    stale = copy.deepcopy(inputs)
                    mutate(stale)
                    with self.subTest(label=label), self.assertRaises(
                        amendment.GovernanceAmendmentError
                    ):
                        authority.authenticate_governance_amendment_issuance(
                            "SecPal/.github", 960, stale
                        )
            signer_factory.assert_not_called()

    def test_live_ci_authenticates_and_inherits_combined_status_head(self) -> None:
        checks = [{
            "name": "governance", "status": "completed",
            "conclusion": "success", "head_sha": HEAD,
        }]
        status = {
            "sha": HEAD, "state": "success", "total_count": 2,
            "statuses": [
                {"context": "license/cla", "state": "success"},
                {"context": "governance", "state": "success"},
            ],
        }
        required_policy = {
            "strict": True,
            "checks": [{"context": "governance", "app_id": None}],
        }

        def observe(value: dict[str, object]) -> dict[str, object]:
            if "statuses" in value and "total_count" not in value:
                value = {**value, "total_count": len(value["statuses"])}
            responses = iter((
                {"total_count": len(checks), "check_runs": checks}, value,
            ))

            def github(arguments: list[str]):
                return subprocess.CompletedProcess(
                    arguments, 0,
                    json.dumps(next(responses)).encode(), b"",
                )

            with mock.patch.object(
                amendment.publication, "_run_gh", side_effect=github
            ), mock.patch.object(
                amendment, "_live_required_check_policy",
                return_value=required_policy,
            ):
                return amendment._live_ci("SecPal/.github", HEAD, PARENT)

        observed = observe(status)
        normalized = [
            {"context": "governance", "state": "success", "sha": HEAD},
            {"context": "license/cla", "state": "success", "sha": HEAD},
        ]
        self.assertEqual(observed, {
            "head_sha": HEAD,
            "workflow_identity": amendment.SOURCE_CI_VERSION,
            "result": "PASS",
            "evidence_digest": authority.digest_json({
                "checks": checks, "statuses": normalized,
                "required_check_policy": required_policy,
            }),
        })

        superseded = [
            {**checks[0], "id": 20},
            {
                **checks[0], "id": 10,
                "conclusion": "cancelled",
            },
        ]
        responses = iter((
            {"total_count": len(superseded), "check_runs": superseded},
            status,
        ))
        with mock.patch.object(
            amendment.publication, "_run_gh",
            side_effect=lambda arguments: subprocess.CompletedProcess(
                arguments, 0, json.dumps(next(responses)).encode(), b"",
            ),
        ), mock.patch.object(
            amendment, "_live_required_check_policy",
            return_value=required_policy,
        ):
            self.assertEqual(
                amendment._live_ci("SecPal/.github", HEAD, PARENT)["result"],
                "PASS",
            )

        latest_cancelled = [
            {**checks[0], "id": 10},
            {
                **checks[0], "id": 20,
                "conclusion": "cancelled",
            },
        ]
        responses = iter((
            {
                "total_count": len(latest_cancelled),
                "check_runs": latest_cancelled,
            },
            status,
        ))
        with mock.patch.object(
            amendment.publication, "_run_gh",
            side_effect=lambda arguments: subprocess.CompletedProcess(
                arguments, 0, json.dumps(next(responses)).encode(), b"",
            ),
        ), mock.patch.object(
            amendment, "_live_required_check_policy",
            return_value=required_policy,
        ), self.assertRaises(amendment.GovernanceAmendmentError):
            amendment._live_ci("SecPal/.github", HEAD, PARENT)

        invalid = {
            "missing envelope head": {
                "state": "success", "statuses": status["statuses"],
            },
            "wrong envelope head": {
                "sha": "9" * 40, "state": "success",
                "statuses": status["statuses"],
            },
            "wrong explicit context head": {
                "sha": HEAD, "state": "success", "statuses": [{
                    "context": "license/cla", "state": "success",
                    "sha": "9" * 40,
                }],
            },
            "null explicit context head": {
                "sha": HEAD, "state": "success", "statuses": [{
                    "context": "license/cla", "state": "success",
                    "sha": None,
                }],
            },
            "duplicate context": {
                "sha": HEAD, "state": "success", "statuses": [
                    {"context": "license/cla", "state": "success"},
                    {"context": "license/cla", "state": "success"},
                ],
            },
            "unexpected context": {
                "sha": HEAD, "state": "success", "statuses": [{
                    "context": "unbound/provider", "state": "success",
                }],
            },
            "pending context": {
                "sha": HEAD, "state": "pending", "statuses": [{
                    "context": "license/cla", "state": "pending",
                }],
            },
            "failed context": {
                "sha": HEAD, "state": "failure", "statuses": [{
                    "context": "license/cla", "state": "failure",
                }],
            },
        }
        for label, value in invalid.items():
            with self.subTest(label=label), self.assertRaises(
                amendment.GovernanceAmendmentError
            ):
                observe(value)

        with self.assertRaisesRegex(
            amendment.GovernanceAmendmentError, "status inventory is truncated"
        ):
            observe({**status, "total_count": 31})

        with mock.patch.object(
            amendment, "_live_required_check_policy",
            return_value=required_policy,
        ):
            for label, check_value in {
                "truncated inventory": {
                    "total_count": 2, "check_runs": checks,
                },
                "arbitrary skipped check": {
                    "total_count": 2,
                    "check_runs": checks + [{
                        "name": "unregistered optional", "status": "completed",
                        "conclusion": "skipped", "head_sha": HEAD,
                    }],
                },
                "required check skipped": {
                    "total_count": 1,
                    "check_runs": [{**checks[0], "conclusion": "skipped"}],
                },
            }.items():
                responses = iter((check_value, status))
                def github(arguments: list[str]):
                    return subprocess.CompletedProcess(
                        arguments, 0, json.dumps(next(responses)).encode(), b""
                    )
                with self.subTest(label=label), mock.patch.object(
                    amendment.publication, "_run_gh", side_effect=github
                ), self.assertRaises(amendment.GovernanceAmendmentError):
                    amendment._live_ci("SecPal/.github", HEAD, PARENT)

    def test_required_check_policy_is_exactly_bound_to_accepted_main(self) -> None:
        contexts = [f"required-{index}" for index in range(13)]
        source = (
            "REQUIRED_CONTEXTS_JSON=\"$(cat <<'EOF'\n"
            + json.dumps({".github": contexts})
            + "\nEOF\n)\"\n"
        ).encode()

        def observe(checks: list[dict[str, object]]) -> dict[str, object]:
            def github(arguments: list[str]):
                return subprocess.CompletedProcess(
                    arguments, 0,
                    json.dumps({"strict": True, "checks": checks}).encode(),
                    b"",
                )
            with mock.patch.object(
                amendment, "_accepted_main_bytes", return_value=source,
            ), mock.patch.object(
                amendment.publication, "_run_gh", side_effect=github,
            ):
                return amendment._live_required_check_policy(
                    "SecPal/.github", PARENT
                )

        exact = [{"context": value, "app_id": None} for value in contexts]
        self.assertEqual(
            observe(exact),
            {"strict": True, "checks": sorted(exact, key=lambda item: item["context"])},
        )
        mutations = {
            "missing": exact[:-1],
            "extra": exact + [{"context": "extra", "app_id": None}],
            "substituted": exact[:-1] + [{"context": "other", "app_id": None}],
            "duplicated": exact[:-1] + [copy.deepcopy(exact[0])],
            "wrong app identity": [
                {**item, "app_id": "untrusted"} if index == 0 else item
                for index, item in enumerate(exact)
            ],
        }
        for label, changed in mutations.items():
            with self.subTest(label=label), self.assertRaises(
                amendment.GovernanceAmendmentError
            ):
                observe(changed)

    def test_historical_absence_comes_from_protected_authority(self) -> None:
        trust = SimpleNamespace(
            repository="SecPal/.github",
            publication_branch="refs/heads/secpal-lifecycle-publications",
        )
        protected = amendment.publication.VerifiedPreEnrollmentAbsence(
            "SecPal/.github", 960,
            "refs/heads/secpal-lifecycle-publications", "1" * 40,
            "2" * 64,
        )
        history = {
            "qualified_source_head_sha": "3" * 40,
            "qualified_source_tree_sha": "4" * 40,
            "qualified_source_parent_shas": ["5" * 40],
            "commits": [],
            "result": "NO_COMMIT_BOUND_VALIDATION_ARTIFACT_ISSUED",
        }
        with mock.patch.object(
            amendment.publication, "verify_pre_enrollment_absence",
            return_value=protected,
        ) as verify_absence, mock.patch.object(
            amendment, "_qualified_source_history_audit", return_value=history,
        ):
            evidence, proof = amendment._observe_historical_absence(
                Path("."), "SecPal/.github", 960, 961, HEAD, PARENT,
                proposed_policy(), trust,
            )
        self.assertEqual(evidence, amendment.historical_evidence())
        self.assertEqual(proof["head_sha"], HEAD)
        self.assertEqual(proof["result"], "NO_HISTORICAL_RECEIPT_ISSUED")
        verify_absence.assert_called_once_with(
            "SecPal/.github", 960, policy=trust
        )

        substituted = copy.copy(protected)
        object.__setattr__(substituted, "delivery_issue", 959)
        with mock.patch.object(
            amendment.publication, "verify_pre_enrollment_absence",
            return_value=substituted,
        ), mock.patch.object(
            amendment, "_qualified_source_history_audit", return_value=history,
        ), self.assertRaisesRegex(
            amendment.GovernanceAmendmentError, "scope changed"
        ):
            amendment._observe_historical_absence(
                Path("."), "SecPal/.github", 960, 961, HEAD, PARENT,
                proposed_policy(), trust,
            )

    def test_qualified_source_artifact_audit_rejects_receipt_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.hermetic_repository(
                directory, attacker_intermediate=False
            )
            trust = SimpleNamespace(signers={
                SOURCE: authority.TrustedSigner(
                    SOURCE,
                    (repo["trusted"].with_suffix(".pub").read_text().strip(),),
                    (),
                ),
            })

            def policy() -> dict[str, object]:
                return {"qualified_source": {
                    "head_sha": repo["git"]("rev-parse", "HEAD"),
                    "tree_sha": repo["git"]("rev-parse", "HEAD^{tree}"),
                    "ordered_parent_shas": [repo["base"]],
                }}

            observed = amendment._qualified_source_history_audit(
                repo["root"], policy(), trust
            )
            self.assertEqual(
                observed["result"],
                "NO_COMMIT_BOUND_VALIDATION_ARTIFACT_ISSUED",
            )
            self.assertEqual(len(observed["commits"]), 2)

            repo["git"](
                "commit", "--amend", "-S", "-m",
                "trusted tip\n\nSecPal-Validation-Receipt: " + "a" * 64,
            )
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError,
                "provenance contradicts absence",
            ):
                amendment._qualified_source_history_audit(
                    repo["root"], policy(), trust
                )

    def test_reviewed_target_audits_only_after_accepted_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.hermetic_repository(
                directory, attacker_intermediate=False, base_receipt=True
            )
            trust = SimpleNamespace(signers={
                SOURCE: authority.TrustedSigner(
                    SOURCE,
                    (repo["trusted"].with_suffix(".pub").read_text().strip(),),
                    (),
                ),
            })
            record = {"delivery_issue": 1053, "qualified_source": {
                "head_sha": repo["head"], "tree_sha": repo["tree"],
                "ordered_parent_shas": [repo["base"]],
            }}
            audited = amendment._qualified_source_history_audit(
                repo["root"], record, trust
            )
            self.assertEqual(
                [item["oid"] for item in audited["commits"]], [repo["head"]]
            )
            record["delivery_issue"] = 960
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError,
                "provenance contradicts absence",
            ):
                amendment._qualified_source_history_audit(
                    repo["root"], record, trust
                )

    def test_caller_cannot_supply_absence_or_current_validation(self) -> None:
        inputs = observation_inputs(authorization())
        for field, value in {
            "historical_evidence": amendment.historical_evidence(),
            "historical_absence_proof": {
                "head_sha": HEAD,
                "verification_authority": "CALLER_ASSERTION",
                "history_digest": "1" * 64,
                "artifact_audit_digest": "2" * 64,
                "result": "NO_HISTORICAL_RECEIPT_ISSUED",
            },
            "current_validation": {
                "accepted_main_sha": PARENT,
                "policy_digest": "3" * 64,
                "command_set_digest": "4" * 64,
                "result": "PASS",
            },
        }.items():
            changed = {**inputs, field: value}
            with self.subTest(field=field), mock.patch.object(
                amendment, "produce_observation"
            ) as producer, self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "not closed"
            ):
                amendment.authenticate_issuance(
                    "SecPal/.github", 960, changed
                )
            producer.assert_not_called()

    def test_current_validation_is_derived_from_accepted_main_registry(self) -> None:
        record = {
            "repository": "SecPal/.github",
            "focused_validation": [{"argv": ["focused"], "working_directory": "."}],
            "required_local_validation": [{"argv": ["complete"], "working_directory": "."}],
        }
        raw = json.dumps({
            "schema_version": "1.0", "repositories": [record],
        }).encode()
        with mock.patch.object(
            amendment, "_accepted_main_bytes", return_value=raw,
        ):
            observed = amendment._bound_current_validation(
                Path("."), "SecPal/.github", PARENT
            )
        self.assertEqual(observed, {
            "accepted_main_sha": PARENT,
            "policy_digest": authority.digest_json(record),
            "command_set_digest": authority.digest_json({
                "focused_validation": record["focused_validation"],
                "required_local_validation": record[
                    "required_local_validation"
                ],
            }),
            "result": "PASS",
        })
        for label, registry in {
            "missing": {"schema_version": "1.0", "repositories": []},
            "duplicate": {
                "schema_version": "1.0", "repositories": [record, record],
            },
            "candidate local substitute": {
                "schema_version": "1.0", "repositories": [{
                    **record, "repository": "SecPal/api",
                }],
            },
        }.items():
            with self.subTest(label=label), mock.patch.object(
                amendment, "_accepted_main_bytes",
                return_value=json.dumps(registry).encode(),
            ), self.assertRaises(amendment.GovernanceAmendmentError):
                amendment._bound_current_validation(
                    Path("."), "SecPal/.github", PARENT
                )

    @contextmanager
    def old_verifier_source(self):
        """Two hermetic commits: corrected tooling and an immutable old verifier."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "authority"
            root.mkdir()
            def git(*arguments):
                return subprocess.run(
                    ["git", "-c", "commit.gpgsign=false", *arguments],
                    cwd=root, check=True, capture_output=True,
                ).stdout.decode().strip()
            git("init", "-b", "main")
            git("config", "user.name", "fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("fetch", str(amendment.ROOT),
                "HEAD")
            git("read-tree", "--reset", "-u", "FETCH_HEAD")
            # Qualify the exact current implementation before it is committed.
            delta = subprocess.run(["git", "diff", "--binary", "HEAD", "--"],
                cwd=amendment.ROOT, check=True, capture_output=True).stdout
            if delta:
                subprocess.run(["git", "apply", "--index", "--binary"],
                    cwd=root, input=delta, check=True, capture_output=True)
            git("commit", "-m", "accepted corrected tooling")
            accepted = git("rev-parse", "HEAD")
            verifier = root / "scripts/secpal_pr_review/lifecycle_authority.py"
            corrected = verifier.read_text()
            old = corrected.replace(
                "    if zero_receipt_root:\n        recovered_adoption_root_historical_evidence(",
                "    if zero_receipt_root:\n"
                "        raise LifecycleAuthorityError('old verifier rejects null historical evidence')\n"
                "        recovered_adoption_root_historical_evidence(",
            )
            self.assertNotEqual(old, corrected)
            verifier.write_text(old)
            git("add", ".")
            git("commit", "-m", "unchanged historical source verifier")
            candidate = git("rev-parse", "HEAD")
            tree = git("rev-parse", "HEAD^{tree}")
            git("reset", "--hard", accepted)
            yield root, accepted, candidate, tree, git

    def test_reviewed_current_safety_uses_accepted_verifier_with_old_exact_source(self):
        with self.old_verifier_source() as (root, accepted, candidate, tree, git):
            before = git("rev-parse", candidate + "^{tree}")
            with mock.patch.object(amendment, "ROOT", root), mock.patch.object(
                amendment.validation_evidence_loss, "ROOT", root,
            ):
                result = amendment._bound_current_validation(
                    root, "SecPal/.github", accepted,
                    target_head_sha=candidate, target_tree_sha=tree,
                )
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(result["accepted_main_sha"], accepted)
            self.assertEqual(git("rev-parse", candidate + "^{tree}"), before)
            self.assertEqual(git("status", "--porcelain"), "")

    def test_reviewed_current_safety_profile_and_source_substitutions_fail_closed(self):
        safety = amendment.exact_source_safety
        with self.old_verifier_source() as (root, accepted, candidate, tree, git):
            profile = amendment._reviewed_current_safety_profile(root, accepted)
            mutations = {
                "caller tooling": lambda p: p["tooling"].append({
                    "path": "scripts/caller.py", "mode": "100644",
                    "blob_oid": "f" * 40, "size": 1,
                }),
                "missing tooling": lambda p: p["tooling"].pop(),
                "wrong blob": lambda p: p["tooling"][0].update(blob_oid="f" * 40),
                "wrong mode": lambda p: p["tooling"][0].update(
                    mode="100755" if p["tooling"][0]["mode"] == "100644" else "100644"),
                "wrong size": lambda p: p["tooling"][0].update(size=1),
                "candidate tooling": lambda p: p.update(tooling=
                    amendment._reviewed_current_safety_profile(root, candidate)["tooling"]),
                "overlap": lambda p: p["tooling"].append(p["harness"][0]),
                "execution model": lambda p: p.update(execution_model="CANDIDATE_TOOLING"),
                "command set": lambda p: p["validation_command_set"].clear(),
                "invariants": lambda p: p["required_invariants"].clear(),
            }
            for name, mutate in mutations.items():
                changed = copy.deepcopy(profile)
                mutate(changed)
                with self.subTest(name=name), self.assertRaises(authority.LifecycleAuthorityError):
                    with safety.two_provenance_execution_roots(
                        root, accepted, source_root=root,
                        candidate_repository="SecPal/.github", profile=changed,
                    ) as roots:
                        safety.run_profile(roots.tooling, changed,
                                           expected_profile=profile,
                                           candidate_root=roots.candidate,
                                           candidate_repository="SecPal/.github")
            for changed_root in ("tooling", "candidate"):
                with self.subTest(root=changed_root), self.assertRaises(authority.LifecycleAuthorityError):
                    with safety.two_provenance_execution_roots(
                        root, accepted, source_root=root,
                        candidate_repository="SecPal/.github", profile=profile,
                    ) as roots:
                        path = getattr(roots, changed_root) / "scripts/secpal_pr_review/lifecycle_authority.py"
                        path.write_text("raise RuntimeError('substituted verifier')\n")
            with self.assertRaises(authority.LifecycleAuthorityError):
                with safety.two_provenance_execution_roots(
                    root, accepted, source_root=root,
                    candidate_repository="other/repository", profile=profile,
                ):
                    self.fail("cross-repository tooling was accepted")
            for head, target_tree in ((candidate, "f" * 40), ("f" * 40, tree)):
                with self.subTest(head=head), self.assertRaises(amendment.GovernanceAmendmentError):
                    amendment._bound_current_validation(root, "SecPal/.github", accepted,
                                                       target_head_sha=head, target_tree_sha=target_tree)
            # A different accepted commit cannot use the previously bound inventory.
            git("checkout", "--detach", candidate)
            with self.assertRaises(authority.LifecycleAuthorityError):
                with safety.two_provenance_execution_roots(
                    root, candidate, source_root=root,
                    candidate_repository="SecPal/.github", profile=profile,
                ):
                    self.fail("accepted tooling advance reused a stale profile")
            git("rm", "scripts/secpal_pr_review/lifecycle_authority.py")
            git("commit", "-m", "missing required accepted verifier fixture")
            with self.assertRaises(authority.LifecycleAuthorityError):
                amendment._reviewed_current_safety_profile(root, git("rev-parse", "HEAD"))

    def test_reviewed_current_safety_rejects_incompatible_loaded_module_origins(self):
        safety = amendment.exact_source_safety
        with self.old_verifier_source() as (root, _accepted, _candidate, _tree, git):
            harness_path = root / amendment.validation_evidence_loss.CURRENT_SAFETY_PATH
            original = harness_path.read_text()
            substitutions = {
                "candidate": ("secpal_pr_review.lifecycle_authority",
                              "Path(os.environ['SECPAL_CURRENT_SAFETY_CANDIDATE_ROOT']) / 'scripts/secpal_pr_review/lifecycle_authority.py'"),
                "ambient site package": ("secpal_pr_review.lifecycle_authority", "_ambient_file"),
                "duplicate namespace": ("scripts.secpal_pr_review.lifecycle_authority",
                                        "Path(os.environ['SECPAL_CURRENT_SAFETY_CANDIDATE_ROOT']) / 'scripts/secpal_pr_review/lifecycle_authority.py'"),
            }
            for name, (namespace, location) in substitutions.items():
                poison = (
                    "\nimport os, types, importlib.util, tempfile\n"
                    "_ambient_root = tempfile.TemporaryDirectory(prefix='site-packages-')\n"
                    "_ambient_file = Path(_ambient_root.name) / 'lifecycle_authority.py'\n"
                    "_ambient_file.write_text('old_verifier = True\\n')\n"
                    "_location = str(" + location + ")\n"
                    "_module = types.ModuleType(" + repr(namespace) + ")\n"
                    "_module.__file__ = _location\n"
                    "_module.__spec__ = importlib.util.spec_from_file_location(" + repr(namespace) + ", _location)\n"
                    "sys.modules[" + repr(namespace) + "] = _module\n"
                )
                harness_path.write_text(original + poison)
                git("add", str(harness_path.relative_to(root)))
                git("commit", "-m", "bound hostile module origin fixture")
                main = git("rev-parse", "HEAD")
                profile = amendment._reviewed_current_safety_profile(root, main)
                with self.subTest(origin=name), self.assertRaises(authority.LifecycleAuthorityError):
                    with safety.two_provenance_execution_roots(
                        root, main, source_root=root,
                        candidate_repository="SecPal/.github", profile=profile,
                    ) as roots:
                        safety.run_profile(roots.tooling, profile, expected_profile=profile,
                                           candidate_root=roots.candidate,
                                           candidate_repository="SecPal/.github")

    def test_reviewed_current_validation_executes_accepted_safety(self) -> None:
        record = {
            "repository": "SecPal/.github", "focused_validation": [{}],
            "required_local_validation": [{}],
        }
        registry = json.dumps({
            "schema_version": "1.0", "repositories": [record],
        }).encode()
        profile = {"validation_command_set": [{"argv": ["python3", "test"]}]}
        with mock.patch.object(
            amendment, "_accepted_main_bytes", return_value=registry,
        ), mock.patch.object(
            amendment, "_git_oid", side_effect=lambda root, expression:
            TREE if expression.endswith("^{tree}") else HEAD,
        ), mock.patch.object(
            amendment, "_reviewed_current_safety_profile",
            return_value=profile,
        ), mock.patch.object(
            amendment, "_run_git",
            return_value=SimpleNamespace(returncode=0),
        ), mock.patch.object(
            amendment.exact_source_safety, "two_provenance_execution_roots",
            return_value=nullcontext(SimpleNamespace(tooling=Path("tooling"),
                                                    candidate=Path("candidate"))),
        ), mock.patch.object(
            amendment.exact_source_safety, "run_profile",
        ) as runner:
            result = amendment._bound_current_validation(
                Path("."), "SecPal/.github", PARENT,
                target_head_sha=HEAD, target_tree_sha=TREE,
            )
            self.assertEqual(result["result"], "PASS")
            runner.assert_called_once()
            runner.side_effect = authority.LifecycleAuthorityError(
                "current safety assertions failed"
            )
            with self.assertRaises(authority.LifecycleAuthorityError):
                amendment._bound_current_validation(
                    Path("."), "SecPal/.github", PARENT,
                    target_head_sha=HEAD, target_tree_sha=TREE,
                )
            runner.reset_mock()
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "source tree changed"
            ):
                amendment._bound_current_validation(
                    Path("."), "SecPal/.github", PARENT,
                    target_head_sha=HEAD, target_tree_sha="f" * 40,
                )
            runner.assert_not_called()

    def test_live_ready_ci_binds_transition_triggered_workflows(self) -> None:
        source_ci = {
            "head_sha": HEAD,
            "workflow_identity": amendment.SOURCE_CI_VERSION,
            "result": "PASS",
            "evidence_digest": "1" * 64,
        }
        events, runs = ready_ci_fixtures(HEAD, PARENT)

        def observe(
            event_values: list[dict[str, object]],
            run_values: list[dict[str, object]],
            *, total_count: int | None = None,
        ) -> dict[str, object]:
            responses = iter((event_values, {
                "total_count": (
                    len(run_values) if total_count is None else total_count
                ),
                "workflow_runs": run_values,
            }))

            def github(arguments: list[str]):
                return subprocess.CompletedProcess(
                    arguments, 0,
                    json.dumps(next(responses)).encode(), b"",
                )

            with mock.patch.object(
                amendment.publication, "_run_gh", side_effect=github
            ):
                return amendment._live_ready_ci(
                    "SecPal/.github", 961, HEAD, PARENT, source_ci
                )

        observed = observe(events, runs)
        normalized_event = {
            "id": events[0]["id"], "event": events[0]["event"],
            "created_at": events[0]["created_at"],
            "actor": events[0]["actor"]["login"],
        }
        ready_authority = {
            "operation": "DRAFT_TO_READY",
            "actor": "aroviqen", "event_id": events[0]["id"],
            "head_sha": HEAD, "accepted_main_sha": PARENT,
            "source_ci_evidence_digest": source_ci["evidence_digest"],
        }
        self.assertEqual(observed, {
            "head_sha": HEAD,
            "workflow_identity": amendment.LIVE_OBSERVATION_VERSION,
            "result": "PASS",
            "evidence_digest": authority.digest_json({
                "source_ci_evidence_digest": source_ci["evidence_digest"],
                "ready_event": normalized_event,
                "ready_workflow_run_history": sorted(
                    [{
                        key: run[key] for key in (
                            "id", "name", "event", "status", "conclusion",
                            "head_sha", "created_at", "run_started_at",
                        )
                    } | {"pull_requests": [{
                        "number": run["pull_requests"][0]["number"],
                        "head_sha": run["pull_requests"][0]["head"]["sha"],
                        "base_sha": run["pull_requests"][0]["base"]["sha"],
                    }]} for run in runs],
                    key=lambda run: (run["name"], run["created_at"], run["id"]),
                ),
                "ready_workflow_runs": sorted(
                    [{
                        key: run[key] for key in (
                            "id", "name", "event", "status", "conclusion",
                            "head_sha", "created_at", "run_started_at",
                        )
                    } | {"pull_requests": [{
                        "number": run["pull_requests"][0]["number"],
                        "head_sha": run["pull_requests"][0]["head"]["sha"],
                        "base_sha": run["pull_requests"][0]["base"]["sha"],
                    }]} for run in runs],
                    key=lambda run: (run["name"], run["created_at"], run["id"]),
                ),
                "ready_transition_authority": {
                    **ready_authority,
                    "authorization_digest": authority.digest_json(
                        ready_authority
                    ),
                },
            }),
        })

        superseded = dict(
            runs[0], id=runs[0]["id"] - 100, conclusion="cancelled"
        )
        self.assertEqual(observe(events, runs + [superseded])["result"], "PASS")
        newest_cancelled = dict(
            runs[0], id=runs[0]["id"] + 100, conclusion="cancelled"
        )
        with self.assertRaises(amendment.GovernanceAmendmentError):
            observe(events, runs + [newest_cancelled])

        invalid = {
            "missing Ready event": ([], runs),
            "duplicate Ready event": (events + copy.deepcopy(events), runs),
            "missing workflow": (events, runs[:-1]),
            "pre-Ready workflow": (
                events,
                [dict(runs[0], created_at="2026-09-18T11:59:59Z")] + runs[1:],
            ),
            "equal-time workflow": (
                events,
                [dict(runs[0], created_at="2026-09-18T12:00:00Z")] + runs[1:],
            ),
            "malformed event time": (
                [dict(events[0], created_at="z")], runs,
            ),
            "malformed workflow time": (
                events,
                [dict(runs[0], created_at="zz")] + runs[1:],
            ),
            "noncanonical workflow time": (
                events,
                [dict(runs[0], created_at="2026-9-18T12:00:01Z")] + runs[1:],
            ),
            "impossible workflow time": (
                events,
                [dict(runs[0], created_at="2026-09-31T12:00:01Z")] + runs[1:],
            ),
            "pending workflow": (
                events,
                [dict(runs[0], status="in_progress", conclusion=None)] + runs[1:],
            ),
            "wrong-head workflow": (
                events,
                [dict(runs[0], head_sha="9" * 40)] + runs[1:],
            ),
            "wrong-PR workflow": (
                events,
                [dict(
                    runs[0],
                    pull_requests=[{
                        "number": 962,
                        "head": {"sha": HEAD},
                        "base": {"sha": PARENT},
                    }],
                )] + runs[1:],
            ),
            "unauthorized Ready actor": (
                [{**events[0], "actor": {"login": "attacker"}}], runs,
            ),
            "missing workflow ID": (
                events, [{**runs[0], "id": None}] + runs[1:],
            ),
            "duplicate workflow ID": (
                events, [runs[0], {**runs[1], "id": runs[0]["id"]}]
                + runs[2:],
            ),
        }
        for label, (event_values, run_values) in invalid.items():
            with self.subTest(label=label), self.assertRaises(
                amendment.GovernanceAmendmentError
            ):
                observe(event_values, run_values)

        with self.assertRaises(amendment.GovernanceAmendmentError):
            observe(events, runs, total_count=101)

    def test_live_feedback_uses_valid_closed_query_and_fails_closed(self) -> None:
        def observe(
            *, live_head: str = HEAD, comment_body: str = "",
            review_body: str = "", incomplete: bool = False,
        ) -> dict[str, object]:
            def github(arguments: list[str]):
                query = next(
                    item[6:] for item in arguments if item.startswith("query=")
                )
                self.assertEqual(query.count("{"), query.count("}"))
                self.assertIn("headRefOid", query)
                cursor = next(
                    (item[7:] for item in arguments if item.startswith("cursor=")),
                    None,
                )
                page = {"hasNextPage": False, "endCursor": None}
                pull: dict[str, object] = {"headRefOid": live_head}
                value: dict[str, object] = {
                    "data": {"repository": {"pullRequest": pull}},
                }
                if "reviewThreads(first:" in query:
                    if incomplete:
                        page = {"hasNextPage": True, "endCursor": None}
                    elif cursor is None:
                        page = {"hasNextPage": True, "endCursor": "threads-2"}
                    pull["reviewThreads"] = {
                        "nodes": [{
                            "id": "T1", "isResolved": True,
                            "isOutdated": False,
                        }],
                        "pageInfo": page,
                    }
                elif "node(id:$thread)" in query:
                    self.assertIn("thread=T1", arguments)
                    value["data"]["node"] = {
                        "comments": {"nodes": [], "pageInfo": page},
                    }
                elif "reviews(first:" in query:
                    pull["reviews"] = {
                        "nodes": [{
                            "id": "R1", "state": "COMMENTED",
                            "body": review_body, "commit": {"oid": HEAD},
                            "author": {"login": "review-bot"},
                        }],
                        "pageInfo": page,
                    }
                elif "comments(first:" in query:
                    pull["comments"] = {
                        "nodes": [{
                            "id": "C1", "body": comment_body,
                            "author": {"login": "review-bot"},
                        }],
                        "pageInfo": page,
                    }
                else:
                    raise AssertionError(query)
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(value).encode(), b"",
                )

            with mock.patch.object(
                amendment.publication, "_run_gh", side_effect=github,
            ):
                return amendment._live_feedback("SecPal/.github", 961, HEAD)

        observed = observe()
        self.assertEqual(observed["material_finding_ids"], [])
        self.assertEqual(observed, observe())
        self.assertEqual(
            observe(comment_body="blocking")["material_finding_ids"],
            ["comment:C1"],
        )
        self.assertEqual(
            observe(review_body="blocking")["material_finding_ids"],
            ["review:R1"],
        )
        with self.assertRaisesRegex(
            amendment.GovernanceAmendmentError,
            "live governance amendment feedback head changed",
        ):
            observe(live_head="9" * 40)
        with self.assertRaisesRegex(
            amendment.GovernanceAmendmentError,
            "live governance amendment feedback pagination is incomplete",
        ):
            observe(incomplete=True)

        self.assertTrue(amendment._provider_summary_is_nonmaterial({
            "author": {"login": "chatgpt-codex-connector"},
            "body": '<!-- codex-pull-request-review-summary -->\n'
                    '<!-- codex-security-review:v1 {"status":"completed"} -->',
        }, review=False))
        self.assertTrue(amendment._provider_summary_is_nonmaterial({
            "author": {"login": "copilot-pull-request-reviewer"},
            "body": "<!-- ccr-overview-v2 -->\nsummary",
        }, review=True))

    def test_strict_provider_merge_gate_binds_base_head_and_clean_state(self) -> None:
        item = authorization()
        pull = {
            "state": "open", "draft": False, "merged": False,
            "head": {"sha": item["head_sha"]},
            "base": {"sha": item["accepted_main_sha"], "ref": "main"},
            "mergeable": True, "mergeable_state": "clean",
        }
        with mock.patch.object(
            amendment, "_live_required_check_policy",
            return_value={"strict": True, "checks": [{"context": "x", "app_id": None}]},
        ), mock.patch.object(
            amendment, "_github_json", return_value=pull,
        ):
            amendment._authenticate_provider_merge_gate(item)
        for label, mutate in {
            "base advance": lambda value: value["base"].update(sha="9" * 40),
            "head change": lambda value: value["head"].update(sha="8" * 40),
            "behind": lambda value: value.update(mergeable_state="behind"),
        }.items():
            changed = copy.deepcopy(pull); mutate(changed)
            with self.subTest(label=label), mock.patch.object(
                amendment, "_live_required_check_policy",
                return_value={"strict": True, "checks": [{"context": "x", "app_id": None}]},
            ), mock.patch.object(
                amendment, "_github_json", return_value=changed,
            ), self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "strict provider merge gate"
            ):
                amendment._authenticate_provider_merge_gate(item)
        with mock.patch.object(
            amendment, "_live_required_check_policy",
            side_effect=amendment.GovernanceAmendmentError("not strict"),
        ), self.assertRaises(amendment.GovernanceAmendmentError):
            amendment._authenticate_provider_merge_gate(item)

        reviewed = reviewed_authorization()
        current = reviewed["current_validation"]["accepted_main_sha"]
        current_pull = copy.deepcopy(pull)
        current_pull["base"]["sha"] = current
        with mock.patch.object(
            amendment, "_live_required_check_policy",
            side_effect=lambda _repo, main: (
                {"strict": True} if main == current else
                (_ for _ in ()).throw(AssertionError("historical policy used"))
            ),
        ), mock.patch.object(
            amendment, "_github_json", return_value=current_pull,
        ):
            amendment._authenticate_provider_merge_gate(reviewed)

    def test_signed_delivery_scope_cannot_change_without_new_root_signature(self) -> None:
        value = authorization()
        for field, replacement in (("delivery_issue", 962), ("pull_request", 962)):
            changed = copy.deepcopy(value)
            changed[field] = replacement
            changed["authorization_id"] = (
                "governance-amendment:SecPal/.github:"
                f"{changed['delivery_issue']}:{changed['pull_request']}"
            )
            unsigned = {
                key: copy.deepcopy(item) for key, item in changed.items()
                if key not in {"authorization_digest", "signature"}
            }
            changed["signature"] = signer(
                authority.canonical_json_bytes(unsigned), amendment.DOMAIN
            )
            signed = {
                key: copy.deepcopy(item) for key, item in changed.items()
                if key != "authorization_digest"
            }
            changed["authorization_digest"] = authority.digest_json(signed)
            first, second = self.patches()
            with self.subTest(field=field), first, second, self.assertRaisesRegex(
                amendment.GovernanceAmendmentError,
                "root authorization scope changed",
            ):
                amendment.verify(changed)

    def test_executor_reauthenticates_all_facts_before_any_git_mutation(self) -> None:
        value = authorization()
        current = {
            key: copy.deepcopy(item) for key, item in value.items()
            if key not in {
                    "root_authorization", "signer_identity", "signature",
                    "authorization_digest",
                }
        }
        current["feedback"]["material_finding_ids"] = ["blocking"]
        first, second = self.patches()
        with first, second, mock.patch.object(
            amendment, "_remote_url", return_value="unused"
        ), mock.patch.object(
            amendment, "produce_observation", return_value=current
        ), mock.patch.object(amendment, "_run_git") as run_git:
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "prerequisites changed"
            ):
                authority.execute_governance_amendment(value)
        run_git.assert_not_called()

    def test_squash_transport_rejects_incompatible_read_back(self) -> None:
        message = b"record\n"
        exact = {
            "oid": "d" * 40, "parent_shas": ["a" * 40],
            "tree_sha": "b" * 40, "message": "record",
            "verification": {"verified": True, "reason": "valid"},
        }
        amendment._verify_squash_read_back(
            exact, oid="d" * 40, parent_sha="a" * 40,
            tree_sha="b" * 40, message=message,
        )
        mutations = {
            "two-parent": lambda value: value.update(
                parent_shas=["a" * 40, "c" * 40]
            ),
            "wrong parent": lambda value: value.update(parent_shas=["c" * 40]),
            "wrong tree": lambda value: value.update(tree_sha="c" * 40),
            "non-squash message": lambda value: value.update(message="other"),
            "unverified": lambda value: value["verification"].update(
                verified=False
            ),
            "bad verification": lambda value: value["verification"].update(
                reason="unsigned"
            ),
        }
        for label, mutate in mutations.items():
            changed = copy.deepcopy(exact)
            mutate(changed)
            with self.subTest(label=label), self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "immutable read-back"
            ):
                amendment._verify_squash_read_back(
                    changed, oid="d" * 40, parent_sha="a" * 40,
                    tree_sha="b" * 40, message=message,
                )

    def test_squash_transport_uses_normal_pr_merge_without_direct_push(self) -> None:
        calls: list[list[str]] = []
        def github(arguments: list[str]):
            calls.append(arguments)
            return subprocess.CompletedProcess(
                arguments, 0,
                json.dumps({"merged": True, "sha": "d" * 40}).encode(), b"",
            )
        with mock.patch.object(amendment.publication, "_run_gh", side_effect=github):
            self.assertEqual(
                amendment._merge_pull_request(
                    "SecPal/.github", 961, "a" * 40,
                    b"Governance amendment\n\nrecord\n",
                ),
                "d" * 40,
            )
        flattened = " ".join(calls[0])
        self.assertIn("merge_method=squash", flattened)
        self.assertNotIn("push", flattened)
        self.assertNotIn("force", flattened)

    def test_scope_and_absence_substitutions_fail_closed(self) -> None:
        mutations = {
            "repository": lambda v: v.update(repository="SecPal/api"),
            "issue": lambda v: v.update(delivery_issue=959),
            "pull request": lambda v: v.update(pull_request=962),
            "head": lambda v: v.update(head_sha="9" * 40),
            "tree": lambda v: v.update(tree_sha="9" * 40),
            "parents": lambda v: v.update(ordered_parent_shas=["9" * 40]),
            "source signer": lambda v: v["source_signature"].update(signer_identity="other"),
            "range digest": lambda v: v["source_signature"].update(
                range_signature_evidence_digest="0" * 64
            ),
            "intermediate signature": lambda v: v.update(source_commits=[
                amendment.source_commit_evidence("8" * 40, SOURCE, v["accepted_main_sha"]),
                *v["source_commits"],
            ]),
            "stale main": lambda v: v.update(accepted_main_sha="9" * 40),
            "caller absence": lambda v: v["historical_evidence"].update(state="UNAVAILABLE"),
            "absence receipt": lambda v: v["historical_evidence"].update(validation_receipt_digest="9" * 64),
            "absence source digest": lambda v: v["historical_evidence"].update(source_validation_evidence_digest="9" * 64),
            "absence attestation digest": lambda v: v["historical_evidence"].update(final_attestation_digest="9" * 64),
            "caller asserted absence": lambda v: v["historical_absence_proof"].update(verification_authority="CALLER_ASSERTION"),
            "unproven recursion": lambda v: v["architecture_necessity"].update(recursive_self_bootstrap="ASSERTED"),
            "unknown reason": lambda v: v.update(purpose="OTHER"),
            "failed validation": lambda v: v["current_validation"].update(result="FAIL"),
            "blocking feedback": lambda v: v["feedback"].update(material_finding_ids=["finding"]),
            "other qualification": lambda v: v["qualified_source"].update(head_sha="9" * 40),
            "counter reset": lambda v: v["intended_state"].update(remediation_cycle_count=0),
            "fabricated Ready": lambda v: v["intended_state"].update(draft=False, ready=True, ready_transition_count=1),
            "Cycle 3": lambda v: v["intended_state"].update(cycle_3_absent=False),
            "cross delivery": lambda v: v.update(authorization_id="governance-amendment:other"),
            "product source": lambda v: v["changed_files"].append({"path":"src/runtime.py","blob_oid":"f"*40,"mode":"100644"}),
            "second use": lambda v: v.update(bounded_uses=2),
        }
        for label, mutate in mutations.items():
            changed = authorization(); mutate(changed); changed = reseal(changed)
            if label == "parents":
                # Final topology is dynamically authorized. Exercise cross-topology
                # replay by tampering after the exact signed authorization exists.
                changed["ordered_parent_shas"] = ["8" * 40]
            first, second = self.patches()
            with self.subTest(label=label), first, second, self.assertRaises((amendment.GovernanceAmendmentError, authority.LifecycleAuthorityError)):
                amendment.verify(changed)

    def test_root_signature_remains_authority_after_registered_scope_binding(self) -> None:
        value = authorization()
        first, second = self.patches()
        with first, second:
            self.assertTrue(amendment.is_verified(amendment.verify(value)))

        changed = copy.deepcopy(value)
        changed["governance_path_prefixes"] = ["src"]
        unsigned = {
            key: copy.deepcopy(item) for key, item in changed.items()
            if key not in {"authorization_digest", "signature"}
        }
        changed["signature"] = signer(
            authority.canonical_json_bytes(unsigned), amendment.DOMAIN
        )
        signed = {
            key: copy.deepcopy(item) for key, item in changed.items()
            if key != "authorization_digest"
        }
        changed["authorization_digest"] = authority.digest_json(signed)
        first, second = self.patches()
        with first, second, self.assertRaisesRegex(
            amendment.GovernanceAmendmentError, "root authorization scope changed"
        ):
            amendment.verify(changed)

    def test_trusted_tip_over_attacker_intermediate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.hermetic_repository(
                directory, attacker_intermediate=True
            )
            policy = copy.deepcopy(proposed_policy())
            policy["accepted_main_sha"] = repo["base"]
            policy["human_authorization_digest"] = authority.digest_json({
                "authority_identity": policy["human_authority_identity"],
                "repository": "SecPal/.github", "delivery_issue": 960,
                "pull_request": 961, "purpose": amendment.PURPOSE,
                "qualified_source_digest": policy["qualified_source"]["qualification_digest"],
                "accepted_main_sha": repo["base"], "decision": "APPROVED",
                "bounded_uses": 1,
            })
            raw = authorization(
                head=repo["head"], tree=repo["tree"],
                parent=repo["source_oids"][-2], accepted_main=repo["base"],
                changed=[{
                    "path": str(repo["path"].relative_to(repo["root"])),
                    "blob_oid": repo["blob"], "mode": "100644",
                }],
                source_oids=repo["source_oids"], policy=policy,
            )
            execution_facts = {
                key: copy.deepcopy(item) for key, item in raw.items()
                if key not in {
                    "root_authorization", "signer_identity", "signature",
                    "authorization_digest",
                }
            }
            trust = SimpleNamespace(
                authority_signer_identities=frozenset({ROOT_SIGNER}),
                legacy_adoption_signer_identities=frozenset({SIGNER}),
                signers={SOURCE: authority.TrustedSigner(
                    SOURCE,
                    (repo["trusted"].with_suffix(".pub").read_text().strip(),),
                    (),
                )},
            )
            first, second = self.patches(trust)
            with mock.patch.object(
                amendment, "ROOT", repo["root"]
            ), mock.patch.object(
                amendment, "_remote_url", return_value=str(repo["remote"])
            ), mock.patch.object(
                amendment, "produce_observation",
                return_value=execution_facts,
            ), first, second, self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "accepted-main key"
            ):
                authority.execute_governance_amendment(raw)
            self.assertEqual(
                repo["git"]("ls-remote", str(repo["remote"]), "refs/heads/main").split()[0],
                repo["base"],
            )

    def test_wrong_or_missing_legacy_signature_fails_before_merge(self) -> None:
        for label, mutate in {
            "missing": lambda value: value.update(signature={}),
            "altered": lambda value: value["signature"].update(value="altered"),
            "wrong signer": lambda value: value.update(signer_identity=SOURCE),
        }.items():
            value = authorization()
            mutate(value)
            first, second = self.patches()
            with self.subTest(label=label), first, second, mock.patch.object(
                amendment, "_merge_pull_request"
            ) as merge, self.assertRaises((
                amendment.GovernanceAmendmentError,
                authority.LifecycleAuthorityError,
            )):
                authority.execute_governance_amendment(value)
            merge.assert_not_called()

    def test_ambient_accepted_principal_with_arbitrary_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            subprocess.run(
                ["git", "init", "--quiet", "-b", "main", str(root)],
                check=True,
            )
            trusted = Path(directory) / "trusted"
            attacker = Path(directory) / "attacker"
            for key in (trusted, attacker):
                subprocess.run(
                    ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                    check=True,
                )
            ambient = Path(directory) / "ambient-allowed-signers"
            ambient.write_text(
                f"{SOURCE} {attacker.with_suffix('.pub').read_text()}",
                encoding="utf-8",
            )
            for key, value in (
                ("user.name", "SecPal Test"),
                ("user.email", "test@secpal.invalid"),
                ("gpg.format", "ssh"),
                ("user.signingkey", str(attacker)),
                ("gpg.ssh.allowedSignersFile", str(ambient)),
                ("commit.gpgsign", "true"),
            ):
                subprocess.run(
                    ["git", "-C", str(root), "config", key, value], check=True
                )
            (root / "governance.txt").write_text("candidate\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-S", "-m", "candidate"],
                check=True,
            )
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True, stdout=subprocess.PIPE, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(root), "verify-commit", head], check=True
            )
            trust = SimpleNamespace(signers={
                SOURCE: authority.TrustedSigner(
                    SOURCE,
                    (trusted.with_suffix(".pub").read_text().strip(),),
                    (),
                )
            })
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "accepted-main key"
            ):
                amendment._verify_commit_against_accepted_trust(
                    root, head, SOURCE, trust
                )

    def test_candidate_local_and_mixed_historical_authority_fail_closed(self) -> None:
        value = authorization()
        with mock.patch.object(authority, "_load_lifecycle_trust_policy", return_value=SimpleNamespace(legacy_adoption_signer_identities=frozenset({SIGNER}))), mock.patch.object(authority, "_policy_signature_verifier", return_value=lambda *_: (_ for _ in ()).throw(authority.LifecycleAuthorityError("untrusted"))):
            with self.assertRaises(amendment.GovernanceAmendmentError):
                amendment.verify(value)
        first, second = self.patches()
        with first, second, self.assertRaises(authority.LifecycleAuthorityError):
            authority.authenticate_exact_state_adoption_external_evidence(
                repository="SecPal/.github", delivery_issue=960, pull_request=961,
                head_sha=HEAD, tree_sha=TREE, pull_request_state="OPEN",
                commit_signature_evidence={"oid": HEAD}, validation_evidence=SimpleNamespace(),
                observed_pre_enrollment_history=history(), intended_state=state(),
                governance_amendment_authorization=value,
            )


if __name__ == "__main__":
    main()
