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
import sqlite3
import subprocess
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
            subprocess.run(["git", "init", "--quiet", "--template=", str(repo)], check=True)
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
            ignored = subprocess.run(["git", "-C", str(repo), "check-ignore", "polyscope.local.json"],
                                     capture_output=True, text=True)
            self.assertEqual(ignored.returncode, 0, ignored.stderr)
            self.assertEqual(ignored.stdout.strip(), "polyscope.local.json")
            # Publication in a non-Git fixture must not manufacture Git metadata.
            plain = root / "plain"
            plain.mkdir()
            rollout.write_local_configs({"plain": {"path": plain, rollout.REGISTRATION_ONLY_SPEC_KEY: True}})
            self.assertFalse((plain / ".git").exists())

    def test_host_route_reconciliation_revokes_only_orphans_and_fails_closed(self):
        for mode in ("refresh", "install", "db-failure", "acl-failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                clones = root / "clones"
                active = clones / "frontend-id" / "active"
                orphan = active.parent / "orphan"
                active.mkdir(parents=True)
                orphan.mkdir()
                (active / "package.json").write_text('{"scripts":{"postinstall":"exit 99"}}')
                database = root / "polyscope.db"
                with sqlite3.connect(database) as connection:
                    connection.execute("create table worktrees (id text, repo_id text, path text, status text)")
                    connection.executemany("insert into worktrees values (?,?,?,?)", [
                        ("live", "frontend-id", str(active), "active"),
                        ("retired", "frontend-id", str(orphan), "archived"),
                    ])
                state = {"frontend": {"id": "frontend-id"}}
                args = Namespace(workspace_root=root, db_path=database, clone_root=clones,
                    polyscope_api_base="http://127.0.0.1:1/api", repo_state_file=None,
                    skip_local_configs=True, skip_db_sync=True, container_preview=False,
                    install_nginx=mode == "install", refresh_nginx=mode != "install",
                    provision_worktrees=True, nginx_http2_syntax="modern",
                    nginx_output=root / "nginx.conf", nginx_manifest_output=root / "manifest.json",
                    summary_output=None)
                granted = {active, orphan}

                def deny(_root, path):
                    if mode == "acl-failure":
                        raise RuntimeError("fixture ACL failure")
                    granted.discard(path)

                forbidden = unittest.mock.Mock(side_effect=AssertionError("workspace code execution"))
                revoke_all = unittest.mock.Mock(side_effect=lambda _root: granted.clear())
                install = unittest.mock.Mock()
                with contextlib.ExitStack() as stack:
                    stack.enter_context(unittest.mock.patch.multiple(rollout,
                        build_repo_specs=unittest.mock.Mock(return_value={}),
                        validate_repo_instruction_files=unittest.mock.Mock(),
                        validate_repo_local_configs=unittest.mock.Mock(),
                        ensure_repositories_registered=unittest.mock.Mock(return_value=state),
                        isolation_blocked_paths=unittest.mock.Mock(return_value=set()),
                        build_preview_workspace_redirects=unittest.mock.Mock(return_value={}),
                        render_nginx_config=unittest.mock.Mock(return_value="fixture nginx\n"),
                        detect_nginx_http2_syntax=unittest.mock.Mock(return_value="modern"),
                        deny_preview_nginx_access=unittest.mock.Mock(side_effect=deny),
                        revoke_all_preview_nginx_access=revoke_all,
                        write_compatible_nginx_manifest=unittest.mock.Mock(),
                        install_nginx_config=install, run_setup_commands=forbidden,
                        ensure_api_runtime_owner=forbidden, ensure_worktree_hooks=forbidden))
                    stack.enter_context(unittest.mock.patch.dict(sys.modules, {"polyscope_nginx": Namespace(
                        build_manifest=unittest.mock.Mock(return_value={}),
                        write_manifest_atomic=unittest.mock.Mock())}))
                    if mode == "db-failure":
                        stack.enter_context(unittest.mock.patch.object(rollout, "load_registered_worktree_paths",
                            side_effect=RuntimeError("fixture native read failure")))
                    result = rollout.run_rollout(args)
                self.assertEqual(result, 1 if mode.endswith("failure") else 0)
                self.assertIn(active, granted, "installation revoked an established preview")
                if mode in ("refresh", "install"):
                    self.assertNotIn(orphan, granted, "unregistered preview retained its ACL")
                revoke_all.assert_not_called()
                forbidden.assert_not_called()
                self.assertEqual(install.call_count, int(mode in ("refresh", "install")))

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
