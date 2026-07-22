#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/preflight-markdownlint-scope.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/scripts" "$workspace/bin" "$workspace/.context"
cp "$REPO_ROOT/scripts/preflight.sh" "$workspace/scripts/preflight.sh"
mkdir -p "$workspace/tests"

log_file="$workspace/npx.log"
test_log="$workspace/test.log"

cat >"$workspace/bin/npx" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$LOG_FILE"
markdownlint_call=0
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

cat >"$workspace/bin/reuse" <<'EOF'
#!/usr/bin/env bash
if [ -e .context/pr-body.md ]; then
  echo "Ignored scratch file reached REUSE" >&2
  exit 7
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

# Git invokes a pre-push hook with the remote name and location as arguments.
(
  cd "$workspace"
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" \
    bash scripts/preflight.sh origin https://github.com/SecPal/.github.git >/dev/null
)

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

if ! grep -Fxq 'validate-ai-instructions' "$test_log" || ! grep -Fxq 'validate-copilot-instructions' "$test_log"; then
  echo "Expected preflight to execute both AI-instructions and legacy Copilot compatibility regression tests" >&2
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
