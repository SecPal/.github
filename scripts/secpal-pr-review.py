#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Capture deterministic, read-only Git and GitHub pull-request evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlparse


SCHEMA_VERSION = "1.0"
DIGEST_ALGORITHM = "sha256"
DEFAULT_MAXIMUM_API_CALLS = 200
DEFAULT_MAXIMUM_ITEMS = 10_000
DEFAULT_MAXIMUM_THREADS = 500
DEFAULT_MAXIMUM_COMMENTS = 10_000
DEFAULT_MAXIMUM_REACTIONS = 10_000
DEFAULT_EXTERNAL_COMMAND_TIMEOUT_SECONDS = 30
BLOCKED_INCOMPLETE = "BLOCKED_INCOMPLETE_REVIEW_STATE"
ZERO_AUTHOR = {
    "kind": "deleted_or_unavailable",
    "login": None,
    "database_id": None,
    "node_id": None,
    "url": None,
}
ALLOWED_GIT_SUBCOMMANDS = {
    "branch",
    "cat-file",
    "remote",
    "rev-list",
    "rev-parse",
    "status",
    "verify-commit",
}
PROHIBITED_GIT_SUBCOMMANDS = {
    "checkout",
    "clean",
    "commit",
    "fetch",
    "push",
    "reset",
    "stash",
    "switch",
}
SUCCESSFUL_CHECK_CONCLUSIONS = {"SUCCESS", "NEUTRAL"}
PENDING_CHECK_STATUSES = {"EXPECTED", "IN_PROGRESS", "PENDING", "QUEUED", "REQUESTED", "WAITING"}
MERGE_STATE_POLICY = {
    "DIRTY": "block",
    "UNKNOWN": "block",
    "BLOCKED": "block",
    "BEHIND": "strict_base",
    "DRAFT": "block",
    "UNSTABLE": "required_checks",
    "HAS_HOOKS": "allow",
    "CLEAN": "allow",
}
MERGE_STATE_STATUSES = set(MERGE_STATE_POLICY)
GIT_ENVIRONMENT_OVERRIDES = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_SYSTEM",
    "GIT_DIR",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_EXEC_PATH",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
}
SAFE_GIT_CONFIG = (
    ("core.fsmonitor", "false"),
    ("gpg.program", "gpg"),
    ("gpg.openpgp.program", "gpg"),
    ("gpg.ssh.program", "ssh-keygen"),
    ("gpg.x509.program", "gpgsm"),
)
REVALIDATION_SUFFIX = ".revalidation"
TRUSTED_COMMAND_DIRECTORIES = (
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/local/bin"),
    Path("/opt/homebrew/bin"),
    Path("/opt/local/bin"),
)
TRUSTED_COMMAND_PATH = os.pathsep.join(str(path) for path in TRUSTED_COMMAND_DIRECTORIES)
CAPTURED_CONNECTIONS = {
    "labels": "labels",
    "review_requests": "reviewRequests",
    "reviews": "reviews",
    "pull_request_reactions": "reactions",
    "conversation_comments": "comments",
    "review_threads": "reviewThreads",
    "commits": "commits",
}
ANCHOR_CONNECTIONS = tuple(CAPTURED_CONNECTIONS.values())
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
GIT_CONFIG_PAIR = re.compile(r"^GIT_CONFIG_(?:KEY|VALUE)_[0-9]+$")
GIT_TRACE_VARIABLE = re.compile(r"^GIT_TRACE(?:2)?(?:$|_)")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OID_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCHEMA_PATH = REPOSITORY_ROOT / "docs/schemas/secpal-pr-review-snapshot.schema.json"
CONFIG_SCHEMA_PATH = REPOSITORY_ROOT / "docs/schemas/secpal-pr-review-repositories.schema.json"


class ContractError(ValueError):
    """Raised when canonical evidence or repository configuration is invalid."""


class CommandPolicyError(ValueError):
    """Raised when an external command is outside the read-only allowlist."""


class OutputSafetyError(ValueError):
    """Raised when an output path is not safe for atomic replacement."""


class BlockedError(RuntimeError):
    """A deterministic terminal blocker."""

    def __init__(
        self,
        code: str,
        message: str,
        connection: str | None = None,
        cursor: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = redact_diagnostic(message)
        self.connection = connection
        self.cursor = cursor

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.code,
            "blocked_reason": {
                "message": self.message,
                "connection": self.connection,
                "cursor": self.cursor,
            },
        }


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandFailure(RuntimeError):
    def __init__(self, arguments: list[str], result: CommandResult) -> None:
        self.arguments = list(arguments)
        self.result = result
        executable = Path(arguments[0]).name if arguments else "command"
        detail = redact_diagnostic(result.stderr or result.stdout or "command failed")
        super().__init__(f"{executable} exited {result.returncode}: {detail}")


@dataclass(frozen=True)
class Page:
    nodes: list[Any]
    has_next_page: bool
    end_cursor: str | None


def redact_diagnostic(value: str) -> str:
    cleaned = CONTROL_CHARACTERS.sub("�", value).strip()
    cleaned = re.sub(r"(?i)(authorization\s*:\s*)(\S+)", r"\1[REDACTED]", cleaned)
    cleaned = re.sub(r"(?i)(token|private[_ -]?key|secret)(\s*[=:]\s*)(\S+)", r"\1\2[REDACTED]", cleaned)
    cleaned = re.sub(r"\b(?:gh[opsu]_|github_pat_)[A-Za-z0-9_]+\b", "[REDACTED]", cleaned)
    return cleaned[:1000]


def validate_external_command(arguments: list[str]) -> None:
    if not arguments:
        raise CommandPolicyError("Empty external command")
    executable = Path(arguments[0]).name
    if executable == "git":
        if len(arguments) < 2:
            raise CommandPolicyError("Git subcommand is required")
        subcommand = arguments[1]
        if subcommand in PROHIBITED_GIT_SUBCOMMANDS or subcommand not in ALLOWED_GIT_SUBCOMMANDS:
            raise CommandPolicyError(f"Git subcommand is not read-only allowlisted: {subcommand}")
        static_commands = {
            ("git", "rev-parse", "--show-toplevel"),
            ("git", "remote", "get-url", "origin"),
            ("git", "status", "--porcelain=v2", "--untracked-files=all"),
            ("git", "branch", "--show-current"),
            ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
            ("git", "rev-parse", "HEAD"),
            ("git", "rev-parse", "@{upstream}"),
        }
        command = tuple(arguments)
        oid = r"[0-9a-fA-F]{40,64}"
        dynamic_command = (
            len(arguments) == 4
            and (
                (subcommand == "cat-file" and arguments[2] == "commit" and re.fullmatch(oid, arguments[3]))
                or (subcommand == "verify-commit" and arguments[2] == "--raw" and re.fullmatch(oid, arguments[3]))
                or (
                    subcommand == "rev-list"
                    and arguments[2] == "--reverse"
                    and re.fullmatch(rf"{oid}\.\.{oid}", arguments[3])
                )
            )
        )
        if command not in static_commands and not dynamic_command:
            raise CommandPolicyError("Git command arguments are not exactly read-only allowlisted")
        return
    if executable != "gh":
        raise CommandPolicyError(f"Executable is not allowlisted: {executable}")
    if len(arguments) < 3:
        raise CommandPolicyError("GitHub CLI subcommand is required")
    if arguments[1] == "pr":
        raise CommandPolicyError(f"GitHub PR operation is not allowlisted: {arguments[2]}")
    if arguments[1] != "api":
        raise CommandPolicyError(f"GitHub CLI operation is not allowlisted: {arguments[1]}")
    if len(arguments) < 5 or arguments[2:4] != ["--hostname", "github.com"]:
        raise CommandPolicyError("GitHub API host must be explicitly pinned to github.com")
    if arguments[4] == "graphql":
        fields = arguments[5:]
        if len(fields) % 2:
            raise CommandPolicyError("GraphQL arguments must be exact flag/value pairs")
        query = ""
        seen_variables: set[str] = set()
        string_variables = {"owner", "name", "after", "nodeId", "oid"}
        for index in range(0, len(fields), 2):
            flag, field = fields[index : index + 2]
            if flag not in {"-f", "-F"} or "=" not in field:
                raise CommandPolicyError("GraphQL arguments are not exactly allowlisted")
            key, value = field.split("=", 1)
            if key == "query":
                if flag != "-f" or query:
                    raise CommandPolicyError("GraphQL query must be supplied once as a raw field")
                query = value
                continue
            if key in seen_variables:
                raise CommandPolicyError(f"GraphQL variable is duplicated: {key}")
            seen_variables.add(key)
            if key == "number":
                if flag != "-F" or not re.fullmatch(r"[1-9][0-9]*", value):
                    raise CommandPolicyError("GraphQL number must be a positive typed integer")
            elif key in string_variables:
                if flag != "-f" or not value or re.search(r"[\x00-\x1f\x7f]", value):
                    raise CommandPolicyError(f"GraphQL string variable is invalid: {key}")
            else:
                raise CommandPolicyError(f"GraphQL variable is not allowlisted: {key}")
        if not re.match(r"^\s*query\b", query) or re.search(r"\bmutation\b", query, re.IGNORECASE):
            raise CommandPolicyError("Only static GraphQL query operations are allowed")
        return
    if len(arguments) != 7 or arguments[4:6] != ["--method", "GET"]:
        raise CommandPolicyError("REST requests must use the exact explicit GET command shape")
    repository = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    encoded_ref = r"[A-Za-z0-9._~%-]+"
    endpoint = arguments[6]
    allowed_endpoint = re.fullmatch(
        rf"repos/{repository}/rules/branches/{encoded_ref}\?per_page=100&page=[1-9][0-9]*",
        endpoint,
    ) or re.fullmatch(
        rf"repos/{repository}/branches/{encoded_ref}/protection/required_status_checks",
        endpoint,
    )
    if not allowed_endpoint:
        raise CommandPolicyError("REST endpoint is not exactly read-only allowlisted")


class CommandRunner:
    """Execute only validated, read-only external commands through argument arrays."""

    def __init__(
        self,
        executable_paths: dict[str, str] | None = None,
        timeout_seconds: int = DEFAULT_EXTERNAL_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
            raise CommandPolicyError("External command timeout must be a positive integer")
        supplied = executable_paths or {}
        if not set(supplied) <= {"git", "gh"}:
            raise CommandPolicyError("Only git and gh executable overrides are supported")
        self.executable_paths = {
            name: _validate_injected_executable(name, value) for name, value in supplied.items()
        }
        self.timeout_seconds = timeout_seconds

    def run(self, arguments: list[str], *, allow_failure: bool = False) -> CommandResult:
        validate_external_command(arguments)
        executable = Path(arguments[0]).name
        resolved = self.executable_paths.get(executable) or resolve_trusted_executable(executable)
        command = [resolved, *arguments[1:]]
        environment = command_environment(executable)
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=self.timeout_seconds,
            )
            result = CommandResult(completed.returncode, completed.stdout, completed.stderr)
        except subprocess.TimeoutExpired:
            result = CommandResult(
                124,
                "",
                f"{executable} timed out after {self.timeout_seconds} seconds",
            )
        if result.returncode != 0 and not allow_failure:
            raise CommandFailure(arguments, result)
        return result


def _validate_injected_executable(name: str, value: str) -> str:
    """Validate an explicit executable supplied by trusted in-process test orchestration."""

    path = Path(value)
    if not path.is_absolute() or path.name != name or not path.is_file() or not os.access(path, os.X_OK):
        raise CommandPolicyError(f"Invalid explicit executable path for {name}")
    return str(path.resolve())


@cache
def resolve_trusted_executable(executable: str) -> str:
    """Resolve an allowlisted tool without consulting repository-controlled PATH entries."""

    if executable not in {"git", "gh"}:
        raise CommandPolicyError(f"Executable is not allowlisted: {executable}")
    for directory in TRUSTED_COMMAND_DIRECTORIES:
        candidate = directory / executable
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    raise CommandPolicyError(f"Trusted executable is unavailable: {executable}")


def command_environment(executable: str) -> dict[str, str]:
    """Build a deterministic environment for an allowlisted external command."""

    environment = os.environ.copy()
    environment["PATH"] = TRUSTED_COMMAND_PATH
    environment["PAGER"] = "cat"
    if executable == "gh":
        environment["GH_PAGER"] = "cat"
        environment["GH_HOST"] = "github.com"
    elif executable == "git":
        for key in GIT_ENVIRONMENT_OVERRIDES:
            environment.pop(key, None)
        for key in tuple(environment):
            if GIT_CONFIG_PAIR.fullmatch(key) or GIT_TRACE_VARIABLE.match(key):
                environment.pop(key)
        environment["GIT_PAGER"] = "cat"
        environment["GIT_NO_LAZY_FETCH"] = "1"
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        environment["GIT_CONFIG_COUNT"] = str(len(SAFE_GIT_CONFIG))
        for index, (key, value) in enumerate(SAFE_GIT_CONFIG):
            environment[f"GIT_CONFIG_KEY_{index}"] = key
            environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


class Budget:
    """Track finite API, aggregate-item, and item-kind limits."""

    def __init__(self, configuration: dict[str, Any]) -> None:
        self.maximum_api_calls = configuration["maximum_api_calls"]
        self.maximum_items = configuration["maximum_items"]
        self.kind_caps = {
            "threads": configuration["maximum_threads"],
            "comments": configuration["maximum_comments"],
            "reactions": configuration["maximum_reactions"],
        }
        self.api_calls = 0
        self.items = 0
        self.kind_items = {key: 0 for key in self.kind_caps}
        self.connections: list[dict[str, Any]] = []

    def note_api_call(self, connection: str, cursor: str | None) -> None:
        if self.api_calls >= self.maximum_api_calls:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"API call cap reached before completing {connection}",
                connection,
                cursor,
            )
        self.api_calls += 1

    def add_items(
        self,
        count: int,
        connection: str,
        cursor: str | None,
        kind: str = "items",
    ) -> None:
        if count < 0:
            raise ContractError("Item count cannot be negative")
        if self.items + count > self.maximum_items:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"Aggregate item cap reached while reading {connection}",
                connection,
                cursor,
            )
        if kind in self.kind_caps and self.kind_items[kind] + count > self.kind_caps[kind]:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"{kind} cap reached while reading {connection}",
                connection,
                cursor,
            )
        self.items += count
        if kind in self.kind_caps:
            self.kind_items[kind] += count

    def require_capacity_for_next_page(self, connection: str, cursor: str | None, kind: str) -> None:
        exhausted = self.items >= self.maximum_items or self.api_calls >= self.maximum_api_calls
        if kind in self.kind_caps:
            exhausted = exhausted or self.kind_items[kind] >= self.kind_caps[kind]
        if exhausted:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"Configured cap reached before completing {connection}",
                connection,
                cursor,
            )

    def record_connection(self, connection: str, pages: int, items: int) -> None:
        self.connections.append({"connection": connection, "pages": pages, "items": items})


def collect_pages(
    connection: str,
    fetch_page: Callable[[str | None], Page],
    budget: Budget,
    *,
    kind: str = "items",
) -> list[Any]:
    cursor: str | None = None
    result: list[Any] = []
    pages = 0
    while True:
        page = fetch_page(cursor)
        if not isinstance(page, Page):
            raise ContractError(f"Page fetcher for {connection} returned an invalid page")
        pages += 1
        budget.add_items(len(page.nodes), connection, cursor, kind)
        result.extend(page.nodes)
        if not page.has_next_page:
            budget.record_connection(connection, pages, len(result))
            return result
        if not page.end_cursor:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"{connection} reported another page without an end cursor",
                connection,
                cursor,
            )
        cursor = page.end_cursor
        budget.require_capacity_for_next_page(connection, cursor, kind)


def parse_api_json(raw: str, connection: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Malformed JSON returned for "
            f"{connection}: {exc.msg if isinstance(exc, json.JSONDecodeError) else 'invalid value'}",
            connection,
            None,
        ) from exc


def parse_graphql_payload(raw: str, connection: str) -> dict[str, Any]:
    payload = parse_api_json(raw, connection)
    if not isinstance(payload, dict):
        raise BlockedError(BLOCKED_INCOMPLETE, f"Invalid GraphQL response for {connection}", connection, None)
    errors = payload.get("errors")
    if errors:
        messages = sorted(
            redact_diagnostic(str(item.get("message", "GraphQL error")))
            for item in errors
            if isinstance(item, dict)
        )
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            f"GraphQL returned errors for {connection}: {'; '.join(messages) or 'unknown error'}",
            connection,
            None,
        )
    if not isinstance(payload.get("data"), dict):
        raise BlockedError(BLOCKED_INCOMPLETE, f"GraphQL data is missing for {connection}", connection, None)
    return payload


def classify_api_failure(message: str) -> BlockedError:
    diagnostic = redact_diagnostic(message)
    lowered = diagnostic.lower()
    if "secondary rate limit" in lowered:
        diagnostic = "GitHub secondary rate limit prevented a complete read"
    elif "rate limit" in lowered:
        diagnostic = "GitHub API rate limit prevented a complete read"
    return BlockedError(BLOCKED_INCOMPLETE, diagnostic)


def validate_repository_name(repository: str) -> tuple[str, str]:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ContractError("Repository must be exactly OWNER/REPO")
    owner, name = repository.split("/", 1)
    return owner, name


def _require_positive_integer(configuration: dict[str, Any], key: str) -> None:
    value = configuration.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{key} must be a positive integer")


@cache
def _load_authoritative_schema(path: str) -> dict[str, Any]:
    try:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load authoritative schema: {redact_diagnostic(str(exc))}") from exc
    if not isinstance(schema, dict):
        raise ContractError("Authoritative schema must be a JSON object")
    return schema


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }.get(expected, False)


def _validate_schema_value(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    location: str,
) -> None:
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            raise ContractError(f"Unsupported schema reference at {location}")
        name = reference.removeprefix("#/$defs/")
        target = root.get("$defs", {}).get(name)
        if not isinstance(target, dict):
            raise ContractError(f"Unknown schema reference at {location}: {reference}")
        _validate_schema_value(value, target, root, location)
        return

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = [expected_type] if isinstance(expected_type, str) else expected_type
        if not isinstance(expected_types, list) or not any(
            isinstance(item, str) and _json_type_matches(value, item) for item in expected_types
        ):
            raise ContractError(f"Schema type mismatch at {location}")

    if "const" in schema and value != schema["const"]:
        raise ContractError(f"Schema constant mismatch at {location}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"Schema enum mismatch at {location}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            raise ContractError(f"Invalid authoritative object schema at {location}")
        missing = sorted(set(required) - value.keys())
        if missing:
            raise ContractError(f"Missing schema fields at {location}: {missing}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ContractError(f"Invalid authoritative properties at {location}")
        if schema.get("additionalProperties") is False:
            extra = sorted(value.keys() - properties.keys())
            if extra:
                raise ContractError(f"Unknown schema fields at {location}: {extra}")
        for key, item in value.items():
            child = properties.get(key)
            if isinstance(child, dict):
                _validate_schema_value(item, child, root, f"{location}.{key}")

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            raise ContractError(f"Schema array is too short at {location}")
        maximum_items = schema.get("maxItems")
        if isinstance(maximum_items, int) and len(value) > maximum_items:
            raise ContractError(f"Schema array is too long at {location}")
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise ContractError(f"Schema array contains duplicates at {location}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema_value(item, item_schema, root, f"{location}[{index}]")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            raise ContractError(f"Schema string is too short at {location}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise ContractError(f"Schema pattern mismatch at {location}")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            raise ContractError(f"Schema integer is too small at {location}")


def validate_against_authoritative_schema(value: Any, path: Path, location: str) -> None:
    schema = _load_authoritative_schema(str(path))
    _validate_schema_value(value, schema, schema, location)


def validate_config(configuration: dict[str, Any]) -> None:
    if not isinstance(configuration, dict):
        raise ContractError("Repository configuration must be a JSON object")
    validate_against_authoritative_schema(configuration, CONFIG_SCHEMA_PATH, "configuration")
    required = {
        "schema_version",
        "repository",
        "default_branch",
        "allowed_base_repositories",
        "reviewer_identities",
        "signature_policy",
        "check_policy",
        "maximum_api_calls",
        "maximum_items",
        "maximum_threads",
        "maximum_comments",
        "maximum_reactions",
    }
    allowed = required | {"$comment"}
    missing = sorted(required - configuration.keys())
    extra = sorted(configuration.keys() - allowed)
    if missing or extra:
        raise ContractError(f"Invalid repository configuration keys: missing={missing}, extra={extra}")
    if configuration["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"Unsupported repository configuration schema: {configuration['schema_version']}")
    validate_repository_name(configuration["repository"])
    if not isinstance(configuration["default_branch"], str) or not configuration["default_branch"]:
        raise ContractError("default_branch must be a non-empty string")
    bases = configuration["allowed_base_repositories"]
    if not isinstance(bases, list) or not bases or len(set(bases)) != len(bases):
        raise ContractError("allowed_base_repositories must be a non-empty unique list")
    for repository in bases:
        validate_repository_name(repository)
    identities = configuration["reviewer_identities"]
    if not isinstance(identities, list):
        raise ContractError("reviewer_identities must be a list")
    canonical: set[str] = set()
    aliases: set[str] = set()
    for identity in identities:
        expected = {
            "canonical_identity",
            "kind",
            "graphql_aliases",
            "rest_event_aliases",
            "node_ids",
            "database_ids",
        }
        if not isinstance(identity, dict) or set(identity) != expected:
            raise ContractError("Each reviewer identity must use the canonical identity fields")
        name = identity["canonical_identity"]
        if not isinstance(name, str) or not name or name in canonical:
            raise ContractError("canonical_identity must be non-empty and unique")
        canonical.add(name)
        if identity["kind"] not in {"human", "bot", "app"}:
            raise ContractError(f"Invalid reviewer identity kind for {name}")
        for key in ("graphql_aliases", "rest_event_aliases", "node_ids"):
            values = identity[key]
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise ContractError(f"{key} must contain non-empty strings")
            if len(values) != len(set(values)):
                raise ContractError(f"{key} contains duplicates")
            for value in values:
                token = f"{key}:{value}"
                if token in aliases:
                    raise ContractError(f"Reviewer identity alias is duplicated: {value}")
                aliases.add(token)
        database_ids = identity["database_ids"]
        if not isinstance(database_ids, list) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in database_ids
        ):
            raise ContractError("database_ids must contain positive integers")
    signature_policy = configuration["signature_policy"]
    if not isinstance(signature_policy, dict) or set(signature_policy) != {
        "require_github_verified",
        "require_local_verified",
        "accepted_formats",
    }:
        raise ContractError("Invalid signature_policy")
    if not all(
        isinstance(signature_policy[key], bool)
        for key in ("require_github_verified", "require_local_verified")
    ):
        raise ContractError("Signature requirements must be booleans")
    formats = signature_policy["accepted_formats"]
    if not isinstance(formats, list) or not formats or not set(formats) <= {"ssh", "openpgp"}:
        raise ContractError("accepted_formats must contain ssh and/or openpgp")
    check_policy = configuration["check_policy"]
    if not isinstance(check_policy, dict) or set(check_policy) != {
        "require_ruleset_evidence",
        "require_branch_protection_evidence",
        "expected_skipped",
    }:
        raise ContractError("Invalid check_policy")
    if not all(
        isinstance(check_policy[key], bool)
        for key in ("require_ruleset_evidence", "require_branch_protection_evidence")
    ) or check_policy["expected_skipped"] not in {"block", "allow"}:
        raise ContractError("Invalid required-check policy values")
    for key in (
        "maximum_api_calls",
        "maximum_items",
        "maximum_threads",
        "maximum_comments",
        "maximum_reactions",
    ):
        _require_positive_integer(configuration, key)


def default_config(repository: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "default_branch": "main",
        "allowed_base_repositories": [repository],
        "reviewer_identities": [],
        "signature_policy": {
            "require_github_verified": True,
            "require_local_verified": True,
            "accepted_formats": ["ssh", "openpgp"],
        },
        "check_policy": {
            "require_ruleset_evidence": True,
            "require_branch_protection_evidence": True,
            "expected_skipped": "block",
        },
        "maximum_api_calls": DEFAULT_MAXIMUM_API_CALLS,
        "maximum_items": DEFAULT_MAXIMUM_ITEMS,
        "maximum_threads": DEFAULT_MAXIMUM_THREADS,
        "maximum_comments": DEFAULT_MAXIMUM_COMMENTS,
        "maximum_reactions": DEFAULT_MAXIMUM_REACTIONS,
    }


def load_config(
    path: str | None,
    repository: str,
    maximum_api_calls: int | None = None,
    maximum_items: int | None = None,
) -> dict[str, Any]:
    configuration = default_config(repository)
    if path:
        try:
            loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"Cannot load repository configuration: {redact_diagnostic(str(exc))}") from exc
        configuration = loaded
    configuration = copy.deepcopy(configuration)
    if configuration.get("repository") != repository:
        raise ContractError(
            f"Configuration repository {configuration.get('repository')!r} does not match {repository!r}"
        )
    if maximum_api_calls is not None:
        configuration["maximum_api_calls"] = maximum_api_calls
    if maximum_items is not None:
        configuration["maximum_items"] = maximum_items
    validate_config(configuration)
    return configuration


def index_reviewer_identities(configuration: dict[str, Any]) -> dict[Any, str]:
    result: dict[Any, str] = {}
    for identity in configuration["reviewer_identities"]:
        canonical = identity["canonical_identity"]
        for key in ("graphql_aliases", "rest_event_aliases", "node_ids", "database_ids"):
            for value in identity[key]:
                result[value] = canonical
    return result


def normalize_actor(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return copy.deepcopy(ZERO_AUTHOR)
    if set(value) == {"kind", "login", "database_id", "node_id", "url"}:
        return copy.deepcopy(value)
    typename = str(value.get("__typename") or "").lower()
    kind = {
        "user": "user",
        "enterpriseuseraccount": "user",
        "bot": "bot",
        "organization": "organization",
        "mannequin": "mannequin",
    }.get(typename, "deleted_or_unavailable")
    login = value.get("login")
    if not isinstance(login, str) or not login:
        return copy.deepcopy(ZERO_AUTHOR)
    database_id = value.get("databaseId", value.get("database_id"))
    if isinstance(database_id, bool) or not isinstance(database_id, int):
        database_id = None
    node_id = value.get("id", value.get("node_id"))
    url = value.get("url")
    return {
        "kind": kind,
        "login": login,
        "database_id": database_id,
        "node_id": node_id if isinstance(node_id, str) else None,
        "url": url if isinstance(url, str) else None,
    }


def _author_sort_key(value: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(value.get("login") or ""),
        int(value.get("database_id") or 0),
        str(value.get("node_id") or ""),
    )


def normalize_reaction(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value.get("id"), str) or not value.get("id"):
        raise BlockedError(BLOCKED_INCOMPLETE, "Reaction identity is unavailable", "reactions", None)
    if not isinstance(value.get("content"), str) or not value.get("content"):
        raise BlockedError(BLOCKED_INCOMPLETE, "Reaction content is unavailable", "reactions", None)
    return {
        "id": value["id"],
        "content": value["content"],
        "created_at": value.get("createdAt", value.get("created_at")),
        "user": normalize_actor(value.get("user")),
    }


def normalize_reactions(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [normalize_reaction(value) for value in values]
    return sorted(
        result,
        key=lambda item: (
            str(item["created_at"] or ""),
            item["content"],
            _author_sort_key(item["user"]),
            str(item["id"] or ""),
        ),
    )


def normalize_review_comment(value: dict[str, Any]) -> dict[str, Any]:
    comment_id = value.get("id")
    created_at = value.get("createdAt", value.get("created_at"))
    updated_at = value.get("updatedAt", value.get("updated_at"))
    if not isinstance(comment_id, str) or not comment_id:
        raise BlockedError(BLOCKED_INCOMPLETE, "Review comment identity is unavailable", "review_comments", None)
    if any(not isinstance(value.get(key), str) for key in ("body", "url")):
        raise BlockedError(BLOCKED_INCOMPLETE, "Review comment content is unavailable", "review_comments", None)
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise BlockedError(BLOCKED_INCOMPLETE, "Review comment timestamps are unavailable", "review_comments", None)
    return {
        "id": comment_id,
        "database_id": value.get("databaseId", value.get("database_id")),
        "author": normalize_actor(value.get("author")) if "author" in value else copy.deepcopy(value["author"]),
        "body": value["body"],
        "url": value["url"],
        "created_at": created_at,
        "updated_at": updated_at,
        "reply_to_id": (
            value.get("replyTo", {}).get("id")
            if isinstance(value.get("replyTo"), dict)
            else value.get("reply_to_id")
        ),
        "review_id": (
            value.get("pullRequestReview", {}).get("id")
            if isinstance(value.get("pullRequestReview"), dict)
            else value.get("review_id")
        ),
        "reactions": normalize_reactions(value.get("reactions", {}).get("nodes", []))
        if isinstance(value.get("reactions"), dict)
        else normalize_reactions(value.get("reactions", [])),
    }


def normalize_review_thread(value: dict[str, Any]) -> dict[str, Any]:
    thread_id = value.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise BlockedError(BLOCKED_INCOMPLETE, "Review thread identity is unavailable", "review_threads", None)
    raw_comments = value.get("comments", [])
    if isinstance(raw_comments, dict):
        raw_comments = raw_comments.get("nodes", [])
    comments = sorted(
        [normalize_review_comment(comment) for comment in raw_comments],
        key=lambda item: (item["created_at"], item["database_id"] or 0, item["id"]),
    )
    if not comments:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Review thread contains no accessible comments",
            f"review_thread.{thread_id}.comments",
            None,
        )
    return {
        "id": thread_id,
        "is_resolved": bool(value.get("isResolved", value.get("is_resolved", False))),
        "is_outdated": bool(value.get("isOutdated", value.get("is_outdated", False))),
        "path": value.get("path"),
        "line": value.get("line"),
        "original_line": value.get("originalLine", value.get("original_line")),
        "side": value.get("diffSide", value.get("side")),
        "start_line": value.get("startLine", value.get("start_line")),
        "start_side": value.get("startDiffSide", value.get("start_side")),
        "comments": comments,
    }


def _normalize_existing_author(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) == {"kind", "login", "database_id", "node_id", "url"}:
        return copy.deepcopy(value)
    return normalize_actor(value)


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(snapshot)
    pr = result.get("pull_request", {})
    if isinstance(pr.get("author"), dict):
        pr["author"] = _normalize_existing_author(pr["author"])
    pr["labels"] = sorted(set(pr.get("labels", [])))
    pr["requested_reviewers"] = sorted(
        [_normalize_existing_author(item) for item in pr.get("requested_reviewers", [])],
        key=_author_sort_key,
    )
    pr["requested_teams"] = sorted(
        pr.get("requested_teams", []), key=lambda item: (str(item.get("slug") or ""), str(item.get("id") or ""))
    )
    pr["reactions"] = normalize_reactions(pr.get("reactions", []))
    result["reviews"] = sorted(
        result.get("reviews", []),
        key=lambda item: (
            str(item.get("submitted_at") or ""),
            int(item.get("database_id") or 0),
            str(item.get("id") or ""),
        ),
    )
    for item in result["reviews"]:
        item["author"] = _normalize_existing_author(item["author"])
        item["reactions"] = normalize_reactions(item.get("reactions", []))
    result["conversation_comments"] = sorted(
        result.get("conversation_comments", []),
        key=lambda item: (
            str(item.get("created_at") or ""),
            int(item.get("database_id") or 0),
            str(item.get("id") or ""),
        ),
    )
    for item in result["conversation_comments"]:
        item["author"] = _normalize_existing_author(item["author"])
        item["reactions"] = normalize_reactions(item.get("reactions", []))
    result["review_threads"] = sorted(
        [normalize_review_thread(item) for item in result.get("review_threads", [])],
        key=lambda item: item["id"],
    )
    result["commits"] = sorted(
        result.get("commits", []),
        key=lambda item: (str(item.get("committed_at") or ""), str(item.get("oid") or "")),
    )
    result["checks"] = sorted(result.get("checks", []), key=lambda item: item["stable_id"])
    completeness = result.get("completeness", {})
    completeness["fully_paginated_connections"] = sorted(
        completeness.get("fully_paginated_connections", []), key=lambda item: item["connection"]
    )
    completeness["warnings"] = sorted(set(completeness.get("warnings", [])))
    evidence = result.get("required_check_evidence", {})
    for key in ("required", "missing", "sources", "unknown_reasons"):
        evidence[key] = sorted(set(evidence.get(key, [])))
    return result


def _canonical_without_digest(snapshot: dict[str, Any]) -> bytes:
    normalized = normalize_snapshot(snapshot)
    normalized.pop("snapshot_digest", None)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_digest(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_without_digest(snapshot)).hexdigest()


def attach_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_snapshot(snapshot)
    normalized["snapshot_digest"] = compute_digest(normalized)
    return normalized


def verify_digest(snapshot: dict[str, Any]) -> bool:
    value = snapshot.get("snapshot_digest")
    return isinstance(value, str) and value == compute_digest(snapshot)


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    normalized = normalize_snapshot(value) if "snapshot_digest" in value else copy.deepcopy(value)
    return (
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _require_keys(value: dict[str, Any], required: set[str], location: str) -> None:
    missing = sorted(required - value.keys())
    if missing:
        raise ContractError(f"Missing {location} fields: {missing}")


def expected_connection_items(snapshot: dict[str, Any]) -> dict[str, int]:
    pr = snapshot["pull_request"]
    captured_counts = pr["captured_connection_counts"]
    expected = {
        "labels": captured_counts["labels"],
        "review_requests": captured_counts["review_requests"],
        "reviews": captured_counts["reviews"],
        "pull_request.reactions": captured_counts["pull_request_reactions"],
        "conversation_comments": captured_counts["conversation_comments"],
        "review_threads": captured_counts["review_threads"],
        "commits": captured_counts["commits"],
    }
    check_items = sum(item["status"] != "MISSING" for item in snapshot["checks"])
    check_source = pr["check_commit_source"]
    if check_source == "test_merge":
        expected["test_merge_checks"] = check_items
    elif check_source == "head":
        if pr["potential_merge_commit_oid"] is not None:
            expected["test_merge_checks"] = 0
        expected["head_checks"] = check_items
    else:
        raise ContractError("Unsupported check commit source")
    sources = snapshot["required_check_evidence"]["sources"]
    if len(sources) != len(set(sources)) or not set(sources) <= {"rulesets", "branch_protection"}:
        raise ContractError("Required-check sources must be unique and supported")
    if "rulesets" in sources:
        expected["rulesets"] = len(snapshot["applicable_rules"]["rulesets"])
    if "branch_protection" in sources:
        expected["branch_protection"] = 1
    for comment in snapshot["conversation_comments"]:
        expected[f"conversation_comment.{comment['id']}.reactions"] = len(comment["reactions"])
    for submitted_review in snapshot["reviews"]:
        expected[f"review.{submitted_review['id']}.reactions"] = len(submitted_review["reactions"])
    for thread in snapshot["review_threads"]:
        expected[f"review_thread.{thread['id']}.comments"] = len(thread["comments"])
        for comment in thread["comments"]:
            expected[f"review_comment.{comment['id']}.reactions"] = len(comment["reactions"])
    for commit in snapshot["commits"]:
        expected[f"commit.{commit['oid']}.parents"] = len(commit["parents"])
    expected[f"labels{REVALIDATION_SUFFIX}"] = expected["labels"]
    expected[f"review_requests{REVALIDATION_SUFFIX}"] = expected["review_requests"]
    expected[f"reviews{REVALIDATION_SUFFIX}"] = expected["reviews"]
    expected[f"pull_request.reactions{REVALIDATION_SUFFIX}"] = expected["pull_request.reactions"]
    expected[f"conversation_comments{REVALIDATION_SUFFIX}"] = len(snapshot["conversation_comments"])
    expected[f"review_threads{REVALIDATION_SUFFIX}"] = len(snapshot["review_threads"])
    expected[f"commits{REVALIDATION_SUFFIX}"] = len(snapshot["commits"])
    for connection in ("test_merge_checks", "head_checks"):
        if connection in expected:
            expected[f"{connection}{REVALIDATION_SUFFIX}"] = expected[connection]
    if "rulesets" in sources:
        expected[f"rulesets{REVALIDATION_SUFFIX}"] = len(snapshot["applicable_rules"]["rulesets"])
    if "branch_protection" in sources:
        expected[f"branch_protection{REVALIDATION_SUFFIX}"] = 1
    for comment in snapshot["conversation_comments"]:
        expected[f"conversation_comment.{comment['id']}.reactions{REVALIDATION_SUFFIX}"] = len(
            comment["reactions"]
        )
    for submitted_review in snapshot["reviews"]:
        expected[f"review.{submitted_review['id']}.reactions{REVALIDATION_SUFFIX}"] = len(
            submitted_review["reactions"]
        )
    for thread in snapshot["review_threads"]:
        expected[f"review_thread.{thread['id']}.comments{REVALIDATION_SUFFIX}"] = len(
            thread["comments"]
        )
        for comment in thread["comments"]:
            expected[f"review_comment.{comment['id']}.reactions{REVALIDATION_SUFFIX}"] = len(
                comment["reactions"]
            )
    for commit in snapshot["commits"]:
        expected[f"commit.{commit['oid']}.parents{REVALIDATION_SUFFIX}"] = len(commit["parents"])
    return expected


def expected_api_calls(connections: list[dict[str, Any]]) -> int:
    direct_connections = {
        "labels",
        "review_requests",
        "reviews",
        "pull_request.reactions",
        "conversation_comments",
        "review_threads",
        "commits",
        "test_merge_checks",
        "head_checks",
        "rulesets",
        "branch_protection",
    }
    calls = 3
    for item in connections:
        connection = item["connection"].removesuffix(REVALIDATION_SUFFIX)
        pages = item["pages"]
        if connection in direct_connections or (
            connection.startswith("review_thread.") and connection.endswith(".comments")
        ):
            calls += pages
        elif connection.endswith(".reactions"):
            calls += max(0, pages - 1)
    return calls


def ensure_revalidated_evidence(label: str, before: Any, after: Any) -> None:
    """Reject volatile evidence that changed between bounded observations."""

    if before != after:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            f"{label} changed during capture",
            label,
            None,
        )


def validate_completeness(snapshot: dict[str, Any]) -> None:
    completeness = snapshot["completeness"]
    if completeness["warnings"]:
        raise ContractError("An authoritative snapshot cannot contain capture warnings")
    expected = expected_connection_items(snapshot)
    evidence: dict[str, int] = {}
    for item in completeness["fully_paginated_connections"]:
        connection = item["connection"]
        if connection in evidence:
            raise ContractError(f"Duplicate pagination evidence for {connection}")
        evidence[connection] = item["items"]
    missing = sorted(expected.keys() - evidence.keys())
    extra = sorted(evidence.keys() - expected.keys())
    mismatched = sorted(
        connection for connection in expected.keys() & evidence.keys() if expected[connection] != evidence[connection]
    )
    if missing or extra or mismatched:
        raise ContractError(
            "Invalid pagination evidence: "
            f"missing={missing}, extra={extra}, mismatched={mismatched}"
        )
    if completeness["items"] != sum(expected.values()):
        raise ContractError("Completeness item total does not match connection evidence")
    if completeness["api_calls"] != expected_api_calls(completeness["fully_paginated_connections"]):
        raise ContractError("Completeness API-call total does not match pagination evidence")
    caps = completeness["configured_caps"]
    if completeness["api_calls"] > caps["maximum_api_calls"] or completeness["items"] > caps["maximum_items"]:
        raise ContractError("Completeness totals exceed configured aggregate caps")
    logical_connections = {
        connection: connection.removesuffix(REVALIDATION_SUFFIX) for connection in expected
    }
    thread_items = sum(
        expected[connection]
        for connection, logical in logical_connections.items()
        if logical == "review_threads"
    )
    comment_items = sum(
        expected[connection]
        for connection, logical in logical_connections.items()
        if logical == "conversation_comments"
        or (logical.startswith("review_thread.") and logical.endswith(".comments"))
    )
    reaction_items = sum(
        expected[connection]
        for connection, logical in logical_connections.items()
        if logical.endswith(".reactions")
    )
    if (
        thread_items > caps["maximum_threads"]
        or comment_items > caps["maximum_comments"]
        or reaction_items > caps["maximum_reactions"]
    ):
        raise ContractError("Completeness totals exceed configured item-kind caps")


def validate_commit_evidence(pull_request: dict[str, Any], commits: list[dict[str, Any]]) -> None:
    """Require a unique, well-formed commit set that contains the captured head."""

    if not commits:
        raise ContractError("Snapshot must include at least one PR commit")
    commit_oids: set[str] = set()
    for commit in commits:
        oid = str(commit.get("oid", ""))
        if not OID_PATTERN.fullmatch(oid):
            raise ContractError("Snapshot contains an invalid commit OID")
        normalized_oid = oid.lower()
        if normalized_oid in commit_oids:
            raise ContractError(f"Snapshot contains a duplicate commit OID: {oid}")
        commit_oids.add(normalized_oid)
        for signature_name in ("github_signature", "local_signature"):
            signature = commit.get(signature_name)
            if not isinstance(signature, dict) or signature.get("state") not in {
                "valid",
                "invalid",
                "unsigned",
                "unknown_key",
                "object_unavailable",
                "verification_pending",
            }:
                raise ContractError(f"Invalid {signature_name} evidence")
            if signature.get("verified") is not (signature["state"] == "valid"):
                raise ContractError(f"Inconsistent {signature_name} signature evidence")
    if pull_request["head_oid_after"].lower() not in commit_oids:
        raise ContractError("Snapshot commit evidence does not include the pull request head commit")


def validate_captured_connection_counts(snapshot: dict[str, Any]) -> None:
    """Bind stored PR-level anchor counts to the supplied collection evidence."""

    pull_request = snapshot["pull_request"]
    captured = pull_request["captured_connection_counts"]
    actual = {
        "labels": len(pull_request["labels"]),
        "review_requests": len(pull_request["requested_reviewers"])
        + len(pull_request["requested_teams"]),
        "reviews": len(snapshot["reviews"]),
        "pull_request_reactions": len(pull_request["reactions"]),
        "conversation_comments": len(snapshot["conversation_comments"]),
        "review_threads": len(snapshot["review_threads"]),
        "commits": len(snapshot["commits"]),
    }
    for connection in CAPTURED_CONNECTIONS:
        if captured[connection] != actual[connection]:
            label = "commit" if connection == "commits" else connection.replace("_", " ")
            raise ContractError(f"Snapshot {label} evidence does not match the captured {label} count")


def _require_unique_identities(label: str, values: Iterable[Any]) -> None:
    identities = list(values)
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ContractError(f"Snapshot contains an invalid {label} identity")
    if len(identities) != len(set(identities)):
        raise ContractError(f"Snapshot contains a duplicate {label} identity")


def validate_stable_evidence_identities(snapshot: dict[str, Any]) -> None:
    """Reject duplicated stable GitHub node identities across canonical collections."""

    _require_unique_identities("review", (item.get("id") for item in snapshot["reviews"]))
    _require_unique_identities(
        "conversation comment",
        (item.get("id") for item in snapshot["conversation_comments"]),
    )
    _require_unique_identities("review thread", (item.get("id") for item in snapshot["review_threads"]))
    review_comments = [
        comment
        for thread in snapshot["review_threads"]
        for comment in thread["comments"]
    ]
    _require_unique_identities("review comment", (item.get("id") for item in review_comments))
    reactions = [
        *snapshot["pull_request"]["reactions"],
        *(reaction for item in snapshot["reviews"] for reaction in item["reactions"]),
        *(reaction for item in snapshot["conversation_comments"] for reaction in item["reactions"]),
        *(reaction for item in review_comments for reaction in item["reactions"]),
    ]
    _require_unique_identities("reaction", (item.get("id") for item in reactions))


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        raise ContractError("Snapshot must be a JSON object")
    validate_against_authoritative_schema(snapshot, SNAPSHOT_SCHEMA_PATH, "snapshot")
    required = {
        "schema_version",
        "snapshot_digest_algorithm",
        "snapshot_digest",
        "repository",
        "pull_request",
        "reviews",
        "conversation_comments",
        "review_threads",
        "commits",
        "checks",
        "applicable_rules",
        "required_check_evidence",
        "completeness",
    }
    _require_keys(snapshot, required, "snapshot")
    if set(snapshot) != required:
        raise ContractError(f"Unknown snapshot fields: {sorted(set(snapshot) - required)}")
    if snapshot["schema_version"] != SCHEMA_VERSION or snapshot["snapshot_digest_algorithm"] != DIGEST_ALGORITHM:
        raise ContractError("Unsupported snapshot schema or digest algorithm")
    if not re.fullmatch(r"[0-9a-f]{64}", str(snapshot["snapshot_digest"])):
        raise ContractError("snapshot_digest must be a lowercase SHA-256 digest")
    if not verify_digest(snapshot):
        raise ContractError("Snapshot digest does not match canonical evidence")
    repository = snapshot["repository"]
    _require_keys(repository, {"id", "owner", "name", "name_with_owner", "url", "default_branch"}, "repository")
    validate_repository_name(repository["name_with_owner"])
    pr = snapshot["pull_request"]
    _require_keys(
        pr,
        {
            "id",
            "database_id",
            "number",
            "url",
            "title",
            "body",
            "state",
            "is_draft",
            "is_merged",
            "mergeable",
            "merge_state_status",
            "review_decision",
            "author",
            "base_repository",
            "base_ref",
            "base_oid",
            "head_repository",
            "head_ref",
            "head_oid_before",
            "head_oid_after",
            "potential_merge_commit_oid",
            "check_commit_oid",
            "check_commit_source",
            "captured_connection_counts",
            "labels",
            "requested_reviewers",
            "requested_teams",
            "reactions",
        },
        "pull_request",
    )
    repository_name = f"{repository['owner']}/{repository['name']}"
    repository_url = f"https://github.com/{repository_name}"
    if (
        repository["name_with_owner"] != repository_name
        or repository["url"] != repository_url
    ):
        raise ContractError("Snapshot repository identity components disagree")
    if pr["base_repository"] != {
        "id": repository["id"],
        "name_with_owner": repository_name,
        "url": repository_url,
    }:
        raise ContractError("Pull request base repository does not match the queried repository")
    if pr["url"] != f"{repository_url}/pull/{pr['number']}":
        raise ContractError("Pull request URL does not match its repository and number")
    if pr["is_merged"] is not (pr["state"] == "MERGED"):
        raise ContractError("Pull request merged state is internally inconsistent")
    head_repository = pr["head_repository"]
    head_values = (
        head_repository["id"],
        head_repository["name_with_owner"],
        head_repository["url"],
    )
    if any(value is None for value in head_values) and not all(value is None for value in head_values):
        raise ContractError("Pull request head repository identity is incomplete")
    if all(value is not None for value in head_values):
        validate_repository_name(head_repository["name_with_owner"])
        if head_repository["url"] != f"https://github.com/{head_repository['name_with_owner']}":
            raise ContractError("Pull request head repository URL is inconsistent")
        if head_repository["id"] == repository["id"] and head_repository != pr["base_repository"]:
            raise ContractError("Pull request head repository identity disagrees with its repository ID")
    if not isinstance(pr["number"], int) or pr["number"] < 1:
        raise ContractError("Pull request number must be positive")
    for key in ("base_oid", "head_oid_before", "head_oid_after", "check_commit_oid"):
        if not isinstance(pr[key], str) or not OID_PATTERN.fullmatch(pr[key]):
            raise ContractError(f"Invalid pull request {key}")
    potential_merge_commit_oid = pr["potential_merge_commit_oid"]
    if potential_merge_commit_oid is not None and (
        not isinstance(potential_merge_commit_oid, str)
        or not OID_PATTERN.fullmatch(potential_merge_commit_oid)
    ):
        raise ContractError("Invalid pull request potential_merge_commit_oid")
    if (
        pr["state"] == "OPEN"
        and pr["mergeable"] in {"MERGEABLE", "UNKNOWN"}
        and potential_merge_commit_oid is None
    ):
        raise ContractError("Potential merge commit is unavailable for an open mergeable pull request")
    if pr["head_oid_before"] != pr["head_oid_after"]:
        raise ContractError("Snapshot head changed during capture")
    if pr["check_commit_source"] == "head":
        if pr["check_commit_oid"] != pr["head_oid_after"]:
            raise ContractError("Head check evidence is bound to the wrong commit")
    elif pr["check_commit_source"] == "test_merge":
        if potential_merge_commit_oid is None or pr["check_commit_oid"] != potential_merge_commit_oid:
            raise ContractError("Test-merge check evidence is bound to the wrong commit")
        if not any(item.get("status") != "MISSING" for item in snapshot["checks"]):
            raise ContractError("Test-merge check evidence cannot be empty")
    else:
        raise ContractError("Unsupported check commit source")
    for collection in ("reviews", "conversation_comments", "review_threads", "commits", "checks"):
        if not isinstance(snapshot[collection], list):
            raise ContractError(f"{collection} must be an array")
    validate_stable_evidence_identities(snapshot)
    validate_captured_connection_counts(snapshot)
    validate_commit_evidence(pr, snapshot["commits"])
    completeness = snapshot["completeness"]
    _require_keys(
        completeness,
        {
            "api_calls",
            "items",
            "configured_caps",
            "fully_paginated_connections",
            "warnings",
            "blocked_reason",
        },
        "completeness",
    )
    if completeness["blocked_reason"] is not None:
        raise ContractError("An authoritative snapshot cannot contain a blocker")
    if not snapshot["applicable_rules"].get("evidence_complete"):
        raise ContractError("Applicable-rule evidence is incomplete")
    required_check_evidence = snapshot["required_check_evidence"]
    if required_check_evidence.get("unknown_reasons"):
        raise ContractError("Complete required-check evidence cannot contain unknown reasons")
    if required_check_evidence.get("determination") != "complete":
        raise ContractError("Required-check evidence is incomplete")
    validate_required_check_metadata(snapshot)
    validate_completeness(snapshot)


def trusted_github_url(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) > 2048 or re.search(r'[\x00-\x20\x7f<>\\\[\]()"\']', value):
        return False
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "github.com"
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def escape_markdown(value: Any) -> str:
    text = CONTROL_CHARACTERS.sub("�", str(value if value is not None else ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    text = text.replace("<!--", "&lt;!--").replace("-->", "--&gt;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    for character in "\\`*_{}[]()#+-.!|":
        text = text.replace(character, f"\\{character}")
    return text


def _markdown_link(label: str, url: str | None) -> str:
    safe_label = escape_markdown(label)
    if trusted_github_url(url):
        return f"[{safe_label}]({url})"
    return f"{safe_label} — {escape_markdown(url or 'URL unavailable')}"


def _markdown_body(body: str) -> str:
    escaped = escape_markdown(body)
    lines = escaped.splitlines() or [""]
    return "\n".join(f"    {line}" for line in lines)


def render_markdown(snapshot: dict[str, Any]) -> str:
    validate_snapshot(snapshot)
    repository = snapshot["repository"]["name_with_owner"]
    pr = snapshot["pull_request"]
    lines = [
        "# Pull Request Evidence Snapshot",
        "",
        "**Canonical authority: JSON snapshot and SHA-256 digest**",
        "",
        f"- Repository: {escape_markdown(repository)}",
        f"- Pull request: {escape_markdown(pr['number'])}",
        f"- Title: {escape_markdown(pr['title'])}",
        f"- State: {escape_markdown(pr['state'])}",
        f"- Draft: {'yes' if pr['is_draft'] else 'no'}",
        f"- Head: `{pr['head_oid_after']}`",
        f"- Digest: `{snapshot['snapshot_digest']}`",
        f"- API calls: {snapshot['completeness']['api_calls']}",
        f"- Captured items: {snapshot['completeness']['items']}",
        "",
        "## Reviews",
    ]
    if not snapshot["reviews"]:
        lines.extend(["", "No review submissions were captured."])
    for item in snapshot["reviews"]:
        login = item["author"]["login"] or "deleted or unavailable"
        lines.extend(
            [
                "",
                f"### {escape_markdown(item['state'])} by {escape_markdown(login)}",
                "",
                f"- Source: {_markdown_link('review', item['url'])}",
                f"- Commit: `{escape_markdown(item['commit_oid'] or 'unavailable')}`",
                "",
                _markdown_body(item["body"]),
            ]
        )
    lines.extend(["", "## Conversation comments"])
    if not snapshot["conversation_comments"]:
        lines.extend(["", "No top-level conversation comments were captured."])
    for item in snapshot["conversation_comments"]:
        login = item["author"]["login"] or "deleted or unavailable"
        lines.extend(
            [
                "",
                f"### {escape_markdown(login)}",
                "",
                f"- Source: {_markdown_link('comment', item['url'])}",
                "",
                _markdown_body(item["body"]),
            ]
        )
    lines.extend(["", "## Review threads"])
    if not snapshot["review_threads"]:
        lines.extend(["", "No inline review threads were captured."])
    for item in snapshot["review_threads"]:
        location = (
            f"{escape_markdown(item['path'] or 'path unavailable')}:"
            f"{escape_markdown(item['line'] if item['line'] is not None else 'line unavailable')}"
        )
        lines.extend(
            [
                "",
                f"### {location}",
                "",
                f"- Thread: `{escape_markdown(item['id'])}`",
                f"- Resolved: {'yes' if item['is_resolved'] else 'no'}",
                f"- Outdated: {'yes' if item['is_outdated'] else 'no'}",
            ]
        )
        for comment in item["comments"]:
            login = comment["author"]["login"] or "deleted or unavailable"
            lines.extend(
                [
                    "",
                    f"#### {escape_markdown(login)}",
                    "",
                    f"- Source: {_markdown_link('inline comment', comment['url'])}",
                    "",
                    _markdown_body(comment["body"]),
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _validate_output_path(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:-1]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            raise OutputSafetyError(f"Output parent does not exist: {current}") from exc
        if stat.S_ISLNK(mode):
            raise OutputSafetyError(f"Output path has a symlink parent: {current}")
        if not stat.S_ISDIR(mode):
            raise OutputSafetyError(f"Output parent is not a directory: {current}")
    try:
        mode = absolute.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OutputSafetyError(f"Output target is a symlink: {absolute}")
    if not stat.S_ISREG(mode):
        raise OutputSafetyError(f"Output target is not a regular file: {absolute}")


def _stage_atomic_file(path: Path, content: bytes) -> Path:
    _validate_output_path(path)
    parent = path.absolute().parent
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path


def atomic_write_many(outputs: dict[Path, bytes]) -> None:
    normalized_targets: set[Path] = set()
    for target in outputs:
        normalized = Path(os.path.abspath(target))
        if normalized in normalized_targets:
            raise OutputSafetyError("Output paths must identify distinct files")
        normalized_targets.add(normalized)
    staged: list[tuple[Path, Path]] = []
    try:
        for target, content in outputs.items():
            staged.append((target, _stage_atomic_file(target, content)))
        for target, temporary in staged:
            os.replace(temporary, target)
            os.chmod(target, 0o600)
    finally:
        for _, temporary in staged:
            temporary.unlink(missing_ok=True)


def prepare_outputs(
    snapshot: dict[str, Any],
    output: str | None,
    markdown_output: str | None,
) -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {}
    if output and markdown_output and Path(os.path.abspath(output)) == Path(os.path.abspath(markdown_output)):
        raise OutputSafetyError("Canonical JSON and derived Markdown require different output paths")
    if output:
        outputs[Path(output)] = canonical_json_bytes(snapshot)
    if markdown_output:
        outputs[Path(markdown_output)] = render_markdown(snapshot).encode("utf-8")
    return outputs


def graphql_arguments(
    owner: str,
    name: str,
    number: int,
    cursor: str | None,
    query_document: str,
    extra_variables: dict[str, Any] | None = None,
) -> list[str]:
    arguments = [
        "gh",
        "api",
        "--hostname",
        "github.com",
        "graphql",
        "-f",
        f"query={query_document}",
        "-f",
        f"owner={owner}",
        "-f",
        f"name={name}",
        "-F",
        f"number={number}",
    ]
    if cursor is not None:
        arguments.extend(["-f", f"after={cursor}"])
    for key, value in sorted((extra_variables or {}).items()):
        arguments.extend(["-f", f"{key}={value}"])
    return arguments


def extract_anchor(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        repository = payload["data"]["repository"]
    except (KeyError, TypeError) as exc:
        raise BlockedError(BLOCKED_INCOMPLETE, "Repository data is missing", "pull_request.anchor", None) from exc
    if repository is None:
        raise BlockedError(BLOCKED_INCOMPLETE, "Repository is unavailable", "pull_request.anchor", None)
    pull_request = repository.get("pullRequest")
    if pull_request is None:
        raise BlockedError(BLOCKED_INCOMPLETE, "Pull request is unavailable", "pull_request.anchor", None)
    if any(
        not isinstance(pull_request.get(key), str)
        or not OID_PATTERN.fullmatch(pull_request[key])
        for key in ("headRefOid", "baseRefOid")
    ):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Pull request head or base OID is unavailable",
            "pull_request.anchor",
            None,
        )
    if "potentialMergeCommit" not in pull_request:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Potential merge commit evidence is unavailable",
            "pull_request.anchor",
            None,
        )
    potential_merge_commit = pull_request["potentialMergeCommit"]
    if potential_merge_commit is not None and (
        not isinstance(potential_merge_commit, dict)
        or not isinstance(potential_merge_commit.get("oid"), str)
        or not OID_PATTERN.fullmatch(potential_merge_commit["oid"])
    ):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Potential merge commit identity is unavailable",
            "pull_request.anchor",
            None,
        )
    mergeable = pull_request.get("mergeable")
    if mergeable not in {"MERGEABLE", "CONFLICTING", "UNKNOWN"}:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Pull request mergeability is unavailable",
            "pull_request.anchor",
            None,
        )
    if (
        pull_request.get("state") == "OPEN"
        and mergeable in {"MERGEABLE", "UNKNOWN"}
        and potential_merge_commit is None
    ):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Potential merge commit is still being generated",
            "pull_request.anchor",
            None,
        )
    repository_strings = {
        "id": repository.get("id"),
        "name": repository.get("name"),
        "nameWithOwner": repository.get("nameWithOwner"),
        "url": repository.get("url"),
        "defaultBranchRef.name": (repository.get("defaultBranchRef") or {}).get("name"),
    }
    pull_request_strings = {
        "id": pull_request.get("id"),
        "url": pull_request.get("url"),
        "title": pull_request.get("title"),
        "body": pull_request.get("body"),
        "state": pull_request.get("state"),
        "baseRefName": pull_request.get("baseRefName"),
    }
    if any(not isinstance(value, str) or not value for value in repository_strings.values()):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Required repository anchor field is unavailable",
            "pull_request.anchor",
            None,
        )
    if any(not isinstance(value, str) for value in pull_request_strings.values()):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Required pull request anchor field is unavailable",
            "pull_request.anchor",
            None,
        )
    if pull_request.get("state") not in {"OPEN", "CLOSED", "MERGED"}:
        raise BlockedError(BLOCKED_INCOMPLETE, "Pull request state is unsupported", "pull_request.anchor", None)
    if pull_request.get("mergeStateStatus") not in MERGE_STATE_STATUSES:
        raise BlockedError(BLOCKED_INCOMPLETE, "Pull request merge state is unsupported", "pull_request.anchor", None)
    if not isinstance(pull_request.get("number"), int) or isinstance(pull_request.get("number"), bool):
        raise BlockedError(BLOCKED_INCOMPLETE, "Pull request number is unavailable", "pull_request.anchor", None)
    if not isinstance(pull_request.get("isDraft"), bool) or not isinstance(pull_request.get("merged"), bool):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Pull request lifecycle state is unavailable",
            "pull_request.anchor",
            None,
        )
    if not isinstance(pull_request.get("updatedAt"), str) or not pull_request.get("updatedAt"):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Pull request update sentinel is unavailable",
            "pull_request.anchor",
            None,
        )
    for connection in ANCHOR_CONNECTIONS:
        value = pull_request.get(connection)
        total_count = value.get("totalCount") if isinstance(value, dict) else None
        if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"Pull request {connection} count sentinel is unavailable",
                "pull_request.anchor",
                None,
            )
    base_repository = pull_request.get("baseRepository")
    if not isinstance(base_repository, dict) or any(
        not isinstance(base_repository.get(key), str) or not base_repository.get(key)
        for key in ("id", "nameWithOwner", "url")
    ):
        raise BlockedError(BLOCKED_INCOMPLETE, "Base repository identity is unavailable", "pull_request.anchor", None)
    return {"repository": repository, "pull_request": pull_request}


def ensure_unchanged_head(before: str, after: str) -> None:
    if before != after:
        raise BlockedError(
            "BLOCKED_HEAD_MOVED",
            f"Pull request head moved during capture: {before} -> {after}",
            "pull_request.anchor",
            None,
        )


def ensure_unchanged_anchor(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before != after:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Pull request or repository anchor changed during capture",
            "pull_request.anchor",
            None,
        )


def ensure_anchor_counts_match(pull_request: dict[str, Any], captured: dict[str, int]) -> None:
    for connection in ANCHOR_CONNECTIONS:
        expected = pull_request[connection]["totalCount"]
        if captured.get(connection) != expected:
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                f"Captured {connection} count does not match pull request anchor",
                connection,
                None,
            )


def _empty_signer() -> dict[str, Any]:
    return copy.deepcopy(ZERO_AUTHOR)


def _local_signature_format(output: str) -> str:
    lowered = output.lower()
    if re.search(r"(?m)^gpgsm(?:\[[0-9]+\])?:", lowered):
        return "smime"
    if re.search(r"(?m)^gpg(?:\[[0-9]+\])?:", lowered):
        return "openpgp"
    if re.search(r'(?m)^(?:good|bad) "git" signature\b', lowered) or re.search(
        r"(?m)^ssh-keygen(?:\[[0-9]+\])?:",
        lowered,
    ):
        return "ssh"
    return "unknown"


def _commit_signature_format(commit_object: str) -> str:
    header = commit_object.partition("\n\n")[0]
    formats = {
        {
            "PGP SIGNATURE": "openpgp",
            "PGP MESSAGE": "openpgp",
            "SSH SIGNATURE": "ssh",
            "SIGNED MESSAGE": "smime",
        }[match]
        for match in re.findall(
            r"(?m)^gpgsig(?:-sha256)? -----BEGIN (PGP SIGNATURE|PGP MESSAGE|SSH SIGNATURE|SIGNED MESSAGE)-----$",
            header,
        )
    }
    return next(iter(formats)) if len(formats) == 1 else "unknown"


def interpret_local_signature(
    returncode: int,
    output: str,
    *,
    signature_format_hint: str = "unknown",
) -> dict[str, Any]:
    lowered = output.lower()
    reported_format = _local_signature_format(lowered)
    if reported_format == "unknown":
        signature_format = signature_format_hint
    elif signature_format_hint in {"unknown", reported_format}:
        signature_format = reported_format
    else:
        signature_format = "unknown"
    if returncode == 0:
        return {
            "state": "valid",
            "verified": True,
            "format": signature_format,
            "reason": "valid",
            "signer": _empty_signer(),
        }
    if "no public key" in lowered or "unknown key" in lowered or "can't check signature" in lowered:
        state = "unknown_key"
    elif "does not have a signature" in lowered or "no signature" in lowered or "unsigned" in lowered:
        state = "unsigned"
    elif "pending" in lowered or "temporarily unavailable" in lowered:
        state = "verification_pending"
    else:
        state = "invalid"
    return {
        "state": state,
        "verified": False,
        "format": signature_format,
        "reason": state,
        "signer": _empty_signer(),
    }


def normalize_github_signature(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "state": "unsigned",
            "verified": False,
            "format": None,
            "reason": "unsigned",
            "signer": _empty_signer(),
        }
    typename = str(value.get("__typename") or "")
    signature_format = {
        "SshSignature": "ssh",
        "GpgSignature": "openpgp",
        "SmimeSignature": "smime",
    }.get(typename, "unknown")
    raw_state = str(value.get("state") or "").upper()
    is_valid = value.get("isValid") is True
    if is_valid and raw_state in {"VALID", ""}:
        state = "valid"
    elif raw_state in {"PENDING", "UNKNOWN", "UNVERIFIED"}:
        state = "verification_pending"
    elif raw_state in {"UNKNOWN_KEY", "NO_USER"}:
        state = "unknown_key"
    elif raw_state in {"UNSIGNED", "NO_SIGNATURE"}:
        state = "unsigned"
    else:
        state = "invalid"
    return {
        "state": state,
        "verified": state == "valid",
        "format": signature_format,
        "reason": raw_state.lower() or state,
        "signer": normalize_actor(value.get("signer")),
    }


def local_signature_for_commit(runner: Any, oid: str) -> dict[str, Any]:
    commit_object = runner.run(["git", "cat-file", "commit", oid], allow_failure=True)
    if commit_object.returncode != 0:
        return {
            "state": "object_unavailable",
            "verified": False,
            "format": None,
            "reason": "object_unavailable",
            "signer": _empty_signer(),
        }
    verified = runner.run(["git", "verify-commit", "--raw", oid], allow_failure=True)
    return interpret_local_signature(
        verified.returncode,
        f"{verified.stdout}\n{verified.stderr}",
        signature_format_hint=_commit_signature_format(commit_object.stdout),
    )


def _check_application() -> dict[str, Any]:
    return {"id": None, "database_id": None, "name": None, "slug": None}


def _required_stable_id(context: str, integration_id: int | None) -> str:
    return f"check:{integration_id or 0}:{context}"


def _check_outcome(status: str | None, conclusion: str | None, expected_skipped: str) -> str:
    normalized_status = str(status or "").upper()
    normalized_conclusion = str(conclusion or "").upper()
    if normalized_status in PENDING_CHECK_STATUSES or not normalized_conclusion:
        return "pending"
    if normalized_conclusion in SUCCESSFUL_CHECK_CONCLUSIONS:
        return "successful"
    if normalized_conclusion == "SKIPPED" and expected_skipped == "allow":
        return "successful"
    return "failed"


def evaluate_checks(
    raw_checks: list[dict[str, Any]],
    required_specs: list[dict[str, Any]] | None,
    policy: dict[str, Any],
    sources: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks = [copy.deepcopy(item) for item in raw_checks]
    if required_specs is None:
        for item in checks:
            item["requiredness"] = "unknown"
            item["evidence_state"] = "requiredness_unknown"
        return sorted(checks, key=lambda item: item["stable_id"]), {
            "determination": "incomplete",
            "required": [],
            "missing": [],
            "sources": [],
            "unknown_reasons": ["required check evidence unavailable"],
        }
    required_by_key = {
        (str(spec["context"]), spec.get("integration_id")): spec for spec in required_specs
    }
    matched: set[tuple[str, int | None]] = set()
    for item in checks:
        name = item["name"]
        app_id = item.get("application", {}).get("database_id")
        matching = [
            key
            for key in required_by_key
            if key[0] == name and (key[1] is None or key[1] == app_id)
        ]
        if matching:
            matched.update(matching)
            item["requiredness"] = "required"
            outcome = _check_outcome(item.get("status"), item.get("conclusion"), policy["expected_skipped"])
            item["evidence_state"] = f"required_{outcome}"
        else:
            item["requiredness"] = "non_required"
            outcome = _check_outcome(item.get("status"), item.get("conclusion"), policy["expected_skipped"])
            item["evidence_state"] = f"non_required_{outcome}"
    missing: list[str] = []
    for key in sorted(
        set(required_by_key) - matched,
        key=lambda value: (value[0], value[1] or 0),
    ):
        stable_id = _required_stable_id(key[0], key[1])
        missing.append(stable_id)
        checks.append(
            {
                "stable_id": stable_id,
                "name": key[0],
                "application": {
                    "id": None,
                    "database_id": key[1],
                    "name": None,
                    "slug": None,
                },
                "status": "MISSING",
                "conclusion": None,
                "requiredness": "required",
                "evidence_state": "required_missing",
                "details_url": None,
            }
        )
    required_ids = sorted(
        _required_stable_id(context, integration_id) for context, integration_id in required_by_key
    )
    return sorted(checks, key=lambda item: item["stable_id"]), {
        "determination": "complete",
        "required": required_ids,
        "missing": missing,
        "sources": sorted(sources if sources is not None else ["branch_protection", "rulesets"]),
        "unknown_reasons": [],
    }


def require_rule_evidence(
    rulesets: Any,
    branch_protection: Any,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    if policy["require_ruleset_evidence"] and not isinstance(rulesets, list):
        raise BlockedError(BLOCKED_INCOMPLETE, "Applicable ruleset evidence is inaccessible", "rulesets", None)
    if policy["require_branch_protection_evidence"] and not isinstance(branch_protection, dict):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Branch-protection required-check evidence is inaccessible",
            "branch_protection",
            None,
        )
    specifications: dict[tuple[str, int | None], dict[str, Any]] = {}
    for rule in rulesets or []:
        if not isinstance(rule, dict):
            raise BlockedError(BLOCKED_INCOMPLETE, "Malformed applicable rule", "rulesets", None)
        if rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters")
        checks = parameters.get("required_status_checks") if isinstance(parameters, dict) else None
        strict = parameters.get("strict_required_status_checks_policy") if isinstance(parameters, dict) else None
        if not isinstance(checks, list) or not isinstance(strict, bool):
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                "Required-status-check rule has malformed parameters",
                "rulesets",
                None,
            )
        for item in checks:
            if not isinstance(item, dict):
                raise BlockedError(BLOCKED_INCOMPLETE, "Malformed required check rule", "rulesets", None)
            context = item.get("context")
            integration_id = item.get("integration_id")
            if not isinstance(context, str) or not context or (
                integration_id is not None
                and (
                    isinstance(integration_id, bool)
                    or not isinstance(integration_id, int)
                    or integration_id < 1
                )
            ):
                raise BlockedError(BLOCKED_INCOMPLETE, "Malformed required check identity", "rulesets", None)
            specifications[(context, integration_id)] = {
                "context": context,
                "integration_id": integration_id,
            }
    if isinstance(branch_protection, dict):
        if policy["require_branch_protection_evidence"] and not isinstance(branch_protection.get("strict"), bool):
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                "Branch-protection strict-check policy is malformed",
                "branch_protection",
                None,
            )
        contexts = branch_protection.get("contexts")
        checks = branch_protection.get("checks")
        if not isinstance(contexts, list) or not isinstance(checks, list):
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                "Branch-protection required checks are malformed",
                "branch_protection",
                None,
            )
        for context in contexts:
            if not isinstance(context, str) or not context:
                raise BlockedError(BLOCKED_INCOMPLETE, "Malformed required status context", "branch_protection", None)
            specifications.setdefault((context, None), {"context": context, "integration_id": None})
        for item in checks:
            if not isinstance(item, dict):
                raise BlockedError(BLOCKED_INCOMPLETE, "Malformed required check", "branch_protection", None)
            context = item.get("context")
            app_id = item.get("app_id")
            if app_id == -1:
                app_id = None
            if not isinstance(context, str) or not context or (
                app_id is not None
                and (isinstance(app_id, bool) or not isinstance(app_id, int) or app_id < 1)
            ):
                raise BlockedError(BLOCKED_INCOMPLETE, "Malformed required check identity", "branch_protection", None)
            specifications[(context, app_id)] = {"context": context, "integration_id": app_id}
            if app_id is not None:
                specifications.pop((context, None), None)
    return [specifications[key] for key in sorted(specifications, key=lambda value: (value[0], value[1] or 0))]


def required_specs_from_snapshot(
    snapshot: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized_rules = snapshot["applicable_rules"]["rulesets"]
    rulesets = []
    for rule in normalized_rules:
        if rule.get("type") == "required_status_checks":
            rulesets.append(
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": rule.get("required_checks"),
                        "strict_required_status_checks_policy": rule.get("strict"),
                    },
                }
            )
    branch_protection = snapshot["applicable_rules"]["branch_protection"]
    return require_rule_evidence(
        rulesets if policy["require_ruleset_evidence"] else None,
        branch_protection if policy["require_branch_protection_evidence"] else None,
        policy,
    )


def validate_required_check_metadata(snapshot: dict[str, Any]) -> None:
    """Reject internally contradictory required-check snapshot evidence."""

    stored_checks = snapshot["checks"]
    stable_ids = [item["stable_id"] for item in stored_checks]
    if len(stable_ids) != len(set(stable_ids)):
        raise ContractError("Snapshot contains a duplicate check identity")
    sources = snapshot["required_check_evidence"]["sources"]
    source_set = set(sources)
    policy = {
        "require_ruleset_evidence": "rulesets" in source_set,
        "require_branch_protection_evidence": "branch_protection" in source_set,
        "expected_skipped": "block",
    }
    try:
        required_specs = required_specs_from_snapshot(snapshot, policy)
    except BlockedError as exc:
        raise ContractError(f"Invalid required-check rule evidence: {exc.message}") from exc
    raw_fields = (
        "stable_id",
        "name",
        "application",
        "status",
        "conclusion",
        "details_url",
    )
    raw_checks = [
        {key: copy.deepcopy(item[key]) for key in raw_fields}
        for item in stored_checks
        if item["status"] != "MISSING"
    ]
    evaluated, expected_evidence = evaluate_checks(
        raw_checks,
        required_specs,
        policy,
        sources,
    )
    stored_evidence = snapshot["required_check_evidence"]
    if any(
        stored_evidence[key] != expected_evidence[key]
        for key in ("determination", "required", "missing", "sources", "unknown_reasons")
    ):
        raise ContractError("Required-check metadata disagrees with applicable rules and checks")
    stored_by_id = {item["stable_id"]: item for item in stored_checks}
    expected_by_id = {item["stable_id"]: item for item in evaluated}
    if stored_by_id.keys() != expected_by_id.keys():
        raise ContractError("Required-check metadata omits or invents check evidence")
    for stable_id, expected in expected_by_id.items():
        stored = stored_by_id[stable_id]
        for key in (*raw_fields[1:], "requiredness"):
            if stored[key] != expected[key]:
                raise ContractError(f"Check requiredness or identity is inconsistent for {stable_id}")
        if stored["status"] == "MISSING":
            allowed_states = {"required_missing"}
        else:
            prefix = stored["requiredness"]
            outcomes = {
                _check_outcome(stored["status"], stored["conclusion"], skipped_policy)
                for skipped_policy in ("allow", "block")
            }
            allowed_states = {f"{prefix}_{outcome}" for outcome in outcomes}
        if stored["evidence_state"] not in allowed_states:
            raise ContractError(f"Check outcome evidence is inconsistent for {stable_id}")


def strict_checks_require_current_base(snapshot: dict[str, Any], policy: dict[str, Any]) -> bool:
    applicable_rules = snapshot["applicable_rules"]
    ruleset_strict = policy["require_ruleset_evidence"] and any(
        rule.get("type") == "required_status_checks"
        and rule.get("strict") is True
        and bool(rule.get("required_checks"))
        for rule in applicable_rules["rulesets"]
    )
    branch_protection = applicable_rules["branch_protection"]
    branch_protection_strict = (
        policy["require_branch_protection_evidence"]
        and branch_protection.get("strict") is True
        and bool(branch_protection.get("contexts") or branch_protection.get("checks"))
    )
    return ruleset_strict or branch_protection_strict


def merge_state_blocker(snapshot: dict[str, Any], policy: dict[str, Any]) -> dict[str, str] | None:
    """Apply the complete fail-closed policy for GitHub merge-state evidence."""

    merge_state = snapshot["pull_request"]["merge_state_status"]
    disposition = MERGE_STATE_POLICY[merge_state]
    if disposition == "block":
        return {
            "code": "BLOCKED_UNSAFE_GITHUB_STATE",
            "reason": f"GitHub reports a non-ready merge state: {merge_state}",
        }
    if disposition == "strict_base" and strict_checks_require_current_base(snapshot, policy):
        return {
            "code": "BLOCKED_HEAD_BEHIND_BASE",
            "reason": "Strict required checks require the pull request head to include the current base",
        }
    return None


def verify_snapshot_gate(snapshot: dict[str, Any], configuration: dict[str, Any]) -> dict[str, Any]:
    validate_config(configuration)
    validate_snapshot(snapshot)
    blockers: list[dict[str, str]] = []
    pr = snapshot["pull_request"]
    if snapshot["repository"]["name_with_owner"] != configuration["repository"]:
        blockers.append(
            {
                "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                "reason": "Snapshot repository does not match configuration",
            }
        )
    if pr["base_repository"]["name_with_owner"] not in configuration["allowed_base_repositories"]:
        blockers.append({"code": "BLOCKED_UNSAFE_GITHUB_STATE", "reason": "PR base repository is not allowed"})
    if pr["base_ref"] != configuration["default_branch"]:
        blockers.append(
            {
                "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                "reason": "PR base branch does not match configuration",
            }
        )
    if pr["head_repository"]["name_with_owner"] is None or pr["head_ref"] is None:
        blockers.append(
            {
                "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                "reason": "PR head repository or branch is unavailable",
            }
        )
    if pr["state"] != "OPEN" or pr["is_merged"] or pr["is_draft"]:
        blockers.append(
            {
                "code": "BLOCKED_UNSAFE_GITHUB_STATE",
                "reason": "PR is not an open non-draft merge candidate",
            }
        )
    if pr["mergeable"] != "MERGEABLE":
        blockers.append({"code": "BLOCKED_UNSAFE_GITHUB_STATE", "reason": "PR mergeability is conflicting or unknown"})
    check_policy = configuration["check_policy"]
    if blocker := merge_state_blocker(snapshot, check_policy):
        blockers.append(blocker)
    signature_policy = configuration["signature_policy"]
    accepted_formats = set(signature_policy["accepted_formats"])
    for commit in snapshot["commits"]:
        if signature_policy["require_github_verified"] and (
            commit["github_signature"]["state"] != "valid"
            or not commit["github_signature"]["verified"]
            or commit["github_signature"]["format"] not in accepted_formats
        ):
            blockers.append(
                {
                    "code": "BLOCKED_INVALID_SIGNATURE",
                    "reason": f"GitHub signature invalid for {commit['oid']}",
                }
            )
        if signature_policy["require_local_verified"] and (
            commit["local_signature"]["state"] != "valid"
            or not commit["local_signature"]["verified"]
            or commit["local_signature"]["format"] not in accepted_formats
        ):
            blockers.append(
                {
                    "code": "BLOCKED_INVALID_SIGNATURE",
                    "reason": f"Local signature invalid for {commit['oid']}",
                }
            )
    required_sources = {
        source
        for source, required in (
            ("rulesets", check_policy["require_ruleset_evidence"]),
            ("branch_protection", check_policy["require_branch_protection_evidence"]),
        )
        if required
    }
    captured_sources = set(snapshot["required_check_evidence"]["sources"])
    for source in sorted(required_sources - captured_sources):
        blockers.append(
            {
                "code": BLOCKED_INCOMPLETE,
                "reason": f"Required check-policy source is absent: {source}",
            }
        )
    raw_checks = [
        {
            key: copy.deepcopy(item[key])
            for key in (
                "stable_id",
                "name",
                "application",
                "status",
                "conclusion",
                "details_url",
            )
        }
        for item in snapshot["checks"]
        if item["status"] != "MISSING"
    ]
    required_specs = required_specs_from_snapshot(snapshot, check_policy)
    evaluated_checks, _ = evaluate_checks(
        raw_checks,
        required_specs,
        check_policy,
        sorted(required_sources),
    )
    for item in evaluated_checks:
        if item["evidence_state"] in {
            "required_pending",
            "required_failed",
            "required_missing",
            "requiredness_unknown",
        }:
            blockers.append(
                {
                    "code": BLOCKED_INCOMPLETE
                    if item["evidence_state"] == "requiredness_unknown"
                    else "BLOCKED_FAILED_OR_PENDING_CI",
                    "reason": f"{item['name']}: {item['evidence_state']}",
                }
            )
    unresolved = [item for item in snapshot["review_threads"] if not item["is_resolved"]]
    requested_changes = pr["review_decision"] == "CHANGES_REQUESTED"
    review_required = pr["review_decision"] == "REVIEW_REQUIRED"
    review_requested = bool(pr["requested_reviewers"] or pr["requested_teams"])
    if unresolved or requested_changes or review_required or review_requested:
        blockers.append(
            {
                "code": "NOT_READY_FOR_MERGE",
                "reason": "Required or unresolved review state prevents the mechanical gate",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_digest": snapshot["snapshot_digest"],
        "status": "BLOCKED" if blockers else "PACKAGE_2_2_CLASSIFICATION_REQUIRED",
        "blockers": blockers,
        "raw_review_state": {
            "reviews": len(snapshot["reviews"]),
            "conversation_comments": len(snapshot["conversation_comments"]),
            "review_threads": len(snapshot["review_threads"]),
            "resolved_threads": len(snapshot["review_threads"]) - len(unresolved),
            "unresolved_threads": len(unresolved),
            "requested_changes": requested_changes,
            "review_required": review_required,
            "review_requested": review_requested,
        },
        "technical_classification_required": bool(
            snapshot["reviews"] or snapshot["conversation_comments"] or snapshot["review_threads"]
        ),
        "merge_authorized": False,
    }


def _safe_git(runner: Any, arguments: list[str]) -> CommandResult:
    try:
        return runner.run(arguments, allow_failure=True)
    except CommandFailure as exc:
        return exc.result


def _remote_repository(remote_url: str) -> str | None:
    value = remote_url.strip()
    patterns = (
        r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return match.group(1)
    return None


def verify_local_against_snapshot(
    snapshot: dict[str, Any],
    configuration: dict[str, Any],
    runner: Any,
    expected_head: str | None,
) -> dict[str, Any]:
    validate_config(configuration)
    validate_snapshot(snapshot)
    blockers: list[dict[str, str]] = []

    def block(code: str, reason: str) -> None:
        blockers.append({"code": code, "reason": reason})

    root = _safe_git(runner, ["git", "rev-parse", "--show-toplevel"])
    remote = _safe_git(runner, ["git", "remote", "get-url", "origin"])
    status = _safe_git(runner, ["git", "status", "--porcelain=v2", "--untracked-files=all"])
    branch = _safe_git(runner, ["git", "branch", "--show-current"])
    upstream = _safe_git(
        runner,
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
    )
    local_head = _safe_git(runner, ["git", "rev-parse", "HEAD"])
    remote_head = _safe_git(runner, ["git", "rev-parse", "@{upstream}"])
    repository_root = root.stdout.strip() if root.returncode == 0 else None
    remote_identity = _remote_repository(remote.stdout) if remote.returncode == 0 else None
    current_branch = branch.stdout.strip() if branch.returncode == 0 else None
    local_oid = local_head.stdout.strip() if local_head.returncode == 0 else None
    remote_oid = remote_head.stdout.strip() if remote_head.returncode == 0 else None
    pr = snapshot["pull_request"]
    pr_head = pr["head_oid_after"]
    commit_range = f"{pr['base_oid']}..{pr_head}"
    local_commits = _safe_git(runner, ["git", "rev-list", "--reverse", commit_range])
    local_commit_oids = local_commits.stdout.splitlines() if local_commits.returncode == 0 else []
    snapshot_commit_oids = [item["oid"] for item in snapshot["commits"]]

    if root.returncode != 0 or not repository_root:
        block("BLOCKED_UNSAFE_GITHUB_STATE", "Local repository root is unavailable")
    if remote_identity != configuration["repository"]:
        block("BLOCKED_UNSAFE_GITHUB_STATE", "Origin repository identity does not match configuration")
    if status.returncode != 0 or status.stdout:
        block("BLOCKED_UNCLEAN_WORKTREE", "Local worktree contains tracked or untracked changes")
    if not current_branch or current_branch != pr["head_ref"]:
        block("BLOCKED_HEAD_MOVED", "Current branch does not match the PR head branch")
    if upstream.returncode != 0 or not upstream.stdout.strip():
        block("BLOCKED_HEAD_MOVED", "Current branch has no configured upstream")
    if local_oid != pr_head or remote_oid != pr_head:
        block("BLOCKED_HEAD_MOVED", "Local, remote-tracking, and PR head OIDs do not match")
    if expected_head is not None and expected_head != pr_head:
        block("BLOCKED_HEAD_MOVED", "Expected head does not match the PR head")
    if local_commits.returncode != 0 or sorted(local_commit_oids) != sorted(snapshot_commit_oids):
        block(
            "BLOCKED_UNEXPLAINED_COMMIT",
            "Local base-to-head commit set does not match the PR commit set",
        )
    if pr["base_repository"]["name_with_owner"] not in configuration["allowed_base_repositories"]:
        block("BLOCKED_UNSAFE_GITHUB_STATE", "PR base repository is not allowed")
    if pr["base_ref"] != configuration["default_branch"]:
        block("BLOCKED_UNSAFE_GITHUB_STATE", "PR base branch does not match configuration")
    if pr["state"] != "OPEN" or pr["is_merged"]:
        block("BLOCKED_UNSAFE_GITHUB_STATE", "PR is closed or merged")

    signatures = []
    signature_policy = configuration["signature_policy"]
    accepted_formats = set(signature_policy["accepted_formats"])
    for commit in snapshot["commits"]:
        value = local_signature_for_commit(runner, commit["oid"])
        signatures.append({"oid": commit["oid"], **value})
        if signature_policy["require_local_verified"] and (
            value["state"] != "valid" or value["format"] not in accepted_formats
        ):
            block("BLOCKED_INVALID_SIGNATURE", f"Local signature is not valid for {commit['oid']}")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "VERIFIED" if not blockers else "BLOCKED",
        "repository": configuration["repository"],
        "repository_root": repository_root,
        "origin_repository": remote_identity,
        "current_branch": current_branch,
        "upstream": upstream.stdout.strip() if upstream.returncode == 0 else None,
        "local_head": local_oid,
        "remote_tracking_head": remote_oid,
        "pr_head": pr_head,
        "pr_state": pr["state"],
        "is_draft": pr["is_draft"],
        "commit_oids": snapshot_commit_oids,
        "local_commit_oids": local_commit_oids,
        "commit_signatures": signatures,
        "blockers": blockers,
        "fetched": False,
    }


PULL_REQUEST_ANCHOR_QUERY = r"""
query PullRequestAnchor($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    id
    name
    nameWithOwner
    url
    defaultBranchRef { name }
    pullRequest(number:$number) {
      id
      databaseId
      number
      url
      title
      body
      state
      isDraft
      merged
      mergeable
      mergeStateStatus
      reviewDecision
      updatedAt
      labels { totalCount }
      reviewRequests { totalCount }
      reviews { totalCount }
      comments { totalCount }
      reviewThreads { totalCount }
      commits { totalCount }
      reactions { totalCount }
      author {
        __typename
        login
        url
        ... on User { id databaseId }
        ... on Bot { id databaseId }
        ... on Organization { id databaseId }
        ... on Mannequin { id databaseId }
      }
      baseRepository { id nameWithOwner url }
      baseRefName
      baseRefOid
      headRepository { id nameWithOwner url }
      headRefName
      headRefOid
      potentialMergeCommit { oid }
    }
  }
}
"""

PULL_REQUEST_LABELS_QUERY = r"""
query PullRequestLabels($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      labels(first:100, after:$after) {
        nodes { name }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

PULL_REQUEST_REVIEW_REQUESTS_QUERY = r"""
query PullRequestReviewRequests($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewRequests(first:100, after:$after) {
        nodes {
          requestedReviewer {
            __typename
            ... on User { id databaseId login url }
            ... on Mannequin { id databaseId login url }
            ... on Team { id slug name url }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

PULL_REQUEST_REVIEWS_QUERY = r"""
query PullRequestReviews($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviews(first:100, after:$after) {
        nodes {
          id
          databaseId
          author {
            __typename
            login
            url
            ... on User { id databaseId }
            ... on Bot { id databaseId }
            ... on Organization { id databaseId }
            ... on Mannequin { id databaseId }
          }
          state
          body
          url
          submittedAt
          commit { oid }
          reactions(first:100) {
            nodes {
              id
              content
              createdAt
              user {
                __typename
                id
                databaseId
                login
                url
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

REVIEW_REACTIONS_QUERY = r"""
query ReviewReactions($owner:String!, $name:String!, $number:Int!, $nodeId:ID!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id }
  }
  node(id:$nodeId) {
    ... on PullRequestReview {
      reactions(first:100, after:$after) {
        nodes {
          id
          content
          createdAt
          user {
            __typename
            id
            databaseId
            login
            url
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

PULL_REQUEST_REACTIONS_QUERY = r"""
query PullRequestReactions($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reactions(first:100, after:$after) {
        nodes {
          id
          content
          createdAt
          user {
            __typename
            id
            databaseId
            login
            url
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

CONVERSATION_COMMENTS_QUERY = r"""
query ConversationComments($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      comments(first:100, after:$after) {
        nodes {
          id
          databaseId
          author {
            __typename
            login
            url
            ... on User { id databaseId }
            ... on Bot { id databaseId }
            ... on Organization { id databaseId }
            ... on Mannequin { id databaseId }
          }
          body
          url
          createdAt
          updatedAt
          reactions(first:100) {
            nodes {
              id
              content
              createdAt
              user {
                __typename
                id
                databaseId
                login
                url
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

ISSUE_COMMENT_REACTIONS_QUERY = r"""
query IssueCommentReactions($owner:String!, $name:String!, $number:Int!, $nodeId:ID!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id }
  }
  node(id:$nodeId) {
    ... on IssueComment {
      reactions(first:100, after:$after) {
        nodes {
          id
          content
          createdAt
          user {
            __typename
            id
            databaseId
            login
            url
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

REVIEW_THREADS_QUERY = r"""
query ReviewThreads($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$after) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          diffSide
          startLine
          startDiffSide
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

REVIEW_THREAD_COMMENTS_QUERY = r"""
query ReviewThreadComments($owner:String!, $name:String!, $number:Int!, $nodeId:ID!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id }
  }
  node(id:$nodeId) {
    ... on PullRequestReviewThread {
      comments(first:100, after:$after) {
        nodes {
          id
          databaseId
          author {
            __typename
            login
            url
            ... on User { id databaseId }
            ... on Bot { id databaseId }
            ... on Organization { id databaseId }
            ... on Mannequin { id databaseId }
          }
          body
          url
          createdAt
          updatedAt
          replyTo { id }
          pullRequestReview { id }
          reactions(first:100) {
            nodes {
              id
              content
              createdAt
              user {
                __typename
                id
                databaseId
                login
                url
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

REVIEW_COMMENT_REACTIONS_QUERY = r"""
query ReviewCommentReactions($owner:String!, $name:String!, $number:Int!, $nodeId:ID!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id }
  }
  node(id:$nodeId) {
    ... on PullRequestReviewComment {
      reactions(first:100, after:$after) {
        nodes {
          id
          content
          createdAt
          user {
            __typename
            id
            databaseId
            login
            url
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

PULL_REQUEST_COMMITS_QUERY = r"""
query PullRequestCommits($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      commits(first:100, after:$after) {
        nodes {
          commit {
            oid
            authoredDate
            committedDate
            parents(first:100) {
              nodes { oid }
              pageInfo { hasNextPage endCursor }
            }
            signature {
              __typename
              isValid
              state
              wasSignedByGitHub
              signer {
                __typename
                id
                databaseId
                login
                url
              }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

COMMIT_CHECKS_QUERY = r"""
query CommitChecks($owner:String!, $name:String!, $number:Int!, $oid:GitObjectID!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id }
    object(oid:$oid) {
      ... on Commit {
        statusCheckRollup {
          contexts(first:100, after:$after) {
            nodes {
              __typename
              ... on CheckRun {
                id
                name
                status
                conclusion
                detailsUrl
                checkSuite {
                  app { id databaseId name slug }
                }
              }
              ... on StatusContext {
                id
                context
                state
                targetUrl
                creator {
                  __typename
                  login
                  url
                  ... on User { id databaseId }
                  ... on Bot { id databaseId }
                  ... on Organization { id databaseId }
                  ... on Mannequin { id databaseId }
                }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
  }
}
"""


def _connection_page(value: Any, connection: str) -> Page:
    if not isinstance(value, dict):
        raise BlockedError(BLOCKED_INCOMPLETE, f"Missing connection data for {connection}", connection, None)
    nodes = value.get("nodes")
    page_info = value.get("pageInfo")
    if not isinstance(nodes, list) or not isinstance(page_info, dict) or not isinstance(
        page_info.get("hasNextPage"), bool
    ):
        raise BlockedError(BLOCKED_INCOMPLETE, f"Malformed connection data for {connection}", connection, None)
    if any(not isinstance(node, dict) for node in nodes):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            f"Connection contains an unavailable item for {connection}",
            connection,
            None,
        )
    end_cursor = page_info.get("endCursor")
    if end_cursor is not None and not isinstance(end_cursor, str):
        raise BlockedError(BLOCKED_INCOMPLETE, f"Invalid cursor for {connection}", connection, None)
    return Page(nodes, page_info["hasNextPage"], end_cursor)


def _path(payload: dict[str, Any], keys: tuple[str, ...], connection: str) -> Any:
    value: Any = payload
    try:
        for key in keys:
            value = value[key]
    except (KeyError, TypeError) as exc:
        raise BlockedError(BLOCKED_INCOMPLETE, f"Missing response field for {connection}", connection, None) from exc
    return value


class GitHubClient:
    def __init__(
        self,
        runner: Any,
        budget: Budget,
        owner: str,
        name: str,
        number: int,
    ) -> None:
        self.runner = runner
        self.budget = budget
        self.owner = owner
        self.name = name
        self.number = number

    def graphql(
        self,
        query_document: str,
        connection: str,
        cursor: str | None = None,
        extra_variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.budget.note_api_call(connection, cursor)
        arguments = graphql_arguments(
            self.owner,
            self.name,
            self.number,
            cursor,
            query_document,
            extra_variables,
        )
        try:
            result = self.runner.run(arguments)
        except CommandFailure as exc:
            failure = classify_api_failure(str(exc))
            failure.connection = connection
            failure.cursor = cursor
            raise failure from exc
        return parse_graphql_payload(result.stdout, connection)

    def rest(self, endpoint: str, connection: str, cursor: str | None = None) -> Any:
        self.budget.note_api_call(connection, cursor)
        arguments = ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint]
        try:
            result = self.runner.run(arguments)
        except CommandFailure as exc:
            failure = classify_api_failure(str(exc))
            failure.connection = connection
            failure.cursor = cursor
            raise failure from exc
        return parse_api_json(result.stdout, connection)


def _pull_request_connection_fetcher(
    client: GitHubClient,
    query_document: str,
    field: str,
    connection: str,
) -> Callable[[str | None], Page]:
    def fetch(cursor: str | None) -> Page:
        payload = client.graphql(query_document, connection, cursor)
        value = _path(payload, ("data", "repository", "pullRequest", field), connection)
        return _connection_page(value, connection)

    return fetch


def _embedded_connection(
    initial: Any,
    fetch_next: Callable[[str], Page],
    connection: str,
    budget: Budget,
    kind: str,
) -> list[Any]:
    first = True

    def fetch(cursor: str | None) -> Page:
        nonlocal first
        if first:
            first = False
            return _connection_page(initial, connection)
        if cursor is None:
            raise ContractError(f"Missing cursor for nested connection {connection}")
        return fetch_next(cursor)

    return collect_pages(connection, fetch, budget, kind=kind)


def _capture_labels(client: GitHubClient, connection_suffix: str = "") -> list[str]:
    connection = f"labels{connection_suffix}"
    raw_labels = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            PULL_REQUEST_LABELS_QUERY,
            "labels",
            connection,
        ),
        client.budget,
    )
    if any(not isinstance(item.get("name"), str) or not item.get("name") for item in raw_labels):
        raise BlockedError(BLOCKED_INCOMPLETE, "Label identity is unavailable", connection, None)
    return sorted(item["name"] for item in raw_labels)


def _capture_review_requests(
    client: GitHubClient,
    connection_suffix: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connection = f"review_requests{connection_suffix}"
    raw_requests = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            PULL_REQUEST_REVIEW_REQUESTS_QUERY,
            "reviewRequests",
            connection,
        ),
        client.budget,
    )
    requested_reviewers = []
    requested_teams = []
    for request in raw_requests:
        target = request.get("requestedReviewer") if isinstance(request, dict) else None
        if not isinstance(target, dict):
            raise BlockedError(BLOCKED_INCOMPLETE, "Requested reviewer is unavailable", connection, None)
        if target.get("__typename") == "Team":
            requested_teams.append(
                {
                    "id": target.get("id"),
                    "slug": target.get("slug"),
                    "name": target.get("name"),
                    "url": target.get("url"),
                }
            )
        else:
            requested_reviewers.append(normalize_actor(target))
    return (
        sorted(requested_reviewers, key=_author_sort_key),
        sorted(
            requested_teams,
            key=lambda item: (str(item.get("slug") or ""), str(item.get("id") or "")),
        ),
    )


def _normalize_review(value: dict[str, Any]) -> dict[str, Any]:
    review_id = value.get("id")
    state = value.get("state")
    if not isinstance(review_id, str) or not review_id:
        raise BlockedError(BLOCKED_INCOMPLETE, "Review identity is unavailable", "reviews", None)
    if state not in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}:
        raise BlockedError(BLOCKED_INCOMPLETE, "Review state is unavailable or unsupported", "reviews", None)
    if not isinstance(value.get("body"), str) or not isinstance(value.get("url"), str):
        raise BlockedError(BLOCKED_INCOMPLETE, "Review content fields are unavailable", "reviews", None)
    commit = value.get("commit")
    raw_reactions = value.get("reactions", [])
    if isinstance(raw_reactions, dict):
        raw_reactions = raw_reactions.get("nodes", [])
    return {
        "id": review_id,
        "database_id": value.get("databaseId"),
        "author": normalize_actor(value.get("author")),
        "state": state,
        "body": value["body"],
        "url": value["url"],
        "submitted_at": value.get("submittedAt"),
        "commit_oid": commit.get("oid") if isinstance(commit, dict) else None,
        "reactions": normalize_reactions(raw_reactions),
    }


def _capture_review_reactions(
    client: GitHubClient,
    submitted_review: dict[str, Any],
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    review_id = submitted_review.get("id")
    if not isinstance(review_id, str) or not review_id:
        raise BlockedError(BLOCKED_INCOMPLETE, "Review node ID is unavailable", "review.reactions", None)
    connection = f"review.{review_id}.reactions{connection_suffix}"

    def next_page(cursor: str) -> Page:
        payload = client.graphql(REVIEW_REACTIONS_QUERY, connection, cursor, {"nodeId": review_id})
        value = _path(payload, ("data", "node", "reactions"), connection)
        return _connection_page(value, connection)

    return _embedded_connection(
        submitted_review.get("reactions"),
        next_page,
        connection,
        client.budget,
        "reactions",
    )


def _capture_reviews(client: GitHubClient, connection_suffix: str = "") -> list[dict[str, Any]]:
    connection = f"reviews{connection_suffix}"
    raw_reviews = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            PULL_REQUEST_REVIEWS_QUERY,
            "reviews",
            connection,
        ),
        client.budget,
    )
    reviews = []
    for raw_review in raw_reviews:
        expanded = copy.deepcopy(raw_review)
        expanded["reactions"] = _capture_review_reactions(client, raw_review, connection_suffix)
        reviews.append(_normalize_review(expanded))
    return sorted(
        reviews,
        key=lambda item: (
            str(item.get("submitted_at") or ""),
            int(item.get("database_id") or 0),
            str(item.get("id") or ""),
        ),
    )


def _capture_pull_request_reactions(
    client: GitHubClient,
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    connection = f"pull_request.reactions{connection_suffix}"
    raw_reactions = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            PULL_REQUEST_REACTIONS_QUERY,
            "reactions",
            connection,
        ),
        client.budget,
        kind="reactions",
    )
    return normalize_reactions(raw_reactions)


def _normalize_conversation_comment(value: dict[str, Any]) -> dict[str, Any]:
    required = ("id", "body", "url", "createdAt", "updatedAt")
    if any(not isinstance(value.get(key), str) for key in required) or not value.get("id"):
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Conversation comment required fields are unavailable",
            "conversation_comments",
            None,
        )
    return {
        "id": value["id"],
        "database_id": value.get("databaseId"),
        "author": normalize_actor(value.get("author")),
        "body": value["body"],
        "url": value["url"],
        "created_at": value["createdAt"],
        "updated_at": value["updatedAt"],
        "reactions": normalize_reactions(value.get("reactions", [])),
    }


def _capture_comment_reactions(
    client: GitHubClient,
    comment: dict[str, Any],
    *,
    review_comment: bool,
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    comment_id = comment.get("id")
    if not isinstance(comment_id, str) or not comment_id:
        raise BlockedError(BLOCKED_INCOMPLETE, "Comment node ID is unavailable", "comment.reactions", None)
    base_connection = (
        f"review_comment.{comment_id}.reactions"
        if review_comment
        else f"conversation_comment.{comment_id}.reactions"
    )
    connection = f"{base_connection}{connection_suffix}"
    query = REVIEW_COMMENT_REACTIONS_QUERY if review_comment else ISSUE_COMMENT_REACTIONS_QUERY

    def next_page(cursor: str) -> Page:
        payload = client.graphql(query, connection, cursor, {"nodeId": comment_id})
        value = _path(payload, ("data", "node", "reactions"), connection)
        return _connection_page(value, connection)

    return _embedded_connection(
        comment.get("reactions"),
        next_page,
        connection,
        client.budget,
        "reactions",
    )


def _capture_thread_comments(
    client: GitHubClient,
    value: dict[str, Any],
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    thread_id = value.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise BlockedError(BLOCKED_INCOMPLETE, "Review thread ID is unavailable", "review_threads", None)
    connection = f"review_thread.{thread_id}.comments{connection_suffix}"

    def fetch_page(cursor: str | None) -> Page:
        payload = client.graphql(
            REVIEW_THREAD_COMMENTS_QUERY,
            connection,
            cursor,
            {"nodeId": thread_id},
        )
        nested = _path(payload, ("data", "node", "comments"), connection)
        return _connection_page(nested, connection)

    raw_comments = collect_pages(connection, fetch_page, client.budget, kind="comments")
    result = []
    for raw_comment in raw_comments:
        reactions = _capture_comment_reactions(
            client,
            raw_comment,
            review_comment=True,
            connection_suffix=connection_suffix,
        )
        expanded = copy.deepcopy(raw_comment)
        expanded["reactions"] = reactions
        result.append(normalize_review_comment(expanded))
    return result


def _capture_conversation_comments(
    client: GitHubClient,
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    connection = f"conversation_comments{connection_suffix}"
    raw_comments = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            CONVERSATION_COMMENTS_QUERY,
            "comments",
            connection,
        ),
        client.budget,
        kind="comments",
    )
    comments = []
    for raw_comment in raw_comments:
        reactions = _capture_comment_reactions(
            client,
            raw_comment,
            review_comment=False,
            connection_suffix=connection_suffix,
        )
        expanded = copy.deepcopy(raw_comment)
        expanded["reactions"] = reactions
        comments.append(_normalize_conversation_comment(expanded))
    return comments


def _capture_review_threads(
    client: GitHubClient,
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    connection = f"review_threads{connection_suffix}"
    raw_threads = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            REVIEW_THREADS_QUERY,
            "reviewThreads",
            connection,
        ),
        client.budget,
        kind="threads",
    )
    threads = []
    for raw_thread in raw_threads:
        expanded = copy.deepcopy(raw_thread)
        expanded["comments"] = _capture_thread_comments(
            client,
            raw_thread,
            connection_suffix,
        )
        threads.append(normalize_review_thread(expanded))
    return threads


def _normalize_commit(
    value: dict[str, Any],
    budget: Budget,
    connection_suffix: str = "",
) -> dict[str, Any]:
    commit = value.get("commit")
    if not isinstance(commit, dict):
        raise BlockedError(BLOCKED_INCOMPLETE, "PR commit object is unavailable", "commits", None)
    oid = commit.get("oid")
    if not isinstance(oid, str) or not OID_PATTERN.fullmatch(oid):
        raise BlockedError(BLOCKED_INCOMPLETE, "PR commit OID is unavailable", "commits", None)
    parent_connection = f"commit.{oid}.parents{connection_suffix}"
    parents = commit.get("parents")
    page = _connection_page(parents, parent_connection)
    if page.has_next_page:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Commit parent connection exceeded the supported bounded page",
            parent_connection,
            page.end_cursor,
        )
    budget.add_items(len(page.nodes), parent_connection, None)
    budget.record_connection(parent_connection, 1, len(page.nodes))
    parent_oids = []
    for parent in page.nodes:
        parent_oid = parent.get("oid") if isinstance(parent, dict) else None
        if not isinstance(parent_oid, str) or not OID_PATTERN.fullmatch(parent_oid):
            raise BlockedError(BLOCKED_INCOMPLETE, "Commit parent OID is unavailable", parent_connection, None)
        parent_oids.append(parent_oid)
    return {
        "oid": oid,
        "parents": sorted(parent_oids),
        "authored_at": str(commit.get("authoredDate") or ""),
        "committed_at": str(commit.get("committedDate") or ""),
        "github_signature": normalize_github_signature(commit.get("signature")),
    }


def _capture_commits(
    client: GitHubClient,
    connection_suffix: str = "",
) -> list[dict[str, Any]]:
    connection = f"commits{connection_suffix}"
    raw_commits = collect_pages(
        connection,
        _pull_request_connection_fetcher(
            client,
            PULL_REQUEST_COMMITS_QUERY,
            "commits",
            connection,
        ),
        client.budget,
    )
    commits = [
        _normalize_commit(
            item,
            client.budget,
            connection_suffix,
        )
        for item in raw_commits
    ]
    if not commits:
        raise BlockedError(BLOCKED_INCOMPLETE, "Pull request has no accessible commits", connection, None)
    return commits


def _attach_local_signatures(
    commits: list[dict[str, Any]],
    runner: Any,
) -> list[dict[str, Any]]:
    """Add checkout-local verification without mixing it into remote revalidation."""

    return [
        {
            **copy.deepcopy(commit),
            "local_signature": local_signature_for_commit(runner, commit["oid"]),
        }
        for commit in commits
    ]


def _normalize_check(value: dict[str, Any]) -> dict[str, Any]:
    typename = value.get("__typename")
    if typename == "CheckRun":
        node_id = value.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise BlockedError(BLOCKED_INCOMPLETE, "Check run identity is unavailable", "checks", None)
        app = value.get("checkSuite", {}).get("app") if isinstance(value.get("checkSuite"), dict) else None
        application = {
            "id": app.get("id") if isinstance(app, dict) else None,
            "database_id": app.get("databaseId") if isinstance(app, dict) else None,
            "name": app.get("name") if isinstance(app, dict) else None,
            "slug": app.get("slug") if isinstance(app, dict) else None,
        }
        name = str(value.get("name") or "")
        if not name:
            raise BlockedError(BLOCKED_INCOMPLETE, "Check run name is unavailable", "checks", None)
        return {
            "stable_id": f"check_run:{node_id}",
            "name": name,
            "application": application,
            "status": value.get("status"),
            "conclusion": value.get("conclusion"),
            "details_url": value.get("detailsUrl"),
        }
    if typename == "StatusContext":
        node_id = value.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise BlockedError(BLOCKED_INCOMPLETE, "Status context identity is unavailable", "checks", None)
        name = str(value.get("context") or "")
        if not name:
            raise BlockedError(BLOCKED_INCOMPLETE, "Status context name is unavailable", "checks", None)
        creator = normalize_actor(value.get("creator"))
        state = value.get("state")
        return {
            "stable_id": f"status_context:{node_id}",
            "name": name,
            "application": {
                "id": creator["node_id"],
                "database_id": None,
                "name": creator["login"],
                "slug": creator["login"],
            },
            "status": state,
            "conclusion": state if str(state).upper() != "PENDING" else None,
            "details_url": value.get("targetUrl"),
        }
    raise BlockedError(BLOCKED_INCOMPLETE, f"Unsupported check type: {typename!r}", "checks", None)


def _capture_checks(
    client: GitHubClient,
    commit_oid: str,
    connection: str,
) -> list[dict[str, Any]]:

    def fetch(cursor: str | None) -> Page:
        payload = client.graphql(
            COMMIT_CHECKS_QUERY,
            connection,
            cursor,
            {"oid": commit_oid},
        )
        commit_object = _path(payload, ("data", "repository", "object"), connection)
        if commit_object is None:
            raise BlockedError(BLOCKED_INCOMPLETE, "Check commit object is inaccessible", connection, cursor)
        rollup = commit_object.get("statusCheckRollup")
        if rollup is None:
            return Page([], False, None)
        return _connection_page(rollup.get("contexts"), connection)

    return [_normalize_check(item) for item in collect_pages(connection, fetch, client.budget)]


def select_effective_check_target(
    head_oid: str,
    potential_merge_commit_oid: str | None,
    test_merge_checks: list[dict[str, Any]],
) -> tuple[str, str]:
    """Apply GitHub's test-merge-first required-check selection rule."""

    if potential_merge_commit_oid is not None and test_merge_checks:
        return potential_merge_commit_oid, "test_merge"
    return head_oid, "head"


def _capture_effective_checks(
    client: GitHubClient,
    head_oid: str,
    potential_merge_commit_oid: str | None,
    connection_suffix: str = "",
) -> tuple[list[dict[str, Any]], str, str]:
    test_merge_checks: list[dict[str, Any]] = []
    if potential_merge_commit_oid is not None:
        test_merge_checks = _capture_checks(
            client,
            potential_merge_commit_oid,
            f"test_merge_checks{connection_suffix}",
        )
    check_commit_oid, check_commit_source = select_effective_check_target(
        head_oid,
        potential_merge_commit_oid,
        test_merge_checks,
    )
    if check_commit_source == "test_merge":
        return test_merge_checks, check_commit_oid, check_commit_source
    return (
        _capture_checks(client, head_oid, f"head_checks{connection_suffix}"),
        check_commit_oid,
        check_commit_source,
    )


def _normalize_applicable_rules(rulesets: list[Any], branch_protection: dict[str, Any]) -> dict[str, Any]:
    normalized_rules = []
    for rule in rulesets:
        if not isinstance(rule, dict):
            raise BlockedError(BLOCKED_INCOMPLETE, "Malformed applicable rule", "rulesets", None)
        if rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters", {})
            checks = parameters.get("required_status_checks", [])
            normalized_rules.append(
                {
                    "type": "required_status_checks",
                    "strict": parameters.get("strict_required_status_checks_policy"),
                    "required_checks": sorted(
                        [
                            {
                                "context": item.get("context"),
                                "integration_id": item.get("integration_id"),
                            }
                            for item in checks
                            if isinstance(item, dict) and isinstance(item.get("context"), str)
                        ],
                        key=lambda item: (item["context"], item["integration_id"] or 0),
                    ),
                }
            )
        else:
            normalized_rules.append({"type": str(rule.get("type") or "unknown")})
    normalized_branch = {
        "strict": branch_protection.get("strict"),
        "contexts": sorted(
            value for value in branch_protection.get("contexts", []) if isinstance(value, str)
        ),
        "checks": sorted(
            [
                {"context": item.get("context"), "app_id": item.get("app_id")}
                for item in branch_protection.get("checks", [])
                if isinstance(item, dict) and isinstance(item.get("context"), str)
            ],
            key=lambda item: (item["context"], item["app_id"] or 0),
        ),
    }
    return {
        "rulesets": sorted(normalized_rules, key=lambda item: json.dumps(item, sort_keys=True)),
        "branch_protection": normalized_branch,
        "evidence_complete": True,
    }


def _capture_rules(
    client: GitHubClient,
    base_ref: str,
    policy: dict[str, Any],
    connection_suffix: str = "",
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    encoded_ref = quote(base_ref, safe="")
    rulesets: list[Any] = []
    branch_protection: dict[str, Any] = {}
    sources: list[str] = []
    if policy["require_ruleset_evidence"]:
        connection = f"rulesets{connection_suffix}"
        base_endpoint = f"repos/{client.owner}/{client.name}/rules/branches/{encoded_ref}"
        page_number = 1
        while True:
            endpoint = f"{base_endpoint}?per_page=100&page={page_number}"
            page = client.rest(endpoint, connection, str(page_number))
            if not isinstance(page, list):
                raise BlockedError(
                    BLOCKED_INCOMPLETE,
                    "Applicable rules response is not an array",
                    connection,
                    str(page_number),
                )
            client.budget.add_items(len(page), connection, str(page_number))
            rulesets.extend(page)
            if len(page) < 100:
                client.budget.record_connection(connection, page_number, len(rulesets))
                break
            page_number += 1
            client.budget.require_capacity_for_next_page(connection, str(page_number), "items")
        sources.append("rulesets")
    if policy["require_branch_protection_evidence"]:
        connection = f"branch_protection{connection_suffix}"
        protection_endpoint = (
            f"repos/{client.owner}/{client.name}/branches/{encoded_ref}/protection/required_status_checks"
        )
        branch_protection = client.rest(protection_endpoint, connection)
        if not isinstance(branch_protection, dict):
            raise BlockedError(
                BLOCKED_INCOMPLETE,
                "Branch-protection response is not an object",
                connection,
                None,
            )
        client.budget.add_items(1, connection, None)
        client.budget.record_connection(connection, 1, 1)
        sources.append("branch_protection")
    required = require_rule_evidence(
        rulesets if policy["require_ruleset_evidence"] else None,
        branch_protection if policy["require_branch_protection_evidence"] else None,
        policy,
    )
    return _normalize_applicable_rules(rulesets, branch_protection), required, sorted(sources)


def _capture_remote_evidence(
    client: GitHubClient,
    head_oid: str,
    potential_merge_commit_oid: str | None,
    base_ref: str,
    configuration: dict[str, Any],
    connection_suffix: str = "",
) -> dict[str, Any]:
    """Capture one complete, normalized observation of mutable GitHub evidence."""

    labels = _capture_labels(client, connection_suffix)
    requested_reviewers, requested_teams = _capture_review_requests(client, connection_suffix)
    reviews = _capture_reviews(client, connection_suffix)
    pull_request_reactions = _capture_pull_request_reactions(client, connection_suffix)
    conversation_comments = _capture_conversation_comments(client, connection_suffix)
    review_threads = _capture_review_threads(client, connection_suffix)
    commits = _capture_commits(client, connection_suffix)
    raw_checks, check_commit_oid, check_commit_source = _capture_effective_checks(
        client,
        head_oid,
        potential_merge_commit_oid,
        connection_suffix,
    )
    applicable_rules, required_specs, rule_sources = _capture_rules(
        client,
        base_ref,
        configuration["check_policy"],
        connection_suffix,
    )
    checks, required_check_evidence = evaluate_checks(
        raw_checks,
        required_specs,
        configuration["check_policy"],
        rule_sources,
    )
    return {
        "labels": labels,
        "requested_reviewers": requested_reviewers,
        "requested_teams": requested_teams,
        "reviews": reviews,
        "pull_request_reactions": pull_request_reactions,
        "conversation_comments": conversation_comments,
        "review_threads": review_threads,
        "commits": commits,
        "checks": checks,
        "check_commit_oid": check_commit_oid,
        "check_commit_source": check_commit_source,
        "applicable_rules": applicable_rules,
        "required_check_evidence": required_check_evidence,
    }


def capture_snapshot(
    repository: str,
    number: int,
    configuration: dict[str, Any],
    runner: Any | None = None,
) -> dict[str, Any]:
    validate_config(configuration)
    owner, name = validate_repository_name(repository)
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ContractError("Pull request number must be a positive integer")
    command_runner = runner or CommandRunner()
    budget = Budget(configuration)
    client = GitHubClient(command_runner, budget, owner, name, number)

    before_payload = client.graphql(PULL_REQUEST_ANCHOR_QUERY, "pull_request.anchor.before")
    before = extract_anchor(before_payload)
    before_pr = before["pull_request"]
    if before["repository"]["nameWithOwner"] != repository:
        raise BlockedError(
            "BLOCKED_UNSAFE_GITHUB_STATE",
            "GitHub repository identity does not match the requested repository",
            "pull_request.anchor",
            None,
        )
    head_before = before_pr["headRefOid"]
    potential_merge_commit = before_pr.get("potentialMergeCommit")
    potential_merge_commit_oid = (
        potential_merge_commit.get("oid") if isinstance(potential_merge_commit, dict) else None
    )

    evidence = _capture_remote_evidence(
        client,
        head_before,
        potential_merge_commit_oid,
        before_pr["baseRefName"],
        configuration,
    )

    ensure_anchor_counts_match(
        before_pr,
        {
            "labels": len(evidence["labels"]),
            "reviewRequests": len(evidence["requested_reviewers"])
            + len(evidence["requested_teams"]),
            "reviews": len(evidence["reviews"]),
            "reactions": len(evidence["pull_request_reactions"]),
            "comments": len(evidence["conversation_comments"]),
            "reviewThreads": len(evidence["review_threads"]),
            "commits": len(evidence["commits"]),
        },
    )

    after_payload = client.graphql(PULL_REQUEST_ANCHOR_QUERY, "pull_request.anchor.after")
    after = extract_anchor(after_payload)
    head_after = after["pull_request"]["headRefOid"]
    ensure_unchanged_head(head_before, head_after)
    if after["pull_request"]["id"] != before_pr["id"]:
        raise BlockedError(
            BLOCKED_INCOMPLETE,
            "Pull request identity changed during capture",
            "pull_request.anchor",
            None,
        )
    ensure_unchanged_anchor(before, after)

    revalidated_evidence = _capture_remote_evidence(
        client,
        head_before,
        potential_merge_commit_oid,
        before_pr["baseRefName"],
        configuration,
        REVALIDATION_SUFFIX,
    )

    terminal_payload = client.graphql(PULL_REQUEST_ANCHOR_QUERY, "pull_request.anchor.terminal")
    terminal = extract_anchor(terminal_payload)
    terminal_head = terminal["pull_request"]["headRefOid"]
    ensure_unchanged_head(head_before, terminal_head)
    ensure_unchanged_anchor(before, terminal)
    ensure_revalidated_evidence("remote GitHub evidence", evidence, revalidated_evidence)
    commits = _attach_local_signatures(evidence["commits"], command_runner)
    head_after = terminal_head

    repository_data = before["repository"]
    base_repository = before_pr.get("baseRepository") or {}
    head_repository = before_pr.get("headRepository") or {}
    state = "MERGED" if before_pr.get("merged") else str(before_pr.get("state") or "CLOSED")
    result = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_digest_algorithm": DIGEST_ALGORITHM,
        "snapshot_digest": "0" * 64,
        "repository": {
            "id": str(repository_data.get("id") or ""),
            "owner": owner,
            "name": name,
            "name_with_owner": str(repository_data.get("nameWithOwner") or ""),
            "url": str(repository_data.get("url") or ""),
            "default_branch": str((repository_data.get("defaultBranchRef") or {}).get("name") or ""),
        },
        "pull_request": {
            "id": str(before_pr.get("id") or ""),
            "database_id": before_pr.get("databaseId"),
            "number": int(before_pr.get("number")),
            "url": str(before_pr.get("url") or ""),
            "title": str(before_pr.get("title") or ""),
            "body": str(before_pr.get("body") or ""),
            "state": state,
            "is_draft": bool(before_pr.get("isDraft")),
            "is_merged": bool(before_pr.get("merged")),
            "mergeable": before_pr.get("mergeable"),
            "merge_state_status": before_pr.get("mergeStateStatus"),
            "review_decision": before_pr.get("reviewDecision"),
            "author": normalize_actor(before_pr.get("author")),
            "base_repository": {
                "id": base_repository.get("id"),
                "name_with_owner": base_repository.get("nameWithOwner"),
                "url": base_repository.get("url"),
            },
            "base_ref": str(before_pr.get("baseRefName") or ""),
            "base_oid": str(before_pr.get("baseRefOid") or ""),
            "head_repository": {
                "id": head_repository.get("id"),
                "name_with_owner": head_repository.get("nameWithOwner"),
                "url": head_repository.get("url"),
            },
            "head_ref": before_pr.get("headRefName"),
            "head_oid_before": head_before,
            "head_oid_after": head_after,
            "potential_merge_commit_oid": potential_merge_commit_oid,
            "check_commit_oid": evidence["check_commit_oid"],
            "check_commit_source": evidence["check_commit_source"],
            "captured_connection_counts": {
                name: before_pr[connection]["totalCount"]
                for name, connection in CAPTURED_CONNECTIONS.items()
            },
            "labels": evidence["labels"],
            "requested_reviewers": evidence["requested_reviewers"],
            "requested_teams": evidence["requested_teams"],
            "reactions": evidence["pull_request_reactions"],
        },
        "reviews": evidence["reviews"],
        "conversation_comments": evidence["conversation_comments"],
        "review_threads": evidence["review_threads"],
        "commits": commits,
        "checks": evidence["checks"],
        "applicable_rules": evidence["applicable_rules"],
        "required_check_evidence": evidence["required_check_evidence"],
        "completeness": {
            "api_calls": budget.api_calls,
            "items": budget.items,
            "configured_caps": {
                "maximum_api_calls": configuration["maximum_api_calls"],
                "maximum_items": configuration["maximum_items"],
                "maximum_threads": configuration["maximum_threads"],
                "maximum_comments": configuration["maximum_comments"],
                "maximum_reactions": configuration["maximum_reactions"],
            },
            "fully_paginated_connections": budget.connections,
            "warnings": [],
            "blocked_reason": None,
        },
    }
    result = attach_digest(result)
    validate_snapshot(result)
    return result


def _load_snapshot_file(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load snapshot: {redact_diagnostic(str(exc))}") from exc
    validate_snapshot(value)
    return value


def _json_report(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture deterministic, read-only Git and GitHub pull-request evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Capture one complete bounded snapshot.")
    snapshot_parser.add_argument("--repo", required=True, help="Repository in OWNER/REPO form.")
    snapshot_parser.add_argument("--pr", required=True, type=_positive_integer, help="Pull request number.")
    snapshot_parser.add_argument("--config", help="Repository configuration JSON.")
    snapshot_parser.add_argument("--output", help="Atomic canonical JSON output path.")
    snapshot_parser.add_argument("--markdown-output", help="Atomic derived Markdown output path.")
    snapshot_parser.add_argument("--max-api-calls", type=_positive_integer)
    snapshot_parser.add_argument("--max-items", type=_positive_integer)

    local_parser = subparsers.add_parser("verify-local", help="Verify local Git state against live PR evidence.")
    local_parser.add_argument("--repo", required=True, help="Repository in OWNER/REPO form.")
    local_parser.add_argument("--pr", required=True, type=_positive_integer, help="Pull request number.")
    local_parser.add_argument("--config", help="Repository configuration JSON.")
    local_parser.add_argument("--expected-head", help="Expected pull-request head OID.")

    gate_parser = subparsers.add_parser("verify-gate", help="Verify deterministic mechanical gate evidence.")
    gate_parser.add_argument("--snapshot", required=True, help="Canonical snapshot JSON.")
    gate_parser.add_argument("--config", help="Repository configuration JSON.")

    render_parser = subparsers.add_parser("render", help="Render derived non-authoritative evidence.")
    render_parser.add_argument("--snapshot", required=True, help="Canonical snapshot JSON.")
    render_parser.add_argument("--format", required=True, choices=("markdown",))
    return parser


def _command_snapshot(arguments: argparse.Namespace) -> int:
    configuration = load_config(
        arguments.config,
        arguments.repo,
        arguments.max_api_calls,
        arguments.max_items,
    )
    value = capture_snapshot(arguments.repo, arguments.pr, configuration)
    outputs = prepare_outputs(value, arguments.output, arguments.markdown_output)
    if outputs:
        atomic_write_many(outputs)
        print(
            _json_report(
                {
                    "status": "SNAPSHOT_WRITTEN",
                    "snapshot_digest": value["snapshot_digest"],
                    "output": str(Path(arguments.output).absolute()) if arguments.output else None,
                    "markdown_output": str(Path(arguments.markdown_output).absolute())
                    if arguments.markdown_output
                    else None,
                }
            ),
            end="",
        )
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))
    return 0


def _command_verify_local(arguments: argparse.Namespace) -> int:
    if arguments.expected_head and not OID_PATTERN.fullmatch(arguments.expected_head):
        raise ContractError("--expected-head must be a 40-64 character hexadecimal OID")
    configuration = load_config(arguments.config, arguments.repo)
    runner = CommandRunner()
    value = capture_snapshot(arguments.repo, arguments.pr, configuration, runner)
    result = verify_local_against_snapshot(
        value,
        configuration,
        runner,
        arguments.expected_head,
    )
    print(_json_report(result), end="")
    return 0 if not result["blockers"] else 3


def _command_verify_gate(arguments: argparse.Namespace) -> int:
    value = _load_snapshot_file(arguments.snapshot)
    repository = value["repository"]["name_with_owner"]
    configuration = load_config(arguments.config, repository)
    result = verify_snapshot_gate(value, configuration)
    print(_json_report(result), end="")
    return 0 if not result["blockers"] else 3


def _command_render(arguments: argparse.Namespace) -> int:
    value = _load_snapshot_file(arguments.snapshot)
    if arguments.format != "markdown":
        raise ContractError("Only Markdown rendering is supported")
    print(render_markdown(value), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "snapshot":
            return _command_snapshot(arguments)
        if arguments.command == "verify-local":
            return _command_verify_local(arguments)
        if arguments.command == "verify-gate":
            return _command_verify_gate(arguments)
        if arguments.command == "render":
            return _command_render(arguments)
        raise ContractError(f"Unknown command: {arguments.command}")
    except BlockedError as exc:
        print(_json_report(exc.as_dict()), file=sys.stderr, end="")
        return 3
    except (CommandFailure, CommandPolicyError, ContractError, OutputSafetyError, OSError) as exc:
        error = {
            "status": "INVALID_OR_UNSAFE_INPUT",
            "error": redact_diagnostic(str(exc)),
        }
        print(_json_report(error), file=sys.stderr, end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
