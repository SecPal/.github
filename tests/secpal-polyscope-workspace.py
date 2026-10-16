#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coordinator behavior against native Polyscope representations, without live writes."""
import concurrent.futures
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "workspace_coordinator", ROOT / "scripts/secpal-polyscope-workspace.py")
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = {"id": "832b2ca0", "name": "SecPal/.github",
                     "path": str(self.root / "source")}
        self.row = {
            "id": "73355d10", "repo_id": self.repo["id"],
            "branch": "plucky-otter", "path": str(self.root / "workspace"),
            "status": "active", "issue_number": 1224, "pr_number": None,
            "issue_url": "https://github.com/SecPal/.github/issues/1224",
            "is_repo_workspace": False, "linked_from_worktree_id": None,
            "linked_worktree_ids": [], "interface_mode": "chat",
        }
        self.rows = []
        self.metadata = {"number": 1224, "state": "OPEN", "title": "Authorized work",
                         "url": self.row["issue_url"], "body": "Existing contract"}
        self.calls = 0
        self.patches = [
            patch.object(workspace, "LOCK_PATH", self.root / "create.lock", create=True),
            patch.object(workspace, "repository", return_value=self.repo),
            patch.object(workspace, "github", side_effect=lambda *args: copy.deepcopy(self.metadata)),
            patch.object(workspace, "read_work_graph", create=True),
            patch.object(workspace, "api_get", side_effect=lambda path: copy.deepcopy(self.rows)),
            patch.object(workspace, "workspace_result", side_effect=self.result, create=True),
            patch.object(workspace, "create_native", side_effect=self.create, create=True),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def result(self, repo, row, sha, *, created=False):
        return {"workspace_id": row["id"], "path": row["path"], "created": created,
                "head": sha or "a" * 40, "branch": row["branch"], "dirty": True}

    def create(self, *args, **kwargs):
        self.calls += 1
        time.sleep(0.01)
        self.rows.append(copy.deepcopy(self.row))
        return copy.deepcopy(self.row)

    def ensure(self):
        return workspace.ensure("SecPal/.github", 1224, None, None)

    def test_missing_workspace_is_created_registered_and_reused_without_approval(self):
        first = self.ensure()
        second = self.ensure()
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["workspace_id"], second["workspace_id"])
        self.assertEqual(self.calls, 1)

    def test_exact_existing_workspace_preserves_pending_source_and_evidence(self):
        path = self.root / "workspace"
        path.mkdir()
        source = path / "uncommitted"
        evidence = path / "evidence"
        source.write_bytes(b"pending source\x00")
        evidence.write_bytes(b"prior evidence")
        self.rows.append(self.row)
        before = [p.read_bytes() for p in [source, evidence]]
        result = self.ensure()
        self.assertTrue(result["dirty"])
        self.assertFalse(result["created"])
        self.assertEqual(before, [p.read_bytes() for p in [source, evidence]])
        self.assertEqual(self.calls, 0)

    def test_concurrent_dispatch_creates_exactly_one_workspace(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.ensure(), range(4)))
        self.assertEqual(self.calls, 1)
        self.assertEqual({r["workspace_id"] for r in results}, {self.row["id"]})

    def test_lost_create_response_is_reconciled_from_native_registration(self):
        def lost(*args, **kwargs):
            self.create()
            raise TimeoutError("response lost")
        self.mocks[-1].side_effect = lost
        self.assertEqual(self.ensure()["workspace_id"], self.row["id"])
        self.assertEqual(self.calls, 1)

    def test_unknown_create_result_is_fenced_until_native_readback(self):
        def ambiguous(*args, **kwargs):
            self.calls += 1
            raise TimeoutError("operation outcome unknown")
        self.mocks[-1].side_effect = ambiguous
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "create-outcome-unverified"):
                self.ensure()
        self.assertEqual(self.calls, 1)
        self.rows.append(self.row)
        self.assertFalse(self.ensure()["created"])
        self.assertEqual(self.calls, 1)

    def test_unrelated_pending_create_does_not_block_existing_workspace_adoption(self):
        self.rows.append(self.row)
        pending = {"repo": "SecPal/.github", "issue": 999, "pr": None, "sha": None}
        (self.root / "create.lock").write_text(json.dumps(pending))
        (self.root / "create.lock").chmod(0o600)
        self.assertFalse(self.ensure()["created"])
        self.assertEqual(self.calls, 0)
        self.assertEqual(json.loads((self.root / "create.lock").read_text()), pending)

    def test_returned_workspace_without_native_registration_is_not_trusted(self):
        self.mocks[-1].side_effect = lambda *args: self.row
        with self.assertRaisesRegex(RuntimeError, "create-outcome-unverified"):
            self.ensure()

    def test_paused_shared_foreign_or_multiple_matches_never_trigger_creation(self):
        cases = [
            [{**self.row, "status": "paused"}],
            [{**self.row, "is_repo_workspace": True}],
            [{**self.row, "linked_from_worktree_id": "foreign"}],
            [{**self.row, "linked_worktree_ids": ["another"]}],
            [{**self.row, "repo_id": "foreign"}],
            [self.row, {**self.row, "id": "other"}],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                self.rows[:] = rows
                with self.assertRaises(RuntimeError):
                    self.ensure()
        self.assertEqual(self.calls, 0)

    def test_changed_issue_or_wrong_pr_selector_is_not_silently_adopted(self):
        self.rows.append(self.row)
        with self.assertRaises(RuntimeError):
            workspace.ensure("SecPal/.github", 1224, 1230, None)
        self.assertEqual(self.calls, 0)

    def test_unavailable_combined_native_binding_stops_before_creation(self):
        def metadata(path, kind, number, repo):
            if kind == "issue":
                return self.metadata
            return {**self.metadata, "number": 1230,
                    "url": "https://github.com/SecPal/.github/pull/1230"}
        with patch.object(workspace, "github", side_effect=metadata):
            with self.assertRaises(RuntimeError):
                workspace.ensure("SecPal/.github", 1224, 1230, None)
            self.assertEqual(self.calls, 0)
            self.rows.append({**self.row, "pr_number": 1230})
            self.assertFalse(workspace.ensure("SecPal/.github", 1224, 1230, None)["created"])

    def test_unrelated_workspace_is_untouched(self):
        other = {**self.row, "id": "other", "issue_number": 999}
        self.rows.append(other)
        self.ensure()
        self.assertEqual(self.rows[0], other)
        self.assertEqual(self.calls, 1)

    def test_closed_issue_or_wrong_github_identity_stops_before_creation(self):
        for change in [{"state": "CLOSED"}, {"number": 999},
                       {"url": "https://github.com/other/repo/issues/1224"}]:
            with self.subTest(change=change):
                with patch.object(workspace, "github", return_value={**self.metadata, **change}):
                    with self.assertRaises(RuntimeError):
                        self.ensure()
        self.assertEqual(self.calls, 0)

    def test_unavailable_native_or_graph_authority_never_becomes_approval_prompt(self):
        for name in ["read_work_graph", "repository"]:
            with patch.object(workspace, name, side_effect=RuntimeError("authority-unavailable")):
                with self.assertRaisesRegex(RuntimeError, "authority-unavailable"):
                    self.ensure()
        self.assertEqual(self.calls, 0)

    def test_read_only_resolve_never_creates_a_workspace(self):
        with self.assertRaises(RuntimeError):
            workspace.resolve("SecPal/.github", 1224, None, None)
        self.assertEqual(self.calls, 0)

    def test_exact_workspace_id_still_checks_issue_ownership(self):
        self.rows.append(self.row)
        with self.assertRaises(RuntimeError):
            workspace.resolve("SecPal/.github", 999, None, None, self.row["id"])
        self.assertEqual(self.calls, 0)


class DispatchTests(unittest.TestCase):
    def test_issue_exec_ensures_context_before_dispatch_without_an_id(self):
        result = {"workspace_id": "73355d10", "path": "/authenticated/workspace"}
        with (patch.object(workspace, "ensure", return_value=result) as ensure,
              patch.object(workspace.os, "chdir") as chdir,
              patch.object(workspace.os, "execvp", side_effect=SystemExit(0)) as execute,
              patch.dict(workspace.os.environ)):
            with self.assertRaises(SystemExit):
                workspace.main(["exec", "--repo", "SecPal/.github", "--issue", "1224",
                                "--", "git", "status", "--short"])
            ensure.assert_called_once_with("SecPal/.github", 1224, None, None)
            chdir.assert_called_once_with(Path(result["path"]))
            execute.assert_called_once_with("git", ["git", "status", "--short"])

    def test_missing_command_never_provisions_an_execution_context(self):
        with (patch.object(workspace, "ensure") as ensure,
              patch.object(workspace.os, "execvp") as execute):
            self.assertEqual(workspace.main([
                "exec", "--repo", "SecPal/.github", "--issue", "1224"]), 2)
            ensure.assert_not_called()
            execute.assert_not_called()

    def test_explicit_workspace_exec_reuses_authenticated_mapping(self):
        with (patch.object(workspace, "ensure") as ensure,
              patch.object(workspace, "resolve", return_value=Path("/exact")) as resolve,
              patch.object(workspace.os, "chdir"),
              patch.object(workspace.os, "execvp", side_effect=SystemExit(0)),
              patch.dict(workspace.os.environ)):
            with self.assertRaises(SystemExit):
                workspace.main(["exec", "--repo", "SecPal/.github", "--workspace-id",
                                "73355d10", "--", "git", "status"])
            ensure.assert_not_called()
            resolve.assert_called_once_with("SecPal/.github", None, None, None, "73355d10")


class RepositoryIdentityTests(unittest.TestCase):
    def test_registration_is_exact_without_another_repository_inventory(self):
        row = {"id": "832b2ca0", "name": "SecPal/.github", "path": "/existing"}
        for rows in [[], [row, row], [{**row, "name": "SecPal/renamed"}]]:
            with self.subTest(rows=rows), patch.object(workspace, "api_get", return_value=rows):
                with self.assertRaises(RuntimeError):
                    workspace.repository("SecPal/.github")
        with patch.object(workspace, "api_get", return_value=[row]):
            self.assertEqual(workspace.repository("SecPal/.github"), row)
            with self.assertRaises(RuntimeError):
                workspace.repository("Untrusted/.github")


class FilesystemAdmissionTests(unittest.TestCase):
    def test_native_git_workspace_view_and_dirty_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            clone = root / "832b2ca0" / "plucky-otter"
            clone.mkdir(parents=True)
            subprocess.run(["git", "init", "--initial-branch=topic", str(clone)],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(clone), "remote", "add", "origin",
                            "https://github.com/SecPal/.github.git"], check=True)
            pending = clone / "pending"
            pending.write_bytes(b"uncommitted")
            row = {"id": "73355d10", "repo_id": "832b2ca0", "path": str(clone),
                   "branch": "topic"}
            with patch.object(workspace, "CLONE_ROOT", root):
                with patch.object(workspace, "git_head", return_value="a" * 40):
                    result = workspace.workspace_result("SecPal/.github", row, None)
                    self.assertTrue(result["dirty"])
                    self.assertEqual(pending.read_bytes(), b"uncommitted")
                    for change in [{"branch": "foreign"}, {"path": str(root)},
                                   {"repo_id": "foreign"}]:
                        with self.assertRaises(RuntimeError):
                            workspace.workspace_result("SecPal/.github", {**row, **change}, None)
                    with self.assertRaises(RuntimeError):
                        workspace.workspace_result("SecPal/api", row, None)
                    with self.assertRaises(RuntimeError):
                        workspace.workspace_result("SecPal/.github", row, "b" * 40)


if __name__ == "__main__":
    unittest.main()
