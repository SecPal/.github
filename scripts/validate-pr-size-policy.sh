#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

python3 - "$@" <<'PY'
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MANAGED_REPOSITORIES = (
    ".github",
    "api",
    "frontend",
    "contracts",
    "android",
    "GuardGuide",
    "guardguide.de",
    "secpal.app",
)
SKIPPED_PARTS = {
    ".context",
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "tests",
}
SKIPPED_FILES = {"CHANGELOG.md", "package-lock.json"}
TEXT_SUFFIXES = {
    "",
    ".md",
    ".sh",
    ".bash",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".js",
    ".mjs",
    ".ts",
}
SIZE_TERMS = re.compile(
    r"\b(?:changed|changes|total changed|lines?|PR size|threshold|max(?:imum)?|insertions?|deletions?)\b",
    re.IGNORECASE,
)
SIZE_COMPARISON = re.compile(
    r"\bif\b.*(?:-(?:gt|ge|lt|le)\b|[<>]=?)", re.IGNORECASE
)
SIZE_VARIABLE = re.compile(
    r"(?:CHANGED|TOTAL_CHANGES|MAX_LINES|ADVISORY_THRESHOLD|PR_SIZE)",
    re.IGNORECASE,
)
EXIT_OR_RETURN = re.compile(r"\b(?:exit|return)(?:\s+([^;\s]+))?")
FALSE_COMMAND = re.compile(r"(?:^|[;&|]\s*)false(?:\s*(?:[;&|]|$))")


def resolve_repositories(arguments: list[str]) -> list[Path]:
    if not arguments:
        workspace = Path.cwd().resolve().parent
        return [workspace / name for name in MANAGED_REPOSITORIES]

    supplied = [Path(value).resolve() for value in arguments]
    if len(supplied) == 1 and all(
        (supplied[0] / name).is_dir() for name in MANAGED_REPOSITORIES
    ):
        return [supplied[0] / name for name in MANAGED_REPOSITORIES]
    return supplied


def active_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIPPED_PARTS for part in relative.parts):
            continue
        if path.name in SKIPPED_FILES:
            continue
        if relative.as_posix() == "scripts/validate-pr-size-policy.sh":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        result.append(path)
    return sorted(result)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def tracked_context_paths(root: Path) -> list[str] | None:
    if not (root / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", ".context"],
            check=False,
            capture_output=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    try:
        return [
            value
            for value in result.stdout.decode("utf-8").split("\0")
            if value
        ]
    except UnicodeDecodeError:
        return None


def hard_size_exit(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if not SIZE_COMPARISON.search(line) or not SIZE_VARIABLE.search(line):
            continue

        depth = 1
        for candidate in lines[index + 1 : index + 80]:
            stripped = candidate.strip()
            if re.match(r"^if\b.*(?:;\s*then|\bthen)$", stripped):
                depth += 1
            if FALSE_COMMAND.search(stripped):
                return True
            for termination in EXIT_OR_RETURN.finditer(stripped):
                status = termination.group(1)
                if status != "0":
                    return True
            if stripped == "fi":
                depth -= 1
                if depth == 0:
                    break
    return False


def size_bypass_instruction(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if "--no-verify" not in line:
            continue
        if re.search(r"\b(?:never|do not|must not|no)\b", line, re.IGNORECASE):
            continue
        nearby = "\n".join(lines[max(0, index - 8) : index + 9])
        if SIZE_TERMS.search(nearby) and re.search(
            r"(?:use|run|push|skip|bypass|override|recommend)", line, re.IGNORECASE
        ):
            return True
    return False


def validate_repository(root: Path) -> list[str]:
    failures: list[str] = []
    if not root.is_dir():
        return ["repository root is missing"]

    tracked_context = tracked_context_paths(root)
    if tracked_context is None:
        failures.append(".context: unable to verify collaboration-data tracking state")
    elif tracked_context:
        failures.append(
            f".context: collaboration data must remain untracked ({tracked_context[0]})"
        )

    contents = {path: read_text(path) for path in active_files(root)}

    for path, text in contents.items():
        relative = path.relative_to(root).as_posix()
        lines = text.splitlines()

        if ".preflight-allow-large-pr" in text:
            failures.append(f"{relative}: obsolete override-file policy")
        if "large-pr-approved" in text:
            failures.append(f"{relative}: obsolete approval-label policy")
        if re.search(r"Maximum allowed:\s*600", text, re.IGNORECASE):
            failures.append(f"{relative}: hard-maximum wording")
        if re.search(r"PR TOO LARGE", text, re.IGNORECASE):
            failures.append(f"{relative}: hard-failure banner")
        if re.search(r"Push aborted", text, re.IGNORECASE) and SIZE_TERMS.search(text):
            failures.append(f"{relative}: size-based push abortion")
        if hard_size_exit(lines):
            failures.append(f"{relative}: size-triggered nonzero exit")
        if size_bypass_instruction(lines):
            failures.append(f"{relative}: size-policy hook bypass instruction")

    preflight = root / "scripts/preflight.sh"
    preflight_text = read_text(preflight) if preflight.is_file() else ""
    has_local_size_calculation = "--numstat" in preflight_text and bool(
        re.search(r"(?:PR_SIZE|MAX_LINES|ADVISORY_THRESHOLD)", preflight_text)
    )
    if has_local_size_calculation:
        required_fragments = {
            "advisory threshold": "advisory-threshold reporting",
            "INSERTIONS": "insertion reporting",
            "DELETIONS": "deletion reporting",
            "WARNING": "above-threshold warning",
        }
        for fragment, description in required_fragments.items():
            if fragment not in preflight_text:
                failures.append(f"scripts/preflight.sh: missing {description}")

    workflow = root / ".github/workflows/pr-size.yml"
    workflow_text = read_text(workflow) if workflow.is_file() else ""
    if workflow_text:
        if "pull-requests: read" in workflow_text:
            failures.append(
                ".github/workflows/pr-size.yml: unused pull-request permission"
            )
        for reference in re.findall(
            r"SecPal/\.github/\.github/workflows/reusable-pr-size\.yml@([^\s]+)",
            workflow_text,
        ):
            if not re.fullmatch(r"[0-9a-f]{40}", reference):
                failures.append(
                    ".github/workflows/pr-size.yml: reusable workflow is not pinned to an immutable SHA"
                )

    reusable = root / ".github/workflows/reusable-pr-size.yml"
    reusable_text = read_text(reusable) if reusable.is_file() else ""
    if reusable_text:
        required_fragments = {
            "git diff --numstat": "locale-independent changed-line calculation",
            "INSERTIONS": "insertion reporting",
            "DELETIONS": "deletion reporting",
            "::warning::": "advisory GitHub warning",
            "Advisory changed-line threshold": "advisory max-lines contract",
        }
        for fragment, description in required_fragments.items():
            if fragment not in reusable_text:
                failures.append(
                    f".github/workflows/reusable-pr-size.yml: missing {description}"
                )

    return sorted(set(failures))


def main() -> int:
    failed = False
    for root in resolve_repositories(sys.argv[1:]):
        failures = validate_repository(root)
        if failures:
            failed = True
            print(f"{root.name}: FAIL - {'; '.join(failures)}")
        else:
            print(f"{root.name}: PASS")
    return 1 if failed else 0


raise SystemExit(main())
PY
