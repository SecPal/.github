#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_SCRIPT="$REPO_ROOT/scripts/sync-required-checks.sh"
SHELL_BIN="${BASH:-$(command -v bash)}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sync-required-checks.XXXXXX")"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

assert_payload_has_context() {
  local payload="$1"
  local expected="$2"

  if ! jq -e --arg expected "$expected" '.strict == true and (.checks | any(.context == $expected))' >/dev/null <<<"$payload"; then
    echo "Expected payload to require '$expected'" >&2
    echo "$payload" >&2
    exit 1
  fi
}

if [[ ! -x "$SYNC_SCRIPT" ]]; then
  echo "Expected executable sync script at $SYNC_SCRIPT" >&2
  exit 1
fi

if grep -Fq 'XXXXXX.json' "$SYNC_SCRIPT"; then
  echo "Sync script uses a BSD-incompatible mktemp template with a suffix after the X placeholder." >&2
  exit 1
fi

if ! grep -Fq 'sync-required-checks.${repo//[^A-Za-z0-9]/_}.json.XXXXXX' "$SYNC_SCRIPT"; then
  echo "Sync script must use a portable mktemp template whose X placeholder is at the end." >&2
  exit 1
fi

api_payload="$(bash "$SYNC_SCRIPT" --repo api --print-payload)"
assert_payload_has_context "$api_payload" "Copilot Instructions / Validate Copilot Instructions"
assert_payload_has_context "$api_payload" "PEST Tests"

android_payload="$(bash "$SYNC_SCRIPT" --repo android --print-payload)"
assert_payload_has_context "$android_payload" "Check PR Size / Check PR Size"
assert_payload_has_context "$android_payload" "Markdown Lint / Lint Markdown Files"
assert_payload_has_context "$android_payload" "Copilot Instructions / Validate Copilot Instructions"

guardguide_payload="$(bash "$SYNC_SCRIPT" --repo GuardGuide --print-payload)"
assert_payload_has_context "$guardguide_payload" "Pest Tests (PostgreSQL)"
assert_payload_has_context "$guardguide_payload" "Pest Tests (MariaDB)"
assert_payload_has_context "$guardguide_payload" "CodeQL"

secpal_app_payload="$(bash "$SYNC_SCRIPT" --repo secpal.app --print-payload)"
assert_payload_has_context "$secpal_app_payload" "Node Tests / Run Tests"
assert_payload_has_context "$secpal_app_payload" "CodeQL"

github_payload="$(bash "$SYNC_SCRIPT" --repo .github --print-payload)"
assert_payload_has_context "$github_payload" "Validate PR Evidence"
assert_payload_has_context "$github_payload" "Validate PR Title And Body Language"
assert_payload_has_context "$github_payload" "Validate Signed PR Commits"

set +e
unknown_output="$(bash "$SYNC_SCRIPT" --repo does-not-exist --print-payload 2>&1)"
unknown_status=$?
set -e

if [[ $unknown_status -eq 0 ]]; then
  echo "Expected unknown repo lookup to fail" >&2
  exit 1
fi

if [[ "$unknown_output" != *"Unknown repository"* ]]; then
  echo "Expected unknown repo error to mention 'Unknown repository'" >&2
  echo "$unknown_output" >&2
  exit 1
fi

missing_jq_bin="$TMP_DIR/missing-jq-bin"
mkdir -p "$missing_jq_bin"
ln -s "$(command -v cat)" "$missing_jq_bin/cat"

set +e
missing_jq_output="$(PATH="$missing_jq_bin" "$SHELL_BIN" "$SYNC_SCRIPT" --repo api --print-payload 2>&1)"
missing_jq_status=$?
set -e

if [[ $missing_jq_status -ne 2 ]]; then
  echo "Expected --print-payload without jq to exit with status 2" >&2
  echo "$missing_jq_output" >&2
  exit 1
fi

if [[ "$missing_jq_output" != *"Missing required command: jq"* ]]; then
  echo "Expected --print-payload without jq to report the missing jq dependency" >&2
  echo "$missing_jq_output" >&2
  exit 1
fi
