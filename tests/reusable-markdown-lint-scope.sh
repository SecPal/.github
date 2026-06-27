#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
workflow_file="$REPO_ROOT/.github/workflows/reusable-markdown-lint.yml"

# shellcheck disable=SC2016
lint_step="$(grep -F 'run: markdownlint --config "${{ inputs.config-file }}"' "$workflow_file")"

if ! printf '%s\n' "$lint_step" | grep -Eq '(^|[[:space:]])--ignore[[:space:]]+\.secpal-governance($|[[:space:]])'; then
    echo "Expected reusable markdown lint workflow to exclude .secpal-governance" >&2
    printf '%s\n' "$lint_step" >&2
    exit 1
fi
