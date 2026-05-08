#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-pull-request-commit-signatures.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/pull-request-commit-signatures.yml"
QUICK_REFERENCE="$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md"
SHELL_BIN="${BASH:-$(command -v bash)}"

if [ ! -f "$VALIDATOR" ]; then
  echo "Expected validator script was not found: $VALIDATOR" >&2
  exit 1
fi

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

if [ ! -f "$QUICK_REFERENCE" ]; then
  echo "Expected quick reference doc was not found: $QUICK_REFERENCE" >&2
  exit 1
fi

if ! grep -Fq 'scripts/validate-pull-request-commit-signatures.sh' "$WORKFLOW"; then
  echo "Workflow does not invoke the pull-request commit signature validator script." >&2
  exit 1
fi

if grep -Fq 'XXXXXX.json' "$VALIDATOR"; then
  echo "Validator uses a BSD-incompatible mktemp template with a suffix after the X placeholder." >&2
  exit 1
fi

if ! grep -Fq 'pull-request-commits.json.XXXXXX' "$VALIDATOR"; then
  echo "Validator must use a portable mktemp template whose X placeholder is at the end." >&2
  exit 1
fi

if ! grep -Fq 'pull_request_target:' "$WORKFLOW"; then
  echo "Workflow must run from the base branch context so PRs cannot self-bypass the validator." >&2
  exit 1
fi

if ! grep -Fq 'github.event.pull_request.base.sha' "$WORKFLOW"; then
  echo "Workflow must check out the base revision before running the validator." >&2
  exit 1
fi

if ! grep -Fq "pulls/\$PR_NUMBER/commits" "$WORKFLOW"; then
  echo "Workflow does not fetch the pull request commits payload from GitHub." >&2
  exit 1
fi

if ! grep -Fq -- '--paginate' "$WORKFLOW"; then
  echo "Workflow must paginate pull request commits so every commit is validated." >&2
  exit 1
fi

if ! grep -Fq 'per_page=100' "$WORKFLOW"; then
  echo "Workflow must request the maximum pull request commit page size from GitHub." >&2
  exit 1
fi

if ! grep -Fq 'synchronize' "$WORKFLOW"; then
  echo "Workflow must rerun when new commits are pushed to the pull request." >&2
  exit 1
fi

if ! grep -Fq 'Signed commit verification is enforced by CI.' "$QUICK_REFERENCE"; then
  echo "Quick reference must document that signed commit verification is enforced by CI." >&2
  exit 1
fi

if ! grep -Fq 'English-only GitHub communication remains reviewer-enforced for now.' "$QUICK_REFERENCE"; then
  echo "Quick reference must document that English-only GitHub communication is still reviewer-enforced." >&2
  exit 1
fi

verified_payload="$(cat <<'EOF'
[
  {
    "sha": "57cce5b2c81fb2c72f1af4de51c4fd586f17972f",
    "commit": {
      "message": "feat(governance): validate pull request evidence\n\nMore context.",
      "verification": {
        "verified": true,
        "reason": "valid"
      }
    }
  }
]
EOF
)"

if ! PR_COMMITS_JSON="$verified_payload" bash "$VALIDATOR" >/tmp/pull-request-commit-signatures-positive.log 2>&1; then
  cat /tmp/pull-request-commit-signatures-positive.log >&2
  echo "Validator rejected a pull request payload whose commits were verified." >&2
  exit 1
fi

python_command=''

if command -v python3 >/dev/null 2>&1; then
  python_command='python3'
elif command -v python >/dev/null 2>&1 && python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info.major == 3 else 1)
PY
then
  python_command='python'
fi

if [ -n "$python_command" ]; then
  parser_fallback_bin="$(mktemp -d "${TMPDIR:-/tmp}/pull-request-commit-signatures.XXXXXX")"
  ln -s "$(command -v "$python_command")" "$parser_fallback_bin/$python_command"
  ln -s "$(command -v mktemp)" "$parser_fallback_bin/mktemp"
  ln -s "$(command -v rm)" "$parser_fallback_bin/rm"

  if ! PATH="$parser_fallback_bin" PR_COMMITS_JSON="$verified_payload" "$SHELL_BIN" "$VALIDATOR" >/tmp/pull-request-commit-signatures-python-fallback.log 2>&1; then
    cat /tmp/pull-request-commit-signatures-python-fallback.log >&2
    echo "Validator rejected a verified payload when only the Python fallback parser was available." >&2
    rm -rf "$parser_fallback_bin"
    exit 1
  fi

  rm -rf "$parser_fallback_bin"
fi

parserless_bin="$(mktemp -d "${TMPDIR:-/tmp}/pull-request-commit-signatures.XXXXXX")"
ln -s "$(command -v mktemp)" "$parserless_bin/mktemp"
ln -s "$(command -v rm)" "$parserless_bin/rm"

if PATH="$parserless_bin" PR_COMMITS_JSON="$verified_payload" "$SHELL_BIN" "$VALIDATOR" >/tmp/pull-request-commit-signatures-parserless.log 2>&1; then
  echo "Validator unexpectedly succeeded without Node.js or Python 3 available." >&2
  rm -rf "$parserless_bin"
  exit 1
fi

if ! grep -Fq 'Node.js or Python 3 is required to validate pull request commit signatures.' /tmp/pull-request-commit-signatures-parserless.log; then
  cat /tmp/pull-request-commit-signatures-parserless.log >&2
  echo "Validator did not explain the missing parser runtime failure." >&2
  rm -rf "$parserless_bin"
  exit 1
fi

rm -rf "$parserless_bin"

unsigned_payload="$(cat <<'EOF'
[
  {
    "sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "commit": {
      "message": "feat(governance): unsigned commit",
      "verification": {
        "verified": false,
        "reason": "unsigned"
      }
    }
  }
]
EOF
)"

if PR_COMMITS_JSON="$unsigned_payload" bash "$VALIDATOR" >/tmp/pull-request-commit-signatures-negative.log 2>&1; then
  echo "Validator unexpectedly accepted an unsigned pull request commit." >&2
  exit 1
fi

if ! grep -Fq 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef' /tmp/pull-request-commit-signatures-negative.log; then
  cat /tmp/pull-request-commit-signatures-negative.log >&2
  echo "Validator did not report the unsigned commit SHA." >&2
  exit 1
fi

if ! grep -Fq 'reason=unsigned' /tmp/pull-request-commit-signatures-negative.log; then
  cat /tmp/pull-request-commit-signatures-negative.log >&2
  echo "Validator did not report the unsigned verification reason." >&2
  exit 1
fi

paginated_unsigned_payload="$(cat <<'EOF'
[
  [
    {
      "sha": "57cce5b2c81fb2c72f1af4de51c4fd586f17972f",
      "commit": {
        "message": "feat(governance): page one",
        "verification": {
          "verified": true,
          "reason": "valid"
        }
      }
    }
  ],
  [
    {
      "sha": "cafebabecafebabecafebabecafebabecafebabe",
      "commit": {
        "message": "feat(governance): page two unsigned",
        "verification": {
          "verified": false,
          "reason": "unsigned"
        }
      }
    }
  ]
]
EOF
)"

if PR_COMMITS_JSON="$paginated_unsigned_payload" bash "$VALIDATOR" >/tmp/pull-request-commit-signatures-paginated.log 2>&1; then
  echo "Validator unexpectedly accepted an unsigned commit from a later paginated payload page." >&2
  exit 1
fi

if ! grep -Fq 'cafebabecafebabecafebabecafebabecafebabe' /tmp/pull-request-commit-signatures-paginated.log; then
  cat /tmp/pull-request-commit-signatures-paginated.log >&2
  echo "Validator did not report the unsigned commit from the later paginated payload page." >&2
  exit 1
fi

empty_payload='[]'

if PR_COMMITS_JSON="$empty_payload" bash "$VALIDATOR" >/tmp/pull-request-commit-signatures-empty.log 2>&1; then
  echo "Validator unexpectedly accepted an empty pull request commit payload." >&2
  exit 1
fi

if ! grep -Fq 'No commits found in pull request payload.' /tmp/pull-request-commit-signatures-empty.log; then
  cat /tmp/pull-request-commit-signatures-empty.log >&2
  echo "Validator did not explain the empty payload failure." >&2
  exit 1
fi
