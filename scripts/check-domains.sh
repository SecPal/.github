#!/bin/bash
# SPDX-FileCopyrightText: 2025-2026 SecPal
# SPDX-License-Identifier: MIT

# Domain Policy Enforcement Script
# Scope: enforces the secpal.* namespace split only (match regex:
#   secpal\.[A-Za-z0-9.-]+). Non-secpal SecPal-owned hosts (e.g.
#   guardguide.de) are intentionally out of scope here and are governed by
#   their owning repository's policy guard.
# ZERO TOLERANCE for unapproved secpal.* hosts or deprecated .app web hosts.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Domain Policy Check ===${NC}"
echo "Scope: enforces the secpal.* namespace split only (match regex: secpal\\.[A-Za-z0-9.-]+)."
echo "Out of scope: non-secpal SecPal-owned hosts such as guardguide.de are governed by"
echo "their own repository policy guards and are intentionally not inspected here."
echo "Allowed: secpal.app, changelog.secpal.app, apk.secpal.app, secpal.dev"
echo "Public changelog site: changelog.secpal.app"
echo "Active web hosts: api.secpal.dev, app.secpal.dev"
echo "Android artifact host: apk.secpal.app"
echo "Human-facing Android landing page: secpal.app/android"
echo "Identifier-only: app.secpal (Android application ID)"
echo "Deprecated web hosts: api.secpal.app"
echo "Forbidden secpal.* variants: secpal.com, secpal.org, secpal.net, secpal.io,"
echo "  secpal.example, app.secpal.app, and any other unapproved secpal.* host."
echo ""

# Defense in depth: `--exclude-dir=".context"` (below) is git-tracking
# unaware, so a `git add --force` on `.context/forced.md` would otherwise
# let a committed forbidden host slip past the gate. Inside a git workspace
# we list every tracked path that sits inside `.context/` and fail loudly
# if any exist — the exclusion is then only doing what it advertises:
# skipping the gitignored agent scratch directory (see SecPal/.github#489).
if command -v git >/dev/null 2>&1 \
    && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    tracked_context_paths=()
    while IFS= read -r -d '' tracked_path; do
        tracked_context_paths+=("$tracked_path")
    done < <(git ls-files -z -- '.context' '.context/**' '**/.context' '**/.context/**' 2>/dev/null || true)
    if [[ ${#tracked_context_paths[@]} -gt 0 ]]; then
        echo -e "${RED}❌ Domain Policy Check FAILED${NC}"
        echo ""
        echo "Tracked files inside the gitignored agent scratch directory '.context/':"
        printf '  %s\n' "${tracked_context_paths[@]}"
        echo ""
        echo ".context/ is meant to be gitignored scratch space for Polyscope-managed"
        echo "workspaces. Never use 'git add --force' on .context/ content — move the"
        echo "file to a tracked path instead so the domain policy gate (and CI) can"
        echo "inspect it. See SecPal/.github#489."
        exit 1
    fi
fi

# --exclude-dir=".context" skips any directory named exactly ".context" at
# any recursion depth. Polyscope-managed workspaces use .context/ as a
# gitignored scratch directory for throwaway agent files (PR body drafts,
# notes, etc.) that never reach CI — so the local gate must not flag them
# either (see SecPal/.github#489). The git-tracking guard above closes the
# `git add --force` bypass so this exclusion can only skip genuinely
# untracked scratch files; violations in any tracked path still fail.
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
    --exclude-dir=".context" \
    . 2>/dev/null | \
    grep -v -- "check-domains.sh" | \
    grep -v -- "Forbidden:" | \
    grep -v -- "FORBIDDEN:" | \
    grep -v -- '- "secpal\.' | \
    # Local SQLite/database paths like `/tmp/secpal.sqlite` are filesystem
    # fixtures, not hostnames. Keep the gate focused on actual secpal.*
    # namespace usage instead of file basenames.
    grep -Ev '(^|[^A-Za-z0-9._-])(\./|\.\./|(/[^[:space:]/]+)+/)secpal\.(sqlite|sqlite3|db)($|[^A-Za-z0-9._-])' | \
    grep -v -- '^[[:space:]]*- \[' || true)

# Allowlist approach: flag any secpal.* domain not matching an approved pattern.
# Approved: secpal.app, apk.secpal.app, secpal.dev, api.secpal.dev, app.secpal.dev.
# api.secpal.app is temporarily tolerated (deprecated web host, flagged separately).
# This catches unknown domains (e.g. secpal.xyz) that a denylist-only check would miss.
violations=$(printf '%s\n' "$matches" | \
    grep -Ev '(^|[^A-Za-z0-9.-])secpal\.app($|[^A-Za-z0-9._-]|\.[^A-Za-z0-9_-]|\.$)|(^|[^A-Za-z0-9.-])changelog\.secpal\.app($|[^A-Za-z0-9._-]|\.[^A-Za-z0-9_-]|\.$)|(^|[^A-Za-z0-9.-])apk\.secpal\.app($|[^A-Za-z0-9._-]|\.[^A-Za-z0-9_-]|\.$)|(^|[^A-Za-z0-9.-])(\*\.|\.)?([A-Za-z0-9-]+\.)*secpal\.dev(\.[A-Za-z0-9_-]+)*($|[^A-Za-z0-9._-]|\.[^A-Za-z0-9_-]|\.$)|(^|[^A-Za-z0-9.-])api\.secpal\.app($|[^A-Za-z0-9._-]|\.[^A-Za-z0-9_-]|\.$)' | \
    grep -E 'secpal\.' || true)

deprecated_web_hosts=$(printf '%s\n' "$matches" | \
    grep -E 'api\.secpal\.app' | \
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
    echo -e "${YELLOW}Policy (scope: secpal.* namespace split only):${NC}"
    echo "  - secpal.app: public homepage and real email addresses"
    echo "  - changelog.secpal.app: public changelog site"
    echo "  - apk.secpal.app: canonical Android artifact/download host"
    echo "  - api.secpal.dev: live API host"
    echo "  - app.secpal.dev: live PWA/frontend host"
    echo "  - secpal.dev: development, staging, testing, examples"
    echo "  - app.secpal: Android application identifier only"
    echo "  - secpal.app/android: human-facing Android landing page"
    echo "  - DEPRECATED as web hosts: api.secpal.app"
    echo "  - FORBIDDEN secpal.* variants: secpal.com, secpal.org, secpal.net, secpal.io, secpal.example, app.secpal.app"
    echo "  - Non-secpal SecPal hosts (e.g. guardguide.de) are out of scope; enforce them in the owning repository."
    echo ""
    echo "Fix these violations before committing."
    exit 1
fi
