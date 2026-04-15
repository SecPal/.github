#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

workflow_path=".github/workflows/codeql.yml"

if [ ! -f "$workflow_path" ]; then
  echo "Expected workflow '$workflow_path' was not found." >&2
  exit 1
fi

has_supported_files=0
if git ls-files '*.js' '*.jsx' '*.ts' '*.tsx' '*.mjs' '*.cjs' | grep -q .; then
  has_supported_files=1
fi

if [ "$has_supported_files" -eq 0 ] && grep -q 'github/codeql-action/' "$workflow_path"; then
  echo "CodeQL workflow still invokes github/codeql-action even though this repository has no tracked JS/TS files." >&2
  echo "Remove the CodeQL action usage or restore supported source files before keeping CodeQL enabled." >&2
  exit 1
fi

if [ "$has_supported_files" -eq 1 ] && ! grep -q 'github/codeql-action/' "$workflow_path"; then
  echo "Tracked JS/TS files were found, but the CodeQL workflow no longer invokes github/codeql-action." >&2
  echo "Restore a real CodeQL scan before merging supported source files into this repository." >&2
  exit 1
fi
