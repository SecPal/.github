#!/bin/bash
# SPDX-FileCopyrightText: 2025-2026 SecPal
# SPDX-License-Identifier: MIT

# Domain Policy Enforcement Script
# Validates that only approved SecPal domains and identifiers are used
# ZERO TOLERANCE for other domains or deprecated .app web hosts

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Domain Policy Check ===${NC}"
echo "Allowed: secpal.app, secpal.dev"
echo "Active web hosts: api.secpal.dev, app.secpal.dev"
echo "Identifier-only: app.secpal.app (Android application ID)"
echo "Deprecated web hosts: api.secpal.app, app.secpal.app"
echo "Forbidden: secpal.com, secpal.org, secpal.net, secpal.io, secpal.example, ANY other"
echo ""

matches=$(grep -r -n -E "secpal\.[A-Za-z0-9.-]+" \
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
    grep -v -- "Forbidden:" | \
    grep -v -- "FORBIDDEN:" | \
    grep -v -- '- "secpal\.' | \
    grep -v -- '^[[:space:]]*- \[' || true)

# Allowlist approach: flag any secpal.* domain not matching an approved pattern.
# Approved: secpal.app, secpal.dev, api.secpal.dev, app.secpal.dev, app.secpal.app (identifier context).
# This catches unknown domains (e.g. secpal.xyz) that a denylist-only check would miss.
violations=$(printf '%s\n' "$matches" | \
    grep -Ev 'secpal\.(app|dev)([^a-zA-Z0-9.-]|$)|api\.secpal\.(dev|app)|app\.secpal\.(dev|app)' | \
    grep -E 'secpal\.' || true)

deprecated_web_hosts=$(printf '%s\n' "$matches" | \
    grep -E 'api\.secpal\.app|app\.secpal\.app' | \
    grep -v -- "appId" | \
    grep -v -- "applicationId" | \
    grep -v -- "package name" | \
    grep -v -- "package/application ID" | \
    grep -v -- "application ID" | \
    grep -v -- "Android application identifier" | \
    grep -v -- "Android identifier" | \
    grep -v -- "Android package ID" | \
    grep -v -- "identifier-only" | \
    grep -v -- "active web hosts" | \
    grep -v -- "Deprecated Web Hosts" | \
    grep -v -- "deprecated_web_hosts" | \
    grep -v -- "android_application_identifier" | \
    grep -v -- "validation_rule" | \
    grep -v -- './.github/copilot-instructions.md:' | \
    grep -v -- './.github/copilot-config.yaml:' | \
    grep -v -- 'namespace "app\.secpal\.app"' | \
    grep -v -- 'package app\.secpal\.app;' | \
    grep -v -- 'package_name' | \
    grep -v -- 'custom_url_scheme' | \
    grep -v -- 'getPackageName()' | \
    grep -v -- "\`app\.secpal\.app\` package" | \
    grep -v -- 'better default than Android-specific variants' | \
    grep -v -- 'adb shell monkey -p app\.secpal\.app' | \
    grep -v -- 'deprecated' | \
    grep -v -- 'mistaken' | \
    grep -v -- 'before deployment' | \
    grep -v -- 'must not appear as active web hosts' | \
    grep -v -- 'not deployed' | \
    grep -v -- 'not treated as a deployable web domain' || true)

if [[ -z "$violations" && -z "$deprecated_web_hosts" ]]; then
    echo -e "${GREEN}✅ Domain Policy Check PASSED${NC}"
    echo "All domain usage matches the approved SecPal split"
    exit 0
else
    echo -e "${RED}❌ Domain Policy Check FAILED${NC}"
    echo ""
    if [[ -n "$violations" ]]; then
        echo "Found forbidden domains:"
        echo "$violations"
        echo ""
    fi
    if [[ -n "$deprecated_web_hosts" ]]; then
        echo "Found deprecated .app web-host usage:"
        echo "$deprecated_web_hosts"
        echo ""
    fi
    echo -e "${YELLOW}Policy:${NC}"
    echo "  - secpal.app: public homepage and real email addresses"
    echo "  - api.secpal.dev: live API host"
    echo "  - app.secpal.dev: live PWA/frontend host"
    echo "  - secpal.dev: development, staging, testing, examples"
    echo "  - app.secpal.app: Android application identifier only"
    echo "  - DEPRECATED as web hosts: api.secpal.app, app.secpal.app"
    echo "  - FORBIDDEN: secpal.com, secpal.org, secpal.net, secpal.io, secpal.example"
    echo ""
    echo "Fix these violations before committing."
    exit 1
fi
