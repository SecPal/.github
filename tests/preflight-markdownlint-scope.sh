#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/preflight-markdownlint-scope.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/scripts" "$workspace/bin"
cp "$REPO_ROOT/scripts/preflight.sh" "$workspace/scripts/preflight.sh"
mkdir -p "$workspace/tests"

log_file="$workspace/npx.log"
test_log="$workspace/test.log"

cat >"$workspace/bin/npx" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$LOG_FILE"
exit 0
EOF
chmod +x "$workspace/bin/npx"

cat >"$workspace/bin/reuse" <<'EOF'
#!/usr/bin/env bash
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

(
  cd "$workspace"
  git init --quiet
  git config user.name 'SecPal Test'
  git config user.email 'test@secpal.dev'
  git add README.md
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

if ! grep -Eq '(^|[[:space:]])--ignore($|[[:space:]])' "$log_file" || ! grep -Eq '(^|[[:space:]])\.git($|[[:space:]])' "$log_file"; then
  echo "Expected preflight markdownlint invocation to exclude .git paths" >&2
  cat "$log_file" >&2
  exit 1
fi

if ! grep -Fxq 'validate-ai-instructions' "$test_log" || ! grep -Fxq 'validate-copilot-instructions' "$test_log"; then
  echo "Expected preflight to execute both AI-instructions and legacy Copilot compatibility regression tests" >&2
  cat "$test_log" >&2
  exit 1
fi
