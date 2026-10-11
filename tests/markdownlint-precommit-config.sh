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

workspace="$(mktemp -d "${TMPDIR:-/tmp}/markdownlint-precommit-config.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT
mkdir -p "$workspace/scripts" "$workspace/bin"
cp "$REPO_ROOT/scripts/setup-pre-commit.sh" "$workspace/scripts/"
cat >"$workspace/bin/npm" <<'EOF'
#!/usr/bin/env bash
printf 'npm %s in %s\n' "$*" "$PWD" >> "$SETUP_LOG"
exit "${NPM_STATUS:-0}"
EOF
cat >"$workspace/bin/pre-commit" <<'EOF'
#!/usr/bin/env bash
printf 'pre-commit %s\n' "$*" >> "$SETUP_LOG"
EOF
chmod +x "$workspace/bin/"*
SETUP_LOG="$workspace/setup.log" PATH="$workspace/bin:$PATH" \
  bash "$workspace/scripts/setup-pre-commit.sh" >/dev/null
expected="npm ci in $workspace
pre-commit install --install-hooks
pre-commit run --all-files"
if [ "$(cat "$workspace/setup.log")" != "$expected" ]; then
  echo "Expected locked npm dependencies before hook installation and execution" >&2
  cat "$workspace/setup.log" >&2
  exit 1
fi
: >"$workspace/setup.log"
if SETUP_LOG="$workspace/setup.log" NPM_STATUS=23 PATH="$workspace/bin:$PATH" \
  bash "$workspace/scripts/setup-pre-commit.sh" >/dev/null 2>&1; then
  echo "Expected npm installation failure to stop hook setup" >&2
  exit 1
fi
if grep -Fq 'pre-commit ' "$workspace/setup.log"; then
  echo "Expected no hook installation after npm failure" >&2
  exit 1
fi
rm "$workspace/bin/npm"
for tool in bash dirname; do
  ln -s "$(command -v "$tool")" "$workspace/bin/$tool"
done
: >"$workspace/setup.log"
if SETUP_LOG="$workspace/setup.log" PATH="$workspace/bin" \
  bash "$workspace/scripts/setup-pre-commit.sh" >"$workspace/missing-npm.log" 2>&1; then
  echo "Expected missing npm to stop hook setup" >&2
  exit 1
fi
grep -Fq 'npm is not installed' "$workspace/missing-npm.log"
if [ -s "$workspace/setup.log" ]; then
  echo "Expected no hook installation when npm is unavailable" >&2
  exit 1
fi

echo "tests/markdownlint-precommit-config.sh: markdownlint pre-commit hook verified."
