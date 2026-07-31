#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

python3 - "$SCRIPT_DIR/parse-pr-size-workflow.cjs" "$@" <<'PY'
from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
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
EXPLICIT_SIZE_CONTEXT = re.compile(
    r"(?:\bPR[- ]?size\b|\bchanged[- ]lines?\b|\bsize[- ](?:limit|threshold)\b|"
    r"\badvisory[- ]threshold\b)",
    re.IGNORECASE,
)
SIZE_COMPARISON = re.compile(r"(?:-(?:gt|ge|lt|le)\b|[<>]=?)", re.IGNORECASE)
IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
ASSIGNMENT = re.compile(
    r"^\s*(?:(?:export|local|readonly)\s+)?"
    r"(?:(?:const|let|var)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)(.*)$"
)
SIZE_CALCULATION = re.compile(
    r"(?:git\s+diff\b[\s\S]{0,400}?--numstat|"
    r"--numstat[\s\S]{0,400}?\bgit\s+diff\b)",
    re.IGNORECASE,
)
FALSE_COMMAND = re.compile(r"(?:^|[;&|]\s*)false(?:\s*(?:[;&|]|$))")
POLICY_ROOTS = {".githooks", ".github", ".husky", "scripts"}
SHELL_SHEBANG = re.compile(rb"^#![^\r\n]*\b(?:ba|da|k|z)?sh\b")
SHELL_ERREXIT_ENABLE = re.compile(
    r"^\s*set\s+(?:-[A-Za-z]*e[A-Za-z]*|-o\s+errexit)(?:\s|$)"
)
SHELL_ERREXIT_DISABLE = re.compile(
    r"^\s*set\s+(?:\+[A-Za-z]*e[A-Za-z]*|\+o\s+errexit)(?:\s|$)"
)
SHELL_TEST_COMMAND = re.compile(r"^\s*!?\s*(?:test\b|\[\[?(?:\s|$)|\(\()")
WORKFLOW_PARSER = Path(sys.argv[1]).resolve()


class PolicyParseError(RuntimeError):
    pass


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


def python_nonzero_status(
    status: str | None, *, empty_is_failure: bool
) -> bool:
    if status is None or not status.strip():
        return empty_is_failure
    if status.strip().strip("\"'") in {"0", "None", "False"}:
        return False
    return nonzero_status(status, empty_is_failure=empty_is_failure)


def canonical_identifier(value: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).lower()


def semantic_size_identifier(value: str) -> bool:
    normalized = canonical_identifier(value)
    if value == "CHANGED":
        return True
    return re.fullmatch(
        r"(?:changed_lines?|total_changes?|"
        r"diff_(?:size|lines?|count|changes?)|pr_size|"
        r"insertions?|deletions?|advisory_threshold|max_lines?)",
        normalized,
    ) is not None


def assignment_expressions(lines: list[str]) -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        match = ASSIGNMENT.match(lines[index])
        if match is None:
            index += 1
            continue
        expression = match.group(2)
        depth = expression.count("(") - expression.count(")")
        while (
            index + 1 < len(lines)
            and len(expression.splitlines()) < 40
            and (depth > 0 or expression.rstrip().endswith("\\"))
        ):
            index += 1
            expression = f"{expression}\n{lines[index]}"
            depth = expression.count("(") - expression.count(")")
        assignments.append((match.group(1).lower(), expression))
        index += 1
    return assignments


@dataclass(frozen=True)
class SizeContext:
    identifiers: frozenset[str]

    @classmethod
    def from_lines(cls, lines: list[str]) -> SizeContext:
        assignments = assignment_expressions(lines)
        source = "\n".join(lines)
        explicit_context = EXPLICIT_SIZE_CONTEXT.search(source) is not None
        diff_changed_context = re.search(
            r"\bdiff\b[^\n]{0,120}\bchanged\b", source, re.IGNORECASE
        ) is not None
        identifiers = {
            name.lower()
            for line in lines
            for name in IDENTIFIER.findall(line)
            if semantic_size_identifier(name)
            or (
                canonical_identifier(name) in {"changed", "changes"}
                and (explicit_context or diff_changed_context)
            )
        }
        changed = True
        while changed:
            changed = False
            for target, expression in assignments:
                references = {
                    name.lower() for name in IDENTIFIER.findall(expression)
                }
                if (
                    SIZE_CALCULATION.search(expression)
                    or references.intersection(identifiers)
                ) and target not in identifiers:
                    identifiers.add(target)
                    changed = True
        return cls(frozenset(identifiers))

    def is_comparison(self, value: str) -> bool:
        if SIZE_COMPARISON.search(value) is None:
            return False
        return any(
            name.lower() in self.identifiers
            for name in IDENTIFIER.findall(value)
        )


def shell_code_line(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character == "#" and (
            index == 0
            or line[index - 1].isspace()
            or line[index - 1] in ";|&()"
        ):
            return line[:index].rstrip()
    return line


def shell_code_lines(lines: list[str]) -> list[str]:
    return [shell_code_line(line) for line in lines]


def shell_structure_line(line: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for character in line:
        if escaped:
            result.append(" " if quote is not None else character)
            escaped = False
            continue
        if character == "\\" and quote != "'":
            result.append(character)
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
                result.append(character)
            else:
                result.append(" ")
            continue
        result.append(character)
        if character in {"'", '"'}:
            quote = character
    return "".join(result)


def shell_terminations(value: str) -> list[tuple[int, str | None]]:
    structure = shell_structure_line(value)
    result: list[tuple[int, str | None]] = []
    for termination in re.finditer(r"\b(?:exit|return)\b", structure):
        status_match = re.match(
            r"\s+(\"[^\"]*\"|'[^']*'|[^;\s]+)", value[termination.end() :]
        )
        result.append(
            (
                termination.start(),
                status_match.group(1) if status_match is not None else None,
            )
        )
    return result


def shell_failure_command(value: str) -> bool:
    structure = shell_structure_line(value)
    if FALSE_COMMAND.search(structure):
        return True
    for start, status in shell_terminations(value):
        if status is None:
            prefix = structure[:start].rstrip()
            if prefix.endswith("||"):
                return True
            continue
        if nonzero_status(status, empty_is_failure=False):
            return True
    return False


def shell_status_identifier(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().strip("\"'")
    match = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", normalized)
    return match.group(1).lower() if match is not None else None


def shell_assignment_nonzero(expression: str) -> bool:
    if re.fullmatch(r"\s*[\"']?\+?0+[\"']?\s*(?:#.*)?", expression):
        return False
    return nonzero_status(expression, empty_is_failure=False)


def shell_deferred_failure(
    lines: list[str], start_index: int, identifiers: set[str]
) -> bool:
    active = set(identifiers)
    for line in lines[start_index:]:
        for command in re.split(r"[;\n]", line):
            assignment = ASSIGNMENT.match(command)
            if assignment is not None:
                active.discard(assignment.group(1).lower())
            for _, status in shell_terminations(command):
                if shell_status_identifier(status) in active:
                    return True
        if not active:
            return False
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
    value: str, enabled: bool, context: SizeContext
) -> tuple[bool, bool]:
    for command in re.split(r"[;\n]", value):
        structure = shell_structure_line(command)
        if SHELL_ERREXIT_DISABLE.search(structure):
            enabled = False
        elif SHELL_ERREXIT_ENABLE.search(structure):
            enabled = True
        if (
            enabled
            and context.is_comparison(command)
            and SHELL_TEST_COMMAND.search(structure)
            and "&&" not in structure
            and "||" not in structure
        ):
            return enabled, True
    return enabled, False


def shell_hard_size_exit(
    lines: list[str],
    *,
    errexit_default: bool = False,
    context: SizeContext | None = None,
) -> bool:
    lines = shell_code_lines(lines)
    context = context or SizeContext.from_lines(lines)
    errexit_enabled = errexit_default
    for index, line in enumerate(lines):
        logical_command = shell_logical_command(lines, index)
        errexit_enabled, errexit_failure = shell_errexit_comparison(
            logical_command, errexit_enabled, context
        )
        if errexit_failure:
            return True
        if not context.is_comparison(logical_command):
            continue

        if (
            "&&" in shell_structure_line(logical_command)
            or "||" in shell_structure_line(logical_command)
        ) and shell_failure_command(logical_command):
            return True

        if not re.search(
            r"\bif\b", shell_structure_line(logical_command), re.IGNORECASE
        ):
            continue
        depth = 0
        opened = False
        deferred_failure_identifiers: set[str] = set()
        block_end = index
        for candidate_index, candidate in enumerate(
            lines[index : index + 80], start=index
        ):
            block_end = candidate_index
            stripped = candidate.strip()
            structure = shell_structure_line(stripped)
            openings = len(
                re.findall(
                    r"(?:^|;\s*)if\b.*?(?:;\s*then\b|\bthen\b)",
                    structure,
                )
            )
            if openings:
                depth += openings
                opened = True
            if shell_failure_command(stripped):
                return True
            assignment = ASSIGNMENT.match(stripped)
            if assignment is not None and shell_assignment_nonzero(
                assignment.group(2)
            ):
                deferred_failure_identifiers.add(assignment.group(1).lower())
            if opened:
                depth -= len(re.findall(r"\bfi\b", structure))
                if depth <= 0:
                    break
        if deferred_failure_identifiers and shell_deferred_failure(
            lines, block_end + 1, deferred_failure_identifiers
        ):
            return True
    return False


def python_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = python_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def python_status(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except ValueError:
        return ""


def python_exception(node: ast.Raise) -> str | None:
    exception = node.exc
    if isinstance(exception, ast.Call):
        return python_name(exception.func)
    return python_name(exception)


def python_handler_catches(handler: ast.ExceptHandler, exception: str | None) -> bool:
    if handler.type is None:
        return True
    caught = (
        handler.type.elts
        if isinstance(handler.type, ast.Tuple)
        else [handler.type]
    )
    names = {python_name(value) for value in caught}
    if exception in names:
        return True
    if exception in {"SystemExit", "sys.exit"}:
        return "BaseException" in names
    return bool(names.intersection({"Exception", "BaseException"}))


def python_caught_failure(
    exception: str,
    caught_by: tuple[tuple[ast.ExceptHandler, ...], ...],
    *,
    process_status_return: bool,
) -> bool | None:
    for index in range(len(caught_by) - 1, -1, -1):
        matching_handler = next(
            (
                handler
                for handler in caught_by[index]
                if python_handler_catches(handler, exception)
            ),
            None,
        )
        if matching_handler is not None:
            return python_failure_nodes(
                matching_handler.body,
                process_status_return=process_status_return,
                caught_by=caught_by[:index],
            )
    return None


def python_failure_nodes(
    nodes: list[ast.stmt],
    *,
    process_status_return: bool = False,
    caught_by: tuple[tuple[ast.ExceptHandler, ...], ...] = (),
) -> bool:
    for node in nodes:
        if isinstance(node, ast.Try):
            handlers = tuple(node.handlers)
            if python_failure_nodes(
                node.body,
                process_status_return=process_status_return,
                caught_by=(*caught_by, handlers),
            ):
                return True
            if any(
                python_failure_nodes(
                    handler.body,
                    process_status_return=process_status_return,
                    caught_by=caught_by,
                )
                for handler in node.handlers
            ):
                return True
            if python_failure_nodes(
                [*node.orelse, *node.finalbody],
                process_status_return=process_status_return,
                caught_by=caught_by,
            ):
                return True
            continue
        if isinstance(node, ast.Raise):
            exception = python_exception(node)
            caught_failure = python_caught_failure(
                exception or "",
                caught_by,
                process_status_return=process_status_return,
            )
            if caught_failure is not None:
                if caught_failure:
                    return True
                continue
            if exception == "SystemExit":
                call = node.exc if isinstance(node.exc, ast.Call) else None
                status = python_status(call.args[0]) if call and call.args else None
                if not python_nonzero_status(status, empty_is_failure=True):
                    continue
            return True
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if python_name(node.value.func) in {"sys.exit", "exit"}:
                status = (
                    python_status(node.value.args[0])
                    if node.value.args
                    else None
                )
                if python_nonzero_status(status, empty_is_failure=True):
                    return True
        if isinstance(node, ast.Return) and process_status_return:
            if python_nonzero_status(
                python_status(node.value), empty_is_failure=False
            ):
                return True
        if isinstance(node, ast.Assert):
            caught_failure = python_caught_failure(
                "AssertionError",
                caught_by,
                process_status_return=process_status_return,
            )
            if caught_failure is None or caught_failure:
                return True
        nested = [
            value
            for value in ast.iter_child_nodes(node)
            if isinstance(value, ast.stmt)
            and not isinstance(value, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if python_failure_nodes(
            nested,
            process_status_return=process_status_return,
            caught_by=caught_by,
        ):
            return True
    return False


def python_tree(lines: list[str]) -> ast.Module:
    try:
        return ast.parse("\n".join(lines))
    except SyntaxError as error:
        raise PolicyParseError("Python policy cannot be parsed safely") from error


def python_failure(lines: list[str]) -> bool:
    tree = python_tree(lines)
    return python_failure_nodes(tree.body)


def python_size_comparison(node: ast.AST, context: SizeContext) -> bool:
    return isinstance(node, ast.Compare) and context.is_comparison(ast.unparse(node))


def python_process_status_functions(tree: ast.Module) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        call: ast.Call | None = None
        if isinstance(node, ast.Call) and python_name(node.func) in {"sys.exit", "exit"}:
            call = node
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if python_name(node.exc.func) == "SystemExit":
                call = node.exc
        if call and call.args and isinstance(call.args[0], ast.Call):
            name = python_name(call.args[0].func)
            if name:
                result.add(name)
    return result


def python_hard_size_nodes(
    nodes: list[ast.stmt],
    context: SizeContext,
    process_status_functions: set[str],
    *,
    current_function: str | None = None,
    caught_by: tuple[tuple[ast.ExceptHandler, ...], ...] = (),
) -> bool:
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if python_hard_size_nodes(
                node.body,
                context,
                process_status_functions,
                current_function=node.name,
                caught_by=(),
            ):
                return True
            continue
        if isinstance(node, ast.Try):
            handlers = tuple(node.handlers)
            if python_hard_size_nodes(
                node.body,
                context,
                process_status_functions,
                current_function=current_function,
                caught_by=(*caught_by, handlers),
            ):
                return True
            branches = [
                *node.orelse,
                *node.finalbody,
                *(statement for handler in node.handlers for statement in handler.body),
            ]
            if python_hard_size_nodes(
                branches,
                context,
                process_status_functions,
                current_function=current_function,
                caught_by=caught_by,
            ):
                return True
            continue
        if isinstance(node, ast.Assert) and any(
            python_size_comparison(candidate, context)
            for candidate in ast.walk(node.test)
        ):
            caught_failure = python_caught_failure(
                "AssertionError",
                caught_by,
                process_status_return=current_function in process_status_functions,
            )
            if caught_failure is None or caught_failure:
                return True
        if isinstance(node, ast.If) and any(
            python_size_comparison(candidate, context)
            for candidate in ast.walk(node.test)
        ):
            if python_failure_nodes(
                [*node.body, *node.orelse],
                process_status_return=current_function in process_status_functions,
                caught_by=caught_by,
            ):
                return True
        nested = [
            value
            for value in ast.iter_child_nodes(node)
            if isinstance(value, ast.stmt)
        ]
        if python_hard_size_nodes(
            nested,
            context,
            process_status_functions,
            current_function=current_function,
            caught_by=caught_by,
        ):
            return True
    return False


def python_hard_size_exit(
    lines: list[str], context: SizeContext | None = None
) -> bool:
    context = context or SizeContext.from_lines(lines)
    tree = python_tree(lines)
    process_status_functions = python_process_status_functions(tree)
    return python_hard_size_nodes(
        tree.body, context, process_status_functions
    )


def parser_result(kind: str, source: str) -> object:
    try:
        result = subprocess.run(
            ["node", str(WORKFLOW_PARSER), kind],
            input=source.encode("utf-8"),
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise PolicyParseError("policy parser is unavailable") from error
    if result.returncode != 0:
        raise PolicyParseError("policy source cannot be parsed safely")
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyParseError("policy parser returned invalid data") from error


@dataclass(frozen=True)
class JavaScriptAnalysis:
    hard_size_exit: bool
    process_failure: bool
    executable_source: str


def javascript_analysis(
    lines: list[str], context: SizeContext | None = None
) -> JavaScriptAnalysis:
    context = context or SizeContext.from_lines(lines)
    value = parser_result(
        "javascript",
        json.dumps(
            {
                "identifiers": sorted(context.identifiers),
                "source": "\n".join(lines),
            }
        ),
    )
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("hardSizeExit"), bool)
        or not isinstance(value.get("processFailure"), bool)
        or not isinstance(value.get("executableSource"), str)
    ):
        raise PolicyParseError("JavaScript parser returned invalid data")
    return JavaScriptAnalysis(
        hard_size_exit=value["hardSizeExit"],
        process_failure=value["processFailure"],
        executable_source=value["executableSource"],
    )


def javascript_failure(lines: list[str]) -> bool:
    return javascript_analysis(lines).process_failure


def javascript_hard_size_exit(
    lines: list[str], context: SizeContext | None = None
) -> bool:
    return javascript_analysis(lines, context).hard_size_exit


def is_workflow_policy(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    parts = relative.parts
    return path.suffix.lower() in {".yml", ".yaml"} and (
        (len(parts) >= 3 and parts[:2] == (".github", "workflows"))
        or (len(parts) >= 2 and parts[0] == "workflow-templates")
        or (len(parts) >= 3 and parts[:2] == (".github", "workflow-templates"))
    )


def is_composite_action(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    parts = relative.parts
    return path.suffix.lower() in {".yml", ".yaml"} and (
        (len(parts) >= 3 and parts[:2] == (".github", "actions"))
        or (len(parts) == 1 and path.stem == "action")
    ) and path.stem == "action"


def is_pre_commit_config(root: Path, path: Path) -> bool:
    return path.relative_to(root).as_posix() in {
        ".pre-commit-config.yaml",
        ".pre-commit-config.yml",
    }


def policy_language(root: Path, path: Path, text: str) -> str | None:
    relative = path.relative_to(root)
    parts = relative.parts
    suffix = path.suffix.lower()
    if is_workflow_policy(root, path) or is_composite_action(root, path):
        return "shell"
    if is_pre_commit_config(root, path):
        return "shell"

    policy_root = bool(parts) and parts[0] in POLICY_ROOTS
    if not policy_root:
        return None
    if suffix in {".sh", ".bash"}:
        return "shell"
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".cjs", ".mjs", ".ts"}:
        return "javascript"
    if suffix == "" and re.match(r"^#!.*\b(?:ba|da|k|z)?sh\b", text):
        return "shell"
    return None


@dataclass(frozen=True)
class WorkflowUnit:
    language: str
    lines: list[str]
    blocking: bool
    conditions: tuple[str, ...]
    uses: str | None


@dataclass(frozen=True)
class WorkflowDocument:
    units: tuple[WorkflowUnit, ...]
    max_lines_description: str | None
    permissions: frozenset[str]


def runner_language(shell_value: object) -> str:
    if shell_value is None:
        shell = "bash"
    elif isinstance(shell_value, str):
        shell = shell_value.strip().lower()
    else:
        raise PolicyParseError("workflow shells must be strings")
    executable = shell.split(maxsplit=1)[0] if shell else ""
    executable = executable.rsplit("/", maxsplit=1)[-1]
    if executable.startswith("python"):
        return "python"
    if executable in {"node", "deno", "bun"}:
        return "javascript"
    if re.fullmatch(r"(?:ba|da|k|z)?sh", executable):
        return "shell"
    return "unknown"


def runner_source(entry: str) -> list[str]:
    try:
        tokens = shlex.split(entry)
    except ValueError as error:
        raise PolicyParseError("runner command cannot be parsed safely") from error
    if (
        len(tokens) >= 3
        and runner_language(tokens[0]) == "shell"
        and tokens[1] == "-c"
    ):
        return tokens[2].splitlines()
    return [entry]


def workflow_document(text: str, kind: str = "workflow") -> WorkflowDocument:
    value = parser_result(kind, text)
    try:
        metadata = value["metadata"]
        units = tuple(
            WorkflowUnit(
                language=item["language"],
                lines=(
                    runner_source(item["lines"][0])
                    if kind == "pre-commit" and len(item["lines"]) == 1
                    else item["lines"]
                ),
                blocking=item["blocking"],
                conditions=tuple(item["conditions"]),
                uses=item["uses"],
            )
            for item in value["units"]
        )
        description = metadata.get("maxLinesDescription")
        permissions = metadata.get("permissions", [])
        if (
            not all(
                isinstance(unit.language, str)
                and isinstance(unit.lines, list)
                and all(isinstance(line, str) for line in unit.lines)
                and isinstance(unit.blocking, bool)
                and all(isinstance(condition, str) for condition in unit.conditions)
                and (unit.uses is None or isinstance(unit.uses, str))
                for unit in units
            )
            or (description is not None and not isinstance(description, str))
            or not isinstance(permissions, list)
            or not all(isinstance(permission, str) for permission in permissions)
        ):
            raise TypeError
        return WorkflowDocument(
            units, description, frozenset(permissions)
        )
    except (KeyError, TypeError) as error:
        raise PolicyParseError("workflow YAML parser returned invalid data") from error


def workflow_units(text: str, kind: str = "workflow") -> tuple[WorkflowUnit, ...]:
    return workflow_document(text, kind).units


def unit_executable_lines(unit: WorkflowUnit) -> list[str]:
    if unit.language == "shell":
        lines = shell_code_lines(unit.lines)
    elif unit.language == "python":
        lines = ast.unparse(python_tree(unit.lines)).splitlines()
    elif unit.language == "javascript":
        lines = javascript_analysis(unit.lines).executable_source.splitlines()
    else:
        lines = unit.lines
    return [*unit.conditions, *lines, *([unit.uses] if unit.uses else [])]


def workflow_executable_text(document: WorkflowDocument) -> str:
    return "\n".join(
        line for unit in document.units for line in unit_executable_lines(unit)
    )


def policy_executable_text(root: Path, path: Path, text: str) -> str:
    if is_workflow_policy(root, path):
        return workflow_executable_text(workflow_document(text))
    if is_composite_action(root, path):
        return workflow_executable_text(workflow_document(text, "action"))
    if is_pre_commit_config(root, path):
        return workflow_executable_text(workflow_document(text, "pre-commit"))
    language = policy_language(root, path, text)
    if language == "shell":
        return "\n".join(shell_code_lines(text.splitlines()))
    if language == "python":
        return ast.unparse(python_tree(text.splitlines()))
    if language == "javascript":
        return javascript_analysis(text.splitlines()).executable_source
    return ""


def workflow_process_failure(unit: WorkflowUnit) -> bool:
    if unit.language == "shell":
        return any(
            shell_failure_command(line) for line in shell_code_lines(unit.lines)
        )
    if unit.language == "python":
        return python_failure(unit.lines)
    if unit.language == "javascript":
        return javascript_failure(unit.lines)
    return any(
        shell_failure_command(line) for line in shell_code_lines(unit.lines)
    )


def local_action_path(root: Path, uses: str) -> Path | None:
    if not uses.startswith("./"):
        return None
    candidate = (root / uses[2:]).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise PolicyParseError("local action reference escapes the repository") from error
    if candidate.is_dir():
        for name in ("action.yml", "action.yaml"):
            action = candidate / name
            if action.is_file():
                return action
        raise PolicyParseError("local action directory has no action metadata")
    if candidate.is_file() and candidate.name in {"action.yml", "action.yaml"}:
        return candidate
    raise PolicyParseError("local action reference is unavailable")


def action_process_failure(
    root: Path,
    uses: str,
    contents: dict[Path, str],
    action_cache: dict[Path, WorkflowDocument],
    resolving: frozenset[Path] = frozenset(),
) -> bool:
    action_path = local_action_path(root, uses)
    if action_path is None:
        return True
    if action_path in resolving:
        raise PolicyParseError("local composite actions contain a cycle")
    text = contents.get(action_path)
    if text is None:
        try:
            text = read_text(action_path)
        except (OSError, UnicodeDecodeError) as error:
            raise PolicyParseError("local action metadata is unreadable") from error
    document = action_cache.get(action_path)
    if document is None:
        document = workflow_document(text, "action")
        action_cache[action_path] = document
    nested = resolving.union({action_path})
    for unit in document.units:
        if not unit.blocking:
            continue
        if unit.uses is not None:
            if action_process_failure(
                root, unit.uses, contents, action_cache, nested
            ):
                return True
        elif workflow_process_failure(unit):
            return True
    return False


def workflow_unit_hard_size_exit(
    unit: WorkflowUnit,
    *,
    root: Path | None = None,
    contents: dict[Path, str] | None = None,
    action_cache: dict[Path, WorkflowDocument] | None = None,
) -> bool:
    if not unit.blocking:
        return False
    analysis_lines = [*unit.conditions, *unit.lines]
    if unit.language == "shell":
        analysis_lines = [*unit.conditions, *shell_code_lines(unit.lines)]
    context = SizeContext.from_lines(analysis_lines)
    if not context.identifiers:
        return False
    if any(context.is_comparison(condition) for condition in unit.conditions):
        if unit.uses is not None:
            if root is None or contents is None or action_cache is None:
                return True
            return action_process_failure(root, unit.uses, contents, action_cache)
        return workflow_process_failure(unit)
    if unit.uses is not None:
        return False
    if unit.language == "shell":
        return shell_hard_size_exit(
            unit.lines, errexit_default=True, context=context
        )
    if unit.language == "python":
        return python_hard_size_exit(unit.lines, context)
    if unit.language == "javascript":
        return javascript_hard_size_exit(unit.lines, context)
    return shell_hard_size_exit(
        unit.lines, errexit_default=True, context=context
    )


def hard_size_exit(
    root: Path,
    path: Path,
    text: str,
    contents: dict[Path, str],
    action_cache: dict[Path, WorkflowDocument],
) -> bool:
    language = policy_language(root, path, text)
    lines = text.splitlines()
    if language == "shell":
        if is_workflow_policy(root, path):
            return any(
                workflow_unit_hard_size_exit(
                    unit,
                    root=root,
                    contents=contents,
                    action_cache=action_cache,
                )
                for unit in workflow_units(text)
            )
        if is_composite_action(root, path):
            return any(
                workflow_unit_hard_size_exit(
                    unit,
                    root=root,
                    contents=contents,
                    action_cache=action_cache,
                )
                for unit in workflow_units(text, "action")
            )
        if is_pre_commit_config(root, path):
            return any(
                workflow_unit_hard_size_exit(unit)
                for unit in workflow_units(text, "pre-commit")
            )
        return shell_hard_size_exit(lines)
    if language == "python":
        return python_hard_size_exit(lines)
    if language == "javascript":
        return javascript_hard_size_exit(lines)
    return False


def shell_assignment_present(lines: list[str], name: str) -> bool:
    return any(
        (match := ASSIGNMENT.match(line)) is not None
        and match.group(1) == name
        for line in shell_code_lines(lines)
    )


def shell_output_present(lines: list[str], fragment: str) -> bool:
    return any(
        fragment in line
        and re.search(
            r"(?:^|[;&|])\s*(?:echo|printf)\b", shell_structure_line(line)
        )
        for line in shell_code_lines(lines)
    )


def reusable_workflow_contract_failures(text: str) -> list[str]:
    failures: list[str] = []
    document = workflow_document(text)
    executable_text = workflow_executable_text(document)
    shell_lines = [
        line
        for unit in document.units
        if unit.language == "shell"
        for line in unit.lines
    ]
    shell_structure = "\n".join(
        shell_structure_line(line) for line in shell_code_lines(shell_lines)
    )
    if re.search(r"\bgit\s+diff\b[^\n]*--numstat\b", shell_structure) is None:
        failures.append("missing locale-independent changed-line calculation")
    if not shell_assignment_present(shell_lines, "INSERTIONS"):
        failures.append("missing insertion reporting")
    if not shell_assignment_present(shell_lines, "DELETIONS"):
        failures.append("missing deletion reporting")
    if not shell_output_present(shell_lines, "::warning::"):
        failures.append("missing advisory GitHub warning")
    if document.max_lines_description is None or not re.search(
        r"advisory.*changed[- ]line.*threshold",
        document.max_lines_description,
        re.IGNORECASE,
    ):
        failures.append("missing advisory max-lines contract")
    if "pull-requests" in document.permissions:
        failures.append("unused pull-request permission")
    if (
        ".preflight-allow-large-pr" in executable_text
        or "large-pr-approved" in executable_text
    ):
        failures.append("obsolete size override")
    if any(
        workflow_unit_hard_size_exit(unit) for unit in document.units
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
    try:
        return reusable_workflow_contract_failures(text)
    except PolicyParseError:
        return ["reusable workflow revision cannot be parsed safely"]


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
    action_cache: dict[Path, WorkflowDocument] = {}
    for path in active_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            contents[path] = read_text(path)
        except (OSError, UnicodeDecodeError):
            failures.append(f"{relative}: unable to read as UTF-8")

    for path, text in contents.items():
        relative = path.relative_to(root).as_posix()
        lines = text.splitlines()
        try:
            executable_text = policy_executable_text(root, path, text)
            if ".preflight-allow-large-pr" in executable_text:
                failures.append(f"{relative}: obsolete override-file policy")
            if "large-pr-approved" in executable_text:
                failures.append(f"{relative}: obsolete approval-label policy")
            if re.search(
                r"Maximum allowed:\s*600", executable_text, re.IGNORECASE
            ):
                failures.append(f"{relative}: hard-maximum wording")
            if re.search(r"PR TOO LARGE", executable_text, re.IGNORECASE):
                failures.append(f"{relative}: hard-failure banner")
            if re.search(
                r"Push aborted", executable_text, re.IGNORECASE
            ) and SIZE_TERMS.search(executable_text):
                failures.append(f"{relative}: size-based push abortion")
            if hard_size_exit(root, path, text, contents, action_cache):
                failures.append(f"{relative}: size-triggered nonzero exit")
        except PolicyParseError:
            failures.append(f"{relative}: policy source cannot be parsed safely")
        if size_bypass_instruction(lines):
            failures.append(f"{relative}: size-policy hook bypass instruction")

    preflight = root / "scripts/preflight.sh"
    preflight_text = contents.get(preflight, "")
    preflight_code = "\n".join(shell_code_lines(preflight_text.splitlines()))
    has_local_size_calculation = "--numstat" in preflight_code and bool(
        re.search(r"(?:PR_SIZE|MAX_LINES|ADVISORY_THRESHOLD)", preflight_code)
    )
    if has_local_size_calculation:
        required_fragments = {
            "advisory threshold": "advisory-threshold reporting",
            "INSERTIONS": "insertion reporting",
            "DELETIONS": "deletion reporting",
            "WARNING": "above-threshold warning",
        }
        for fragment, description in required_fragments.items():
            if fragment not in preflight_code:
                failures.append(f"scripts/preflight.sh: missing {description}")

    for workflow, workflow_text in contents.items():
        relative = workflow.relative_to(root)
        if (
            len(relative.parts) < 3
            or relative.parts[:2] != (".github", "workflows")
            or workflow.suffix.lower() not in {".yml", ".yaml"}
        ):
            continue
        try:
            document = workflow_document(workflow_text)
        except PolicyParseError:
            continue
        executable_text = workflow_executable_text(document)
        references = [
            match.group(1)
            for unit in document.units
            if unit.uses is not None
            and (
                match := re.fullmatch(
                    r"SecPal/\.github/\.github/workflows/reusable-pr-size\.yml@(.+)",
                    unit.uses,
                    re.IGNORECASE,
                )
            )
        ]
        is_size_workflow = bool(references) or (
            "git diff --numstat" in executable_text
            and re.search(r"\bPR[- ]?size\b", executable_text, re.IGNORECASE)
        )
        if "pull-requests" in document.permissions and is_size_workflow:
            failures.append(
                f"{relative.as_posix()}: unused pull-request permission"
            )
        for reference in references:
            if not re.fullmatch(r"[0-9a-f]{40}", reference):
                failures.append(
                    f"{relative.as_posix()}: reusable workflow is not pinned to an immutable SHA"
                )
                continue
            contract_failures = workflow_contract_cache.get(reference)
            if contract_failures is None:
                contract_failures = pinned_workflow_contract_failures(
                    workflow_source, reference
                )
                workflow_contract_cache[reference] = contract_failures
            if contract_failures:
                failures.append(
                    f"{relative.as_posix()}: pinned reusable workflow violates the advisory contract "
                    f"({', '.join(contract_failures)})"
                )

    reusable = root / ".github/workflows/reusable-pr-size.yml"
    reusable_text = contents.get(reusable, "")
    if reusable_text:
        try:
            contract_failures = reusable_workflow_contract_failures(reusable_text)
        except PolicyParseError:
            contract_failures = ["workflow YAML cannot be parsed safely"]
        for description in contract_failures:
            failures.append(
                f".github/workflows/reusable-pr-size.yml: {description}"
            )

    return sorted(set(failures))


def main() -> int:
    failed = False
    repositories = resolve_repositories(sys.argv[2:])
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
