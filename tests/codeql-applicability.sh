#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

language="${1:-javascript-typescript}"
case "$language" in
  javascript-typescript)
    # Retain the existing JavaScript/TypeScript applicability boundary.
    patterns=('*.js' '*.jsx' '*.ts' '*.tsx' '*.mjs' '*.cjs' ':(exclude)scripts/**')
    fixture_source='tests/example.mjs'
    ;;
  python)
    patterns=('*.py')
    fixture_source='scripts/example.py'
    ;;
  actions)
    patterns=(':(glob).github/workflows/*.yml' ':(glob).github/workflows/*.yaml' \
              ':(glob).github/actions/**/action.yml' ':(glob).github/actions/**/action.yaml')
    fixture_source='.github/workflows/example.yml'
    ;;
  *)
    echo 'Unsupported CodeQL language.' >&2
    exit 1
    ;;
esac

validate_applicability() {
  local root="$1"
  local workflow_path="$2"
  local codeql_sources

  if [ ! -f "$root/$workflow_path" ]; then
    echo "Expected workflow '$workflow_path' was not found." >&2
    return 1
  fi

  codeql_sources="$(git -C "$root" ls-files "${patterns[@]}")"
  if [[ -n "$codeql_sources" ]]; then
    if ! grep -q 'github/codeql-action/' "$root/$workflow_path"; then
      echo "Tracked $language source requires github/codeql-action." >&2
      return 1
    fi
  elif grep -q 'github/codeql-action/' "$root/$workflow_path"; then
    echo "CodeQL workflow invokes github/codeql-action without tracked $language source." >&2
    return 1
  fi
}

workflow_path=".github/workflows/codeql.yml"
validate_applicability "$REPO_ROOT" "$workflow_path"

fixture="$(mktemp -d "${TMPDIR:-/tmp}/codeql-applicability.XXXXXX")"
trap 'rm -rf "$fixture"' EXIT
git init --quiet "$fixture"
fixture_workflow='workflow-contract.yml'
invocation='uses: github/codeql-action/analyze@0123456789012345678901234567890123456789'
# Keep the declaration outside the fixture source so Actions can test both cases.
printf '%s\n' "$invocation" >"$fixture/$fixture_workflow"
if validate_applicability "$fixture" "$fixture_workflow" >/dev/null 2>&1; then
  echo "Declared $language analysis without tracked source unexpectedly passed." >&2
  exit 1
fi
mkdir -p "$(dirname "$fixture/$fixture_source")"
touch "$fixture/$fixture_source"
printf '%s\n' 'name: CodeQL' >"$fixture/$fixture_workflow"
git -C "$fixture" add .
if validate_applicability "$fixture" "$fixture_workflow" >/dev/null 2>&1; then
  echo "Tracked supported source without CodeQL analysis unexpectedly passed." >&2
  exit 1
fi
printf '%s\n' "$invocation" >"$fixture/$fixture_workflow"
if ! validate_applicability "$fixture" "$fixture_workflow"; then
  echo "Tracked supported source with CodeQL analysis unexpectedly failed." >&2
  exit 1
fi
