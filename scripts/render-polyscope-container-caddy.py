#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Render fail-closed Caddy routes for active registered SecPal previews."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sqlite3
import tempfile


ROUTES = (
    ("SecPal/api", "api", "api", "public", "php"),
    ("SecPal/guardguide.de", "guardguide.de", "guardguide-de", "dist", "static"),
    ("SecPal/GuardGuide", "GuardGuide", "guardguide", "public", "php"),
    ("SecPal/frontend", "frontend", "frontend", "dist", "static"),
    ("SecPal/secpal.app", "secpal.app", "secpal-app", "dist", "static"),
)
REPOSITORY_ID_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?$")
WORKSPACE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
WORKSPACE_ALIAS_REGISTRY = ".polyscope-secpal-workspace-aliases.json"


def _resolved(path: pathlib.Path) -> pathlib.Path:
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"required Polyscope path is unavailable: {path}") from error


def repository_ids(
    db_path: pathlib.Path, repository_root: pathlib.Path
) -> dict[str, str]:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "select name, id, path from repositories where name in ({})".format(
                ",".join("?" for _route in ROUTES)
            ),
            tuple(route[0] for route in ROUTES),
        ).fetchall()

    result: dict[str, str] = {}
    for name, repository_directory, _host_prefix, _document_root, _route_type in ROUTES:
        named_rows = [row for row in rows if str(row[0]) == name]
        if not named_rows:
            continue
        expected_path = _resolved(repository_root / repository_directory)
        canonical_rows = [
            (str(repository_id), pathlib.Path(str(source_path)))
            for _row_name, repository_id, source_path in named_rows
            if pathlib.Path(str(source_path)).is_absolute()
            and _resolved(pathlib.Path(str(source_path))) == expected_path
        ]
        if len(canonical_rows) != 1:
            raise RuntimeError(
                f"expected exactly one canonical Polyscope repository for {name}, "
                f"found {len(canonical_rows)}"
            )
        repository_id = canonical_rows[0][0]
        if REPOSITORY_ID_PATTERN.fullmatch(repository_id) is None:
            raise RuntimeError(f"unsafe Polyscope repository id for {name}: {repository_id!r}")
        result[name] = repository_id
    return result


def active_workspaces(
    db_path: pathlib.Path,
    repository_id: str,
    clone_root: pathlib.Path,
    document_root: str,
) -> list[tuple[str, str]]:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "select path from worktrees where repo_id = ? and status = 'active' order by path",
            (repository_id,),
        ).fetchall()

    if not rows:
        return []
    repository_clone_root = _resolved(clone_root / repository_id)
    registry_path = clone_root / repository_id / WORKSPACE_ALIAS_REGISTRY
    if registry_path.is_symlink() or not registry_path.is_file():
        raise RuntimeError(f"required Polyscope workspace alias registry is unavailable: {registry_path}")
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid Polyscope workspace alias registry: {registry_path}") from error
    if not isinstance(registry, dict) or registry.get("version") != 1:
        raise RuntimeError(f"unsupported Polyscope workspace alias registry: {registry_path}")
    aliases = registry.get("aliases")
    if not isinstance(aliases, dict):
        raise RuntimeError(f"invalid Polyscope workspace aliases: {registry_path}")
    for logical_name, physical_name in aliases.items():
        if (
            not isinstance(logical_name, str)
            or WORKSPACE_PATTERN.fullmatch(logical_name) is None
            or not isinstance(physical_name, str)
            or WORKSPACE_PATTERN.fullmatch(physical_name) is None
        ):
            raise RuntimeError(f"unsafe Polyscope workspace alias in {registry_path}")

    workspaces: list[tuple[str, str]] = []
    for (raw_path,) in rows:
        registered_path = pathlib.Path(str(raw_path))
        if not registered_path.is_absolute() or registered_path.parent != clone_root / repository_id:
            raise RuntimeError(
                f"active worktree is outside its registered clone root: {registered_path}"
            )
        physical_workspace = registered_path.name
        if WORKSPACE_PATTERN.fullmatch(physical_workspace) is None:
            raise RuntimeError(
                f"unsafe active Polyscope workspace name: {physical_workspace!r}"
            )
        physical_worktree = _resolved(registered_path)
        if physical_worktree.parent != repository_clone_root:
            raise RuntimeError(f"active worktree escapes its clone root: {registered_path}")
        host_document_root = physical_worktree / document_root
        if not host_document_root.is_dir():
            raise RuntimeError(f"active preview document root is unavailable: {host_document_root}")
        for candidate in host_document_root.rglob("*"):
            if candidate.is_symlink():
                raise RuntimeError(
                    f"active preview document root contains a symbolic link: {candidate}"
                )
        logical_aliases = [
            logical_name
            for logical_name, physical_name in aliases.items()
            if physical_name == physical_workspace
        ]
        if len(logical_aliases) != 1:
            raise RuntimeError(
                "expected exactly one canonical Polyscope workspace alias for "
                f"{repository_id}/{physical_workspace}, found {len(logical_aliases)}"
            )
        logical_workspace = logical_aliases[0]
        if any(existing_logical == logical_workspace for existing_logical, _ in workspaces):
            raise RuntimeError(
                "duplicate active Polyscope workspace alias for repository "
                f"{repository_id}: {logical_workspace}"
            )
        workspaces.append((logical_workspace, physical_workspace))
    return workspaces


def render(
    db_path: pathlib.Path,
    container_root: pathlib.Path,
    clone_root: pathlib.Path,
    repository_root: pathlib.Path,
) -> str:
    identifiers = repository_ids(db_path, repository_root)
    blocks: list[str] = [
        "{",
        "    admin off",
        "    auto_https off",
        "    frankenphp",
        "}",
        "",
        ":18080 {",
    ]
    route_index = 0
    for repository_name, _repository_directory, host_prefix, document_root, route_type in ROUTES:
        repository_id = identifiers.get(repository_name)
        if repository_id is None:
            continue
        for workspace, physical_workspace in active_workspaces(
            db_path, repository_id, clone_root, document_root
        ):
            route_index += 1
            matcher = f"preview_{route_index}"
            root = container_root / repository_id / physical_workspace / document_root
            blocks.extend(
                [
                    f"    @{matcher} host {host_prefix}-{workspace}.preview.secpal.dev",
                    f"    handle @{matcher} {{",
                    f"        root * {root}",
                ]
            )
            if route_type == "php":
                non_front_controller = f"non_front_controller_php_{route_index}"
                static_file = f"static_file_{route_index}"
                blocks.extend(
                    [
                        "        route {",
                        f"            @{non_front_controller} {{",
                        "                path *.php",
                        "                not path /index.php",
                        "            }",
                        f'            respond @{non_front_controller} "Not found" 404',
                        f"            @{static_file} {{",
                        "                file {path}",
                        "                not path *.php",
                        "            }",
                        f"            file_server @{static_file}",
                        "            rewrite * /index.php",
                        "            php",
                        "        }",
                    ]
                )
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
    parser.add_argument("--clone-root", required=True, type=pathlib.Path)
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    for option, path in (
        ("--container-root", args.container_root),
        ("--clone-root", args.clone_root),
        ("--repository-root", args.repository_root),
    ):
        if not path.is_absolute() or re.fullmatch(r"/[A-Za-z0-9._/ +#-]+", str(path)) is None:
            parser.error(f"{option} must be a safe absolute path")
    write_atomic(
        args.output,
        render(args.db_path, args.container_root, args.clone_root, args.repository_root),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
