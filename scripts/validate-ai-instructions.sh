#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

    if [ "$(basename "$PWD")" = "GuardGuide" ] \
        || grep -qiE '"name"[[:space:]]*:[[:space:]]*"([^"]*/)?guardguide"' composer.json package.json 2>/dev/null; then
        echo "guardguide"
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

    if [ -d "workflow-templates" ]; then
        echo "org"
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

test_agents_exists() {
    if [ -f "AGENTS.md" ]; then
        print_result "AGENTS.md exists" "PASS"
    else
        print_result "AGENTS.md exists" "FAIL" "File not found"
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

test_agents_reuse() {
    local spdx_license_marker='SPDX-License''-Identifier:'
    local sidecar_license_pattern='SPDX-License''-Identifier:[[:space:]]+(CC0-1.0|AGPL-3.0-or-later)'

    if [ ! -f "AGENTS.md" ]; then
        print_result "AGENTS.md has REUSE license" "FAIL" "Missing AGENTS.md"
        return
    fi

    if [ -f "AGENTS.md.license" ]; then
        if grep -qE "$sidecar_license_pattern" "AGENTS.md.license"; then
            print_result "AGENTS.md has REUSE license" "PASS"
        else
            print_result "AGENTS.md has REUSE license" "FAIL" "Sidecar .license exists but does not declare an allowed license (CC0-1.0 or AGPL-3.0-or-later)"
        fi
        return
    fi

    if head -n 10 "AGENTS.md" | grep -q "$spdx_license_marker"; then
        print_result "AGENTS.md has REUSE license" "PASS"
    else
        print_result "AGENTS.md has REUSE license" "FAIL" "Missing inline SPDX header or .license sidecar"
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
    if markdownlint_runner .github/copilot-instructions.md >/dev/null 2>&1; then
        print_result "copilot-instructions.md passes markdown lint" "PASS"
    elif markdownlint_available; then
        print_result "copilot-instructions.md passes markdown lint" "FAIL" "Run: markdownlint --config .markdownlint.json .github/copilot-instructions.md --fix"
    else
        print_result "copilot-instructions.md passes markdown lint" "PASS" "Skipped (run npm ci in SecPal/.github to install markdownlint-cli)"
    fi
}

test_agents_markdown_lint() {
    if markdownlint_runner AGENTS.md >/dev/null 2>&1; then
        print_result "AGENTS.md passes markdown lint" "PASS"
    elif markdownlint_available; then
        print_result "AGENTS.md passes markdown lint" "FAIL" "Run: markdownlint --config .markdownlint.json AGENTS.md --fix"
    else
        print_result "AGENTS.md passes markdown lint" "PASS" "Skipped (run npm ci in SecPal/.github to install markdownlint-cli)"
    fi
}

markdownlint_runner() {
    local target="$1"

    if [ -x "$SCRIPT_DIR/../node_modules/.bin/markdownlint" ]; then
        "$SCRIPT_DIR/../node_modules/.bin/markdownlint" --config .markdownlint.json "$target"
        return
    fi

    if command -v markdownlint >/dev/null 2>&1; then
        markdownlint --config .markdownlint.json "$target"
        return
    fi

    if command -v npx >/dev/null 2>&1; then
        npx --yes --package markdownlint-cli@0.49.0 markdownlint --config .markdownlint.json "$target"
        return
    fi

    return 127
}

markdownlint_available() {
    [ -x "$SCRIPT_DIR/../node_modules/.bin/markdownlint" ] || command -v markdownlint >/dev/null 2>&1 || command -v npx >/dev/null 2>&1
}

mirror_matches_agents() {
    python3 - <<'PY'
import pathlib
import re
import sys


def strip_html_comment_header(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("<!--"):
        parts = stripped.split("-->\n", 1)
        if len(parts) == 2:
            return parts[1].lstrip()
    return text


def extract_agents_body(text: str) -> str:
    body = strip_html_comment_header(text)
    core_index = body.find("## Core Runtime Baseline")
    if core_index != -1:
        return body[core_index:].strip()
    heading = re.search(r"^##\s+", body, re.MULTILINE)
    if heading is None:
        raise SystemExit(1)
    return body[heading.start():].strip()


def extract_mirror_body(text: str) -> str:
    body = strip_html_comment_header(text)
    marker = body.find("## Authoritative Sources")
    if marker == -1:
        raise SystemExit(1)
    remaining = body[marker + len("## Authoritative Sources"):]
    heading = re.search(r"^##\s+", remaining, re.MULTILINE)
    if heading is None:
        raise SystemExit(1)
    start = marker + len("## Authoritative Sources") + heading.start()
    return body[start:].strip()


def normalize_mirrored_body(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


agents = pathlib.Path("AGENTS.md").read_text()
mirror = pathlib.Path(".github/copilot-instructions.md").read_text()
sys.exit(
    0
    if normalize_mirrored_body(extract_agents_body(agents))
    == normalize_mirrored_body(extract_mirror_body(mirror))
    else 1
)
PY
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

    if [ -f "AGENTS.md" ]; then
        search_targets+=("AGENTS.md")
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
    local runtime_file="AGENTS.md"

    if [ ! -f "$runtime_file" ]; then
        if [ "$repo_type" = "org" ]; then
            print_result "org instructions define runtime model" "FAIL" "Missing AGENTS.md"
        else
            print_result "repo instructions are self-contained" "FAIL" "Missing AGENTS.md"
        fi
        return
    fi

    if [ "$repo_type" = "org" ]; then
        local has_authoritative=1
        local has_runtime_application_model=1
        local has_self_contained_or_no_auto_inherit=1
        local runtime_model_pattern='runtime[^[:alpha:]]*(application|model)|(application|model)[^[:alpha:]]*runtime'

        if grep -qiE 'authoritative' "$runtime_file"; then
            has_authoritative=0
        fi

        if grep -qiE "$runtime_model_pattern" "$runtime_file"; then
            has_runtime_application_model=0
        fi

        if grep -qiE 'self-contained|(do not.*automatically.*(inherit|inheritance))' "$runtime_file"; then
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

    if grep -qiE 'self-contained|repo-local' "$runtime_file" && grep -qiE 'Required Checklist|Required Validation' "$runtime_file"; then
        print_result "repo instructions are self-contained" "PASS"
    else
        print_result "repo instructions are self-contained" "FAIL" "Missing self-contained guidance or Required Checklist/Validation"
    fi
}

test_critical_rules() {
    if grep -qiE "critical[[:space:]_-]+rules|core[[:space:]_-]+principles|always[-[:space:]_]*on[[:space:]_-]+rules" AGENTS.md; then
        print_result "instructions contain critical rules" "PASS"
    else
        print_result "instructions contain critical rules" "FAIL" "No critical rules/principles found"
    fi
}

test_agents_size_limit() {
    local instructions_file="AGENTS.md"
    local max_bytes=32768
    local byte_count

    if [ ! -f "$instructions_file" ]; then
        print_result "AGENTS.md stays under runtime discovery size limit" "FAIL" "Missing $instructions_file"
        return
    fi

    byte_count="$(wc -c <"$instructions_file")"
    if [ "$byte_count" -le "$max_bytes" ]; then
        print_result "AGENTS.md stays under runtime discovery size limit" "PASS"
    else
        print_result "AGENTS.md stays under runtime discovery size limit" "FAIL" "$byte_count bytes exceeds $max_bytes bytes"
    fi
}

test_ai_findings_guidance() {
    local instructions_file="AGENTS.md"
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

test_review_guidelines() {
    local instructions_file="AGENTS.md"
    local has_section=1
    local has_provider_neutral=1
    local has_no_attribution=1

    if [ ! -f "$instructions_file" ]; then
        print_result "instructions contain provider-neutral review guidelines" "FAIL" "Missing $instructions_file"
        return
    fi

    if grep -qiE '^## Review guidelines$' "$instructions_file"; then
        has_section=0
    fi

    if grep -qiE 'provider-neutral|any AI reviewer|AI reviewer' "$instructions_file"; then
        has_provider_neutral=0
    fi

    if grep -qiE 'self-referential AI wording|generated-by text|AI attribution|tool promotion' "$instructions_file"; then
        has_no_attribution=0
    fi

    if [ "$has_section" -eq 0 ] && [ "$has_provider_neutral" -eq 0 ] && [ "$has_no_attribution" -eq 0 ]; then
        print_result "instructions contain provider-neutral review guidelines" "PASS"
    else
        print_result "instructions contain provider-neutral review guidelines" "FAIL" "Missing Review guidelines, provider-neutral review language, or no-attribution guidance"
    fi
}

test_repo_specific_ai_risk_guidance() {
    local repo_type="$1"
    local instructions_file="AGENTS.md"
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
        guardguide)
            first_pattern='shadcn/ui|Lingui|localization|application-layer encryption|QR|magic-link|supervised fallback'
            second_pattern='MariaDB|PostgreSQL|tenant-scoped|mutable display name|IP addresses|user-agent strings'
            message='Missing GuardGuide AI guardrails for localization, sensitive-data handling, or dual-database acknowledgement flows'
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

test_copilot_compat_contract() {
    if [ ! -f ".github/copilot-instructions.md" ]; then
        print_result "copilot instructions mirror AGENTS.md" "FAIL" "Missing .github/copilot-instructions.md"
        return
    fi

    # shellcheck disable=SC2016
    if grep -q 'mirrors the authoritative root `AGENTS.md`' .github/copilot-instructions.md \
        && grep -q 'Edit `AGENTS.md` first' .github/copilot-instructions.md \
        && grep -q '## Authoritative Sources' .github/copilot-instructions.md \
        && mirror_matches_agents; then
        print_result "copilot instructions mirror AGENTS.md" "PASS"
    else
        print_result "copilot instructions mirror AGENTS.md" "FAIL" "Missing AGENTS compatibility notice, authoritative-source section, or mirrored AGENTS body"
    fi
}

main() {
    local repo_type

    echo "========================================="
    echo "SecPal AI Instructions Validation"
    echo "========================================="
    echo ""

    repo_type="$(detect_repo_type)"
    echo "Repository Type: $repo_type"
    echo ""

    test_instructions_exists
    test_agents_exists
    test_yaml_config_exists
    test_instructions_reuse
    test_agents_reuse
    test_yaml_config_reuse
    test_markdown_lint
    test_agents_markdown_lint
    test_yaml_syntax
    test_no_pseudo_inheritance
    test_runtime_model "$repo_type"
    test_critical_rules
    test_agents_size_limit
    test_ai_findings_guidance
    test_review_guidelines
    test_repo_specific_ai_risk_guidance "$repo_type"
    test_instruction_frontmatter
    test_copilot_compat_contract

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

if [ "$#" -gt 0 ]; then
    overall_status=0
    for repo_path in "$@"; do
        if [ ! -d "$repo_path" ]; then
            echo "Repository path not found: $repo_path" >&2
            overall_status=1
            continue
        fi

        (
            cd "$repo_path"
            "$SCRIPT_DIR/validate-ai-instructions.sh"
        ) || overall_status=1
    done
    exit "$overall_status"
fi

main
