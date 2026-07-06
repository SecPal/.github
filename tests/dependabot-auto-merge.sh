#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression tests for the .github repository's Dependabot caller and reusable
# workflows. Verifies the caller explicitly grants the write permissions
# required by the reusable workflow and that both workflows gate on the PR
# author rather than the event actor so maintainer-triggered `reopened` and
# `ready_for_review` events on Dependabot-authored PRs still enroll in
# auto-merge.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_WORKFLOW="$REPO_ROOT/.github/workflows/dependabot-auto-merge.yml"
REUSABLE_WORKFLOW="$REPO_ROOT/.github/workflows/reusable-dependabot-auto-merge.yml"
WORKFLOW_INSTRUCTIONS="$REPO_ROOT/.github/instructions/github-workflows.instructions.md"

for workflow in "$CALLER_WORKFLOW" "$REUSABLE_WORKFLOW"; do
  if [ ! -f "$workflow" ]; then
    echo "Expected workflow was not found: $workflow" >&2
    exit 1
  fi
done

if [ ! -f "$WORKFLOW_INSTRUCTIONS" ]; then
  echo "Expected workflow instructions were not found: $WORKFLOW_INSTRUCTIONS" >&2
  exit 1
fi

grep -q '^permissions:$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must declare explicit permissions." >&2
  exit 1
}

grep -q '^  contents: write$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must grant contents: write." >&2
  exit 1
}

grep -q '^  pull-requests: write$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must grant pull-requests: write." >&2
  exit 1
}

# Gate on the PR author (github.event.pull_request.user.login) rather than the
# event actor (github.actor). The actor is the user who triggered the latest
# event, which for `reopened` / `ready_for_review` is often a maintainer rather
# than Dependabot itself. Gating on the author preserves the Dependabot-only
# scope while still enrolling maintainer-triggered events on Dependabot PRs.
grep -q "^    if: github.event.pull_request.user.login == 'dependabot\\[bot\\]'$" "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must gate on github.event.pull_request.user.login so maintainer-triggered reopened / ready_for_review events on Dependabot PRs are not skipped." >&2
  exit 1
}

# Defensive guard against regression: the brittle actor-based gate must not
# come back, because it silently skips auto-merge enrollment whenever a
# maintainer reopens or marks a Dependabot PR as ready for review. The
# pattern is anchored to real YAML `if:` lines so explanatory comments or
# documentation that mention the old `github.actor` pattern do not trip the
# check.
if grep -qE "^[[:space:]]+if:.*github\.actor == 'dependabot\[bot\]'" "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not gate on github.actor; use github.event.pull_request.user.login instead so maintainer-triggered events on Dependabot PRs are not skipped." >&2
  exit 1
fi

grep -q '^    uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@v1$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must keep the reusable workflow uses line pinned to @v1." >&2
  exit 1
}

# Reusable-workflow caller jobs cannot declare timeout-minutes alongside uses:.
# GitHub rejects that combination at workflow-parse time before any job starts.
if grep -q '^    timeout-minutes:' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not set timeout-minutes on a reusable-workflow uses job." >&2
  exit 1
fi

grep -q 'Reusable-workflow caller jobs that use `jobs\.<job_id>\.uses` cannot set `timeout-minutes` on the caller job' "$WORKFLOW_INSTRUCTIONS" || {
  echo "Workflow instructions must document the reusable-workflow caller timeout-minutes exception." >&2
  exit 1
}

# The reusable workflow's check-eligibility and skip-auto-merge jobs must also
# gate on the PR author so the same maintainer-triggered events are not
# skipped when other repositories invoke this reusable workflow directly.
grep -q "^    if: github.event.pull_request.user.login == 'dependabot\\[bot\\]'$" "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must gate check-eligibility on github.event.pull_request.user.login so maintainer-triggered reopened / ready_for_review events on Dependabot PRs are not skipped." >&2
  exit 1
}

grep -q "needs.check-eligibility.outputs.should-auto-merge != 'true' && github.event.pull_request.user.login == 'dependabot\\[bot\\]'" "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must gate skip-auto-merge on github.event.pull_request.user.login so maintainer-triggered events on Dependabot PRs still receive the manual-review comment." >&2
  exit 1
}

# Same anchoring as the caller guard: only flag actual YAML `if:` lines so
# explanatory comments or documentation mentioning the old `github.actor`
# pattern do not trip the regression check.
if grep -qE "^[[:space:]]+if:.*github\.actor == 'dependabot\[bot\]'" "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must not gate on github.actor; use github.event.pull_request.user.login instead so maintainer-triggered events on Dependabot PRs are not skipped." >&2
  exit 1
fi

echo "✓ dependabot auto-merge workflow regression checks passed"
