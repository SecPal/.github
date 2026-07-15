#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKFLOW="${WORKFLOW:-$SCRIPT_DIR/../.github/workflows/project-automation-core.yml}"

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected project automation workflow was not found: $WORKFLOW" >&2
  exit 1
fi

if grep -q '^          app-id:' "$WORKFLOW"; then
  echo "Project automation must not use the deprecated GitHub App app-id input." >&2
  exit 1
fi

if ! awk '
  function validate_token_step() {
    if (!has_with || !has_client_id || !has_private_key) {
      invalid_token_step = 1
    }
  }

  /^        uses: actions\/create-github-app-token@v3$/ {
    if (in_token_step) {
      validate_token_step()
    }
    token_steps++
    in_token_step = 1
    has_with = has_client_id = has_private_key = 0
    next
  }

  in_token_step && /^      - name:/ {
    validate_token_step()
    in_token_step = 0
    next
  }

  in_token_step && /^        with:$/ { has_with = 1 }
  in_token_step && /^          client-id: \${{ secrets.APP_ID }}$/ { has_client_id = 1 }
  in_token_step && /^          private-key: \${{ secrets.APP_PRIVATE_KEY }}$/ { has_private_key = 1 }

  END {
    if (in_token_step) {
      validate_token_step()
    }
    exit invalid_token_step || token_steps != 3
  }
' "$WORKFLOW"; then
  echo "Each project automation token step must use client-id with the APP_ID and APP_PRIVATE_KEY secret contract." >&2
  exit 1
fi

echo "✓ project automation GitHub App token inputs passed"
