#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Service reconciliation and native registration must not execute workspace code."""

import contextlib
import importlib.util
import json
import os
from argparse import Namespace
from pathlib import Path
import shlex
import sys
import tempfile
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("registration_rollout", ROOT / "scripts/polyscope-rollout.py")
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


class RegistrationOnlyTests(unittest.TestCase):
    def test_native_configs_have_no_executable_setup_or_run_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = rollout.build_repo_specs(root)
            with unittest.mock.patch.object(rollout, "require_repo_instruction_files"), \
                    unittest.mock.patch.object(rollout, "should_manage_api_runtime_units", return_value=False), \
                    unittest.mock.patch.object(rollout, "resolve_current_workspace_name", return_value="fixture"):
                for name, config in specs.items():
                    with self.subTest(repository=name):
                        # Exercise enrichment too: it must not reintroduce run actions.
                        rendered = rollout.render_local_config(config)
                        native = json.loads(rollout.render_worktree_local_config(
                            config, root / "clones" / name / "fixture", container_preview=True))
                        self.assertEqual(rendered["scripts"], {"setup": "", "run": []})
                        self.assertEqual(native["scripts"], {"setup": "", "run": []})
                        self.assertEqual(rendered.get("tasks"), native.get("tasks"))
                        self.assertFalse(rendered["copyGitignored"])

    def test_installed_skip_callers_still_publish_safe_native_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "operations"
            repo.mkdir()
            specs = {"operations": {"path": repo, rollout.REGISTRATION_ONLY_SPEC_KEY: True}}
            args = Namespace(workspace_root=root, polyscope_api_base="http://127.0.0.1:1/api", skip_local_configs=True, skip_db_sync=True,
                repo_state_file=None, container_preview=True, install_nginx=False,
                refresh_nginx=False, provision_worktrees=False, summary_output=None)
            with unittest.mock.patch.object(rollout, "build_repo_specs", return_value=specs), \
                    unittest.mock.patch.object(rollout, "ensure_repositories_registered", return_value={"operations": {"id": "ops"}}), \
                    unittest.mock.patch.object(rollout, "refresh_container_preview"):
                self.assertEqual(rollout.run_rollout(args), 0)
            config = json.loads((repo / "polyscope.local.json").read_text())
            self.assertEqual(config["scripts"], {"setup": "", "run": []})
            self.assertFalse(config["copyGitignored"])

    def test_config_publication_cannot_follow_candidate_or_git_metadata_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "canonical"
            repo.mkdir()
            outside = root / "untouched"
            outside.write_text("private fixture data\n")
            target = repo / "polyscope.local.json"
            target.symlink_to(outside)
            (repo / ".git").symlink_to(root)
            rollout.sync_worktree_local_config(repo, '{"scripts":{"setup":"","run":[]}}\n')
            self.assertFalse(target.is_symlink())
            self.assertEqual(json.loads(target.read_text())["scripts"], {"setup": "", "run": []})
            self.assertEqual(outside.read_text(), "private fixture data\n")
            before = target.stat().st_mtime_ns
            with unittest.mock.patch.object(rollout.os, "replace", side_effect=AssertionError("unchanged config was rewritten")):
                rollout.sync_worktree_local_config(repo, target.read_text())
            self.assertEqual(target.stat().st_mtime_ns, before)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["canonical", "untouched"])

    def test_manifest_and_executable_changes_never_reach_service_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worktree = root / "workspace"
            worktree.mkdir()
            marker = worktree / "executed"
            lifecycle = worktree / "lifecycle.py"
            lifecycle.write_text("from pathlib import Path\nPath('executed').write_text('unexpected service execution')\n")
            package = {"name": "registration-fixture", "version": "1.0.0", "private": True}
            lock = {"name": package["name"], "version": "1.0.0", "lockfileVersion": 3,
                    "requires": True, "packages": {"": {"name": package["name"], "version": "1.0.0"}}}
            (worktree / "package-lock.json").write_text(json.dumps(lock))
            package["scripts"] = {"postinstall": shlex.join([sys.executable, "lifecycle.py"])}
            (worktree / "package.json").write_text(json.dumps(package))
            (worktree / "composer.json").write_text(json.dumps({"scripts": {"post-install-cmd": "python3 lifecycle.py"}}))
            state = {"api": {"id": "api"}, "deployment": {"id": "deployment"}}
            commands = [
                "npm ci --offline --no-audit --no-fund --ignore-scripts=false",
                shlex.join([sys.executable, "lifecycle.py"]),
            ]
            for command in commands:
                with self.subTest(command=command), contextlib.ExitStack() as stack:
                    marker.unlink(missing_ok=True)
                    patches = {
                        "isolation_state": None,
                        "isolation_path_blocked": False,
                        "should_manage_api_runtime_units": False,
                        "load_registered_worktree_paths": {"api": [], "deployment": [worktree]},
                        "is_provisionable_worktree": True,
                        "cleanup_removed_workspace_aliases": [],
                        "cleanup_removed_api_preview_databases": [],
                        "preserve_registered_workspace_physical_path": None,
                        "render_worktree_local_config": "{}",
                        "sync_worktree_local_config": None,
                        "ensure_workspace_alias": None,
                        "sync_worktree_auxiliary_files": None,
                        "ensure_worktree_hooks": None,
                        "collect_linked_setup_context": {},
                        "resolve_current_workspace_name": "fixture",
                        "load_provision_marker": {"setup_hash": "before-manifest-change"},
                        "write_provision_marker": None,
                    }
                    for name, result in patches.items():
                        stack.enter_context(unittest.mock.patch.object(rollout, name, return_value=result))
                    # Fixtures are controlled and offline; do not expose delivery credentials.
                    stack.enter_context(unittest.mock.patch.dict(os.environ,
                        {"PATH": os.environ["PATH"], "HOME": str(root)}, clear=True))
                    settings = {"deployment": {"path": root, "preview_prefix": None,
                        rollout.NATIVE_SETUP_COMMANDS_KEY: [command]}}
                    result = rollout.provision_worktrees(state, settings, root, container_preview=True)
                    self.assertFalse(marker.exists(), "reconciliation executed mutable workspace code")
                    self.assertEqual(result, ([], [], []))
                    self.assertEqual(json.loads((worktree / "package-lock.json").read_text()), lock)


if __name__ == "__main__":
    unittest.main()
