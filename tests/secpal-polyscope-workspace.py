#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coordinator behavior against native Polyscope representations, without live writes."""
import concurrent.futures
import copy
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import threading
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

    def test_confirmed_rejection_with_no_native_registration_allows_corrected_retry(self):
        self.mocks[-1].side_effect = RuntimeError("polyscope-create-rejected")
        with self.assertRaisesRegex(RuntimeError, "polyscope-create-rejected"):
            self.ensure()
        self.assertEqual((self.root / "create.lock").read_text(), "")
        self.mocks[-1].side_effect = self.create
        self.assertTrue(self.ensure()["created"])
        self.assertEqual(len(self.rows), 1)

    def test_unsupported_issue_sha_pin_fails_before_native_creation(self):
        with self.assertRaisesRegex(RuntimeError, "native-issue-sha-create-unavailable"):
            workspace.ensure("SecPal/.github", 1224, None, "a"*40)
        self.assertEqual(self.calls, 0)

    def test_unsupported_pr_sha_pin_fails_before_native_creation(self):
        metadata = {**self.metadata, "number": 1225, "headRefOid": "a"*40,
                    "url": "https://github.com/SecPal/.github/pull/1225"}
        with patch.object(workspace, "github", return_value=metadata):
            with self.assertRaisesRegex(RuntimeError, "native-pr-sha-create-unavailable"):
                workspace.ensure("SecPal/.github", None, 1225, "a"*40)
        self.assertEqual(self.calls, 0)

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
        def metadata(kind, number, repo):
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
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        git = directory / "git"
        git.write_text("#!/bin/sh\nexit 0\n")
        git.chmod(0o755)
        configured = patch.object(workspace, "GIT_BIN_DIR", directory)
        configured.start()
        self.addCleanup(configured.stop)

    def test_missing_managed_wrapper_fails_before_setup_or_dispatch(self):
        with (patch.object(workspace, "GIT_BIN_DIR", Path("/nonexistent/managed-git")),
              patch.object(workspace, "ensure") as ensure,
              patch.object(workspace.os, "execvp") as execute):
            self.assertEqual(workspace.main([
                "exec", "--repo", "SecPal/.github", "--issue", "1224",
                "--", "git", "status"]), 2)
            ensure.assert_not_called()
            execute.assert_not_called()

    def test_issue_exec_ensures_context_before_dispatch_without_an_id(self):
        result = {"workspace_id": "73355d10", "path": "/authenticated/workspace"}
        def admitted(*args):
            self.assertEqual(shutil.which("git"), str(workspace.GIT_BIN_DIR / "git"))
            return result
        with (patch.object(workspace, "ensure", side_effect=admitted) as ensure,
              patch.object(workspace.os, "chdir") as chdir,
              patch.object(workspace.os, "execvp", side_effect=SystemExit(0)) as execute,
              patch.dict(workspace.os.environ)):
            with self.assertRaises(SystemExit):
                workspace.main(["exec", "--repo", "SecPal/.github", "--issue", "1224",
                                "--", "git", "status", "--short"])
            ensure.assert_called_once_with("SecPal/.github", 1224, None, None)
            chdir.assert_called_once_with(Path(result["path"]))
            wrapper = str(workspace.GIT_BIN_DIR / "git")
            execute.assert_called_once_with(wrapper, [wrapper, "status", "--short"])

    def test_dispatch_resolves_git_through_existing_managed_wrapper(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            git = directory / "git"
            git.write_text("#!/bin/sh\nexit 0\n")
            git.chmod(0o755)
            def execute(*args):
                self.assertEqual(shutil.which("git"), str(git))
                raise SystemExit(0)
            with (patch.object(workspace, "GIT_BIN_DIR", directory, create=True),
                  patch.object(workspace, "ensure", return_value={"path": "/exact"}),
                  patch.object(workspace.os, "chdir"),
                  patch.object(workspace.os, "execvp", side_effect=execute),
                  patch.dict(workspace.os.environ)):
                with self.assertRaises(SystemExit):
                    workspace.main(["exec", "--repo", "SecPal/.github", "--issue",
                                    "1224", "--", "git", "status"])

    def test_absolute_git_dispatch_retains_the_existing_wrapper(self):
        with (patch.object(workspace, "resolve", return_value=Path("/exact")),
              patch.object(workspace.os, "chdir"),
              patch.object(workspace.os, "execvp", side_effect=SystemExit(0)) as execute,
              patch.dict(workspace.os.environ)):
            with self.assertRaises(SystemExit):
                workspace.main(["exec", "--repo", "SecPal/.github", "--workspace-id",
                                "73355d10", "--", "/usr/bin/git", "status"])
            wrapper = str(workspace.GIT_BIN_DIR / "git")
            execute.assert_called_once_with(wrapper, [wrapper, "status"])

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


class NativeRelationshipTests(unittest.TestCase):
    def test_native_relationship_read_accepts_blocked_work_and_rejects_partial_evidence(self):
        issue = {"number": 1224, "url": "https://github.com/SecPal/.github/issues/1224",
                 "parent": None, "blockedBy": {"totalCount": 2},
                 "blocking": {"totalCount": 1}, "subIssues": {"totalCount": 0}}
        value = {"data": {"repository": {"issue": issue}}}
        with (patch.object(workspace, "command", return_value=json.dumps(value)) as command,
              patch.object(workspace, "repository",
                           return_value={"path": "/untrusted/registered/path"})):
            workspace.read_work_graph("SecPal/.github", 1224)
            self.assertEqual(command.call_args.args[0][:3], ["gh", "api", "graphql"])
        for value in [
            {"errors": [{"message": "partial private error"}]},
            {"data": {"repository": {"issue": None}}},
            {"data": {"repository": {"issue": {**issue, "number": 999}}}},
        ]:
            with patch.object(workspace, "command", return_value=json.dumps(value)):
                with self.assertRaises(RuntimeError):
                    workspace.read_work_graph("SecPal/.github", 1224)


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


class RuntimeConfigurationTests(unittest.TestCase):
    def test_existing_configured_state_clone_root_and_api_are_consumed(self):
        with tempfile.TemporaryDirectory() as raw:
            with patch.dict(workspace.os.environ, {
                    "POLYSCOPE_HOME": raw + "/state",
                    "POLYSCOPE_CLONE_ROOT": raw + "/clones",
                    "POLYSCOPE_API_BASE": "http://127.0.0.1:5432/api"}):
                candidate = importlib.util.spec_from_file_location(
                    "configured_workspace", ROOT / "scripts/secpal-polyscope-workspace.py")
                module = importlib.util.module_from_spec(candidate)
                candidate.loader.exec_module(module)
                self.assertEqual(module.CLONE_ROOT, Path(raw + "/clones"))
                self.assertEqual(module.API_BASE, "http://127.0.0.1:5432/api")

    def test_opaque_repository_ids_are_path_safe_and_uri_encoded(self):
        for identifier in ["api12345", "gh123456", "opaque #?"]:
            row = {"id": identifier, "name": "SecPal/.github", "path": "/existing"}
            with patch.object(workspace, "api_get", return_value=[row]) as api:
                record = workspace.repository("SecPal/.github")
            with patch.object(workspace, "api_get", return_value=[]) as api:
                self.assertIsNone(workspace.lookup(record, 1224, None))
                from urllib.parse import quote
                api.assert_called_once_with("/repos/" + quote(identifier, safe="") + "/worktrees")
        for identifier in ["", ".", "..", "../foreign", "two/parts", "x"*129, None]:
            row = {"id": identifier, "name": "SecPal/.github"}
            with patch.object(workspace, "api_get", return_value=[row]):
                with self.assertRaises(RuntimeError):
                    workspace.repository("SecPal/.github")


class LoopbackTransportTests(unittest.TestCase):
    def test_loopback_authority_cannot_be_replaced_by_proxy_or_redirect(self):
        hits = []
        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"authority":"proxy"}')
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        proxy_url = "http://127.0.0.1:" + str(proxy.server_port)
        class Native(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if self.path.endswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", proxy_url + "/redirected")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"authority":"native-loopback"}')
        native = ThreadingHTTPServer(("127.0.0.1", 0), Native)
        for server in (proxy, native):
            thread = threading.Thread(target=lambda s=server: s.serve_forever(poll_interval=0.01))
            thread.start()
            self.addCleanup(thread.join)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(native.server_port) + "/api"
        with (patch.object(workspace, "API_BASE", base),
              patch.dict(workspace.os.environ, {"http_proxy": proxy_url, "HTTP_PROXY": proxy_url,
                                                "no_proxy": "", "NO_PROXY": ""}),
              patch.object(workspace.urllib.request, "_opener", None)):
            self.assertEqual(workspace.api_get("/repos"), {"authority": "native-loopback"})
            with self.assertRaises(RuntimeError):
                workspace.api_get("/redirect")
        self.assertEqual(hits, [])


class BridgeBoundaryTests(unittest.TestCase):
    def test_configured_loopback_origin_reaches_native_bridge(self):
        result = subprocess.CompletedProcess([], 0, stdout='{"id":"native-id"}', stderr="")
        with (patch.object(workspace, "API_BASE", "http://127.0.0.1:5432/api"),
              patch.dict(workspace.os.environ, {"HTTP_PROXY": "http://untrusted.invalid",
                                                "https_proxy": "http://untrusted.invalid"}),
              patch.object(workspace.subprocess, "run", return_value=result) as run):
            row = workspace.create_native(
                {"id": "opaque-id"}, {"number": 1224, "title": "Work", "url": "issue",
                                     "body": "Authorized scope"}, 1224, None, None, [])
            self.assertEqual(row["id"], "native-id")
            self.assertEqual(len(run.call_args.args[0]), 2)
            payload = json.loads(run.call_args.kwargs["input"])
            environment = run.call_args.kwargs["env"]
            self.assertNotIn("HTTP_PROXY", environment)
            self.assertNotIn("https_proxy", environment)
            self.assertEqual(environment["NO_PROXY"], "*")
            self.assertEqual(environment["no_proxy"], "*")
            self.assertEqual(payload["socketUrl"],
                             "ws://127.0.0.1:5432/ws?client=secpal-workspace-bridge")

    def test_closed_bridge_failure_survives_nonzero_process_exit(self):
        result = subprocess.CompletedProcess(
            [], 2, stdout='{"error":"polyscope-create-rejected"}',
            stderr="untrusted server detail must not become a diagnostic")
        def native(*args, **kwargs):
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(2, args[0], output=result.stdout,
                                                    stderr=result.stderr)
            return result
        with patch.object(workspace.subprocess, "run", side_effect=native):
            with self.assertRaisesRegex(RuntimeError, "^polyscope-create-rejected$"):
                workspace.create_native(
                    {"id": "opaque-id"}, {"number": 1224, "title": "Work", "url": "issue",
                                         "body": "Authorized scope"}, 1224, None, None, [])

    def test_nonlocal_or_credentialed_api_configuration_fails_before_io(self):
        for base in ["https://remote.invalid/api", "http://name:value@localhost/api",
                     "http://localhost/api?target=other", "http://localhost/wrong"]:
            with (self.subTest(base=base), patch.object(workspace, "API_BASE", base),
                  patch.object(workspace.urllib.request, "urlopen") as request):
                with self.assertRaisesRegex(RuntimeError, "polyscope-api-configuration"):
                    workspace.api_get("/repos")
                request.assert_not_called()


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
                    fake_bin = root / "untrusted-bin"
                    fake_bin.mkdir()
                    marker = root / "untrusted-git-ran"
                    fake_git = fake_bin / "git"
                    fake_git.write_text("#!/bin/sh\ntouch " + str(marker) + "\nexit 1\n")
                    fake_git.chmod(0o755)
                    with patch.dict(workspace.os.environ, {"PATH": str(fake_bin) + ":/usr/bin:/bin"}):
                        admitted = workspace.workspace_result("SecPal/.github", row, None)
                        self.assertTrue(admitted["dirty"])
                    self.assertFalse(marker.exists())
                    for override in [
                        {"GIT_DIR": str(root / "wrong-git-dir")},
                        {"GIT_WORK_TREE": str(root / "wrong-tree")},
                        {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "remote.origin.url",
                         "GIT_CONFIG_VALUE_0": "https://github.com/other/repository.git"},
                    ]:
                        with patch.dict(workspace.os.environ, override):
                            self.assertTrue(workspace.workspace_result(
                                "SecPal/.github", row, None)["dirty"])
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
