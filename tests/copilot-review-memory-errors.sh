#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_SCRIPT="$REPO_ROOT/tests/copilot-review-memory.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/copilot-review-memory.yml"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/copilot-review-memory-errors.XXXXXX")"
WORKFLOW_BACKUP="$TMP_DIR/copilot-review-memory.yml.original"
LOG_FILE="$TMP_DIR/test.log"

cleanup() {
  if [ -f "$WORKFLOW_BACKUP" ]; then
    cp "$WORKFLOW_BACKUP" "$WORKFLOW"
  fi
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

cp "$WORKFLOW" "$WORKFLOW_BACKUP"

assert_dedicated_failure() {
  local scenario="$1"
  local expected_message="$2"

  if bash "$TEST_SCRIPT" >"$LOG_FILE" 2>&1; then
    cat "$LOG_FILE" >&2
    echo "Regression test unexpectedly passed for scenario: $scenario" >&2
    exit 1
  fi

  if ! grep -Fq "$expected_message" "$LOG_FILE"; then
    cat "$LOG_FILE" >&2
    echo "Regression test did not emit the dedicated error for scenario: $scenario" >&2
    exit 1
  fi
}

awk '
  /^          \.\/scripts\/copilot-review-tool\.sh scan \\$/ { next }
  { print }
' "$WORKFLOW_BACKUP" >"$WORKFLOW"
assert_dedicated_failure \
  "missing privileged script line" \
  "Copilot review memory workflow must checkout trusted code before running copilot-review-tool.sh."

cp "$WORKFLOW_BACKUP" "$WORKFLOW"

awk '
  /^      - name: Checkout repository$/ { next }
  { print }
' "$WORKFLOW_BACKUP" >"$WORKFLOW"
assert_dedicated_failure \
  "missing checkout line" \
  "Copilot review memory workflow must checkout trusted code before running copilot-review-tool.sh."

echo "✓ copilot review memory workflow failure diagnostics are stable"
