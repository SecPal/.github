#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

print_result() {
    local test_name="$1"
    local status="$2"
    local message="${3:-}"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$status" = "PASS" ]; then
        printf '%b✓%b %s\n' "$GREEN" "$NC" "$test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return
    fi

    printf '%b✗%b %s\n' "$RED" "$NC" "$test_name"
    if [ -n "$message" ]; then
        printf '  %b→%b %s\n' "$YELLOW" "$NC" "$message"
    fi
    FAILED_TESTS=$((FAILED_TESTS + 1))
}

detect_repo_type() {
    if [ -f "artisan" ] || [ -f "composer.json" ]; then
        echo "api"
        return
    fi

    if [ -f "package.json" ] && grep -q "vite" package.json 2>/dev/null; then
        echo "frontend"
        return
    fi

    if [ -f "docs/openapi.yaml" ] || { [ -f "package.json" ] && grep -q "openapi" package.json 2>/dev/null; }; then
        echo "contracts"
        return
    fi

    echo "org"
}

test_instructions_exists() {
    if [ -f ".github/copilot-instructions.md" ]; then
        print_result "copilot-instructions.md exists" "PASS"
    else
        print_result "copilot-instructions.md exists" "FAIL" "File not found"
    fi
}

test_yaml_config_exists() {
    local repo_type="$1"

    if [ -f ".github/copilot-config.yaml" ]; then
        print_result "copilot-config.yaml exists" "PASS"
    elif [ "$repo_type" = "org" ]; then
        print_result "copilot-config.yaml exists" "FAIL" "File not found"
    else
        print_result "copilot-config.yaml exists" "PASS" "Skipped (repo-local config not required)"
    fi
}

test_instructions_reuse() {
    if [ -f ".github/copilot-instructions.md.license" ] && grep -q "CC0-1.0" ".github/copilot-instructions.md.license"; then
        print_result "copilot-instructions.md has REUSE license" "PASS"
    else
        print_result "copilot-instructions.md has REUSE license" "FAIL" "Missing or wrong license file"
    fi
}

test_yaml_config_reuse() {
    local repo_type="$1"

    if [ ! -f ".github/copilot-config.yaml" ]; then
        if [ "$repo_type" = "org" ]; then
            print_result "copilot-config.yaml has REUSE license" "FAIL" "Config file missing"
        else
            print_result "copilot-config.yaml has REUSE license" "PASS" "Skipped (repo-local config not present)"
        fi
        return
    fi

    if [ -f ".github/copilot-config.yaml.license" ] && grep -q "CC0-1.0" ".github/copilot-config.yaml.license"; then
        print_result "copilot-config.yaml has REUSE license" "PASS"
    else
        print_result "copilot-config.yaml has REUSE license" "FAIL" "Missing or wrong license file"
    fi
}

test_markdown_lint() {
    if command -v npx >/dev/null 2>&1 && npx markdownlint-cli2 .github/copilot-instructions.md >/dev/null 2>&1; then
        print_result "copilot-instructions.md passes markdown lint" "PASS"
    elif command -v npx >/dev/null 2>&1; then
        print_result "copilot-instructions.md passes markdown lint" "FAIL" "Run: npx markdownlint-cli2 .github/copilot-instructions.md --fix"
    else
        print_result "copilot-instructions.md passes markdown lint" "PASS" "Skipped (markdownlint-cli2 not available)"
    fi
}

test_yaml_syntax() {
    if [ ! -f ".github/copilot-config.yaml" ]; then
        print_result "copilot-config.yaml has valid syntax" "PASS" "Skipped (YAML config not present)"
        return
    fi

    if command -v yq >/dev/null 2>&1 && yq eval '.version' .github/copilot-config.yaml >/dev/null 2>&1; then
        print_result "copilot-config.yaml has valid syntax" "PASS"
    elif command -v yq >/dev/null 2>&1; then
        print_result "copilot-config.yaml has valid syntax" "FAIL" "YAML parsing error"
    else
        print_result "copilot-config.yaml has valid syntax" "PASS" "Skipped (yq not available)"
    fi
}

test_no_pseudo_inheritance() {
    if grep -RInE '@EXTENDS|INHERITANCE' .github/copilot-instructions.md .github/instructions >/dev/null 2>&1; then
        print_result "instructions avoid pseudo-inheritance markers" "FAIL" "Found @EXTENDS or INHERITANCE markers in active instructions"
    else
        print_result "instructions avoid pseudo-inheritance markers" "PASS"
    fi
}

test_runtime_model() {
    local repo_type="$1"

    if [ "$repo_type" = "org" ]; then
        if grep -qiE 'authoritative|runtime application model' .github/copilot-instructions.md && grep -qiE 'self-contained|do not automatically inherit' .github/copilot-instructions.md; then
            print_result "org instructions define runtime model" "PASS"
        else
            print_result "org instructions define runtime model" "FAIL" "Missing runtime application model guidance"
        fi
        return
    fi

    if grep -qiE 'self-contained|repo-local' .github/copilot-instructions.md && grep -qiE 'Required Checklist|Required Validation' .github/copilot-instructions.md; then
        print_result "repo instructions are self-contained" "PASS"
    else
        print_result "repo instructions are self-contained" "FAIL" "Missing self-contained guidance or Required Checklist/Validation"
    fi
}

test_critical_rules() {
    if grep -qiE "critical[[:space:]]+rules|core[[:space:]]+principles|always-on[[:space:]]+rules" .github/copilot-instructions.md; then
        print_result "instructions contain critical rules" "PASS"
    else
        print_result "instructions contain critical rules" "FAIL" "No critical rules/principles found"
    fi
}

test_instruction_frontmatter() {
    local file
    local found=0
    local message

    while IFS= read -r -d '' file; do
        found=1
        if ! head -n 10 "$file" | grep -q '^applyTo:' || ! head -n 10 "$file" | grep -q '^name:'; then
            printf -v message 'Missing name/applyTo in %s' "$file"
            print_result "instruction files include required frontmatter" "FAIL" "$message"
            return
        fi
    done < <(find .github/instructions -type f -name '*.instructions.md' -print0 2>/dev/null)

    if [ "$found" -eq 0 ]; then
        print_result "instruction files include required frontmatter" "PASS" "Skipped (no file-based instructions present)"
        return
    fi

    print_result "instruction files include required frontmatter" "PASS"
}

main() {
    local repo_type

    echo "========================================="
    echo "Copilot Instructions Validation"
    echo "========================================="
    echo ""

    repo_type="$(detect_repo_type)"
    echo "Repository Type: $repo_type"
    echo ""

    test_instructions_exists
    test_yaml_config_exists "$repo_type"
    test_instructions_reuse
    test_yaml_config_reuse "$repo_type"
    test_markdown_lint
    test_yaml_syntax
    test_no_pseudo_inheritance
    test_runtime_model "$repo_type"
    test_critical_rules
    test_instruction_frontmatter

    echo ""
    echo "========================================="
    echo "Summary"
    echo "========================================="
    echo "Total Tests: $TOTAL_TESTS"
    echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
    echo ""

    if [ "$FAILED_TESTS" -eq 0 ]; then
            printf '%b✓ All tests passed!%b\n' "$GREEN" "$NC"
        exit 0
    fi

        printf '%b✗ Some tests failed%b\n' "$RED" "$NC"
    exit 1
}

main "$@"
