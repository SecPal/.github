#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PRE_COMMIT_CONFIG="$REPO_ROOT/.pre-commit-config.yaml"

if grep -Fq 'https://github.com/DavidAnson/markdownlint-cli2' "$PRE_COMMIT_CONFIG"; then
  echo "Expected .pre-commit-config.yaml to stop using the markdownlint-cli2 hook repo" >&2
  exit 1
fi

if grep -Fq 'id: markdownlint-cli2' "$PRE_COMMIT_CONFIG"; then
  echo "Expected .pre-commit-config.yaml to stop using the markdownlint-cli2 hook id" >&2
  exit 1
fi

if ! grep -Fq 'id: markdownlint' "$PRE_COMMIT_CONFIG"; then
  echo "Expected .pre-commit-config.yaml to define a markdownlint hook" >&2
  exit 1
fi

if ! grep -Fq 'npx --yes --package markdownlint-cli@0.49.0 markdownlint --config .markdownlint.json' "$PRE_COMMIT_CONFIG"; then
  echo "Expected .pre-commit-config.yaml to pin markdownlint-cli@0.49.0 via npx" >&2
  exit 1
fi

echo "tests/markdownlint-precommit-config.sh: markdownlint pre-commit hook verified."
