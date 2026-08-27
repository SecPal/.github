#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import json
import pathlib
import socket
import sqlite3
import subprocess
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install-polyscope-container-preview.sh"


def write_executable(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="polyscope-container-installer.") as temporary:
        root = pathlib.Path(temporary)
        home = root / "home"
        repository_root = home / ".polyscope/repos/SecPal"
        clone_root = home / ".polyscope/clones"
        for repository in ("api", "frontend"):
            (repository_root / repository).mkdir(parents=True)
        (clone_root / "api-repo/calm-otter-a1b2c3d4/public").mkdir(parents=True)
        (clone_root / "frontend_repo/calm-otter-e5f6a7b8/dist").mkdir(parents=True)
        (clone_root / "api-repo/.polyscope-secpal-workspace-aliases.json").write_text(
            json.dumps({"version": 1, "aliases": {"calm-otter": "calm-otter-a1b2c3d4"}})
        )
        (clone_root / "frontend_repo/.polyscope-secpal-workspace-aliases.json").write_text(
            json.dumps({"version": 1, "aliases": {"calm-otter": "calm-otter-e5f6a7b8"}})
        )

        db_path = home / ".polyscope/polyscope.db"
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "create table repositories (id text primary key, name text not null, path text not null)"
            )
            connection.execute(
                "create table worktrees (id text primary key, repo_id text not null, path text not null, status text not null)"
            )
            connection.executemany(
                "insert into repositories (id, name, path) values (?, ?, ?)",
                [
                    ("api-repo", "SecPal/api", str(repository_root / "api")),
                    ("frontend_repo", "SecPal/frontend", str(repository_root / "frontend")),
                ],
            )
            connection.executemany(
                "insert into worktrees (id, repo_id, path, status) values (?, ?, ?, 'active')",
                [
                    (
                        "api-worktree",
                        "api-repo",
                        str(clone_root / "api-repo/calm-otter-a1b2c3d4"),
                    ),
                    (
                        "frontend-worktree",
                        "frontend_repo",
                        str(clone_root / "frontend_repo/calm-otter-e5f6a7b8"),
                    ),
                ],
            )

        fake_bin = root / "bin"
        fake_bin.mkdir()
        command_log = root / "commands.log"
        network_state = root / "network.exists"
        service_state = root / "service-state"
        service_state.mkdir()
        write_executable(
            fake_bin / "podman",
            "#!/bin/sh\n"
            'printf "podman:%s\\n" "$*" >>"$COMMAND_LOG"\n'
            'if [ "$1 $2" = "image exists" ]; then exit 0; fi\n'
            'if [ "$1 $2" = "network exists" ]; then [ -e "$NETWORK_STATE" ]; exit $?; fi\n'
            'if [ "$1 $2" = "network create" ]; then : >"$NETWORK_STATE"; exit 0; fi\n'
            'if [ "$1 $2" = "network inspect" ]; then\n'
            '  case "$*" in\n'
            '    *preview.secpal.dev/managed*) if [ "${UNMANAGED_NETWORK:-0}" = 1 ] || [ "${LEGACY_MANAGED_NETWORK:-0}" = 1 ]; then printf "false\\n"; else printf "true\\n"; fi ;;\n'
            '    *polyscope.preview*) if [ "${LEGACY_MANAGED_NETWORK:-0}" = 1 ]; then printf "true\\n"; else printf "false\\n"; fi ;;\n'
            '    *Containers*) if [ "${FOREIGN_NETWORK:-0}" = 1 ]; then printf "foreign-container\\n"; fi ;;\n'
            '  esac\n'
            '  exit 0\n'
            'fi\n'
            "exit 0\n",
        )
        write_executable(
            fake_bin / "systemctl",
            "#!/bin/sh\n"
            'printf "systemctl:%s\\n" "$*" >>"$COMMAND_LOG"\n'
            'args="$*"; unit="${args##* }"\n'
            'case "$args" in\n'
            '  "--user is-enabled --quiet "*) [ -e "$SERVICE_STATE/$unit.enabled" ]; exit $? ;;\n'
            '  "--user is-active --quiet "*) [ -e "$SERVICE_STATE/$unit.active" ]; exit $? ;;\n'
            '  "--user enable --now polyscope-preview.service")\n'
            '    if [ "${FAIL_PREVIEW_ENABLE:-0}" = 1 ]; then exit 1; fi ;;\n'
            'esac\n'
            'case "$args" in\n'
            '  "--user enable --now "*|"--user enable "*) : >"$SERVICE_STATE/$unit.enabled" ;;\n'
            '  "--user disable --now "*|"--user disable "*) rm -f "$SERVICE_STATE/$unit.enabled" ;;\n'
            'esac\n'
            'case "$args" in\n'
            '  "--user enable --now "*|"--user start "*|"--user restart "*) : >"$SERVICE_STATE/$unit.active" ;;\n'
            '  "--user disable --now "*|"--user stop "*) rm -f "$SERVICE_STATE/$unit.active" ;;\n'
            'esac\n'
            "exit 0\n",
        )
        write_executable(fake_bin / "getenforce", "#!/bin/sh\nprintf 'Disabled\\n'\n")
        write_executable(fake_bin / "date", "#!/bin/sh\nprintf '20260826T120000Z\\n'\n")
        write_executable(fake_bin / "psql", "#!/bin/sh\nexit 0\n")

        socket_path = root / "postgresql/.s.PGSQL.5432"
        socket_path.parent.mkdir()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as postgres_socket:
            postgres_socket.bind(str(socket_path))
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "XDG_CONFIG_HOME": str(home / ".config"),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "COMMAND_LOG": str(command_log),
                    "NETWORK_STATE": str(network_state),
                    "SERVICE_STATE": str(service_state),
                    "POLYSCOPE_POSTGRES_SOCKET": str(socket_path),
                    "POLYSCOPE_CLONE_ROOT": str(clone_root),
                    "POLYSCOPE_REPOSITORY_ROOT": str(repository_root),
                    "POLYSCOPE_DB_PATH": str(db_path),
                    "POLYSCOPE_LIBEXEC_DIR": str(home / "custom-libexec"),
                    "POLYSCOPE_PREVIEW_PORT": "18081",
                }
            )
            for _attempt in range(2):
                result = subprocess.run(
                    ["bash", str(INSTALLER)],
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                assert result.returncode == 0, (result.stdout, result.stderr)

            foreign_env = env | {"FOREIGN_NETWORK": "1"}
            rejected_foreign = subprocess.run(
                ["bash", str(INSTALLER)],
                env=foreign_env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert rejected_foreign.returncode != 0
            assert "foreign container" in rejected_foreign.stderr

            unmanaged_env = env | {"UNMANAGED_NETWORK": "1"}
            rejected_unmanaged = subprocess.run(
                ["bash", str(INSTALLER)],
                env=unmanaged_env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert rejected_unmanaged.returncode != 0
            assert "unmanaged pre-existing Podman network" in rejected_unmanaged.stderr

            legacy_env = env | {"LEGACY_MANAGED_NETWORK": "1"}
            accepted_legacy = subprocess.run(
                ["bash", str(INSTALLER)],
                env=legacy_env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert accepted_legacy.returncode == 0, (
                accepted_legacy.stdout,
                accepted_legacy.stderr,
            )

        unit_dir = home / ".config/systemd/user"
        proxy_unit = unit_dir.joinpath("polyscope-postgresql-proxy.service").read_text()
        preview_unit = unit_dir.joinpath("polyscope-preview.service").read_text()
        refresh_unit = unit_dir.joinpath("polyscope-preview-refresh.service").read_text()
        refresh_path = unit_dir.joinpath("polyscope-preview-refresh.path").read_text()
        php_wrapper = home.joinpath(".local/bin/php").read_text()
        caddyfile = home.joinpath(".config/polyscope-preview/Caddyfile").read_text()
        assert "--security-opt label=disable" in proxy_unit
        assert "--cap-drop=all" in proxy_unit
        assert " -p " not in proxy_unit
        assert str(home / "custom-libexec/polyscope-postgresql-socket-proxy.py") in proxy_unit
        assert "label=disable" not in preview_unit
        assert "run-polyscope-container-preview.py" in preview_unit
        assert "--preview-port 18081" in preview_unit
        assert "podman run" not in preview_unit
        assert home.joinpath("custom-libexec/run-polyscope-container-preview.py").is_file()
        assert "DB_HOST=polyscope-postgresql-proxy" in php_wrapper
        assert "KEK_PATH=/app/storage/app/keys/kek.key" in php_wrapper
        assert '-v "$PWD":/app:rw' in php_wrapper
        assert f"-v '{clone_root}':'{clone_root}':ro" in php_wrapper
        assert "api-calm-otter.preview.secpal.dev" in caddyfile
        assert "frontend-calm-otter.preview.secpal.dev" in caddyfile
        assert "calm-otter-a1b2c3d4.preview.secpal.dev" not in caddyfile
        assert "root * /workspaces/api-repo/calm-otter-a1b2c3d4/public" in caddyfile
        assert "root * /workspaces/frontend_repo/calm-otter-e5f6a7b8/dist" in caddyfile
        assert f"PathChanged={db_path}" in refresh_path
        assert f"PathChanged={db_path}-wal" in refresh_path
        assert "polyscope-preview-refresh.service" in refresh_path
        assert "refresh-polyscope-container-preview.sh" in refresh_unit
        assert "cleanup-polyscope-container-preview.py" in refresh_unit
        assert f"Environment=PATH={fake_bin}:/usr/bin" in refresh_unit
        assert "StartLimitIntervalSec=0" in refresh_unit
        assert "ExecStartPre=/usr/bin/sleep 2" in refresh_unit
        assert home.joinpath("custom-libexec/cleanup-polyscope-container-preview.py").is_file()
        assert "Restart=" not in refresh_unit
        backups = list((home / ".local/state/polyscope/backups").iterdir())
        assert len(backups) == 3, backups

        for state_path in service_state.iterdir():
            state_path.unlink()
        rollback_env = env | {"FAIL_PREVIEW_ENABLE": "1"}
        rolled_back = subprocess.run(
            ["bash", str(INSTALLER)],
            env=rollback_env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rolled_back.returncode != 0
        assert "previous managed files were restored" in rolled_back.stderr
        assert list(service_state.iterdir()) == []

        commands = command_log.read_text()
        assert "podman:image exists localhost/secpal-polyscope-api-toolchain:php84" in commands
        assert "podman:network create --label preview.secpal.dev/managed=true polyscope-preview-db" in commands
        assert "systemctl:--user enable --now polyscope-postgresql-proxy.service" in commands
        assert "systemctl:--user enable --now polyscope-preview.service" in commands
        assert "systemctl:--user restart polyscope-postgresql-proxy.service" in commands
        assert "systemctl:--user restart polyscope-preview.service" in commands
        assert "systemctl:--user enable --now polyscope-preview-refresh.path" in commands
        assert (
            "systemctl:--user reset-failed polyscope-preview-refresh.path "
            "polyscope-preview-refresh.service"
        ) in commands

        rejected = subprocess.run(
            ["bash", str(INSTALLER), "--image", "bad'image"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected.returncode != 0
        assert "image reference contains unsupported characters" in rejected.stderr


if __name__ == "__main__":
    main()
