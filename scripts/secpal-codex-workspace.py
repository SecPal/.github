#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Execute development commands as codex against one attested native workspace."""
from __future__ import annotations
import argparse
import contextlib
import signal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile

guard_path = Path(__file__).with_name("polyscope-isolation.py")
if not guard_path.is_file():
    guard_path = Path("/usr/local/libexec/secpal/polyscope-isolation.py")
spec = importlib.util.spec_from_file_location("_isolation", guard_path)
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)
IsolationError = isolation.IsolationError
RECEIPT = Path("/etc/secpal/api-2639-development.json")
VIEW = Path("/srv/secpal-development/api-2639")
SCOPE = ("SecPal/api", 2639)
ENV = dict(PATH="/usr/bin:/bin", HOME="/home/codex", XDG_RUNTIME_DIR="/run/user/1001", LANG="C.UTF-8")

@contextlib.contextmanager
def interruptible():
    def stop(signum, frame):
        raise InterruptedError("development-interrupted")
    previous = {s:signal.signal(s,stop) for s in (signal.SIGTERM,signal.SIGINT)}
    try:
        yield
    finally:
        for sig,handler in previous.items():
            signal.signal(sig,handler)


def check_attestation(current, expected):
    try:
        for key in ("version", "repo", "repo_id", "issue", "workspace_id", "path", "branch", "filesystem"):
            if type(current[key]) is not type(expected[key]) or current[key] != expected[key]:
                raise IsolationError("native-identity-changed")
        if sorted(current["members"], key=lambda x:x["id"]) != sorted(expected["members"], key=lambda x:x["id"]):
            raise IsolationError("native-group-changed")
        ids = [x["id"] for x in current["members"]]
        if len(ids) != len(set(ids)) or len(ids) != 4 or current["workspace_id"] not in ids:
            raise IsolationError("native-group-shape")
    except (KeyError, TypeError):
        raise IsolationError("native-attestation-invalid") from None

def fresh_attestation():
    p = subprocess.run(
        ["/usr/bin/sudo", "-n", "-u", "secpal", "/usr/local/bin/secpal-polyscope-workspace",
         "resolve", "--repo", SCOPE[0], "--issue", str(SCOPE[1])],
        env=ENV, cwd="/", capture_output=True, text=True, check=True, timeout=20)
    return json.loads(p.stdout)

def mount_records():
    records = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        a = line.split()
        target = a[4].replace("\\040", " ").replace("\\134", "\\")
        records.append((Path(target), set(a[5].split(","))))
    return records

def audit_tree(root, *, shared_ok=False):
    root = Path(root)
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise IsolationError("workspace-root")
    device = root.stat().st_dev
    if any(p != root and p.is_relative_to(root) for p,flags in mount_records()):
        raise IsolationError("nested-mount")
    if not (root/".git").is_dir() or (root/".git").is_symlink():
        raise IsolationError("git-directory")
    if (root/".git/objects/info/alternates").exists() or (root/".git/commondir").exists():
        raise IsolationError("git-shared-store")
    files = []
    for base, dirs, names in os.walk(root, followlinks=False):
        for name in [*dirs, *names]:
            path = Path(base)/name
            info = path.lstat()
            if info.st_dev != device:
                raise IsolationError("filesystem-boundary")
            if stat.S_ISLNK(info.st_mode):
                if not path.resolve().is_relative_to(root):
                    raise IsolationError("external-symlink")
            elif stat.S_ISREG(info.st_mode):
                if info.st_mode & 0o6000 or "security.capability" in os.listxattr(path):
                    raise IsolationError("setid-file")
                if info.st_nlink > 1 and not shared_ok:
                    raise IsolationError("shared-inode")
                files.append(path)
            elif not stat.S_ISDIR(info.st_mode):
                raise IsolationError("special-file")
    return files

def prepare_tree(root, *, source_uid=1003):
    """Administrative pre-grant operation, never exposed by the codex CLI."""
    root = Path(root)
    if root.stat().st_uid != source_uid:
        raise IsolationError("source-owner")
    files = audit_tree(root, shared_ok=True)
    for path in files:
        info = path.stat()
        if info.st_uid != source_uid:
            raise IsolationError("mixed-source-owner")
        if path.name in (".env", ".git-credentials", ".npmrc", "auth.json"):
            raise IsolationError("credential-file")
    split = 0
    for path in files:
        before = path.stat()
        if before.st_nlink == 1:
            continue
        fd, temp = tempfile.mkstemp(prefix=".isolation-", dir=path.parent)
        os.close(fd)
        try:
            shutil.copy2(path, temp, follow_symlinks=False)
            os.chown(temp, before.st_uid, before.st_gid)
            after = path.stat()
            if (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_size) != (
                    after.st_dev,after.st_ino,after.st_mtime_ns,after.st_size):
                raise IsolationError("source-raced")
            if hashlib.sha256(Path(temp).read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
                raise IsolationError("copy-content")
            os.replace(temp, path)
            split += 1
        finally:
            Path(temp).unlink(missing_ok=True)
    audit_tree(root)
    subprocess.run(["/usr/bin/git", "-c", "safe.directory="+str(root),
                    "-C", str(root), "fsck", "--full", "--no-reflogs"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return split

def check_view(receipt):
    root = Path(receipt["view"])
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise IsolationError("view-path")
    for parent in root.parents:
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise IsolationError("view-parent")
    info = root.stat()
    if [info.st_dev,info.st_ino] != receipt["inode"] or info.st_uid != 1001 or info.st_gid != 1001:
        raise IsolationError("view-replaced")
    matches = [flags for path,flags in mount_records() if path == root]
    if len(matches) != 1 or not {"nosuid","nodev"} <= matches[0]:
        raise IsolationError("view-mount-flags")
    audit_tree(root)
    return root

class Launcher:
    def __init__(self, receipt_path=RECEIPT, attest=fresh_attestation, scope=SCOPE):
        self.receipt_path, self.attest, self.scope = receipt_path, attest, scope

    def authorize(self):
        if os.getuid()!=1001 or os.geteuid()!=1001:
            raise IsolationError("development-identity")
        receipt = isolation.load_policy(self.receipt_path)
        if (receipt["native"]["repo"],receipt["native"]["issue"]) != self.scope:
            raise IsolationError("task-scope")
        # Always refresh through the sole trusted coordinator before execution.
        check_attestation(self.attest(), receipt["native"])
        root = check_view(receipt)
        native_fs = receipt["native"]["filesystem"]
        if ([native_fs["device"], native_fs["inode"]] != receipt["inode"]
                or (native_fs["uid"], native_fs["gid"]) != (1003, 1003)):
            raise IsolationError("native-view-binding")
        if not isinstance(receipt["image"],str) or not __import__("re").fullmatch(r"sha256:[0-9a-f]{64}",receipt["image"]):
            raise IsolationError("image-pin")
        if not __import__("re").fullmatch(r"sha256:[0-9a-f]{64}",receipt["postgres_image"]):
            raise IsolationError("postgres-image-pin")
        hooks = Path(receipt["hooks_dir"])
        if hooks.is_symlink() or not hooks.is_dir() or list(hooks.iterdir()):
            raise IsolationError("hooks-directory")
        for path in (hooks,*hooks.parents):
            info = path.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise IsolationError("hooks-authority")
        config = Path(receipt["containers_conf"])
        isolation.trusted_bytes(config)
        if config.is_symlink() or config.stat().st_uid != 0 or config.stat().st_mode & 0o022:
            raise IsolationError("container-config")
        return receipt, root

    def podman(self, receipt, args, *, capture=False, timeout=None):
        env = dict(ENV, CONTAINERS_CONF=receipt["containers_conf"])
        return subprocess.run(
            ["/usr/bin/podman","--remote=false","--default-mounts-file=/dev/null",
             "--hooks-dir="+receipt["hooks_dir"],"--runtime=/usr/bin/crun","--root","/home/codex/.local/share/containers/storage",
             "--runroot","/run/user/1001/containers",*args],
            env=env, cwd="/", check=True, capture_output=capture, text=True, timeout=timeout)

    def execute(self, command, *, network="pasta", extra=()):
        with interruptible():
            return self._execute(command, network=network, extra=extra)

    def _execute(self, command, *, network="pasta", extra=()):
        receipt, root = self.authorize()
        if not command or command[0].startswith("-"):
            raise IsolationError("command-required")
        name = "secpal-codex-exec-"+secrets.token_hex(8)
        args = ["run","--rm","--no-healthcheck","--name",name,"--label","secpal.development.scope="+self.scope_label(),"--userns","keep-id","--user","1001:1001",
                "--read-only","--tmpfs","/tmp:rw,nosuid,nodev",
                "--cap-drop","ALL","--security-opt","no-new-privileges",
                "--network",network,"--unsetenv-all","-e",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "-e","HOME=/tmp","-e","COMPOSER_HOME=/tmp/composer",
                "-v",str(root)+":/work","-w","/work",*extra,receipt["image"],*command]
        try:
            return self.podman(receipt,args).returncode
        finally:
            # Killing a Podman client does not necessarily stop its container.
            self.podman(receipt,["rm","--force","--ignore",name],capture=True)

    def build(self):
        receipt, root = self.authorize()
        return self.podman(receipt,["build","--pull=never","--network=none",
                    "--tag","localhost/secpal-api-2639-development:local",str(root)]).returncode

    def scope_label(self):
        return self.scope[0]+"#"+str(self.scope[1])

    def remove_resources(self, receipt, resources):
        failed = []
        for kind, ident in reversed(resources):
            try:
                if kind == "container":
                    self.podman(receipt, ["rm", "--force", "--ignore", ident],
                                capture=True, timeout=30)
                else:
                    try:
                        self.podman(receipt, [kind, "exists", ident],
                                    capture=True, timeout=30)
                    except subprocess.CalledProcessError as error:
                        if error.returncode == 1:
                            continue
                        raise
                    self.podman(receipt, [kind, "rm", ident], capture=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                failed.append(kind + " " + ident)
        if failed:
            raise IsolationError("test-resource-cleanup-failed")

    def cleanup(self):
        # Resource rollback needs no live API: it cannot execute workspace code.
        if os.getuid()!=1001 or os.geteuid()!=1001:
            raise IsolationError("development-identity")
        receipt = isolation.load_policy(self.receipt_path)
        if (receipt["native"]["repo"],receipt["native"]["issue"]) != self.scope:
            raise IsolationError("task-scope")
        label="label=secpal.development.scope="+self.scope_label()
        resources = []
        for kind, listing in [("network", ["network", "ls", "-q"]),
                              ("volume", ["volume", "ls", "-q"]),
                              ("container", ["ps", "-aq"])]:
            ids = self.podman(receipt, [*listing, "--filter", label], capture=True).stdout.split()
            resources.extend((kind, ident) for ident in ids)
        self.remove_resources(receipt, resources)
        for directory in Path("/home/codex").glob("secpal-test-*"):
            if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid!=1001:
                continue
            marker=directory/".scope"
            if marker.is_file() and not marker.is_symlink() and marker.read_text()==self.scope_label():
                shutil.rmtree(directory)

    def test(self, command):
        with interruptible():
            return self._test(command)

    def _test(self, command):
        receipt, root = self.authorize()
        ident="secpal-codex-test-"+secrets.token_hex(8)
        network,volume=ident+"-net",ident+"-data"
        resources = []
        directory=Path(tempfile.mkdtemp(prefix="secpal-test-",dir="/home/codex"))
        (directory/".scope").write_text(self.scope_label())
        password=secrets.token_urlsafe(36)
        secret=directory/"password";secret.write_text(password);secret.chmod(0o600)
        envfile=directory/"test.env"
        envfile.write_text("DB_CONNECTION=pgsql\nDB_HOST=fixture-db\nDB_PORT=5432\nDB_DATABASE=qualification\nDB_USERNAME=fixture\nDB_PASSWORD="+password+"\n")
        envfile.chmod(0o600)
        try:
            resources.append(("network", network))
            self.podman(receipt,["network","create","--internal","--label","secpal.development.scope="+self.scope_label(),network],capture=True)
            resources.append(("volume", volume))
            self.podman(receipt,["volume","create","--label","secpal.development.scope="+self.scope_label(),volume],capture=True)
            resources.append(("container", ident))
            self.podman(receipt,["run","-d","--name",ident,"--label","secpal.development.scope="+self.scope_label(),"--network",network,
                "--network-alias","fixture-db","--security-opt","no-new-privileges",
                "-e","POSTGRES_USER=fixture","-e","POSTGRES_DB=qualification",
                "-e","POSTGRES_PASSWORD_FILE=/run/secrets/db_password",
                "-v",str(secret)+":/run/secrets/db_password:ro,Z",
                "-v",volume+":/var/lib/postgresql",receipt["postgres_image"]],capture=True)
            import time
            for _ in range(40):
                try:
                    self.podman(receipt,["exec",ident,"pg_isready","-U","fixture","-d","qualification"],capture=True)
                    break
                except subprocess.CalledProcessError:
                    time.sleep(.25)
            else:
                raise IsolationError("test-database-not-ready")
            return self.execute(command or ["composer","test"],network=network,
                extra=("--env-file",str(envfile),"-v",str(secret)+":/run/secrets/db_password:ro,Z"))
        finally:
            # Register intent before creation: interruption can arrive after
            # Podman creates a resource but before its client reports success.
            try:
                self.remove_resources(receipt, resources)
            finally:
                shutil.rmtree(directory)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("exec","build","test","cleanup"))
    parser.add_argument("command",nargs=argparse.REMAINDER)
    args=parser.parse_args()
    if os.getuid()!=1001 or os.geteuid()!=1001:
        raise IsolationError("development-identity")
    launcher=Launcher()
    command=args.command[1:] if args.command[:1]==["--"] else args.command
    if args.operation=="cleanup":
        if command:raise IsolationError("cleanup-options-not-accepted")
        launcher.cleanup();return 0
    if args.operation=="build":
        if command:raise IsolationError("build-options-not-accepted")
        return launcher.build()
    return launcher.test(command) if args.operation=="test" else launcher.execute(command)

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (IsolationError,OSError,ValueError,KeyError,subprocess.SubprocessError):
        print("codex-workspace: admission-or-execution-failed",file=sys.stderr)
        raise SystemExit(2)
