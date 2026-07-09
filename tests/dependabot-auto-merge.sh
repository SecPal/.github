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
#
# shellcheck disable=SC2016 # This test intentionally matches literal GitHub expressions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_WORKFLOW="$REPO_ROOT/.github/workflows/dependabot-auto-merge.yml"
REUSABLE_WORKFLOW="$REPO_ROOT/.github/workflows/reusable-dependabot-auto-merge.yml"
WORKFLOW_INSTRUCTIONS="$REPO_ROOT/.github/instructions/github-workflows.instructions.md"
WORKFLOW_EXAMPLE="$REPO_ROOT/EXAMPLE_workflow_for_other_repos.yml"
WORKFLOW_CATALOG_README="$REPO_ROOT/.github/workflows/README.md"
ROLLOUT_GUIDE="$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md"

for workflow in "$CALLER_WORKFLOW" "$REUSABLE_WORKFLOW"; do
  if [ ! -f "$workflow" ]; then
    echo "Expected workflow was not found: $workflow" >&2
    exit 1
  fi

  marker_count="$(grep -c '^---$' "$workflow")"
  if [ "$marker_count" -ne 1 ]; then
    echo "Dependabot workflows must contain exactly one YAML document marker: $workflow" >&2
    exit 1
  fi
done

grep -q '^---$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must include a YAML document marker." >&2
  exit 1
}

grep -q '^name: Dependabot Auto-Merge$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must declare its workflow name." >&2
  exit 1
}

if ! awk '
  /^---$/ { marker = NR; next }
  /^name: Dependabot Auto-Merge$/ { name = NR }
  END { exit !(marker > 0 && name == marker + 1) }
' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow YAML document marker must appear immediately before name:." >&2
  exit 1
fi

if [ ! -f "$WORKFLOW_INSTRUCTIONS" ]; then
  echo "Expected workflow instructions were not found: $WORKFLOW_INSTRUCTIONS" >&2
  exit 1
fi

if [ ! -f "$WORKFLOW_EXAMPLE" ]; then
  echo "Expected workflow example was not found: $WORKFLOW_EXAMPLE" >&2
  exit 1
fi

if [ ! -f "$WORKFLOW_CATALOG_README" ]; then
  echo "Expected workflow catalog README was not found: $WORKFLOW_CATALOG_README" >&2
  exit 1
fi

if [ ! -f "$ROLLOUT_GUIDE" ]; then
  echo "Expected rollout guide was not found: $ROLLOUT_GUIDE" >&2
  exit 1
fi

if ! awk '
  /^---$/ { document_start_markers++ }
  /^----+$/ { malformed_document_markers++ }
  END { exit !(document_start_markers == 1 && malformed_document_markers == 0) }
' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must contain exactly one valid YAML document start marker." >&2
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

grep -q '^    uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@main$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must keep auto-merge decisions on the reviewed main-branch reusable workflow." >&2
  exit 1
}

if awk '
  /^  auto-merge:$/ { in_job = 1; next }
  in_job && /^  [[:alnum:]_-]+:$/ { in_job = 0 }
  in_job && /^[[:space:]]+uses: SecPal\/\.github\/\.github\/workflows\/reusable-dependabot-auto-merge\.yml@main$/ {
    reusable_job = 1
  }
  in_job && /^[[:space:]]+timeout-minutes:/ { has_timeout = 1 }
  END { exit !(reusable_job && has_timeout) }
' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not set timeout-minutes on a reusable workflow caller job." >&2
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

awk '
  /^  skip-auto-merge:$/ { in_job = 1; next }
  in_job && /^  [[:alnum:]_-]+:$/ { in_job = 0 }
  in_job && /needs\.check-eligibility\.outputs\.should-auto-merge != '\''true'\''/ { has_output_guard = 1 }
  in_job && /github\.event\.pull_request\.user\.login == '\''dependabot\[bot\]'\''/ { has_author_guard = 1 }
  END { exit !(has_output_guard && has_author_guard) }
' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must gate skip-auto-merge on github.event.pull_request.user.login so maintainer-triggered events on Dependabot PRs still receive the manual-review comment." >&2
  exit 1
}

grep -q '^        uses: dependabot/fetch-metadata@25dd0e34f4fe68f24cc83900b1fe3fe149efef98$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must pin dependabot/fetch-metadata to the v3.1.0 commit with the null update-type fix." >&2
  exit 1
}

grep -q '^        continue-on-error: true$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must soft-fail fetch-metadata into the manual-review path." >&2
  exit 1
}

if grep -q '^          skip-verification: true$' "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must not bypass fetch-metadata commit verification." >&2
  exit 1
fi

grep -q '^#       uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@<trusted-commit-sha>$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow usage example must tell external callers to pin the workflow to a reviewed immutable commit SHA." >&2
  exit 1
}

if grep -q '^#       uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@v1$' "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow usage example must not steer callers back to the stale @v1 tag." >&2
  exit 1
fi

if grep -qE '^[[:space:]]+uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@v1$' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not self-reference the reusable workflow through the stale @v1 tag." >&2
  exit 1
fi

if grep -q '^    uses: \./\.github/workflows/reusable-dependabot-auto-merge\.yml$' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not execute the reusable workflow from the PR merge commit." >&2
  exit 1
fi

if grep -qE 'uses: SecPal/\.github/\.github/workflows/[^[:space:]]+@main$' "$WORKFLOW_EXAMPLE"; then
  echo "Workflow example must not steer cross-repository callers to moving @main refs." >&2
  exit 1
fi

grep -q '^    uses: SecPal/\.github/\.github/workflows/project-automation-v2\.yml@<trusted-commit-sha>$' "$WORKFLOW_EXAMPLE" || {
  echo "Workflow example must pin project automation to a trusted commit SHA." >&2
  exit 1
}

grep -q '^    uses: SecPal/\.github/\.github/workflows/draft-pr-reminder\.yml@<trusted-commit-sha>$' "$WORKFLOW_EXAMPLE" || {
  echo "Workflow example must pin draft PR reminder to a trusted commit SHA." >&2
  exit 1
}

if grep -qE 'uses: SecPal/\.github/\.github/workflows/[^[:space:]]+@main$' "$WORKFLOW_CATALOG_README"; then
  echo "Workflow catalog README must not steer cross-repository callers to moving @main refs." >&2
  exit 1
fi

grep -q '@<trusted-commit-sha>' "$WORKFLOW_CATALOG_README" || {
  echo "Workflow catalog README must document trusted commit SHA pinning for reusable workflows." >&2
  exit 1
}

ROLLOUT_GUIDE_MAIN_REF_PATTERN='^[[:space:]]*uses: SecPal/\.github/\.github/workflows/[^[:space:]]+@main$'

printf 'Do not copy moving refs such as `@main` into consumer repositories.\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" && {
    echo "Rollout guide regression guard must allow prose warnings that mention @main." >&2
    exit 1
  }

printf 'Example prose: uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" && {
    echo "Rollout guide regression guard must ignore prose that embeds a uses: pin mid-line." >&2
    exit 1
  }

printf '    uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" || {
    echo "Rollout guide regression guard must still reject uses: pins that track @main." >&2
    exit 1
  }

if grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" "$ROLLOUT_GUIDE"; then
  echo "Rollout guide must not tell cross-repository consumers to track moving @main refs." >&2
  exit 1
fi

if grep -q '@v1\.0\.0' "$ROLLOUT_GUIDE"; then
  echo "Rollout guide must not steer cross-repository consumers to stale release tags." >&2
  exit 1
fi

grep -q '@<trusted-commit-sha>' "$ROLLOUT_GUIDE" || {
  echo "Rollout guide must document trusted commit SHA pinning for reusable workflows." >&2
  exit 1
}

grep -q '^# SPDX-FileCopyrightText: 2025-2026 SecPal$' "$REPO_ROOT/.github/workflows/quality.yml" || {
  echo "Quality workflow SPDX year must stay current when the file is edited." >&2
  exit 1
}

grep -Fq '          METADATA_STEP_OUTCOME: ${{ steps.metadata.outcome }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must surface the fetch-metadata step outcome." >&2
  exit 1
}

grep -Fq '          DEPENDENCY_GROUP: ${{ steps.metadata.outputs.dependency-group }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must surface the dependency-group metadata output." >&2
  exit 1
}

grep -Fq '          MAINTAINER_CHANGES: ${{ steps.metadata.outputs.maintainer-changes }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must surface the maintainer-changes metadata output." >&2
  exit 1
}

grep -Fq '          PR_TITLE: ${{ github.event.pull_request.title }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must expose the PR title for the metadata-empty fallback path." >&2
  exit 1
}

grep -Fq 'Fallback to PR title parsing only when fetch-metadata returns empty outputs' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must document the metadata-empty title fallback boundary." >&2
  exit 1
}

# Keep every metadata-empty GitHub Actions update on manual review, even when
# the PR title still looks semver-shaped. Title parsing is only allowed for
# non-GitHub-Actions ecosystems with empty fetch-metadata outputs.
grep -Fq 'elif [[ "${PACKAGE_ECOSYSTEM}" != "github-actions" ]] && fallback_from_pr_title; then' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must restrict the metadata-empty PR title fallback to non-GitHub-Actions ecosystems." >&2
  exit 1
}

grep -Fq 'if [[ "${MAINTAINER_CHANGES}" == "true" ]]; then' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must fail closed when Dependabot metadata reports maintainer changes." >&2
  exit 1
}

grep -Fq 'if [[ "${METADATA_STEP_OUTCOME}" != "success" ]]; then' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must fail closed when fetch-metadata itself cannot verify the PR." >&2
  exit 1
}

grep -Fq 'echo "update-type=maintainer-changes" >> "${GITHUB_OUTPUT}"' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must classify maintainer-changed Dependabot PRs for manual review." >&2
  exit 1
}

grep -Fq '[[ -n "${DEPENDENCY_GROUP}" || "${DEPENDENCY_NAMES}" == *,* ]]' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must detect grouped Dependabot PRs conservatively." >&2
  exit 1
}

grep -Fq 'echo "update-type=grouped-update" >> "${GITHUB_OUTPUT}"' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must classify grouped Dependabot PRs for manual review." >&2
  exit 1
}

if grep -Fq 'Eligible for auto-merge (Phase 3): MAJOR' "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must not auto-merge major updates in any phase." >&2
  exit 1
fi

grep -q 'MAJOR semver update requires manual review' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must route major updates to manual review." >&2
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
