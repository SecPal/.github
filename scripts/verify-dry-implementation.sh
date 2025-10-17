#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Note: Don't use set -e, we want to collect all test results

echo "🔍 DRY Implementation Verification Script"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

passed=0
failed=0

# Test 1: Check template exists
echo "Test 1: Check template script exists..."
if [ -f ".github/templates/scripts/check-licenses.sh" ]; then
    echo -e "${GREEN}✅ PASS${NC}: Template exists"
    ((passed++))
else
    echo -e "${RED}❌ FAIL${NC}: Template not found"
    ((failed++))
fi

# Test 2: Check reusable workflows exist
echo ""
echo "Test 2: Check reusable workflows exist..."
missing=false
for workflow in reusable-dependency-review.yml reusable-license-check.yml reusable-copilot-review.yml; do
    if [ -f ".github/workflows/$workflow" ]; then
        echo -e "${GREEN}  ✅${NC} $workflow found"
    else
        echo -e "${RED}  ❌${NC} $workflow missing"
        missing=true
    fi
done

if [ "$missing" = false ]; then
    ((passed++))
else
    ((failed++))
fi

# Test 3: Check automation workflows exist
echo ""
echo "Test 3: Check automation workflows exist..."
missing=false
for workflow in sync-templates.yml detect-template-drift.yml; do
    if [ -f ".github/workflows/$workflow" ]; then
        echo -e "${GREEN}  ✅${NC} $workflow found"
    else
        echo -e "${RED}  ❌${NC} $workflow missing"
        missing=true
    fi
done

if [ "$missing" = false ]; then
    ((passed++))
else
    ((failed++))
fi

# Test 4: Verify .github workflows use reusables
echo ""
echo "Test 4: Verify .github workflows migrated to reusables..."
errors=false

if grep -q "uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main" .github/workflows/dependency-review.yml 2>/dev/null; then
    echo -e "${GREEN}  ✅${NC} dependency-review.yml uses reusable"
else
    echo -e "${RED}  ❌${NC} dependency-review.yml not migrated"
    errors=true
fi

if grep -q "uses: SecPal/.github/.github/workflows/reusable-license-check.yml@main" .github/workflows/license-check.yml 2>/dev/null; then
    echo -e "${GREEN}  ✅${NC} license-check.yml uses reusable"
else
    echo -e "${RED}  ❌${NC} license-check.yml not migrated"
    errors=true
fi

if [ "$errors" = false ]; then
    ((passed++))
else
    ((failed++))
fi

# Test 5: Verify contracts workflows use reusables
echo ""
echo "Test 5: Verify contracts workflows migrated to reusables..."

# Use environment variable if set, otherwise default to sibling directory
# CONTRACTS_REPO_PATH: Optional path to contracts repository (default: ../contracts)
CONTRACTS_PATH="${CONTRACTS_REPO_PATH:-../contracts}"

if cd "$CONTRACTS_PATH" 2>/dev/null; then
    if [ -d ".github/workflows" ]; then
        errors=false

        if grep -q "uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main" .github/workflows/dependency-review.yml 2>/dev/null; then
            echo -e "${GREEN}  ✅${NC} dependency-review.yml uses reusable"
        else
            echo -e "${RED}  ❌${NC} dependency-review.yml not migrated"
            errors=true
        fi

        if grep -q "uses: SecPal/.github/.github/workflows/reusable-license-check.yml@main" .github/workflows/license-check.yml 2>/dev/null; then
            echo -e "${GREEN}  ✅${NC} license-check.yml uses reusable"
        else
            echo -e "${RED}  ❌${NC} license-check.yml not migrated"
            errors=true
        fi

        if [ "$errors" = false ]; then
            ((passed++))
        else
            ((failed++))
        fi

        cd - > /dev/null
    else
        echo -e "${YELLOW}⚠️  SKIP${NC}: .github/workflows directory not found in contracts repo"
        ((failed++))
        cd - > /dev/null
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC}: contracts repo not found at $CONTRACTS_PATH"
    echo -e "${YELLOW}   ${NC}Set CONTRACTS_REPO_PATH env var to specify location"
    ((failed++))
fi

# Test 6: Check Lesson #27 exists
echo ""
echo "Test 6: Check documentation..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Validate that GITHUB_ROOT exists before attempting to cd
if [ ! -d "$GITHUB_ROOT" ]; then
    echo -e "${RED}  ❌${NC} GITHUB_ROOT directory does not exist: $GITHUB_ROOT"
    exit 1
fi

# Navigate to .github root directory
# Note: All subsequent tests (Test 6-8) assume working directory is the .github repository root
if ! cd "$GITHUB_ROOT"; then
    echo -e "${RED}  ❌${NC} Failed to navigate to .github root directory"
    exit 1
fi

if [ -f "docs/lessons/lesson-27.md" ]; then
    echo -e "${GREEN}  ✅${NC} Lesson #27 exists"
    ((passed++))
else
    echo -e "${RED}  ❌${NC} Lesson #27 missing"
    ((failed++))
fi

# Test 7: Verify YAML syntax
echo ""
echo "Test 7: Validate YAML syntax..."
yaml_errors=false

for workflow in .github/workflows/sync-templates.yml .github/workflows/detect-template-drift.yml; do
    if python3 -c "import yaml; yaml.safe_load(open('$workflow'))" 2>/dev/null; then
        echo -e "${GREEN}  ✅${NC} $(basename $workflow) valid"
    else
        echo -e "${RED}  ❌${NC} $(basename $workflow) invalid YAML"
        yaml_errors=true
    fi
done

if [ "$yaml_errors" = false ]; then
    ((passed++))
else
    ((failed++))
fi

# Test 8: Check DRY-ANALYSIS updated
echo ""
echo "Test 8: Check DRY-ANALYSIS-AND-STRATEGY.md updated..."
if grep -q "PHASE 1 & 2 COMPLETE" docs/DRY-ANALYSIS-AND-STRATEGY.md 2>/dev/null; then
    echo -e "${GREEN}  ✅${NC} Document shows Phase 1 & 2 complete"
    ((passed++))
else
    echo -e "${RED}  ❌${NC} Document not updated"
    ((failed++))
fi

# Summary
echo ""
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="
echo -e "Passed: ${GREEN}$passed${NC}"
echo -e "Failed: ${RED}$failed${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    echo ""
    echo "DRY Implementation is complete and verified!"
    echo "Ready for commit and PR creation."
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please review the failures above."
    exit 1
fi
