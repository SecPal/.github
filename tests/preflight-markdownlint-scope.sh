#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/preflight-markdownlint-scope.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/scripts" "$workspace/bin" "$workspace/.context" "$workspace/node_modules/.bin"
cp "$REPO_ROOT/scripts/preflight.sh" "$workspace/scripts/preflight.sh"
mkdir -p "$workspace/tests"

log_file="$workspace/npx.log"
test_log="$workspace/test.log"

cat >"$workspace/bin/npx" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${0##*/} $*" >> "$LOG_FILE"
markdownlint_call=0
if [ "${0##*/}" = markdownlint ]; then
  markdownlint_call=1
fi
tracked_bad=0
for argument in "$@"; do
  case "$argument" in
    markdownlint)
      markdownlint_call=1
      ;;
    .context/*)
      echo "Ignored scratch file reached a repository gate: $argument" >&2
      exit 8
      ;;
    docs/tracked-bad.md)
      tracked_bad=1
      ;;
  esac
done
if [ "$markdownlint_call" -eq 1 ] && [ "$tracked_bad" -eq 1 ]; then
  echo "Tracked Markdown violation reached markdownlint: docs/tracked-bad.md" >&2
  exit 9
fi
exit 0
EOF
chmod +x "$workspace/bin/npx"
cp "$workspace/bin/npx" "$workspace/node_modules/.bin/markdownlint"

cat >"$workspace/bin/reuse" <<'EOF'
#!/usr/bin/env bash
if [ -e .context/pr-body.md ]; then
  echo "Ignored scratch file reached REUSE" >&2
  exit 7
fi
if [ -e .git ]; then
  echo "Git metadata reached REUSE" >&2
  exit 10
fi
if [ ! -e README.md ]; then
  echo "Tracked files did not reach REUSE" >&2
  exit 6
fi
if [ ! -e ./-tracked.md ]; then
  echo "Option-like tracked file did not reach REUSE" >&2
  exit 5
fi
exit 0
EOF
chmod +x "$workspace/bin/reuse"

cat >"$workspace/tests/validate-ai-instructions.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "validate-ai-instructions" >> "$TEST_LOG"
EOF
chmod +x "$workspace/tests/validate-ai-instructions.sh"

cat >"$workspace/tests/validate-copilot-instructions.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "validate-copilot-instructions" >> "$TEST_LOG"
EOF
chmod +x "$workspace/tests/validate-copilot-instructions.sh"

# Stand-ins for the unconditional unittest commands in scripts/preflight.sh.
unit_suites=(
  polyscope-work-graph-advisory
  secpal-pr-advisory-unit
  secpal-work-graph-replan-unit
  secpal-trivy-repository-scan-unit
  secpal-trivy-action-archive
  polyscope-work-graph-replanning
)
for suite in "${unit_suites[@]}"; do
  cat >"$workspace/tests/$suite.py" <<'EOF'
"""Hermetic stand-in proving the maintained unittest command executed."""

import os
from pathlib import Path
import unittest


class PreflightFixtureTest(unittest.TestCase):
    def test_fixture_runs(self):
        with open(os.environ["TEST_LOG"], "a", encoding="utf-8") as log:
            log.write(Path(__file__).stem + "\n")


if __name__ == "__main__":
    unittest.main()
EOF
done

assert_unit_suites_ran() {
  local suite
  for suite in "${unit_suites[@]}"; do
    if [ "$(grep -Fxc "$suite" "$test_log")" -ne 1 ]; then
      echo "Expected preflight to execute required suite exactly once: $suite" >&2
      cat "$test_log" >&2
      exit 1
    fi
  done
}

cat >"$workspace/tests/evidence-architecture-governance.py" <<'EOF'
"""Fixture stand-in proving preflight requires the governance suite."""

import os


with open(os.environ["TEST_LOG"], "a", encoding="utf-8") as log:
    log.write("evidence-architecture-governance\n")
EOF

cat >"$workspace/tests/delivery-lifecycle-governance.py" <<'EOF'
"""Fixture stand-in proving preflight requires Draft-first governance."""

import os


with open(os.environ["TEST_LOG"], "a", encoding="utf-8") as log:
    log.write("delivery-lifecycle-governance\n")
EOF

cat >"$workspace/tests/postgresql-18-baseline-governance.py" <<'EOF'
"""Fixture stand-in proving preflight requires the PostgreSQL baseline suite."""

import os


with open(os.environ["TEST_LOG"], "a", encoding="utf-8") as log:
    log.write("postgresql-18-baseline-governance\n")
EOF

cat >"$workspace/README.md" <<'EOF'
# Test Workspace
EOF

cat >"$workspace/-tracked.md" <<'EOF'
# Leading Option-Like Name
EOF

mkdir -p "$workspace/docs"
cat >"$workspace/docs/guide.md" <<'EOF'
# Nested Test Guide
EOF

cat >"$workspace/.gitignore" <<'EOF'
.context/
EOF

cat >"$workspace/.context/pr-body.md" <<'EOF'
#Skipped heading levels are an ignored scratch violation
EOF

(
  cd "$workspace"
  git init --quiet
  git config user.name 'SecPal Test'
  git config user.email 'test@secpal.dev'
  git add -- .gitignore README.md docs/guide.md -tracked.md
  git commit --quiet -m 'test: seed preflight workspace'
  git checkout --quiet -b test-branch
  git update-ref refs/remotes/origin/main HEAD
  git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main

  cat >"$workspace/bin/mkdir" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" != "-p" ] || [ "${2:-}" != "--" ]; then
  echo "mkdir did not receive an explicit option terminator" >&2
  exit 24
fi
shift 2
exec /bin/mkdir -p -- "$@"
EOF
  chmod +x "$workspace/bin/mkdir"

  cat >"$workspace/bin/cp" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" != "-P" ] || [ "${2:-}" != "--" ]; then
  echo "cp did not receive an explicit option terminator" >&2
  exit 25
fi
shift 2
exec /bin/cp -P -- "$@"
EOF
  chmod +x "$workspace/bin/cp"

  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" bash scripts/preflight.sh >/dev/null
)

assert_unit_suites_ran

# Exercise a real PATH without Node tooling, retaining only fixture prerequisites.
mkdir -p "$workspace/no-node-bin"
for tool in bash git mktemp xargs python3 mkdir cp rm grep sed awk cat find; do
  ln -s "$(command -v "$tool")" "$workspace/no-node-bin/$tool"
done
: >"$log_file"
: >"$test_log"
(
  cd "$workspace"
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/no-node-bin" \
    bash scripts/preflight.sh >"$workspace/no-npx.log" 2>&1
)
if ! grep -Fq 'markdownlint --config .markdownlint.json --' "$log_file"; then
  echo "Expected locked Markdown linting to run without npx" >&2
  exit 1
fi
printf '#Invalid tracked heading\n' >"$workspace/docs/tracked-bad.md"
git -C "$workspace" add docs/tracked-bad.md
if (
  cd "$workspace"
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/no-node-bin" \
    bash scripts/preflight.sh >"$workspace/no-npx-violation.log" 2>&1
); then
  echo "Expected tracked Markdown violations to fail without npx" >&2
  exit 1
fi
grep -Fq 'Tracked Markdown violation reached markdownlint' "$workspace/no-npx-violation.log"
git -C "$workspace" reset --quiet HEAD -- docs/tracked-bad.md
rm "$workspace/docs/tracked-bad.md"
mv "$workspace/node_modules/.bin/markdownlint" "$workspace/saved-markdownlint"
if (
  cd "$workspace"
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/no-node-bin" \
    bash scripts/preflight.sh >"$workspace/no-node-tools.log" 2>&1
); then
  echo "Expected missing locked markdownlint to fail even without npx" >&2
  exit 1
fi
grep -Fq "run 'npm ci' first" "$workspace/no-node-tools.log"
mv "$workspace/saved-markdownlint" "$workspace/node_modules/.bin/markdownlint"

# An absent locked CLI must fail instead of downloading a separate toolchain.
mv "$workspace/node_modules/.bin/markdownlint" "$workspace/saved-markdownlint"
if (
  cd "$workspace"
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" \
    bash scripts/preflight.sh >"$workspace/missing-markdownlint.log" 2>&1
); then
  echo "Expected missing locked markdownlint to fail preflight" >&2
  exit 1
fi
if ! grep -Fq "run 'npm ci' first" "$workspace/missing-markdownlint.log"; then
  echo "Expected missing locked markdownlint to explain how to install it" >&2
  cat "$workspace/missing-markdownlint.log" >&2
  exit 1
fi
if grep -Fq -- '--package markdownlint' "$log_file"; then
  echo "Expected preflight never to download a fallback markdownlint" >&2
  exit 1
fi
mv "$workspace/saved-markdownlint" "$workspace/node_modules/.bin/markdownlint"
: >"$test_log"

# Git invokes a pre-push hook with the remote name and location as arguments.
(
  cd "$workspace"
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" \
    bash scripts/preflight.sh origin https://github.com/SecPal/.github.git >/dev/null
)

assert_unit_suites_ran

if ! grep -Eq '(^|[[:space:]])markdownlint-cli($|[[:space:]])|(^|[[:space:]])markdownlint($|[[:space:]])' "$log_file"; then
  echo "Expected preflight to invoke markdownlint" >&2
  cat "$log_file" >&2
  exit 1
fi

if grep -Fq '**/' "$log_file" || grep -Fq '.context/pr-body.md' "$log_file"; then
  echo "Expected preflight formatters to receive tracked files, not broad filesystem globs or ignored scratch files" >&2
  cat "$log_file" >&2
  exit 1
fi

# Missing or failing Trivy stand-ins must fail through the real preflight command.
for suite in secpal-trivy-repository-scan-unit secpal-trivy-action-archive; do
  stand_in="$workspace/tests/$suite.py"
  mv "$stand_in" "$workspace/saved-stand-in.py"
  for failure in missing failed; do
    if [ "$failure" = failed ]; then
      cat >"$stand_in" <<'EOF'
import unittest


class PreflightFixtureTest(unittest.TestCase):
    def test_fixture_fails(self):
        self.fail("Required fixture stand-in failed")
EOF
    fi
    if (
      cd "$workspace"
      LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" \
        bash scripts/preflight.sh >"$workspace/failure.log" 2>&1
    ); then
      echo "Expected $failure required stand-in to fail preflight: $suite" >&2
      exit 1
    fi
    if [ "$failure" = missing ]; then
      diagnostic="No module named 'tests/$suite'"
    else
      diagnostic="Required fixture stand-in failed"
    fi
    if ! grep -Fq "$diagnostic" "$workspace/failure.log"; then
      echo "Expected $failure stand-in diagnostic for $suite" >&2
      cat "$workspace/failure.log" >&2
      exit 1
    fi
  done
  mv "$workspace/saved-stand-in.py" "$stand_in"
done

cat >"$workspace/docs/tracked-bad.md" <<'EOF'
#Skipped heading levels are a tracked violation
EOF
(
  cd "$workspace"
  git add docs/tracked-bad.md
  set +e
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" bash scripts/preflight.sh >/dev/null 2>&1
  tracked_status=$?
  set -e
  if [ "$tracked_status" -eq 0 ]; then
    echo "Expected a tracked Markdown violation to fail preflight" >&2
    exit 1
  fi
)

if ! grep -Eq 'markdownlint.*(^|[[:space:]])README\.md($|[[:space:]])' "$log_file" \
  || ! grep -Eq 'markdownlint.*(^|[[:space:]])docs/guide\.md($|[[:space:]])' "$log_file" \
  || ! grep -Eq 'markdownlint.*(^|[[:space:]])docs/tracked-bad\.md($|[[:space:]])' "$log_file" \
  || grep -Eq '(^|[[:space:]])\.git/' "$log_file"; then
  echo "Expected preflight markdownlint to receive root and nested tracked Markdown paths only" >&2
  cat "$log_file" >&2
  exit 1
fi

if ! grep -Fxq 'validate-ai-instructions' "$test_log" \
  || ! grep -Fxq 'validate-copilot-instructions' "$test_log" \
  || ! grep -Fxq 'evidence-architecture-governance' "$test_log" \
  || ! grep -Fxq 'postgresql-18-baseline-governance' "$test_log"; then
  echo "Expected preflight to execute the selected fixture compatibility and advisory regression tests" >&2
  cat "$test_log" >&2
  exit 1
fi

cat >"$workspace/bin/cp" <<'EOF'
#!/usr/bin/env bash
exit 23
EOF
chmod +x "$workspace/bin/cp"

reuse_tmp="$workspace/reuse-tmp"
mkdir -p "$reuse_tmp"
set +e
(
  cd "$workspace"
  TMPDIR="$reuse_tmp" PATH="$workspace/bin:$PATH" \
    bash scripts/preflight.sh --reuse-tracked-only >/dev/null 2>&1
)
copy_failure_status=$?
set -e
if [ "$copy_failure_status" -eq 0 ]; then
  echo "Expected a tracked-file copy failure to fail REUSE validation" >&2
  exit 1
fi
if find "$reuse_tmp" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
  echo "Expected REUSE temporary workspaces to be removed after copy failure" >&2
  exit 1
fi
