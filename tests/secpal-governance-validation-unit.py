#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Scope routing is based on the whole authenticated PR, never a caller flag."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
from tests.secpal_actions_fixture import load_actions
actions = load_actions()


class GovernanceValidationTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")
        for path in ("AGENTS.md", "CONTRIBUTING.md", "app.php"):
            (self.root / path).write_text("baseline\n")
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.entry = copy.deepcopy(actions.select_repository(actions.load_registry(), "SecPal/api"))
        self.entry["governance_only_validation"] = "API_RUNTIME_INSTRUCTIONS"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout

    def tree(self):
        self.git("add", ".")
        return self.git("write-tree").strip()

    def classify(self, base=None):
        return actions._governance_only_candidate(
            self.entry, self.root, self.base if base is None else base, self.tree()
        )

    def test_governance_only_whole_candidate_is_eligible(self):
        (self.root / "AGENTS.md").write_text("changed instructions\n")
        self.assertTrue(self.classify())

    def test_application_delta_in_published_predecessor_is_not_hidden(self):
        (self.root / "app.php").write_text("changed behavior\n")
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "published behavior")
        (self.root / "AGENTS.md").write_text("remediation instructions\n")
        self.assertFalse(self.classify())

    def test_empty_change_does_not_select_governance(self):
        self.assertFalse(self.classify())

    def test_missing_or_malformed_authenticated_base_selects_full_validation(self):
        for base in ("", "not-an-oid", "f" * 40):
            with self.subTest(base=base):
                self.assertFalse(self.classify(base))

    def test_dependency_or_workflow_changes_select_full_validation(self):
        for path in ("composer.json", ".github/workflows/test.yml"):
            with self.subTest(path=path):
                target = self.root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("{}\n")
                self.assertFalse(self.classify())
                target.unlink()
                self.git("reset", "-q", "--", path)

    def test_symlink_executable_and_deletion_select_full_validation(self):
        (self.root / "AGENTS.md").unlink()
        self.assertFalse(self.classify())
        (self.root / "AGENTS.md").symlink_to("app.php")
        self.assertFalse(self.classify())
        (self.root / "AGENTS.md").unlink()
        (self.root / "AGENTS.md").write_text("changed\n")
        (self.root / "AGENTS.md").chmod(0o755)
        self.assertFalse(self.classify())

    def test_other_repository_or_unregistered_policy_cannot_use_route(self):
        (self.root / "AGENTS.md").write_text("changed\n")
        for repository, policy in (("SecPal/frontend", "API_RUNTIME_INSTRUCTIONS"),
                                   ("SecPal/api", None)):
            self.entry["repository"] = repository
            if policy is None:
                self.entry.pop("governance_only_validation")
            self.assertFalse(self.classify())

    def test_route_is_part_of_signed_registry_binding(self):
        original = actions.select_repository(actions.load_registry(), "SecPal/api")
        self.assertEqual(original.get("governance_only_validation"), "API_RUNTIME_INSTRUCTIONS")
        projection = actions._fast_registry_binding(original)
        self.assertEqual(projection["governance_only_validation"], "API_RUNTIME_INSTRUCTIONS")
        wrong = copy.deepcopy(actions.load_registry())
        target = next(item for item in wrong["repositories"] if item["repository"] == "SecPal/api")
        target["governance_only_validation"] = "SKIP_TESTS"
        with self.assertRaises(actions.RegistryError):
            actions.validate_registry(wrong)

    def test_governance_route_uses_maintained_validator_not_composer(self):
        tree = self.tree()
        with mock.patch.object(actions, "_governance_only_candidate", return_value=True), \
             mock.patch.object(actions, "_validation_executable", return_value="/usr/bin/validator") as executable, \
             mock.patch.object(actions.subprocess, "run", return_value=mock.Mock(returncode=0)) as run, \
             mock.patch.object(actions, "_complete_validation_commands") as application:
            result = actions._run_registered_validations(
                self.entry, self.root, governance_base=self.base, governance_tree=tree
            )
        self.assertTrue(result)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(result.command_set, list(actions._governance_validation_commands()))
        self.assertTrue(all("composer" not in call.args[0] for call in run.call_args_list))
        self.assertTrue(all(call.args[1:] == (actions.REPOSITORY_ROOT, actions.REPOSITORY_ROOT)
                            for call in executable.call_args_list))
        application.assert_not_called()

    def test_unbound_call_keeps_application_commands(self):
        with mock.patch.object(actions, "_governance_only_candidate", return_value=False), \
             mock.patch.object(actions, "_complete_validation_commands", return_value=()) as application:
            self.assertTrue(actions._run_registered_validations(self.entry, self.root))
        application.assert_called_once_with(self.entry)

    def test_current_registry_is_ssh_only(self):
        for entry in actions.load_registry()["repositories"]:
            self.assertEqual(entry["signature_policy"]["accepted_formats"], ["ssh"])

    def test_current_user_openpgp_is_not_new_signing_authority(self):
        commit = {
            "oid": "1" * 40, "source": "USER",
            "local_signature": {"verified": True, "state": "valid", "format": "openpgp"},
            "github_verification": {"verified": True, "reason": "valid"},
        }
        with self.assertRaises(actions.fast_path.SecurityBlocker):
            actions.fast_path.verify_commit_signatures([commit])
        commit["source"] = "GITHUB"
        self.assertEqual(actions.fast_path.verify_commit_signatures([commit])[0]["classification"], "GITHUB_VERIFIED")

    def test_governance_receipt_binds_actual_portable_commands(self):
        binding = actions._fast_registry_binding(self.entry)
        commands = list(actions._governance_validation_commands())
        self.assertFalse(any(str(actions.REPOSITORY_ROOT) in str(command) for command in commands))
        evidence = {"command_set_digest": actions.fast_path.digest_json(commands)}
        self.assertEqual(actions.fast_path.validation_commands_for_evidence(binding, evidence), commands)
        self.assertNotEqual(evidence["command_set_digest"], actions.fast_path.digest_json(binding["validation"]))
        for key in ("integration_evidence_digest", "exceptional_recovery_evidence_digest", "exceptional_continuation_evidence_digest"):
            with self.subTest(key=key), self.assertRaises(actions.fast_path.SecurityBlocker):
                actions.fast_path.validation_commands_for_evidence(binding, {**evidence, key: "a" * 64})

    def test_command_selection_cannot_be_borrowed_by_other_repository(self):
        binding = actions._fast_registry_binding(self.entry)
        evidence = {"command_set_digest": actions.fast_path.digest_json(list(actions._governance_validation_commands()))}
        for change in ({"repository": "SecPal/frontend"}, {"governance_only_validation": "SKIP_TESTS"}):
            with self.subTest(change=change), self.assertRaises(actions.fast_path.SecurityBlocker):
                actions.fast_path.validation_commands_for_evidence({**binding, **change}, evidence)
        with self.assertRaises(actions.fast_path.SecurityBlocker):
            actions.fast_path.validation_commands_for_evidence(binding, {"command_set_digest": "f" * 64})

    def test_governance_receipt_attestation_roundtrip_and_tamper_rejection(self):
        fast = actions.fast_path
        reviewed = fast.StableFeedbackState.from_payload({
            "repository": "SecPal/api", "pull_request_number": 1563,
            "head_sha": "1" * 40, "base_ref": "main", "base_sha": "2" * 40,
            "pr_state": "OPEN", "pull_request_reactions": [], "reviews": [],
            "conversation_comments": [], "threads": [],
        })
        binding = actions._fast_registry_binding(self.entry)
        commands = list(actions._governance_validation_commands())
        gates = [{"gate": gate, "satisfied": True, "evidence": "Focused governance validation; no application suite claim"}
                 for gate in binding["manual_gates"]]
        receipt = actions._validation_receipt(
            repository="SecPal/api", head_sha=reviewed.head_sha, tree_sha="3" * 40,
            binding=binding, reviewed=reviewed, manual_gate_evidence=gates,
            command_set=commands,
        )
        self.assertEqual(receipt["command_set_digest"], fast.digest_json(commands))
        attestation = fast.create_validation_attestation(
            repository="SecPal/api", head_sha="4" * 40, registry=binding,
            command_set=commands, successful_result=True, reviewed_state=reviewed,
            validation_receipt=receipt,
        )
        def verify(value):
            return fast.verify_validation_attestation(
                value, repository="SecPal/api", head_sha="4" * 40,
                registry=binding, command_set=binding["validation"],
                reviewed_state=reviewed, commit_parent_sha=reviewed.head_sha,
                commit_tree_sha="3" * 40, commit_validation_receipt_digest=receipt["receipt_digest"],
            )
        self.assertTrue(fast.is_verified_validation_evidence(verify(attestation)))
        wrong = copy.deepcopy(attestation)
        wrong["command_set_digest"] = fast.digest_json(binding["validation"])
        with self.assertRaises(fast.SecurityBlocker):
            verify(wrong)

    def test_governance_commands_require_authenticated_registry_history(self):
        fast = actions.fast_path
        binding = actions._fast_registry_binding(self.entry)
        registry = actions.load_registry()
        schema = fast.DELIVERY_REGISTRY_SCHEMA_PATH.read_text(encoding="utf-8")
        tip = "a" * 40
        observations = {
            ("remote", "get-url", "origin"): "https://github.com/SecPal/.github.git",
            ("rev-parse", "HEAD"): tip,
            ("log", "--format=%H", tip, "--", fast.DELIVERY_REGISTRY_PATH): tip,
            ("show", f"{tip}:{fast.DELIVERY_REGISTRY_PATH}"): actions.json.dumps(registry),
            ("show", f"{tip}:{fast.DELIVERY_REGISTRY_SCHEMA_RELATIVE_PATH}"): schema,
        }
        def read(arguments, **_):
            return 0, observations[tuple(arguments)]
        with mock.patch.object(fast, "_central_git_result", side_effect=read):
            for commands in (binding["validation"], fast.governance_validation_commands()):
                self.assertEqual(fast.load_immutable_delivery_registry_binding(
                    repository="SecPal/api", delivery_head_sha="b" * 40,
                    expected_registry_digest=fast.digest_json(binding),
                    expected_command_set_digest=fast.digest_json(commands),
                ), binding)
            with self.assertRaises(fast.SecurityBlocker):
                fast.load_immutable_delivery_registry_binding(
                    repository="SecPal/api", delivery_head_sha="b" * 40,
                    expected_registry_digest=fast.digest_json(binding),
                    expected_command_set_digest="f" * 64,
                )



if __name__ == "__main__":
    main()
