#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

# Regression test for scripts/check-domains.sh covering SecPal/.github#484.
#
# The script is intentionally scoped to enforcing the secpal.* namespace
# split. SecPal-external hosts (e.g. guardguide.de) are governed by their
# own repository policy guards and must NOT be flagged here. This test
# locks in three guarantees so the banner can never drift back to claiming
# the gate covers "any other" domain:
#
#   1. The banner and the failure-mode Policy block document the scope limit
#      (so the help text and the regex agree).
#   2. scripts/README.md documents the same intentional scope.
#   3. Behaviour matches the documented scope: guardguide.de references in
#      a workspace pass cleanly, while an unapproved secpal.* host still
#      fails the gate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/check-domains.sh"
README="$REPO_ROOT/scripts/README.md"

if [ ! -f "$SCRIPT" ]; then
  echo "Missing scripts/check-domains.sh" >&2
  exit 1
fi

if [ ! -f "$README" ]; then
  echo "Missing scripts/README.md" >&2
  exit 1
fi

# 1. Banner documents the intentional scope limit.
if ! grep -Fq 'Scope: enforces the secpal.* namespace split only' "$SCRIPT"; then
  echo "scripts/check-domains.sh banner must declare the secpal.* namespace scope" >&2
  exit 1
fi

if ! grep -Fq 'guardguide.de' "$SCRIPT"; then
  echo "scripts/check-domains.sh must call out guardguide.de as out of scope" >&2
  exit 1
fi

# 2. Failure-mode Policy block also documents the scope.
if ! grep -Fq 'scope: secpal.* namespace split only' "$SCRIPT"; then
  echo "scripts/check-domains.sh Policy block must repeat the scope limit on failure" >&2
  exit 1
fi

if ! grep -Fq 'Non-secpal SecPal hosts' "$SCRIPT"; then
  echo "scripts/check-domains.sh Policy block must point readers at owning-repo guards" >&2
  exit 1
fi

# 3. README documents the intentional scope.
if ! grep -Fq 'Scope (intentional limit)' "$README"; then
  echo "scripts/README.md must document the check-domains.sh scope limit" >&2
  exit 1
fi

if ! grep -Fq 'guardguide.de' "$README"; then
  echo "scripts/README.md must mention guardguide.de as the canonical out-of-scope example" >&2
  exit 1
fi

# 4. Behavioural check: guardguide.de references pass, unapproved secpal.* fails.
workspace="$(mktemp -d "${TMPDIR:-/tmp}/check-domains.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/scripts"
cp "$SCRIPT" "$workspace/scripts/check-domains.sh"

cat >"$workspace/guardguide.md" <<'EOF'
# GuardGuide notes

Production homepage: https://guardguide.de
Marketing redirect: https://www.guardguide.de

Approved SecPal hosts used in examples:
- https://secpal.app
- https://changelog.secpal.app
- https://apk.secpal.app
- https://api.secpal.dev
- https://app.secpal.dev
- https://feature-branch.preview.secpal.dev
EOF

(
  cd "$workspace"
  bash scripts/check-domains.sh >output.txt 2>&1
)

if ! grep -Fq 'Domain Policy Check PASSED' "$workspace/output.txt"; then
  cat "$workspace/output.txt"
  echo "check-domains.sh should pass when only guardguide.de + approved secpal.* hosts are present" >&2
  exit 1
fi

if grep -F 'guardguide' "$workspace/output.txt" | grep -qiv 'out of scope\|governed by\|namespace'; then
  cat "$workspace/output.txt"
  echo "check-domains.sh must not flag guardguide.de as a violation" >&2
  exit 1
fi

# Now confirm an unapproved secpal.* host still fails the gate so the scope
# limit is not a free pass for actual namespace violations.
cat >"$workspace/regression.md" <<'EOF'
# Regression fixture

This file intentionally references an unapproved secpal.xyz host so the
gate has something to fail on.

Bad: https://secpal.xyz
EOF

set +e
(
  cd "$workspace"
  bash scripts/check-domains.sh >output.txt 2>&1
)
exit_code=$?
set -e

if [ "$exit_code" -eq 0 ]; then
  cat "$workspace/output.txt"
  echo "check-domains.sh must still fail when an unapproved secpal.* host is present" >&2
  exit 1
fi

if ! grep -Fq 'secpal.xyz' "$workspace/output.txt"; then
  cat "$workspace/output.txt"
  echo "check-domains.sh must surface the unapproved secpal.xyz host in its output" >&2
  exit 1
fi

echo "tests/check-domains.sh: ok"
