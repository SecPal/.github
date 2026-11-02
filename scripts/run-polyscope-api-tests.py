#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Run API tests against one disposable, private PostgreSQL instance."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import pathlib
import secrets
import signal
import subprocess
import sys
import tempfile
import time

POSTGRES_IMAGE = "docker.io/library/postgres:18-bookworm@sha256:1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af"


def podman(arguments: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["podman", *arguments], check=True, text=True, **kwargs)


def run_tests(image: str, arguments: list[str]) -> int:
    if "--full" in arguments and arguments != ["--full"]:
        raise RuntimeError("--full runs the existing Composer test script without additional arguments.")
    workspace = pathlib.Path.cwd().resolve()
    if not all((workspace / name).is_file() for name in ("artisan", "phpunit.xml", "composer.lock")):
        raise RuntimeError("Run from an installed SecPal API worktree.")
    if os.geteuid() == 0:
        raise RuntimeError("Run as the unprivileged development account.")
    os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if podman(["info", "--format", "{{.Host.Security.Rootless}}"], capture_output=True).stdout.strip() != "true":
        raise RuntimeError("Rootless Podman is required.")
    common = pathlib.Path(subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True
    ).strip())
    token = secrets.token_hex(8)
    name = "polyscope-test-" + hashlib.sha256(str(workspace).encode()).hexdigest()[:12] + "-" + token
    resources: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="polyscope-api-test-") as directory:
        private = pathlib.Path(directory)
        database_password = secrets.token_hex(32)
        app_password = secrets.token_hex(32)
        database_env = private / "postgres.env"
        database_env.write_text(f"POSTGRES_PASSWORD={database_password}\n")
        database_env.chmod(0o600)
        app_env = private / "test.env"
        app_env.write_text(
            "APP_ENV=testing\nDB_CONNECTION=pgsql\nDB_HOST=database\nDB_PORT=5432\n"
            "DB_DATABASE=testing\nSECPAL_TEST_DATABASE=testing\nDB_USERNAME=testing\n"
            f"DB_PASSWORD={app_password}\nDB_URL=\nDATABASE_URL=\n"
            f"APP_KEY=base64:{base64.b64encode(secrets.token_bytes(32)).decode()}\n"
            "KEK_PATH=/tmp/secpal-tests/kek.key\n"
        )
        app_env.chmod(0o600)
        try:
            network = podman([
                "network", "create", "--internal", "--label", f"test.secpal.dev/workspace={workspace}", name
            ], capture_output=True).stdout.strip()
            resources.append(("network", network))
            database = podman([
                "create", "--name", name + "-db", "--network", network, "--network-alias", "database",
                "--user", "postgres", "--security-opt", "no-new-privileges", "--cap-drop=all",
                "--env-file", str(database_env), POSTGRES_IMAGE,
            ], capture_output=True).stdout.strip()
            resources.append(("container", database))
            podman(["start", database], stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 90
            while True:
                ready = subprocess.run([
                    "podman", "exec", database, "pg_isready", "-q", "-h", "127.0.0.1",
                    "-U", "postgres", "-d", "postgres",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if ready.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("Isolated PostgreSQL readiness timed out; no preview fallback.")
                time.sleep(0.5)
            podman([
                "exec", "--interactive", database, "psql", "--no-psqlrc", "--username", "postgres",
                "--dbname", "postgres", "--set", "ON_ERROR_STOP=1",
            ], input=(
                f"CREATE ROLE testing LOGIN CREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION PASSWORD '{app_password}';\n"
                "CREATE DATABASE testing OWNER testing;\n"
            ), stdout=subprocess.DEVNULL, timeout=15)
            command = ["composer", "test"] if arguments == ["--full"] else ["php", "artisan", "test", *arguments]
            application = podman([
                "create", "--interactive", "--userns=keep-id:uid=1000,gid=1000", "--no-healthcheck", "--name", name + "-php", "--network", network,
                "--security-opt", "no-new-privileges", "--cap-drop=all",
                "--env-file", str(app_env), "--volume", f"{workspace}:/app:rw,z",
                "--volume", f"{common}:{common}:ro,z", "--workdir", "/app",
                "--entrypoint", "/bin/sh", image, "-ec",
                ('umask 077; mkdir -p /tmp/secpal-tests; '
                 + 'php -r \'file_put_contents(getenv("KEK_PATH"), sodium_crypto_secretbox_keygen());\'; '
                 + 'exec "$@"'), "test", *command,
            ], capture_output=True).stdout.strip()
            resources.append(("container", application))
            result = subprocess.run(["podman", "start", "--attach", "--interactive", application])
            return result.returncode
        finally:
            failed = []
            for kind, identity in reversed(resources):
                command = (["network", "rm", identity] if kind == "network"
                           else ["rm", "--force", "--volumes", identity])
                try:
                    result = subprocess.run(["podman", *command], capture_output=True, text=True, timeout=30)
                    if result.returncode:
                        failed.append(f"{kind} {identity}")
                except subprocess.TimeoutExpired:
                    failed.append(f"{kind} {identity}")
            if failed:
                raise RuntimeError("Unable to clean isolated test resources: " + ", ".join(failed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        return run_tests(args.image, arguments)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Isolated API tests failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
