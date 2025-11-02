#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to print test result
print_result() {
    local test_name="$1"
    local status="$2"
    local message="${3:-}"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$status" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗${NC} $test_name"
        if [ -n "$message" ]; then
            echo -e "  ${YELLOW}→${NC} $message"
        fi
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# Test 1: Check if copilot-instructions.md exists
test_instructions_exists() {
    if [ -f ".github/copilot-instructions.md" ]; then
        print_result "copilot-instructions.md exists" "PASS"
    else
        print_result "copilot-instructions.md exists" "FAIL" "File not found"
    fi
}

# Test 2: Check if copilot-config.yaml exists
test_yaml_config_exists() {
    if [ -f ".github/copilot-config.yaml" ]; then
        print_result "copilot-config.yaml exists" "PASS"
    else
        print_result "copilot-config.yaml exists" "FAIL" "File not found (optional)"
    fi
}

# Test 3: Check REUSE compliance for instructions
test_instructions_reuse() {
    if [ -f ".github/copilot-instructions.md.license" ]; then
        if grep -q "CC0-1.0" ".github/copilot-instructions.md.license"; then
            print_result "copilot-instructions.md has REUSE license" "PASS"
        else
            print_result "copilot-instructions.md has REUSE license" "FAIL" "Wrong license (expected CC0-1.0)"
        fi
    else
        print_result "copilot-instructions.md has REUSE license" "FAIL" "License file not found"
    fi
}

# Test 4: Check REUSE compliance for YAML config
test_yaml_config_reuse() {
    if [ -f ".github/copilot-config.yaml" ]; then
        if [ -f ".github/copilot-config.yaml.license" ]; then
            if grep -q "CC0-1.0" ".github/copilot-config.yaml.license"; then
                print_result "copilot-config.yaml has REUSE license" "PASS"
            else
                print_result "copilot-config.yaml has REUSE license" "FAIL" "Wrong license (expected CC0-1.0)"
            fi
        else
            print_result "copilot-config.yaml has REUSE license" "FAIL" "License file not found"
        fi
    else
        print_result "copilot-config.yaml has REUSE license" "PASS" "Skipped (YAML config not present)"
    fi
}

# Test 5: Check markdown lint compliance
test_markdown_lint() {
    if command -v npx &> /dev/null; then
        if npx markdownlint-cli2 .github/copilot-instructions.md &> /dev/null; then
            print_result "copilot-instructions.md passes markdown lint" "PASS"
        else
            print_result "copilot-instructions.md passes markdown lint" "FAIL" "Run: npx markdownlint-cli2 .github/copilot-instructions.md --fix"
        fi
    else
        print_result "copilot-instructions.md passes markdown lint" "PASS" "Skipped (markdownlint-cli2 not available)"
    fi
}

# Test 6: Check YAML syntax validity
test_yaml_syntax() {
    if [ -f ".github/copilot-config.yaml" ]; then
        if command -v yq &> /dev/null; then
            if yq eval '.version' .github/copilot-config.yaml &> /dev/null; then
                print_result "copilot-config.yaml has valid syntax" "PASS"
            else
                print_result "copilot-config.yaml has valid syntax" "FAIL" "YAML parsing error"
            fi
        else
            print_result "copilot-config.yaml has valid syntax" "PASS" "Skipped (yq not available)"
        fi
    else
        print_result "copilot-config.yaml has valid syntax" "PASS" "Skipped (YAML config not present)"
    fi
}

# Test 7: Check for @EXTENDS reference in repo-specific instructions
test_extends_reference() {
    local repo_type="${1:-org}"

    if [ "$repo_type" != "org" ]; then
        if [ -f ".github/copilot-instructions.md" ]; then
            if grep -q "@EXTENDS" .github/copilot-instructions.md; then
                print_result "repo-specific instructions use @EXTENDS" "PASS"
            else
                print_result "repo-specific instructions use @EXTENDS" "FAIL" "Missing @EXTENDS reference to org instructions"
            fi
        else
            print_result "repo-specific instructions use @EXTENDS" "PASS" "Skipped (no repo-specific instructions)"
        fi
    else
        print_result "repo-specific instructions use @EXTENDS" "PASS" "Skipped (org-level instructions)"
    fi
}

# Test 8: Check critical rules section exists
test_critical_rules() {
    if [ -f ".github/copilot-instructions.md" ]; then
        if grep -qiE "critical[[:space:]]+rules|core[[:space:]]+principles" .github/copilot-instructions.md; then
            print_result "instructions contain critical rules" "PASS"
        else
            print_result "instructions contain critical rules" "FAIL" "No critical rules/principles found"
        fi
    else
        print_result "instructions contain critical rules" "FAIL" "Instructions file not found"
    fi
}

# Test 9: Check for org-wide instructions reminder (repo-specific only)
test_org_reminder() {
    local repo_type="${1:-org}"

    if [ "$repo_type" != "org" ]; then
        if [ -f ".github/copilot-instructions.md" ]; then
            # Use text-only pattern for portability (omit emoji for encoding safety)
            if grep -q "AI MUST READ ORGANIZATION-WIDE INSTRUCTIONS FIRST" .github/copilot-instructions.md; then
                print_result "repo-specific instructions have org-wide reminder" "PASS"
            else
                print_result "repo-specific instructions have org-wide reminder" "FAIL" "Missing reminder block for org-wide instructions"
            fi
        else
            print_result "repo-specific instructions have org-wide reminder" "FAIL" "Instructions file not found"
        fi
    else
        print_result "repo-specific instructions have org-wide reminder" "PASS" "Skipped (org-level instructions)"
    fi
}

# Main execution
main() {
    echo "========================================="
    echo "Copilot Instructions Validation"
    echo "========================================="
    echo ""

    # Detect repository type (robust detection)
    local repo_type="org"
    local has_laravel=0
    local has_vite=0
    local has_openapi=0

    # Check for Laravel-specific files
    if [ -f "artisan" ] || [ -f "composer.json" ]; then
        has_laravel=1
    fi

    # Check package.json dependencies if it exists
    if [ -f "package.json" ]; then
        if grep -q "vite" package.json 2>/dev/null; then
            has_vite=1
        fi
        if grep -q "openapi" package.json 2>/dev/null; then
            has_openapi=1
        fi
    fi

    # Determine repo type (Laravel takes precedence)
    if [ "$has_laravel" -eq 1 ]; then
        repo_type="api"
    elif [ "$has_openapi" -eq 1 ] && [ "$has_laravel" -eq 0 ]; then
        repo_type="contracts"
    elif [ "$has_vite" -eq 1 ] && [ "$has_laravel" -eq 0 ]; then
        repo_type="frontend"
    fi

    echo "Repository Type: $repo_type"
    echo ""

    # Run tests
    test_instructions_exists
    test_yaml_config_exists
    test_instructions_reuse
    test_yaml_config_reuse
    test_markdown_lint
    test_yaml_syntax
    test_extends_reference "$repo_type"
    test_critical_rules
    test_org_reminder "$repo_type"

    # Summary
    echo ""
    echo "========================================="
    echo "Summary"
    echo "========================================="
    echo "Total Tests: $TOTAL_TESTS"
    echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
    echo ""

    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}✗ Some tests failed${NC}"
        exit 1
    fi
}

main "$@"
