#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
validator="$repo_root/scripts/validate-pr-size-policy.sh"
preflight="$repo_root/scripts/preflight.sh"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/validate-pr-size-policy.XXXXXX")"
trap 'rm -rf -- "$workspace"' EXIT

make_repo() {
  local name="$1"
  mkdir -p "$workspace/$name/scripts" "$workspace/$name/.github/workflows"
}

make_repo advisory
cat >"$workspace/advisory/scripts/preflight.sh" <<'EOF'
ADVISORY_THRESHOLD=600
CHANGED=$((INSERTIONS + DELETIONS))
echo "PR size: $CHANGED changed lines ($INSERTIONS insertions, $DELETIONS deletions; advisory threshold: $ADVISORY_THRESHOLD)"
if [ "$CHANGED" -gt "$ADVISORY_THRESHOLD" ]; then
  echo "WARNING: PR size advisory threshold exceeded."
fi
EOF
cat >"$workspace/advisory/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  pr-size:
    uses: SecPal/.github/.github/workflows/reusable-pr-size.yml@7f5d24a599c03cdc59998c22578c345c518b755d
EOF

make_repo no-gate
cat >"$workspace/no-gate/CHANGELOG.md" <<'EOF'
# Changelog

In 2025 the repository used a hard 600-line limit.
EOF

make_repo hard-exit
cat >"$workspace/hard-exit/scripts/preflight.sh" <<'EOF'
if [ "$CHANGED" -gt 600 ]; then
  echo "PR TOO LARGE"
  exit 2
fi
EOF

make_repo override-file
cat >"$workspace/override-file/scripts/preflight.sh" <<'EOF'
if [ -f .preflight-allow-large-pr ]; then
  echo "override active"
fi
EOF

make_repo label-override
cat >"$workspace/label-override/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - run: gh pr view "$PR_NUMBER" --json labels
      - run: grep -q large-pr-approved labels.json
EOF

make_repo workflow-failure
cat >"$workspace/workflow-failure/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - run: |
          if [ "$CHANGED" -gt "$MAX_LINES" ]; then
            echo "Maximum allowed: 600"
            exit 1
          fi
EOF

bash "$validator" "$workspace/advisory" "$workspace/no-gate" >"$workspace/pass.out"
grep -Fq "advisory: PASS" "$workspace/pass.out"
grep -Fq "no-gate: PASS" "$workspace/pass.out"

for invalid in hard-exit override-file label-override workflow-failure; do
  if bash "$validator" "$workspace/$invalid" >"$workspace/$invalid.out" 2>&1; then
    echo "Expected $invalid fixture to fail policy validation" >&2
    exit 1
  fi
  grep -Fq "$invalid: FAIL" "$workspace/$invalid.out"
done

bash "$validator" \
  "$repo_root" \
  "$repo_root/../api" \
  "$repo_root/../frontend" \
  "$repo_root/../contracts" \
  "$repo_root/../android" \
  "$repo_root/../GuardGuide" \
  "$repo_root/../guardguide.de" \
  "$repo_root/../secpal.app"

grep -Fq "bash tests/validate-pr-size-policy.sh" "$preflight"

echo "tests/validate-pr-size-policy.sh: organization-wide policy verified."
