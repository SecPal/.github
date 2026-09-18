# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main safety assertions for the immutable Node-24 delivery tree."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys


INVARIANTS = [
    "current_tree_exact",
    "historical_bytes_unavailable",
    "registered_validation",
    "source_history",
]
BASELINE = Path(".nvmrc")
ACTION = Path(".github/actions/setup-node-with-deps/action.yml")
VALIDATOR = Path("scripts/validate-node-baseline.mjs")
SYSTEM_CHECK = Path("scripts/check-system-requirements.sh")
PACKAGE = Path("package.json")
VALIDATOR_TERMS = (
    "resolveWorkflowInputs",
    "localSetupDefault",
    "nodeCommandIndexes",
    "setupIndexes.some((setupIndex) => setupIndex < commandIndex)",
    "executes Node tooling without an explicit Node setup step",
    "must set up Node before its Node tooling command",
)
SYSTEM_CHECK_TERMS = (
    'NODE_BASELINE_FILE="$REPO_ROOT/.nvmrc"',
    'REQUIRED_NODE_MAJOR="$(<"$NODE_BASELINE_FILE")"',
    '"$major_version" -ge "$REQUIRED_NODE_MAJOR"',
    "canonical baseline: Node ${REQUIRED_NODE_MAJOR} LTS",
)
ACTIVE_DOCUMENT_ROOTS = (
    Path("docs/scripts"),
    Path("docs/workflows"),
    Path(".github/ISSUE_TEMPLATE"),
)
ACTIVE_DOCUMENTS = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("scripts/README.md"),
    Path(".github/workflows/README.md"),
)
NODE_22 = re.compile(r"\bNode(?:\.js)?\s+22(?:\.x)?\b|node-version:\s*[\"']?22(?:\.x)?\b", re.I)


def _active_documents() -> list[Path]:
    documents = list(ACTIVE_DOCUMENTS)
    for root in ACTIVE_DOCUMENT_ROOTS:
        if root.is_dir():
            documents.extend(
                path for path in root.rglob("*")
                if path.is_file() and path.suffix in {".md", ".yml", ".yaml"}
            )
    return sorted(set(documents))


def main(arguments: list[str]) -> int:
    required = (BASELINE, ACTION, VALIDATOR, SYSTEM_CHECK, PACKAGE)
    workflows = sorted(Path(".github/workflows").glob("*.y*ml"))
    if arguments or any(not path.is_file() for path in required) or not workflows:
        print(json.dumps(["registered_validation"]))
        return 1
    try:
        baseline = BASELINE.read_text(encoding="utf-8").strip()
        action = ACTION.read_text(encoding="utf-8")
        validator = VALIDATOR.read_text(encoding="utf-8")
        system_check = SYSTEM_CHECK.read_text(encoding="utf-8")
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
        document_text = "\n".join(
            path.read_text(encoding="utf-8") for path in _active_documents()
        )
        syntax = (
            subprocess.run(
                ["bash", "-n", str(SYSTEM_CHECK)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            ),
            subprocess.run(
                ["node", "--check", str(VALIDATOR)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            ),
        )
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        print(json.dumps(["registered_validation"]))
        return 1
    scripts = package.get("scripts")
    if (
        baseline != "24"
        or 'default: "24.x"' not in action
        or "node-version: ${{ inputs.node-version }}" not in action
        or any(term not in validator for term in VALIDATOR_TERMS)
        or any(term not in system_check for term in SYSTEM_CHECK_TERMS)
        or not isinstance(scripts, dict)
        or scripts.get("test:node-baseline")
        != "node --test tests/node-baseline-governance.test.mjs"
        or NODE_22.search(workflow_text + "\n" + action + "\n" + document_text)
        or any(result.returncode != 0 for result in syntax)
    ):
        print(json.dumps(["registered_validation"]))
        return 1
    print(json.dumps(INVARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
