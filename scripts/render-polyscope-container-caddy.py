#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Render the host-native Caddy router for registered SecPal previews."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sqlite3
import tempfile


ROUTES = (
    ("SecPal/api", "api", "public", "php"),
    ("SecPal/GuardGuide", "guardguide", "public", "php"),
    ("SecPal/frontend", "frontend", "dist", "static"),
    ("SecPal/secpal.app", "secpal_app", "dist", "static"),
    ("SecPal/guardguide.de", "guardguide_de", "dist", "static"),
)
REPOSITORY_ID_PATTERN = re.compile(r"^[a-z0-9]+$")


def repository_ids(db_path: pathlib.Path) -> dict[str, str]:
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "select name, id from repositories where name in ({})".format(
                ",".join("?" for _route in ROUTES)
            ),
            tuple(route[0] for route in ROUTES),
        ).fetchall()
    result = {str(name): str(repository_id) for name, repository_id in rows}
    for name, repository_id in result.items():
        if REPOSITORY_ID_PATTERN.fullmatch(repository_id) is None:
            raise RuntimeError(f"unsafe Polyscope repository id for {name}: {repository_id!r}")
    return result


def render(db_path: pathlib.Path, container_root: pathlib.Path) -> str:
    identifiers = repository_ids(db_path)
    blocks: list[str] = [
        "{",
        "    admin off",
        "    auto_https off",
        "    frankenphp",
        "    order php_server before file_server",
        "}",
        "",
        ":18080 {",
    ]
    for repository_name, route_name, document_root, route_type in ROUTES:
        repository_id = identifiers.get(repository_name)
        if repository_id is None:
            continue
        host_prefix = route_name.replace("_", "-")
        capture_name = route_name
        root = container_root / repository_id / f"{{re.{capture_name}.1}}" / document_root
        blocks.extend(
            [
                f"    @{route_name} header_regexp Host ^{host_prefix}-([a-z0-9][a-z0-9-]*)\\.preview\\.secpal\\.dev$",
                f"    handle @{route_name} {{",
                f"        root * {root}",
            ]
        )
        if route_type == "php":
            blocks.append("        php_server")
        else:
            blocks.extend(["        try_files {path} /index.html", "        file_server"])
        blocks.extend(["    }", ""])
    blocks.extend(['    respond "Unknown Polyscope preview workspace" 404', "}", ""])
    return "\n".join(blocks)


def write_atomic(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True, type=pathlib.Path)
    parser.add_argument("--container-root", default=pathlib.Path("/workspaces"), type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if not args.container_root.is_absolute() or not re.fullmatch(
        r"/[A-Za-z0-9._/+-]+", str(args.container_root)
    ):
        parser.error("--container-root must be a safe absolute path")
    write_atomic(args.output, render(args.db_path, args.container_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
