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
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gov_actions", ROOT / "scripts/secpal-pr-review-actions.py")
actions = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = actions
spec.loader.exec_module(actions)


class GovernanceValidationTests(unittest.TestCase):
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
        self.assertTrue(all("composer" not in call.args[0] for call in run.call_args_list))
        self.assertTrue(all(call.args[1:] == (actions.REPOSITORY_ROOT, actions.REPOSITORY_ROOT)
                            for call in executable.call_args_list))
        application.assert_not_called()

    def test_unbound_call_keeps_application_commands(self):
        with mock.patch.object(actions, "_governance_only_candidate", return_value=False), \
             mock.patch.object(actions, "_complete_validation_commands", return_value=()) as application:
            self.assertTrue(actions._run_registered_validations(self.entry, self.root))
        application.assert_called_once_with(self.entry)


if __name__ == "__main__":
    unittest.main()
