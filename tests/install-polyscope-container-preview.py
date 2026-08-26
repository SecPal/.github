#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
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
        clone_root = home / ".polyscope/clones"
        clone_root.mkdir(parents=True)
        db_path = home / ".polyscope/polyscope.db"
        with sqlite3.connect(db_path) as connection:
            connection.execute("create table repositories (id text primary key, name text not null)")
            connection.executemany(
                "insert into repositories (id, name) values (?, ?)",
                [("api123", "SecPal/api"), ("frontend456", "SecPal/frontend")],
            )

        fake_bin = root / "bin"
        fake_bin.mkdir()
        command_log = root / "commands.log"
        write_executable(
            fake_bin / "podman",
            "#!/bin/sh\n"
            'printf "podman:%s\\n" "$*" >>"$COMMAND_LOG"\n'
            "exit 0\n",
        )
        write_executable(
            fake_bin / "systemctl",
            "#!/bin/sh\n"
            'printf "systemctl:%s\\n" "$*" >>"$COMMAND_LOG"\n'
            "exit 0\n",
        )
        write_executable(fake_bin / "getenforce", "#!/bin/sh\nprintf 'Disabled\\n'\n")

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
                    "POLYSCOPE_POSTGRES_SOCKET": str(socket_path),
                    "POLYSCOPE_CLONE_ROOT": str(clone_root),
                    "POLYSCOPE_DB_PATH": str(db_path),
                    "POLYSCOPE_PREVIEW_PORT": "18081",
                }
            )
            result = subprocess.run(
                ["bash", str(INSTALLER)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, (result.stdout, result.stderr)

        unit_dir = home / ".config/systemd/user"
        proxy_unit = unit_dir.joinpath("polyscope-postgresql-proxy.service").read_text()
        preview_unit = unit_dir.joinpath("polyscope-preview.service").read_text()
        php_wrapper = home.joinpath(".local/bin/php").read_text()
        caddyfile = home.joinpath(".config/polyscope-preview/Caddyfile").read_text()
        assert "--security-opt label=disable" in proxy_unit
        assert "--cap-drop=all" in proxy_unit
        assert " -p " not in proxy_unit
        assert "label=disable" not in preview_unit
        assert "-p 127.0.0.1:18081:18080" in preview_unit
        assert "DB_HOST=polyscope-postgresql-proxy" in php_wrapper
        assert "root * /workspaces/api123/{re.api.1}/public" in caddyfile
        assert "root * /workspaces/frontend456/{re.frontend.1}/dist" in caddyfile

        commands = command_log.read_text()
        assert "podman:image exists localhost/secpal-polyscope-api-toolchain:php84" in commands
        assert "podman:network exists polyscope-preview-db" in commands
        assert "systemctl:--user enable --now polyscope-postgresql-proxy.service" in commands
        assert "systemctl:--user enable --now polyscope-preview.service" in commands

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
