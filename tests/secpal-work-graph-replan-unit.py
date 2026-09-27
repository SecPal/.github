#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Behavior evidence for bounded graph-first replanning operations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secpal_work_graph import github, github_replanning, model, replanning  # noqa: E402

REPO = "SecPal/.github"


def trusted_test_executable(name: str) -> Path:
    """Resolve a test tool through the same finite directories production trusts."""

    for directory in replanning.TRUSTED_GIT_DIRECTORIES:
        candidate = (directory / name).resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(f"required trusted test executable is unavailable: {name}")


@contextmanager
def hermetic_signing_account(signer_format: str):
    """Provide an isolated OS-account Git signer without ambient configuration."""

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        account_home = root / "account"
        repository = root / "repository"
        account_home.mkdir(mode=0o700)
        git = trusted_test_executable("git")
        ssh_keygen = trusted_test_executable("ssh-keygen")
        gpg = trusted_test_executable("gpg")
        previous_home = replanning.ACCOUNT_HOME
        try:
            replanning.ACCOUNT_HOME = account_home
            environment = replanning.GitRecoverySigner._environment()
            subprocess.run([str(git), "init", "-q", str(repository)], check=True, env=environment)
            for key_name, value in (
                ("user.name", "Recovery Test"),
                ("user.email", "recovery@example.invalid"),
                ("gpg.format", signer_format),
            ):
                subprocess.run(
                    [str(git), "config", "--global", key_name, value],
                    check=True,
                    env=environment,
                )

            if signer_format == "ssh":
                signing_key = account_home / "recovery-signing-key"
                subprocess.run(
                    [
                        str(ssh_keygen),
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        str(signing_key),
                    ],
                    check=True,
                    env=environment,
                )
                allowed_signers = account_home / "allowed-signers"
                allowed_signers.write_text(
                    "recovery@example.invalid "
                    + signing_key.with_suffix(".pub").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                signer_identity = str(signing_key)
                extra_config = (
                    ("user.signingkey", signer_identity),
                    ("gpg.ssh.allowedSignersFile", str(allowed_signers)),
                )
            elif signer_format == "openpgp":
                gnupg = account_home / ".gnupg"
                gnupg.mkdir(mode=0o700)
                subprocess.run(
                    [
                        str(gpg),
                        "--batch",
                        "--homedir",
                        str(gnupg),
                        "--passphrase",
                        "",
                        "--quick-generate-key",
                        "Recovery Test <recovery@example.invalid>",
                        "ed25519",
                        "sign",
                        "0",
                    ],
                    check=True,
                    capture_output=True,
                    env=environment,
                )
                listing = subprocess.run(
                    [
                        str(gpg),
                        "--batch",
                        "--homedir",
                        str(gnupg),
                        "--with-colons",
                        "--list-secret-keys",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=environment,
                ).stdout
                signer_identity = next(
                    line.split(":")[9]
                    for line in listing.splitlines()
                    if line.startswith("fpr:")
                )
                allowed_signers = None
                extra_config = (("user.signingkey", signer_identity),)
            else:
                raise ValueError(f"unsupported test signing format: {signer_format}")

            for key_name, value in extra_config:
                subprocess.run(
                    [str(git), "config", "--global", key_name, value],
                    check=True,
                    env=environment,
                )
            subprocess.run(
                [
                    str(git),
                    "-C",
                    str(repository),
                    "commit",
                    "--allow-empty",
                    "--no-gpg-sign",
                    "-m",
                    "root",
                ],
                check=True,
                capture_output=True,
                env=environment,
            )
            yield {
                "account_home": account_home,
                "allowed_signers": allowed_signers,
                "environment": environment,
                "git": git,
                "gpg": gpg,
                "repository": repository,
                "signer_identity": signer_identity,
                "ssh_keygen": ssh_keygen,
            }
        finally:
            replanning.ACCOUNT_HOME = previous_home


def key(number: int) -> str:
    return model.node_key(REPO, number)


def node(number: int, **overrides) -> model.Node:
    fields = {
        "repository": REPO,
        "number": number,
        "node_id": f"ISSUE_{number}",
        "repository_id": "REPO_ID",
        "has_acceptance_criteria": True,
        "blocking_observable": True,
    }
    fields.update(overrides)
    if "blocking" in overrides and "blocking_count" not in overrides:
        fields["blocking_count"] = len(overrides["blocking"])
    return model.Node(**fields)


def graph(*nodes: model.Node) -> model.Snapshot:
    return model.build_snapshot(nodes)


def finding(name: str, **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "classification": name,
        "technically_blocking": False,
        "mechanically_blocking": False,
        "timing": "BEFORE_FREEZE",
        "risk": [],
    }
    value.update(overrides)
    return value


def signer_document(operation_digest: str, **state_overrides) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": replanning.RECOVERY_SCHEMA,
        "plan_digest": operation_digest,
        "actor": "alice",
        "current_issue": key(1),
        "snapshot_digest": "0" * 64,
        "baseline": [],
        "outcome": "NO_WRITES",
        "next_step": 0,
        "attempting_step": None,
        "created": {},
    }
    document.update(state_overrides)
    document["journal_digest"] = replanning.recovery_document_digest(document)
    return document


def signer_evidence(document, authentication):
    return {**document, "authentication": authentication}


def recovery_plan(*steps):
    baseline = graph(node(1))
    plan = replanning.Plan(
        actor="alice",
        classification=replanning.Classification(
            "MISSING_PREREQUISITE",
            "INSERT_PREREQUISITE",
            True,
            True,
            "BEFORE_FREEZE",
            ("P2",),
        ),
        current_issue=key(1),
        owner=None,
        snapshot_digest=replanning.snapshot_digest(baseline),
        steps=tuple(steps),
        request={},
    )
    return plan, baseline


def recovery_state(plan, baseline, **overrides):
    document = {
        "schema": replanning.RECOVERY_SCHEMA,
        "plan_digest": replanning.plan_digest(plan),
        "actor": plan.actor,
        "current_issue": plan.current_issue,
        "snapshot_digest": plan.snapshot_digest,
        "baseline": replanning.snapshot_document(baseline),
        "outcome": "NO_WRITES",
        "next_step": 0,
        "attempting_step": None,
        "created": {},
    }
    document.update(overrides)
    document["journal_digest"] = replanning.recovery_document_digest(document)
    return document


def created_identity(number, *, repository=REPO):
    return {
        "key": f"{repository}#{number}",
        "node_id": f"ISSUE_{number}",
        "repository_id": f"REPOSITORY_{repository}",
    }


def recovery_child_commit(fixture, parent, message, *, signing_key=None, signed=True):
    repository = fixture["repository"]
    tree = subprocess.run(
        [str(fixture["git"]), "-C", str(repository), "rev-parse", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
        env=fixture["environment"],
    ).stdout.strip()
    command = [str(fixture["git"]), "-C", str(repository)]
    if signing_key is not None:
        command.extend(["-c", f"user.signingkey={signing_key}"])
    command.extend(["commit-tree", *( ["-S"] if signed else []), tree, "-p", parent])
    return subprocess.run(
        command,
        check=True,
        input=message.rstrip() + "\n",
        capture_output=True,
        text=True,
        env=fixture["environment"],
    ).stdout.strip()


def advance_recovery_ref(fixture, authentication, commit_oid):
    subprocess.run(
        [
            str(fixture["git"]),
            "-C",
            str(fixture["repository"]),
            "update-ref",
            authentication["ref"],
            commit_oid,
            authentication["commit_oid"],
        ],
        check=True,
        env=fixture["environment"],
    )


class FakeRecoverySigner:
    def sign(self, operation_digest, document, previous=None):
        return {
            "kind": "test-signature",
            "value": "signed:" + operation_digest + ":" + document["journal_digest"],
        }

    def verify(self, authentication, operation_digest, document):
        if authentication != {
            "kind": "test-signature",
            "value": "signed:" + operation_digest + ":" + document["journal_digest"],
        }:
            raise replanning.StalePlanError("recovery authentication is invalid")
        return None


class ClassificationTests(TestCase):
    def test_each_classification_selects_exactly_one_bounded_action(self):
        expected = {
            "IN_CONTRACT_DEFECT": "KEEP_IN_CURRENT_CONTRACT",
            "MISSING_PREREQUISITE": "INSERT_PREREQUISITE",
            "NEW_RESPONSIBILITY": "CREATE_OWNED_SIBLING",
            "PROMOTE_TO_SUB_EPIC": "PROMOTE_TO_SUB_EPIC",
            "NON_BLOCKING_FOLLOWUP": "CREATE_OWNED_FOLLOWUP",
            "INVALID_FINDING": "REJECT_WITH_EVIDENCE",
        }
        for classification, action in expected.items():
            facts = finding(classification)
            if classification in {
                "IN_CONTRACT_DEFECT",
                "MISSING_PREREQUISITE",
                "PROMOTE_TO_SUB_EPIC",
            }:
                facts["technically_blocking"] = True
            if classification == "NON_BLOCKING_FOLLOWUP":
                facts["timing"] = "AFTER_FREEZE"
            with self.subTest(classification=classification):
                self.assertEqual(replanning.classify(facts).action, action)

    def test_blocking_facts_remain_independent(self):
        result = replanning.classify(
            finding(
                "NON_BLOCKING_FOLLOWUP",
                timing="AFTER_FREEZE",
                technically_blocking=False,
                mechanically_blocking=True,
                risk=["P3"],
            )
        )
        self.assertFalse(result.technically_blocking)
        self.assertTrue(result.mechanically_blocking)

    def test_pre_freeze_in_contract_defect_stays_in_current_contract_without_a_technical_blocker(self):
        for risk, mechanical in (("P3", True), ("INFORMATIONAL", False)):
            with self.subTest(risk=risk, mechanically_blocking=mechanical):
                result = replanning.validate_request(
                    {
                        "current_issue": key(2),
                        "finding": finding(
                            "IN_CONTRACT_DEFECT",
                            technically_blocking=False,
                            mechanically_blocking=mechanical,
                            risk=[risk],
                        ),
                        "operation": {"kind": "KEEP_IN_CURRENT_CONTRACT"},
                    }
                )
                self.assertEqual(result.action, "KEEP_IN_CURRENT_CONTRACT")
                self.assertFalse(result.technically_blocking)
                self.assertEqual(result.mechanically_blocking, mechanical)

    def test_rollout_prerequisite_does_not_become_a_technical_blocker(self):
        result = replanning.classify(
            finding(
                "MISSING_PREREQUISITE",
                technically_blocking=False,
                mechanically_blocking=True,
                risk=["P3"],
            )
        )
        self.assertEqual(result.action, "INSERT_PREREQUISITE")
        self.assertFalse(result.technically_blocking)
        self.assertTrue(result.mechanically_blocking)

    def test_promotion_requirement_does_not_become_a_technical_blocker(self):
        result = replanning.classify(
            finding(
                "PROMOTE_TO_SUB_EPIC",
                technically_blocking=False,
                mechanically_blocking=True,
                risk=["INFORMATIONAL"],
            )
        )
        self.assertEqual(result.action, "PROMOTE_TO_SUB_EPIC")
        self.assertFalse(result.technically_blocking)
        self.assertTrue(result.mechanically_blocking)

    def test_high_risk_findings_cannot_use_non_blocking_follow_up(self):
        for risk in ("P1", "P2", "SECURITY", "AUTHENTICATION", "INTEGRITY", "FAIL_OPEN"):
            with self.subTest(risk=risk), self.assertRaises(replanning.PlanError):
                replanning.classify(
                    finding(
                        "NON_BLOCKING_FOLLOWUP",
                        timing="AFTER_FREEZE",
                        risk=[risk],
                    )
                )

    def test_in_contract_defect_cannot_escape_to_a_follow_up_before_freeze(self):
        with self.assertRaisesRegex(replanning.PlanError, "current contract"):
            replanning.validate_request(
                {
                    "current_issue": key(2),
                    "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
                    "operation": {"kind": "CREATE_OWNED_FOLLOWUP"},
                }
            )

    def test_post_freeze_high_risk_defect_stays_in_current_contract(self):
        result = replanning.validate_request(
            {
                "current_issue": key(2),
                "finding": finding(
                    "IN_CONTRACT_DEFECT",
                    timing="AFTER_FREEZE",
                    technically_blocking=True,
                    mechanically_blocking=True,
                    risk=["P1", "INTEGRITY"],
                ),
                "operation": {"kind": "KEEP_IN_CURRENT_CONTRACT"},
            }
        )
        self.assertEqual(result.action, "KEEP_IN_CURRENT_CONTRACT")
        self.assertTrue(result.technically_blocking)


class PlanningTests(TestCase):
    def setUp(self):
        self.snapshot = graph(
            node(1, children=(key(2), key(9))),
            node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
            node(3, blocking=(key(2),)),
            node(8, blocked_by=(key(2),)),
            node(9, parent=key(1)),
        )

    def test_new_responsibility_is_owned_and_keeps_siblings_parallel(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Deliver separate work",
                    "body": "## Acceptance Criteria\n\n- Delivered independently.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        self.assertEqual(plan.owner, key(1))
        self.assertEqual(
            [step.kind for step in plan.steps],
            ["CREATE_ISSUE", "REPRIORITIZE_SUB_ISSUE"],
        )
        self.assertFalse(any(step.kind == "ADD_BLOCKED_BY" for step in plan.steps))
        self.assertEqual(plan.steps[1].arguments["after"], key(2))

    def test_obsolete_dependency_removal_plans_the_exact_existing_edge(self):
        request = {
            "current_issue": key(2),
            "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
                "contract_no_longer_requires_blocker": True,
            },
        }

        plan = replanning.build_plan(self.snapshot, request, actor="alice")

        self.assertEqual(
            [(step.kind, dict(step.arguments)) for step in plan.steps],
            [("REMOVE_BLOCKED_BY", {"blocked": key(2), "blocker": key(3)})],
        )

    def test_obsolete_dependency_removal_changes_only_the_planned_edge(self):
        request = {
            "current_issue": key(2),
            "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
                "contract_no_longer_requires_blocker": True,
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        after = graph(
            node(1, children=(key(2), key(9))),
            node(2, parent=key(1), blocking=(key(8),)),
            node(3),
            node(8, blocked_by=(key(2),)),
            node(9, parent=key(1)),
        )

        replanning.verify_applied(plan, after, {})
        replanning.verify_unchanged_relationships(plan, self.snapshot, after, {})

    def test_obsolete_dependency_removal_requires_exact_observable_edge(self):
        request = {
            "current_issue": key(2),
            "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
                "contract_no_longer_requires_blocker": True,
            },
        }
        cases = {
            "edge_absent": graph(
                node(1, children=(key(2), key(9))),
                node(2, parent=key(1), blocking=(key(8),)),
                node(3),
                node(8, blocked_by=(key(2),)),
                node(9, parent=key(1)),
            ),
            "forward_incomplete": graph(
                node(1, children=(key(2), key(9))),
                node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),), dependencies_observable=False),
                node(3, blocking=(key(2),)),
                node(8, blocked_by=(key(2),)),
                node(9, parent=key(1)),
            ),
            "reverse_incomplete": graph(
                node(1, children=(key(2), key(9))),
                node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
                node(3, blocking=(key(2),), blocking_observable=False),
                node(8, blocked_by=(key(2),)),
                node(9, parent=key(1)),
            ),
            "reverse_count_inconsistent": graph(
                node(1, children=(key(2), key(9))),
                node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
                node(3, blocking=(key(2),), blocking_count=2),
                node(8, blocked_by=(key(2),)),
                node(9, parent=key(1)),
            ),
        }

        for label, snapshot in cases.items():
            with self.subTest(label=label), self.assertRaises(replanning.PlanError):
                replanning.build_plan(snapshot, request, actor="alice")

    def test_obsolete_dependency_removal_requires_explicit_current_contract_judgment(self):
        base = {
            "current_issue": key(2),
            "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
            },
        }
        for value in (None, False):
            request = json.loads(json.dumps(base))
            if value is not None:
                request["operation"]["contract_no_longer_requires_blocker"] = value
            with self.subTest(value=value), self.assertRaises(replanning.PlanError):
                replanning.build_plan(self.snapshot, request, actor="alice")

    def test_other_classifications_and_bare_current_contract_intent_cannot_remove_dependency(self):
        removal = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
                "contract_no_longer_requires_blocker": True,
            },
        }
        with self.assertRaises(replanning.PlanError):
            replanning.build_plan(self.snapshot, removal, actor="alice")
        bare = replanning.build_plan(
            self.snapshot,
            {
                "current_issue": key(2),
                "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
                "operation": {"kind": "KEEP_IN_CURRENT_CONTRACT"},
            },
            actor="alice",
        )
        self.assertEqual(bare.steps, ())

    def test_obsolete_dependency_recovery_accepts_only_the_exact_removed_edge(self):
        before = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1), blocked_by=(key(3), key(4))),
            node(3, blocking=(key(2),)),
            node(4, blocking=(key(2),)),
        )
        request = {
            "current_issue": key(2),
            "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
                "contract_no_longer_requires_blocker": True,
            },
        }
        plan = replanning.build_plan(before, request, actor="alice")
        exact_after = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1), blocked_by=(key(4),)),
            node(3),
            node(4, blocking=(key(2),)),
        )
        substituted_after = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1), blocked_by=(key(3),)),
            node(3, blocking=(key(2),)),
            node(4),
        )
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            journal.start(before)
            journal.begin_step(0)
            journal.complete_step(0, None)

            recovered, baseline, aliases, next_step = replanning.recover_plan(
                plan.to_dict(), exact_after, actor="alice", recovery=journal
            )

            self.assertEqual(recovered, plan)
            self.assertEqual(baseline, before)
            self.assertEqual(aliases, {})
            self.assertEqual(next_step, 1)
            with self.assertRaisesRegex(replanning.StalePlanError, "prefix"):
                replanning.recover_plan(
                    plan.to_dict(), substituted_after, actor="alice", recovery=journal
                )

    def test_post_freeze_follow_up_is_owned_without_a_technical_dependency(self):
        request = {
            "current_issue": key(2),
            "finding": finding(
                "NON_BLOCKING_FOLLOWUP",
                timing="AFTER_FREEZE",
                mechanically_blocking=True,
                risk=["INFORMATIONAL"],
            ),
            "operation": {
                "kind": "CREATE_OWNED_FOLLOWUP",
                "issue": {
                    "alias": "follow-up",
                    "repository": REPO,
                    "title": "Track later improvement",
                    "body": "## Acceptance Criteria\n\n- Improvement is delivered.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        self.assertEqual(plan.owner, key(1))
        self.assertNotIn("ADD_BLOCKED_BY", [step.kind for step in plan.steps])

    def test_existing_cross_repository_prerequisite_keeps_its_owner(self):
        prerequisite = model.Node(
            repository="SecPal/api",
            number=44,
            node_id="API_44",
            repository_id="API_REPO",
            has_acceptance_criteria=True,
            blocking_observable=True,
        )
        snapshot = model.build_snapshot((*self.snapshot.nodes.values(), prerequisite))
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "existing_issue": "SecPal/api#44",
                "move_current_blockers": [],
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        self.assertEqual([step.kind for step in plan.steps], ["ADD_BLOCKED_BY"])
        self.assertEqual(plan.steps[0].arguments["blocked"], key(2))
        self.assertEqual(plan.steps[0].arguments["blocker"], "SecPal/api#44")

    def test_new_prerequisite_for_root_leaf_creates_native_epic_first(self):
        snapshot = graph(node(2))
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "epic": {
                    "alias": "aggregate",
                    "repository": REPO,
                    "title": "Coordinate aggregate delivery",
                    "body": "## Acceptance Criteria\n\n- Both contracts are complete.\n",
                },
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Provide prerequisite",
                    "body": "## Acceptance Criteria\n\n- Output exists.\n",
                },
                "move_current_blockers": [],
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        self.assertEqual(plan.owner, "@aggregate")
        self.assertEqual(
            [step.kind for step in plan.steps],
            [
                "CREATE_ISSUE",
                "ADD_SUB_ISSUE",
                "CREATE_ISSUE",
                "REPRIORITIZE_SUB_ISSUE",
                "ADD_BLOCKED_BY",
            ],
        )
        self.assertIsNone(plan.steps[0].arguments["parent"])
        self.assertEqual(plan.steps[1].arguments["child"], key(2))

    def test_inserted_prerequisite_rewires_only_named_edges(self):
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Provide prerequisite",
                    "body": "## Acceptance Criteria\n\n- Required output exists.\n",
                },
                "move_current_blockers": [key(3)],
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        edges = [(step.kind, dict(step.arguments)) for step in plan.steps if "BLOCKED_BY" in step.kind]
        self.assertEqual(
            edges,
            [
                ("ADD_BLOCKED_BY", {"blocked": "@prerequisite", "blocker": key(3)}),
                ("ADD_BLOCKED_BY", {"blocked": key(2), "blocker": "@prerequisite"}),
                ("REMOVE_BLOCKED_BY", {"blocked": key(2), "blocker": key(3)}),
            ],
        )

    def test_planned_dependency_cycle_fails_before_mutation(self):
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "existing_issue": key(8),
                "move_current_blockers": [],
            },
        }
        with self.assertRaisesRegex(replanning.PlanError, "canonical structural"):
            replanning.build_plan(self.snapshot, request, actor="alice")

    def test_intermediate_native_dependency_limit_fails_before_mutation(self):
        dependents = tuple(key(number) for number in range(100, 149))
        snapshot = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1), blocked_by=(key(3),)),
            node(
                3,
                blocking=(key(2), *dependents),
                blocking_count=model.MAX_DEPENDENCIES_PER_TYPE,
            ),
            *(node(number, blocked_by=(key(3),)) for number in range(100, 149)),
        )
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Provide prerequisite",
                    "body": "## Acceptance Criteria\n\n- Required output exists.\n",
                },
                "move_current_blockers": [key(3)],
            },
        }
        with self.assertRaisesRegex(replanning.PlanError, "canonical structural"):
            replanning.build_plan(snapshot, request, actor="alice")

    def test_promotion_requires_exhaustive_edge_placement(self):
        incomplete = {
            "current_issue": key(2),
            "finding": finding("PROMOTE_TO_SUB_EPIC", technically_blocking=True),
            "operation": {
                "kind": "PROMOTE_TO_SUB_EPIC",
                "children": [],
                "blocked_by_placement": {},
                "blocking_placement": {},
            },
        }
        with self.assertRaisesRegex(replanning.PlanError, "every existing"):
            replanning.build_plan(self.snapshot, incomplete, actor="alice")

    def test_promotion_repoints_only_semantically_selected_edges(self):
        request = {
            "current_issue": key(2),
            "finding": finding("PROMOTE_TO_SUB_EPIC", technically_blocking=True),
            "operation": {
                "kind": "PROMOTE_TO_SUB_EPIC",
                "children": [
                    {
                        "alias": "contract-a",
                        "repository": REPO,
                        "title": "Contract A",
                        "body": "## Acceptance Criteria\n\n- A is delivered.\n",
                    },
                    {
                        "alias": "contract-b",
                        "repository": REPO,
                        "title": "Contract B",
                        "body": "## Acceptance Criteria\n\n- B is delivered.\n",
                    },
                ],
                "blocked_by_placement": {key(3): ["contract-a"]},
                "blocking_placement": {key(8): ["contract-b"]},
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        edges = [(step.kind, dict(step.arguments)) for step in plan.steps if "BLOCKED_BY" in step.kind]
        self.assertEqual(
            edges,
            [
                ("ADD_BLOCKED_BY", {"blocked": "@contract-a", "blocker": key(3)}),
                ("REMOVE_BLOCKED_BY", {"blocked": key(2), "blocker": key(3)}),
                ("ADD_BLOCKED_BY", {"blocked": key(8), "blocker": "@contract-b"}),
                ("REMOVE_BLOCKED_BY", {"blocked": key(8), "blocker": key(2)}),
            ],
        )
        self.assertNotIn("ADD_CHILD_DEPENDENCY", [step.kind for step in plan.steps])

    def test_snapshot_drift_fails_before_any_mutation(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        changed = graph(
            node(1, children=(key(9), key(2))),
            *[item for item in self.snapshot.nodes.values() if item.number != 1],
        )
        writer = replanning.RecordingWriter()
        with self.assertRaisesRegex(replanning.StalePlanError, "drift"):
            replanning.apply_plan(plan, changed, actor="alice", writer=writer)
        self.assertEqual(writer.calls, [])

    def test_post_mutation_verification_rejects_unrelated_relationship_changes(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        after = graph(
            node(1, children=(key(2), key(10), key(9))),
            node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
            node(3, blocking=(key(2),)),
            node(8, blocked_by=(key(2),)),
            # This unrelated node was re-parented during the operation.
            node(9, parent=None),
            node(10, parent=key(1)),
        )
        with self.assertRaisesRegex(replanning.PlanError, "unrelated"):
            replanning.verify_unchanged_relationships(
                plan,
                self.snapshot,
                after,
                {
                    "new-work": replanning.CreatedIssueIdentity(
                        key=key(10), node_id="ISSUE_10", repository_id="REPO_ID"
                    )
                },
            )

    def test_created_issue_is_verified_as_an_exact_postcondition(self):
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(self.snapshot, request, actor="alice")
        identity = replanning.CreatedIssueIdentity(
            key=key(10), node_id="ISSUE_10", repository_id="REPO_ID"
        )
        expected_body = replanning.created_issue_body(plan, 0)
        base_created = node(
            10,
            parent=key(1),
            title="Separate work",
            body_digest=replanning.content_digest(expected_body),
        )
        cases = {
            "content": node(
                10,
                parent=key(1),
                title="Separate work",
                body_digest=replanning.content_digest("changed"),
            ),
            "dependency": model.Node(
                **{
                    **base_created.__dict__,
                    "blocked_by": (key(3),),
                }
            ),
            "unobservable": model.Node(
                **{
                    **base_created.__dict__,
                    "dependencies_observable": False,
                }
            ),
        }
        for label, created in cases.items():
            after = graph(
                node(1, children=(key(2), key(10), key(9))),
                node(2, parent=key(1), blocked_by=(key(3),), blocking=(key(8),)),
                node(3, blocking=(key(2),)),
                node(8, blocked_by=(key(2),)),
                node(9, parent=key(1)),
                created,
            )
            with self.subTest(label=label), self.assertRaises(replanning.PlanError):
                replanning.verify_applied(plan, after, {"new-work": identity})


class MutationBoundaryTests(TestCase):
    class FakeAdapter:
        def __init__(self):
            self.calls = []
            self.next_issue = 10

        def query(self, document, variables):
            self.calls.append((document, variables))
            if "WorkGraphViewer" in document:
                return github.GraphQLResponse({"viewer": {"login": "alice"}}, ())
            if "ReplanCreateIssue" in document:
                number = self.next_issue
                self.next_issue += 1
                return github.GraphQLResponse(
                    {
                        "createIssue": {
                            "issue": {
                                "id": f"ISSUE_{number}",
                                "number": number,
                                "url": f"https://github.com/SecPal/.github/issues/{number}",
                                "repository": {"id": "REPO_ID", "nameWithOwner": REPO},
                                "parent": (
                                    {"id": variables["input"]["parentIssueId"]}
                                    if "parentIssueId" in variables["input"]
                                    else None
                                ),
                            }
                        }
                    },
                    (),
                )
            if "ReplanPrioritizeSubIssue" in document:
                return github.GraphQLResponse(
                    {
                        "reprioritizeSubIssue": {
                            "issue": {"id": variables["input"]["issueId"]}
                        }
                    },
                    (),
                )
            if "ReplanAddSubIssue" in document:
                value = variables["input"]
                return github.GraphQLResponse(
                    {
                        "addSubIssue": {
                            "issue": {"id": value["issueId"]},
                            "subIssue": {"id": value["subIssueId"]},
                        }
                    },
                    (),
                )
            if "ReplanAddBlockedBy" in document or "ReplanRemoveBlockedBy" in document:
                value = variables["input"]
                field = "addBlockedBy" if "ReplanAddBlockedBy" in document else "removeBlockedBy"
                return github.GraphQLResponse(
                    {
                        field: {
                            "issue": {"id": value["issueId"]},
                            "blockingIssue": {"id": value["blockingIssueId"]},
                        }
                    },
                    (),
                )
            raise AssertionError("unexpected mutation")

    def apply_with_recovery(self, plan, snapshot, adapter):
        with tempfile.TemporaryDirectory() as directory:
            return replanning.apply_plan(
                plan,
                snapshot,
                actor="alice",
                writer=github_replanning.GitHubMutationWriter(adapter),
                recovery=replanning.RecoveryJournal(
                    Path(directory) / "operation.json", plan, FakeRecoverySigner()
                ),
            )

    def test_writer_uses_only_the_compiled_native_mutations(self):
        snapshot = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1)),
        )
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = self.FakeAdapter()
        aliases = self.apply_with_recovery(plan, snapshot, adapter)
        self.assertEqual(aliases["new-work"].key, key(10))
        mutations = [call for call in adapter.calls if call[0].lstrip().startswith("mutation")]
        self.assertEqual(len(mutations), 2)
        self.assertIn("mutation ReplanCreateIssue", mutations[0][0])
        self.assertIn("mutation ReplanPrioritizeSubIssue", mutations[1][0])
        create_input = mutations[0][1]["input"]
        self.assertEqual(create_input["parentIssueId"], "ISSUE_1")
        self.assertNotIn("replaceParent", create_input)
        self.assertEqual(create_input["body"], request["operation"]["issue"]["body"])

    def test_writer_reuses_the_exact_dependency_removal_mutation(self):
        snapshot = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1), blocked_by=(key(3),)),
            node(3, blocking=(key(2),)),
        )
        request = {
            "current_issue": key(2),
            "finding": finding("IN_CONTRACT_DEFECT", technically_blocking=True),
            "operation": {
                "kind": "REMOVE_OBSOLETE_DEPENDENCY",
                "blocker": key(3),
                "contract_no_longer_requires_blocker": True,
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = self.FakeAdapter()

        self.apply_with_recovery(plan, snapshot, adapter)

        mutations = [call for call in adapter.calls if call[0].lstrip().startswith("mutation")]
        self.assertEqual(len(mutations), 1)
        self.assertIn("mutation ReplanRemoveBlockedBy", mutations[0][0])
        self.assertEqual(
            mutations[0][1]["input"],
            {
                "issueId": "ISSUE_2",
                "blockingIssueId": "ISSUE_3",
                "clientMutationId": f"secpal-replan-{replanning.plan_digest(plan)[:16]}-1",
            },
        )

    def test_client_mutation_ids_bind_the_exact_finite_plan(self):
        snapshot = graph(
            node(1, children=(key(2),)),
            node(2, parent=key(1)),
        )

        def build(title):
            return replanning.build_plan(
                snapshot,
                {
                    "current_issue": key(2),
                    "finding": finding("NEW_RESPONSIBILITY"),
                    "operation": {
                        "kind": "CREATE_OWNED_SIBLING",
                        "issue": {
                            "alias": "new-work",
                            "repository": REPO,
                            "title": title,
                            "body": "## Acceptance Criteria\n\n- Complete.\n",
                        },
                    },
                },
                actor="alice",
            )

        first_plan = build("First separate work")
        second_plan = build("Second separate work")
        self.assertEqual(first_plan.snapshot_digest, second_plan.snapshot_digest)
        self.assertNotEqual(
            replanning.plan_digest(first_plan), replanning.plan_digest(second_plan)
        )
        self.assertEqual(
            replanning.plan_digest(first_plan), replanning.plan_digest(first_plan)
        )

        first_adapter = self.FakeAdapter()
        repeated_adapter = self.FakeAdapter()
        second_adapter = self.FakeAdapter()
        self.apply_with_recovery(first_plan, snapshot, first_adapter)
        self.apply_with_recovery(first_plan, snapshot, repeated_adapter)
        self.apply_with_recovery(second_plan, snapshot, second_adapter)
        first_mutations = [
            variables["input"]
            for document, variables in first_adapter.calls
            if document.lstrip().startswith("mutation")
        ]
        second_mutations = [
            variables["input"]
            for document, variables in second_adapter.calls
            if document.lstrip().startswith("mutation")
        ]
        repeated_mutations = [
            variables["input"]
            for document, variables in repeated_adapter.calls
            if document.lstrip().startswith("mutation")
        ]
        first_prefix = f"secpal-replan-{replanning.plan_digest(first_plan)[:16]}"
        second_prefix = f"secpal-replan-{replanning.plan_digest(second_plan)[:16]}"
        self.assertEqual(
            [item["clientMutationId"] for item in first_mutations],
            [f"{first_prefix}-1", f"{first_prefix}-2"],
        )
        self.assertEqual(
            second_mutations[0]["clientMutationId"], f"{second_prefix}-1"
        )
        self.assertNotEqual(
            first_mutations[0]["clientMutationId"],
            second_mutations[0]["clientMutationId"],
        )
        self.assertEqual(
            [item["clientMutationId"] for item in repeated_mutations],
            [item["clientMutationId"] for item in first_mutations],
        )
        self.assertEqual(first_mutations[0]["parentIssueId"], "ISSUE_1")
        self.assertEqual(first_mutations[1]["issueId"], "ISSUE_1")

    def test_root_prerequisite_path_creates_owner_and_native_edges(self):
        snapshot = graph(node(2))
        request = {
            "current_issue": key(2),
            "finding": finding("MISSING_PREREQUISITE", technically_blocking=True),
            "operation": {
                "kind": "INSERT_PREREQUISITE",
                "epic": {
                    "alias": "aggregate",
                    "repository": REPO,
                    "title": "Aggregate",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "issue": {
                    "alias": "prerequisite",
                    "repository": REPO,
                    "title": "Prerequisite",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "move_current_blockers": [],
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = self.FakeAdapter()
        aliases = self.apply_with_recovery(plan, snapshot, adapter)
        self.assertEqual(
            {alias: identity.key for alias, identity in aliases.items()},
            {"aggregate": key(10), "prerequisite": key(11)},
        )
        self.assertEqual(
            [
                next(name for name in (
                    "ReplanCreateIssue",
                    "ReplanAddSubIssue",
                    "ReplanPrioritizeSubIssue",
                    "ReplanAddBlockedBy",
                ) if name in document)
                for document, _ in adapter.calls
                if document.lstrip().startswith("mutation")
            ],
            [
                "ReplanCreateIssue",
                "ReplanAddSubIssue",
                "ReplanCreateIssue",
                "ReplanPrioritizeSubIssue",
                "ReplanAddBlockedBy",
            ],
        )
        first_mutation = next(call for call in adapter.calls if "ReplanCreateIssue" in call[0])
        self.assertNotIn("parentIssueId", first_mutation[1]["input"])

    def test_actor_is_reauthenticated_immediately_before_each_write(self):
        class ChangedActorAdapter(self.FakeAdapter):
            def query(self, document, variables):
                if "WorkGraphViewer" in document:
                    self.calls.append((document, variables))
                    return github.GraphQLResponse({"viewer": {"login": "mallory"}}, ())
                return super().query(document, variables)

        snapshot = graph(node(1, children=(key(2),)), node(2, parent=key(1)))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        adapter = ChangedActorAdapter()
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            with self.assertRaisesRegex(github_replanning.MutationError, "actor changed"):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(adapter),
                    recovery=journal,
                )
            self.assertEqual(journal.load()["outcome"], "NO_WRITES")
        self.assertFalse(any(call[0].lstrip().startswith("mutation") for call in adapter.calls))

    def test_partial_root_creation_is_recovered_without_duplicate_creation(self):
        class FailsSecondActorCheck(self.FakeAdapter):
            def __init__(self):
                super().__init__()
                self.viewer_reads = 0

            def query(self, document, variables):
                if "WorkGraphViewer" in document:
                    self.viewer_reads += 1
                    if self.viewer_reads == 2:
                        self.calls.append((document, variables))
                        return github.GraphQLResponse({"viewer": {"login": "mallory"}}, ())
                return super().query(document, variables)

        snapshot = graph(node(2))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "epic": {
                    "alias": "aggregate",
                    "repository": REPO,
                    "title": "Aggregate",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            adapter = FailsSecondActorCheck()
            with self.assertRaises(github_replanning.MutationError):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(adapter),
                    recovery=journal,
                )
            evidence = journal.load()
            self.assertEqual(evidence["outcome"], "KNOWN_WRITES")
            self.assertEqual(evidence["next_step"], 1)
            self.assertEqual(evidence["created"]["aggregate"]["key"], key(10))

            with self.assertRaisesRegex(replanning.StalePlanError, "recovery"):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(self.FakeAdapter()),
                    recovery=journal,
                )

            recovered = replanning.recovery_identities(evidence)
            created_epic = node(
                10,
                title="Aggregate",
                body_digest=replanning.content_digest(replanning.created_issue_body(plan, 0)),
            )
            recovery_snapshot = graph(node(2), created_epic)
            replanning.verify_applied(plan, recovery_snapshot, recovered, step_limit=1)
            replanning.verify_unchanged_relationships(
                plan, snapshot, recovery_snapshot, recovered, step_limit=1
            )

            resumed_adapter = self.FakeAdapter()
            resumed_adapter.next_issue = 11
            completed = replanning.apply_plan(
                plan,
                snapshot,
                actor="alice",
                writer=github_replanning.GitHubMutationWriter(resumed_adapter),
                recovery=journal,
                resume=True,
            )
            self.assertEqual(completed["aggregate"].key, key(10))
            create_mutations = [
                call for call in resumed_adapter.calls if "ReplanCreateIssue" in call[0]
            ]
            self.assertEqual(len(create_mutations), 1)
            self.assertEqual(journal.load()["outcome"], "COMPLETE")

            tampered = journal.load()
            tampered.pop("journal_digest")
            tampered.pop("authentication")
            tampered["created"]["aggregate"]["node_id"] = "ISSUE_999"
            tampered["journal_digest"] = replanning.recovery_document_digest(tampered)
            tampered["authentication"] = {
                "kind": "test-signature",
                "value": "signed:stale",
            }
            journal.path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(replanning.StalePlanError, "authentication"):
                journal.load()

    def test_unknown_mutation_outcome_is_retained_and_never_resumed(self):
        class UnknownCreateAdapter(self.FakeAdapter):
            def query(self, document, variables):
                if "ReplanCreateIssue" in document:
                    self.calls.append((document, variables))
                    return github.GraphQLResponse(None, ({"message": "unknown"},))
                return super().query(document, variables)

        snapshot = graph(node(1, children=(key(2),)), node(2, parent=key(1)))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(snapshot, request, actor="alice")
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            with self.assertRaises(github_replanning.MutationError):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(UnknownCreateAdapter()),
                    recovery=journal,
                )
            self.assertEqual(journal.load()["outcome"], "UNKNOWN_MUTATION_OUTCOME")
            with self.assertRaisesRegex(replanning.StalePlanError, "unknown mutation outcome"):
                replanning.apply_plan(
                    plan,
                    snapshot,
                    actor="alice",
                    writer=github_replanning.GitHubMutationWriter(self.FakeAdapter()),
                    recovery=journal,
                    resume=True,
                )

    def test_known_prefix_recovery_uses_the_authenticated_baseline(self):
        before = graph(node(1, children=(key(2),)), node(2, parent=key(1)))
        request = {
            "current_issue": key(2),
            "finding": finding("NEW_RESPONSIBILITY"),
            "operation": {
                "kind": "CREATE_OWNED_SIBLING",
                "issue": {
                    "alias": "new-work",
                    "repository": REPO,
                    "title": "Separate work",
                    "body": "## Acceptance Criteria\n\n- Complete.\n",
                },
            },
        }
        plan = replanning.build_plan(before, request, actor="alice")
        identity = replanning.CreatedIssueIdentity(
            key=key(10), node_id="ISSUE_10", repository_id="REPO_ID"
        )
        after_prefix = graph(
            node(1, children=(key(2), key(10))),
            node(2, parent=key(1)),
            node(
                10,
                parent=key(1),
                title="Separate work",
                body_digest=replanning.content_digest(replanning.created_issue_body(plan, 0)),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            journal = replanning.RecoveryJournal(
                Path(directory) / "operation.json", plan, FakeRecoverySigner()
            )
            journal.start(before)
            journal.begin_step(0)
            journal.complete_step(0, identity)

            recovered, baseline, identities, next_step = replanning.recover_plan(
                plan.to_dict(), after_prefix, actor="alice", recovery=journal
            )
            self.assertEqual(recovered, plan)
            self.assertEqual(baseline, before)
            self.assertEqual(identities, {"new-work": identity})
            self.assertEqual(next_step, 1)

            drifted = graph(
                node(1, children=(key(2), key(10))),
                node(2, parent=key(1), title="unrelated change"),
                after_prefix.require(key(10)),
            )
            with self.assertRaisesRegex(replanning.StalePlanError, "prefix"):
                replanning.recover_plan(
                    plan.to_dict(), drifted, actor="alice", recovery=journal
                )
            writer = replanning.RecordingWriter()
            completed = replanning.apply_plan(
                recovered,
                after_prefix,
                actor="alice",
                writer=writer,
                recovery=journal,
                resume=True,
                baseline_snapshot=baseline,
            )
            self.assertEqual(completed, {"new-work": identity})
            self.assertEqual([step.kind for step in writer.calls], ["REPRIORITIZE_SUB_ISSUE"])


class GitRecoverySignerTests(TestCase):
    def test_plan_rejects_signed_crash_ahead_alias_for_non_create_step(self):
        with hermetic_signing_account("ssh") as fixture:
            plan, baseline = recovery_plan(
                replanning.Step(
                    "ADD_BLOCKED_BY", {"blocked": key(1), "blocker": key(2)}
                )
            )
            signer = replanning.GitRecoverySigner.discover(fixture["repository"])
            journal = replanning.RecoveryJournal.for_plan(plan, signer)
            journal.start(baseline)
            journal.begin_step(0)
            durable = journal.load()
            invalid = recovery_state(
                plan,
                baseline,
                outcome="COMPLETE",
                next_step=1,
                created={"invented": created_identity(99)},
            )
            predecessor = durable["authentication"]["commit_oid"]
            descendant = recovery_child_commit(
                fixture,
                predecessor,
                replanning._authentication_message(
                    replanning.plan_digest(plan), invalid, predecessor
                ),
            )
            advance_recovery_ref(fixture, durable["authentication"], descendant)

            with self.assertRaises(replanning.StalePlanError):
                journal.load()

    def test_plan_accepts_and_reuses_exact_create_completion_crash_ahead(self):
        with hermetic_signing_account("ssh") as fixture:
            plan, baseline = recovery_plan(
                replanning.Step(
                    "CREATE_ISSUE",
                    {
                        "alias": "created",
                        "repository": REPO,
                        "title": "Created",
                        "body": "Created",
                    },
                )
            )
            signer = replanning.GitRecoverySigner.discover(fixture["repository"])
            journal = replanning.RecoveryJournal.for_plan(plan, signer)
            journal.start(baseline)
            journal.begin_step(0)
            durable = journal.load()
            identity = replanning.CreatedIssueIdentity(**created_identity(99))
            completed = recovery_state(
                plan,
                baseline,
                outcome="COMPLETE",
                next_step=1,
                created={"created": identity.to_dict()},
            )
            predecessor = durable["authentication"]["commit_oid"]
            descendant = recovery_child_commit(
                fixture,
                predecessor,
                replanning._authentication_message(
                    replanning.plan_digest(plan), completed, predecessor
                ),
            )
            advance_recovery_ref(fixture, durable["authentication"], descendant)

            self.assertEqual(journal.load()["outcome"], "UNKNOWN_MUTATION_OUTCOME")
            journal.complete_step(0, identity)
            evidence = journal.load()
            self.assertEqual(evidence["outcome"], "COMPLETE")
            self.assertEqual(evidence["created"], {"created": identity.to_dict()})
            self.assertEqual(evidence["authentication"]["commit_oid"], descendant)

    def test_authentication_survives_git_gc_and_ref_substitution_fails(self):
        with hermetic_signing_account("ssh") as fixture:
            repository = fixture["repository"]
            signer = replanning.GitRecoverySigner.discover(repository)
            self.assertEqual(signer.signer_format, "ssh")
            operation_digest = "a" * 64
            initial = signer_document(operation_digest)
            authentication = signer.sign(operation_digest, initial)
            attempting = signer_document(
                operation_digest,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            )
            replacement = signer.sign(
                operation_digest,
                attempting,
                signer_evidence(initial, authentication),
            )
            ref = authentication["ref"]
            self.assertEqual(
                subprocess.run(
                    [
                        str(fixture["git"]),
                        "-C",
                        str(repository),
                        "merge-base",
                        "--is-ancestor",
                        authentication["commit_oid"],
                        ref,
                    ],
                    env=fixture["environment"],
                ).returncode,
                0,
            )
            subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "gc", "--prune=now", "--quiet"],
                check=True,
                env=fixture["environment"],
            )
            signer.verify(authentication, operation_digest, initial)
            signer.verify(replacement, operation_digest, attempting)
            changed = dict(initial)
            changed["journal_digest"] = "e" * 64
            with self.assertRaisesRegex(replanning.StalePlanError, "digest"):
                signer.verify(authentication, operation_digest, changed)
            subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "update-ref", "-d", ref],
                check=True,
                env=fixture["environment"],
            )
            with self.assertRaisesRegex(replanning.StalePlanError, "reference"):
                signer.verify(authentication, operation_digest, initial)

    def test_hostile_signing_environment_is_not_inherited(self):
        hostile = {
            "HOME": "/tmp/hostile-home",
            "XDG_CONFIG_HOME": "/tmp/hostile-xdg",
            "GNUPGHOME": "/tmp/hostile-gnupg",
        }
        previous = {name: os.environ.get(name) for name in hostile}
        try:
            os.environ.update(hostile)
            environment = replanning.GitRecoverySigner._environment()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        for name, value in hostile.items():
            with self.subTest(name=name):
                self.assertNotEqual(environment.get(name), value)

    def test_recovery_directory_symlink_is_rejected_before_signing(self):
        before = graph(node(1))
        request = {
            "current_issue": key(1),
            "finding": finding("IN_CONTRACT_DEFECT"),
            "operation": {"kind": "KEEP_IN_CURRENT_CONTRACT"},
        }
        plan = replanning.build_plan(before, request, actor="alice")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir(mode=0o700)
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            journal = replanning.RecoveryJournal(
                link / "operation.json", plan, FakeRecoverySigner()
            )
            with self.assertRaisesRegex(replanning.StalePlanError, "canonical"):
                journal.start(before)

    def test_another_locally_valid_ssh_signer_is_rejected(self):
        with hermetic_signing_account("ssh") as fixture:
            repository = fixture["repository"]
            signer = replanning.GitRecoverySigner.discover(repository)
            self.assertEqual(signer.signer_format, "ssh")
            operation_digest = "c" * 64
            document = signer_document(operation_digest)
            authentication = dict(signer.sign(operation_digest, document))

            alternate = repository / "alternate"
            subprocess.run(
                [
                    str(fixture["ssh_keygen"]),
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(alternate),
                ],
                check=True,
                env=fixture["environment"],
            )
            allowed = fixture["allowed_signers"]
            self.assertIsNotNone(allowed)
            allowed.write_text(
                allowed.read_text(encoding="utf-8").rstrip()
                + "\nattacker@example.invalid "
                + alternate.with_suffix(".pub").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            tree = subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "rev-parse", "HEAD^{tree}"],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            message = replanning._authentication_message(
                operation_digest, document, authentication["commit_oid"]
            ) + "\n"
            alternate_commit = subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "-c",
                    "user.name=Attacker",
                    "-c",
                    "user.email=attacker@example.invalid",
                    "-c",
                    f"user.signingkey={alternate}",
                    "commit-tree",
                    "-S",
                    tree,
                    "-p",
                    authentication["commit_oid"],
                ],
                check=True,
                input=message,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "update-ref",
                    authentication["ref"],
                    alternate_commit,
                    authentication["commit_oid"],
                ],
                check=True,
                env=fixture["environment"],
            )
            with self.assertRaises(replanning.StalePlanError):
                signer.verify(authentication, operation_digest, document)

    def test_unsigned_private_ref_descendant_is_rejected(self):
        with hermetic_signing_account("ssh") as fixture:
            repository = fixture["repository"]
            signer = replanning.GitRecoverySigner.discover(repository)
            operation_digest = "1" * 64
            document = signer_document(operation_digest)
            authentication = dict(signer.sign(operation_digest, document))
            tree = subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "rev-parse", "HEAD^{tree}"],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            unsigned = subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "commit-tree",
                    tree,
                    "-p",
                    authentication["commit_oid"],
                ],
                check=True,
                input="unsigned descendant\n",
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "update-ref",
                    authentication["ref"],
                    unsigned,
                    authentication["commit_oid"],
                ],
                check=True,
                env=fixture["environment"],
            )

            with self.assertRaises(replanning.StalePlanError):
                signer.verify(authentication, operation_digest, document)

    def test_signed_private_ref_descendants_require_the_exact_operation_and_transition(self):
        cases = ("wrong-operation", "malformed", "invalid-transition")
        for case in cases:
            with self.subTest(case=case), hermetic_signing_account("ssh") as fixture:
                signer = replanning.GitRecoverySigner.discover(fixture["repository"])
                operation_digest = "6" * 64
                document = signer_document(operation_digest)
                authentication = dict(signer.sign(operation_digest, document))
                attempting = signer_document(
                    operation_digest,
                    outcome="UNKNOWN_MUTATION_OUTCOME",
                    attempting_step=0,
                )
                if case == "wrong-operation":
                    message = replanning._authentication_message(
                        "7" * 64, attempting, authentication["commit_oid"]
                    )
                elif case == "malformed":
                    message = "Authenticate work-graph recovery\n\nmalformed"
                else:
                    invalid = signer_document(
                        operation_digest,
                        outcome="COMPLETE",
                        next_step=1,
                    )
                    message = replanning._authentication_message(
                        operation_digest, invalid, authentication["commit_oid"]
                    )
                descendant = recovery_child_commit(
                    fixture, authentication["commit_oid"], message
                )
                advance_recovery_ref(fixture, authentication, descendant)

                with self.assertRaises(replanning.StalePlanError):
                    signer.verify(authentication, operation_digest, document)

    def test_signed_private_ref_descendant_must_be_linear(self):
        with hermetic_signing_account("ssh") as fixture:
            repository = fixture["repository"]
            signer = replanning.GitRecoverySigner.discover(repository)
            operation_digest = "9" * 64
            document = signer_document(operation_digest)
            authentication = dict(signer.sign(operation_digest, document))
            attempting = signer_document(
                operation_digest,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            )
            tree = subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "rev-parse", "HEAD^{tree}"],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            source_head = subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            descendant = subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "commit-tree",
                    "-S",
                    tree,
                    "-p",
                    authentication["commit_oid"],
                    "-p",
                    source_head,
                ],
                check=True,
                input=replanning._authentication_message(
                    operation_digest, attempting, authentication["commit_oid"]
                )
                + "\n",
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            advance_recovery_ref(fixture, authentication, descendant)

            with self.assertRaisesRegex(replanning.StalePlanError, "substituted"):
                signer.verify(authentication, operation_digest, document)

    def test_private_ref_cannot_advance_two_states_beyond_the_journal(self):
        with hermetic_signing_account("ssh") as fixture:
            signer = replanning.GitRecoverySigner.discover(fixture["repository"])
            operation_digest = "5" * 64
            initial = signer_document(operation_digest)
            authentication = dict(signer.sign(operation_digest, initial))
            attempting = signer_document(
                operation_digest,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            )
            first = recovery_child_commit(
                fixture,
                authentication["commit_oid"],
                replanning._authentication_message(
                    operation_digest,
                    attempting,
                    authentication["commit_oid"],
                ),
            )
            second = recovery_child_commit(
                fixture,
                first,
                replanning._authentication_message(operation_digest, initial, first),
            )
            advance_recovery_ref(fixture, authentication, second)

            with self.assertRaisesRegex(replanning.StalePlanError, "substituted"):
                signer.verify(authentication, operation_digest, initial)

    def test_legitimate_signed_crash_ahead_state_is_reused(self):
        with hermetic_signing_account("ssh") as fixture:
            before = graph(node(1, children=(key(2),)), node(2, parent=key(1)))
            request = {
                "current_issue": key(2),
                "finding": finding("NEW_RESPONSIBILITY"),
                "operation": {
                    "kind": "CREATE_OWNED_SIBLING",
                    "issue": {
                        "alias": "new-work",
                        "repository": REPO,
                        "title": "Separate work",
                        "body": "## Acceptance Criteria\n\n- Complete.\n",
                    },
                },
            }
            plan = replanning.build_plan(before, request, actor="alice")
            signer = replanning.GitRecoverySigner.discover(fixture["repository"])
            journal = replanning.RecoveryJournal.for_plan(plan, signer)
            journal.start(before)
            durable_journal = journal.path.read_bytes()
            journal.begin_step(0)
            crash_ahead_tip = subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(fixture["repository"]),
                    "rev-parse",
                    "--verify",
                    signer._ref_name(replanning.plan_digest(plan)),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()

            journal.path.write_bytes(durable_journal)
            self.assertEqual(journal.load()["outcome"], "NO_WRITES")
            journal.begin_step(0)
            reused_tip = subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(fixture["repository"]),
                    "rev-parse",
                    "--verify",
                    signer._ref_name(replanning.plan_digest(plan)),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            self.assertEqual(reused_tip, crash_ahead_tip)
            self.assertEqual(journal.load()["outcome"], "UNKNOWN_MUTATION_OUTCOME")

    def test_private_ref_compare_and_swap_rejects_a_concurrent_substitution(self):
        with hermetic_signing_account("ssh") as fixture:
            signer = replanning.GitRecoverySigner.discover(fixture["repository"])
            operation_digest = "8" * 64
            document = signer_document(operation_digest)
            authentication = dict(signer.sign(operation_digest, document))
            unsigned = recovery_child_commit(
                fixture,
                authentication["commit_oid"],
                "concurrent unsigned descendant",
                signed=False,
            )
            attempting = signer_document(
                operation_digest,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            )
            original_run = signer._run
            substituted = False

            def race(arguments, **kwargs):
                nonlocal substituted
                if arguments and arguments[0] == "update-ref" and not substituted:
                    substituted = True
                    advance_recovery_ref(fixture, authentication, unsigned)
                return original_run(arguments, **kwargs)

            signer._run = race
            with self.assertRaises(replanning.StalePlanError):
                signer.sign(
                    operation_digest,
                    attempting,
                    signer_evidence(document, authentication),
                )
            self.assertTrue(substituted)

    def test_signing_refuses_to_extend_an_unsigned_private_ref_descendant(self):
        with hermetic_signing_account("ssh") as fixture:
            repository = fixture["repository"]
            signer = replanning.GitRecoverySigner.discover(repository)
            operation_digest = "3" * 64
            document = signer_document(operation_digest)
            authentication = dict(signer.sign(operation_digest, document))
            tree = subprocess.run(
                [str(fixture["git"]), "-C", str(repository), "rev-parse", "HEAD^{tree}"],
                check=True,
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            unsigned = subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "commit-tree",
                    tree,
                    "-p",
                    authentication["commit_oid"],
                ],
                check=True,
                input="unsigned descendant\n",
                capture_output=True,
                text=True,
                env=fixture["environment"],
            ).stdout.strip()
            subprocess.run(
                [
                    str(fixture["git"]),
                    "-C",
                    str(repository),
                    "update-ref",
                    authentication["ref"],
                    unsigned,
                    authentication["commit_oid"],
                ],
                check=True,
                env=fixture["environment"],
            )

            attempting = signer_document(
                operation_digest,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            )
            with self.assertRaises(replanning.StalePlanError):
                signer.sign(
                    operation_digest,
                    attempting,
                    signer_evidence(document, authentication),
                )

    def test_openpgp_configured_signer_is_accepted(self):
        with hermetic_signing_account("openpgp") as fixture:
            signer = replanning.GitRecoverySigner.discover(fixture["repository"])
            operation_digest = "e" * 64
            document = signer_document(operation_digest)
            authentication = signer.sign(operation_digest, document)
            signer.verify(authentication, operation_digest, document)
            self.assertEqual(authentication["signer_format"], "openpgp")
            self.assertEqual(
                authentication["signer_fingerprint"], fixture["signer_identity"]
            )


class RecoveryTransitionTests(TestCase):
    def test_begin_and_cancel_transitions_are_exact_and_preserve_aliases(self):
        plan, baseline = recovery_plan(
            replanning.Step(
                "ADD_BLOCKED_BY", {"blocked": key(1), "blocker": key(2)}
            )
        )
        initial = recovery_state(plan, baseline)
        attempting = recovery_state(
            plan,
            baseline,
            outcome="UNKNOWN_MUTATION_OUTCOME",
            attempting_step=0,
        )
        replanning._validate_recovery_transition(plan, initial, attempting)
        replanning._validate_recovery_transition(plan, attempting, initial)

        invalid_begin = recovery_state(
            plan,
            baseline,
            outcome="UNKNOWN_MUTATION_OUTCOME",
            attempting_step=0,
            created={"invented": created_identity(99)},
        )
        with self.assertRaises(replanning.StalePlanError):
            replanning._validate_recovery_transition(plan, initial, invalid_begin)

    def test_create_completion_rejects_wrong_or_multiple_aliases_and_changed_identity(self):
        first = replanning.Step(
            "CREATE_ISSUE",
            {"alias": "first", "repository": REPO, "title": "First", "body": "First"},
        )
        second = replanning.Step(
            "CREATE_ISSUE",
            {"alias": "second", "repository": REPO, "title": "Second", "body": "Second"},
        )
        plan, baseline = recovery_plan(first, second)
        previous = recovery_state(
            plan,
            baseline,
            outcome="UNKNOWN_MUTATION_OUTCOME",
            next_step=1,
            attempting_step=1,
            created={"first": created_identity(10)},
        )
        invalid_created = (
            {"first": created_identity(10)},
            {"first": created_identity(10), "wrong": created_identity(11)},
            {
                "first": created_identity(10),
                "second": created_identity(11),
                "extra": created_identity(12),
            },
            {"first": created_identity(99), "second": created_identity(11)},
        )
        for created in invalid_created:
            with self.subTest(created=created), self.assertRaises(
                replanning.StalePlanError
            ):
                replanning._validate_recovery_transition(
                    plan,
                    previous,
                    recovery_state(
                        plan,
                        baseline,
                        outcome="COMPLETE",
                        next_step=2,
                        created=created,
                    ),
                )

    def test_create_completion_rejects_malformed_cross_repository_or_colliding_identity(self):
        first = replanning.Step(
            "CREATE_ISSUE",
            {"alias": "first", "repository": REPO, "title": "First", "body": "First"},
        )
        second = replanning.Step(
            "CREATE_ISSUE",
            {"alias": "second", "repository": REPO, "title": "Second", "body": "Second"},
        )
        plan, baseline = recovery_plan(first, second)
        existing = created_identity(10)
        previous = recovery_state(
            plan,
            baseline,
            outcome="UNKNOWN_MUTATION_OUTCOME",
            next_step=1,
            attempting_step=1,
            created={"first": existing},
        )
        invalid_identities = (
            {"key": key(11), "node_id": 11, "repository_id": "REPOSITORY"},
            {"key": "not-a-canonical-issue", "node_id": "ISSUE_11", "repository_id": "R"},
            created_identity(11, repository="SecPal/api"),
            {**created_identity(11), "key": existing["key"]},
            {**created_identity(11), "node_id": existing["node_id"]},
        )
        for identity in invalid_identities:
            with self.subTest(identity=identity), self.assertRaises(
                replanning.StalePlanError
            ):
                replanning._validate_recovery_transition(
                    plan,
                    previous,
                    recovery_state(
                        plan,
                        baseline,
                        outcome="COMPLETE",
                        next_step=2,
                        created={"first": existing, "second": identity},
                    ),
                )

    def test_completion_outcome_must_match_the_exact_plan_position(self):
        steps = (
            replanning.Step(
                "ADD_BLOCKED_BY", {"blocked": key(1), "blocker": key(2)}
            ),
            replanning.Step(
                "REMOVE_BLOCKED_BY", {"blocked": key(1), "blocker": key(3)}
            ),
        )
        plan, baseline = recovery_plan(*steps)
        cases = (
            (
                recovery_state(
                    plan,
                    baseline,
                    outcome="UNKNOWN_MUTATION_OUTCOME",
                    attempting_step=0,
                ),
                recovery_state(plan, baseline, outcome="COMPLETE", next_step=1),
            ),
            (
                recovery_state(
                    plan,
                    baseline,
                    outcome="UNKNOWN_MUTATION_OUTCOME",
                    next_step=1,
                    attempting_step=1,
                ),
                recovery_state(plan, baseline, outcome="KNOWN_WRITES", next_step=2),
            ),
            (
                recovery_state(plan, baseline, outcome="COMPLETE", next_step=2),
                recovery_state(
                    plan,
                    baseline,
                    outcome="UNKNOWN_MUTATION_OUTCOME",
                    next_step=2,
                    attempting_step=2,
                ),
            ),
        )
        for previous, current in cases:
            with self.subTest(previous=previous["outcome"]), self.assertRaises(
                replanning.StalePlanError
            ):
                replanning._validate_recovery_transition(plan, previous, current)

    def test_valid_non_create_and_create_completions_are_accepted(self):
        non_create_plan, baseline = recovery_plan(
            replanning.Step(
                "ADD_BLOCKED_BY", {"blocked": key(1), "blocker": key(2)}
            )
        )
        replanning._validate_recovery_transition(
            non_create_plan,
            recovery_state(
                non_create_plan,
                baseline,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            ),
            recovery_state(non_create_plan, baseline, outcome="COMPLETE", next_step=1),
        )

        create_plan, baseline = recovery_plan(
            replanning.Step(
                "CREATE_ISSUE",
                {"alias": "created", "repository": REPO, "title": "New", "body": "New"},
            )
        )
        replanning._validate_recovery_transition(
            create_plan,
            recovery_state(
                create_plan,
                baseline,
                outcome="UNKNOWN_MUTATION_OUTCOME",
                attempting_step=0,
            ),
            recovery_state(
                create_plan,
                baseline,
                outcome="COMPLETE",
                next_step=1,
                created={"created": created_identity(10)},
            ),
        )


if __name__ == "__main__":
    main()
