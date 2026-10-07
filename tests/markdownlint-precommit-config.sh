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

node --input-type=module - "$PRE_COMMIT_CONFIG" <<'NODE'
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { load } from 'js-yaml';

const config = load(readFileSync(process.argv[2], 'utf8'));
const hooks = config.repos.flatMap((repo) => repo.hooks);
const hook = hooks.find((candidate) => candidate.id === 'markdownlint');
assert.equal(hook.entry, './node_modules/.bin/markdownlint --config .markdownlint.json --');
assert.equal(hook.language, 'system');
assert.notEqual(hook.pass_filenames, false);
NODE

echo "tests/markdownlint-precommit-config.sh: markdownlint pre-commit hook verified."
