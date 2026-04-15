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

if ! grep -Fq 'If CHANGELOG.md changed, every entry was checked against the implementation, tests, schema, or config changed in this PR' "$TEMPLATE"; then
  echo "PR template is missing the changelog verification checklist item." >&2
  exit 1
fi

if ! grep -Fq 'and avoids claims that the code does not actually enforce yet' "$TEMPLATE"; then
  echo "PR template is missing the no-overstatement reminder for changelog entries." >&2
  exit 1
fi
