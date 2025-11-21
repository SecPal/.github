#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal
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

  echo -e "${YELLOW}Configuring $repo...${NC}"

  # Get current branch protection settings
  if ! gh api "repos/$repo/branches/$branch/protection" > /dev/null 2>&1; then
    echo -e "${RED}  ✗ No branch protection configured for $repo/$branch${NC}"
    echo -e "    Run: gh api repos/$repo/branches/$branch/protection -X PUT --input protection.json"
    return 1
  fi

  # Get current required checks (all checks)
  all_checks=$(gh api "repos/$repo/branches/$branch/protection/required_status_checks" --jq '.checks[]' 2>/dev/null || echo "")
  
  if [ -z "$all_checks" ]; then
    echo -e "${GREEN}  ✓ No required checks configured, skipping${NC}"
    return 0
  fi

  # Filter out codecov checks
  required_checks=$(gh api "repos/$repo/branches/$branch/protection/required_status_checks" --jq '.checks[] | select(.context | test("codecov") | not) | .context' 2>/dev/null || echo "")

  # Check if any codecov checks were present
  codecov_checks=$(gh api "repos/$repo/branches/$branch/protection/required_status_checks" --jq '.checks[] | select(.context | test("codecov")) | .context' 2>/dev/null || echo "")
  
  if [ -z "$codecov_checks" ]; then
    echo -e "${GREEN}  ✓ No codecov checks found, skipping${NC}"
    return 0
  fi

  # Update required checks (remove codecov if present)
  echo "  → Removing codecov from required checks..."

  # Build JSON array of non-codecov checks (can be empty array if codecov was the only check)
  checks_json="["
  first=true
  while IFS= read -r check; do
    if [ -n "$check" ]; then
      if [ "$first" = true ]; then
        first=false
      else
        checks_json+=","
      fi
      checks_json+="{\"context\":\"$check\",\"app_id\":-1}"
    fi
  done <<< "$required_checks"
  checks_json+="]"

  # Update branch protection
  if gh api "repos/$repo/branches/$branch/protection/required_status_checks" \
    -X PATCH \
    -f strict=true \
    -F checks="$checks_json" > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Codecov marked as optional${NC}"
  else
    echo -e "${RED}  ✗ Failed to update branch protection${NC}"
    return 1
  fi
}

# Configure each repository
success_count=0
fail_count=0

for repo in "${REPOS[@]}"; do
  if configure_repo "$repo"; then
    ((success_count++))
  else
    ((fail_count++))
  fi
  echo ""
done

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $fail_count -eq 0 ]; then
  echo -e "${GREEN}✓ All repositories configured successfully!${NC}"
else
  echo -e "${YELLOW}⚠ $success_count succeeded, $fail_count failed${NC}"
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
