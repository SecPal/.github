#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Pre-create execution fence; native Polyscope remains the workspace registry."""
from __future__ import annotations
import argparse
import base64
import contextlib
import fcntl
import functools
import importlib.util
import importlib.machinery
import json
import os
import pwd
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

QUALIFIED_SERVER_SHA256 = "a9d6865ab8e7789a0914b1d3d1aaf62f61f864f29b02c4ff55547a58da48f886"

COORDINATOR_PATH = Path("/usr/local/bin/secpal-polyscope-workspace")
DEFAULT_POLICY_PATH = Path("/etc/secpal/workspace-isolation.json")
REQUIRED_MARKER_PATH = Path("/etc/secpal/workspace-isolation.required")

class IsolationError(RuntimeError):
    pass

@functools.lru_cache(maxsize=1)
def coordinator():
    path = Path(__file__).with_name("secpal-polyscope-workspace.py")
    if not path.is_file():
        path = COORDINATOR_PATH
    name = "_secpal_workspace_owner"
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def snapshot(owner):
    return [dict(id=r["id"], name=r["name"], path=r.get("path"), linked_repo_ids=r.get("linked_repo_ids", []),
                 workspaces=owner.native_workspaces(r)) for r in owner.api_get("/repos")]

def index(records, clone_root):
    repos, rows, seen_paths = {}, {}, set()
    root = Path(clone_root)
    if not root.is_absolute() or str(root) != clone_root:
        raise IsolationError("clone-root")
    for repo in records:
        rid = repo["id"]
        if rid in repos or not re.fullmatch(r"[A-Za-z0-9_.-]+", rid):
            raise IsolationError("repository-identity")
        repos[rid] = repo
        for row in repo["workspaces"]:
            ident, path = row["id"], Path(row["path"])
            base = row.get("is_repo_workspace") is True and row["path"] == repo.get("path")
            if (not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", ident)
                    or ident in rows or str(path) in seen_paths or row["repo_id"] != rid or not path.is_absolute()
                    or str(path) != row["path"] or ".." in path.parts or (not base and path.parent != root / rid)
                    or path.name in (".", "..") or row.get("status") not in ("active", "archived", "merged", "paused")):
                raise IsolationError("native-identity")
            rows[ident] = row
            seen_paths.add(str(path))
    return repos, rows

def reservation(records, repo, issue, clone_root):
    repos, rows = index(records, clone_root)
    roots = [r for r in repos.values() if r["name"] == repo]
    if len(roots) != 1 or type(issue) is not int or issue < 1:
        raise IsolationError("task-identity")
    source = roots[0]
    if any(w["repo_id"] == source["id"] and w.get("issue_number") == issue for w in rows.values()):
        raise IsolationError("reservation-must-precede-create")
    related = [source["id"], *source["linked_repo_ids"]]
    if len(related) != len(set(related)) or not set(related) <= repos.keys():
        raise IsolationError("repository-group")
    # This is an immutable before-ID fence, not a catalog of generated workspaces.
    return dict(version=1, repo=repo, issue=issue, repo_id=source["id"],
                related_repo_ids=sorted(related), clone_root=clone_root,
                before_ids=sorted(rows))

def validate_policy(policy, records):
    try:
        if (type(policy["version"]) is not int or policy["version"] != 1 or type(policy["issue"]) is not int or policy["issue"] < 1
                or not isinstance(policy["before_ids"], list)
                or len(policy["before_ids"]) != len(set(policy["before_ids"]))):
            raise IsolationError("reservation-shape")
        repos, rows = index(records, policy["clone_root"])
        source = repos[policy["repo_id"]]
        expected = sorted([source["id"], *source["linked_repo_ids"]])
        if source["name"] != policy["repo"] or expected != policy["related_repo_ids"]:
            raise IsolationError("reservation-repository-drift")
        return repos, rows
    except (KeyError, TypeError, ValueError):
        raise IsolationError("reservation-invalid") from None

def complete_group(row, repos, rows):
    if row.get("linked_from_worktree_id") is not None or (
            row.get("issue_number") is None and row.get("pr_number") is None):
        return None
    members = {row["id"], *row.get("linked_worktree_ids", [])}
    expected = {row["repo_id"], *repos[row["repo_id"]]["linked_repo_ids"]}
    if not members <= rows.keys() or {rows[i]["repo_id"] for i in members} != expected:
        return None
    if len(members) != len(expected):
        raise IsolationError("group-duplicate-repository")
    for ident in members:
        member = rows[ident]
        if (member.get("status") != "active" or member.get("is_repo_workspace")
                or set(member.get("linked_worktree_ids", [])) != members - {ident}):
            raise IsolationError("group-inconsistent")
        if ident != row["id"] and (member.get("linked_from_worktree_id") != row["id"]
                or member.get("issue_number") is not None or member.get("pr_number") is not None):
            raise IsolationError("group-child-ownership")
    if any((r.get("linked_from_worktree_id") in members
            or members.intersection(r.get("linked_worktree_ids", [])))
           for ident, r in rows.items() if ident not in members):
        raise IsolationError("group-shared")
    return members

def classify(policy, records, path, *, pending=False):
    """True means quarantine; unknown paths/authority never mean permission."""
    repos, rows = validate_policy(policy, records)
    matches = [r for r in rows.values() if r["path"] == str(path)]
    if len(matches) != 1:
        raise IsolationError("workspace-not-exact")
    row = matches[0]
    targets = [r for r in rows.values() if r["repo_id"] == policy["repo_id"]
               and r.get("issue_number") == policy["issue"]]
    if len(targets) > 1:
        raise IsolationError("task-ambiguous")
    protected = set()
    for target in targets:
        protected |= {target["id"], *target.get("linked_worktree_ids", [])}
    if row["id"] in protected or row.get("linked_from_worktree_id") in protected:
        return True
    if row.get("is_repo_workspace") and row.get("issue_number") is None and row.get("pr_number") is None:
        return False
    if row["id"] in policy["before_ids"]:
        if protected.intersection(row.get("linked_worktree_ids", [])):
            raise IsolationError("prior-workspace-rebound")
        return False
    if pending:
        return True
    # Complete, independently bound later groups continue normal provisioning.
    for candidate in rows.values():
        if candidate in targets:
            continue
        members = complete_group(candidate, repos, rows)
        if members and row["id"] in members:
            return False
    # A new, incomplete/unbound child cannot outrun its parent's registration.
    return row["repo_id"] in policy["related_repo_ids"]

def trusted_bytes(path, *, owner_uid=0):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid or info.st_mode & 0o022:
            raise IsolationError("reservation-owner-mode")
        # All ancestors are authority too; a writable directory permits replacement.
        for parent in path.absolute().parents:
            s = parent.stat()
            if s.st_uid != owner_uid or s.st_mode & 0o022:
                raise IsolationError("reservation-parent")
        with os.fdopen(os.dup(fd), "rb") as stream:
            return stream.read()
    finally:
        os.close(fd)

def load_policy(path, *, owner_uid=0):
    return json.loads(trusted_bytes(path, owner_uid=owner_uid))


@contextlib.contextmanager
def native_fence(owner):
    fd = os.open(owner.LOCK_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1:
            raise IsolationError("creation-fence-owner-mode")
        fcntl.flock(fd, fcntl.LOCK_SH)
        raw = os.read(fd, 4096)
        yield bool(raw.strip())
    finally:
        os.close(fd)

def server_digest(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_server(policy):
    try:
        path = Path(policy["server_bin"])
        if (not path.is_absolute() or path.resolve(strict=True) != path
                or policy["server_sha256"] != QUALIFIED_SERVER_SHA256
                or server_digest(path) != QUALIFIED_SERVER_SHA256):
            raise IsolationError("native-version-unqualified")
        return path
    except (KeyError, TypeError, OSError):
        raise IsolationError("native-version-unqualified") from None


class Gate:
    def __init__(self, policy_path, owner=None):
        self.policy = load_policy(policy_path)
        # Rehash current bytes: deployment tools can preserve timestamps.
        validate_server(self.policy)
        self.owner = owner or coordinator()

    @contextlib.contextmanager
    def observation(self):
        with native_fence(self.owner) as pending:
            records = snapshot(self.owner)
            validate_policy(self.policy, records)
            yield records, pending

    def blocked_paths(self):
        with self.observation() as (records, pending):
            return {r["path"] for repo in records for r in repo["workspaces"]
                    if classify(self.policy, records, r["path"], pending=pending)}

def guarded_command(policy_path, command, *, cwd=None, owner=None):
    gate = Gate(policy_path, owner)
    with gate.observation() as (records, pending):
        if classify(gate.policy, records, str(cwd or Path.cwd()), pending=pending):
            return 0
    # Admission is bounded. Persistent queue/scheduler commands must not pin
    # the create fence; creation cannot rebind an existing admitted workspace.
    return subprocess.run(command, cwd=cwd, check=False).returncode

def publish_policy(path, data):
    """Publish complete authority atomically, without replacing an existing file."""
    path = Path(path)
    for parent in path.absolute().parents:
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise IsolationError("reservation-parent")
    fd, temporary = tempfile.mkstemp(prefix=".workspace-isolation-", dir=path.parent)
    temporary = Path(temporary)
    published = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(data, sort_keys=True).encode())
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        if load_policy(temporary) != data:
            raise IsolationError("reservation-readback")
        # Hardlink publication is atomic and exclusive; only complete bytes
        # become visible to concurrent watcher/timer processes.
        os.link(temporary, path, follow_symlinks=False)
        published = True
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if load_policy(path) != data:
            raise IsolationError("reservation-readback")
    except BaseException:
        if published and path.samefile(temporary):
            path.unlink()
        raise
    finally:
        temporary.unlink(missing_ok=True)


def arm(policy_path, model, server_bin):
    """Administrative reservation before creation; no generated-ID assignment."""
    if os.geteuid() != 0 or not re.fullmatch(r"[a-z0-9._:-]{1,128}", model) or model.startswith("claude-"):
        raise IsolationError("arm-authority-or-model")
    owner = coordinator()
    # Root publishes for the dedicated service, never its own or the app home.
    try:
        service_uid = pwd.getpwnam("polyscope").pw_uid
    except KeyError:
        raise IsolationError("polyscope-service-account-missing") from None
    if service_uid == 0:
        raise IsolationError("polyscope-service-account-root")
    owner.configure_paths(service_uid)
    lock = owner.LOCK_PATH
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != service_uid or info.st_mode & 0o077 or info.st_nlink != 1:
            raise IsolationError("creation-fence-owner-mode")
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.read(fd, 4096).strip():
            raise IsolationError("creation-outcome-unresolved")
        data = reservation(snapshot(owner), "SecPal/api", 2639, str(owner.CLONE_ROOT))
        binary = Path(server_bin).resolve(strict=True)
        data.update(model=model, server_bin=str(binary), server_sha256=QUALIFIED_SERVER_SHA256)
        validate_server(data)
        # A missing JSON must never silently disarm already guarded consumers.
        # Publish the durable fail-closed marker first, and retain it on failure.
        if REQUIRED_MARKER_PATH.exists() or REQUIRED_MARKER_PATH.is_symlink():
            trusted_bytes(REQUIRED_MARKER_PATH)
        else:
            publish_policy(REQUIRED_MARKER_PATH, {"version": 1})
        publish_policy(policy_path, data)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--command-base64")
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--server-bin")
    args = parser.parse_args()
    try:
        if args.arm:
            if args.command_base64 or not args.model or not args.server_bin:
                raise IsolationError("arm-arguments")
            arm(args.policy, args.model, args.server_bin)
            return 0
        if args.model or args.server_bin or not args.command_base64:
            raise IsolationError("command-arguments")
        command = base64.b64decode(args.command_base64, validate=True).decode()
        return guarded_command(args.policy, ["/bin/bash", "-c", command])
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        print("workspace-isolation: authorization-unavailable", file=sys.stderr)
        return 75


def from_environment():
    path = os.environ.get("SECPAL_WORKSPACE_ISOLATION_POLICY")
    default = DEFAULT_POLICY_PATH
    if not path and (default.exists() or REQUIRED_MARKER_PATH.exists()
                     or REQUIRED_MARKER_PATH.is_symlink()):
        path = str(default)
    return Gate(path) if path else None

def wrap_config(config, policy_path):
    import copy
    import shlex
    result = copy.deepcopy(config)
    scripts = result.setdefault("scripts", {})
    def wrap(command):
        encoded = base64.b64encode(command.encode()).decode()
        return shlex.join(["/usr/bin/python3", str(Path(__file__).resolve()),
                           "--policy", str(policy_path), "--command-base64", encoded])
    setup = scripts.get("setup")
    if setup:
        scripts["setup"] = [wrap(setup if isinstance(setup, str) else " && ".join(setup))]
    actions = scripts.get("run", [])
    if isinstance(actions, str):
        actions = [actions]
    scripts["run"] = [wrap(a) if isinstance(a, str) else dict(a, command=wrap(a["command"])) for a in actions]
    return result

if __name__ == "__main__":
    raise SystemExit(main())
