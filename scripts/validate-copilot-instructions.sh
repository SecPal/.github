#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

run_legacy_repo_validation() {
    local repo_path="$1"

    (
        cd "$repo_path"

        if [ ! -f ".github/copilot-instructions.md" ]; then
            echo "Missing .github/copilot-instructions.md in $repo_path" >&2
            exit 1
        fi

        local spdx_license_marker='SPDX-License''-Identifier:'
        local sidecar_license_pattern='SPDX-License''-Identifier:[[:space:]]+(CC0-1.0|AGPL-3.0-or-later)'
        if [ -f ".github/copilot-instructions.md.license" ]; then
            grep -qE "$sidecar_license_pattern" ".github/copilot-instructions.md.license" || {
                echo "Invalid .github/copilot-instructions.md.license in $repo_path" >&2
                exit 1
            }
        else
            head -n 10 ".github/copilot-instructions.md" | grep -q "$spdx_license_marker" || {
                echo "Missing SPDX header in .github/copilot-instructions.md for $repo_path" >&2
                exit 1
            }
        fi

        if [ -x "$SCRIPT_DIR/../node_modules/.bin/markdownlint" ]; then
            "$SCRIPT_DIR/../node_modules/.bin/markdownlint" --config .markdownlint.json .github/copilot-instructions.md >/dev/null
        fi

        pseudo_inheritance_hits="$(
            grep -RniE '@?extends|inherit[[:space:]]+from|inherits[[:space:]]+from|auto[-[:space:]]*inherit|base[_ -]?instructions?[^[:alpha:]]*(apply|load|import)|parent[_ -]?instructions?[^[:alpha:]]*(apply|load|import)' \
                .github/copilot-instructions.md .github/instructions 2>/dev/null || true
        )"
        if [ -n "$pseudo_inheritance_hits" ] && printf '%s\n' "$pseudo_inheritance_hits" | grep -viE 'do not .*inherit|do not automatically inherit|without inheriting' >/dev/null; then
            echo "Legacy copilot instructions must remain self-contained at runtime in $repo_path" >&2
            exit 1
        fi
    )
}

if [ "$#" -eq 0 ]; then
    if [ -f "AGENTS.md" ]; then
        exec "$SCRIPT_DIR/validate-ai-instructions.sh"
    fi
    run_legacy_repo_validation "$PWD"
    exit 0
fi

overall_status=0
for repo_path in "$@"; do
    if [ ! -d "$repo_path" ]; then
        echo "Repository path not found: $repo_path" >&2
        overall_status=1
        continue
    fi

    if [ -f "$repo_path/AGENTS.md" ]; then
        bash "$SCRIPT_DIR/validate-ai-instructions.sh" "$repo_path" || overall_status=1
        continue
    fi

    run_legacy_repo_validation "$repo_path" || overall_status=1
done

exit "$overall_status"
