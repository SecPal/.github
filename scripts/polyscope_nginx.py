#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Strict manifest contract shared by rollout and the privileged nginx helper."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import stat
import tempfile
from typing import Any


MAX_MANIFEST_BYTES = 32 * 1024
EXPECTED_PREVIEW_DOMAIN = "preview.secpal.dev"
EXPECTED_CLONE_ROOT = "/home/secpal/.polyscope/clones"
EXPECTED_REPOSITORIES = (
    "api",
    "frontend",
    "GuardGuide",
    "secpal.app",
    "guardguide.de",
    "changelog",
)
EXPECTED_UNIX_UPSTREAM = "/run/php/php8.4-fpm-secpal-preview.sock"
TOP_LEVEL_KEYS = {
    "version",
    "preview_domain",
    "clone_root",
    "repositories",
    "php_upstream",
    "nginx_http2_syntax",
}
REPOSITORY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _require_exact_keys(payload: dict[str, Any], expected: set[str], description: str) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError(f"{description} has invalid fields: {'; '.join(details)}")


def validate_manifest_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("nginx manifest must be a JSON object")
    _require_exact_keys(payload, TOP_LEVEL_KEYS, "nginx manifest")

    if payload["version"] != 1:
        raise ValueError("nginx manifest version must be 1")
    if payload["preview_domain"] != EXPECTED_PREVIEW_DOMAIN:
        raise ValueError(f"preview_domain must be exactly {EXPECTED_PREVIEW_DOMAIN}")
    if payload["clone_root"] != EXPECTED_CLONE_ROOT:
        raise ValueError(f"clone_root must be exactly {EXPECTED_CLONE_ROOT}")
    if payload["nginx_http2_syntax"] not in {"modern", "legacy"}:
        raise ValueError("nginx_http2_syntax must be modern or legacy")

    repositories = payload["repositories"]
    if not isinstance(repositories, dict):
        raise ValueError("repositories must be a JSON object")
    _require_exact_keys(repositories, set(EXPECTED_REPOSITORIES), "repositories")
    for repo_name, repo_id in repositories.items():
        if not isinstance(repo_id, str) or REPOSITORY_ID_PATTERN.fullmatch(repo_id) is None:
            raise ValueError(f"repository id for {repo_name} is unsafe")

    upstream = payload["php_upstream"]
    if not isinstance(upstream, dict):
        raise ValueError("php_upstream must be a JSON object")
    kind = upstream.get("kind")
    if kind == "unix":
        _require_exact_keys(upstream, {"kind", "path"}, "unix php_upstream")
        if upstream["path"] != EXPECTED_UNIX_UPSTREAM:
            raise ValueError(f"unix php_upstream path must be exactly {EXPECTED_UNIX_UPSTREAM}")
    elif kind == "tcp":
        _require_exact_keys(upstream, {"kind", "host", "port"}, "tcp php_upstream")
        if upstream["host"] not in {"127.0.0.1", "::1"}:
            raise ValueError("tcp php_upstream host must be loopback")
        port = upstream["port"]
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("tcp php_upstream port must be an integer from 1 through 65535")
    else:
        raise ValueError("php_upstream kind must be unix or tcp")

    return payload


def load_manifest(path: pathlib.Path, *, expected_uid: int) -> dict[str, Any]:
    open_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        open_flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, open_flags)
    except OSError as error:
        if path.is_symlink():
            raise ValueError(f"nginx manifest must not be a symbolic link: {path}") from error
        raise ValueError(f"unable to open nginx manifest safely {path}: {error}") from error

    try:
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"nginx manifest must be a regular file: {path}")
            if metadata.st_uid != expected_uid:
                raise ValueError(
                    f"nginx manifest owner {metadata.st_uid} does not match expected owner {expected_uid}: {path}"
                )
            if stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ValueError(f"nginx manifest mode must be exactly 0600: {path}")
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
        if not raw or len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError(
                f"nginx manifest size must be between 1 and {MAX_MANIFEST_BYTES} bytes: {path}"
            )
        text = raw.decode("utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"nginx manifest must be readable UTF-8 JSON: {path}: {error}") from error
    return validate_manifest_data(payload)


def build_manifest(
    repo_state: dict[str, dict[str, Any]],
    *,
    nginx_http2_syntax: str,
) -> dict[str, Any]:
    payload = {
        "version": 1,
        "preview_domain": EXPECTED_PREVIEW_DOMAIN,
        "clone_root": EXPECTED_CLONE_ROOT,
        "repositories": {
            repo_name: str(repo_state[repo_name]["id"])
            for repo_name in EXPECTED_REPOSITORIES
        },
        "php_upstream": {
            "kind": "unix",
            "path": EXPECTED_UNIX_UPSTREAM,
        },
        "nginx_http2_syntax": nginx_http2_syntax,
    }
    return validate_manifest_data(payload)


def write_manifest_atomic(path: pathlib.Path, payload: dict[str, Any]) -> None:
    validated = validate_manifest_data(payload)
    content = json.dumps(validated, indent=2, sort_keys=True) + "\n"
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError(f"rendered nginx manifest exceeds {MAX_MANIFEST_BYTES} bytes")

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symbolic-link nginx manifest: {path}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary_path = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _load_rollout_renderer() -> Any:
    renderer_path = pathlib.Path(__file__).with_name("polyscope-rollout.py")
    if not renderer_path.is_file():
        raise RuntimeError(f"root-owned nginx renderer is missing: {renderer_path}")
    module_spec = importlib.util.spec_from_file_location("polyscope_nginx_renderer", renderer_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"unable to load root-owned nginx renderer: {renderer_path}")
    renderer = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(renderer)
    return renderer


def render_nginx_config(payload: dict[str, Any]) -> str:
    manifest = validate_manifest_data(payload)
    repo_state = {
        repo_name: {"id": repo_id}
        for repo_name, repo_id in manifest["repositories"].items()
    }
    renderer = _load_rollout_renderer()
    rendered = renderer.render_nginx_config(
        repo_state,
        nginx_http2_syntax=manifest["nginx_http2_syntax"],
    )

    upstream = manifest["php_upstream"]
    if upstream["kind"] == "unix":
        desired_upstream = f"unix:{upstream['path']}"
    else:
        host = f"[{upstream['host']}]" if upstream["host"] == "::1" else upstream["host"]
        desired_upstream = f"{host}:{upstream['port']}"
    rendered = rendered.replace(
        f"unix:{EXPECTED_UNIX_UPSTREAM}",
        desired_upstream,
    )
    return rendered
