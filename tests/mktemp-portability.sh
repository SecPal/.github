#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

assert_contains() {
  local path="$1"
  local expected="$2"

  if ! grep -Fq "$expected" "$path"; then
    echo "Expected to find '$expected' in $path" >&2
    exit 1
  fi
}

assert_not_contains() {
  local path="$1"
  local unexpected="$2"

  if grep -Fq "$unexpected" "$path"; then
    echo "Did not expect to find '$unexpected' in $path" >&2
    exit 1
  fi
}

# Enforce "${TMPDIR:-/tmp}/<name>.XXXXXX" templates across shell tests. The
# `mktemp -d -t <template>` pattern is not portable between GNU coreutils and BSD/macOS.
while IFS='|' read -r rel_path slug; do
  [ -n "${rel_path:-}" ] || continue
  path="$REPO_ROOT/$rel_path"
  # Match literal ${TMPDIR:-/tmp} in repository scripts (not shell expansion here).
  # shellcheck disable=SC2016
  expected='mktemp -d "${TMPDIR:-/tmp}/'"$slug"'.XXXXXX"'
  forbidden='mktemp -d -t '"$slug"'.XXXXXX'
  assert_contains "$path" "$expected"
  assert_not_contains "$path" "$forbidden"
done <<'EOF'
tests/setup-project-board.sh|setup-project-board
tests/validate-copilot-instructions.sh|validate-copilot-instructions
tests/audit-closed-epics.sh|audit-closed-epics
tests/setup-hooks.sh|setup-hooks
tests/preflight-markdownlint-scope.sh|preflight-markdownlint-scope
tests/polyscope-rollout.sh|polyscope-rollout
EOF
