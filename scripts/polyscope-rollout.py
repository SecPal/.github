#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


POLYSCOPE_LOCAL_CONFIG_NAME = "polyscope.local.json"
PROVISION_MARKER_FILENAME = ".polyscope-secpal-provisioned.json"
ROLLOUT_SCRIPT_PATH = pathlib.Path(__file__).resolve()
DEFAULT_ANDROID_SDK_ROOT = pathlib.Path.home() / "Android" / "Sdk"
PREVIEW_DATABASE_BASE_ENV_KEY = "POLYSCOPE_BASE_DB_DATABASE"
PREVIEW_DB_PASSWORD_SOURCE_ENV_KEY = "POLYSCOPE_DB_PASSWORD_SOURCE"
PREVIEW_DB_PASSWORD_SOURCE_SHA256_ENV_KEY = "POLYSCOPE_DB_PASSWORD_SOURCE_SHA256"
PREVIEW_DB_PASSWORD_SOURCE_VALUE = "source"
PREVIEW_SCHEMA_ENV_KEY = "POLYSCOPE_PREVIEW_SCHEMA"
PREVIEW_STORAGE_MODE_ENV_KEY = "POLYSCOPE_PREVIEW_STORAGE_MODE"
POSTGRES_PREVIEW_DATABASE_SEPARATOR = "__preview__"
POSTGRES_IDENTIFIER_MAX_LENGTH = 63
ENV_ASSIGNMENT_PATTERN = re.compile(r"^([A-Z0-9_]+)=(.*)$")
SENSITIVE_ENV_KEY_PATTERN = re.compile(r"(?:^|_)(?:APP_KEY|KEY|SECRET|TOKEN|PASSWORD|PASS|KEK|CREDENTIAL|PRIVATE)(?:$|_)")
SOURCE_ENV_BASE_VALUE_KEYS = {
    "APP_ENV",
    "APP_DEBUG",
    "LOG_CHANNEL",
    "LOG_LEVEL",
    "DB_CONNECTION",
    "DB_HOST",
    "DB_PORT",
    "DB_DATABASE",
    "DB_USERNAME",
    "DB_PASSWORD",
}
NO_AI_ATTRIBUTION_RULE = (
    "Do not add AI agent attribution, AI self-references, generated-by text, "
    "tool-specific labels or prefixes, promotional AI wording, or AI `Co-authored-by` "
    "trailers to commits, branches, pull request titles or bodies, issues, comments, "
    "documentation, code comments, UI copy, release notes, or any other project content."
)
MODERN_NGINX_HTTP2_VERSION = (1, 25, 1)
NGINX_HTTP2_SYNTAX_CHOICES = ("modern", "legacy", "auto")
API_BOOTSTRAP_SETUP_COMMAND_PLACEHOLDER = "__POLYSCOPE_API_BOOTSTRAP_SETUP__"
API_REFRESH_COMMAND_PLACEHOLDER = "__POLYSCOPE_API_REFRESH__"
API_QUEUE_WORKER_COMMAND = (
    "php artisan queue:work --queue=activity-hash-chain,merkle,opentimestamp,default "
    "--sleep=3 --tries=3"
)
API_SCHEDULER_COMMAND = "php artisan schedule:work"
API_PAIL_COMMAND = "php artisan pail --timeout=0"
API_RUNTIME_PREVIEW_COMMANDS = frozenset(
    {
        API_QUEUE_WORKER_COMMAND,
        API_SCHEDULER_COMMAND,
        API_PAIL_COMMAND,
    }
)


def default_polyscope_db_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("POLYSCOPE_DB_PATH", pathlib.Path.home() / ".polyscope" / "polyscope.db"))


def resolve_path_for_matching(path: pathlib.Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def normalize_workspace_name(value: str, fallback: str = "workspace") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-+", "-", normalized)
    return normalized or fallback


def strip_legacy_workspace_suffix(value: str) -> str:
    return re.sub(r"-[0-9a-f]{8}$", "", value)


def build_colliding_workspace_name(worktree_name: str, workspace: str) -> str:
    digest = hashlib.sha1(worktree_name.encode("utf-8")).hexdigest()[:8]
    return f"{workspace}-{digest}"


def workspace_slug_has_collision(worktree_path: pathlib.Path, workspace: str) -> bool:
    try:
        sibling_paths = tuple(worktree_path.parent.iterdir())
    except OSError:
        return False

    current_path = resolve_path_for_matching(worktree_path)
    for sibling_path in sibling_paths:
        if sibling_path == worktree_path:
            continue

        sibling_workspace = normalize_workspace_name(strip_legacy_workspace_suffix(sibling_path.name))
        if sibling_workspace != workspace:
            continue

        if resolve_path_for_matching(sibling_path) == current_path:
            continue

        return True

    return False


def resolve_workspace_name_from_path(worktree_path: pathlib.Path) -> str:
    normalized_name = normalize_workspace_name(worktree_path.name)
    legacy_name = normalize_workspace_name(strip_legacy_workspace_suffix(worktree_path.name))
    collision_path = worktree_path
    collision_name = worktree_path.name
    if legacy_name == normalized_name:
        try:
            resolved_path = worktree_path.resolve()
        except OSError:
            if workspace_slug_has_collision(worktree_path, normalized_name):
                return build_colliding_workspace_name(worktree_path.name, normalized_name)
            return normalized_name
        resolved_normalized_name = normalize_workspace_name(resolved_path.name)
        resolved_legacy_name = normalize_workspace_name(strip_legacy_workspace_suffix(resolved_path.name))
        if resolved_legacy_name == resolved_normalized_name:
            if workspace_slug_has_collision(resolved_path, resolved_normalized_name):
                return build_colliding_workspace_name(resolved_path.name, resolved_normalized_name)
            return resolved_normalized_name
        normalized_name = resolved_normalized_name
        legacy_name = resolved_legacy_name
        collision_path = resolved_path
        collision_name = resolved_path.name
    if workspace_slug_has_collision(collision_path, legacy_name):
        if legacy_name == normalized_name:
            return build_colliding_workspace_name(collision_name, legacy_name)
        return normalized_name
    return legacy_name


def resolve_workspace_name_fallback(worktree_path: pathlib.Path) -> str:
    return resolve_workspace_name_from_path(worktree_path)


def resolve_workspace_name_from_marker(worktree_path: pathlib.Path) -> str | None:
    marker = load_provision_marker(worktree_path / PROVISION_MARKER_FILENAME)
    if marker is None:
        return None

    workspace = marker.get("workspace")
    if not isinstance(workspace, str):
        return None

    workspace = workspace.strip()
    if not workspace:
        return None

    return normalize_workspace_name(workspace)


def resolve_stable_workspace_name(worktree_path: pathlib.Path) -> str:
    marker_workspace = resolve_workspace_name_from_marker(worktree_path)
    if marker_workspace is not None:
        return marker_workspace

    return resolve_workspace_name_from_path(worktree_path)


def find_current_worktree_record(
    connection: sqlite3.Connection,
    worktree_path: pathlib.Path,
) -> tuple[str | None, str | None] | None:
    current_path = resolve_path_for_matching(worktree_path)
    rows = connection.execute(
        """
        select id, path
        from worktrees
        order by created_at desc
        """
    ).fetchall()

    for worktree_id, registered_path in rows:
        if not isinstance(registered_path, str) or not registered_path.strip():
            continue

        try:
            registered_resolved_path = str(pathlib.Path(registered_path).resolve())
        except OSError:
            registered_resolved_path = registered_path

        if registered_resolved_path == current_path:
            return worktree_id, registered_path

    return None


def resolve_current_workspace_name(worktree_path: pathlib.Path, *, db_path: pathlib.Path | None = None) -> str:
    marker_workspace = resolve_workspace_name_from_marker(worktree_path)
    if marker_workspace is not None:
        return marker_workspace

    resolved_db_path = db_path or default_polyscope_db_path()
    if resolved_db_path.exists():
        try:
            with sqlite3.connect(resolved_db_path) as connection:
                current_worktree = find_current_worktree_record(connection, worktree_path)
        except sqlite3.Error:
            current_worktree = None

        if current_worktree is not None and isinstance(current_worktree[1], str) and current_worktree[1].strip():
            return resolve_stable_workspace_name(pathlib.Path(current_worktree[1]))

    return resolve_workspace_name_fallback(worktree_path)


def resolve_linked_workspace_name(
    worktree_path: pathlib.Path,
    linked_repo_name: str,
    *,
    db_path: pathlib.Path | None = None,
) -> str | None:
    resolved_db_path = db_path or default_polyscope_db_path()
    if not resolved_db_path.exists():
        return None

    try:
        with sqlite3.connect(resolved_db_path) as connection:
            current_worktree = find_current_worktree_record(connection, worktree_path)
            if current_worktree is None:
                return None

            current_worktree_id = current_worktree[0]
            row = connection.execute(
                """
                select linked_worktree.path
                from worktree_links
                join worktrees current_worktree on current_worktree.id = worktree_links.worktree_id
                join worktrees linked_worktree on linked_worktree.id = worktree_links.linked_worktree_id
                join repositories linked_repo on linked_repo.id = linked_worktree.repo_id
                where current_worktree.id = ? and linked_repo.name = ?
                order by worktree_links.created_at desc
                limit 1
                """,
                (current_worktree_id, linked_repo_name),
            ).fetchone()
    except sqlite3.Error:
        return None

    if row is None:
        return None

    return resolve_stable_workspace_name(pathlib.Path(row[0]))


def collect_linked_setup_context(
    worktree_path: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> dict[str, str]:
    resolved_db_path = db_path or default_polyscope_db_path()
    if not resolved_db_path.exists():
        return {}

    try:
        with sqlite3.connect(resolved_db_path) as connection:
            current_worktree = find_current_worktree_record(connection, worktree_path)
            if current_worktree is None:
                return {}

            current_worktree_id = current_worktree[0]
            rows = connection.execute(
                """
                select linked_repo.name, linked_worktree.path
                from worktree_links
                join worktrees current_worktree on current_worktree.id = worktree_links.worktree_id
                join worktrees linked_worktree on linked_worktree.id = worktree_links.linked_worktree_id
                join repositories linked_repo on linked_repo.id = linked_worktree.repo_id
                where current_worktree.id = ?
                order by linked_repo.name asc, worktree_links.created_at desc
                """,
                (current_worktree_id,),
            ).fetchall()
    except sqlite3.Error:
        return {}

    context: dict[str, str] = {}
    for repo_name, linked_path in rows:
        workspace_name = resolve_stable_workspace_name(pathlib.Path(linked_path))
        context.setdefault(repo_name, workspace_name)

    return context


def build_linked_workspace_resolver_source() -> str:
    return textwrap.dedent(
        """
        from pathlib import Path
        import hashlib
        import json
        import os
        import re
        import sqlite3

        def resolve_path_for_matching(path):
            try:
                return str(path.resolve())
            except OSError:
                return str(path)

        def find_current_worktree(connection):
            current_path = resolve_path_for_matching(Path.cwd())
            rows = connection.execute(
                '''
                select id, path
                from worktrees
                order by created_at desc
                '''
            ).fetchall()

            for worktree_id, registered_path in rows:
                if not isinstance(registered_path, str) or not registered_path.strip():
                    continue
                try:
                    registered_resolved_path = str(Path(registered_path).resolve())
                except OSError:
                    registered_resolved_path = registered_path
                if registered_resolved_path == current_path:
                    return worktree_id, registered_path

            return None

        def normalize_workspace_name(value, fallback='workspace'):
            normalized = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
            normalized = re.sub(r'-+', '-', normalized)
            return normalized or fallback

        def strip_legacy_workspace_suffix(value):
            return re.sub(r"-[0-9a-f]{8}$", "", value)

        def build_colliding_workspace_name(worktree_name, workspace):
            digest = hashlib.sha1(worktree_name.encode("utf-8")).hexdigest()[:8]
            return f"{workspace}-{digest}"

        def workspace_slug_has_collision(worktree_path, workspace):
            try:
                sibling_paths = tuple(worktree_path.parent.iterdir())
            except OSError:
                return False

            current_path = resolve_path_for_matching(worktree_path)
            for sibling_path in sibling_paths:
                if sibling_path == worktree_path:
                    continue

                sibling_workspace = normalize_workspace_name(strip_legacy_workspace_suffix(sibling_path.name))
                if sibling_workspace != workspace:
                    continue

                if resolve_path_for_matching(sibling_path) == current_path:
                    continue

                return True

            return False

        def resolve_workspace_name_from_path(worktree_path):
            normalized_name = normalize_workspace_name(worktree_path.name)
            legacy_name = normalize_workspace_name(strip_legacy_workspace_suffix(worktree_path.name))
            collision_path = worktree_path
            collision_name = worktree_path.name
            if legacy_name == normalized_name:
                try:
                    resolved_path = worktree_path.resolve()
                except OSError:
                    if workspace_slug_has_collision(worktree_path, normalized_name):
                        return build_colliding_workspace_name(worktree_path.name, normalized_name)
                    return normalized_name
                resolved_normalized_name = normalize_workspace_name(resolved_path.name)
                resolved_legacy_name = normalize_workspace_name(strip_legacy_workspace_suffix(resolved_path.name))
                if resolved_legacy_name == resolved_normalized_name:
                    if workspace_slug_has_collision(resolved_path, resolved_normalized_name):
                        return build_colliding_workspace_name(resolved_path.name, resolved_normalized_name)
                    return resolved_normalized_name
                normalized_name = resolved_normalized_name
                legacy_name = resolved_legacy_name
                collision_path = resolved_path
                collision_name = resolved_path.name
            if workspace_slug_has_collision(collision_path, legacy_name):
                if legacy_name == normalized_name:
                    return build_colliding_workspace_name(collision_name, legacy_name)
                return normalized_name
            return legacy_name

        def resolve_workspace_fallback(fallback):
            return resolve_workspace_name_from_path(Path(fallback))

        def load_provision_marker(marker_path):
            if not marker_path.exists():
                return None
            try:
                marker = json.loads(marker_path.read_text())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return None
            if not isinstance(marker, dict):
                return None
            return marker

        def resolve_workspace_name_from_marker(worktree_path):
            marker = load_provision_marker(worktree_path / ".polyscope-secpal-provisioned.json")
            if marker is None:
                return None
            workspace = marker.get("workspace")
            if not isinstance(workspace, str):
                return None
            workspace = workspace.strip()
            if not workspace:
                return None
            return normalize_workspace_name(workspace)

        def resolve_stable_workspace_name(worktree_path):
            marker_workspace = resolve_workspace_name_from_marker(worktree_path)
            if marker_workspace is not None:
                return marker_workspace
            return resolve_workspace_name_from_path(worktree_path)

        def resolve_current_workspace(fallback):
            marker_workspace = resolve_workspace_name_from_marker(Path(fallback))
            if marker_workspace is not None:
                return marker_workspace
            db_path = os.environ.get(
                "POLYSCOPE_DB_PATH",
                str(Path.home() / ".polyscope" / "polyscope.db"),
            )
            if not Path(db_path).exists():
                return resolve_workspace_fallback(fallback)
            try:
                with sqlite3.connect(db_path) as connection:
                    current_worktree = find_current_worktree(connection)
            except sqlite3.Error:
                current_worktree = None

            if current_worktree is not None and isinstance(current_worktree[1], str) and current_worktree[1].strip():
                return resolve_stable_workspace_name(Path(current_worktree[1]))

            return resolve_workspace_fallback(fallback)

        def resolve_linked_workspace(linked_repo_name, fallback):
            db_path = Path(os.environ.get("POLYSCOPE_DB_PATH", Path.home() / ".polyscope" / "polyscope.db"))
            if not db_path.exists():
                return fallback

            try:
                with sqlite3.connect(db_path) as connection:
                    current_worktree = find_current_worktree(connection)
                    if current_worktree is None:
                        return fallback
                    current_worktree_id = current_worktree[0]
                    row = connection.execute(
                        '''
                        select linked_worktree.path
                        from worktree_links
                        join worktrees current_worktree on current_worktree.id = worktree_links.worktree_id
                        join worktrees linked_worktree on linked_worktree.id = worktree_links.linked_worktree_id
                        join repositories linked_repo on linked_repo.id = linked_worktree.repo_id
                        where current_worktree.id = ? and linked_repo.name = ?
                        order by worktree_links.created_at desc
                        limit 1
                        ''',
                        (current_worktree_id, linked_repo_name),
                    ).fetchone()
            except sqlite3.Error:
                return fallback

            if row is None:
                return fallback

            return resolve_stable_workspace_name(Path(row[0]))
        """
    ).strip()


def generate_laravel_app_key() -> str:
    return "base64:" + base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def build_preview_url_template(preview_prefix: str | None) -> str:
    if preview_prefix:
        return f"https://{preview_prefix}-{{{{worktree}}}}.preview.secpal.dev"
    return "https://{{worktree}}.preview.secpal.dev"


def build_api_preview_env_setup_command(source_repo_path: pathlib.Path) -> str:
    rollout_script = shlex.quote(str(ROLLOUT_SCRIPT_PATH))
    source_repo = shlex.quote(str(source_repo_path))
    return (
        f"python3 {rollout_script} --prepare-api-worktree \"$PWD\" "
        f"--source-repo-path {source_repo}"
    )


def build_api_preview_runtime_shell_command(command: str, source_repo_path: pathlib.Path) -> str:
    rollout_script = shlex.quote(str(ROLLOUT_SCRIPT_PATH))
    source_repo = shlex.quote(str(source_repo_path))
    shell_command = shlex.quote(command)
    return (
        f"python3 {rollout_script} --run-api-worktree \"$PWD\" "
        f"--source-repo-path {source_repo} --shell-command {shell_command}"
    )


def decode_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        inner_value = value[1:-1]
        if value[0] == "\"":
            return inner_value.replace("\\\"", "\"").replace("\\\\", "\\")
        return inner_value
    return value


def load_env_assignments(env_path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        match = ENV_ASSIGNMENT_PATTERN.match(line.strip())
        if match is None:
            continue
        values[match.group(1)] = decode_env_value(match.group(2))
    return values


def upsert_env_assignments(text: str, updates: dict[str, str]) -> str:
    for key, value in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        replacement = f"{key}={encode_env_value(value)}"
        if pattern.search(text):
            text = pattern.sub(lambda _match, replacement=replacement: replacement, text)
            continue
        if text and not text.endswith("\n"):
            text += "\n"
        text += replacement + "\n"
    return text


def encode_env_value(value: str) -> str:
    if value == "":
        return value
    if not re.search(r'[\s"#\']', value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_api_worktree_env_template(
    source_repo_path: pathlib.Path,
    *,
    source_env_path: pathlib.Path | None = None,
) -> str:
    template_env_path = source_repo_path / ".env.example"
    if not template_env_path.exists():
        raise SystemExit(
            f"api source template missing; expected .env.example at {template_env_path}"
        )

    template_text = template_env_path.read_text()
    template_values = load_env_assignments(template_env_path)
    source_env_values: dict[str, str] = {}
    if source_env_path is not None and source_env_path.exists():
        source_env_values = load_env_assignments(source_env_path)

    merged_values: dict[str, str] = {}
    for key, value in template_values.items():
        if key not in SOURCE_ENV_BASE_VALUE_KEYS:
            continue
        if SENSITIVE_ENV_KEY_PATTERN.search(key):
            continue
        source_value = source_env_values.get(key)
        if source_value is None:
            continue
        merged_values[key] = source_value

    return upsert_env_assignments(template_text, merged_values)


def sanitize_postgres_identifier_component(value: str, fallback: str) -> str:
    sanitized = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return sanitized or fallback


def shorten_postgres_identifier_component(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 9:
        return value[:limit]
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    head = value[: limit - len(digest) - 1].rstrip("_") or value[: limit - len(digest) - 1]
    if not head:
        head = value[:1]
    return f"{head}_{digest}"


def build_preview_database_prefix(base_database: str) -> str:
    base_component = sanitize_postgres_identifier_component(base_database, "app")
    available = POSTGRES_IDENTIFIER_MAX_LENGTH - len(POSTGRES_PREVIEW_DATABASE_SEPARATOR) - 16
    return shorten_postgres_identifier_component(base_component, max(1, available)) + POSTGRES_PREVIEW_DATABASE_SEPARATOR


def build_preview_database_name(base_database: str, workspace: str) -> str:
    prefix = build_preview_database_prefix(base_database)
    workspace_component = sanitize_postgres_identifier_component(workspace, "workspace")
    available = POSTGRES_IDENTIFIER_MAX_LENGTH - len(prefix)
    workspace_component = shorten_postgres_identifier_component(workspace_component, max(1, available))
    return prefix + workspace_component


def resolve_base_database_name(env_values: dict[str, str], workspace: str) -> str | None:
    explicit_base = env_values.get(PREVIEW_DATABASE_BASE_ENV_KEY)
    if explicit_base:
        return explicit_base

    current_database = env_values.get("DB_DATABASE")
    if not current_database:
        return None

    workspace_components = {
        sanitize_postgres_identifier_component(workspace, "workspace"),
        sanitize_postgres_identifier_component(pathlib.Path(workspace).name, "workspace"),
    }
    stripped_workspace = re.sub(r"-[0-9a-f]{8}$", "", workspace)
    workspace_components.add(sanitize_postgres_identifier_component(stripped_workspace, "workspace"))

    if POSTGRES_PREVIEW_DATABASE_SEPARATOR in current_database:
        suffix = current_database.split(POSTGRES_PREVIEW_DATABASE_SEPARATOR, 1)[1]
        workspace_components.add(suffix)

    for workspace_component in workspace_components:
        preview_suffix = POSTGRES_PREVIEW_DATABASE_SEPARATOR + workspace_component
        if current_database.endswith(preview_suffix):
            candidate = current_database[: -len(preview_suffix)]
            if candidate:
                return candidate

    return current_database


def build_postgres_command_env(env_values: dict[str, str]) -> dict[str, str]:
    command_env = os.environ.copy()
    for source_key, target_key in {
        "DB_HOST": "PGHOST",
        "DB_PORT": "PGPORT",
        "DB_USERNAME": "PGUSER",
        "DB_PASSWORD": "PGPASSWORD",
    }.items():
        if source_key in env_values:
            command_env[target_key] = env_values[source_key]
    return command_env


def run_postgres_command(env_values: dict[str, str], database_name: str, sql: str) -> str:
    command = ["psql", "-v", "ON_ERROR_STOP=1"]
    host = env_values.get("DB_HOST", "").strip()
    port = env_values.get("DB_PORT", "").strip()
    username = env_values.get("DB_USERNAME", "").strip()
    if host:
        command.extend(["-h", host])
    if port:
        command.extend(["-p", port])
    if username:
        command.extend(["-U", username])
    command.extend(["-d", database_name, "-Atqc", sql])

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=build_postgres_command_env(env_values),
        )
    except FileNotFoundError as error:
        raise SystemExit("psql is required to manage Polyscope preview databases") from error
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.strip() or error.stdout.strip() or str(error)
        raise SystemExit(f"failed to manage Polyscope preview database via psql: {stderr}") from error

    return result.stdout.strip()


def postgres_role_can_create_databases(env_values: dict[str, str], base_database: str) -> bool:
    result = run_postgres_command(
        env_values,
        base_database,
        "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user",
    )
    return result.lower() in {"1", "t", "true", "yes", "on"}


def ensure_postgres_preview_database(env_values: dict[str, str], base_database: str, preview_database: str) -> None:
    exists = run_postgres_command(
        env_values,
        base_database,
        f"SELECT 1 FROM pg_database WHERE datname = '{preview_database}'",
    )
    if exists == "1":
        return

    run_postgres_command(env_values, base_database, f'CREATE DATABASE "{preview_database}"')


def list_postgres_preview_databases(env_values: dict[str, str], base_database: str) -> list[str]:
    prefix = build_preview_database_prefix(base_database)
    output = run_postgres_command(
        env_values,
        base_database,
        f"SELECT datname FROM pg_database WHERE datname LIKE '{prefix}%' ORDER BY datname",
    )
    return [line for line in output.splitlines() if line]


def drop_postgres_preview_database(env_values: dict[str, str], base_database: str, preview_database: str) -> None:
    run_postgres_command(
        env_values,
        base_database,
        f'DROP DATABASE IF EXISTS "{preview_database}" WITH (FORCE)',
    )


def list_postgres_preview_schemas(env_values: dict[str, str], base_database: str) -> list[str]:
    prefix = build_preview_database_prefix(base_database)
    output = run_postgres_command(
        env_values,
        base_database,
        f"SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE '{prefix}%' ORDER BY schema_name",
    )
    return [line for line in output.splitlines() if line]


def ensure_postgres_preview_schema(env_values: dict[str, str], base_database: str, preview_schema: str) -> None:
    run_postgres_command(env_values, base_database, f'CREATE SCHEMA IF NOT EXISTS "{preview_schema}"')


def drop_postgres_preview_schema(env_values: dict[str, str], base_database: str, preview_schema: str) -> None:
    run_postgres_command(env_values, base_database, f'DROP SCHEMA IF EXISTS "{preview_schema}" CASCADE')


def build_postgres_url(env_values: dict[str, str], database_name: str, search_path: str | None = None) -> str:
    username = env_values.get("DB_USERNAME", "")
    password = env_values.get("DB_PASSWORD", "")
    host = env_values.get("DB_HOST", "")
    port = env_values.get("DB_PORT", "")

    authority = ""
    if username:
        authority = urllib.parse.quote(username, safe="")
        if password:
            authority += ":" + urllib.parse.quote(password, safe="")
        authority += "@"
    authority += host
    if port:
        authority += f":{port}"

    query = ""
    if search_path is not None:
        query = urllib.parse.urlencode({"search_path": search_path})

    return urllib.parse.urlunsplit(
        (
            "postgresql",
            authority,
            "/" + urllib.parse.quote(database_name, safe=""),
            query,
            "",
        )
    )


def build_api_preview_kek_path(worktree_path: pathlib.Path) -> str:
    return str((worktree_path / "storage" / "app" / "keys" / "kek.key").resolve())


def load_optional_env_assignments(env_path: pathlib.Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    return load_env_assignments(env_path)


def build_db_password_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_source_managed_db_password(
    worktree_env_values: dict[str, str],
    source_env_values: dict[str, str],
) -> bool:
    if worktree_env_values.get("DB_CONNECTION", "").strip().lower() != "pgsql":
        return False

    worktree_db_password = worktree_env_values.get("DB_PASSWORD", "").strip()
    if not worktree_db_password:
        return True

    if (
        worktree_env_values.get(PREVIEW_DB_PASSWORD_SOURCE_ENV_KEY, "").strip()
        != PREVIEW_DB_PASSWORD_SOURCE_VALUE
    ):
        return False

    recorded_source_hash = worktree_env_values.get(
        PREVIEW_DB_PASSWORD_SOURCE_SHA256_ENV_KEY,
        "",
    ).strip()
    if recorded_source_hash:
        return recorded_source_hash == build_db_password_sha256(worktree_db_password)

    source_db_password = source_env_values.get("DB_PASSWORD", "").strip()
    return bool(source_db_password) and worktree_db_password == source_db_password


def build_source_db_password_tracking_updates(
    worktree_env_values: dict[str, str],
    source_env_values: dict[str, str],
) -> dict[str, str]:
    if is_source_managed_db_password(worktree_env_values, source_env_values):
        source_db_password = source_env_values.get("DB_PASSWORD", "").strip()
        if source_db_password:
            return {
                PREVIEW_DB_PASSWORD_SOURCE_ENV_KEY: PREVIEW_DB_PASSWORD_SOURCE_VALUE,
                PREVIEW_DB_PASSWORD_SOURCE_SHA256_ENV_KEY: build_db_password_sha256(source_db_password),
            }
        return {
            PREVIEW_DB_PASSWORD_SOURCE_ENV_KEY: "",
            PREVIEW_DB_PASSWORD_SOURCE_SHA256_ENV_KEY: "",
        }

    if any(
        worktree_env_values.get(key, "").strip()
        for key in (
            PREVIEW_DB_PASSWORD_SOURCE_ENV_KEY,
            PREVIEW_DB_PASSWORD_SOURCE_SHA256_ENV_KEY,
        )
    ):
        return {
            PREVIEW_DB_PASSWORD_SOURCE_ENV_KEY: "",
            PREVIEW_DB_PASSWORD_SOURCE_SHA256_ENV_KEY: "",
        }

    return {}


def build_api_preview_env_updates(
    workspace: str,
    frontend_workspace: str | None = None,
    *,
    worktree_path: pathlib.Path | None = None,
) -> dict[str, str]:
    resolved_frontend_workspace = frontend_workspace or workspace
    updates = {
        "APP_URL": f"https://api-{workspace}.preview.secpal.dev",
        "FRONTEND_URL": f"https://frontend-{resolved_frontend_workspace}.preview.secpal.dev",
        "SESSION_DOMAIN": ".secpal.dev",
        "SANCTUM_STATEFUL_DOMAINS": ",".join(
            (
                f"frontend-{resolved_frontend_workspace}.preview.secpal.dev",
                f"{resolved_frontend_workspace}.preview.secpal.dev",
                "app.secpal.dev",
            )
        ),
        "CORS_ALLOWED_ORIGINS": ",".join(
            (
                f"https://frontend-{resolved_frontend_workspace}.preview.secpal.dev",
                f"https://{resolved_frontend_workspace}.preview.secpal.dev",
                "https://app.secpal.dev",
            )
        ),
    }
    if worktree_path is not None:
        updates["KEK_PATH"] = build_api_preview_kek_path(worktree_path)
    return updates


def build_api_preview_storage_target(env_values: dict[str, str]) -> str | None:
    storage_mode = env_values.get(PREVIEW_STORAGE_MODE_ENV_KEY, "").strip().lower()

    if storage_mode == "database":
        preview_database = env_values.get("DB_DATABASE", "").strip()
        if preview_database:
            return f"database:{preview_database}"

    if storage_mode == "schema":
        base_database = env_values.get(PREVIEW_DATABASE_BASE_ENV_KEY, env_values.get("DB_DATABASE", "")).strip()
        preview_schema = env_values.get(PREVIEW_SCHEMA_ENV_KEY, "").strip()
        if base_database and preview_schema:
            return f"schema:{base_database}:{preview_schema}"

    return None


def build_api_worktree_runtime_env(
    worktree_env_values: dict[str, str],
    source_env_values: dict[str, str],
) -> dict[str, str]:
    runtime_env_values = dict(worktree_env_values)
    if is_source_managed_db_password(worktree_env_values, source_env_values):
        runtime_env_values["DB_PASSWORD"] = source_env_values.get("DB_PASSWORD", "").strip()
    return runtime_env_values


def build_api_worktree_command_env(
    worktree_env_values: dict[str, str],
    source_env_values: dict[str, str],
) -> dict[str, str]:
    command_env = os.environ.copy()
    runtime_env_values = build_api_worktree_runtime_env(worktree_env_values, source_env_values)
    for key, value in runtime_env_values.items():
        command_env[key] = value
    if runtime_env_values.get("DB_PASSWORD", "").strip():
        command_env["PGPASSWORD"] = runtime_env_values["DB_PASSWORD"]
    return command_env


def build_api_preview_test_user_tinker_script() -> str:
    return textwrap.dedent(
        r"""
        $canonical = \App\Models\User::where('email', 'test@example.com')->first();
        $legacy = \App\Models\User::where('email', 'test@password.com')->first();

        if ($canonical !== null) {
            if ($legacy !== null && ! $legacy->is($canonical)) {
                $legacy->delete();
            }
            $user = $canonical;
        } elseif ($legacy !== null) {
            $user = $legacy;
        } else {
            throw new \RuntimeException('Preview test user missing after seeding.');
        }

        $user->forceFill([
            'email' => 'test@example.com',
            'password' => bcrypt('password'),
            'email_verified_at' => now(),
        ])->save();
        """
    ).strip()


def discover_existing_api_preview_targets(env_values: dict[str, str], base_database: str) -> set[str]:
    preview_targets: set[str] = set()
    preview_prefix = build_preview_database_prefix(base_database)

    database_name = env_values.get("DB_DATABASE", "").strip()
    if database_name.startswith(preview_prefix):
        preview_targets.add(database_name)

    preview_schema = env_values.get(PREVIEW_SCHEMA_ENV_KEY, "").strip()
    if preview_schema.startswith(preview_prefix):
        preview_targets.add(preview_schema)

    return preview_targets


def ensure_api_worktree_ready(
    worktree_path: pathlib.Path,
    source_repo_path: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> tuple[bool, str | None]:
    env_path = worktree_path / ".env"
    source_env_path = source_repo_path / ".env"
    source_env_values = load_optional_env_assignments(source_env_path)
    if not env_path.exists():
        env_path.write_text(
            build_api_worktree_env_template(
                source_repo_path,
                source_env_path=source_env_path if source_env_path.exists() else None,
            )
        )
        print(
            f"Healed api worktree {worktree_path.name} at {worktree_path}: "
            f"wrote missing .env from template {source_repo_path / '.env.example'}"
        )

    env_text = env_path.read_text()
    env_values = load_env_assignments(env_path)
    runtime_env_values = build_api_worktree_runtime_env(env_values, source_env_values)
    workspace = resolve_current_workspace_name(worktree_path, db_path=db_path)
    frontend_workspace = resolve_linked_workspace_name(worktree_path, "SecPal/frontend", db_path=db_path)
    updated_values = build_api_preview_env_updates(
        workspace,
        frontend_workspace,
        worktree_path=worktree_path,
    )
    if not env_values.get("APP_KEY", "").strip():
        updated_values["APP_KEY"] = generate_laravel_app_key()

    if env_values.get("DB_CONNECTION", "").lower() == "pgsql":
        if (
            env_values.get("DB_PASSWORD", "").strip()
            != runtime_env_values.get("DB_PASSWORD", "").strip()
        ):
            updated_values["DB_PASSWORD"] = runtime_env_values["DB_PASSWORD"]
        updated_values.update(
            build_source_db_password_tracking_updates(env_values, source_env_values)
        )
        base_database = resolve_base_database_name(runtime_env_values, workspace)
        if not base_database:
            raise SystemExit(f"api worktree {worktree_path} is missing DB_DATABASE in .env")
        preview_target = build_preview_database_name(base_database, workspace)
        if postgres_role_can_create_databases(runtime_env_values, base_database):
            ensure_postgres_preview_database(runtime_env_values, base_database, preview_target)
            updated_values["DB_DATABASE"] = preview_target
            updated_values["DB_URL"] = ""
            updated_values[PREVIEW_STORAGE_MODE_ENV_KEY] = "database"
            updated_values[PREVIEW_SCHEMA_ENV_KEY] = ""
        else:
            ensure_postgres_preview_schema(runtime_env_values, base_database, preview_target)
            schema_url_env_values = runtime_env_values.copy()
            schema_url_env_values["DB_PASSWORD"] = ""
            updated_values["DB_DATABASE"] = base_database
            updated_values["DB_URL"] = build_postgres_url(
                schema_url_env_values,
                base_database,
                preview_target,
            )
            updated_values[PREVIEW_STORAGE_MODE_ENV_KEY] = "schema"
            updated_values[PREVIEW_SCHEMA_ENV_KEY] = preview_target
        updated_values[PREVIEW_DATABASE_BASE_ENV_KEY] = base_database

    updated_env_text = upsert_env_assignments(env_text, updated_values)
    if updated_env_text != env_text:
        env_path.write_text(updated_env_text)

    final_env_values = env_values.copy()
    final_env_values.update(updated_values)

    return True, build_api_preview_storage_target(final_env_values)


def run_api_worktree_bootstrap_command(
    worktree_path: pathlib.Path,
    command: list[str],
    *,
    command_env: dict[str, str],
) -> None:
    result = subprocess.run(
        command,
        cwd=worktree_path,
        env=command_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    result.check_returncode()


def is_recoverable_preview_tenant_key_failure(error: subprocess.CalledProcessError) -> bool:
    """Return whether seed output proves an isolated preview KEK mismatch."""
    output = error.output
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    if not isinstance(output, str):
        return False

    return "App\\Models\\TenantKey::loadKek" in output and "App\\Models\\TenantKey::unwrapDek" in output


def discard_stale_preview_kek(
    worktree_path: pathlib.Path,
    env_values: dict[str, str],
    preview_storage_target: str | None,
) -> bool:
    """Discard only a stale KEK belonging to an isolated API preview worktree."""
    if preview_storage_target is None or "__preview__" not in preview_storage_target:
        return False

    configured_kek_path = env_values.get("KEK_PATH", "").strip()
    expected_kek_path = pathlib.Path(build_api_preview_kek_path(worktree_path))
    if not configured_kek_path or pathlib.Path(configured_kek_path).resolve() != expected_kek_path:
        return False

    if expected_kek_path.exists():
        expected_kek_path.unlink()
    return True


def bootstrap_api_worktree(
    worktree_path: pathlib.Path,
    source_repo_path: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
    migration_command: list[str] | None = None,
    migration_label: str = "running migrations",
    allow_tenant_key_recovery: bool = True,
) -> tuple[bool, str | None]:
    env_path = worktree_path / ".env"
    preview_storage_target: str | None = None
    if not env_path.exists():
        ready, preview_storage_target = ensure_api_worktree_ready(
            worktree_path,
            source_repo_path,
            db_path=db_path,
        )
        if not ready:
            return ready, preview_storage_target

    env_values = load_env_assignments(env_path)
    if preview_storage_target is None:
        preview_storage_target = build_api_preview_storage_target(env_values)
    source_env_values = load_optional_env_assignments(source_repo_path / ".env")
    command_env = build_api_worktree_command_env(env_values, source_env_values)
    workspace = resolve_current_workspace_name(worktree_path, db_path=db_path)
    workspace_label = os.environ.get("POLYSCOPE_WORKSPACE_LABEL", workspace)
    prefix = f"[api:{workspace_label}]"
    if migration_command is None:
        migration_command = ["php", "artisan", "migrate", "--force"]

    if env_values.get("APP_KEY", "").strip():
        print(f"{prefix} app key already present")
    else:
        print(f"{prefix} generating app key")

    print(f"{prefix} clearing config cache")
    run_api_worktree_bootstrap_command(
        worktree_path,
        ["php", "artisan", "config:clear"],
        command_env=command_env,
    )

    print(f"{prefix} {migration_label}")
    run_api_worktree_bootstrap_command(
        worktree_path,
        migration_command,
        command_env=command_env,
    )

    print(f"{prefix} seeding database")
    try:
        run_api_worktree_bootstrap_command(
            worktree_path,
            ["php", "artisan", "db:seed", "--force"],
            command_env=command_env,
        )
    except subprocess.CalledProcessError as error:
        if not (
            allow_tenant_key_recovery
            and is_recoverable_preview_tenant_key_failure(error)
            and discard_stale_preview_kek(worktree_path, env_values, preview_storage_target)
        ):
            raise

        print(f"{prefix} recovering stale preview tenant key material")
        return bootstrap_api_worktree(
            worktree_path,
            source_repo_path,
            db_path=db_path,
            migration_command=["php", "artisan", "migrate:fresh", "--force"],
            migration_label="resetting preview database after tenant key recovery",
            allow_tenant_key_recovery=False,
        )

    print(f"{prefix} normalizing preview test user")
    run_api_worktree_bootstrap_command(
        worktree_path,
        ["php", "artisan", "tinker", f"--execute={build_api_preview_test_user_tinker_script()}"],
        command_env=command_env,
    )

    return True, preview_storage_target


def refresh_api_worktree(
    worktree_path: pathlib.Path,
    source_repo_path: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> tuple[bool, str | None]:
    ready, preview_storage_target = ensure_api_worktree_ready(
        worktree_path,
        source_repo_path,
        db_path=db_path,
    )
    if not ready:
        return ready, preview_storage_target
    return bootstrap_api_worktree(
        worktree_path,
        source_repo_path,
        db_path=db_path,
        migration_command=["php", "artisan", "migrate:fresh", "--force"],
        migration_label="refreshing database",
    )


def run_api_worktree_shell_command(
    worktree_path: pathlib.Path,
    source_repo_path: pathlib.Path,
    shell_command: str,
    *,
    db_path: pathlib.Path | None = None,
) -> None:
    env_path = worktree_path / ".env"
    if not env_path.exists():
        raise SystemExit(f"api worktree {worktree_path} is missing .env")

    env_values = load_env_assignments(env_path)
    source_env_values = load_optional_env_assignments(source_repo_path / ".env")
    command_env = build_api_worktree_command_env(env_values, source_env_values)
    if db_path is not None:
        command_env["POLYSCOPE_DB_PATH"] = str(db_path)

    os.chdir(worktree_path)
    os.execvpe("bash", ["bash", "-c", f"set -euo pipefail; exec {shell_command}"], command_env)


def cleanup_removed_api_preview_databases(
    repo_state: dict[str, dict[str, Any]],
    repo_specs: dict[str, dict[str, Any]],
    clone_root: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> list[str]:
    api_clone_root = clone_root / repo_state["api"]["id"]
    if not api_clone_root.exists():
        return []

    source_env_path = pathlib.Path(repo_specs["api"]["path"]) / ".env"
    if not source_env_path.exists():
        return []

    env_values = load_env_assignments(source_env_path)
    if env_values.get("DB_CONNECTION", "").lower() != "pgsql":
        return []

    base_database = resolve_base_database_name(env_values, "source")
    if not base_database:
        return []

    api_spec = repo_specs["api"]
    api_validation_commands = render_local_config(api_spec).get("scripts", {}).get("setup", [])
    active_targets: set[str] = set()
    for worktree_path in api_clone_root.iterdir():
        if not worktree_path.is_dir() or worktree_path.is_symlink():
            continue

        try:
            protects_storage_target = is_provisionable_worktree(
                "api",
                worktree_path,
                api_validation_commands,
                log_skip_reason=False,
            )
        except (OSError, SystemExit):
            protects_storage_target = True

        if protects_storage_target:
            active_targets.add(
                build_preview_database_name(
                    base_database,
                    resolve_current_workspace_name(worktree_path, db_path=db_path),
                )
            )
            env_path = worktree_path / ".env"
            if env_path.exists():
                active_targets.update(discover_existing_api_preview_targets(load_env_assignments(env_path), base_database))

    cleaned_databases: list[str] = []
    if postgres_role_can_create_databases(env_values, base_database):
        for preview_database in list_postgres_preview_databases(env_values, base_database):
            if preview_database in active_targets:
                continue
            drop_postgres_preview_database(env_values, base_database, preview_database)
            cleaned_databases.append(preview_database)

    for preview_schema in list_postgres_preview_schemas(env_values, base_database):
        if preview_schema in active_targets:
            continue
        drop_postgres_preview_schema(env_values, base_database, preview_schema)
        cleaned_databases.append(preview_schema)

    return cleaned_databases


def build_frontend_preview_env_setup_command() -> str:
    script = textwrap.dedent(
        f"""\
from pathlib import Path
import re

{build_linked_workspace_resolver_source()}

workspace = resolve_current_workspace(Path.cwd())
api_workspace = resolve_linked_workspace("SecPal/api", workspace)
pattern = re.compile(r"^VITE_API_URL=.*$", re.MULTILINE)
replacement = f"VITE_API_URL=https://api-{{api_workspace}}.preview.secpal.dev"

for env_name in (".env.local", ".env.preview.local", ".env.production.local"):
    env_path = Path(env_name)
    text = env_path.read_text() if env_path.exists() else ""
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        if text and not text.endswith("\\n"):
            text += "\\n"
        text += replacement + "\\n"

    env_path.write_text(text)
        """
    ).strip()

    return f"python3 -c {shlex.quote(script)}"


def build_verified_npm_ci_command() -> str:
    remove_node_modules_script = textwrap.dedent(
        """\
import os
import shutil
import stat
import time
from pathlib import Path

node_modules = Path("node_modules")
if not node_modules.exists():
    raise SystemExit(0)

def handle_remove_error(function, path, _excinfo):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass
    function(path)

last_error = None
for _ in range(5):
    try:
        shutil.rmtree(node_modules, onerror=handle_remove_error)
        last_error = None
        break
    except FileNotFoundError:
        last_error = None
        break
    except OSError as error:
        last_error = error
        time.sleep(1)

if last_error is not None:
    raise last_error
        """
    ).strip()

    validate_install_script = textwrap.dedent(
        """\
import json
from pathlib import Path

package_json = Path("package.json")
declared_packages = set()
if package_json.is_file():
    try:
        package_data = json.loads(package_json.read_text())
    except json.JSONDecodeError:
        package_data = {}
    if isinstance(package_data, dict):
        for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            section = package_data.get(key, {})
            if isinstance(section, dict):
                declared_packages.update(name for name in section if isinstance(name, str))

required_paths = []
if declared_packages:
    required_paths.append(Path("node_modules/.package-lock.json"))
if "typescript" in declared_packages:
    required_paths.extend(
        [
            Path("node_modules/typescript/lib/lib.es2020.d.ts"),
            Path("node_modules/typescript/lib/lib.dom.d.ts"),
        ]
    )
if "@types/node" in declared_packages:
    required_paths.append(Path("node_modules/@types/node/package.json"))

missing = [str(path) for path in required_paths if not path.is_file()]
if missing:
    raise SystemExit(1)
        """
    ).strip()

    return textwrap.dedent(
        f"""\
python3 -c {shlex.quote(remove_node_modules_script)}
for attempt in 1 2 3; do
    if test -f package.json && python3 - <<'PY'
import json
from pathlib import Path

for candidate in (Path("package-lock.json"), Path("npm-shrinkwrap.json")):
    if not candidate.is_file():
        continue
    try:
        data = json.loads(candidate.read_text())
    except json.JSONDecodeError:
        continue
    if isinstance(data, dict) and int(data.get("lockfileVersion", 0)) >= 1:
        raise SystemExit(0)

raise SystemExit(1)
PY
    then
        install_status=0
        if npm ci; then
            if python3 - <<'PY'
{validate_install_script}
PY
            then
                exit 0
            fi
            install_status=$?
        else
            install_status=$?
        fi
        echo "npm ci produced an incomplete install on attempt $attempt; retrying" >&2
        rm -rf node_modules
    fi
    sleep 2
done
echo "package-lock.json or npm-shrinkwrap.json was missing, incomplete, or npm ci produced an invalid install" >&2
exit 1
        """
    ).strip()


def build_frontend_preview_build_command() -> str:
    script = textwrap.dedent(
        f"""\
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

{build_linked_workspace_resolver_source()}

def replace_file(src_file: Path, dest_file: Path, tmp_dir: Path) -> None:
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", prefix=dest_file.name + "-", dir=tmp_dir)
    os.close(fd)
    shutil.copy2(src_file, tmp_path)
    if dest_file.is_dir() and not dest_file.is_symlink():
        shutil.rmtree(dest_file)
    os.replace(tmp_path, dest_file)

def merge_tree(src_dir: Path, dest_dir: Path, tmp_dir: Path) -> None:
    if dest_dir.is_symlink() or (dest_dir.exists() and not dest_dir.is_dir()):
        dest_dir.unlink()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for child in sorted(src_dir.iterdir()):
        dest_child = dest_dir / child.name
        if child.is_dir():
            merge_tree(child, dest_child, tmp_dir)
        else:
            replace_file(child, dest_child, tmp_dir)

def collect_stage_paths(stage_dir: Path, tmp_dir: Path) -> tuple[set[Path], set[Path]]:
    stage_dirs = {{Path(".")}}
    stage_files = set()
    for child in stage_dir.rglob("*"):
        if child == tmp_dir or tmp_dir in child.parents:
            continue

        relative = child.relative_to(stage_dir)
        if child.is_symlink():
            raise RuntimeError(f"staged build output contains symlink: {{relative}}")
        if child.is_dir():
            stage_dirs.add(relative)
        else:
            stage_files.add(relative)
    return stage_dirs, stage_files

def prune_live_tree(live_root: Path, stage_dirs: set[Path], stage_files: set[Path]) -> None:
    for child in sorted(live_root.rglob("*"), key=lambda path: len(path.relative_to(live_root).parts), reverse=True):
        relative = child.relative_to(live_root)
        if child.is_dir() and not child.is_symlink():
            if relative not in stage_dirs:
                shutil.rmtree(child)
        elif relative not in stage_files:
            child.unlink(missing_ok=True)

def publish_preview_build(stage_dir: Path) -> None:
    live_root = Path("dist")
    if live_root.is_symlink():
        raise RuntimeError("live preview dist is a symlink")
    live_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="publish-tmp-", dir=stage_dir) as _tmp:
        tmp_dir = Path(_tmp)
        stage_dirs, stage_files = collect_stage_paths(stage_dir, tmp_dir)

        stage_assets = stage_dir / "assets"
        if stage_assets.is_dir():
            merge_tree(stage_assets, live_root / "assets", tmp_dir)

        deferred_index: Path | None = None
        for child in sorted(stage_dir.iterdir()):
            if child.name == "assets":
                continue
            if child.name == tmp_dir.name:
                continue
            if child.name == "index.html":
                deferred_index = child
                continue
            destination = live_root / child.name
            if child.is_dir():
                merge_tree(child, destination, tmp_dir)
            else:
                replace_file(child, destination, tmp_dir)

        if deferred_index is not None:
            replace_file(deferred_index, live_root / "index.html", tmp_dir)

        prune_live_tree(live_root, stage_dirs, stage_files)

workspace = resolve_current_workspace(Path.cwd())
api_workspace = resolve_linked_workspace("SecPal/api", workspace)
env = os.environ.copy()
env["VITE_API_URL"] = f"https://api-{{api_workspace}}.preview.secpal.dev"
stage_root = Path(".polyscope-preview-stage")
stage_root.mkdir(exist_ok=True)
stage_dir = Path(tempfile.mkdtemp(prefix="frontend-", dir=stage_root))
try:
    result = subprocess.run(
        [
            "npm",
            "run",
            "build",
            "--",
            "--mode",
            "preview",
            "--outDir",
            stage_dir.as_posix(),
        ],
        env=env,
    )
    if result.returncode == 0:
        try:
            publish_preview_build(stage_dir)
        except Exception as exc:
            print(f"publish failed: {{exc}}", file=__import__("sys").stderr)
            raise SystemExit(1) from exc
    raise SystemExit(result.returncode)
finally:
    shutil.rmtree(stage_dir, ignore_errors=True)
        """
    ).strip()

    return f"python3 -c {shlex.quote(script)}"


def build_frontend_preview_build_watch_command() -> str:
    script = textwrap.dedent(
        f"""\
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

{build_linked_workspace_resolver_source()}

watch_directories = [Path("src"), Path("public"), Path("config")]
watch_files = [
            Path("index.html"),
            Path("package.json"),
            Path("package-lock.json"),
            Path("tsconfig.json"),
            Path("vite.config.ts"),
            Path("lingui.config.cjs"),
            Path("linguiVitePluginInterop.ts"),
            Path(".env.local"),
            Path(".env.preview.local"),
            Path(".env.production.local"),
            Path("node_modules/.package-lock.json"),
            Path("node_modules/.bin/cross-env"),
            Path("node_modules/.bin/vite"),
]
watch_suffixes = {
            ".css",
            ".html",
            ".ico",
            ".js",
            ".json",
            ".mjs",
            ".png",
            ".po",
            ".svg",
            ".ts",
            ".tsx",
            ".webmanifest",
}

def iter_watch_paths():
    seen = set()

    for path in watch_files:
        if not path.exists():
            continue

        try:
            resolved = path.resolve()
        except OSError:
            continue

        if resolved in seen:
            continue

        seen.add(resolved)
        yield path

    for directory in watch_directories:
        if not directory.exists():
            continue

        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in watch_suffixes:
                continue

            try:
                resolved = path.resolve()
            except OSError:
                continue

            if resolved in seen:
                continue

            seen.add(resolved)
            yield path

def snapshot() -> str:
    state = []

    for path in iter_watch_paths():
        try:
            stat = path.stat()
        except OSError:
            continue

        state.append(f"{{path.as_posix()}}:{{stat.st_mtime_ns}}:{{stat.st_size}}")

    return hashlib.sha256("\\n".join(state).encode("utf-8")).hexdigest()

def replace_file(src_file: Path, dest_file: Path, tmp_dir: Path) -> None:
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", prefix=dest_file.name + "-", dir=tmp_dir)
    os.close(fd)
    shutil.copy2(src_file, tmp_path)
    if dest_file.is_dir() and not dest_file.is_symlink():
        shutil.rmtree(dest_file)
    os.replace(tmp_path, dest_file)

def merge_tree(src_dir: Path, dest_dir: Path, tmp_dir: Path) -> None:
    if dest_dir.is_symlink() or (dest_dir.exists() and not dest_dir.is_dir()):
        dest_dir.unlink()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for child in sorted(src_dir.iterdir()):
        dest_child = dest_dir / child.name
        if child.is_dir():
            merge_tree(child, dest_child, tmp_dir)
        else:
            replace_file(child, dest_child, tmp_dir)

def collect_stage_paths(stage_dir: Path, tmp_dir: Path) -> tuple[set[Path], set[Path]]:
    stage_dirs = {{Path(".")}}
    stage_files = set()
    for child in stage_dir.rglob("*"):
        if child == tmp_dir or tmp_dir in child.parents:
            continue

        relative = child.relative_to(stage_dir)
        if child.is_symlink():
            raise RuntimeError(f"staged build output contains symlink: {{relative}}")
        if child.is_dir():
            stage_dirs.add(relative)
        else:
            stage_files.add(relative)
    return stage_dirs, stage_files

def prune_live_tree(live_root: Path, stage_dirs: set[Path], stage_files: set[Path]) -> None:
    for child in sorted(live_root.rglob("*"), key=lambda path: len(path.relative_to(live_root).parts), reverse=True):
        relative = child.relative_to(live_root)
        if child.is_dir() and not child.is_symlink():
            if relative not in stage_dirs:
                shutil.rmtree(child)
        elif relative not in stage_files:
            child.unlink(missing_ok=True)

def publish_preview_build(stage_dir: Path) -> None:
    live_root = Path("dist")
    if live_root.is_symlink():
        raise RuntimeError("live preview dist is a symlink")
    live_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="publish-tmp-", dir=stage_dir) as _tmp:
        tmp_dir = Path(_tmp)
        stage_dirs, stage_files = collect_stage_paths(stage_dir, tmp_dir)

        stage_assets = stage_dir / "assets"
        if stage_assets.is_dir():
            merge_tree(stage_assets, live_root / "assets", tmp_dir)

        deferred_index = None
        for child in sorted(stage_dir.iterdir()):
            if child.name == "assets":
                continue
            if child.name == tmp_dir.name:
                continue
            if child.name == "index.html":
                deferred_index = child
                continue
            destination = live_root / child.name
            if child.is_dir():
                merge_tree(child, destination, tmp_dir)
            else:
                replace_file(child, destination, tmp_dir)

        if deferred_index is not None:
            replace_file(deferred_index, live_root / "index.html", tmp_dir)

        prune_live_tree(live_root, stage_dirs, stage_files)

def run_build() -> int:
    workspace = resolve_current_workspace(Path.cwd())
    api_workspace = resolve_linked_workspace("SecPal/api", workspace)
    env = os.environ.copy()
    env["VITE_API_URL"] = f"https://api-{{api_workspace}}.preview.secpal.dev"
    stage_root = Path(".polyscope-preview-stage")
    stage_root.mkdir(exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix="frontend-", dir=stage_root))

    try:
        result = subprocess.run(
            [
                "npm",
                "run",
                "build",
                "--",
                "--mode",
                "preview",
                "--outDir",
                stage_dir.as_posix(),
            ],
            check=False,
            env=env,
        )
        if result.returncode == 0:
            try:
                publish_preview_build(stage_dir)
            except Exception as exc:
                print(f"publish failed: {{exc}}", file=sys.stderr)
                return 1
        return result.returncode
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

print("Watching frontend preview sources for changes...", flush=True)
previous_snapshot = None

while True:
    current_snapshot = snapshot()
    if current_snapshot != previous_snapshot:
        previous_snapshot = current_snapshot
        exit_code = run_build()
        if exit_code != 0:
            if exit_code == 127:
                print(
                    "Preview build dependencies were unavailable; waiting for dependency installation or a source change.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"Preview rebuild failed with exit code {{exit_code}}; waiting for the next change before retrying.",
                    file=sys.stderr,
                    flush=True,
                )

    time.sleep(1)
        """
    ).strip()

    return f"python3 -c {shlex.quote(script)}"


def build_frontend_preview_playwright_command(*, authenticated: bool) -> str:
    test_args = ["npx", "playwright", "test"]
    if not authenticated:
        test_args.extend(["tests/e2e/smoke.spec.ts", "--project=chromium", "--project=mobile-chrome"])

    script = textwrap.dedent(
        f"""\
import os
import subprocess
from pathlib import Path

{build_linked_workspace_resolver_source()}

workspace = resolve_current_workspace(Path.cwd())
api_workspace = resolve_linked_workspace("SecPal/api", workspace)
env = os.environ.copy()
env["PLAYWRIGHT_BASE_URL"] = f"https://frontend-{{workspace}}.preview.secpal.dev"
env["PLAYWRIGHT_API_BASE_URL"] = f"https://api-{{api_workspace}}.preview.secpal.dev"
{"env['TEST_USER_EMAIL'] = 'test@example.com'" if authenticated else "env['CI'] = 'true'"}
{"env['TEST_USER_PASSWORD'] = 'password'" if authenticated else "env['PLAYWRIGHT_SKIP_GLOBAL_LOGIN'] = '1'"}
raise SystemExit(subprocess.run({test_args!r}, env=env).returncode)
        """
    ).strip()

    return f"python3 -c {shlex.quote(script)}"


def build_preview_full_rebuild_watch_command(
    *,
    label: str,
    watch_directories: list[str],
    ignored_directories: list[str] | None = None,
    ignored_paths: list[str] | None = None,
    watch_files: list[str],
    watch_suffixes: list[str],
    build_args: list[str] | None = None,
) -> str:
    command = build_args or ["npm", "run", "build"]
    ignored_directories = ignored_directories or []
    ignored_paths = ignored_paths or []
    script = textwrap.dedent(
        f"""
        import hashlib
        import subprocess
        import sys
        import time
        from pathlib import Path

        watch_directories = [Path(value) for value in {watch_directories!r}]
        ignored_entries = [Path(value).resolve() for value in {(ignored_directories + ignored_paths)!r}]
        watch_files = [Path(value) for value in {watch_files!r}]
        watch_suffixes = set({watch_suffixes!r})
        build_args = {command!r}

        def is_ignored(path: Path) -> bool:
            try:
                resolved = path.resolve()
            except OSError:
                return True

            return any(ignored == resolved or ignored in resolved.parents for ignored in ignored_entries)

        def iter_watch_paths():
            seen = set()

            for path in watch_files:
                if not path.exists():
                    continue

                try:
                    resolved = path.resolve()
                except OSError:
                    continue

                if is_ignored(path):
                    continue

                if resolved in seen:
                    continue

                seen.add(resolved)
                yield path

            for directory in watch_directories:
                if not directory.exists():
                    continue

                for path in sorted(directory.rglob("*")):
                    if not path.is_file() or path.suffix not in watch_suffixes:
                        continue

                    try:
                        resolved = path.resolve()
                    except OSError:
                        continue

                    if is_ignored(path):
                        continue

                    if resolved in seen:
                        continue

                    seen.add(resolved)
                    yield path

        def snapshot() -> str:
            state = []

            for path in iter_watch_paths():
                try:
                    stat = path.stat()
                except OSError:
                    continue

                state.append(f"{{path.as_posix()}}:{{stat.st_mtime_ns}}:{{stat.st_size}}")

            return hashlib.sha256("\\n".join(state).encode("utf-8")).hexdigest()

        def run_build() -> int:
            return subprocess.run(build_args, check=False).returncode

        print({label!r}, flush=True)
        previous_snapshot = None

        while True:
            current_snapshot = snapshot()
            if current_snapshot != previous_snapshot:
                previous_snapshot = current_snapshot
                exit_code = run_build()
                if exit_code != 0:
                    print(
                        f"Preview rebuild failed with exit code {{exit_code}}; waiting for the next change before retrying.",
                        file=sys.stderr,
                        flush=True,
                    )

            time.sleep(1)
        """
    ).strip()

    return f"python3 -c {shlex.quote(script)}"


def build_guardguide_preview_build_watch_command() -> str:
    return build_preview_full_rebuild_watch_command(
        label="Watching GuardGuide preview sources for changes...",
        watch_directories=["app", "config", "public", "resources", "routes"],
        ignored_directories=["public/build"],
        watch_files=[
            "components.json",
            "lingui.config.cjs",
            "package.json",
            "package-lock.json",
            "postcss.config.mjs",
            "tailwind.config.js",
            "tailwind.config.cjs",
            "tailwind.config.mjs",
            "tailwind.config.ts",
            "tsconfig.json",
            "vite.config.ts",
        ],
        watch_suffixes=[
            ".avif",
            ".css",
            ".gif",
            ".html",
            ".jpeg",
            ".jpg",
            ".js",
            ".json",
            ".mjs",
            ".otf",
            ".php",
            ".po",
            ".png",
            ".svg",
            ".ts",
            ".tsx",
            ".vue",
            ".webp",
            ".woff",
            ".woff2",
        ],
    )


def build_static_preview_build_watch_command(
    site_name: str,
    watch_directories: list[str],
    *,
    ignored_paths: list[str] | None = None,
) -> str:
    return build_preview_full_rebuild_watch_command(
        label=f"Watching {site_name} preview sources for changes...",
        watch_directories=watch_directories,
        ignored_paths=ignored_paths,
        watch_files=[
            "astro.config.mjs",
            "eslint.config.js",
            "next.config.mjs",
            "package.json",
            "package-lock.json",
            "postcss.config.mjs",
            "tailwind.config.ts",
            "tsconfig.json",
        ],
        watch_suffixes=[
            ".avif",
            ".astro",
            ".css",
            ".gif",
            ".html",
            ".ico",
            ".jpeg",
            ".jpg",
            ".js",
            ".json",
            ".md",
            ".mdx",
            ".mjs",
            ".png",
            ".svg",
            ".ts",
            ".txt",
            ".tsx",
            ".webmanifest",
            ".webp",
            ".woff",
            ".woff2",
            ".xml",
            ".yml",
            ".yaml",
        ],
    )


def build_guardguide_preview_env_setup_command() -> str:
    script = "\n".join(
        [
            "from pathlib import Path",
            "import re",
            "",
            build_linked_workspace_resolver_source(),
            'workspace = resolve_current_workspace(Path.cwd())',
            'env_path = Path(".env")',
            'text = env_path.read_text() if env_path.exists() else ""',
            'pattern = re.compile(r"^APP_URL=.*$", re.MULTILINE)',
            'replacement = f"APP_URL=https://guardguide-{workspace}.preview.secpal.dev"',
            "",
            "if pattern.search(text):",
            "    text = pattern.sub(replacement, text)",
            "else:",
            '    if text and not text.endswith("\\n"):',
            '        text += "\\n"',
            '    text += replacement + "\\n"',
            "",
            "env_path.write_text(text)",
        ]
    )

    return f"python3 -c {shlex.quote(script)}"


def build_api_preview_bootstrap_command(source_repo_path: pathlib.Path) -> str:
    rollout_script = shlex.quote(str(ROLLOUT_SCRIPT_PATH))
    source_repo = shlex.quote(str(source_repo_path))
    return (
        f"python3 {rollout_script} --bootstrap-api-worktree \"$PWD\" "
        f"--source-repo-path {source_repo}"
    )


def build_api_preview_refresh_command(source_repo_path: pathlib.Path) -> str:
    rollout_script = shlex.quote(str(ROLLOUT_SCRIPT_PATH))
    source_repo = shlex.quote(str(source_repo_path))
    return (
        f"python3 {rollout_script} --refresh-api-worktree \"$PWD\" "
        f"--source-repo-path {source_repo}"
    )


def build_guardguide_preview_seed_command() -> str:
    tinker_script = textwrap.dedent(
        r"""
        $role = \Spatie\Permission\Models\Role::findByName(
            \App\Auth\GuardGuideAccessCatalog::ROLE_PLATFORM_ADMINISTRATOR,
            \App\Auth\GuardGuideAccessCatalog::GUARD,
        );

        $user = \App\Models\User::firstOrNew([
            'email' => 'test@example.com',
        ]);

        $user->forceFill([
            'name' => 'Test User',
            'email' => 'test@example.com',
            'password' => bcrypt('password'),
            'email_verified_at' => now(),
        ])->save();

        $user->assignRole($role);
        """
    ).strip()

    return (
        "php artisan db:seed --class=Database\\\\Seeders\\\\GuardGuideAccessSeeder --force && "
        f"php artisan tinker --execute={shlex.quote(tinker_script)}"
    )


def build_repo_all_checks_command(repo_name: str) -> str | None:
    commands = {
        "api": "php artisan test && vendor/bin/pint --dirty && vendor/bin/phpstan analyse --no-progress",
        "frontend": "npm run lint && npm run typecheck && npm run test:run:all && npm run build",
        "GuardGuide": "npm run format:check && npm run lint:check && npm run typecheck && npm run test && composer run lint:check && composer run analyse && composer run test",
        "contracts": "npm run validate && npm run lint && npm run format:check",
        "android": "npm run lint && npm run typecheck && npm run test:run && npm run native:verify",
        "secpal.app": "npm run check && npm run lint && npm run test && npm run build",
        "changelog": "npm run check && npm run lint && npm run csp:check && npm run build",
        "guardguide.de": "npm run check && npm run lint && npm run test && npm run build",
        ".github": "./scripts/preflight.sh",
    }
    return commands.get(repo_name)


def ensure_run_action(
    actions: list[dict[str, Any]],
    *,
    label: str,
    command: str,
    run_mode: str = "preserve",
    autostart: bool | None = None,
) -> list[dict[str, Any]]:
    if any(item.get("label") == label for item in actions):
        return actions

    action: dict[str, Any] = {"label": label, "command": command, "runMode": run_mode}
    if autostart is not None:
        action["autostart"] = autostart

    return [action, *actions]


def ensure_task(tasks: list[dict[str, str]], *, label: str, prompt: str) -> list[dict[str, str]]:
    if any(item.get("label") == label for item in tasks):
        return tasks
    return [{"label": label, "prompt": prompt}, *tasks]


def enrich_local_config(repo_name: str, spec: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    scripts = config.setdefault("scripts", {})
    run_actions = [dict(item) for item in scripts.get("run", [])]

    all_checks_command = build_repo_all_checks_command(repo_name)
    if all_checks_command is not None:
        run_actions = ensure_run_action(run_actions, label="All Checks", command=all_checks_command)

    preflight_script = pathlib.Path(spec["path"]) / "scripts" / "preflight.sh"
    if preflight_script.is_file():
        run_actions = ensure_run_action(run_actions, label="Preflight", command="./scripts/preflight.sh")

    scripts["run"] = run_actions

    tasks = [dict(item) for item in config.get("tasks", [])]
    tasks = ensure_task(
        tasks,
        label="Fix current findings",
        prompt=(
            "Run the generated validation actions for this repo, including All Checks and Preflight when available. "
            "Fix the current findings in this repo only, rerun the touched validations until they are clean, and keep the branch scoped to one issue. "
            "If the findings expand into unrelated topics or require broader cleanup, stop and track them instead of widening the change."
        ),
    )
    config["tasks"] = tasks

    return config


REPO_SETTINGS: dict[str, dict[str, Any]] = {
    "api": {
        "display_name": "SecPal/api",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/php-laravel.instructions.md",
        ],
        "preview_prefix": "api",
        "review_focus": "Laravel 13, Pest 4, Request -> Controller -> Service -> Repository -> Model, Sanctum session versus bearer-token flows, and encrypted data handling via *_plain/*_idx without direct *_enc reads.",
        "link_names": ["frontend", "contracts", "android"],
        "local_config": {
            "copyGitignored": False,
            "runMode": "replace",
            "preview": {"url": build_preview_url_template("api")},
            "scripts": {
                "setup": [
                    "test -d vendor || composer install",
                    API_BOOTSTRAP_SETUP_COMMAND_PLACEHOLDER,
                ],
                "run": [
                    {"label": "Queue Worker", "command": API_QUEUE_WORKER_COMMAND, "autostart": True, "runMode": "replace"},
                    {"label": "Scheduler", "command": API_SCHEDULER_COMMAND, "autostart": True, "runMode": "replace"},
                    {"label": "Pail", "command": API_PAIL_COMMAND, "runMode": "replace"},
                    # Preview-only safety note: this destructive reset is for SecPal preview/dev workspaces only.
                    # It intentionally reseeds the canonical E2E login `test@example.com` / `password` and must never target production.
                    {
                        "label": "Preview Only: Refresh DB + E2E User",
                        "command": API_REFRESH_COMMAND_PLACEHOLDER,
                        "runMode": "preserve",
                    },
                    {"label": "Pest", "command": "php artisan test", "runMode": "preserve"},
                    {"label": "Pint (dirty)", "command": "vendor/bin/pint --dirty", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review auth surface",
                    "prompt": "Review the authentication and self-service surface for regressions. Focus on Sanctum session versus bearer-token behavior, route aliases, permission gates, and missing Pest coverage. If frontend behavior or contract shape is involved, ask for the relevant linked workspace before proposing changes.",
                },
                {
                    "label": "Triage failing Pest",
                    "prompt": "Reproduce the failing behavior, identify the smallest relevant Pest test to add or update first, then implement the minimal fix and rerun the touched validation. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "frontend": {
        "display_name": "SecPal/frontend",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/react-typescript.instructions.md",
        ],
        "preview_prefix": "frontend",
        "review_focus": "React, Vite, strict TypeScript, generated API types, Testing Library/MSW boundaries, auth-storage discipline, and transport failure handling.",
        "link_names": ["api", "contracts", "android"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": build_preview_url_template("frontend")},
            "scripts": {
                "setup": [
                    build_frontend_preview_env_setup_command(),
                    build_verified_npm_ci_command(),
                    build_frontend_preview_build_command(),
                ],
                "run": [
                    {
                        "label": "Build Watch",
                        "command": build_frontend_preview_build_watch_command(),
                        "autostart": True,
                        "runMode": "replace",
                    },
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "Typecheck", "command": "npm run typecheck", "runMode": "preserve"},
                    {"label": "Vitest", "command": "npm run test:watch", "runMode": "replace"},
                    {
                        "label": "Workspace Preview CSP Smoke",
                        "command": "npm run test:preview:pwa-headers",
                        "runMode": "preserve",
                    },
                    {
                        "label": "Playwright Local Preview Smoke",
                        "command": "npm run test:e2e:ci",
                        "runMode": "preserve",
                    },
                    {
                        "label": "Playwright Workspace Preview Smoke",
                        "command": build_frontend_preview_playwright_command(authenticated=False),
                        "runMode": "preserve",
                    },
                    {
                        "label": "Playwright Workspace Preview Authenticated",
                        "command": build_frontend_preview_playwright_command(authenticated=True),
                        "runMode": "preserve",
                    },
                ],
            },
            "tasks": [
                {
                    "label": "Review UI/API contract",
                    "prompt": "Review the touched frontend flow for contract drift, auth-state regressions, transport error handling, and missing Vitest coverage. If the issue touches API responses or auth rules, ask for the linked API workspace before proposing changes.",
                },
                {
                    "label": "Triage failing Vitest",
                    "prompt": "Reproduce the failing behavior, add or update the smallest relevant test first, then implement the minimal fix and rerun the touched validation. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "GuardGuide": {
        "display_name": "SecPal/GuardGuide",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/php-laravel.instructions.md",
            ".github/instructions/react-shadcn.instructions.md",
        ],
        "preview_prefix": "guardguide",
        "review_focus": "Laravel 13 monolith boundaries, Pest coverage plus frontend build and typecheck validation, shadcn/ui-aligned UI patterns, Lingui localization, application-layer encryption for person-related data, and standalone-first acknowledgement flows.",
        "link_names": ["api", "frontend", "contracts", "android"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": build_preview_url_template("guardguide")},
            "scripts": {
                "setup": [
                    "composer install",
                    "npm ci",
                    "test -f .env || cp .env.example .env",
                    build_guardguide_preview_env_setup_command(),
                    "test -f database/database.sqlite || touch database/database.sqlite",
                    "grep -Eq '^APP_KEY=.+$' .env || php artisan key:generate --force",
                    "php artisan migrate --force",
                    build_guardguide_preview_seed_command(),
                    "npm run build",
                ],
                "run": [
                    {"label": "Pest", "command": "php artisan test", "runMode": "preserve"},
                    {"label": "Typecheck", "command": "npm run typecheck", "runMode": "preserve"},
                    {"label": "Build", "command": "npm run build", "runMode": "preserve"},
                    {
                        "label": "Build Watch",
                        "command": build_guardguide_preview_build_watch_command(),
                        "autostart": True,
                        "runMode": "replace",
                    },
                ],
            },
            "tasks": [
                {
                    "label": "Review monolith boundary",
                    "prompt": "Review the changed GuardGuide flow for Laravel monolith boundary drift, shadcn/ui regressions, localization gaps, encryption-at-rest constraints, and missing Pest coverage or frontend validation. Keep the change scoped to one GuardGuide issue.",
                },
                {
                    "label": "Triage GuardGuide validation",
                    "prompt": "Reproduce the failing GuardGuide behavior, add or update the smallest relevant Pest coverage first when possible, then implement the minimal fix and rerun the touched validation. Use typecheck or build validation when the touched slice is frontend-only. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "contracts": {
        "display_name": "SecPal/contracts",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/openapi.instructions.md",
        ],
        "preview_prefix": None,
        "review_focus": "OpenAPI 3.1 as contract-first source of truth, reusable $ref schemas, consistent security schemes, complete response coverage, and Redocly validation.",
        "link_names": ["api", "frontend"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "scripts": {
                "setup": [build_verified_npm_ci_command()],
                "run": [
                    {"label": "Validate", "command": "npm run validate", "runMode": "preserve"},
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "Format Check", "command": "npm run format:check", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review contract drift",
                    "prompt": "Review the changed OpenAPI contract for breaking shape changes, enum drift, security scheme regressions, and missing example or Redocly validation coverage. If API or frontend implementation is involved, ask for the linked workspace before proposing changes.",
                },
                {
                    "label": "Triage failing Redocly",
                    "prompt": "Reproduce the failing contract validation, update the smallest relevant schema or example first, then rerun the touched validation. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "android": {
        "display_name": "SecPal/android",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/react-capacitor.instructions.md",
        ],
        "preview_prefix": None,
        "review_focus": "React plus Capacitor bridge boundaries, managed-mode and device-owner semantics, listener cleanup through remove(), and strict TypeScript around native interop.",
        "link_names": ["api", "frontend"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "scripts": {
                "setup": [build_verified_npm_ci_command()],
                "run": [
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "Typecheck", "command": "npm run typecheck", "runMode": "preserve"},
                    {"label": "Vitest", "command": "npm run test:run", "runMode": "preserve"},
                    {"label": "Native Verify", "command": "npm run native:verify", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review native boundary",
                    "prompt": "Review the Android-side change for Capacitor bridge regressions, device-owner or managed-mode side effects, auth bootstrap behavior, and missing focused Vitest coverage. If the web build or API contract is involved, ask for the linked frontend or API workspace before proposing changes.",
                },
                {
                    "label": "Triage Android validation",
                    "prompt": "Reproduce the failing Android-side behavior, update the smallest relevant test first when possible, then implement the minimal fix and rerun the touched validation. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "secpal.app": {
        "display_name": "SecPal/secpal.app",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/astro-static.instructions.md",
        ],
        "preview_prefix": "secpal-app",
        "review_focus": "Astro static rendering, minimal client-side JavaScript, semantic HTML, accessible landmarks, and strict TypeScript on the public site.",
        "link_names": ["changelog"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": build_preview_url_template("secpal-app")},
            "scripts": {
                "setup": [build_verified_npm_ci_command(), "npm run build"],
                "run": [
                    {
                        "label": "Build Watch",
                        "command": build_static_preview_build_watch_command(
                            "secpal.app",
                            ["public", "scripts", "secpal.app", "src"],
                            ignored_paths=[
                                "public/og-default.svg",
                                "public/og-default.png",
                                "public/og-de.svg",
                                "public/og-de.png",
                            ],
                        ),
                        "autostart": True,
                        "runMode": "replace",
                    },
                    {"label": "Astro Check", "command": "npm run check", "runMode": "preserve"},
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "Tests", "command": "npm run test", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review site semantics",
                    "prompt": "Review the marketing-site change for static-build regressions, accessibility drift, semantic HTML changes, and missing test or Astro-check coverage. Keep the work scoped to the touched page or component.",
                },
                {
                    "label": "Triage failing Astro",
                    "prompt": "Reproduce the failing static-site behavior or Astro check, add or update the smallest relevant validation first, then implement the minimal fix and rerun the touched commands. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "guardguide.de": {
        "display_name": "SecPal/guardguide.de",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/astro-static.instructions.md",
        ],
        "preview_prefix": "guardguide-de",
        "review_focus": "Astro static rendering, minimal client-side JavaScript, semantic HTML, accessible landmarks, and strict TypeScript on the public site.",
        "link_names": [],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": build_preview_url_template("guardguide-de")},
            "scripts": {
                "setup": [build_verified_npm_ci_command(), "npm run build"],
                "run": [
                    {
                        "label": "Build Watch",
                        "command": build_static_preview_build_watch_command(
                            "guardguide.de",
                            ["public", "scripts", "src"],
                            ignored_paths=[
                                "public/og-default.svg",
                                "public/og-default.png",
                                "public/og-de.svg",
                                "public/og-de.png",
                            ],
                        ),
                        "autostart": True,
                        "runMode": "replace",
                    },
                    {"label": "Astro Check", "command": "npm run check", "runMode": "preserve"},
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "Tests", "command": "npm run test", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review site semantics",
                    "prompt": "Review the marketing-site change for static-build regressions, accessibility drift, semantic HTML changes, and missing test or Astro-check coverage. Keep the work scoped to the touched page or component.",
                },
                {
                    "label": "Triage failing Astro",
                    "prompt": "Reproduce the failing static-site behavior or Astro check, add or update the smallest relevant validation first, then implement the minimal fix and rerun the touched commands. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    "changelog": {
        "display_name": "SecPal/changelog",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [
            ".github/instructions/org-shared.instructions.md",
            ".github/instructions/nextjs-changelog.instructions.md",
        ],
        "preview_prefix": "changelog",
        "review_focus": "Next.js static-style changelog output, MDX content rules, Commit template conventions, CSP/feed safety, and no server-side runtime dependencies.",
        "link_names": ["secpal.app"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": build_preview_url_template("changelog")},
            "scripts": {
                "setup": [build_verified_npm_ci_command(), "npm run build"],
                "run": [
                    {
                        "label": "Build Watch",
                        "command": build_static_preview_build_watch_command(
                            "changelog",
                            ["changelog", "mdx", "public", "scripts", "src"],
                        ),
                        "autostart": True,
                        "runMode": "replace",
                    },
                    {"label": "Typecheck", "command": "npm run check", "runMode": "preserve"},
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "CSP Check", "command": "npm run csp:check", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review changelog export",
                    "prompt": "Review the changelog-site change for static export regressions, feed or CSP drift, MDX rendering issues, and missing lint or typecheck coverage. Keep the work scoped to the touched entry or component.",
                },
                {
                    "label": "Triage failing Next build",
                    "prompt": "Reproduce the failing changelog build or typecheck, update the smallest relevant input first, then implement the minimal fix and rerun the touched validation. Keep the change scoped to one issue.",
                },
            ],
        },
    },
    ".github": {
        "display_name": "SecPal/.github",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [".github/instructions/github-workflows.instructions.md"],
        "preview_prefix": None,
        "review_focus": "GitHub Actions permissions, timeout-minutes, pinned actions, reusable workflow invariants, preflight validation, and governance safety over cosmetic cleanup.",
        "link_names": [],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "scripts": {
                "setup": [build_verified_npm_ci_command()],
                "run": [
                    {"label": "Preflight", "command": "./scripts/preflight.sh", "runMode": "preserve"},
                    {"label": "AI Review Scan", "command": "npm run copilot:review:scan", "runMode": "preserve"},
                ],
            },
            "tasks": [
                {
                    "label": "Review workflow governance",
                    "prompt": "Review the changed governance or workflow files for policy regressions, coverage gaps, permission drift, and missing validation. Keep the change scoped to one workflow or rule set.",
                },
                {
                    "label": "Triage failing preflight",
                    "prompt": "Reproduce the failing governance validation, update the smallest relevant rule or fixture first, then implement the minimal fix and rerun preflight. Keep the change scoped to one issue.",
                },
            ],
        },
    },
}


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            return parts[1]
    return text


def strip_html_comment_header(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("<!--"):
        parts = stripped.split("-->\n", 1)
        if len(parts) == 2:
            return parts[1].lstrip()
    return text


def write_text_if_changed(path: pathlib.Path, content: str) -> bool:
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def resolve_android_sdk_root() -> pathlib.Path:
    for variable_name in ("POLYSCOPE_ANDROID_SDK_ROOT", "ANDROID_SDK_ROOT", "ANDROID_HOME"):
        value = os.environ.get(variable_name, "").strip()
        if value:
            return pathlib.Path(value).expanduser()
    return DEFAULT_ANDROID_SDK_ROOT


def render_android_local_properties(existing_text: str = "") -> str:
    sdk_dir_line = f"sdk.dir={resolve_android_sdk_root().as_posix()}"
    preserved_lines: list[str] = []
    sdk_dir_written = False

    for raw_line in existing_text.splitlines():
        if raw_line.startswith("sdk.dir="):
            if not sdk_dir_written:
                preserved_lines.append(sdk_dir_line)
                sdk_dir_written = True
            continue
        preserved_lines.append(raw_line)

    if not sdk_dir_written:
        preserved_lines.append(sdk_dir_line)

    return "\n".join(preserved_lines) + "\n"


def sync_repo_auxiliary_files(repo_name: str, repo_path: pathlib.Path) -> None:
    if repo_name != "android":
        return

    android_project_dir = repo_path / "android"
    if not android_project_dir.is_dir():
        raise SystemExit(f"android worktree at {repo_path} is missing committed android/ project directory")

    local_properties_path = android_project_dir / "local.properties"
    existing_local_properties = local_properties_path.read_text() if local_properties_path.exists() else ""
    write_text_if_changed(local_properties_path, render_android_local_properties(existing_local_properties))
    ensure_exclude(repo_path, {"android/local.properties"})


def extract_bullets_from_lines(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            bullets.append(collapse_spaces(" ".join(current)))
            current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            flush()
            current.append(stripped[2:])
            continue
        if current and not stripped.startswith("#"):
            current.append(stripped)
            continue
        flush()

    flush()
    return bullets


def extract_all_bullets(text: str) -> list[str]:
    return extract_bullets_from_lines(strip_frontmatter(text).splitlines())


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in strip_frontmatter(text).splitlines():
        heading_match = re.match(r"^##\s+(.*)$", line)
        if heading_match:
            if current_heading is not None:
                sections[current_heading] = extract_bullets_from_lines(current_lines)
            current_heading = heading_match.group(1).strip()
            current_lines = []
            continue
        if current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = extract_bullets_from_lines(current_lines)

    return sections


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def select_bullets(bullets: list[str], keywords: list[str], limit: int) -> list[str]:
    lowered_keywords = [keyword.lower() for keyword in keywords]
    prioritized = [
        bullet
        for bullet in bullets
        if any(keyword in bullet.lower() for keyword in lowered_keywords)
    ]
    return dedupe_keep_order(prioritized + bullets)[:limit]


def format_bullets(bullets: list[str]) -> str:
    return "; ".join(bullets)


def build_repo_specs(workspace_root: pathlib.Path) -> dict[str, dict[str, Any]]:
    repo_specs: dict[str, dict[str, Any]] = {}
    for repo_name, settings in REPO_SETTINGS.items():
        spec = copy.deepcopy(settings)
        repo_path = workspace_root / repo_name
        spec["path"] = repo_path
        spec["agent_instructions"] = repo_path / "AGENTS.md"
        spec["copilot_instructions"] = repo_path / settings["copilot_instructions"]
        spec["focus_instruction_paths"] = [repo_path / path for path in settings["focus_instruction_paths"]]
        if repo_name == "api":
            spec["local_config"]["scripts"]["setup"].insert(0, build_api_preview_env_setup_command(repo_path))
            spec["local_config"]["scripts"]["setup"] = [
                build_api_preview_bootstrap_command(repo_path)
                if command == API_BOOTSTRAP_SETUP_COMMAND_PLACEHOLDER
                else command
                for command in spec["local_config"]["scripts"]["setup"]
            ]
            for run_action in spec["local_config"]["scripts"]["run"]:
                if run_action.get("command") == API_REFRESH_COMMAND_PLACEHOLDER:
                    run_action["command"] = build_api_preview_refresh_command(repo_path)
                    continue
                if run_action.get("command") in API_RUNTIME_PREVIEW_COMMANDS:
                    run_action["command"] = build_api_preview_runtime_shell_command(run_action["command"], repo_path)
        repo_specs[repo_name] = spec
    return repo_specs


def instruction_reference(spec: dict[str, Any]) -> str:
    if spec["agent_instructions"].exists():
        return str(spec["agent_instructions"])
    return str(spec["copilot_instructions"])


def load_runtime_instructions_text(spec: dict[str, Any]) -> str:
    if spec["agent_instructions"].exists():
        return spec["agent_instructions"].read_text()
    return spec["copilot_instructions"].read_text()


def extract_agents_runtime_body(text: str) -> str:
    body = strip_html_comment_header(text)
    core_index = body.find("## Core Runtime Baseline")
    if core_index != -1:
        return body[core_index:].strip()
    heading = re.search(r"^##\s+", body, re.MULTILINE)
    if heading is None:
        raise SystemExit("AGENTS.md is missing a section heading after the repository preamble")
    return body[heading.start() :].strip()


def render_copilot_compat_instructions(spec: dict[str, Any]) -> str:
    if not spec["agent_instructions"].exists():
        raise FileNotFoundError(spec["agent_instructions"])
    body = extract_agents_runtime_body(spec["agent_instructions"].read_text())
    focus_lines = "\n".join(
        f"- `{path.relative_to(spec['path']).as_posix()}`" for path in spec["focus_instruction_paths"]
    )
    rendered = "\n".join(
        [
            "<!--",
            "SPDX-FileCopyrightText: 2026 SecPal",
            "SPDX-License" + "-Identifier: AGPL-3.0-or-later",
            "-->",
            "",
            f"# {spec['display_name']} Copilot Instructions",
            "",
            "This file mirrors the authoritative root `AGENTS.md` for tooling",
            "that automatically loads `.github/copilot-instructions.md`.",
            "Edit `AGENTS.md` first. Keep the focused overlay files aligned",
            "for path-specific or stack-specific rules.",
            "",
            "## Authoritative Sources",
            "",
            "- `AGENTS.md`",
            *([focus_lines] if focus_lines else []),
            "",
            body,
        ]
    ).rstrip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", rendered)


def write_copilot_compat_instructions(repo_specs: dict[str, dict[str, Any]]) -> None:
    for spec in repo_specs.values():
        if not spec["agent_instructions"].exists():
            continue
        write_text_if_changed(spec["copilot_instructions"], render_copilot_compat_instructions(spec))


def build_prompt_bundle(spec: dict[str, Any]) -> dict[str, str]:
    agents_text = load_runtime_instructions_text(spec)
    sections = parse_sections(agents_text)
    focus_bullets: list[str] = []
    for focus_path in spec["focus_instruction_paths"]:
        focus_bullets.extend(extract_all_bullets(pathlib.Path(focus_path).read_text()))

    always_on = select_bullets(
        sections.get("Always-On Rules", []),
        ["git status", "tdd", "validate-first", "one topic", "bypass", "changelog", "issue immediately", "domain policy"],
        7,
    )
    validation = select_bullets(
        sections.get("Required Validation", []),
        ["scope", "tdd", "validation", "lint", "typecheck", "build", "pest", "preflight", "changelog", "issue", "gpg", "reuse", "no bypass"],
        8,
    )
    triage = select_bullets(
        sections.get("AI Findings Triage", []),
        ["prove the defect", "green ci", "compatibility", "refactor", "regression", "security"],
        5,
    )
    focus = select_bullets(
        focus_bullets,
        ["test", "validation", "strict typescript", "generated api types", "bridge", "openapi 3.1", "semantic", "permissions", "timeout-minutes", "pint", "form requests", "client-side javascript", "server actions"],
        6,
    )
    issue_pr = select_bullets(
        sections.get("Issue And PR Discipline", []),
        ["draft", "english", "body-file", "one topic", "self-review"],
        5,
    )

    instruction_ref = instruction_reference(spec)
    review_prompt = collapse_spaces(
        f"Apply the current SecPal instructions from {instruction_ref}. "
        f"Non-negotiable rules: {NO_AI_ATTRIBUTION_RULE}; {format_bullets(always_on)}. "
        f"Repository focus: {spec['review_focus']} "
        f"Targeted file-scope rules: {format_bullets(focus)}. "
        f"Review and AI-triage bar: {format_bullets(triage)}. "
        "If shared auth, contract, mobile, or release behavior crosses repo boundaries, pull the relevant linked workspaces before proposing changes."
    )
    pr_prompt = collapse_spaces(
        f"Write a concise English PR body for {spec['display_name']}. Apply {instruction_ref}. "
        f"{NO_AI_ATTRIBUTION_RULE} "
        f"Keep the PR to one topic and reflect the PR discipline: {format_bullets(issue_pr)}. "
        "Lead with the failing test, validation, or reproduced defect. Then summarize the user-, API-, contract-, or governance-visible change, the validations run, CHANGELOG impact, linked-repo impact, and any out-of-scope issues filed."
    )
    draft_pr_prompt = collapse_spaces(
        f"Create a draft PR in English for {spec['display_name']}. Apply {instruction_ref}. "
        f"{NO_AI_ATTRIBUTION_RULE} "
        f"Keep one topic per branch and follow: {format_bullets(issue_pr)}. "
        "Lead with the failing test, validation, or reproduced defect, summarize the current change and validations already run, and note any linked workspaces or unresolved checks that still need follow-up before marking the PR ready."
    )
    merge_prompt = collapse_spaces(
        f"Before merge for {spec['display_name']}, stop on the first failed check and enforce the current SecPal instructions from {instruction_ref}. "
        f"{NO_AI_ATTRIBUTION_RULE} "
        f"Required validation gate: {format_bullets(validation)}. "
        f"Also enforce: {format_bullets(select_bullets(always_on, ['one topic', 'bypass', 'changelog', 'issue immediately'], 4))}."
    )
    merge_and_push_prompt = collapse_spaces(
        f"Before push and merge for {spec['display_name']}, apply {instruction_ref}. "
        f"{NO_AI_ATTRIBUTION_RULE} "
        f"Run or re-run the touched checks demanded by the repo instructions, then verify: {format_bullets(select_bullets(validation, ['validation', 'lint', 'typecheck', 'build', 'pest', 'preflight', 'changelog', 'issue', 'gpg', 'reuse'], 7))}. "
        "Do not bypass hooks or force operations, and after merge return the repo to the ready state described in the repo instructions."
    )

    return {
        "review_prompt": review_prompt,
        "pr_prompt": pr_prompt,
        "draft_pr_prompt": draft_pr_prompt,
        "merge_prompt": merge_prompt,
        "merge_and_push_prompt": merge_and_push_prompt,
    }


def render_local_config(spec: dict[str, Any]) -> dict[str, Any]:
    config = copy.deepcopy(spec["local_config"])
    config = enrich_local_config(spec["path"].name, spec, config)
    preamble = collapse_spaces(
        f"Apply the current SecPal instructions from {instruction_reference(spec)} before taking action. "
        f"{NO_AI_ATTRIBUTION_RULE}"
    )
    for task in config.get("tasks", []):
        task["prompt"] = collapse_spaces(f"{preamble} {task['prompt']}")
    return config


def prefix_first_line(prefix: str, text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return prefix

    lines[0] = prefix + lines[0]
    return "\n".join(lines)


def render_pretty_json(value: Any, indent: int = 0, first_line_prefix_len: int = 0) -> str:
    current_indent = "  " * indent
    next_indent = "  " * (indent + 1)

    if isinstance(value, dict):
        if not value:
            return "{}"

        items = list(value.items())
        lines: list[str] = []
        for index, (key, nested_value) in enumerate(items):
            key_prefix = f"{json.dumps(key)}: "
            rendered_value = render_pretty_json(nested_value, indent + 1, len(key_prefix))
            line = prefix_first_line(f"{next_indent}{key_prefix}", rendered_value)
            if index < len(items) - 1:
                line += ","
            lines.append(line)

        return "{\n" + "\n".join(lines) + f"\n{current_indent}" + "}"

    if isinstance(value, list):
        if not value:
            return "[]"

        rendered_items = [render_pretty_json(item, indent + 1) for item in value]
        inline_candidate = "[" + ", ".join(rendered_items) + "]"
        if all("\n" not in item for item in rendered_items) and len(current_indent) + first_line_prefix_len + len(inline_candidate) <= 80:
            return inline_candidate

        lines: list[str] = []
        for index, rendered_item in enumerate(rendered_items):
            line = prefix_first_line(next_indent, rendered_item)
            if index < len(rendered_items) - 1:
                line += ","
            lines.append(line)

        return "[\n" + "\n".join(lines) + f"\n{current_indent}" + "]"

    return json.dumps(value)


def load_package_scripts(repo_path: pathlib.Path) -> set[str]:
    package_json_path = repo_path / "package.json"
    if not package_json_path.exists():
        return set()

    raw_text = package_json_path.read_text()
    try:
        package_data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid package.json for rollout validation ({package_json_path}): {error}") from error

    scripts = package_data.get("scripts", {})
    if not isinstance(scripts, dict):
        raise SystemExit(f"invalid package.json for rollout validation ({package_json_path}): scripts must be an object")

    return {str(script_name) for script_name in scripts}


def load_composer_scripts(repo_path: pathlib.Path) -> set[str]:
    composer_json_path = repo_path / "composer.json"
    if not composer_json_path.exists():
        return set()

    raw_text = composer_json_path.read_text()
    try:
        composer_data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid composer.json for rollout validation ({composer_json_path}): {error}") from error

    scripts = composer_data.get("scripts", {})
    if not isinstance(scripts, dict):
        raise SystemExit(f"invalid composer.json for rollout validation ({composer_json_path}): scripts must be an object")

    return {str(script_name) for script_name in scripts}


def validate_local_config_command(
    repo_name: str,
    repo_path: pathlib.Path,
    package_scripts: set[str],
    composer_scripts: set[str],
    command: str,
) -> None:
    package_json_path = repo_path / "package.json"
    package_lock_path = repo_path / "package-lock.json"
    composer_json_path = repo_path / "composer.json"
    artisan_path = repo_path / "artisan"

    if re.search(r"\bcomposer\s+(?:install|run(?:-script)?)\b", command) and not composer_json_path.exists():
        raise SystemExit(f"{repo_name} polyscope config references composer without a composer.json at the repo root")

    if re.search(r"\bphp\s+artisan\b", command) and not artisan_path.exists():
        raise SystemExit(f"{repo_name} polyscope config references artisan without an artisan file at the repo root")

    references_npm = any(
        re.search(pattern, command)
        for pattern in (r"\bnpm\s+ci\b", r"\bnpm\s+install\b", r"\bnpm\s+run\b", r"\bnpx\b")
    )
    if references_npm and not package_json_path.exists():
        raise SystemExit(f"{repo_name} polyscope config references npm without a package.json at the repo root")

    if re.search(r"\bnpm\s+ci\b", command) and not package_lock_path.exists():
        raise SystemExit(f"{repo_name} polyscope config references npm ci without a package-lock.json at the repo root")

    for script_name in re.findall(r"\bnpm\s+run\s+([A-Za-z0-9:_-]+)\b", command):
        if script_name not in package_scripts:
            raise SystemExit(f"{repo_name} polyscope config references missing npm script '{script_name}'")

    for script_name in re.findall(r"\bcomposer\s+(?:run|run-script)\s+([A-Za-z0-9:_-]+)\b", command):
        if script_name not in composer_scripts:
            raise SystemExit(f"{repo_name} polyscope config references missing composer script '{script_name}'")

    try:
        tokens = shlex.split(command)
    except ValueError as error:
        raise SystemExit(f"{repo_name} polyscope config command could not be parsed: {command}: {error}") from error

    relative_path_token: str | None = None
    if tokens:
        if tokens[0].startswith("./"):
            relative_path_token = tokens[0]
        elif len(tokens) > 1 and tokens[0] in {"bash", "node", "php", "python", "python3"} and tokens[1].startswith("./"):
            relative_path_token = tokens[1]

    if relative_path_token is not None:
        suffix = relative_path_token[2:]
        if not suffix or suffix.startswith("/"):
            raise SystemExit(f"{repo_name} polyscope config has invalid relative path '{relative_path_token}'")
        candidate = (repo_path / suffix).resolve()
        anchor = repo_path.resolve()
        try:
            candidate.relative_to(anchor)
        except ValueError:
            raise SystemExit(
                f"{repo_name} polyscope config references relative path outside repo root: '{relative_path_token}'"
            )
        if not candidate.exists():
            raise SystemExit(f"{repo_name} polyscope config references missing relative path '{relative_path_token}'")


def validate_repo_local_configs(repo_specs: dict[str, dict[str, Any]]) -> None:
    for repo_name, spec in repo_specs.items():
        repo_path = pathlib.Path(spec["path"])
        config = render_local_config(spec)
        package_scripts = load_package_scripts(repo_path)
        composer_scripts = load_composer_scripts(repo_path)

        for command in config.get("scripts", {}).get("setup", []):
            validate_local_config_command(repo_name, repo_path, package_scripts, composer_scripts, command)

        for item in config.get("scripts", {}).get("run", []):
            command = item.get("command")
            if isinstance(command, str):
                validate_local_config_command(repo_name, repo_path, package_scripts, composer_scripts, command)


def is_provisionable_worktree(
    repo_name: str,
    worktree_path: pathlib.Path,
    validation_commands: list[str],
    *,
    log_skip_reason: bool = True,
) -> bool:
    def skip(reason: str) -> bool:
        if log_skip_reason:
            print(f"Skipping {repo_name} worktree {worktree_path.name} at {worktree_path}: {reason}")
        return False

    try:
        git_dir = resolve_git_dir(worktree_path)
        if not git_dir.is_dir():
            return skip("missing .git")
    except SystemExit:
        return skip("invalid .git pointer")

    if repo_name == "android":
        android_project_dir = worktree_path / "android"
        if not android_project_dir.is_dir():
            return skip("missing committed android/ project directory")
        if not (android_project_dir / "settings.gradle").is_file():
            return skip("missing committed native Android Gradle project")

    copilot_instructions_rel = REPO_SETTINGS[repo_name]["copilot_instructions"]
    copilot_instructions_path = worktree_path / copilot_instructions_rel
    if not copilot_instructions_path.is_file():
        return skip(f"missing required repo file {copilot_instructions_rel}")

    package_scripts = load_package_scripts(worktree_path)
    composer_scripts = load_composer_scripts(worktree_path)
    try:
        for command in validation_commands:
            validate_local_config_command(repo_name, worktree_path, package_scripts, composer_scripts, command)
    except SystemExit as error:
        return skip(str(error))

    return True


def resolve_git_dir(repo_path: pathlib.Path) -> pathlib.Path:
    git_path = repo_path / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        pointer = git_path.read_text().strip()
        prefix = "gitdir: "
        if not pointer.startswith(prefix):
            raise SystemExit(f"invalid .git pointer in {repo_path}: {pointer}")
        git_dir = pathlib.Path(pointer[len(prefix) :])
        if not git_dir.is_absolute():
            git_dir = (repo_path / git_dir).resolve()
        return git_dir
    return git_path


def ensure_exclude(repo_path: pathlib.Path, entries: set[str] | None = None) -> None:
    exclude_path = resolve_git_dir(repo_path) / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text() if exclude_path.exists() else ""
    desired_entries = entries or {POLYSCOPE_LOCAL_CONFIG_NAME}
    existing_entries = {line.strip() for line in existing.splitlines()}
    missing_entries = [entry for entry in sorted(desired_entries) if entry not in existing_entries]
    if missing_entries:
        with exclude_path.open("a") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            for entry in missing_entries:
                handle.write(f"{entry}\n")


def write_local_configs(repo_specs: dict[str, dict[str, Any]]) -> None:
    for repo_name, spec in repo_specs.items():
        repo_path = pathlib.Path(spec["path"])
        config_path = repo_path / POLYSCOPE_LOCAL_CONFIG_NAME
        config_path.write_text(render_pretty_json(render_local_config(spec)) + "\n")
        sync_repo_auxiliary_files(repo_name, repo_path)
        ensure_exclude(repo_path)


def render_local_configs(repo_specs: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        repo_name: render_pretty_json(render_local_config(spec)) + "\n"
        for repo_name, spec in repo_specs.items()
    }


def render_worktree_local_config(
    spec: dict[str, Any],
    worktree_path: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> str:
    config = render_local_config(spec)
    preview = config.get("preview")
    if isinstance(preview, dict) and "url" in preview:
        workspace = resolve_current_workspace_name(worktree_path, db_path=db_path)
        preview_prefix = spec.get("preview_prefix")
        if isinstance(preview_prefix, str) and preview_prefix:
            preview["url"] = f"https://{preview_prefix}-{workspace}.preview.secpal.dev"
        else:
            preview["url"] = f"https://{workspace}.preview.secpal.dev"
    return render_pretty_json(config) + "\n"


def collect_setup_inputs(worktree_path: pathlib.Path, setup_commands: list[str]) -> dict[str, str]:
    inputs: dict[str, str] = {}
    command_text = "\n".join(setup_commands)

    candidate_paths: list[pathlib.Path] = []
    if re.search(r"\bnpm\s+(?:ci|install|run)\b|\bnpx\b", command_text):
        candidate_paths.extend([worktree_path / "package.json", worktree_path / "package-lock.json"])

    if re.search(r"\bcomposer\s+(?:install|run(?:-script)?)\b", command_text):
        candidate_paths.extend([worktree_path / "composer.json", worktree_path / "composer.lock"])

    for path in candidate_paths:
        if path.is_file():
            inputs[path.name] = path.read_text()

    return inputs


def build_setup_hash(
    worktree_path: pathlib.Path,
    setup_commands: list[str],
    *,
    db_path: pathlib.Path | None = None,
    linked_context: dict[str, str] | None = None,
) -> str:
    payload = {
        "commands": setup_commands,
        "inputs": collect_setup_inputs(worktree_path, setup_commands),
        "workspace": resolve_current_workspace_name(worktree_path, db_path=db_path),
    }
    if linked_context is None:
        linked_context = collect_linked_setup_context(worktree_path, db_path=db_path)
    if linked_context:
        payload["linked_workspaces"] = linked_context

    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_provision_marker(marker_path: pathlib.Path) -> dict[str, Any] | None:
    if not marker_path.exists():
        return None

    try:
        marker = json.loads(marker_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(marker, dict):
        return None
    return marker


def run_setup_commands(worktree_path: pathlib.Path, commands: list[str], *, db_path: pathlib.Path | None = None) -> None:
    env = os.environ.copy()
    if db_path is not None:
        env["POLYSCOPE_DB_PATH"] = str(db_path)

    for command in commands:
        subprocess.run(
            ["bash", "-c", f"set -euo pipefail; {command}"],
            cwd=worktree_path,
            env=env,
            check=True,
        )


def sync_worktree_local_config(worktree_path: pathlib.Path, config_text: str) -> None:
    (worktree_path / POLYSCOPE_LOCAL_CONFIG_NAME).write_text(config_text)
    ensure_exclude(worktree_path, {POLYSCOPE_LOCAL_CONFIG_NAME, PROVISION_MARKER_FILENAME})


def normalize_registered_workspace_path(
    worktree_path: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> None:
    resolved_db_path = db_path or default_polyscope_db_path()
    if not resolved_db_path.exists():
        return

    normalized_path = worktree_path.parent / resolve_current_workspace_name(worktree_path, db_path=resolved_db_path)
    if normalized_path == worktree_path:
        return

    if normalized_path.exists() and not normalized_path.is_symlink():
        return

    if normalized_path.is_symlink():
        try:
            if normalized_path.resolve() != worktree_path.resolve():
                return
        except OSError:
            return

    try:
        with sqlite3.connect(resolved_db_path) as connection:
            current_worktree = find_current_worktree_record(connection, worktree_path)
            if current_worktree is None:
                return

            worktree_id = current_worktree[0]
            connection.execute(
                """
                update worktrees
                set path = ?
                where id = ?
                """,
                (str(normalized_path), worktree_id),
            )
            connection.commit()
    except sqlite3.Error:
        return

    if not normalized_path.exists():
        normalized_path.symlink_to(worktree_path.name)


def ensure_workspace_alias(worktree_path: pathlib.Path, *, db_path: pathlib.Path | None = None) -> None:
    workspace = resolve_current_workspace_name(worktree_path, db_path=db_path)
    if workspace == worktree_path.name:
        return

    alias_path = worktree_path.parent / workspace
    if alias_path == worktree_path:
        return

    if alias_path.is_symlink():
        try:
            if alias_path.resolve() == worktree_path.resolve():
                return
        except OSError:
            # Broken or inaccessible symlinks are recreated below.
            # Intentionally fall through to unlink + re-create the alias.
            pass
        alias_path.unlink()
    elif alias_path.exists():
        raise RuntimeError(
            f"workspace alias path {alias_path} already exists and does not point to {worktree_path}"
        )

    alias_path.symlink_to(worktree_path.name)


def sync_worktree_auxiliary_files(repo_name: str, worktree_path: pathlib.Path) -> None:
    sync_repo_auxiliary_files(repo_name, worktree_path)


def resolve_executable(command: str) -> str | None:
    executable = shutil.which(command)
    if executable is not None:
        return executable

    user_local_candidate = pathlib.Path.home() / ".local" / "bin" / command
    if user_local_candidate.is_file() and os.access(user_local_candidate, os.X_OK):
        return str(user_local_candidate)

    return None


def ensure_pre_commit_hook(worktree_path: pathlib.Path) -> None:
    if not (worktree_path / ".pre-commit-config.yaml").exists():
        return

    hook_path = resolve_git_dir(worktree_path) / "hooks" / "pre-commit"
    if hook_path.exists() or hook_path.is_symlink():
        return

    pre_commit = resolve_executable("pre-commit")
    if pre_commit is None:
        raise SystemExit(f"pre-commit is required to provision hooks for {worktree_path}")

    subprocess.run(
        [pre_commit, "install", "--install-hooks", "--hook-type", "pre-commit"],
        cwd=worktree_path,
        check=True,
    )


def ensure_pre_push_hook(worktree_path: pathlib.Path) -> None:
    preflight_script = worktree_path / "scripts" / "preflight.sh"
    if not preflight_script.exists():
        return

    hooks_dir = resolve_git_dir(worktree_path) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "pre-push"
    target = pathlib.Path(os.path.relpath(preflight_script, hooks_dir))

    if hook_path.is_symlink():
        if pathlib.Path(os.readlink(hook_path)) == target:
            return
        hook_path.unlink()
    elif hook_path.exists():
        hook_path.replace(hook_path.with_name("pre-push.backup"))

    hook_path.symlink_to(target)


def ensure_commit_msg_hook(worktree_path: pathlib.Path) -> None:
    strip_script = pathlib.Path(__file__).parent / "strip-ai-trailers.sh"
    if not strip_script.exists():
        return

    hooks_dir = resolve_git_dir(worktree_path) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "commit-msg"
    target = pathlib.Path(os.path.relpath(strip_script, hooks_dir))

    if hook_path.is_symlink():
        if pathlib.Path(os.readlink(hook_path)) == target:
            return
        hook_path.unlink()
    elif hook_path.exists():
        hook_path.replace(hook_path.with_name("commit-msg.backup"))

    hook_path.symlink_to(target)


def ensure_worktree_hooks(worktree_path: pathlib.Path) -> None:
    ensure_pre_commit_hook(worktree_path)
    ensure_pre_push_hook(worktree_path)
    ensure_commit_msg_hook(worktree_path)


def provision_worktrees(
    repo_state: dict[str, dict[str, Any]],
    repo_specs: dict[str, dict[str, Any]],
    clone_root: pathlib.Path,
    *,
    db_path: pathlib.Path | None = None,
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    provisioned_worktrees: list[str] = []
    cleaned_preview_storage_targets = cleanup_removed_api_preview_databases(
        repo_state,
        repo_specs,
        clone_root,
        db_path=db_path,
    )
    failed_provision_worktrees: list[dict[str, str]] = []

    for repo_name, spec in repo_specs.items():
        repo_clone_root = clone_root / repo_state[repo_name]["id"]
        if not repo_clone_root.exists():
            continue

        local_config = render_local_config(spec)
        validation_commands = local_config.get("scripts", {}).get("setup", [])
        setup_commands = validation_commands
        if repo_name == "api":
            setup_commands = setup_commands[1:]

        for worktree_path in sorted(path for path in repo_clone_root.iterdir() if path.is_dir() and not path.is_symlink()):
            try:
                if not is_provisionable_worktree(repo_name, worktree_path, validation_commands):
                    continue

                normalize_registered_workspace_path(worktree_path, db_path=db_path)
                config_text = render_worktree_local_config(spec, worktree_path, db_path=db_path)
                sync_worktree_local_config(worktree_path, config_text)
                ensure_workspace_alias(worktree_path, db_path=db_path)
                sync_worktree_auxiliary_files(repo_name, worktree_path)
                ensure_worktree_hooks(worktree_path)
                linked_setup_context = collect_linked_setup_context(worktree_path, db_path=db_path)
                workspace = resolve_current_workspace_name(worktree_path, db_path=db_path)
                setup_hash = build_setup_hash(
                    worktree_path,
                    setup_commands,
                    db_path=db_path,
                    linked_context=linked_setup_context,
                )

                preview_storage_target: str | None = None
                if repo_name == "api":
                    ready, preview_storage_target = ensure_api_worktree_ready(worktree_path, spec["path"], db_path=db_path)
                    if not ready:
                        continue

                marker_path = worktree_path / PROVISION_MARKER_FILENAME
                marker = load_provision_marker(marker_path)
                if marker is not None and marker.get("setup_hash") == setup_hash:
                    if repo_name != "api" or marker.get("preview_storage_target") == preview_storage_target:
                        continue

                if setup_commands:
                    print(f"Provisioning {repo_name} worktree {worktree_path.name} at {worktree_path}")
                    run_setup_commands(worktree_path, setup_commands, db_path=db_path)

                marker_payload: dict[str, Any] = {
                    "repo": repo_name,
                    "workspace": workspace,
                    "physical_workspace": worktree_path.name,
                    "setup_hash": setup_hash,
                    "provisioned_at": datetime.now(timezone.utc).isoformat(),
                }
                if repo_name == "api" and preview_storage_target is not None:
                    marker_payload["preview_storage_target"] = preview_storage_target
                if linked_setup_context:
                    marker_payload["linked_workspaces"] = linked_setup_context

                marker_path.write_text(json.dumps(marker_payload, indent=2) + "\n")
                provisioned_worktrees.append(f"{repo_name}:{workspace}")
            except (OSError, RuntimeError, subprocess.CalledProcessError, SystemExit) as error:
                error_message = str(error)
                print(
                    f"Failed to provision {repo_name} worktree {worktree_path.name} at {worktree_path}: {error_message}",
                    file=sys.stderr,
                )
                failed_provision_worktrees.append(
                    {
                        "repo": repo_name,
                        "workspace": worktree_path.name,
                        "path": str(worktree_path),
                        "error": error_message,
                    }
                )

    return provisioned_worktrees, cleaned_preview_storage_targets, failed_provision_worktrees


def request_json(api_base: str, path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    payload = None
    headers: dict[str, str] = {}
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(api_base + path, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def load_repo_state(repo_state_file: pathlib.Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(repo_state_file.read_text())
    result: dict[str, dict[str, Any]] = {}
    for name in REPO_SETTINGS:
        if name not in raw:
            raise SystemExit(f"repo-state file is missing entry for '{name}'; regenerate it by running without --repo-state-file")
        entry = raw[name]
        for field in ("id", "path"):
            if field not in entry:
                raise SystemExit(f"repo-state entry for '{name}' is missing required field '{field}'")
        result[name] = entry
    return result


def ensure_repositories_registered(api_base: str, repo_specs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    repos = request_json(api_base, "/repos")
    by_path = {repo["path"]: repo for repo in repos}
    state: dict[str, dict[str, Any]] = {}

    for repo_name, spec in repo_specs.items():
        repo_path = str(spec["path"])
        repo = by_path.get(repo_path)
        if repo is None:
            request_json(
                api_base,
                "/repos",
                method="POST",
                body={"name": spec["display_name"], "path": repo_path, "base_branch": spec["base_branch"]},
            )
            repos = request_json(api_base, "/repos")
            by_path = {entry["path"]: entry for entry in repos}
            repo = by_path[repo_path]
        state[repo_name] = repo

    return state


def backup_db(db_path: pathlib.Path) -> pathlib.Path:
    ensure_polyscope_db_exists(db_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.parent / f"{db_path.name}.backup-{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def ensure_polyscope_db_exists(db_path: pathlib.Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"Polyscope DB not found at {db_path}; start Polyscope at least once so the DB is created before running this script")


def build_desired_repository_metadata(
    repo_state: dict[str, dict[str, Any]], repo_specs: dict[str, dict[str, Any]]
) -> tuple[set[tuple[str, str]], dict[str, tuple[str, str, str, str, str]]]:
    desired_links: set[tuple[str, str]] = set()
    desired_prompts: dict[str, tuple[str, str, str, str, str]] = {}

    for repo_name, spec in repo_specs.items():
        repo_id = repo_state[repo_name]["id"]
        for linked_name in spec["link_names"]:
            desired_links.add((repo_id, repo_state[linked_name]["id"]))

        prompts = build_prompt_bundle(spec)
        desired_prompts[repo_id] = (
            prompts["review_prompt"],
            prompts["pr_prompt"],
            prompts["draft_pr_prompt"],
            prompts["merge_prompt"],
            prompts["merge_and_push_prompt"],
        )

    return desired_links, desired_prompts


def read_current_repository_metadata(
    conn: sqlite3.Connection, managed_repo_ids: list[str]
) -> tuple[set[tuple[str, str]], dict[str, tuple[str, str, str, str, str]]]:
    cur = conn.cursor()
    placeholders = ", ".join("?" for _ in managed_repo_ids)
    current_links = set(
        cur.execute(
            f"select repo_id, linked_repo_id from repository_links where repo_id in ({placeholders}) or linked_repo_id in ({placeholders})",
            managed_repo_ids + managed_repo_ids,
        ).fetchall()
    )
    current_prompts = {
        row[0]: row[1:]
        for row in cur.execute(
            f"select id, review_prompt, pr_prompt, draft_pr_prompt, merge_prompt, merge_and_push_prompt from repositories where id in ({placeholders})",
            managed_repo_ids,
        ).fetchall()
    }
    return current_links, current_prompts


def sync_repository_metadata(
    db_path: pathlib.Path, repo_state: dict[str, dict[str, Any]], repo_specs: dict[str, dict[str, Any]]
) -> pathlib.Path | None:
    managed_repo_ids = [repo_state[name]["id"] for name in REPO_SETTINGS]
    desired_links, desired_prompts = build_desired_repository_metadata(repo_state, repo_specs)
    ensure_polyscope_db_exists(db_path)

    conn = sqlite3.connect(db_path)
    current_links, current_prompts = read_current_repository_metadata(conn, managed_repo_ids)
    conn.close()

    if current_links == desired_links and current_prompts == desired_prompts:
        return None

    backup_path = backup_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    placeholders = ", ".join("?" for _ in managed_repo_ids)
    cur.execute(
        f"delete from repository_links where repo_id in ({placeholders}) or linked_repo_id in ({placeholders})",
        managed_repo_ids + managed_repo_ids,
    )

    for repo_name, spec in repo_specs.items():
        repo_id = repo_state[repo_name]["id"]
        for linked_name in spec["link_names"]:
            cur.execute(
                "insert or replace into repository_links (repo_id, linked_repo_id) values (?, ?)",
                (repo_id, repo_state[linked_name]["id"]),
            )

        prompt_values = desired_prompts[repo_id]
        cur.execute(
            """
            update repositories
            set review_prompt = ?,
                pr_prompt = ?,
                draft_pr_prompt = ?,
                merge_prompt = ?,
                merge_and_push_prompt = ?
            where id = ?
            """,
            (*prompt_values, repo_id),
        )

    conn.commit()
    conn.close()
    return backup_path


def parse_nginx_version(version_output: str) -> tuple[int, int, int] | None:
    match = re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", version_output)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def select_nginx_http2_syntax(nginx_version: tuple[int, int, int]) -> str:
    if nginx_version >= MODERN_NGINX_HTTP2_VERSION:
        return "modern"
    return "legacy"


def detect_nginx_http2_syntax() -> str:
    nginx_bin = shutil.which("nginx") or "/usr/sbin/nginx"
    result = subprocess.run([nginx_bin, "-v"], check=True, capture_output=True, text=True)
    nginx_version = parse_nginx_version(result.stdout + result.stderr)
    if nginx_version is None:
        raise RuntimeError("could not parse nginx version from `nginx -v` output")
    return select_nginx_http2_syntax(nginx_version)


def render_nginx_config(repo_state: dict[str, dict[str, Any]], nginx_http2_syntax: str = "modern") -> str:
    if nginx_http2_syntax not in {"modern", "legacy"}:
        raise ValueError(f"unsupported nginx HTTP/2 syntax: {nginx_http2_syntax}")
    api_id = repo_state["api"]["id"]
    frontend_id = repo_state["frontend"]["id"]
    guardguide_id = repo_state["GuardGuide"]["id"]
    secpal_app_id = repo_state["secpal.app"]["id"]
    guardguide_de_id = repo_state["guardguide.de"]["id"]
    changelog_id = repo_state["changelog"]["id"]
    http2_listen_suffix = "" if nginx_http2_syntax == "modern" else " http2"
    http2_directive = "\n            http2 on;" if nginx_http2_syntax == "modern" else ""
    # NOTE: workspace names starting with api-, frontend-, guardguide-, guardguide-de-, secpal-app-, or changelog- are
    # reserved for legacy per-repo routing (e.g. api-WORKSPACE.preview.secpal.dev).
    # Generic workspaces must not use those prefixes; the regex will treat them as legacy
    # hosts and route them to the wrong backend.
    # `http2 on;` requires nginx >= 1.25.1, so install mode version-gates this render option.
    return textwrap.dedent(
        f"""
        server {{
            listen 80;
            listen [::]:80;
            server_name ~^(?:(?<repo>api|frontend|guardguide-de|guardguide|secpal-app|changelog)-)?(?<workspace>[a-z0-9][a-z0-9-]*)\\.preview\\.secpal\\.dev$;

            location /.well-known/acme-challenge/ {{
                root /var/www/certbot;
            }}

            return 301 https://$host$request_uri;
        }}

        server {{
            listen 443 ssl{http2_listen_suffix};
            listen [::]:443 ssl{http2_listen_suffix};{http2_directive}
            server_name ~^(?:(?<repo>api|frontend|guardguide-de|guardguide|secpal-app|changelog)-)?(?<workspace>[a-z0-9][a-z0-9-]*)\\.preview\\.secpal\\.dev$;  # same reserved-prefix rule

            access_log /var/log/nginx/preview.secpal.dev.access.log;
            error_log /var/log/nginx/preview.secpal.dev.error.log;

            client_max_body_size 25m;
            index index.html index.php;

            ssl_certificate /etc/letsencrypt/live/preview.secpal.dev/fullchain.pem;
            ssl_certificate_key /etc/letsencrypt/live/preview.secpal.dev/privkey.pem;
            include /etc/letsencrypt/options-ssl-nginx.conf;
            ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

            set $api_root /home/secpal/.polyscope/clones/{api_id}/$workspace;
            set $api_public $api_root/public;
            set $frontend_root /home/secpal/.polyscope/clones/{frontend_id}/$workspace;
            set $frontend_dist $frontend_root/dist;
            set $guardguide_root /home/secpal/.polyscope/clones/{guardguide_id}/$workspace;
            set $guardguide_public $guardguide_root/public;
            set $secpal_app_root /home/secpal/.polyscope/clones/{secpal_app_id}/$workspace;
            set $secpal_app_dist $secpal_app_root/dist;
            set $guardguide_de_root /home/secpal/.polyscope/clones/{guardguide_de_id}/$workspace;
            set $guardguide_de_dist $guardguide_de_root/dist;
            set $changelog_root /home/secpal/.polyscope/clones/{changelog_id}/$workspace;
            set $changelog_out $changelog_root/out;
            set $preview_docroot /home/secpal/.polyscope/__missing_preview_docroot__;
            set $php_root $api_public;
            set $route_mode static;
            set $preview_relaxed_csp "default-src 'self'; base-uri 'self'; connect-src 'self' https:; font-src 'self' data:; form-action 'self'; frame-ancestors 'none'; frame-src 'none'; img-src 'self' data: blob:; manifest-src 'self'; media-src 'self'; object-src 'none'; script-src 'self' 'unsafe-inline'; script-src-attr 'none'; style-src 'self' 'unsafe-inline'; style-src-elem 'self' 'unsafe-inline'; style-src-attr 'unsafe-inline'; worker-src 'self'; upgrade-insecure-requests";
            set $secpal_csp $preview_relaxed_csp;
            set $secpal_permissions_policy "accelerometer=(), autoplay=(), camera=(), clipboard-read=(), clipboard-write=(), display-capture=(), fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()";

            if (-f $api_public/index.php) {{
                set $preview_docroot $api_public;
                set $route_mode api;
            }}

            if (-f $frontend_dist/index.html) {{
                set $preview_docroot $frontend_dist;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if (-f $secpal_app_dist/index.html) {{
                set $preview_docroot $secpal_app_dist;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if (-f $guardguide_de_dist/index.html) {{
                set $preview_docroot $guardguide_de_dist;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if (-f $changelog_out/index.html) {{
                set $preview_docroot $changelog_out;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if ($repo = changelog) {{
                set $preview_docroot $changelog_out;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if ($repo = secpal-app) {{
                set $preview_docroot $secpal_app_dist;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if ($repo = guardguide-de) {{
                set $preview_docroot $guardguide_de_dist;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if ($repo = frontend) {{
                set $preview_docroot $frontend_dist;
                set $route_mode static;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if ($repo = guardguide) {{
                set $preview_docroot $guardguide_public;
                set $php_root $guardguide_public;
                set $route_mode api;
                set $secpal_csp $preview_relaxed_csp;
            }}

            if ($repo = api) {{
                set $preview_docroot $api_public;
                set $php_root $api_public;
                set $route_mode api;
                set $secpal_csp $preview_relaxed_csp;
            }}

            root $preview_docroot;

            add_header Content-Security-Policy $secpal_csp always;
            add_header Permissions-Policy $secpal_permissions_policy always;
            add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
            add_header X-Content-Type-Options "nosniff" always;
            add_header X-XSS-Protection "0" always;
            add_header X-Frame-Options "DENY" always;
            add_header Referrer-Policy "strict-origin-when-cross-origin" always;
            add_header Cross-Origin-Opener-Policy "same-origin" always;
            add_header Cross-Origin-Resource-Policy "same-origin" always;
            add_header Origin-Agent-Cluster "?1" always;
            add_header X-Permitted-Cross-Domain-Policies "none" always;

            location /.well-known/acme-challenge/ {{
                root /var/www/certbot;
            }}

            location ~ /\\.(?!well-known) {{
                deny all;
            }}

            location / {{
                try_files $uri @preview_router;
            }}

            location = / {{
                if ($route_mode = api) {{
                    rewrite ^ /index.php last;
                }}

                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                add_header Cache-Control "no-cache, no-store, must-revalidate" always;
                try_files /index.html =404;
            }}

            location = /index.html {{
                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                add_header Cache-Control "no-cache, no-store, must-revalidate" always;
                try_files $uri =404;
            }}

            location = /sw.js {{
                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                add_header Cache-Control "no-cache, no-store, must-revalidate" always;
                add_header Service-Worker-Allowed "/" always;
                try_files $uri =404;
            }}

            location = /manifest.webmanifest {{
                default_type application/manifest+json;
                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                add_header Cache-Control "no-cache, must-revalidate" always;
                try_files $uri =404;
            }}

            location ^~ /assets/ {{
                try_files $uri =404;
                expires off;
                add_header Cache-Control "no-cache, must-revalidate" always;
                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                if ($uri ~ (?:/\\.|\\.php$)) {{
                    return 404;
                }}
            }}

            location ^~ /_astro/ {{
                try_files $uri =404;
                expires 1y;
                add_header Cache-Control "public, immutable" always;
                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                if ($uri ~ (?:/\\.|\\.php$)) {{
                    return 404;
                }}
            }}

            location ^~ /_next/static/ {{
                try_files $uri =404;
                expires 1y;
                add_header Cache-Control "public, immutable" always;
                add_header Content-Security-Policy $secpal_csp always;
                add_header Permissions-Policy $secpal_permissions_policy always;
                add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-XSS-Protection "0" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "strict-origin-when-cross-origin" always;
                add_header Cross-Origin-Opener-Policy "same-origin" always;
                add_header Cross-Origin-Resource-Policy "same-origin" always;
                add_header Origin-Agent-Cluster "?1" always;
                add_header X-Permitted-Cross-Domain-Policies "none" always;
                if ($uri ~ (?:/\\.|\\.php$)) {{
                    return 404;
                }}
            }}

            location ~* \\.(?:svg|ico|png|jpg|jpeg|webp|avif|woff|woff2|ttf|otf|xml|txt)$ {{
                try_files $uri =404;
                expires 1d;
            }}

            location @preview_router {{
                if ($route_mode = api) {{
                    rewrite ^ /index.php last;
                }}

                try_files $uri/index.html /index.html =404;
            }}

            location = /index.php {{
                if (!-f $php_root/index.php) {{
                    return 404;
                }}

                include snippets/fastcgi-php.conf;
                fastcgi_pass unix:/run/php/php8.4-fpm-secpal-preview.sock;
                fastcgi_buffer_size 32k;
                fastcgi_buffers 16 16k;
                fastcgi_param SCRIPT_FILENAME $php_root/index.php;
                fastcgi_param DOCUMENT_ROOT $php_root;
                fastcgi_param HTTP_HOST $host;
            }}

            location ~ \\.php$ {{
                return 404;
            }}
        }}
        """
    ).strip() + "\n"


def build_summary(
    repo_state: dict[str, dict[str, Any]],
    repo_specs: dict[str, dict[str, Any]],
    db_backup: pathlib.Path | None,
    nginx_output: pathlib.Path,
    provisioned_worktrees: list[str],
    cleaned_preview_storage_targets: list[str],
    failed_provision_worktrees: list[dict[str, str]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "db_backup": str(db_backup) if db_backup is not None else None,
        "rendered_nginx_config": str(nginx_output),
        "provisioned_worktrees": provisioned_worktrees,
        "cleaned_preview_storage_targets": cleaned_preview_storage_targets,
        "failed_provision_worktrees": failed_provision_worktrees,
        "repositories": {},
    }
    for repo_name, spec in repo_specs.items():
        prompts = build_prompt_bundle(spec)
        summary["repositories"][repo_name] = {
            "id": repo_state[repo_name]["id"],
            "path": str(spec["path"]),
            "agent_instructions": str(spec["agent_instructions"]),
            "copilot_instructions": str(spec["copilot_instructions"]),
            "focus_instruction_paths": [str(path) for path in spec["focus_instruction_paths"]],
            "linked_repositories": spec["link_names"],
            "preview_prefix": spec["preview_prefix"],
            "review_prompt_excerpt": prompts["review_prompt"][:280],
        }
    return summary


def install_nginx_config(
    nginx_output: pathlib.Path,
    *,
    target: pathlib.Path = pathlib.Path("/etc/nginx/sites-available/preview.secpal.dev"),
    sudo_bin: str | None = None,
    nginx_bin: str = "nginx",
    systemctl_bin: str = "systemctl",
) -> None:
    sudo_bin = sudo_bin or os.environ.get("POLYSCOPE_SUDO_BIN", "sudo")

    def sudo_command(*command: str) -> list[str]:
        if os.geteuid() == 0:
            return list(command)
        return [sudo_bin, "-n", *command]

    target_exists = subprocess.run(
        sudo_command("test", "-f", str(target)),
        check=False,
    ).returncode == 0
    if target_exists:
        unchanged = subprocess.run(
            sudo_command("cmp", "-s", str(nginx_output), str(target)),
            check=False,
        ).returncode == 0
        if unchanged:
            return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_target = target.with_name(f"{target.name}.bak-{timestamp}")
    if target_exists:
        subprocess.run(sudo_command("cp", str(target), str(backup_target)), check=True)

    def restore_previous_config() -> None:
        if target_exists:
            subprocess.run(sudo_command("cp", str(backup_target), str(target)), check=True)
        else:
            subprocess.run(sudo_command("rm", "-f", str(target)), check=True)

    subprocess.run(sudo_command("install", "-m", "644", str(nginx_output), str(target)), check=True)
    try:
        subprocess.run(sudo_command(nginx_bin, "-t"), check=True)
    except subprocess.CalledProcessError:
        restore_previous_config()
        subprocess.run(sudo_command(nginx_bin, "-t"), check=True)
        raise

    try:
        subprocess.run(sudo_command(systemctl_bin, "reload", "nginx"), check=True)
    except subprocess.CalledProcessError:
        restore_previous_config()
        subprocess.run(sudo_command(nginx_bin, "-t"), check=True)
        subprocess.run(sudo_command(systemctl_bin, "reload", "nginx"), check=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync SecPal Polyscope prompts, links, and preview config.")
    parser.add_argument("--prepare-api-worktree", type=pathlib.Path)
    parser.add_argument("--bootstrap-api-worktree", type=pathlib.Path)
    parser.add_argument("--refresh-api-worktree", type=pathlib.Path)
    parser.add_argument("--run-api-worktree", type=pathlib.Path)
    parser.add_argument("--source-repo-path", type=pathlib.Path)
    parser.add_argument("--shell-command")
    parser.add_argument("--workspace-root", type=pathlib.Path, default=pathlib.Path.home() / "code" / "SecPal")
    parser.add_argument("--db-path", type=pathlib.Path, default=default_polyscope_db_path())
    parser.add_argument("--clone-root", type=pathlib.Path, default=pathlib.Path.home() / ".polyscope" / "clones")
    parser.add_argument("--polyscope-api-base", default="http://127.0.0.1:4321/api")
    parser.add_argument("--repo-state-file", type=pathlib.Path)
    parser.add_argument(
        "--nginx-output",
        type=pathlib.Path,
        default=pathlib.Path.home() / "polyscope-preview-secpal-dev.nginx.conf",
    )
    parser.add_argument(
        "--nginx-http2-syntax",
        choices=NGINX_HTTP2_SYNTAX_CHOICES,
        default="modern",
        help="HTTP/2 syntax for rendered nginx config; install mode always auto-detects the host-safe syntax.",
    )
    parser.add_argument("--summary-output", type=pathlib.Path)
    parser.add_argument("--skip-local-configs", action="store_true")
    parser.add_argument("--skip-db-sync", action="store_true")
    parser.add_argument("--install-nginx", action="store_true")
    parser.add_argument("--provision-worktrees", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.prepare_api_worktree is not None:
        if args.source_repo_path is None:
            raise SystemExit("--source-repo-path is required with --prepare-api-worktree")
        ready, _preview_storage_target = ensure_api_worktree_ready(
            args.prepare_api_worktree,
            args.source_repo_path,
            db_path=args.db_path,
        )
        return 0 if ready else 1

    if args.bootstrap_api_worktree is not None:
        if args.source_repo_path is None:
            raise SystemExit("--source-repo-path is required with --bootstrap-api-worktree")
        ready, _preview_storage_target = bootstrap_api_worktree(
            args.bootstrap_api_worktree,
            args.source_repo_path,
            db_path=args.db_path,
        )
        return 0 if ready else 1

    if args.refresh_api_worktree is not None:
        if args.source_repo_path is None:
            raise SystemExit("--source-repo-path is required with --refresh-api-worktree")
        ready, _preview_storage_target = refresh_api_worktree(
            args.refresh_api_worktree,
            args.source_repo_path,
            db_path=args.db_path,
        )
        return 0 if ready else 1

    if args.run_api_worktree is not None:
        if args.source_repo_path is None:
            raise SystemExit("--source-repo-path is required with --run-api-worktree")
        if not args.shell_command:
            raise SystemExit("--shell-command is required with --run-api-worktree")
        run_api_worktree_shell_command(
            args.run_api_worktree,
            args.source_repo_path,
            args.shell_command,
            db_path=args.db_path,
        )
        return 0

    repo_specs = build_repo_specs(args.workspace_root)

    validate_repo_local_configs(repo_specs)
    write_copilot_compat_instructions(repo_specs)

    if not args.skip_local_configs:
        write_local_configs(repo_specs)

    if args.repo_state_file is not None:
        repo_state = load_repo_state(args.repo_state_file)
    else:
        repo_state = ensure_repositories_registered(args.polyscope_api_base, repo_specs)

    db_backup: pathlib.Path | None = None
    if not args.skip_db_sync:
        db_backup = sync_repository_metadata(args.db_path, repo_state, repo_specs)

    nginx_http2_syntax = args.nginx_http2_syntax
    if args.install_nginx or nginx_http2_syntax == "auto":
        nginx_http2_syntax = detect_nginx_http2_syntax()

    args.nginx_output.write_text(render_nginx_config(repo_state, nginx_http2_syntax=nginx_http2_syntax))

    if args.install_nginx:
        install_nginx_config(args.nginx_output)

    provisioned_worktrees: list[str] = []
    cleaned_preview_storage_targets: list[str] = []
    failed_provision_worktrees: list[dict[str, str]] = []
    if args.provision_worktrees:
        provisioned_worktrees, cleaned_preview_storage_targets, failed_provision_worktrees = provision_worktrees(
            repo_state,
            repo_specs,
            args.clone_root,
            db_path=args.db_path,
        )

    summary = build_summary(
        repo_state,
        repo_specs,
        db_backup,
        args.nginx_output,
        provisioned_worktrees,
        cleaned_preview_storage_targets,
        failed_provision_worktrees,
    )
    if args.summary_output is not None:
        args.summary_output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if failed_provision_worktrees:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
