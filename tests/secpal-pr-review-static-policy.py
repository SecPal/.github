#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Enforce the closed process-launch surface of the PR review helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class ProcessCall:
    class_name: str | None
    function_name: str
    executable: str
    arguments: str
    keywords: frozenset[str]


ACTION_CALLS = (
    ProcessCall(
        None,
        "_run_registered_validations",
        "executable",
        "command['argv'][1:]",
        frozenset({"check", "cwd", "env", "stderr", "stdin", "stdout", "timeout"}),
    ),
    ProcessCall(
        "ActionCommandRunner",
        "run",
        "self.executable_path",
        "arguments[1:]",
        frozenset(
            {
                "capture_output",
                "check",
                "encoding",
                "env",
                "errors",
                "stdin",
                "text",
                "timeout",
            }
        ),
    ),
    ProcessCall(
        "FastPathGateway",
        "_git",
        "self.git_executable",
        "arguments",
        frozenset(
            {
                "capture_output",
                "check",
                "cwd",
                "encoding",
                "env",
                "errors",
                "stdin",
                "text",
                "timeout",
            }
        ),
    ),
    ProcessCall(
        None,
        "_run_attestation_git",
        "git_executable",
        "arguments",
        frozenset(
            {
                "capture_output",
                "check",
                "cwd",
                "encoding",
                "env",
                "errors",
                "stdin",
                "text",
                "timeout",
            }
        ),
    ),
)

RESOLVER_CALLS = (
    ProcessCall(
        None,
        "_run_gh",
        "executable",
        "arguments",
        frozenset(
            {
                "capture_output",
                "check",
                "encoding",
                "env",
                "errors",
                "stdin",
                "text",
                "timeout",
            }
        ),
    ),
)

EXPECTED_CALLS = {
    "secpal-pr-review-actions.py": ACTION_CALLS,
    "fast_path.py": (),
    "secpal-resolve-fixed-threads.py": RESOLVER_CALLS,
}

SAFE_SUBPROCESS_ATTRIBUTES = {
    "CompletedProcess",
    "DEVNULL",
    "TimeoutExpired",
}
SAFE_OS_ATTRIBUTES = {
    "X_OK",
    "access",
    "close",
    "devnull",
    "fchmod",
    "fdopen",
    "fsync",
    "getuid",
    "pathsep",
    "replace",
    "unlink",
}
PROHIBITED_IMPORT_ROOTS = {
    "asyncio",
    "commands",
    "concurrent",
    "ctypes",
    "multiprocessing",
    "posix",
    "pty",
    "runpy",
    "time",
}


class PolicyVisitor(ast.NodeVisitor):
    def __init__(
        self,
        label: str,
        expected_calls: tuple[ProcessCall, ...],
        *,
        bounded_resolver: bool,
    ) -> None:
        self.label = label
        self.expected_calls = expected_calls
        self.bounded_resolver = bounded_resolver
        self.findings: list[str] = []
        self.seen_calls: list[ProcessCall] = []
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.parents: dict[ast.AST, ast.AST] = {}

    def inspect(self, tree: ast.AST) -> list[str]:
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent
        self.visit(tree)
        missing = [call for call in self.expected_calls if call not in self.seen_calls]
        for call in missing:
            self.findings.append(
                f"{self.label}: missing allowed subprocess.run in "
                f"{call.class_name + '.' if call.class_name else ''}{call.function_name}"
            )
        return self.findings

    def finding(self, node: ast.AST, message: str) -> None:
        self.findings.append(
            f"{self.label}:{getattr(node, 'lineno', '?')}: {message}"
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root in PROHIBITED_IMPORT_ROOTS:
                self.finding(node, f"prohibited process-capable import: {root}")
            if root in {"os", "subprocess"} and alias.asname is not None:
                self.finding(node, f"{root} must not be aliased")
            if root == "importlib" and alias.name != "importlib.util":
                self.finding(node, "only importlib.util is allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".", 1)[0]
        if root in PROHIBITED_IMPORT_ROOTS | {"importlib", "os", "subprocess"}:
            self.finding(node, f"prohibited direct import from {root}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in {"os", "subprocess"} and isinstance(node.ctx, ast.Load):
            parent = self.parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.value is not node:
                self.finding(node, f"bare {node.id} module reference is prohibited")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "subprocess":
            parent = self.parents.get(node)
            if node.attr == "run":
                if not isinstance(parent, ast.Call) or parent.func is not node:
                    self.finding(node, "subprocess.run may only be called directly")
            elif node.attr not in SAFE_SUBPROCESS_ATTRIBUTES:
                self.finding(node, f"prohibited subprocess attribute: {node.attr}")
        elif isinstance(node.value, ast.Name) and node.value.id == "os":
            if node.attr not in SAFE_OS_ATTRIBUTES:
                self.finding(node, f"prohibited os attribute: {node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in {
            "__import__",
            "eval",
            "exec",
        }:
            self.finding(node, f"dynamic execution is prohibited: {node.func.id}")
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
        ):
            self._inspect_process_call(node)
        self.generic_visit(node)

    def _inspect_process_call(self, node: ast.Call) -> None:
        candidates = [
            call
            for call in self.expected_calls
            if self.classes
            == ([call.class_name] if call.class_name is not None else [])
            and self.functions == [call.function_name]
        ]
        if len(candidates) != 1:
            self.finding(node, "subprocess.run is outside the closed allowlist")
            return
        expected = candidates[0]
        if expected in self.seen_calls:
            self.finding(node, "allowed subprocess.run occurs more than once")
            return
        self.seen_calls.append(expected)

        if len(node.args) != 1 or not isinstance(node.args[0], ast.List):
            self.finding(node, "process argv must be one inline list")
            return
        argv = node.args[0]
        if len(argv.elts) != 2 or not isinstance(argv.elts[1], ast.Starred):
            self.finding(node, "process argv must have one executable and one starred tail")
            return
        if ast.unparse(argv.elts[0]) != expected.executable:
            self.finding(node, "process executable expression changed")
        if ast.unparse(argv.elts[1].value) != expected.arguments:
            self.finding(node, "process argument expression changed")

        if any(keyword.arg is None for keyword in node.keywords):
            self.finding(node, "expanded process keyword arguments are prohibited")
            return
        keywords = frozenset(
            keyword.arg for keyword in node.keywords if keyword.arg is not None
        )
        if keywords != expected.keywords or len(node.keywords) != len(keywords):
            self.finding(node, "process keyword set changed")

    def visit_While(self, node: ast.While) -> None:
        if self.bounded_resolver:
            self.finding(node, "simple resolver loops must be statically bounded")
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        if self.bounded_resolver:
            self.finding(node, "simple resolver must not use async iteration")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        if self.bounded_resolver and isinstance(node.iter, ast.Call):
            if isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                valid_range = (
                    (self.functions[-1] if self.functions else "") == "read_target_thread"
                    and len(node.iter.args) == 1
                    and not node.iter.keywords
                    and ast.unparse(node.iter.args[0])
                    == "budget.remaining_api_calls"
                )
                if not valid_range:
                    self.finding(node, "resolver range loop is outside the bounded pagination site")
            elif isinstance(node.iter.func, ast.Name) and node.iter.func.id == "iter":
                self.finding(node, "callable-sentinel loops are prohibited")
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        if self.bounded_resolver and isinstance(node.iter, ast.Call):
            self.finding(node, "resolver comprehensions must not poll call results")
        self.generic_visit(node)


def inspect_source(
    source: str,
    label: str,
    expected_calls: tuple[ProcessCall, ...],
    *,
    bounded_resolver: bool = False,
) -> list[str]:
    tree = ast.parse(source, filename=label)
    return PolicyVisitor(
        label,
        expected_calls,
        bounded_resolver=bounded_resolver,
    ).inspect(tree)


def self_test() -> None:
    safe_call = ProcessCall(
        None,
        "safe_runner",
        "executable",
        "arguments",
        frozenset({"check"}),
    )
    safe = (
        "import subprocess\n"
        "def safe_runner(executable, arguments):\n"
        "    return subprocess.run([executable, *arguments], check=False)\n"
    )
    if inspect_source(safe, "safe-fixture", (safe_call,)):
        raise SystemExit("static policy safe fixture was rejected")

    unsafe: dict[str, tuple[str, tuple[ProcessCall, ...]]] = {
        "shell-dispatch-through-env": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    return subprocess.run(\n"
                "        ['/usr/bin/env', 'bash', '-c', *arguments], check=False\n"
                "    )\n"
            ),
            (safe_call,),
        ),
        "variable-array-gh-merge-authority": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    argv = [executable, 'pr', 'merge', *arguments]\n"
                "    return subprocess.run(argv, check=False)\n"
            ),
            (safe_call,),
        ),
        "aliased-run": (
            (
                "import subprocess\n"
                "def safe_runner(executable, arguments):\n"
                "    runner = subprocess.run\n"
                "    return runner([executable, *arguments], check=False)\n"
            ),
            (safe_call,),
        ),
        "nested-allowlist-name": (
            (
                "import subprocess\n"
                "def outer():\n"
                "    def safe_runner(executable, arguments):\n"
                "        return subprocess.run([executable, *arguments], check=False)\n"
            ),
            (safe_call,),
        ),
        "blocking-wait": (
            "from time import sleep\nsleep(1)\n",
            (),
        ),
        "alternate-process-api": (
            "import os\nos.system(command)\n",
            (),
        ),
    }
    for name, (source, expected) in unsafe.items():
        if not inspect_source(source, name, expected):
            raise SystemExit(f"static policy negative fixture was not detected: {name}")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        raise SystemExit(
            "usage: secpal-pr-review-static-policy.py "
            "ACTIONS FAST_PATH SIMPLE_RESOLVER"
        )
    self_test()
    findings: list[str] = []
    for value in argv[1:]:
        path = Path(value)
        expected = EXPECTED_CALLS.get(path.name)
        if expected is None:
            raise SystemExit(f"no static policy registered for {path.name}")
        findings.extend(
            inspect_source(
                path.read_text(encoding="utf-8"),
                str(path),
                expected,
                bounded_resolver=path.name == "secpal-resolve-fixed-threads.py",
            )
        )
    if findings:
        raise SystemExit("\n".join(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
