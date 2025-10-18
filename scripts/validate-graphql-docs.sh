#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# validate-graphql-docs.sh: Validate GraphQL queries in documentation
# Usage: validate-graphql-docs.sh <file1.md> [file2.md ...]
# Exit 0: All GraphQL queries valid
# Exit 1: Invalid queries found

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TMPDIR=$(umask 077; mktemp -d)
trap 'rm -rf -- "$TMPDIR"' EXIT

FAILED=0
TOTAL_QUERIES=0

extract_graphql_queries() {
    local file="$1"
    local in_graphql=false
    local query_num=0
    local current_query=""
    local is_shell_block=false

    while IFS= read -r line; do
        # Detect GraphQL in bash/shell blocks
        if [[ "$line" =~ ^\`\`\`(bash|sh|yaml) ]]; then
            is_shell_block=true
        elif [[ "$line" =~ ^[[:space:]]*query=\' ]]; then
            in_graphql=true
            ((++query_num))
            current_query="$line"$'\n'
        elif [[ "$line" =~ ^[[:space:]]*query=\" ]]; then
            in_graphql=true
            ((++query_num))
            current_query="$line"$'\n'
        elif [[ "$line" =~ ^[[:space:]]*-f[[:space:]]+query= ]]; then
            in_graphql=true
            ((++query_num))
            current_query="$line"$'\n'
        elif [ "$in_graphql" = true ]; then
            current_query+="$line"$'\n'
            # End detection (closing quote or next command)
            if [[ "$line" =~ \'|\" ]] && [[ "$line" =~ -f\ |^\` ]]; then
                in_graphql=false
                local query_file="$TMPDIR/query_${query_num}.graphql"
                echo "$current_query" > "$query_file"
                echo "$query_file"
            fi
        elif [[ "$line" =~ ^\`\`\` ]]; then
            is_shell_block=false
            in_graphql=false
        fi
    done < "$file"
}

check_graphql_query() {
    local query_file="$1"
    local violations=()

    # Extract actual GraphQL from shell wrapper
    # Extract GraphQL query content using multi-step approach for clarity
    local raw_query
    raw_query=$(sed -n "/query=/,/'/p" "$query_file" || echo "")

    local graphql_content
    graphql_content=$(echo "$raw_query" | sed "s/.*query=['\"]//" | sed "s/['\"].*//" || echo "")

    if [ -z "$graphql_content" ]; then
        violations+=("Could not extract GraphQL query")
        printf '%s\n' "${violations[@]}"
        return
    fi

    # Pattern 1: Variable usage without parameter
    if echo "$graphql_content" | grep -qE '\$[a-zA-Z_]+'; then
        # Check if query definition has matching variables
        local vars_used
        vars_used=$(echo "$graphql_content" | grep -oE '\$[a-zA-Z_]+' | sort -u)
        local query_def
        query_def=$(echo "$graphql_content" | grep -E '^query')

        for var in $vars_used; do
            var_name=${var#$}
            if ! echo "$query_def" | grep -qE "\\\$$var_name:"; then
                violations+=("Variable $var used but not declared in query parameters")
            fi
        done
    fi

    # Pattern 2: Single-quoted query with variable expansion
    if grep -qE "query='.*\\\$" "$query_file"; then
        violations+=("Single-quoted query with variable (won't expand) - use double quotes or GraphQL variables")
    fi

    # Pattern 3: Hardcoded values instead of variables
    if echo "$graphql_content" | grep -qE 'owner: "(SecPal|[a-zA-Z]+)"' && ! echo "$graphql_content" | grep -qE '\$owner'; then
        violations+=("Hardcoded owner - use \$owner variable")
    fi

    if echo "$graphql_content" | grep -qE 'number: [0-9]+' && ! echo "$graphql_content" | grep -qE '\$number'; then
        violations+=("Hardcoded number - use \$number variable")
    fi

    if echo "$graphql_content" | grep -qE 'name: "(\\.github|[a-zA-Z-]+)"' && ! echo "$graphql_content" | grep -qE '\$name'; then
        violations+=("Hardcoded name - use \$name variable")
    fi

    # Pattern 4: Pagination without pageInfo
    if echo "$graphql_content" | grep -qE 'first: [0-9]+'; then
        if ! echo "$graphql_content" | grep -qE 'pageInfo.*hasNextPage|endCursor'; then
            violations+=("Pagination used (first:) without pageInfo - add pageInfo { hasNextPage endCursor }")
        fi
    fi

    # Pattern 5: Basic syntax errors
    local opening_braces
    opening_braces=$(echo "$graphql_content" | grep -o '{' | wc -l)
    local closing_braces
    closing_braces=$(echo "$graphql_content" | grep -o '}' | wc -l)

    if [ "$opening_braces" -ne "$closing_braces" ]; then
        violations+=("Mismatched braces: $opening_braces opening, $closing_braces closing")
    fi

    printf '%s\n' "${violations[@]}"
}

echo "🔍 GraphQL Query Validator"
echo "=========================="
echo ""

for file in "$@"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌${NC} File not found: $file"
        ((FAILED++))
        continue
    fi

    echo "📄 Processing: $file"

    # Extract GraphQL queries
    mapfile -t queries < <(extract_graphql_queries "$file")

    if [ ${#queries[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️${NC}  No GraphQL queries found"
        echo ""
        continue
    fi

    echo "   Found ${#queries[@]} GraphQL quer(y/ies)"
    ((TOTAL_QUERIES += ${#queries[@]}))

    # Check each query
    for query_file in "${queries[@]}"; do
        query_name=$(basename "$query_file")
        echo -n "   Checking $query_name... "

        mapfile -t violations < <(check_graphql_query "$query_file")

        if [ ${#violations[@]} -gt 0 ] && [ -n "${violations[0]}" ]; then
            echo -e "${RED}FAIL${NC}"
            printf '      - %s\n' "${violations[@]}"
            ((FAILED++))
        else
            echo -e "${GREEN}PASS${NC}"
        fi
    done

    echo ""
done

echo "=========================="
echo "Total queries checked: $TOTAL_QUERIES"

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}❌ $FAILED quer(y/ies) failed${NC}"
    echo ""
    echo "Common fixes:"
    echo "  1. Use GraphQL variables: query(\$number: Int!) instead of hardcoding"
    echo "  2. Use double quotes for variable expansion in shell"
    echo "  3. Add pageInfo when using pagination (first:)"
    echo "  4. Parameterize owner, name, number"
    exit 1
else
    echo -e "${GREEN}✅ All queries valid${NC}"
    exit 0
fi
