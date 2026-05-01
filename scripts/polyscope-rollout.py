#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import urllib.request
from datetime import datetime, timezone
from typing import Any


REPO_SETTINGS: dict[str, dict[str, Any]] = {
    "api": {
        "display_name": "SecPal/api",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [".github/instructions/php-laravel.instructions.md"],
        "preview_prefix": "api",
        "review_focus": "Laravel 13, Pest 4, Request -> Controller -> Service -> Repository -> Model, Sanctum session versus bearer-token flows, and encrypted data handling via *_plain/*_idx without direct *_enc reads.",
        "link_names": ["frontend", "contracts", "android"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": "https://api-{{folder}}.preview.secpal.dev"},
            "scripts": {
                "setup": [
                    "test -d vendor || composer install",
                ],
                "run": [
                    {"label": "Queue Worker", "command": "php artisan queue:listen --tries=1", "runMode": "replace"},
                    {"label": "Pail", "command": "php artisan pail --timeout=0", "runMode": "replace"},
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
        "focus_instruction_paths": [".github/instructions/react-typescript.instructions.md"],
        "preview_prefix": "frontend",
        "review_focus": "React, Vite, strict TypeScript, generated API types, Testing Library/MSW boundaries, auth-storage discipline, and transport failure handling.",
        "link_names": ["api", "contracts", "android"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": "https://frontend-{{folder}}.preview.secpal.dev"},
            "scripts": {
                "setup": ["test -d node_modules || npm ci", "npm run build"],
                "run": [
                    {"label": "Build Watch", "command": "npx vite build --watch", "autostart": True, "runMode": "replace"},
                    {"label": "Lint", "command": "npm run lint", "runMode": "preserve"},
                    {"label": "Typecheck", "command": "npm run typecheck", "runMode": "preserve"},
                    {"label": "Vitest", "command": "npm run test:watch", "runMode": "replace"},
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
    "contracts": {
        "display_name": "SecPal/contracts",
        "base_branch": "main",
        "copilot_instructions": ".github/copilot-instructions.md",
        "focus_instruction_paths": [".github/instructions/openapi.instructions.md"],
        "preview_prefix": None,
        "review_focus": "OpenAPI 3.1 as contract-first source of truth, reusable $ref schemas, consistent security schemes, complete response coverage, and Redocly validation.",
        "link_names": ["api", "frontend"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "scripts": {
                "setup": ["test -d node_modules || npm ci"],
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
        "focus_instruction_paths": [".github/instructions/react-capacitor.instructions.md"],
        "preview_prefix": None,
        "review_focus": "React plus Capacitor bridge boundaries, managed-mode and device-owner semantics, listener cleanup through remove(), and strict TypeScript around native interop.",
        "link_names": ["api", "frontend"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "scripts": {
                "setup": ["test -d node_modules || npm ci"],
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
        "focus_instruction_paths": [".github/instructions/astro-static.instructions.md"],
        "preview_prefix": "secpal-app",
        "review_focus": "Astro static rendering, minimal client-side JavaScript, semantic HTML, accessible landmarks, and strict TypeScript on the public site.",
        "link_names": ["changelog"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": "https://secpal-app-{{folder}}.preview.secpal.dev"},
            "scripts": {
                "setup": ["test -d node_modules || npm ci", "npm run build"],
                "run": [
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
        "focus_instruction_paths": [".github/instructions/nextjs-changelog.instructions.md"],
        "preview_prefix": "changelog",
        "review_focus": "Next.js static-style changelog output, MDX content rules, Commit template conventions, CSP/feed safety, and no server-side runtime dependencies.",
        "link_names": ["secpal.app"],
        "local_config": {
            "copyGitignored": True,
            "runMode": "replace",
            "preview": {"url": "https://changelog-{{folder}}.preview.secpal.dev"},
            "scripts": {
                "setup": ["test -d node_modules || npm ci", "npm run build"],
                "run": [
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
                "setup": ["test -d node_modules || npm ci"],
                "run": [
                    {"label": "Preflight", "command": "./scripts/preflight.sh", "runMode": "preserve"},
                    {"label": "Copilot Review Scan", "command": "npm run copilot:review:scan", "runMode": "preserve"},
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
        spec["copilot_instructions"] = repo_path / settings["copilot_instructions"]
        spec["focus_instruction_paths"] = [repo_path / path for path in settings["focus_instruction_paths"]]
        repo_specs[repo_name] = spec
    return repo_specs


def instruction_reference(spec: dict[str, Any]) -> str:
    refs = [str(spec["copilot_instructions"])]
    refs.extend(str(path) for path in spec["focus_instruction_paths"])
    return "; ".join(refs)


def build_prompt_bundle(spec: dict[str, Any]) -> dict[str, str]:
    copilot_text = pathlib.Path(spec["copilot_instructions"]).read_text()
    sections = parse_sections(copilot_text)
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
        f"Non-negotiable rules: {format_bullets(always_on)}. "
        f"Repository focus: {spec['review_focus']} "
        f"Targeted file-scope rules: {format_bullets(focus)}. "
        f"Review and AI-triage bar: {format_bullets(triage)}. "
        "If shared auth, contract, mobile, or release behavior crosses repo boundaries, pull the relevant linked workspaces before proposing changes."
    )
    pr_prompt = collapse_spaces(
        f"Write a concise English PR body for {spec['display_name']}. Apply {instruction_ref}. "
        f"Keep the PR to one topic and reflect the PR discipline: {format_bullets(issue_pr)}. "
        "Lead with the failing test, validation, or reproduced defect. Then summarize the user-, API-, contract-, or governance-visible change, the validations run, CHANGELOG impact, linked-repo impact, and any out-of-scope issues filed."
    )
    draft_pr_prompt = collapse_spaces(
        f"Create a draft PR in English for {spec['display_name']}. Apply {instruction_ref}. "
        f"Keep one topic per branch and follow: {format_bullets(issue_pr)}. "
        "Lead with the failing test, validation, or reproduced defect, summarize the current change and validations already run, and note any linked workspaces or unresolved checks that still need follow-up before marking the PR ready."
    )
    merge_prompt = collapse_spaces(
        f"Before merge for {spec['display_name']}, stop on the first failed check and enforce the current SecPal instructions from {instruction_ref}. "
        f"Required validation gate: {format_bullets(validation)}. "
        f"Also enforce: {format_bullets(select_bullets(always_on, ['one topic', 'bypass', 'changelog', 'issue immediately'], 4))}."
    )
    merge_and_push_prompt = collapse_spaces(
        f"Before push and merge for {spec['display_name']}, apply {instruction_ref}. "
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
    preamble = collapse_spaces(f"Apply the current SecPal instructions from {instruction_reference(spec)} before taking action.")
    for task in config.get("tasks", []):
        task["prompt"] = collapse_spaces(f"{preamble} {task['prompt']}")
    return config


def prefix_first_line(prefix: str, text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return prefix

    lines[0] = prefix + lines[0]
    return "\n".join(lines)


def render_pretty_json(value: Any, indent: int = 0) -> str:
    current_indent = "  " * indent
    next_indent = "  " * (indent + 1)

    if isinstance(value, dict):
        if not value:
            return "{}"

        items = list(value.items())
        lines: list[str] = []
        for index, (key, nested_value) in enumerate(items):
            rendered_value = render_pretty_json(nested_value, indent + 1)
            line = prefix_first_line(f"{next_indent}{json.dumps(key)}: ", rendered_value)
            if index < len(items) - 1:
                line += ","
            lines.append(line)

        return "{\n" + "\n".join(lines) + f"\n{current_indent}" + "}"

    if isinstance(value, list):
        if not value:
            return "[]"

        rendered_items = [render_pretty_json(item, indent + 1) for item in value]
        inline_candidate = "[" + ", ".join(rendered_items) + "]"
        if all("\n" not in item for item in rendered_items) and len(current_indent) + len(inline_candidate) <= 80:
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

    package_data = json.loads(package_json_path.read_text())
    scripts = package_data.get("scripts", {})
    if not isinstance(scripts, dict):
        return set()

    return {str(script_name) for script_name in scripts}


def validate_local_config_command(repo_name: str, repo_path: pathlib.Path, package_scripts: set[str], command: str) -> None:
    package_json_path = repo_path / "package.json"
    package_lock_path = repo_path / "package-lock.json"
    composer_json_path = repo_path / "composer.json"
    artisan_path = repo_path / "artisan"

    if re.search(r"\bcomposer\s+install\b", command) and not composer_json_path.exists():
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

    if relative_path_token is not None and not (repo_path / relative_path_token[2:]).exists():
        raise SystemExit(f"{repo_name} polyscope config references missing relative path '{relative_path_token}'")


def validate_repo_local_configs(repo_specs: dict[str, dict[str, Any]]) -> None:
    for repo_name, spec in repo_specs.items():
        repo_path = pathlib.Path(spec["path"])
        config = render_local_config(spec)
        package_scripts = load_package_scripts(repo_path)

        for command in config.get("scripts", {}).get("setup", []):
            validate_local_config_command(repo_name, repo_path, package_scripts, command)

        for item in config.get("scripts", {}).get("run", []):
            command = item.get("command")
            if isinstance(command, str):
                validate_local_config_command(repo_name, repo_path, package_scripts, command)


def ensure_exclude(repo_path: pathlib.Path) -> None:
    exclude_path = repo_path / ".git" / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text() if exclude_path.exists() else ""
    if "polyscope.local.json" not in {line.strip() for line in existing.splitlines()}:
        with exclude_path.open("a") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("polyscope.local.json\n")


def write_local_configs(repo_specs: dict[str, dict[str, Any]]) -> None:
    for spec in repo_specs.values():
        repo_path = pathlib.Path(spec["path"])
        config_path = repo_path / "polyscope.local.json"
        config_path.write_text(render_pretty_json(render_local_config(spec)) + "\n")
        ensure_exclude(repo_path)


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
    if not db_path.exists():
        raise SystemExit(f"Polyscope DB not found at {db_path}; start Polyscope at least once so the DB is created before running this script")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.parent / f"{db_path.name}.backup-{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def sync_repository_metadata(db_path: pathlib.Path, repo_state: dict[str, dict[str, Any]], repo_specs: dict[str, dict[str, Any]]) -> pathlib.Path:
    backup_path = backup_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    managed_repo_ids = [repo_state[name]["id"] for name in REPO_SETTINGS]
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

        prompts = build_prompt_bundle(spec)
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
            (
                prompts["review_prompt"],
                prompts["pr_prompt"],
                prompts["draft_pr_prompt"],
                prompts["merge_prompt"],
                prompts["merge_and_push_prompt"],
                repo_id,
            ),
        )

    conn.commit()
    conn.close()
    return backup_path


def render_nginx_config(repo_state: dict[str, dict[str, Any]]) -> str:
    api_id = repo_state["api"]["id"]
    frontend_id = repo_state["frontend"]["id"]
    secpal_app_id = repo_state["secpal.app"]["id"]
    changelog_id = repo_state["changelog"]["id"]
    return textwrap.dedent(
        f"""
        server {{
            listen 80;
            listen [::]:80;
            server_name ~^(?<repo>api|frontend|secpal-app|changelog)-(?<workspace>[a-z0-9][a-z0-9-]*)\\.preview\\.secpal\\.dev$;

            location /.well-known/acme-challenge/ {{
                root /var/www/certbot;
            }}

            return 301 https://$host$request_uri;
        }}

        server {{
            listen 443 ssl;
            listen [::]:443 ssl;
            server_name ~^(?<repo>api|frontend|secpal-app|changelog)-(?<workspace>[a-z0-9][a-z0-9-]*)\\.preview\\.secpal\\.dev$;

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
            set $secpal_app_root /home/secpal/.polyscope/clones/{secpal_app_id}/$workspace;
            set $secpal_app_dist $secpal_app_root/dist;
            set $changelog_root /home/secpal/.polyscope/clones/{changelog_id}/$workspace;
            set $changelog_out $changelog_root/out;
            set $preview_docroot /home/secpal/.polyscope/empty;
            set $route_mode static;

            if ($repo = api) {{
                set $preview_docroot $api_public;
                set $route_mode api;
            }}

            if ($repo = frontend) {{
                set $preview_docroot $frontend_dist;
            }}

            if ($repo = secpal-app) {{
                set $preview_docroot $secpal_app_dist;
            }}

            if ($repo = changelog) {{
                set $preview_docroot $changelog_out;
            }}

            root $preview_docroot;

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
                try_files $uri $uri/ @preview_router;
            }}

            location @preview_router {{
                if ($route_mode = api) {{
                    rewrite ^ /index.php last;
                }}

                try_files /index.html =404;
            }}

            location = /index.php {{
                if (!-f $api_public/index.php) {{
                    return 404;
                }}

                include snippets/fastcgi-php.conf;
                fastcgi_pass unix:/run/php/php8.4-fpm-secpal-api.sock;
                fastcgi_param SCRIPT_FILENAME $api_public/index.php;
                fastcgi_param DOCUMENT_ROOT $api_public;
                fastcgi_param HTTP_HOST $host;
            }}

            location ~ \\.php$ {{
                return 404;
            }}
        }}
        """
    ).strip() + "\n"


def build_summary(repo_state: dict[str, dict[str, Any]], repo_specs: dict[str, dict[str, Any]], db_backup: pathlib.Path | None, nginx_output: pathlib.Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "db_backup": str(db_backup) if db_backup is not None else None,
        "rendered_nginx_config": str(nginx_output),
        "repositories": {},
    }
    for repo_name, spec in repo_specs.items():
        prompts = build_prompt_bundle(spec)
        summary["repositories"][repo_name] = {
            "id": repo_state[repo_name]["id"],
            "path": str(spec["path"]),
            "copilot_instructions": str(spec["copilot_instructions"]),
            "focus_instruction_paths": [str(path) for path in spec["focus_instruction_paths"]],
            "linked_repositories": spec["link_names"],
            "preview_prefix": spec["preview_prefix"],
            "review_prompt_excerpt": prompts["review_prompt"][:280],
        }
    return summary


def install_nginx_config(nginx_output: pathlib.Path) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_target = f"/etc/nginx/sites-available/preview.secpal.dev.bak-{timestamp}"
    subprocess.run(["sudo", "cp", "/etc/nginx/sites-available/preview.secpal.dev", backup_target], check=True)
    subprocess.run(["sudo", "install", "-m", "644", str(nginx_output), "/etc/nginx/sites-available/preview.secpal.dev"], check=True)
    subprocess.run(["sudo", "nginx", "-t"], check=True)
    subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync SecPal Polyscope prompts, links, and preview config.")
    parser.add_argument("--workspace-root", type=pathlib.Path, default=pathlib.Path.home() / "code" / "SecPal")
    parser.add_argument("--db-path", type=pathlib.Path, default=pathlib.Path.home() / ".polyscope" / "polyscope.db")
    parser.add_argument("--polyscope-api-base", default="http://127.0.0.1:4321/api")
    parser.add_argument("--repo-state-file", type=pathlib.Path)
    parser.add_argument("--nginx-output", type=pathlib.Path, default=pathlib.Path.home() / "copilot-preview-secpal-dev.nginx.conf")
    parser.add_argument("--summary-output", type=pathlib.Path)
    parser.add_argument("--skip-local-configs", action="store_true")
    parser.add_argument("--skip-db-sync", action="store_true")
    parser.add_argument("--install-nginx", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_specs = build_repo_specs(args.workspace_root)

    validate_repo_local_configs(repo_specs)

    if not args.skip_local_configs:
        write_local_configs(repo_specs)

    if args.repo_state_file is not None:
        repo_state = load_repo_state(args.repo_state_file)
    else:
        repo_state = ensure_repositories_registered(args.polyscope_api_base, repo_specs)

    db_backup: pathlib.Path | None = None
    if not args.skip_db_sync:
        db_backup = sync_repository_metadata(args.db_path, repo_state, repo_specs)

    args.nginx_output.write_text(render_nginx_config(repo_state))

    if args.install_nginx:
        install_nginx_config(args.nginx_output)

    summary = build_summary(repo_state, repo_specs, db_backup, args.nginx_output)
    if args.summary_output is not None:
        args.summary_output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
