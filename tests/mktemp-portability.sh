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

# shellcheck disable=SC2016
assert_contains "$REPO_ROOT/tests/setup-project-board.sh" 'mktemp -d "${TMPDIR:-/tmp}/setup-project-board.XXXXXX"'
assert_not_contains "$REPO_ROOT/tests/setup-project-board.sh" 'mktemp -d -t setup-project-board.XXXXXX'

# shellcheck disable=SC2016
assert_contains "$REPO_ROOT/tests/validate-copilot-instructions.sh" 'mktemp -d "${TMPDIR:-/tmp}/validate-copilot-instructions.XXXXXX"'
assert_not_contains "$REPO_ROOT/tests/validate-copilot-instructions.sh" 'mktemp -d -t validate-copilot-instructions.XXXXXX'
