#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# Prevention Strategy Validation Script
# Validates that all prevention measures are properly configured
# Can be run manually or via GitHub Actions

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

REPO="${1:-}"
if [ -z "$REPO" ]; then
  echo "Usage: $0 <owner/repo>"
  echo "Example: $0 SecPal/.github"
  exit 1
fi

echo "🔍 Prevention Strategy Validation for ${REPO}"
echo "================================================"
echo ""

FAILURES=0

# Check 1: Pre-commit hooks (local check only - can't verify remotely)
echo "📋 Check 1: Pre-commit Hooks"
echo "⚠️  Cannot verify remotely - manual check required"
echo "   To verify locally:"
echo "   cd /path/to/repo && [ -f .git/hooks/pre-commit ] && echo '✅ Installed' || echo '❌ Missing'"
echo ""

# Check 2: Branch protection - enforce_admins
echo "📋 Check 2: Branch Protection - enforce_admins"
ENFORCE_ADMINS=$(gh api "/repos/${REPO}/branches/main/protection" --jq '.enforce_admins.enabled' 2>/dev/null || echo "ERROR")
if [ "$ENFORCE_ADMINS" = "true" ]; then
  echo -e "${GREEN}✅${NC} enforce_admins: true"
else
  echo -e "${RED}❌${NC} enforce_admins: ${ENFORCE_ADMINS}"
  ((FAILURES++))
fi
echo ""

# Check 3: Required status checks exist
echo "📋 Check 3: Required Status Checks"
REQUIRED_CHECKS=$(gh api "/repos/${REPO}/branches/main/protection" --jq '.required_status_checks.contexts[]' 2>/dev/null || echo "ERROR")
if [ -z "$REQUIRED_CHECKS" ] || [ "$REQUIRED_CHECKS" = "ERROR" ]; then
  echo -e "${RED}❌${NC} No required status checks configured"
  ((FAILURES++))
else
  echo -e "${GREEN}✅${NC} Required status checks configured:"
  echo "$REQUIRED_CHECKS" | sed 's/^/   - /'
fi
echo ""

# Check 4: Copilot Review in required checks
echo "📋 Check 4: Copilot Review Enforcement"
COPILOT_REQUIRED=$(echo "$REQUIRED_CHECKS" | grep -i "copilot" || echo "")
if [ -n "$COPILOT_REQUIRED" ]; then
  echo -e "${GREEN}✅${NC} Copilot Review is required:"
  echo "$COPILOT_REQUIRED" | sed 's/^/   - /'
else
  echo -e "${RED}❌${NC} Copilot Review NOT in required checks (Lesson #18)"
  ((FAILURES++))
fi
echo ""

# Check 5: Verify workflows exist and are enabled
echo "📋 Check 5: Enforcement Workflows"
echo "Checking recent workflow runs..."
RECENT_RUNS=$(gh run list --repo "$REPO" --limit 10 --json name,conclusion | jq -r '.[] | "\(.name): \(.conclusion)"' || echo "ERROR")
if [ -z "$RECENT_RUNS" ] || [ "$RECENT_RUNS" = "ERROR" ]; then
  echo -e "${YELLOW}⚠️${NC}  Could not fetch recent workflow runs"
else
  echo "Recent runs:"
  echo "$RECENT_RUNS" | sed 's/^/   /'
fi
echo ""

# Check 6: Status check names match job names (sample check)
echo "📋 Check 6: Status Check Names (Lesson #1, #21)"
echo "Required checks:"
echo "$REQUIRED_CHECKS" | sed 's/^/   /'
echo ""
echo "⚠️  Manual verification needed:"
echo "   Compare required checks with actual job names from recent runs"
echo "   gh run view <run_id> --repo $REPO --json jobs --jq '.jobs[].name'"
echo ""

# Check 7: Reusable workflows in use
echo "📋 Check 7: Reusable Workflows (DRY)"
echo "Checking for reusable workflow usage..."
WORKFLOW_FILES=$(gh api "/repos/${REPO}/contents/.github/workflows" --jq '.[].name' 2>/dev/null || echo "ERROR")
if [ -z "$WORKFLOW_FILES" ] || [ "$WORKFLOW_FILES" = "ERROR" ]; then
  echo -e "${YELLOW}⚠️${NC}  Could not fetch workflow files"
else
  for file in $WORKFLOW_FILES; do
    USES_REUSABLE=$(gh api "/repos/${REPO}/contents/.github/workflows/$file" --jq '.content' | base64 -d | grep "uses: SecPal/.github" || echo "")
    if [ -n "$USES_REUSABLE" ]; then
      echo -e "${GREEN}✅${NC} $file uses reusable workflows"
    fi
  done
fi
echo ""

# Summary
echo "================================================"
echo "📊 Validation Summary"
echo "================================================"
if [ $FAILURES -eq 0 ]; then
  echo -e "${GREEN}✅ All checks passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ $FAILURES check(s) failed${NC}"
  echo ""
  echo "🔧 Remediation:"
  echo "   See: docs/PREVENTION-STRATEGY-VALIDATION-2025-10-18.md"
  echo "   See: docs/REPOSITORY-SETUP-GUIDE.md"
  exit 1
fi
