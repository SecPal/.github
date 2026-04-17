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
        if [ -n "$message" ]; then
            printf '  %b→%b %s\n' "$YELLOW" "$NC" "$message"
        fi
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
    if [ -n "${REPO_TYPE:-}" ]; then
        echo "$REPO_TYPE"
        return
    fi

    if [ -f "artisan" ] || [ -f "composer.json" ]; then
        echo "api"
        return
    fi

    if [ -f "next.config.mjs" ]; then
        echo "changelog"
        return
    fi

    if [ -f "capacitor.config.ts" ] || [ -d "android/app/src" ]; then
        echo "android"
        return
    fi

    if [ -f "astro.config.mjs" ]; then
        echo "website"
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
    if [ -f ".github/copilot-config.yaml" ]; then
        print_result "copilot-config.yaml optional (legacy)" "PASS"
    else
        print_result "copilot-config.yaml optional (legacy)" "PASS" "Legacy file not present"
    fi
}

test_instructions_reuse() {
    local spdx_license_marker='SPDX-License''-Identifier:'
    local sidecar_license_pattern='SPDX-License''-Identifier:[[:space:]]+(CC0-1.0|AGPL-3.0-or-later)'

    if [ ! -f ".github/copilot-instructions.md" ]; then
        print_result "copilot-instructions.md has REUSE license" "FAIL" "Missing .github/copilot-instructions.md"
        return
    fi

    if [ -f ".github/copilot-instructions.md.license" ]; then
        if grep -qE "$sidecar_license_pattern" ".github/copilot-instructions.md.license"; then
            print_result "copilot-instructions.md has REUSE license" "PASS"
        else
            print_result "copilot-instructions.md has REUSE license" "FAIL" "Sidecar .license exists but does not declare an allowed license (CC0-1.0 or AGPL-3.0-or-later)"
        fi
        return
    fi

    if head -n 10 ".github/copilot-instructions.md" | grep -q "$spdx_license_marker"; then
        print_result "copilot-instructions.md has REUSE license" "PASS"
    else
        print_result "copilot-instructions.md has REUSE license" "FAIL" "Missing inline SPDX header or .license sidecar"
    fi
}

test_yaml_config_reuse() {
    if [ ! -f ".github/copilot-config.yaml" ]; then
        print_result "copilot-config.yaml has REUSE license" "PASS" "Skipped (legacy config not present)"
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

    if command -v ruby >/dev/null 2>&1 && ruby -e 'require "psych"; Psych.parse_file(ARGV[0])' .github/copilot-config.yaml >/dev/null 2>&1; then
        print_result "copilot-config.yaml has valid syntax" "PASS"
    elif command -v ruby >/dev/null 2>&1; then
        print_result "copilot-config.yaml has valid syntax" "FAIL" "YAML parsing error"
    else
        print_result "copilot-config.yaml has valid syntax" "PASS" "Skipped (Ruby not available)"
    fi
}

test_no_pseudo_inheritance() {
    local search_targets=()
    # Pseudo-inheritance markers include explicit directives and common textual variants.
    # Keep this list centralized so it is easy to review and extend as conventions evolve.
    local pseudo_inheritance_pattern='@?extends|inherit[[:space:]]+from|inherits[[:space:]]+from|auto[-[:space:]]*inherit|base[_ -]?instructions?[^[:alpha:]]*(apply|load|import)|parent[_ -]?instructions?[^[:alpha:]]*(apply|load|import)'

    if [ -f ".github/copilot-instructions.md" ]; then
        search_targets+=(".github/copilot-instructions.md")
    fi

    if [ -d ".github/instructions" ]; then
        search_targets+=(".github/instructions")
    fi

    if [ "${#search_targets[@]}" -eq 0 ]; then
        print_result "instructions avoid pseudo-inheritance markers" "PASS" "Skipped (no instruction files/directories present)"
        return
    fi

    while IFS= read -r match; do
        if printf '%s\n' "$match" | grep -qiE 'do not[^[:alpha:]]+.*(inherit|auto[-[:space:]]*inherit)|does not[^[:alpha:]]+.*(inherit|auto[-[:space:]]*inherit)|not[^[:alpha:]]+automatically[^[:alpha:]]+.*inherit'; then
            continue
        fi

        print_result "instructions avoid pseudo-inheritance markers" "FAIL" "Found pseudo-inheritance markers in active instructions"
        return
    done < <(grep -RInEi "$pseudo_inheritance_pattern" "${search_targets[@]}" 2>/dev/null || true)

    print_result "instructions avoid pseudo-inheritance markers" "PASS"
}

test_runtime_model() {
    local repo_type="$1"

    if [ ! -f ".github/copilot-instructions.md" ]; then
        if [ "$repo_type" = "org" ]; then
            print_result "org instructions define runtime model" "FAIL" "Missing .github/copilot-instructions.md"
        else
            print_result "repo instructions are self-contained" "FAIL" "Missing .github/copilot-instructions.md"
        fi
        return
    fi

    if [ "$repo_type" = "org" ]; then
        local has_authoritative=1
        local has_runtime_application_model=1
        local has_self_contained_or_no_auto_inherit=1
        local runtime_model_pattern='runtime[^[:alpha:]]*(application|model)|(application|model)[^[:alpha:]]*runtime'

        if grep -qiE 'authoritative' .github/copilot-instructions.md; then
            has_authoritative=0
        fi

        if grep -qiE "$runtime_model_pattern" .github/copilot-instructions.md; then
            has_runtime_application_model=0
        fi

        if grep -qiE 'self-contained|(do not.*automatically.*(inherit|inheritance))' .github/copilot-instructions.md; then
            has_self_contained_or_no_auto_inherit=0
        fi

        if { [ "$has_authoritative" -eq 0 ] || [ "$has_runtime_application_model" -eq 0 ]; } \
            && [ "$has_self_contained_or_no_auto_inherit" -eq 0 ]; then
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
    if grep -qiE "critical[[:space:]_-]+rules|core[[:space:]_-]+principles|always[-[:space:]_]*on[[:space:]_-]+rules" .github/copilot-instructions.md; then
        print_result "instructions contain critical rules" "PASS"
    else
        print_result "instructions contain critical rules" "FAIL" "No critical rules/principles found"
    fi
}

test_ai_findings_guidance() {
    local instructions_file=".github/copilot-instructions.md"
    local has_ai_findings=1
    local has_proof_requirement=1
    local has_ci_guardrail=1

    if [ ! -f "$instructions_file" ]; then
        print_result "instructions contain AI findings triage guidance" "FAIL" "Missing $instructions_file"
        return
    fi

    if grep -qiE 'AI findings?|AI-generated' "$instructions_file"; then
        has_ai_findings=0
    fi

    if grep -qiE 'failing test|reproducible defect|stated invariant|prove the defect|proof of the defect|violates it' "$instructions_file"; then
        has_proof_requirement=0
    fi

    if grep -qiE 'green CI alone|CI alone|green checks alone' "$instructions_file"; then
        has_ci_guardrail=0
    fi

    if [ "$has_ai_findings" -eq 0 ] && [ "$has_proof_requirement" -eq 0 ] && [ "$has_ci_guardrail" -eq 0 ]; then
        print_result "instructions contain AI findings triage guidance" "PASS"
    else
        print_result "instructions contain AI findings triage guidance" "FAIL" "Missing AI-finding proof or CI guardrail language"
    fi
}

test_repo_specific_ai_risk_guidance() {
    local repo_type="$1"
    local instructions_file=".github/copilot-instructions.md"
    local first_pattern=''
    local second_pattern=''
    local message=''

    if [ ! -f "$instructions_file" ]; then
        print_result "instructions contain repo-specific AI risk guidance" "FAIL" "Missing $instructions_file"
        return
    fi

    case "$repo_type" in
        api)
            first_pattern='resource|serializer|presentation code|runs once per request'
            second_pattern='mutable display name|stable key|stable identifier|tenant-scoped|tenant scoping|composite unique|unique constraint'
            message='Missing API AI guardrails for resource purity or stable tenant-scoped identifiers'
            ;;
        frontend)
            first_pattern='locale|language|tenant|user-derived|auth transition|session change'
            second_pattern='memoization|dependency|stale|cache'
            message='Missing frontend AI guardrails for stale locale or session-derived state'
            ;;
        contracts)
            first_pattern='allowlist|regex|discovery pattern'
            second_pattern='required field|enum|security scheme|positive and negative example|validation evidence'
            message='Missing contracts AI guardrails for allowlist drift or unproven contract widening'
            ;;
        android)
            first_pattern='listener-handle|listener handle|teardown|bridge'
            second_pattern='WebView history|back behavior|back-navigation|managed-mode|owner-state'
            message='Missing android AI guardrails for bridge teardown or managed/back-navigation behavior'
            ;;
        website)
            first_pattern='static|client-only|route|build'
            second_pattern='accessib|semantic'
            message='Missing website AI guardrails for static rendering or accessibility regressions'
            ;;
        changelog)
            first_pattern='MDX|markup|label|feed'
            second_pattern='static build|build output|exported page|metadata'
            message='Missing changelog AI guardrails for MDX or static export regressions'
            ;;
        org)
            first_pattern='validator|reusable workflow|repo-specific guardrail'
            second_pattern='positive and negative fixture|positive and negative evidence|regression test'
            message='Missing org AI guardrails for validator or reusable workflow regressions'
            ;;
        *)
            print_result "instructions contain repo-specific AI risk guidance" "PASS" "Skipped (no repo-specific pattern defined for $repo_type)"
            return
            ;;
    esac

    if grep -qiE "$first_pattern" "$instructions_file" && grep -qiE "$second_pattern" "$instructions_file"; then
        print_result "instructions contain repo-specific AI risk guidance" "PASS"
    else
        print_result "instructions contain repo-specific AI risk guidance" "FAIL" "$message"
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
    test_yaml_config_exists
    test_instructions_reuse
    test_yaml_config_reuse
    test_markdown_lint
    test_yaml_syntax
    test_no_pseudo_inheritance
    test_runtime_model "$repo_type"
    test_critical_rules
    test_ai_findings_guidance
    test_repo_specific_ai_risk_guidance "$repo_type"
    test_instruction_frontmatter

    echo ""
    echo "========================================="
    echo "Summary"
    echo "========================================="
    echo "Total Tests: $TOTAL_TESTS"
    printf 'Passed: %b%s%b\n' "$GREEN" "$PASSED_TESTS" "$NC"
    printf 'Failed: %b%s%b\n' "$RED" "$FAILED_TESTS" "$NC"
    echo ""

    if [ "$FAILED_TESTS" -eq 0 ]; then
        printf '%b✓ All tests passed!%b\n' "$GREEN" "$NC"
        exit 0
    fi

    printf '%b✗ Some tests failed%b\n' "$RED" "$NC"
    exit 1
}

main "$@"
