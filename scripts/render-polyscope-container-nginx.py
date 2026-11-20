#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Render fail-closed Nginx routes for active registered SecPal previews."""

from __future__ import annotations

import argparse
import importlib.util
import functools
import json
import os
import pathlib
import re
import sqlite3
import stat
import tempfile
from typing import NamedTuple


@functools.lru_cache(maxsize=1)
def isolation_module():
    path = pathlib.Path(__file__).with_name("polyscope-isolation.py")
    if not path.is_file():
        path = pathlib.Path("/usr/local/libexec/secpal/polyscope-isolation.py")
    if (not path.is_file()
            and not os.environ.get("SECPAL_WORKSPACE_ISOLATION_POLICY")
            and not pathlib.Path("/etc/secpal/workspace-isolation.json").exists()
            and not pathlib.Path("/etc/secpal/workspace-isolation.required").exists()):
        from types import SimpleNamespace
        return SimpleNamespace(from_environment=lambda: None)
    spec = importlib.util.spec_from_file_location("_secpal_isolation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ROUTES = (
    ("SecPal/api", "api", "api", "public", "php"),
    ("SecPal/frontend", "frontend", "frontend", "dist", "static"),
    ("SecPal/secpal.app", "secpal.app", "secpal-app", "dist", "static"),
)
REPOSITORY_ID_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?$")
WORKSPACE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
PHYSICAL_SUFFIX_PATTERN = re.compile(r"^.+-[0-9a-f]{8}$")
API_PREVIEW_ADMISSION_FILENAME = ".polyscope-secpal-container-ready"
WORKSPACE_ALIAS_REGISTRY = ".polyscope-secpal-workspace-aliases.json"



def api_preview_is_admitted(worktree: pathlib.Path) -> bool:
    token = worktree / "public" / API_PREVIEW_ADMISSION_FILENAME
    return not token.is_symlink() and token.is_file()


def has_provisioned_physical_name(worktree: pathlib.Path) -> bool:
    """Rollout deliberately creates no self-alias for a colliding canonical name."""
    marker = worktree / ".polyscope-secpal-provisioned.json"
    try:
        with open(
            marker, encoding="utf-8",
            opener=lambda path, flags: os.open(
                path, flags | os.O_NOFOLLOW | os.O_NONBLOCK
            ),
        ) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return False
            data = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("workspace") == worktree.name


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
    *,
    require_runtime_admission: bool = False,
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
    aliases: dict[str, str] = {}
    if registry_path.is_symlink():
        raise RuntimeError(f"invalid Polyscope workspace alias registry: {registry_path}")
    if registry_path.exists():
        if not registry_path.is_file():
            raise RuntimeError(f"invalid Polyscope workspace alias registry: {registry_path}")
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

    gate = isolation_module().from_environment()
    observed = None
    if gate:
        with gate.observation() as (records, pending):
            observed = records, pending
    workspaces: list[tuple[str, str]] = []
    for (raw_path,) in rows:
        if observed:
            records, pending = observed
            try:
                blocked = isolation_module().classify(gate.policy, records, str(raw_path), pending=pending)
            except isolation_module().IsolationError:
                blocked = True
            if blocked:
                continue
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
        if require_runtime_admission and not api_preview_is_admitted(physical_worktree):
            continue
        host_document_root = physical_worktree / document_root
        if host_document_root.is_symlink() or not host_document_root.is_dir():
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
        if not logical_aliases and (
            PHYSICAL_SUFFIX_PATTERN.fullmatch(physical_workspace) is None
            or has_provisioned_physical_name(physical_worktree)
        ):
            logical_aliases = [physical_workspace]
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


class PreviewRoute(NamedTuple):
    host: str
    redirect_host: str | None
    worktree: pathlib.Path
    document_root: str
    php: bool


def preview_routes(db_path, clone_root, repository_root) -> list[PreviewRoute]:
    identifiers = repository_ids(db_path, repository_root)
    routes = []
    for repository, _directory, prefix, document_root, route_type in ROUTES:
        repository_id = identifiers.get(repository)
        if repository_id is None:
            continue
        php = route_type == "php"
        workspaces = active_workspaces(
            db_path, repository_id, clone_root, document_root, require_runtime_admission=php,
        )
        canonical_names = {workspace for workspace, _ in workspaces}
        for workspace, physical in workspaces:
            if physical != workspace and physical in canonical_names:
                raise RuntimeError(
                    "physical preview hostname conflicts with a canonical workspace: "
                    f"{repository_id}/{physical}"
                )
            host = f"{prefix}-{workspace}.preview.secpal.dev"
            redirect = f"{prefix}-{physical}.preview.secpal.dev" if physical != workspace else None
            routes.append(PreviewRoute(
                host, redirect, clone_root / repository_id / physical, document_root, php,
            ))
    return routes


def render_routes(routes: list[PreviewRoute], container_root: pathlib.Path) -> str:
    blocks = [
        "pid /tmp/nginx.pid;",
        "error_log /dev/null;",
        "events {}",
        "http {",
        "    include /etc/nginx/mime.types;",
        "    server_names_hash_bucket_size 128;",
        "    access_log off;",
        "    client_body_temp_path /tmp/client-body;",
        "    proxy_temp_path /tmp/proxy;",
        "    fastcgi_temp_path /tmp/fastcgi;",
        "    uwsgi_temp_path /tmp/uwsgi;",
        "    scgi_temp_path /tmp/scgi;",
        "    client_max_body_size 12m;",
        "    server {",
        "        listen 18080 default_server;",
        "        server_name _;",
        "        return 404;",
        "    }",
    ]
    for index, route in enumerate(routes, start=1):
        public_root = container_root / str(index)
        # Podman bind mounts hold directories by identity. Trigger refresh when
        # a build or workspace recreation replaces a directory at the same path.
        mount_paths = [route.worktree / route.document_root]
        if route.php:
            mount_paths.extend([route.worktree, route.worktree / "storage"])
        identities = [path.stat(follow_symlinks=False) for path in mount_paths]
        mounts = " ".join(f"{item.st_dev}:{item.st_ino}" for item in identities)
        blocks.append(f"    # Preview mounts: {mounts}")
        if route.redirect_host:
            blocks.extend([
                "    server {",
                "        listen 18080;",
                f"        server_name {route.redirect_host};",
                f"        return 308 https://{route.host}$request_uri;",
                "    }",
            ])
        blocks.extend([
            "    server {",
            "        listen 18080;",
            f"        server_name {route.host};",
            f"        root {public_root};",
            "        disable_symlinks on from=$document_root;",
            r"        location ~ /\. { return 404; }",
            r"        location ~* \.php(?:/|$) { return 404; }",
        ])
        if route.php:
            blocks.extend([
                f"        if (!-f {public_root / API_PREVIEW_ADMISSION_FILENAME}) {{ return 503; }}",
                "        location / { try_files $uri /index.php?$query_string; }",
                "        location = /index.php {",
                "            root /app/public;",
                "            include /etc/nginx/fastcgi_params;",
                "            fastcgi_param SCRIPT_FILENAME /app/public/index.php;",
                "            fastcgi_param HTTP_HOST $host;",
                "            fastcgi_param HTTP_AUTHORIZATION $http_authorization;",
                "            fastcgi_param HTTP_COOKIE $http_cookie;",
                '            fastcgi_param HTTP_PROXY "";',
                "            fastcgi_buffering off;",
                f"            fastcgi_pass unix:/run/preview-sockets/{index}/api.sock;",
                "        }",
            ])
        else:
            blocks.append("        location / { try_files $uri $uri/ /index.html =404; }")
        blocks.append("    }")
    blocks.extend(["}", ""])
    return "\n".join(blocks)


def render(db_path, container_root, clone_root, repository_root) -> str:
    return render_routes(preview_routes(db_path, clone_root, repository_root), container_root)


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
        if not path.is_absolute() or re.fullmatch(r"/[A-Za-z0-9._/+-]+", str(path)) is None:
            parser.error(f"{option} must be a safe absolute path")
    write_atomic(
        args.output,
        render(args.db_path, args.container_root, args.clone_root, args.repository_root),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
