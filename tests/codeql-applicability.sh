#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

validate_applicability() {
  local root="$1"
  local workflow_path="$2"
  local codeql_sources

  if [ ! -f "$root/$workflow_path" ]; then
    echo "Expected workflow '$workflow_path' was not found." >&2
    return 1
  fi

  # Exclude scripts/: Node governance tooling is not the application surface
  # that activates this repository-level analysis contract.
  codeql_sources="$(git -C "$root" ls-files '*.js' '*.jsx' '*.ts' '*.tsx' '*.mjs' '*.cjs' | grep -v '^scripts/' || true)"
  if echo "$codeql_sources" | grep -q .; then
    if ! grep -q 'github/codeql-action/' "$root/$workflow_path"; then
      echo "CodeQL-applicable JS/TS sources outside scripts/ were found, but the CodeQL workflow no longer invokes github/codeql-action." >&2
      return 1
    fi
  elif grep -q 'github/codeql-action/' "$root/$workflow_path"; then
    echo "CodeQL workflow invokes github/codeql-action without a supported source surface." >&2
    return 1
  fi
}

workflow_path=".github/workflows/codeql.yml"
validate_applicability "$REPO_ROOT" "$workflow_path"

fixture="$(mktemp -d "${TMPDIR:-/tmp}/codeql-applicability.XXXXXX")"
trap 'rm -rf "$fixture"' EXIT
git init --quiet "$fixture"
mkdir -p "$fixture/.github/workflows" "$fixture/tests"
printf '%s\n' 'console.log("fixture");' >"$fixture/tests/example.mjs"
printf '%s\n' 'name: CodeQL' >"$fixture/$workflow_path"
git -C "$fixture" add .
if validate_applicability "$fixture" "$workflow_path" >/dev/null 2>&1; then
  echo "Tracked supported source without CodeQL analysis unexpectedly passed." >&2
  exit 1
fi
printf '%s\n' 'uses: github/codeql-action/analyze@0123456789012345678901234567890123456789' >"$fixture/$workflow_path"
if ! validate_applicability "$fixture" "$workflow_path"; then
  echo "Tracked supported source with CodeQL analysis unexpectedly failed." >&2
  exit 1
fi
