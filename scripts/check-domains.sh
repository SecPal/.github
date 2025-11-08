#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: MIT

# Domain Policy Enforcement Script
# Validates that ONLY secpal.app and secpal.dev are used
# ZERO TOLERANCE for other domains

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Domain Policy Check ===${NC}"
echo "Allowed: secpal.app, secpal.dev"
echo "Forbidden: secpal.com, secpal.org, secpal.net, secpal.io, secpal.example, ANY other"
echo ""

# Search for secpal domains
# Includes common file types: md, yaml, json, sh, ts, tsx, js, jsx, php, html
# Excludes:
#   - This script itself
#   - Lines documenting forbidden domains (with "Forbidden:" or "FORBIDDEN:" label)
#   - YAML arrays of forbidden domains (lines with "- "secpal.")
#   - Checklist items mentioning forbidden domains (lines with "[ ]")
violations=$(grep -r "secpal\." \
    --include="*.md" \
    --include="*.yaml" \
    --include="*.yml" \
    --include="*.json" \
    --include="*.sh" \
    --include="*.ts" \
    --include="*.tsx" \
    --include="*.js" \
    --include="*.jsx" \
    --include="*.php" \
    --include="*.html" \
    --exclude-dir=".git" \
    --exclude-dir="node_modules" \
    --exclude-dir="vendor" \
    . 2>/dev/null | \
    grep -v -- "check-domains.sh" | \
    grep -v -- "secpal\.app\|secpal\.dev" | \
    grep -v -- "Forbidden:" | \
    grep -v -- "FORBIDDEN:" | \
    grep -v -- '- "secpal\.' | \
    grep -v -- '\[' || true)

if [[ -z "$violations" ]]; then
    echo -e "${GREEN}✅ Domain Policy Check PASSED${NC}"
    echo "All domains use secpal.app or secpal.dev"
    exit 0
else
    echo -e "${RED}❌ Domain Policy Check FAILED${NC}"
    echo ""
    echo "Found forbidden domains:"
    echo "$violations"
    echo ""
    echo -e "${YELLOW}Policy:${NC}"
    echo "  - secpal.app: Production services, ALL emails"
    echo "  - secpal.dev: Development, testing, examples, docs"
    echo "  - FORBIDDEN: secpal.com, secpal.org, secpal.net, secpal.io, secpal.example"
    echo ""
    echo "Fix these violations before committing."
    exit 1
fi
