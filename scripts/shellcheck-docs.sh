#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# shellcheck-docs: Extract and validate bash code blocks from markdown files
# Usage: shellcheck-docs.sh <file1.md> [file2.md ...]
# Exit 0: All checks pass
# Exit 1: shellcheck violations found

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Temporary directory for extracted scripts
TMPDIR=$(umask 077; mktemp -d)
trap 'rm -rf -- "$TMPDIR"' EXIT

FAILED=0
TOTAL_BLOCKS=0

extract_bash_blocks() {
    local file="$1"
    local in_bash_block=false
    local block_num=0
    local current_block=""

    while IFS= read -r line; do
        if [[ "$line" =~ ^\`\`\`(bash|sh|zsh|shell) ]]; then
            in_bash_block=true
            ((++block_num))
            current_block=""
        elif [[ "$line" =~ ^\`\`\` ]] && [ "$in_bash_block" = true ]; then
            in_bash_block=false
            # Save block to temp file
            local block_file="$TMPDIR/$(basename "$file" .md)_block_${block_num}.sh"
            echo "$current_block" > "$block_file"
            echo "$block_file"
        elif [ "$in_bash_block" = true ]; then
            current_block+="$line"$'\n'
        fi
    done < "$file"
}

check_bash_patterns() {
    local script="$1"
    local violations=()

    # Pattern 1: Missing shopt -s nullglob for globs
    if grep -E 'for .* in \*\.(sh|txt|md|yml|yaml|json)' "$script" > /dev/null 2>&1; then
        if ! grep -q 'shopt -s nullglob' "$script"; then
            violations+=("Missing 'shopt -s nullglob' before glob pattern")
        fi
    fi

    # Pattern 2: while loop with pipe (subshell exit issue)
    if grep -E '\| *while .*read' "$script" > /dev/null 2>&1; then
        if ! grep -E '< *<\(' "$script" > /dev/null 2>&1; then
            violations+=("Piped while loop (exit won't propagate) - use process substitution")
        fi
    fi

    # Pattern 3: mktemp without atomic permissions
    if grep -q 'mktemp -d' "$script"; then
        # Check for umask 077 with mktemp
        if ! grep -E 'umask 077.*mktemp' "$script" > /dev/null 2>&1; then
            # Look for variable assignment from mktemp
            local mktemp_var
            mktemp_var=$(grep -E '([A-Za-z_][A-Za-z0-9_]*)=.*mktemp' "$script" | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/' | head -n1)
            if [ -n "$mktemp_var" ]; then
                # Check if chmod is applied to that specific variable
                if ! grep -E "chmod .*\\\$$mktemp_var" "$script" > /dev/null 2>&1; then
                    violations+=("mktemp without atomic permissions (use: TMPDIR=\$(umask 077; mktemp -d) or chmod on mktemp result)")
                fi
            else
                violations+=("mktemp without atomic permissions (use: TMPDIR=\$(umask 077; mktemp -d))")
            fi
        fi
    fi

    # Pattern 4: Trap without cleanup
    if grep -q 'mktemp' "$script"; then
        if ! grep -E "trap.*'rm -rf" "$script" > /dev/null 2>&1; then
            violations+=("mktemp without trap cleanup")
        fi
    fi

    # Pattern 5: rm -rf without -- protection
    if grep -E 'rm -rf [^-]' "$script" > /dev/null 2>&1; then
        if ! grep -E 'rm -rf -- ' "$script" > /dev/null 2>&1; then
            violations+=("rm -rf without '--' protection (use: rm -rf -- \"\$VAR\")")
        fi
    fi

    # Pattern 6: read without -r (only match bash read command, not GraphQL)
    if grep -E '^[[:space:]]*read [A-Z_]+' "$script" > /dev/null 2>&1; then
        if ! grep -q 'read -r' "$script"; then
            violations+=("read without -r (backslash interpretation risk)")
        fi
    fi

    printf '%s\n' "${violations[@]}"
}

echo "🔍 Shellcheck for Documentation Code Blocks"
echo "==========================================="
echo ""

for file in "$@"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌${NC} File not found: $file"
        ((FAILED++))
        continue
    fi

    echo "📄 Processing: $file"

    # Extract bash blocks
    mapfile -t blocks < <(extract_bash_blocks "$file")

    if [ ${#blocks[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️${NC}  No bash blocks found"
        echo ""
        continue
    fi

    echo "   Found ${#blocks[@]} bash block(s)"
    ((TOTAL_BLOCKS += ${#blocks[@]}))

    # Check each block
    for block_file in "${blocks[@]}"; do
        block_name=$(basename "$block_file")
        echo -n "   Checking $block_name... "

        # Run shellcheck
        if ! shellcheck -x -s bash "$block_file" > "$TMPDIR/${block_name}.log" 2>&1; then
            echo -e "${RED}FAIL${NC}"
            echo "   Shellcheck violations:"
            sed 's/^/      /' "$TMPDIR/${block_name}.log"
            ((FAILED++))
        else
            # Check custom patterns
            mapfile -t pattern_violations < <(check_bash_patterns "$block_file")

            if [ ${#pattern_violations[@]} -gt 0 ] && [ -n "${pattern_violations[0]}" ]; then
                echo -e "${RED}FAIL${NC}"
                echo "   Pattern violations:"
                printf '      - %s\n' "${pattern_violations[@]}"
                ((FAILED++))
            else
                echo -e "${GREEN}PASS${NC}"
            fi
        fi
    done

    echo ""
done

echo "==========================================="
echo "Total blocks checked: $TOTAL_BLOCKS"

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}❌ $FAILED block(s) failed${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All blocks passed${NC}"
    exit 0
fi
