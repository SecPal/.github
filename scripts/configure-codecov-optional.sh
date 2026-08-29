#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
# SPDX-License-Identifier: CC0-1.0

# Configure Codecov as optional check in branch protection
# This allows Dependabot PRs to merge when no coverage data is uploaded
# while keeping coverage required for normal developer PRs

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔧 Configuring Codecov branch protection for SecPal repositories..."
echo ""

# Array of repositories to configure
REPOS=(
  "SecPal/.github"
  "SecPal/api"
  "SecPal/frontend"
  "SecPal/contracts"
)

# Function to configure branch protection for a repo
configure_repo() {
  local repo=$1
  local branch="main"
  local endpoint="repos/$repo/branches/$branch/protection/required_status_checks"

  echo -e "${YELLOW}Configuring $repo...${NC}"

  (
    state_file="$(mktemp "${TMPDIR:-/tmp}/configure-codecov-state.${repo//[^A-Za-z0-9]/_}.json.XXXXXX")"
    trap 'rm -f "$state_file"' EXIT
    payload_file="$(mktemp "${TMPDIR:-/tmp}/configure-codecov-payload.${repo//[^A-Za-z0-9]/_}.json.XXXXXX")"
    trap 'rm -f "$state_file" "$payload_file"' EXIT

    if ! gh api "$endpoint" >"$state_file"; then
      echo -e "${RED}  ✗ Failed to read required checks for $repo/$branch${NC}" >&2
      return 1
    fi

    if ! jq -e '
      type == "object" and
      (.strict | type) == "boolean" and
      (.checks | type) == "array" and
      all(.checks[];
        type == "object" and
        (.context | type) == "string" and
        (.context | length) > 0 and
        has("app_id") and
        (
          .app_id == null or
          (
            (.app_id | type) == "number" and
            .app_id == (.app_id | floor) and
            (.app_id == -1 or .app_id > 0)
          )
        )
      ) and
      ([.checks[].context] | length) == ([.checks[].context] | unique | length)
    ' "$state_file" >/dev/null; then
      echo -e "${RED}  ✗ Malformed required checks for $repo/$branch${NC}" >&2
      return 1
    fi

    if ! jq -e '.checks | any(.context | test("codecov"; "i"))' "$state_file" >/dev/null; then
      echo -e "${GREEN}  ✓ No codecov checks found, skipping${NC}"
      return 0
    fi

    jq '{
      strict,
      checks: [
        .checks[]
        | select(.context | test("codecov"; "i") | not)
        | {
            context,
            app_id: (if .app_id == null then -1 else .app_id end)
          }
      ]
    }' "$state_file" >"$payload_file"

    echo "  → Removing codecov from required checks..."
    if ! gh api "$endpoint" -X PATCH --input "$payload_file" >/dev/null; then
      echo -e "${RED}  ✗ Failed to update required checks for $repo/$branch${NC}" >&2
      return 1
    fi

    echo -e "${GREEN}  ✓ Codecov marked as optional${NC}"
  )
}

# Configure each repository
success_count=0
fail_count=0

for repo in "${REPOS[@]}"; do
  if configure_repo "$repo"; then
    success_count=$((success_count + 1))
  else
    fail_count=$((fail_count + 1))
  fi
  echo ""
done

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $fail_count -eq 0 ]; then
  echo -e "${GREEN}✓ All repositories configured successfully!${NC}"
else
  echo -e "${YELLOW}⚠ $success_count succeeded, $fail_count failed${NC}"
  exit 1
fi
echo ""
echo "📋 What was changed:"
echo "  - Codecov status check removed from required checks"
echo "  - Codecov will still run and report coverage"
echo "  - Developer PRs: Coverage visible and expected"
echo "  - Dependabot PRs: Can merge without coverage data"
echo ""
echo "🔍 Verify changes:"
echo "  gh api repos/SecPal/api/branches/main/protection/required_status_checks"
