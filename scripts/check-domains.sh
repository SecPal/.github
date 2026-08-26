#!/bin/bash
# SPDX-FileCopyrightText: 2025-2026 SecPal
# SPDX-License-Identifier: MIT

# Domain Policy Enforcement Script
# Scope: enforces the secpal.* namespace split only (match regex:
#   secpal\.[A-Za-z0-9.-]+). Non-secpal SecPal-owned hosts (e.g.
#   guardguide.de) are intentionally out of scope here and are governed by
#   their owning repository's policy guard.
# ZERO TOLERANCE for unapproved secpal.* values or deprecated .app web hosts.

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
echo "Public hosts: secpal.app, apk.secpal.app"
echo "Development/preview hosts: secpal.dev, api.secpal.dev, app.secpal.dev, preview.secpal.dev, and approved *.preview.secpal.dev identities"
echo "Private internal service identities: db.secpal.internal (exact only)"
echo "Identifier-only values: app.secpal (Android application ID)"
echo "Approved reverse-DNS technical identifiers: io.secpal.polyscope.preview (exact only; not a host)"
echo "Deprecated web hosts: api.secpal.app"
echo "Forbidden secpal.* variants: secpal.com, secpal.org, secpal.net, secpal.io,"
echo "  secpal.example, app.secpal.app, every other secpal.internal name, and any"
echo "  other unapproved secpal.* value."
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
historical_evidence_paths=(
    "docs/feature-requirements.md"
    "docs/adr/20251219-user-based-tenant-resolution.md"
)

# These exact files are an archived planning record and a superseded ADR. They
# may quote historical identifiers as evidence, but that evidence never creates
# current domain authority. Keep this registry exact: no directory, ADR, marker,
# or wildcard-based exception is permitted.
is_historical_evidence_path() {
    local path="${1#./}"
    local historical_path
    for historical_path in "${historical_evidence_paths[@]}"; do
        if [ "$path" = "$historical_path" ]; then
            return 0
        fi
    done
    return 1
}

# SecPal's control of secpal.io establishes io.secpal as legitimate reverse-DNS
# namespace authority, but it does not authorize web or service hosts. Technical
# identifiers are approved individually and remain separate from host policy.
approved_technical_identifiers=(
    "io.secpal.polyscope.preview"
)

is_approved_technical_identifier() {
    local candidate="$1"
    local approved_identifier
    for approved_identifier in "${approved_technical_identifiers[@]}"; do
        if [ "$candidate" = "$approved_identifier" ]; then
            return 0
        fi
    done
    return 1
}

# Technical-identifier approval is usage-specific. Reject the same token when
# it is an HTTP(S) authority or an explicit Host field. Keep the Host-field
# pattern structural so ordinary prose such as "not a host" is not reclassified.
is_explicit_host_usage() {
    local candidate="$1"
    local source_text="$2"
    local candidate_pattern="${candidate//./\\.}"

    if printf '%s\n' "$source_text" \
        | grep -Eiq "https?://([^/@[:space:]]+@)?${candidate_pattern}([/:?#]|[[:space:]\"']|\$)"; then
        return 0
    fi

    if printf '%s\n' "$source_text" \
        | grep -Eiq "(^[[:space:]]*([-*][[:space:]]+)?|[,{][[:space:]]*)['\"]?host['\"]?[[:space:]]*:[[:space:]]*['\"]?${candidate_pattern}([:/?#[:space:],;}\"']|\$)"; then
        return 0
    fi

    # Curl's header options are case-sensitive syntax; only the Host field name
    # is case-insensitive. Keep this separate from the structural field check so
    # an unrelated short option such as `-h` does not become a header option.
    if printf '%s\n' "$source_text" \
        | grep -Eq "(^|[[:space:]])(-H[[:space:]]+|--header([[:space:]]+|=[[:space:]]*))['\"]?[Hh][Oo][Ss][Tt][[:space:]]*:[[:space:]]*${candidate_pattern}([:/?#[:space:],;}\"']|\$)"; then
        return 0
    fi

    return 1
}

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
    grep -v -- "Forbidden:" | \
    grep -v -- "FORBIDDEN:" | \
    grep -v -- '- "secpal\.' | \
    grep -v -- '^[[:space:]]*- \[' || true)

# The validator's own policy prose names approved and forbidden examples. Its
# exact source path is not an inspected policy surface; tests remain inspected
# and construct negative fixtures at runtime. Historical evidence paths are
# likewise removed from active namespace enforcement without approving their
# quoted identifiers.
active_matches=""
while IFS= read -r matched_line; do
    source_path="${matched_line%%:*}"
    if [ "${source_path#./}" = "scripts/check-domains.sh" ] \
        || is_historical_evidence_path "$source_path"; then
        continue
    fi
    active_matches+="${matched_line}"$'\n'
done <<< "$matches"

# Allowlist approach: classify every matched secpal.* token independently.
# Exact approved reverse-DNS technical identifiers form a separate class and
# are accepted only outside explicit URL-authority and Host-field contexts;
# namespace authority grants no host authority. Unknown technical-looking
# values therefore still fail closed.
# Public/external: secpal.app and apk.secpal.app. Development/preview: secpal.dev,
# api.secpal.dev, app.secpal.dev, the preview.secpal.dev base, and arbitrary
# *.preview.secpal.dev identities.
# Private internal: db.secpal.internal exactly. api.secpal.app is temporarily
# tolerated here because it is reported separately as a deprecated web host.
# This catches unknown values that a denylist-only check would miss, and ensures
# one approved token cannot mask a forbidden token on the same source line.
violations=""
while IFS= read -r matched_line; do
    source_path="${matched_line%%:*}"
    line_remainder="${matched_line#*:}"
    source_line="${line_remainder%%:*}"
    source_text="${line_remainder#*:}"

    while IFS= read -r token; do
        if is_approved_technical_identifier "$token" \
            && ! is_explicit_host_usage "$token" "$source_text"; then
            continue
        fi
        case "$token" in
            secpal.app | apk.secpal.app | secpal.dev | api.secpal.dev | app.secpal.dev | preview.secpal.dev | db.secpal.internal | *.preview.secpal.dev | api.secpal.app)
                ;;
            *)
                violations+="${source_path}:${source_line}:${token}"$'\n'
                ;;
        esac
    done < <(printf '%s\n' "$source_text" | grep -oE '(\*\.)?([A-Za-z0-9_-]+\.)*secpal\.[A-Za-z0-9._-]+' || true)
done <<< "$active_matches"

deprecated_web_hosts=$(printf '%s\n' "$active_matches" | \
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
    echo "All secpal.* usage matches the approved host/service or technical-identifier classifications"
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
    echo "  - Public hosts: secpal.app (homepage/real email), apk.secpal.app (Android downloads)"
    echo "  - Development/preview hosts: secpal.dev, api.secpal.dev, app.secpal.dev, preview.secpal.dev, and *.preview.secpal.dev identities"
    echo "  - Private internal service identity: db.secpal.internal (exact only; not a public host)"
    echo "  - Identifier-only value: app.secpal (Android application ID)"
    echo "  - Reverse-DNS technical identifier: io.secpal.polyscope.preview (exact only; not a host)"
    echo "  - Reverse-DNS namespace authority does not authorize web or service hosts"
    echo "  - Deprecated web host: api.secpal.app"
    echo "  - FORBIDDEN secpal.* variants include every other secpal.internal name and unknown values"
    echo "  - Non-secpal SecPal hosts (e.g. guardguide.de) are out of scope; enforce them in the owning repository."
    echo ""
    echo "Fix these violations before committing."
    exit 1
fi
