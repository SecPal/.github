#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$REPO_ROOT/.github/pull_request_template.md"

if [ ! -f "$TEMPLATE" ]; then
  echo "Expected file '.github/pull_request_template.md' was not found." >&2
  exit 1
fi

required_changelog_phrases=(
  'CHANGELOG\.md changed'
  'every entry was checked'
  'implementation, tests, schema, or config changed in this PR'
)

for phrase in "${required_changelog_phrases[@]}"; do
  if ! grep -Eiq "$phrase" "$TEMPLATE"; then
    echo "PR template is missing the changelog verification checklist item." >&2
    exit 1
  fi
done

if ! grep -Eq 'avoids claims.*does not actually enforce yet' "$TEMPLATE"; then
  echo "PR template is missing the no-overstatement reminder for changelog entries." >&2
  exit 1
fi
