#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import pathlib
import sqlite3
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "render-polyscope-container-caddy.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_caddy", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="polyscope-caddy.") as temporary:
        root = pathlib.Path(temporary)
        db_path = root / "polyscope.db"
        with sqlite3.connect(db_path) as connection:
            connection.execute("create table repositories (id text primary key, name text not null)")
            connection.executemany(
                "insert into repositories (id, name) values (?, ?)",
                [
                    ("api123", "SecPal/api"),
                    ("frontend456", "SecPal/frontend"),
                    ("ignored789", "SecPal/deployment"),
                ],
            )

        rendered = module.render(db_path, pathlib.Path("/srv/polyscope/clones"))
        assert "^api-([a-z0-9][a-z0-9-]*)\\.preview\\.secpal\\.dev$" in rendered
        assert "root * /srv/polyscope/clones/api123/{re.api.1}/public" in rendered
        assert "php_server" in rendered
        assert "root * /srv/polyscope/clones/frontend456/{re.frontend.1}/dist" in rendered
        assert "try_files {path} /index.html" in rendered
        assert "ignored789" not in rendered

        output = root / "config" / "Caddyfile"
        module.write_atomic(output, rendered)
        assert output.read_text() == rendered
        assert (output.stat().st_mode & 0o777) == 0o600

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "insert into repositories (id, name) values (?, ?)",
                ("unsafe/id", "SecPal/GuardGuide"),
            )
        try:
            module.render(db_path, pathlib.Path("/srv/polyscope/clones"))
        except RuntimeError as error:
            assert "unsafe Polyscope repository id" in str(error)
        else:
            raise AssertionError("unsafe repository id was accepted")


if __name__ == "__main__":
    main()
