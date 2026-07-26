#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL="$REPO_ROOT/.agents/skills/secpal-pr-review/SKILL.md"
CONTRACT="$REPO_ROOT/.agents/skills/secpal-pr-review/references/contract.md"
ACTIONS="$REPO_ROOT/scripts/secpal-pr-review-actions.py"
EVIDENCE="$REPO_ROOT/scripts/secpal-pr-review.py"
REGISTRY="$REPO_ROOT/.agents/skills/secpal-pr-review/references/repositories.json"
PLAN_SCHEMA="$REPO_ROOT/.agents/skills/secpal-pr-review/references/mutation-plan.schema.json"
FAST_SCHEMA="$REPO_ROOT/.agents/skills/secpal-pr-review/references/fast-path-batch.schema.json"
FAST_PATH="$REPO_ROOT/scripts/secpal_pr_review/fast_path.py"
SIMPLE_RESOLVER="$REPO_ROOT/scripts/secpal-resolve-fixed-threads.py"
INTEGRATION="$REPO_ROOT/tests/secpal-pr-review-skill-integration.sh"
QUALITY_WORKFLOW="$REPO_ROOT/.github/workflows/quality.yml"
GOVERNANCE_SUITE="$REPO_ROOT/tests/review-governance-suite.sh"
P21_BASELINE="833eef2afc063ae777e7e2b64b2f252e3fe1e49e"

fail() {
  printf 'policy failure: %s\n' "$1" >&2
  exit 1
}

for required in "$SKILL" "$CONTRACT" "$ACTIONS" "$FAST_PATH" "$SIMPLE_RESOLVER" "$REGISTRY" "$PLAN_SCHEMA" "$FAST_SCHEMA"; do
  test -f "$required" || fail "missing ${required#"$REPO_ROOT"/}"
done
test -x "$GOVERNANCE_SUITE" || fail 'registered governance suite is not executable'

# Policy cases: exact fast-path counters, one audit, explicit checkpoint, one
# bounded read retry, no polling, and zero review-request/merge authority.
grep -Fq 'normal_complete_snapshots: 0' "$CONTRACT" || fail 'normal snapshot limit drifted'
grep -Fq 'normal_stable_feedback_reads: 2' "$CONTRACT" || fail 'stable feedback read limit drifted'
grep -Fq 'normal_required_check_reads_before_resolution: 1' "$CONTRACT" || fail 'required-check read limit drifted'
grep -Fq 'normal_complete_validation_runs: 1' "$CONTRACT" || fail 'complete validation limit drifted'
grep -Fq 'maximum_holistic_audits: 1' "$CONTRACT" || fail 'holistic audit limit drifted'
grep -Fq 'normal_signed_remediation_commits: 1' "$CONTRACT" || fail 'commit limit drifted'
grep -Fq 'normal_fast_forward_pushes: 1' "$CONTRACT" || fail 'push limit drifted'
grep -Fq 'maximum_evidence_replies_total: 10' "$CONTRACT" || fail 'reply limit drifted'
grep -Fq 'WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION' "$CONTRACT" || fail 'user checkpoint missing'
grep -Fq 'A normal invocation has one remediation pass.' "$CONTRACT" || fail 'single-pass rule missing'
grep -Fq 'never appends unreviewed feedback' "$CONTRACT" || fail 'late-feedback rule missing'

for phrase in \
  'zero review requests' \
  'zero Draft-to-Ready transitions' \
  'zero merge operations' \
  'zero auto-merge operations' \
  'no polling' \
  'no sleep-and-retry' \
  'Green CI does not establish technical truth'; do
  grep -Fqi "$phrase" "$CONTRACT" || fail "missing contract phrase: $phrase"
done

polling_pattern='sleep\(|time\.sleep|while[[:space:]]+true|retrying'
resolver_polling_pattern="$polling_pattern|while[[:space:]]+True"
prohibited_authority_pattern='gh[[:space:]]+pr[[:space:]]+(review|ready|merge)|requestReviews|enablePullRequestAutoMerge|mergePullRequest|addLabelsToLabelable|createIssue'

if grep -En "$polling_pattern" "$ACTIONS" "$FAST_PATH"; then
  fail 'mutation helper contains polling behavior'
fi
if grep -En "$resolver_polling_pattern" "$SIMPLE_RESOLVER"; then
  fail 'mutation helper contains polling behavior'
fi

if grep -En "$prohibited_authority_pattern" "$ACTIONS" "$FAST_PATH" "$SIMPLE_RESOLVER"; then
  fail 'mutation helper exposes prohibited GitHub authority'
fi

# Parse Python calls structurally because shell-related keywords may span lines.
python3 - "$ACTIONS" "$FAST_PATH" "$SIMPLE_RESOLVER" <<'PY'
import ast
import pathlib
import sys


def unsafe_calls(source: str, label: str) -> list[str]:
    tree = ast.parse(source, filename=label)
    shell_executable_names = {
        "sh",
        "bash",
        "dash",
        "fish",
        "ksh",
        "zsh",
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
    }
    subprocess_modules: set[str] = set()
    subprocess_functions: set[str] = set()
    subprocess_shell_functions: set[str] = set()
    os_modules: set[str] = set()
    os_shell_functions: set[str] = set()
    asyncio_modules: set[str] = set()
    asyncio_shell_functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_modules.add(alias.asname or alias.name)
                elif alias.name == "os":
                    os_modules.add(alias.asname or alias.name)
                elif alias.name == "asyncio":
                    asyncio_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                for alias in node.names:
                    if alias.name in {
                        "run",
                        "Popen",
                        "call",
                        "check_call",
                        "check_output",
                    }:
                        subprocess_functions.add(alias.asname or alias.name)
                    elif alias.name in {"getoutput", "getstatusoutput"}:
                        subprocess_shell_functions.add(alias.asname or alias.name)
            elif node.module == "os":
                for alias in node.names:
                    if alias.name in {"system", "popen"}:
                        os_shell_functions.add(alias.asname or alias.name)
            elif node.module == "asyncio":
                for alias in node.names:
                    if alias.name == "create_subprocess_shell":
                        asyncio_shell_functions.add(alias.asname or alias.name)

    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            findings.append(
                f"{label}:{node.lineno}: dynamic code execution is prohibited"
            )
            continue
        os_shell_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in os_modules
            and node.func.attr in {"system", "popen"}
        ) or (
            isinstance(node.func, ast.Name)
            and node.func.id in os_shell_functions
        )
        asyncio_shell_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in asyncio_modules
            and node.func.attr == "create_subprocess_shell"
        ) or (
            isinstance(node.func, ast.Name)
            and node.func.id in asyncio_shell_functions
        )
        if os_shell_call or asyncio_shell_call:
            findings.append(
                f"{label}:{node.lineno}: shell process creation is prohibited"
            )
            continue
        subprocess_shell_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in subprocess_modules
            and node.func.attr in {"getoutput", "getstatusoutput"}
        ) or (
            isinstance(node.func, ast.Name)
            and node.func.id in subprocess_shell_functions
        )
        if subprocess_shell_call:
            findings.append(
                f"{label}:{node.lineno}: implicit shell execution is prohibited"
            )
            continue
        subprocess_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in subprocess_modules
            and node.func.attr
            in {"run", "Popen", "call", "check_call", "check_output"}
        ) or (
            isinstance(node.func, ast.Name)
            and node.func.id in subprocess_functions
        )
        if not subprocess_call:
            continue
        command = node.args[0] if node.args else next(
            (
                keyword.value
                for keyword in node.keywords
                if keyword.arg == "args"
            ),
            None,
        )
        if isinstance(command, (ast.List, ast.Tuple)):
            command_tokens = [
                element.value
                if isinstance(element, ast.Constant)
                and isinstance(element.value, str)
                else None
                for element in command.elts
            ]
        else:
            command_tokens = None
        if command_tokens is not None:
            if any(
                command_tokens[index] == "pr"
                and command_tokens[index + 1] in {"review", "ready", "merge"}
                for index in range(len(command_tokens) - 1)
            ):
                findings.append(
                    f"{label}:{node.lineno}: prohibited gh pr authority is exposed"
                )
        if command is not None:
            executable: str | None = None
            if isinstance(command, ast.Constant) and isinstance(command.value, str):
                executable = command.value
            elif (
                isinstance(command, (ast.List, ast.Tuple))
                and command.elts
                and isinstance(command.elts[0], ast.Constant)
                and isinstance(command.elts[0].value, str)
            ):
                executable = command.elts[0].value
            if executable is not None:
                command_name = executable.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if command_name in shell_executable_names:
                    findings.append(
                        f"{label}:{node.lineno}: explicit shell dispatch is prohibited"
                    )
        for keyword in node.keywords:
            if keyword.arg is None:
                findings.append(
                    f"{label}:{node.lineno}: subprocess kwargs cannot prove shell=False"
                )
            elif keyword.arg == "shell" and not (
                isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
            ):
                findings.append(
                    f"{label}:{node.lineno}: subprocess shell execution is prohibited"
                )
            elif keyword.arg == "executable":
                if (
                    isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is None
                ):
                    continue
                if (
                    isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    executable_name = (
                        keyword.value.value.replace("\\", "/")
                        .rsplit("/", 1)[-1]
                        .lower()
                    )
                    if executable_name in shell_executable_names:
                        findings.append(
                            f"{label}:{node.lineno}: shell executable override is prohibited"
                        )
                else:
                    findings.append(
                        f"{label}:{node.lineno}: subprocess executable override cannot prove a non-shell target"
                    )
    return findings


negative_fixtures = {
    "single-line": "import subprocess\nsubprocess.run(command, shell=True)\n",
    "multiline": (
        "import subprocess\nsubprocess.run(\n"
        "    command,\n"
        "    shell=True,\n"
        ")\n"
    ),
    "module-alias": "import subprocess as sp\nsp.Popen(command, shell=True)\n",
    "direct-import": (
        "from subprocess import run as execute\n"
        "execute(command, shell=True)\n"
    ),
    "dynamic-kwargs": "import subprocess\nsubprocess.run(command, **options)\n",
    "eval": "eval(source)\n",
    "exec": "exec(source)\n",
    "os-system": "import os\nos.system(command)\n",
    "asyncio-shell": (
        "import asyncio\n"
        "asyncio.create_subprocess_shell(command)\n"
    ),
    "subprocess-call": (
        "import subprocess\n"
        "subprocess.call(command, shell=True)\n"
    ),
    "subprocess-getoutput": (
        "import subprocess\n"
        "subprocess.getoutput(command)\n"
    ),
    "explicit-shell-dispatch": (
        "import subprocess\n"
        "subprocess.run(['/bin/bash', '-c', command])\n"
    ),
    "array-gh-merge-authority": (
        "import subprocess\n"
        "gh = '/usr/bin/gh'\n"
        "subprocess.run([gh, 'pr', 'merge', '123'])\n"
    ),
    "keyword-array-gh-ready-authority": (
        "import subprocess\n"
        "gh = '/usr/bin/gh'\n"
        "subprocess.run(args=[gh, 'pr', 'ready', '123'])\n"
    ),
    "shell-executable-override": (
        "import subprocess\n"
        "subprocess.run(\n"
        "    ['placeholder', '-c', command],\n"
        "    executable='/bin/bash',\n"
        ")\n"
    ),
    "dynamic-executable-override": (
        "import subprocess\n"
        "subprocess.run(command, executable=launcher)\n"
    ),
}
for fixture_name, fixture_source in negative_fixtures.items():
    if not unsafe_calls(fixture_source, fixture_name):
        raise SystemExit(f"policy negative fixture was not detected: {fixture_name}")

safe_fixture = (
    "import subprocess\n"
    "subprocess.run(command)\n"
    "subprocess.Popen(command, shell=False)\n"
    "subprocess.run(command, executable=None)\n"
    "subprocess.run(command, executable='/usr/bin/git')\n"
)
if unsafe_calls(safe_fixture, "safe-fixture"):
    raise SystemExit("policy safe fixture was rejected")

violations: list[str] = []
for source_path in sys.argv[1:]:
    path = pathlib.Path(source_path)
    violations.extend(unsafe_calls(path.read_text(encoding="utf-8"), str(path)))
if violations:
    raise SystemExit("\n".join(violations))
PY

grep -Eq "$resolver_polling_pattern" <<< 'while True:' \
  || fail 'polling policy negative fixture was not detected'
grep -Eq "$prohibited_authority_pattern" <<< 'mergePullRequest' \
  || fail 'authority policy negative fixture was not detected'

grep -Fq 'secpal-pr-review.py' "$SKILL" || fail 'skill does not route reads through P2.1 helper'
grep -Fq 'secpal-pr-review-actions.py' "$SKILL" || fail 'skill does not route bounded writes through action helper'
grep -Fq 'explicit PR-feedback remediation request' "$SKILL" || fail 'skill trigger is not narrow'
sed -n '/^description:/p' "$SKILL" \
  | grep -Fq 'fixed-thread resolution-only requests' \
  || fail 'skill trigger does not advertise fixed-thread resolution-only requests'
grep -Fq 'not a reviewer' "$SKILL" || fail 'skill reviewer boundary is missing'
simple_skill_section="$(sed -n '/^## Simple fixed-thread resolution$/,/^## /p' "$SKILL")"
test -n "$simple_skill_section" || fail 'skill simple-resolution route is missing'
grep -Fq 'scripts/secpal-resolve-fixed-threads.py' <<<"$simple_skill_section" \
  || fail 'skill does not route fixed-and-pushed requests through the simple resolver'
if grep -Fq 'resolve-batch' <<<"$simple_skill_section"; then
  fail 'skill simple-resolution route still invokes the readiness batch'
fi
grep -Fq 'Simple resolution-only path' "$CONTRACT" \
  || fail 'contract does not define the simple resolution-only path'
grep -Fq 'scripts/secpal-resolve-fixed-threads.py' "$CONTRACT" \
  || fail 'contract does not bind the simple resolver'

git -C "$REPO_ROOT" cat-file -e "$P21_BASELINE^{commit}" 2>/dev/null \
  || fail "accepted P2.1 baseline commit is unavailable: $P21_BASELINE"
cmp "$EVIDENCE" <(git -C "$REPO_ROOT" show "$P21_BASELINE:scripts/secpal-pr-review.py") \
  || fail 'accepted P2.1 evidence helper changed'

test ! -e "$REPO_ROOT/.github/workflows/secpal-pr-review.yml" || fail 'skill must not run automatically'
test ! -e "$REPO_ROOT/.github/workflows/secpal-pr-review.yaml" || fail 'skill must not run automatically'
if grep -En '/home/secpal' "$INTEGRATION"; then
  fail 'integration test must not depend on one host account layout'
fi
grep -Fq 'python3 -m unittest tests/secpal-pr-review-actions-unit.py' "$QUALITY_WORKFLOW" \
  || fail 'guarded-action unit tests are not enforced in CI'
grep -Fq 'python3 -m unittest tests/secpal-resolve-fixed-threads-unit.py' "$QUALITY_WORKFLOW" \
  || fail 'simple resolver unit tests are not enforced in CI'
grep -Fq 'bash tests/secpal-pr-review-skill-policy.sh' "$QUALITY_WORKFLOW" \
  || fail 'skill policy tests are not enforced in CI'
grep -Fq 'bash tests/secpal-pr-review-skill-integration.sh' "$QUALITY_WORKFLOW" \
  || fail 'skill integration tests are not enforced in CI'
grep -Fq './tests/review-governance-suite.sh' "$REGISTRY" \
  || fail 'repository governance suite is not registered'
grep -Fq 'tests/secpal-resolve-fixed-threads-unit.py' "$REGISTRY" \
  || fail 'simple resolver unit tests are not registered'

protected_paths=(
  "$REPO_ROOT"/.github/workflows/*-review-memory.yml
  "$REPO_ROOT"/scripts/*-review-tool.sh
  "$REPO_ROOT"/docs/*-review-automation.md
  "$REPO_ROOT"/AGENTS.md
  "$REPO_ROOT"/templates/*-AGENTS.md
)
relative_paths=()
for path in "${protected_paths[@]}"; do
  relative_paths+=("${path#"$REPO_ROOT"/}")
done
test "$(git -C "$REPO_ROOT" diff --name-only "$P21_BASELINE" -- "${relative_paths[@]}" | wc -l)" -eq 0 \
  || fail 'existing review governance or instruction routing changed'

python3 - "$PLAN_SCHEMA" "$FAST_SCHEMA" "$REGISTRY" <<'PY'
import json
import sys

plan_schema = json.load(open(sys.argv[1], encoding="utf-8"))
fast_schema = json.load(open(sys.argv[2], encoding="utf-8"))
registry = json.load(open(sys.argv[3], encoding="utf-8"))

allowed = {"REACTION", "EVIDENCE_REPLY", "THREAD_RESOLUTION"}
operation_kind = plan_schema["$defs"]["operation"]["properties"]["kind"]["enum"]
assert set(operation_kind) == allowed
serialized = json.dumps(plan_schema, sort_keys=True)
for prohibited in (
    "REVIEW_REQUEST", "READY_TRANSITION", "LABEL", "ISSUE", "REVIEW_SUBMISSION",
    "MERGE", "AUTO_MERGE", "COMMENT_DELETE", "REVIEW_DISMISSAL", "BRANCH_WRITE",
):
    assert f'"{prohibited}"' not in serialized
    assert f'"{prohibited}"' not in json.dumps(fast_schema, sort_keys=True)
assert fast_schema["$defs"]["operation"]["properties"]["kind"] == {
    "const": "THREAD_RESOLUTION"
}

expected = [
    "SecPal/.github", "SecPal/api", "SecPal/frontend", "SecPal/contracts",
    "SecPal/android", "SecPal/changelog", "SecPal/GuardGuide",
    "SecPal/guardguide.de", "SecPal/secpal.app",
]
assert [item["repository"] for item in registry["repositories"]] == expected
for item in registry["repositories"]:
    for command_group in ("focused_validation", "required_local_validation"):
        for command in item[command_group]:
            assert isinstance(command["argv"], list)
            assert command["argv"]
            assert all(isinstance(value, str) and value for value in command["argv"])
PY

printf '✓ finite secpal-pr-review skill policy checks passed\n'
