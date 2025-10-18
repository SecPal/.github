#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# check-bash-best-practices.sh: Enforce bash scripting best practices
# Primary focus: Lesson #24 - Missing 'set -euo pipefail'
#
# Scope: GitHub Actions workflows (run: blocks), shell scripts, git hooks
#
# Usage: check-bash-best-practices.sh <file1.yml|file1.sh> [file2 ...]
# Exit 0: No violations found
# Exit 1: Violations detected

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# Check for missing 'set -euo pipefail' (Lesson #24)
check_set_flags() {
    local file="$1"
    local ext="${file##*.}"
    local violations=0

    case "$ext" in
        yml|yaml)
            # For workflows: Each 'run:' block should start with 'set -euo pipefail'
            local run_blocks
            mapfile -t run_blocks < <(grep -n "run: |" "$file" 2>/dev/null || true)

            if [ ${#run_blocks[@]} -gt 0 ] && [ -n "${run_blocks[0]}" ]; then
                for block_line in "${run_blocks[@]}"; do
                    local line_num="${block_line%%:*}"

                    # Find first non-empty, non-comment line after 'run: |'
                    local first_script_line
                    first_script_line=$(awk -v line="$line_num" 'NR>line {
                        # Skip empty lines
                        if ($0 ~ /^[[:space:]]*$/) next;
                        # Skip comment lines
                        if ($0 ~ /^[[:space:]]*#/) next;
                        # Found first real command
                        print;
                        exit
                    }' "$file")

                    # Check if first script line contains 'set -euo pipefail'
                    if [ -n "$first_script_line" ] && ! echo "$first_script_line" | grep -q "set -euo pipefail"; then
                        echo -e "${RED}❌${NC} Missing 'set -euo pipefail' in run block at line $line_num"
                        echo "   Fix: Add 'set -euo pipefail' as first line of run block"
                        ((violations++))
                    fi
                done
            fi
            ;;
        sh|*)
            # For shell scripts: Should appear in first 10 lines
            if ! head -10 "$file" | grep -q "set -euo pipefail"; then
                echo -e "${RED}❌${NC} Missing 'set -euo pipefail' in script header"
                echo "   Fix: Add 'set -euo pipefail' after shebang"
                ((violations++))
            fi
            ;;
    esac

    return "$violations"
}

# Main check function
check_file() {
    local file="$1"
    local file_failed=0

    echo "📄 Checking: $file"

    # Run check
    if ! check_set_flags "$file"; then
        ((file_failed += $?))
    fi

    if [ "$file_failed" -eq 0 ]; then
        echo -e "${GREEN}✅${NC} No bash best practice violations detected"
    else
        ((FAILED += file_failed))
    fi

    echo ""
    return "$file_failed"
}

# Main execution
if [ $# -eq 0 ]; then
    echo "Usage: $0 <file1> [file2 ...]"
    echo ""
    echo "Checks bash best practices in:"
    echo "  - GitHub Actions workflows (.yml/.yaml)"
    echo "  - Shell scripts (.sh)"
    echo "  - Git hooks"
    exit 1
fi

for file in "$@"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌${NC} File not found: $file"
        ((FAILED++))
        continue
    fi

    check_file "$file"
done

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}❌ Found $FAILED violation(s)${NC}"
    echo ""
    echo "See Lesson #24 for bash scripting best practices:"
    echo "  https://github.com/SecPal/.github/blob/main/docs/lessons/lesson-24.md"
    exit 1
else
    echo -e "${GREEN}✅ All checks passed!${NC}"
    exit 0
fi
