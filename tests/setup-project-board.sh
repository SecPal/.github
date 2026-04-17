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

assert_contains "$REPO_ROOT/scripts/setup-project-board.sh" "optional GitHub Project Board mirror"
assert_contains "$REPO_ROOT/scripts/setup-project-board.sh" "Issues, milestones, and linked PRs remain the source of truth."
assert_contains "$REPO_ROOT/scripts/setup-project-board.sh" "status: discussion|BFD4F2|Needs decision before implementation"
assert_not_contains "$REPO_ROOT/scripts/setup-project-board.sh" "Specified in feature-requirements.md"

assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "optional GitHub Project Board mirror"
assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "Issues, milestones, and linked PRs remain the source of truth."
assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "status: discussion|BFD4F2|Needs decision before implementation"
assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "The project board is an optional mirrored view"
assert_not_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "Specified in feature-requirements.md"

assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "optional GitHub Project Board mirror"
assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "Issues, milestones, and linked PRs remain the source of truth."
assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "status: discussion|BFD4F2|Needs decision before implementation"
assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "The project board is an optional mirrored view"
assert_not_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "Specified in feature-requirements.md"

# Behavioral coverage guard:
# This test must not be limited to static string checks. Add/maintain integration
# scenarios that execute scripts/setup-project-board.sh with stubbed `gh` and
# simulated interactive input (yes/no), and verify behavior for:
#   - gh unavailable
#   - existing labels/project artifacts
#   - prompt decision branches
# If integration coverage is intentionally disabled, set
# SETUP_PROJECT_BOARD_INTEGRATION_TESTED=1 in the test environment.
: "${SETUP_PROJECT_BOARD_INTEGRATION_TESTED:?Integration coverage missing for setup-project-board.sh (set SETUP_PROJECT_BOARD_INTEGRATION_TESTED=1 only when equivalent integration tests run).}"
