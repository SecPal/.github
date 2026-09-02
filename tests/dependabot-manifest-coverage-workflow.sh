#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
workflow="$root/.github/workflows/reusable-dependabot-manifest-coverage.yml"

grep -Fq "workflow_call:" "$workflow"
grep -Fq "permissions: {}" "$workflow"
grep -Fq "manifest-coverage:" "$workflow"
grep -Fq "cadence-policy:" "$workflow"

if grep -Eq 'issues:[[:space:]]*write|packages:[[:space:]]*write|deployments:[[:space:]]*write' "$workflow"; then
  echo "Dependabot guard workflow has forbidden write permissions." >&2
  exit 1
fi

# The literal GitHub expression must not be expanded by this validation shell.
# shellcheck disable=SC2016
immutable_checkouts="$(grep -Fc 'ref: ${{ fromJSON(toJSON(job)).workflow_sha }}' "$workflow")"
if [ "$immutable_checkouts" -ne 2 ]; then
  echo "Both assertions must load governance from the called workflow SHA." >&2
  exit 1
fi

if [ "$(grep -Fc 'path: .secpal-subject' "$workflow")" -ne 2 ]; then
  echo "Both assertions must isolate the subject checkout from governance." >&2
  exit 1
fi

# shellcheck disable=SC2016
if [ "$(grep -Fc -- '--root "$GITHUB_WORKSPACE/.secpal-subject"' "$workflow")" -ne 2 ]; then
  echo "Both assertions must inspect only the isolated subject checkout." >&2
  exit 1
fi

if grep -Fq 'node scripts/secpal-dependabot-manifest-coverage.mjs' "$workflow"; then
  echo "Workflow may not execute the caller checkout's governance script." >&2
  exit 1
fi

if [ "$(grep -Fc 'npm ci --ignore-scripts' "$workflow")" -ne 2 ]; then
  echo "Both jobs must install immutable parser dependencies without lifecycle scripts." >&2
  exit 1
fi

echo "Dependabot manifest coverage reusable-workflow boundary passed."
