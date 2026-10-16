#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trusted coordinator for the existing native Polyscope workspace interface.

The caller owns task authorization. This helper grants no execution/merge/cloud
authority. Native Polyscope records remain the only workspace registry.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import time
import urllib.request

POLYSCOPE_HOME = Path(pwd.getpwuid(os.geteuid()).pw_dir)
CLONE_ROOT = POLYSCOPE_HOME / ".polyscope" / "clones"
API_BASE = "http://127.0.0.1:4321/api"
WS_CLIENT = Path(__file__).resolve().with_name("secpal-polyscope-workspace-ws.js")
if not WS_CLIENT.is_file():
    WS_CLIENT = Path("/usr/local/libexec/secpal-polyscope-workspace-ws.js")
LOCK_PATH = POLYSCOPE_HOME / ".local/state/polyscope/workspace-create.lock"


def command(arguments, *, cwd=None, timeout=30):
    """Bounded, non-secret transport diagnostic; never forward provider stderr."""
    try:
        return subprocess.run(arguments, cwd=cwd, check=True, capture_output=True,
                              text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("command-unavailable") from None


def api_get(path):
    try:
        with urllib.request.urlopen(API_BASE + path, timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError):
        raise RuntimeError("polyscope-api-unavailable") from None


def git_head(workspace):
    return command(["git", "-C", str(workspace), "rev-parse", "HEAD"])


def repository(repo):
    if not re.fullmatch(r"SecPal/[A-Za-z0-9._-]+", repo):
        raise RuntimeError("repository-identity")
    matches = [item for item in api_get("/repos") if item.get("name") == repo]
    if len(matches) != 1 or not re.fullmatch(r"[a-f0-9-]{8,64}", matches[0]["id"]):
        raise RuntimeError("repository-registration")
    return matches[0]


def github(repo_path, kind, number, repo):
    fields = ("number,title,url,headRefName,baseRefName,body,isDraft,headRefOid,state"
              if kind == "pr" else "number,title,url,body,state")
    return json.loads(command(
        ["gh", kind, "view", str(number), "--repo", repo, "--json", fields],
        cwd=repo_path))


def read_work_graph(repo, issue):
    # Reuse the read-only resolver. A blocked task may still need a workspace;
    # do not turn planning readiness into another delivery/merge gate.
    # The existing registration identifies the maintained governance checkout;
    # do not invent another workspace/repository catalog in the coordinator.
    root = Path(repository("SecPal/.github")["path"])
    resolver = root / "scripts/secpal-work-graph.py"
    command([sys.executable, str(resolver), "show", f"{repo}#{issue}"], timeout=60)


def select_workspace(rows, repo_id, issue, pr, workspace_id=None):
    """Pure exact scope admission over native API records, including paused rows."""
    if issue is None and pr is None and workspace_id is None:
        raise RuntimeError("workspace-selector-required")
    matches = [
        row for row in rows
        if ((workspace_id is not None and row["id"] == workspace_id)
            or (workspace_id is None and (
                (issue is not None and row.get("issue_number") == issue)
                or (pr is not None and row.get("pr_number") == pr))))
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise RuntimeError("workspace-ambiguous")
    row = matches[0]
    if (row.get("repo_id") != repo_id
            or (issue is not None and row.get("issue_number") != issue)
            or (pr is not None and row.get("pr_number") != pr)):
        raise RuntimeError("workspace-ownership")
    if (row.get("status") != "active" or row.get("is_repo_workspace")
            or row.get("linked_from_worktree_id") or row.get("linked_worktree_ids")):
        raise RuntimeError("workspace-unusable-or-shared")
    return row


def workspace_result(repo, row, sha, *, created=False):
    path = Path(row["path"])
    root = CLONE_ROOT.resolve(strict=True)
    if (not path.is_absolute() or not path.is_dir() or path.is_symlink()
            or path.resolve(strict=True) != path
            or path.parent != root / row["repo_id"]):
        raise RuntimeError("workspace-path")
    remote = command(["git", "-C", str(path), "remote", "get-url", "origin"])
    if remote not in (f"https://github.com/{repo}.git", f"git@github.com:{repo}.git"):
        raise RuntimeError("workspace-git-origin")
    branch = command(["git", "-C", str(path), "symbolic-ref", "--short", "HEAD"])
    if branch != row["branch"] or branch in ("main", "master", "production"):
        raise RuntimeError("workspace-branch")
    head = git_head(path)
    if sha is not None and head != sha:
        raise RuntimeError("workspace-head")
    dirty = bool(command(["git", "-C", str(path), "status", "--porcelain"]))
    return {"workspace_id": row["id"], "path": str(path), "head": head,
            "branch": branch, "dirty": dirty, "created": created}


def lookup(repo_record, issue, pr, workspace_id=None):
    rows = api_get(f"/repos/{repo_record['id']}/worktrees")
    return select_workspace(rows, repo_record["id"], issue, pr, workspace_id)


def resolve(repo, issue, pr, sha, workspace_id=None):
    """Strictly read-only; never turns missing/invalid ownership into creation."""
    record = repository(repo)
    row = lookup(record, issue, pr, workspace_id)
    if row is None:
        raise RuntimeError("workspace-not-found")
    return Path(workspace_result(repo, row, sha)["path"])


@contextmanager
def creation_lock():
    # One standard advisory lock serializes this coordinator's native creates.
    # Its in-flight fence is not a workspace catalog: IDs/ownership live only in
    # Polyscope. Never retry an unknown result just because the response was lost.
    LOCK_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (LOCK_PATH.parent.is_symlink()
            or LOCK_PATH.parent.stat().st_uid != os.geteuid()
            or LOCK_PATH.parent.stat().st_mode & 0o022):
        raise RuntimeError("workspace-lock-directory")
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o077):
            raise RuntimeError("workspace-lock-identity")
        until = time.monotonic() + 150
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= until:
                    raise RuntimeError("workspace-create-busy") from None
                time.sleep(0.1)
        with os.fdopen(os.dup(fd), "r+", encoding="utf-8") as stream:
            yield stream
    finally:
        os.close(fd)


def fence(stream, value):
    stream.seek(0)
    stream.truncate()
    if value is not None:
        json.dump(value, stream)
    stream.flush()
    os.fsync(stream.fileno())


def create_native(record, metadata, issue, pr, sha, before):
    repo_id = record["id"]
    if pr is not None:
        message = {"type": "worktree.create_from_pr", "repoId": repo_id,
                   "pr": {k: metadata[k] for k in [
                       "number", "title", "url", "headRefName", "baseRefName",
                       "body", "isDraft"]}}
    else:
        message = {"type": "worktree.create_from_issue", "repoId": repo_id,
                   "issue": {k: metadata[k] for k in ["number", "title", "url", "body"]}}
    payload = {"message": message, "beforeIds": [row["id"] for row in before],
               "expectedPr": pr, "expectedIssue": issue, "timeoutMs": 120000}
    return json.loads(command(["node", str(WS_CLIENT),
                               json.dumps(payload, separators=(",", ":"))], timeout=130))


def authenticate_task(repo, record, issue, pr, sha):
    if issue is None and pr is None:
        raise RuntimeError("issue-or-pr-required")
    metadata = None
    for kind, number in [("issue", issue), ("pr", pr)]:
        if number is None:
            continue
        if type(number) is not int or number < 1:
            raise RuntimeError("task-number")
        item = github(Path(record["path"]), kind, number, repo)
        segment = "pull" if kind == "pr" else "issues"
        if (item["number"] != number or item["state"] != "OPEN"
                or item["url"] != f"https://github.com/{repo}/{segment}/{number}"):
            raise RuntimeError("github-task-identity-or-state")
        if kind == "pr" and sha is not None and item["headRefOid"] != sha:
            raise RuntimeError("github-pr-head")
        metadata = item
    if issue is not None:
        read_work_graph(repo, issue)
    return metadata


def ensure(repo, issue, pr, sha):
    """ADOPT_OR_CREATE, called by the trusted coordinator before task dispatch."""
    record = repository(repo)
    with creation_lock() as stream:
        metadata = authenticate_task(repo, record, issue, pr, sha)
        # Reconcile even a previous interrupted/ambiguous create before another
        # mutation. A registered but invalid/paused/shared row remains an error.
        raw = stream.read(4096)
        pending = json.loads(raw) if raw else None
        before = api_get(f"/repos/{record['id']}/worktrees")
        row = select_workspace(before, record["id"], issue, pr)
        if row is not None:
            result = workspace_result(repo, row, sha)
            if (pending is not None
                    and (pending["repo"], pending["issue"], pending["pr"]) == (repo, issue, pr)):
                fence(stream, None)
            return result
        if pending is not None:
            prior_repo = repository(pending["repo"])
            prior = lookup(prior_repo, pending["issue"], pending["pr"])
            if prior is None:
                raise RuntimeError("create-outcome-unverified")
            workspace_result(pending["repo"], prior, pending["sha"])
            fence(stream, None)
        # Re-read after reconciling another native creation.
        before = api_get(f"/repos/{record['id']}/worktrees")
        row = select_workspace(before, record["id"], issue, pr)
        if row is not None:
            return workspace_result(repo, row, sha)
        # The supported create messages register either an Issue or a PR.
        # Do not create a partial ownership mapping for combined selectors.
        if issue is not None and pr is not None:
            raise RuntimeError("native-combined-binding-unavailable")
        fence(stream, {"repo": repo, "issue": issue, "pr": pr, "sha": sha})
        returned = None
        try:
            returned = create_native(record, metadata, issue, pr, sha, before)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            # Native API read-back, never a blind second create.
            pass
        row = lookup(record, issue, pr)
        if row is None:
            raise RuntimeError("create-outcome-unverified")
        if returned is not None and returned.get("id") != row["id"]:
            raise RuntimeError("create-readback-identity")
        result = workspace_result(repo, row, sha, created=True)
        fence(stream, None)
        return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="action", required=True)
    for action in ("resolve", "ensure", "create", "exec"):
        sub = subcommands.add_parser(action)
        sub.add_argument("--repo", required=True)
        sub.add_argument("--issue", type=int)
        sub.add_argument("--pr", type=int)
        sub.add_argument("--sha")
        if action in ("resolve", "exec"):
            sub.add_argument("--workspace-id")
        if action == "exec":
            sub.add_argument("command", nargs=argparse.REMAINDER)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        command_args = None
        if args.action == "exec":
            command_args = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command_args:
                raise RuntimeError("exec-command-required")
        if args.action in ("ensure", "create"):
            print(json.dumps(ensure(args.repo, args.issue, args.pr, args.sha)))
            return 0
        if args.action == "exec" and args.workspace_id is None:
            path = Path(ensure(args.repo, args.issue, args.pr, args.sha)["path"])
        else:
            path = resolve(args.repo, args.issue, args.pr, args.sha, args.workspace_id)
        if args.action == "resolve":
            print(path)
            return 0
        os.chdir(path)
        os.environ.update(HOME=str(POLYSCOPE_HOME),
                          LOGNAME=pwd.getpwuid(os.geteuid()).pw_name,
                          USER=pwd.getpwuid(os.geteuid()).pw_name,
                          PATH=f"{POLYSCOPE_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin")
        os.execvp(command_args[0], command_args)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        # Internal codes only, never raw GitHub/API/command output.
        code = str(error) if type(error) is RuntimeError else "workspace-observation-failed"
        print(f"secpal-polyscope-workspace: {code}", file=sys.stderr)
        return 2
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
