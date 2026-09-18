#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
from contextlib import nullcontext
import hashlib
import json
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
    accepted_main: str = "3887b00e1b84ef0d14ab2846507a3100512c2c28",
    changed: list[dict[str, str]] | None = None,
    source_oids: list[str] | None = None,
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    policy = policy or proposed_policy()
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
        "signature_evidence_digest": authority.digest_json({
            "source_commits": value["source_commits"],
            "accepted_main_sha": accepted_main,
        }),
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
        for key in amendment.OBSERVATION_INPUT_FIELDS
    }


class GovernanceAmendmentTests(TestCase):
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

    def hermetic_repository(
        self, directory: str, *, attacker_intermediate: bool,
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
        git("commit", "-S", "-m", "base")
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
            path = root / "scripts" / "secpal_pr_review" / "governance_amendment.py"
            path.parent.mkdir(parents=True); path.write_text("base\n")
            git("add", "."); git("commit", "-S", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(remote)); git("push", "origin", "HEAD:main")
            git("switch", "-c", "candidate"); path.write_text("amendment\n")
            git("commit", "-S", "-am", "amendment")
            head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            blob = git("rev-parse", f"HEAD:{path.relative_to(root)}")
            policy = copy.deepcopy(proposed_policy())
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
            issuance_facts = {
                k: copy.deepcopy(v) for k, v in raw.items()
                if k not in {
                    "root_authorization", "signer_identity", "signature",
                    "authorization_digest",
                }
            }
            trusted_signer = authority.TrustedSigner(
                SOURCE,
                (key.with_suffix(".pub").read_text().strip(),),
                (),
            )
            trust = SimpleNamespace(
                authority_signer_identities=frozenset({ROOT_SIGNER}),
                legacy_adoption_signer_identities=frozenset({SIGNER}),
                signers={SOURCE: trusted_signer},
            )
            first, second = self.patches(trust)
            def role_signer(_trust, identities, _label, **_kwargs):
                if identities == trust.authority_signer_identities:
                    return ROOT_SIGNER, root_signer
                return SIGNER, signer

            with mock.patch.object(amendment, "ROOT", root), mock.patch.object(amendment, "_remote_url", return_value=str(remote)), mock.patch.object(amendment, "_push_credentials", return_value=nullcontext((root, None))), mock.patch.object(amendment, "produce_observation", return_value=issuance_facts), first, second, mock.patch.object(amendment.execution, "_policy_role_signer", side_effect=role_signer):
                authenticated = authority.authenticate_governance_amendment_issuance("SecPal/.github", 960, observation_inputs(raw))
                issued = authority.issue_governance_amendment_authorization(authenticated)
                result = authority.execute_governance_amendment(issued)
                self.assertEqual(result["status"], "CONSUMED")
                self.assertEqual(git("ls-remote", str(remote), "refs/heads/main").split()[0], result["merge_commit_sha"])
                self.assertEqual(git("show", "-s", "--format=%P", result["merge_commit_sha"]).split(), [base, head])
                accepted_message = git("show", "-s", "--format=%B", result["merge_commit_sha"])
                self.assertIn(issued["authorization_digest"], accepted_message)
                for fabricated in ("lifecycle CURRENT", "Ready transition", "validation receipt"):
                    self.assertNotIn(fabricated, accepted_message)
                with self.assertRaisesRegex(
                    amendment.GovernanceAmendmentError,
                    "protected main changed",
                ):
                    authority.execute_governance_amendment(issued)

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
            facts["natural_ci"] = {
                "head_sha": repo["head"],
                "workflow_identity": amendment.LIVE_OBSERVATION_VERSION,
                "result": "PASS",
                "evidence_digest": authority.digest_json({
                    "checks": checks, "statuses": statuses,
                }),
            }
            threads: list[dict[str, object]] = []
            reviews = [{
                "state": "COMMENTED", "commit": {"oid": repo["head"]},
                "author": {"login": "review-bot"},
            }]
            facts["feedback"] = {
                "state_digest": authority.digest_json({
                    "head_sha": repo["head"], "pull_request": 961,
                }),
                "feedback_digest": authority.digest_json({
                    "threads": threads, "reviews": reviews,
                }),
                "thread_inventory_digest": authority.digest_json({
                    "threads": threads,
                }),
                "material_finding_ids": [],
            }
            facts["source_signature"] = {
                "signer_identity": SOURCE,
                "signature_evidence_digest": authority.digest_json({
                    "source_commits": facts["source_commits"],
                    "accepted_main_sha": repo["base"],
                }),
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
                "number": 961, "state": "open", "draft": True,
                "merged": False,
                "head": {"sha": repo["head"], "repo": {"full_name": "SecPal/.github"}},
                "base": {"sha": repo["base"], "ref": "main", "repo": {"full_name": "SecPal/.github"}},
            }
            issue = {"number": 960, "state": "open"}
            feedback = {"data": {"repository": {"pullRequest": {
                "reviewThreads": {"nodes": threads, "pageInfo": {"hasNextPage": False}},
                "reviews": {"nodes": reviews, "pageInfo": {"hasNextPage": False}},
            }}}}

            def github(arguments: list[str]):
                joined = " ".join(arguments)
                if "pulls/961" in joined:
                    value = pull
                elif "issues/960" in joined:
                    value = issue
                elif "check-runs" in joined:
                    value = {"check_runs": checks}
                elif "/status" in joined:
                    value = {"state": "pending", "statuses": statuses}
                elif "graphql" in arguments:
                    value = feedback
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
            ), first, second:
                observed = authority.observe_governance_amendment_issuance(
                    "SecPal/.github", 960, inputs
                )
                self.assertEqual(observed, facts)
                mutations = {
                    "stale head": lambda value: value[
                        "independent_qualification"
                    ].update(head_sha="9" * 40),
                    "stale main": lambda value: value.update(
                        accepted_main_sha="9" * 40
                    ),
                }
                for label, mutate in mutations.items():
                    stale = copy.deepcopy(inputs)
                    mutate(stale)
                    with self.subTest(label=label), self.assertRaises(
                        amendment.GovernanceAmendmentError
                    ):
                        authority.observe_governance_amendment_issuance(
                            "SecPal/.github", 960, stale
                        )
            signer_factory.assert_not_called()

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

    def test_candidate_policy_and_registry_are_not_authority(self) -> None:
        value = authorization()
        first, second = self.patches()
        with first, second, mock.patch.object(
            amendment.Path, "read_text",
            side_effect=AssertionError("candidate policy was consulted"),
        ):
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

    def test_wrong_key_merge_fails_before_remote_mutation(self) -> None:
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
            repo["git"]("config", "user.signingkey", str(repo["attacker"]))
            first, second = self.patches(trust)
            with mock.patch.object(
                amendment, "ROOT", repo["root"]
            ), mock.patch.object(
                amendment, "_remote_url", return_value=str(repo["remote"])
            ), mock.patch.object(
                amendment, "_push_credentials",
                return_value=nullcontext((repo["root"], None)),
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
