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
    ".cjs",
    ".mjs",
    ".py",
    ".ts",
}
SIZE_TERMS = re.compile(
    r"\b(?:changed|changes|total changed|lines?|PR size|threshold|max(?:imum)?|insertions?|deletions?)\b",
    re.IGNORECASE,
)
SIZE_POLICY_CONTEXT = re.compile(
    r"(?:\bPR[- ]?size\b|\bchanged[- ]lines?\b|\bsize[- ](?:limit|threshold)\b|"
    r"\badvisory[- ]threshold\b|\b(?:CHANGED|TOTAL_CHANGES|MAX_LINES|PR_SIZE)\b)",
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
PYTHON_EXIT = re.compile(
    r"(?:sys\.exit\s*\(\s*([^)]*)\)|raise\s+SystemExit(?:\s*\(\s*([^)]*)\)|\s+([^;\s]+))?)"
)
JAVASCRIPT_EXIT = re.compile(
    r"(?:process|Deno|Bun)\.exit\s*\(\s*([^)]*)\)"
)


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
    return path.read_text(encoding="utf-8")


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


def nonzero_status(status: str | None, *, empty_is_failure: bool) -> bool:
    if status is None or not status.strip():
        return empty_is_failure
    normalized = status.strip().strip("\"'")
    return re.fullmatch(r"\+?0+", normalized) is None


def shell_hard_size_exit(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if not SIZE_COMPARISON.search(line) or not SIZE_VARIABLE.search(line):
            continue

        depth = 0
        opened = False
        for candidate in lines[index : index + 80]:
            stripped = candidate.strip()
            openings = len(
                re.findall(r"(?:^|;\s*)if\b.*?(?:;\s*then\b|\bthen\b)", stripped)
            )
            if openings:
                depth += openings
                opened = True
            if FALSE_COMMAND.search(stripped):
                return True
            for termination in EXIT_OR_RETURN.finditer(stripped):
                if nonzero_status(termination.group(1), empty_is_failure=True):
                    return True
            if opened:
                depth -= len(re.findall(r"\bfi\b", stripped))
                if depth <= 0:
                    break
    return False


def indentation_block(lines: list[str], index: int) -> list[str]:
    condition = lines[index]
    condition_indent = len(condition) - len(condition.lstrip())
    result = [condition]
    for candidate in lines[index + 1 : index + 80]:
        if not candidate.strip():
            result.append(candidate)
            continue
        indent = len(candidate) - len(candidate.lstrip())
        if indent <= condition_indent:
            break
        result.append(candidate)
    return result


def python_hard_size_exit(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if not SIZE_COMPARISON.search(line) or not SIZE_VARIABLE.search(line):
            continue
        for candidate in indentation_block(lines, index):
            for termination in PYTHON_EXIT.finditer(candidate):
                status = next(
                    (
                        value
                        for value in termination.groups()
                        if value is not None
                    ),
                    None,
                )
                if nonzero_status(status, empty_is_failure=False):
                    return True
    return False


def javascript_block(lines: list[str], index: int) -> list[str]:
    condition = lines[index]
    result = [condition]
    depth = condition.count("{") - condition.count("}")
    if depth <= 0:
        return indentation_block(lines, index)
    for candidate in lines[index + 1 : index + 80]:
        result.append(candidate)
        depth += candidate.count("{") - candidate.count("}")
        if depth <= 0:
            break
    return result


def javascript_hard_size_exit(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if not SIZE_COMPARISON.search(line) or not SIZE_VARIABLE.search(line):
            continue
        for candidate in javascript_block(lines, index):
            for termination in JAVASCRIPT_EXIT.finditer(candidate):
                if nonzero_status(termination.group(1), empty_is_failure=False):
                    return True
    return False


def policy_language(root: Path, path: Path, text: str) -> str | None:
    relative = path.relative_to(root)
    parts = relative.parts
    suffix = path.suffix.lower()
    if (
        len(parts) >= 3
        and parts[:2] == (".github", "workflows")
        and suffix in {".yml", ".yaml"}
    ):
        return "shell"

    policy_root = bool(parts) and parts[0] in {
        ".githooks",
        ".github",
        ".husky",
        "scripts",
    }
    if not policy_root:
        return None
    if suffix in {".sh", ".bash", ".yml", ".yaml"}:
        return "shell"
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".cjs", ".mjs", ".ts"}:
        return "javascript"
    if suffix == "" and re.match(r"^#!.*\b(?:ba|da|k|z)?sh\b", text):
        return "shell"
    return None


def hard_size_exit(root: Path, path: Path, text: str) -> bool:
    language = policy_language(root, path, text)
    lines = text.splitlines()
    if language == "shell":
        return shell_hard_size_exit(lines)
    if language == "python":
        return python_hard_size_exit(lines)
    if language == "javascript":
        return javascript_hard_size_exit(lines)
    return False


def size_bypass_instruction(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if "--no-verify" not in line:
            continue
        if re.search(
            r"\b(?:never|do not|must not|should not|don't)\b",
            line,
            re.IGNORECASE,
        ):
            continue
        nearby = "\n".join(lines[max(0, index - 8) : index + 9])
        if SIZE_POLICY_CONTEXT.search(nearby) and re.search(
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

    contents: dict[Path, str] = {}
    for path in active_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            contents[path] = read_text(path)
        except (OSError, UnicodeDecodeError):
            failures.append(f"{relative}: unable to read as UTF-8")

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
        if hard_size_exit(root, path, text):
            failures.append(f"{relative}: size-triggered nonzero exit")
        if size_bypass_instruction(lines):
            failures.append(f"{relative}: size-policy hook bypass instruction")

    preflight = root / "scripts/preflight.sh"
    preflight_text = contents.get(preflight, "")
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

    for workflow, workflow_text in contents.items():
        relative = workflow.relative_to(root)
        if (
            len(relative.parts) < 3
            or relative.parts[:2] != (".github", "workflows")
            or workflow.suffix.lower() not in {".yml", ".yaml"}
        ):
            continue
        references = re.findall(
            r"SecPal/\.github/\.github/workflows/reusable-pr-size\.yml@([^\s\"']+)",
            workflow_text,
        )
        is_size_workflow = bool(references) or (
            "git diff --numstat" in workflow_text
            and re.search(r"\bPR[- ]?size\b", workflow_text, re.IGNORECASE)
        )
        if "pull-requests: read" in workflow_text and is_size_workflow:
            failures.append(
                f"{relative.as_posix()}: unused pull-request permission"
            )
        for reference in references:
            if not re.fullmatch(r"[0-9a-f]{40}", reference):
                failures.append(
                    f"{relative.as_posix()}: reusable workflow is not pinned to an immutable SHA"
                )

    reusable = root / ".github/workflows/reusable-pr-size.yml"
    reusable_text = contents.get(reusable, "")
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
