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

log_file="$workspace/npx.log"

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
  LOG_FILE="$log_file" PATH="$workspace/bin:$PATH" bash scripts/preflight.sh >/dev/null
)

if ! grep -F 'markdownlint-cli2' "$log_file" | grep -Eq '(^|[[:space:]])#\.git($|[[:space:]])'; then
  echo "Expected preflight markdownlint invocation to exclude .git paths" >&2
  cat "$log_file" >&2
  exit 1
fi
