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

# Enforce "${TMPDIR:-/tmp}/<basename>.XXXXXX" for every tests/*.sh that uses mktemp
# (slug matches the script basename so new tests are covered without editing this file).
# The `mktemp -d -t <template>` pattern is not portable between GNU coreutils and BSD/macOS.
shopt -s nullglob
for path in "$REPO_ROOT"/tests/*.sh; do
  base="${path##*/}"
  if [ "$base" = "mktemp-portability.sh" ]; then
    continue
  fi
  if ! grep -Fq 'mktemp' "$path"; then
    continue
  fi
  if grep -Fq 'mktemp -d -t' "$path"; then
    printf 'Non-portable mktemp -d -t usage in tests/%s; use explicit TMPDIR template paths ending in .XXXXXX (see tests/setup-hooks.sh).\n' "$base" >&2
    exit 1
  fi
  slug="${base%.sh}"
  # Match literal ${TMPDIR:-/tmp} in repository scripts (not shell expansion here).
  # shellcheck disable=SC2016
  expected='mktemp -d "${TMPDIR:-/tmp}/'"$slug"'.XXXXXX"'
  assert_contains "$path" "$expected"
done
shopt -u nullglob
