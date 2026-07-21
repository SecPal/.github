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
    tracked-bad.md)
      tracked_bad=1
      ;;
  esac
done
if [ "$markdownlint_call" -eq 1 ] && [ "$tracked_bad" -eq 1 ]; then
  echo "Tracked Markdown violation reached markdownlint: tracked-bad.md" >&2
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
  git add .gitignore README.md
  git commit --quiet -m 'test: seed preflight workspace'
  git checkout --quiet -b test-branch
  git update-ref refs/remotes/origin/main HEAD
  git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" bash scripts/preflight.sh >/dev/null
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

cat >"$workspace/tracked-bad.md" <<'EOF'
#Skipped heading levels are a tracked violation
EOF
(
  cd "$workspace"
  git add tracked-bad.md
  set +e
  LOG_FILE="$log_file" TEST_LOG="$test_log" PATH="$workspace/bin:$PATH" bash scripts/preflight.sh >/dev/null 2>&1
  tracked_status=$?
  set -e
  if [ "$tracked_status" -eq 0 ]; then
    echo "Expected a tracked Markdown violation to fail preflight" >&2
    exit 1
  fi
)

if ! grep -Eq 'markdownlint.*(^|[[:space:]])README\.md($|[[:space:]])' "$log_file" || grep -Eq '(^|[[:space:]])\.git/' "$log_file"; then
  echo "Expected preflight markdownlint to receive the explicit tracked Markdown path only" >&2
  cat "$log_file" >&2
  exit 1
fi

if ! grep -Fxq 'validate-ai-instructions' "$test_log" || ! grep -Fxq 'validate-copilot-instructions' "$test_log"; then
  echo "Expected preflight to execute both AI-instructions and legacy Copilot compatibility regression tests" >&2
  cat "$test_log" >&2
  exit 1
fi
