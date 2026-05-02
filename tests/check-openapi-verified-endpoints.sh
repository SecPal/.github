#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

MJS="$ROOT/scripts/check-openapi-verified-endpoints.mjs"
PASS_FIXTURE="$ROOT/tests/fixtures/openapi-verified-presence/pass-min.yaml"
FAIL_FIXTURE="$ROOT/tests/fixtures/openapi-verified-presence/fail-missing.yaml"

if node "$MJS" "$PASS_FIXTURE"; then
  :
else
  echo "Expected pass fixture to succeed" >&2
  exit 1
fi

if fail_stderr=$(node "$MJS" "$FAIL_FIXTURE" 2>&1 1>/dev/null); then
  echo "Expected fail fixture to exit non-zero" >&2
  exit 1
fi
echo "$fail_stderr" | grep -q "Missing operations:" || {
  echo "Fail fixture error output did not mention 'Missing operations:'; got: $fail_stderr" >&2
  exit 1
}

echo "openapi verified-endpoint presence tests OK"
