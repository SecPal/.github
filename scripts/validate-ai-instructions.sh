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
        printf '%s\n' "$REPO_TYPE"
        return
    fi

    if [ "$(basename "$PWD")" = "GuardGuide" ]; then
        printf '%s\n' guardguide
    elif [ -f artisan ] || [ -f composer.json ]; then
        printf '%s\n' api
    elif [ -f next.config.mjs ]; then
        printf '%s\n' changelog
    elif [ -f capacitor.config.ts ] || [ -d android/app/src ]; then
        printf '%s\n' android
    elif [ -f astro.config.mjs ]; then
        printf '%s\n' website
    elif [ -f package.json ] && grep -q vite package.json 2>/dev/null; then
        printf '%s\n' frontend
    elif [ -f docs/openapi.yaml ]; then
        printf '%s\n' contracts
    else
        printf '%s\n' org
    fi
}

test_instruction_path_boundaries() {
    local path
    local symlink

    for path in AGENTS.md .github .github/copilot-instructions.md .github/instructions; do
        if [ -L "$path" ]; then
            print_result "instruction paths stay inside the repository" "FAIL" \
                "Instruction discovery paths must not be symlinks: $path"
            return 1
        fi
    done

    if { [ -e AGENTS.md ] && [ ! -f AGENTS.md ]; } \
        || { [ -e .github ] && [ ! -d .github ]; } \
        || { [ -e .github/copilot-instructions.md ] \
            && [ ! -f .github/copilot-instructions.md ]; } \
        || { [ -e .github/instructions ] && [ ! -d .github/instructions ]; }; then
        print_result "instruction paths stay inside the repository" "FAIL" \
            "Instruction files must be regular files and instruction containers must be regular directories"
        return 1
    fi

    while IFS= read -r -d '' symlink; do
        print_result "instruction paths stay inside the repository" "FAIL" \
            "Focused instruction directories must not contain symlinks: $symlink"
        return 1
    done < <(find .github/instructions -type l -print0 2>/dev/null)

    print_result "instruction paths stay inside the repository" "PASS"
}

test_required_files() {
    local missing=()
    local required_file

    for required_file in AGENTS.md .github/copilot-instructions.md; do
        if [ ! -f "$required_file" ]; then
            missing+=("$required_file")
        fi
    done

    if [ "${#missing[@]}" -eq 0 ]; then
        print_result "required instruction files exist" "PASS"
    else
        print_result "required instruction files exist" "FAIL" \
            "Missing: ${missing[*]}"
    fi
}

test_readable_utf8_markdown() {
    local file="$1"
    local label="$2"

    if [ ! -r "$file" ] || [ ! -s "$file" ]; then
        print_result "$label is readable UTF-8 Markdown" "FAIL" \
            "Missing, unreadable, or empty: $file"
        return
    fi

    if python3 - "$file" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    text = path.read_bytes().decode("utf-8")
except UnicodeDecodeError:
    raise SystemExit(1)

if not text.strip() or re.search(r"^#\s+\S", text, re.MULTILINE) is None:
    raise SystemExit(1)
PY
    then
        print_result "$label is readable UTF-8 Markdown" "PASS"
    else
        print_result "$label is readable UTF-8 Markdown" "FAIL" \
            "File must be non-empty UTF-8 Markdown with a top-level heading"
    fi
}

test_reuse_license() {
    local file="$1"
    local label="$2"
    local license_pattern='SPDX-License''-Identifier:[[:space:]]+(CC0-1.0|AGPL-3.0-or-later)'

    if [ ! -f "$file" ]; then
        print_result "$label has REUSE license" "FAIL" "Missing $file"
        return
    fi

    if [ -f "$file.license" ]; then
        if grep -qE "$license_pattern" "$file.license"; then
            print_result "$label has REUSE license" "PASS"
        else
            print_result "$label has REUSE license" "FAIL" \
                "Sidecar .license exists but does not declare an allowed license"
        fi
        return
    fi

    if head -n 10 "$file" | grep -qE "$license_pattern"; then
        print_result "$label has REUSE license" "PASS"
    else
        print_result "$label has REUSE license" "FAIL" \
            "Missing inline SPDX header or .license sidecar"
    fi
}

markdownlint_available() {
    [ -x "$SCRIPT_DIR/../node_modules/.bin/markdownlint" ] \
        || command -v markdownlint >/dev/null 2>&1
}

markdownlint_runner() {
    if [ -x "$SCRIPT_DIR/../node_modules/.bin/markdownlint" ]; then
        "$SCRIPT_DIR/../node_modules/.bin/markdownlint" \
            --config .markdownlint.json "$@"
        return
    fi

    markdownlint --config .markdownlint.json "$@"
}

test_markdown_lint() {
    local targets=()
    local file
    local lint_output

    for file in AGENTS.md .github/copilot-instructions.md; do
        if [ -f "$file" ]; then
            targets+=("$file")
        fi
    done
    while IFS= read -r -d '' file; do
        targets+=("$file")
    done < <(find .github/instructions -type f -name '*.instructions.md' -print0 2>/dev/null)

    if [ "${#targets[@]}" -eq 0 ]; then
        print_result "instruction Markdown passes lint" "FAIL" \
            "No instruction Markdown files found"
    elif ! markdownlint_available; then
        print_result "instruction Markdown passes lint" "FAIL" \
            "Markdownlint is unavailable; provide it with the committed lockfile dependencies or a compatible global markdownlint"
    elif lint_output="$(markdownlint_runner "${targets[@]}" 2>&1)"; then
        print_result "instruction Markdown passes lint" "PASS"
    else
        print_result "instruction Markdown passes lint" "FAIL" \
            "${lint_output:-Run the repository-pinned markdownlint on the instruction files}"
    fi
}

test_instruction_frontmatter() {
    local file
    local -a files=()
    local yaml_package="$SCRIPT_DIR/../node_modules/js-yaml"
    local yaml_module

    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(find .github/instructions -type f -name '*.instructions.md' -print0 2>/dev/null)

    if [ "${#files[@]}" -eq 0 ]; then
        print_result "instruction overlays include valid frontmatter" "PASS" \
            "Skipped (no focused instruction files present)"
        return
    fi

    if ! command -v node >/dev/null 2>&1 \
        || ! yaml_module="$(node - "$yaml_package" <<'JS'
try {
    process.stdout.write(require.resolve(process.argv[2]));
} catch (_error) {
    process.exit(1);
}
JS
        )"; then
        print_result "instruction overlays include valid frontmatter" "FAIL" \
            "repository-pinned js-yaml is unavailable; install the committed lockfile dependencies"
        return
    fi

    for file in "${files[@]}"; do
        if ! node - "$file" "$yaml_module" <<'JS'
const fs = require("fs");

const file = process.argv[2];
const yamlModule = process.argv[3];

try {
    const yaml = require(yamlModule);
    const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
    if (lines.length === 0 || lines[0].trim() !== "---") {
        process.exit(1);
    }

    const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
    if (end === -1) {
        process.exit(1);
    }

    const frontmatter = yaml.load(lines.slice(1, end).join("\n"));
    if (frontmatter === null || typeof frontmatter !== "object" || Array.isArray(frontmatter)) {
        process.exit(1);
    }

    for (const key of ["name", "applyTo"]) {
        if (typeof frontmatter[key] !== "string" || frontmatter[key].trim() === "") {
            process.exit(1);
        }
    }
} catch (_error) {
    process.exit(1);
}
JS
        then
            print_result "instruction overlays include valid frontmatter" "FAIL" \
                "Invalid YAML, delimiters, or non-empty string name/applyTo in $file"
            return
        fi
    done

    print_result "instruction overlays include valid frontmatter" "PASS"
}

test_instruction_size_limit() {
    local file="$1"
    local label="$2"
    local limit_name="$3"
    local max_bytes=32768
    local byte_count

    if [ ! -f "$file" ]; then
        print_result "$label stays under $limit_name size limit" "FAIL" \
            "Missing $file"
        return
    fi

    byte_count="$(wc -c <"$file")"
    if [ "$byte_count" -le "$max_bytes" ]; then
        print_result "$label stays under $limit_name size limit" "PASS"
    else
        print_result "$label stays under $limit_name size limit" "FAIL" \
            "$file: $byte_count bytes exceeds $max_bytes bytes"
    fi
}

main() {
    local repo_type

    printf '%s\n' '========================================='
    printf '%s\n' 'SecPal AI Instructions Validation'
    printf '%s\n\n' '========================================='

    repo_type="$(detect_repo_type)"
    printf 'Repository Type: %s\n\n' "$repo_type"

    test_instruction_path_boundaries || return 1
    test_required_files
    test_readable_utf8_markdown AGENTS.md AGENTS.md
    test_readable_utf8_markdown \
        .github/copilot-instructions.md copilot-instructions.md
    test_reuse_license AGENTS.md AGENTS.md
    test_reuse_license \
        .github/copilot-instructions.md copilot-instructions.md
    test_instruction_frontmatter
    test_markdown_lint
    test_instruction_size_limit AGENTS.md AGENTS.md "runtime discovery"
    test_instruction_size_limit \
        .github/copilot-instructions.md copilot-instructions.md "instruction discovery"

    printf '\n%s\n' '========================================='
    printf '%s\n' 'Summary'
    printf '%s\n' '========================================='
    printf 'Total Tests: %s\n' "$TOTAL_TESTS"
    printf 'Passed: %b%s%b\n' "$GREEN" "$PASSED_TESTS" "$NC"
    printf 'Failed: %b%s%b\n\n' "$RED" "$FAILED_TESTS" "$NC"

    if [ "$FAILED_TESTS" -eq 0 ]; then
        printf '%b✓ All tests passed!%b\n' "$GREEN" "$NC"
        return 0
    fi

    printf '%b✗ Some tests failed%b\n' "$RED" "$NC"
    return 1
}

if [ "$#" -gt 0 ]; then
    overall_status=0
    for repo_path in "$@"; do
        if [ ! -d "$repo_path" ]; then
            printf 'Repository path not found: %s\n' "$repo_path" >&2
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
