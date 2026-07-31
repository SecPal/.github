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
SIZE_COMPARISON = re.compile(r"(?:-(?:gt|ge|lt|le)\b|[<>]=?)", re.IGNORECASE)
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
POLICY_ROOTS = {".githooks", ".github", ".husky", "scripts"}
SHELL_SHEBANG = re.compile(rb"^#![^\r\n]*\b(?:ba|da|k|z)?sh\b")
SHELL_ERREXIT_ENABLE = re.compile(
    r"^\s*set\s+(?:-[A-Za-z]*e[A-Za-z]*|-o\s+errexit)(?:\s|$)"
)
SHELL_ERREXIT_DISABLE = re.compile(
    r"^\s*set\s+(?:\+[A-Za-z]*e[A-Za-z]*|\+o\s+errexit)(?:\s|$)"
)
SHELL_TEST_COMMAND = re.compile(r"^\s*!?\s*(?:test\b|\[\[?(?:\s|$)|\(\()")


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


def suffixless_shell_policy(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if not relative.parts or relative.parts[0] not in POLICY_ROOTS:
        return False
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(512)
    except OSError:
        return True
    return SHELL_SHEBANG.search(first_line) is not None


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
        if path.suffix.lower() not in TEXT_SUFFIXES and not (
            path.suffix == "" and suffixless_shell_policy(root, path)
        ):
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


def size_comparison(value: str) -> bool:
    return SIZE_COMPARISON.search(value) is not None and SIZE_VARIABLE.search(
        value
    ) is not None


def shell_failure_command(value: str) -> bool:
    if FALSE_COMMAND.search(value):
        return True
    for termination in EXIT_OR_RETURN.finditer(value):
        status = termination.group(1)
        if status is None:
            prefix = value[: termination.start()].rstrip()
            if prefix.endswith("||"):
                return True
            continue
        if nonzero_status(status, empty_is_failure=False):
            return True
    return False


def shell_logical_command(lines: list[str], index: int) -> str:
    command = lines[index].strip()
    for candidate in lines[index + 1 : index + 8]:
        if not re.search(r"(?:\\|&&|\|\|)\s*$", command):
            break
        command = re.sub(r"\\\s*$", "", command)
        command = f"{command} {candidate.strip()}"
    return command


def shell_errexit_comparison(
    value: str, enabled: bool
) -> tuple[bool, bool]:
    for command in re.split(r"[;\n]", value):
        if SHELL_ERREXIT_DISABLE.search(command):
            enabled = False
        elif SHELL_ERREXIT_ENABLE.search(command):
            enabled = True
        if (
            enabled
            and size_comparison(command)
            and SHELL_TEST_COMMAND.search(command)
            and "&&" not in command
            and "||" not in command
        ):
            return enabled, True
    return enabled, False


def shell_hard_size_exit(
    lines: list[str], *, errexit_default: bool = False
) -> bool:
    errexit_enabled = errexit_default
    for index, line in enumerate(lines):
        logical_command = shell_logical_command(lines, index)
        errexit_enabled, errexit_failure = shell_errexit_comparison(
            logical_command, errexit_enabled
        )
        if errexit_failure:
            return True
        if not size_comparison(logical_command):
            continue

        if (
            "&&" in logical_command or "||" in logical_command
        ) and shell_failure_command(logical_command):
            return True

        if not re.search(r"\bif\b", logical_command, re.IGNORECASE):
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
            if shell_failure_command(stripped):
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
        if not re.search(r"\bif\b", line) or not size_comparison(line):
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
        if not re.search(r"\bif\b", line) or not size_comparison(line):
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

    policy_root = bool(parts) and parts[0] in POLICY_ROOTS
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


def workflow_steps(lines: list[str]) -> list[list[str]]:
    steps: list[list[str]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)steps:\s*(?:#.*)?$", lines[index])
        if match is None:
            index += 1
            continue
        steps_indent = len(match.group(1))
        index += 1
        current: list[str] = []
        item_indent: int | None = None
        while index < len(lines):
            line = lines[index]
            if line.strip():
                indent = len(line) - len(line.lstrip())
                if indent <= steps_indent:
                    break
                item = re.match(r"^(\s*)-\s+(.*)$", line)
                if item is not None and (
                    item_indent is None or len(item.group(1)) == item_indent
                ):
                    if current:
                        steps.append(current)
                    item_indent = len(item.group(1))
                    current = [" " * (item_indent + 2) + item.group(2)]
                    index += 1
                    continue
            if current:
                current.append(line)
            index += 1
        if current:
            steps.append(current)
    return steps


def workflow_step_shell_units(step: list[str]) -> list[list[str]]:
    size_conditions = [
        match.group(1)
        for line in step
        if (
            match := re.match(r"^\s*if:\s*(.*?)\s*(?:#.*)?$", line)
        )
        and size_comparison(match.group(1))
    ]
    units: list[list[str]] = []
    for index, line in enumerate(step):
        match = re.match(r"^(\s*)run:\s*(.*)$", line)
        if match is None:
            continue
        run_indent = len(match.group(1))
        scalar = match.group(2).strip()
        if re.fullmatch(r"[|>][-+]?", scalar):
            block: list[str] = []
            for candidate in step[index + 1 :]:
                if candidate.strip():
                    indent = len(candidate) - len(candidate.lstrip())
                    if indent <= run_indent:
                        break
                block.append(candidate)
        else:
            block = [scalar.strip("\"'")]
        condition_lines = [f"if {condition}" for condition in size_conditions]
        units.append(condition_lines + block)
    return units


def workflow_shell_units(text: str) -> list[list[str]]:
    return [
        unit
        for step in workflow_steps(text.splitlines())
        for unit in workflow_step_shell_units(step)
    ]


def hard_size_exit(root: Path, path: Path, text: str) -> bool:
    language = policy_language(root, path, text)
    lines = text.splitlines()
    if language == "shell":
        relative = path.relative_to(root)
        if (
            len(relative.parts) >= 3
            and relative.parts[:2] == (".github", "workflows")
            and path.suffix.lower() in {".yml", ".yaml"}
        ):
            return any(
                shell_hard_size_exit(unit, errexit_default=True)
                for unit in workflow_shell_units(text)
            )
        return shell_hard_size_exit(lines)
    if language == "python":
        return python_hard_size_exit(lines)
    if language == "javascript":
        return javascript_hard_size_exit(lines)
    return False


def reusable_workflow_contract_failures(text: str) -> list[str]:
    failures: list[str] = []
    required_fragments = {
        "git diff --numstat": "locale-independent changed-line calculation",
        "INSERTIONS": "insertion reporting",
        "DELETIONS": "deletion reporting",
        "::warning::": "advisory GitHub warning",
        "Advisory changed-line threshold": "advisory max-lines contract",
    }
    for fragment, description in required_fragments.items():
        if fragment not in text:
            failures.append(f"missing {description}")
    if "pull-requests: read" in text:
        failures.append("unused pull-request permission")
    if ".preflight-allow-large-pr" in text or "large-pr-approved" in text:
        failures.append("obsolete size override")
    if any(
        shell_hard_size_exit(unit, errexit_default=True)
        for unit in workflow_shell_units(text)
    ):
        failures.append("size-triggered nonzero exit")
    return sorted(set(failures))


def governance_root(repositories: list[Path]) -> Path | None:
    candidates = [
        root
        for root in repositories
        if (root / ".git").exists()
        and (root / ".github/workflows/reusable-pr-size.yml").is_file()
    ]
    return candidates[0] if len(candidates) == 1 else None


def pinned_workflow_contract_failures(
    root: Path | None, revision: str
) -> list[str]:
    if root is None:
        return ["reusable workflow advisory contract cannot be verified"]
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "show",
                f"{revision}:.github/workflows/reusable-pr-size.yml",
            ],
            check=False,
            capture_output=True,
        )
    except OSError:
        return ["reusable workflow advisory contract cannot be verified"]
    if result.returncode != 0:
        return ["reusable workflow revision is unavailable for contract validation"]
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return ["reusable workflow revision is not readable UTF-8"]
    return reusable_workflow_contract_failures(text)


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


def validate_repository(
    root: Path,
    workflow_source: Path | None,
    workflow_contract_cache: dict[str, list[str]],
) -> list[str]:
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
                continue
            contract_failures = workflow_contract_cache.setdefault(
                reference,
                pinned_workflow_contract_failures(workflow_source, reference),
            )
            if contract_failures:
                failures.append(
                    f"{relative.as_posix()}: pinned reusable workflow violates the advisory contract "
                    f"({', '.join(contract_failures)})"
                )

    reusable = root / ".github/workflows/reusable-pr-size.yml"
    reusable_text = contents.get(reusable, "")
    if reusable_text:
        for description in reusable_workflow_contract_failures(reusable_text):
            failures.append(
                f".github/workflows/reusable-pr-size.yml: {description}"
            )

    return sorted(set(failures))


def main() -> int:
    failed = False
    repositories = resolve_repositories(sys.argv[1:])
    workflow_source = governance_root(repositories)
    workflow_contract_cache: dict[str, list[str]] = {}
    for root in repositories:
        failures = validate_repository(
            root, workflow_source, workflow_contract_cache
        )
        if failures:
            failed = True
            print(f"{root.name}: FAIL - {'; '.join(failures)}")
        else:
            print(f"{root.name}: PASS")
    return 1 if failed else 0


raise SystemExit(main())
PY
