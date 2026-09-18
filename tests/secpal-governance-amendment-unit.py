#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
from contextlib import nullcontext
import hashlib
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock

from scripts.secpal_pr_review import governance_amendment as amendment
from scripts.secpal_pr_review import lifecycle_authority as authority

SIGNER = "lifecycle-legacy-adoption@secpal.app"
SOURCE = "aroviqen@secpal.app"
ROOT_SIGNER = SOURCE
HEAD = "a" * 40
TREE = "b" * 40
PARENT = "c" * 40


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


def state() -> dict[str, object]:
    value = authority.initial_state()
    value.update(unrestricted_review_count=1, remediation_cycle_count=1)
    return value


def history() -> list[dict[str, object]]:
    return [
        {"sequence": 1, "kind": "PR_CREATED_DRAFT", "observed_at": "2026-09-18T10:00:00Z", "head_sha": PARENT, "reviewed_head_sha": None},
        {"sequence": 2, "kind": "REMEDIATION_HEAD_OBSERVED", "observed_at": "2026-09-18T11:00:00Z", "head_sha": HEAD, "reviewed_head_sha": None},
    ]


def authorization(
    *, head: str = HEAD, tree: str = TREE, parent: str = PARENT,
    accepted_main: str = "3887b00e1b84ef0d14ab2846507a3100512c2c28",
    changed: list[dict[str, str]] | None = None,
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    policy = policy or amendment._load_policy()
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
        "source_signature": {
            "signer_identity": SOURCE,
            "signature_evidence_digest": authority.digest_json({
            "oid": head, "source": "USER", "signer_identity": SOURCE,
                "classification": "LOCAL_SSH_VERIFIED",
            }),
            "verified": True,
        },
        "natural_ci": {"head_sha": head, "workflow_identity": "pull-request-ci", "result": "PASS", "evidence_digest": "2" * 64},
        "independent_qualification": {"verifier_identity": "verifier", "conversation_id": "new-verifier", "head_sha": head, "tree_sha": tree, "result": "PASS", "qualification_digest": "3" * 64},
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
        "bounded_uses": 1, "signer_identity": SIGNER, "signature": {},
        "authorization_digest": "",
    }
    return reseal(value)


def reseal(value: dict[str, object]) -> dict[str, object]:
    value = copy.deepcopy(value)
    value["change_digest"] = authority.digest_json({
        key: value[key] for key in (
            "repository", "delivery_issue", "pull_request", "head_sha", "tree_sha",
            "ordered_parent_shas", "accepted_main_sha", "changed_files",
        )
    })
    unsigned = {key: copy.deepcopy(item) for key, item in value.items() if key not in {"authorization_digest", "signature"}}
    value["signature"] = signer(authority.canonical_json_bytes(unsigned), amendment.DOMAIN)
    signed = {key: copy.deepcopy(item) for key, item in value.items() if key != "authorization_digest"}
    value["authorization_digest"] = authority.digest_json(signed)
    return value


class GovernanceAmendmentTests(TestCase):
    def patches(self):
        return (
            mock.patch.object(
                amendment, "_accepted_trust_policy",
                return_value=SimpleNamespace(
                    authority_signer_identities=frozenset({ROOT_SIGNER}),
                    legacy_adoption_signer_identities=frozenset({SIGNER}),
                ),
            ),
            mock.patch.object(authority, "_policy_signature_verifier", return_value=verifier),
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
            path = root / "scripts" / "secpal_pr_review" / "governance_amendment.py"
            path.parent.mkdir(parents=True); path.write_text("base\n")
            git("add", "."); git("commit", "-S", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote)); git("push", "origin", "HEAD:main")
            git("switch", "-c", "candidate"); path.write_text("amendment\n")
            git("commit", "-S", "-am", "amendment")
            head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            blob = git("rev-parse", f"HEAD:{path.relative_to(root)}")
            policy = copy.deepcopy(amendment._load_policy())
            policy["accepted_main_sha"] = base
            policy["human_authorization_digest"] = authority.digest_json({
                "authority_identity": policy["human_authority_identity"],
                "repository": "SecPal/.github", "delivery_issue": 960,
                "pull_request": 961, "purpose": amendment.PURPOSE,
                "qualified_source_digest": policy["qualified_source"]["qualification_digest"],
                "accepted_main_sha": base, "decision": "APPROVED", "bounded_uses": 1,
            })
            raw = authorization(
                head=head, tree=tree, parent=base, accepted_main=base,
                changed=[{"path": str(path.relative_to(root)), "blob_oid": blob, "mode": "100644"}],
                policy=policy,
            )
            unsigned = {k: copy.deepcopy(v) for k, v in raw.items() if k not in {"signer_identity", "signature", "authorization_digest"}}
            first, second = self.patches()
            with mock.patch.object(amendment, "ROOT", root), mock.patch.object(amendment, "_remote_url", return_value=str(remote)), mock.patch.object(amendment, "_push_credentials", return_value=nullcontext((root, None))), mock.patch.object(amendment, "_acquire_issuance_facts", return_value=unsigned), mock.patch.object(amendment, "_acquire_execution_facts", return_value=unsigned), mock.patch.object(amendment, "_load_policy", return_value=policy), first, second, mock.patch.object(amendment.execution, "_policy_role_signer", return_value=(SIGNER, signer)):
                authenticated = authority.authenticate_governance_amendment_issuance("SecPal/.github", 960, unsigned)
                issued = authority.issue_governance_amendment_authorization(authenticated)
                result = authority.execute_governance_amendment(issued)
                self.assertEqual(result["status"], "CONSUMED")
                self.assertEqual(git("ls-remote", str(remote), "refs/heads/main").split()[0], result["merge_commit_sha"])
                self.assertEqual(git("show", "-s", "--format=%P", result["merge_commit_sha"]).split(), [base, head])
                accepted_message = git("show", "-s", "--format=%B", result["merge_commit_sha"])
                self.assertIn(issued["authorization_digest"], accepted_message)
                for fabricated in ("lifecycle CURRENT", "Ready transition", "validation receipt"):
                    self.assertNotIn(fabricated, accepted_message)
                with self.assertRaisesRegex(amendment.GovernanceAmendmentError, "protected main changed"):
                    authority.execute_governance_amendment(issued)

    def test_issuer_requires_exact_root_observation_and_sealed_input(self) -> None:
        value = authorization()
        unsigned = {
            key: copy.deepcopy(item) for key, item in value.items()
            if key not in {"signer_identity", "signature", "authorization_digest"}
        }
        changed = copy.deepcopy(unsigned)
        changed["head_sha"] = "9" * 40
        with mock.patch.object(amendment, "_acquire_issuance_facts", return_value=changed):
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "not authenticated"
            ):
                authority.authenticate_governance_amendment_issuance(
                    "SecPal/.github", 960, unsigned
                )
        with self.assertRaisesRegex(
            amendment.GovernanceAmendmentError, "canonical authenticated"
        ):
            authority.issue_governance_amendment_authorization(unsigned)

    def test_root_observations_are_signed_canonical_and_phase_bound(self) -> None:
        facts = {
            key: copy.deepcopy(item) for key, item in authorization().items()
            if key not in {"signer_identity", "signature", "authorization_digest"}
        }
        fields = {
            "schema_version": "1.0",
            "kind": amendment.ROOT_OBSERVATION_KIND,
            "domain": amendment.ROOT_OBSERVATION_DOMAIN,
            "phase": "ISSUANCE",
            "facts": facts,
            "signer_identity": ROOT_SIGNER,
        }
        signed = {
            **fields,
            "signature": root_signer(
                authority.canonical_json_bytes(fields),
                amendment.ROOT_OBSERVATION_DOMAIN,
            ),
        }
        envelope = {
            **signed,
            "observation_digest": authority.digest_json(signed),
        }
        trust = SimpleNamespace(
            authority_signer_identities=frozenset({ROOT_SIGNER})
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observation.json"
            path.write_bytes(authority.canonical_json_bytes(envelope))
            path.chmod(0o600)
            with mock.patch.dict(
                "os.environ",
                {"SECPAL_GOVERNANCE_AMENDMENT_ISSUANCE": str(path)},
            ), mock.patch.object(
                amendment, "_accepted_trust_policy", return_value=trust
            ), mock.patch.object(
                authority, "_policy_signature_verifier", return_value=root_verifier
            ):
                self.assertEqual(
                    amendment._acquire_issuance_facts("SecPal/.github", 960),
                    facts,
                )
                with self.assertRaisesRegex(
                    amendment.GovernanceAmendmentError, "not canonical"
                ):
                    amendment._read_root_observation(
                        "SECPAL_GOVERNANCE_AMENDMENT_ISSUANCE",
                        "EXECUTION", "SecPal/.github", 960,
                    )
            path.write_bytes(authority.canonical_json_bytes(envelope) + b"\n")
            with mock.patch.dict(
                "os.environ",
                {"SECPAL_GOVERNANCE_AMENDMENT_ISSUANCE": str(path)},
            ):
                with self.assertRaisesRegex(
                    amendment.GovernanceAmendmentError, "not canonical"
                ):
                    amendment._acquire_issuance_facts("SecPal/.github", 960)

    def test_executor_reauthenticates_all_facts_before_any_git_mutation(self) -> None:
        value = authorization()
        current = {
            key: copy.deepcopy(item) for key, item in value.items()
            if key not in {"signer_identity", "signature", "authorization_digest"}
        }
        current["feedback"]["material_finding_ids"] = ["blocking"]
        first, second = self.patches()
        with first, second, mock.patch.object(
            amendment, "_remote_url", return_value="unused"
        ), mock.patch.object(
            amendment, "_acquire_execution_facts", return_value=current
        ), mock.patch.object(amendment, "_run_git") as run_git:
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "prerequisites changed"
            ):
                authority.execute_governance_amendment(value)
        run_git.assert_not_called()

    def test_concurrent_main_change_rejects_without_force_or_rewrite(self) -> None:
        attempted: list[str] = []

        def reject_push(
            _root: Path, arguments: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            attempted.extend(arguments)
            return subprocess.CompletedProcess(arguments, 1, b"", b"rejected")

        with mock.patch.object(
            amendment, "_push_credentials",
            return_value=nullcontext((Path("."), None)),
        ), mock.patch.object(amendment, "_run_git", side_effect=reject_push):
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "compare-and-swap"
            ):
                amendment._push_protected_main(
                    Path("."), "origin", "f" * 40, "SecPal/.github",
                    "e" * 40,
                )
        self.assertEqual(
            attempted,
            ["push", "--porcelain", "origin", f"{'f' * 40}:refs/heads/main"],
        )
        self.assertFalse(any("force" in argument for argument in attempted))

    def test_scope_and_absence_substitutions_fail_closed(self) -> None:
        mutations = {
            "repository": lambda v: v.update(repository="SecPal/api"),
            "issue": lambda v: v.update(delivery_issue=959),
            "pull request": lambda v: v.update(pull_request=962),
            "head": lambda v: v.update(head_sha="9" * 40),
            "tree": lambda v: v.update(tree_sha="9" * 40),
            "parents": lambda v: v.update(ordered_parent_shas=["9" * 40]),
            "source signer": lambda v: v["source_signature"].update(signer_identity="other"),
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

    def test_policy_requires_the_accepted_registry_entry(self) -> None:
        value = authorization()
        first, second = self.patches()
        real_loads = amendment.json.loads

        def unregistered(raw: str):
            parsed = real_loads(raw)
            if isinstance(parsed, dict) and "repositories" in parsed:
                parsed["repositories"][0].pop("governance_amendment_policy")
            return parsed

        with first, second, mock.patch.object(amendment.json, "loads", side_effect=unregistered):
            with self.assertRaisesRegex(
                amendment.GovernanceAmendmentError, "not registered"
            ):
                amendment.verify(value)

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
