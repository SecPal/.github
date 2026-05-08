#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-pull-request-commit-signatures.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/pull-request-commit-signatures.yml"
QUICK_REFERENCE="$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md"

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
