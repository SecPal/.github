#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression tests for the .github repository's Dependabot caller workflow.
# Verifies the caller explicitly grants the write permissions required by the
# reusable workflow and only invokes it for Dependabot-authored PRs so regular
# pull requests do not fail during workflow startup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/dependabot-auto-merge.yml"

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

grep -q '^permissions:$' "$WORKFLOW" || {
  echo "Dependabot caller workflow must declare explicit permissions." >&2
  exit 1
}

grep -q '^  contents: write$' "$WORKFLOW" || {
  echo "Dependabot caller workflow must grant contents: write." >&2
  exit 1
}

grep -q '^  pull-requests: write$' "$WORKFLOW" || {
  echo "Dependabot caller workflow must grant pull-requests: write." >&2
  exit 1
}

grep -q "^    if: github.actor == 'dependabot\\[bot\\]'$" "$WORKFLOW" || {
  echo "Dependabot caller workflow must skip non-Dependabot PRs before invoking the reusable workflow." >&2
  exit 1
}

grep -q '^    uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@v1$' "$WORKFLOW" || {
  echo "Dependabot caller workflow must keep the reusable workflow uses line pinned to @v1." >&2
  exit 1
}

echo "✓ dependabot auto-merge workflow regression checks passed"
