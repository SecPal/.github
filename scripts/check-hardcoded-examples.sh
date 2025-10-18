#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# check-hardcoded-examples.sh: Detect hardcoded values in documentation
# Usage: check-hardcoded-examples.sh <file1.md> [file2.md ...]
# Exit 0: No hardcoded values found
# Exit 1: Hardcoded values detected

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# Patterns to detect (add more as needed)
declare -A PATTERNS=(
    ["PR_NUMBER=[0-9]+"]="Hardcoded PR number (use: PR_NUMBER=\$PR_NUMBER or PR_NUMBER=42 # example)"
    ["number: [0-9]{2,}"]="Hardcoded PR/issue number in GraphQL (use: \\\$number variable)"
    ["owner: \"SecPal\""]="Hardcoded owner in GraphQL (use: \\\$owner variable)"
    ["name: \"\\.github\""]="Hardcoded repo name in GraphQL (use: \\\$name variable)"
    ["repository\(owner: \"[^$]"]="Hardcoded repository owner (use: variables)"
    ["pullRequest\(number: [0-9]"]="Hardcoded PR number in query (use: \\\$number variable)"
    ["PRRT\\*\\\\\\*|PRRC\\*\\\\\\*"]="Incorrect markdown escaping (use backticks: \`PRRT_*\` or \`PRRC_*\`)"
)

# Exceptions (lines to ignore - e.g., examples that ARE supposed to be specific)
declare -A EXCEPTIONS=(
    ["Example: "]="Example lines"
    ["# Example"]="Comment examples"
    ["e.g.,"]="Inline examples"
    ["<!-- Example"]="HTML comment examples"
)

check_file() {
    local file="$1"
    local file_failed=0

    echo "📄 Checking: $file"

    for pattern in "${!PATTERNS[@]}"; do
        local desc="${PATTERNS[$pattern]}"

        # Find matching lines
        local matches
        mapfile -t matches < <(grep -nE "$pattern" "$file" 2>/dev/null || true)

        if [ ${#matches[@]} -gt 0 ] && [ -n "${matches[0]}" ]; then
            # Filter out exceptions
            local actual_violations=()
            for match in "${matches[@]}"; do
                local is_exception=false
                for exception in "${!EXCEPTIONS[@]}"; do
                    if echo "$match" | grep -qF "$exception"; then
                        is_exception=true
                        break
                    fi
                done

                if [ "$is_exception" = false ]; then
                    actual_violations+=("$match")
                fi
            done

            if [ ${#actual_violations[@]} -gt 0 ]; then
                echo -e "${RED}❌${NC} $desc"
                printf '   Line %s\n' "${actual_violations[@]}"
                ((file_failed++))
            fi
        fi
    done

    if [ "$file_failed" -eq 0 ]; then
        echo -e "${GREEN}✅${NC} No hardcoded values detected"
    else
        ((FAILED += file_failed))
    fi

    echo ""
}

echo "🔍 Hardcoded Examples Linter"
echo "============================"
echo ""

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file1.md> [file2.md ...]"
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

echo "============================"

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}❌ $FAILED violation(s) found${NC}"
    echo ""
    echo "Fix by:"
    echo "  1. Use variables instead of hardcoded values"
    echo "  2. Add '# example' or 'e.g.,' to mark intentional examples"
    echo "  3. Use GraphQL variables: \$number, \$owner, \$name"
    echo "  4. Use backticks for node IDs: \`PRRT_*\` not PRRT*\\*"
    exit 1
else
    echo -e "${GREEN}✅ All files passed${NC}"
    exit 0
fi
