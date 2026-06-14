#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

# Regression test for scripts/check-domains.sh covering SecPal/.github#484
# plus the PR #488 Copilot review findings.
#
# The script is intentionally scoped to enforcing the secpal.* namespace
# split. SecPal-external hosts (e.g. guardguide.de) are governed by their
# own repository policy guards and must NOT be flagged here. This test
# locks in the following guarantees so neither the banner nor any of the
# surrounding documentation can drift back to claiming the gate covers
# "any other" domain:
#
#   1. The banner and the failure-mode Policy block document the scope
#      limit (so the help text and the regex agree).
#   2. The script's top-of-file header comment documents the same scope
#      instead of the legacy "ZERO TOLERANCE for other domains" wording
#      that contradicted the matcher.
#   3. scripts/README.md documents the same intentional scope and does not
#      claim the script only scans tracked files (it greps the working
#      tree, untracked files included) so contributors do not develop the
#      wrong mental model.
#   4. CHANGELOG.md does not contain a literal unapproved secpal.* host
#      such as secpal.xyz, even when describing the regression fixture;
#      such hosts only ever live inside the test's own temporary workspace
#      so the prose cannot accidentally trip the gate after a reword.
#   5. Behaviour matches the documented scope: guardguide.de references in
#      a workspace pass cleanly, while an unapproved secpal.* host still
#      fails the gate.
#   6. The gate skips the gitignored agent scratch directory `.context/` so
#      Polyscope-managed workspaces can stash PR body drafts and other
#      throwaway notes that quote forbidden hosts verbatim without tripping
#      the local gate (CI never sees `.context/` because it is gitignored).
#      Tracked content with the same string still fails so the exclusion is
#      not a free pass (see SecPal/.github#489).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/check-domains.sh"
README="$REPO_ROOT/scripts/README.md"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

if [ ! -f "$SCRIPT" ]; then
  echo "Missing scripts/check-domains.sh" >&2
  exit 1
fi

if [ ! -f "$README" ]; then
  echo "Missing scripts/README.md" >&2
  exit 1
fi

if [ ! -f "$CHANGELOG" ]; then
  echo "Missing CHANGELOG.md" >&2
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

# 2b. Header comment documents the scope and does not contradict it
# (PR #488 review thread on scripts/check-domains.sh:7).
if ! grep -Fq '# Scope: enforces the secpal.* namespace split only' "$SCRIPT"; then
  echo "scripts/check-domains.sh header comment must declare the secpal.* namespace scope" >&2
  exit 1
fi

if grep -Fq 'ZERO TOLERANCE for other domains' "$SCRIPT"; then
  echo "scripts/check-domains.sh header comment must not reuse the contradicting 'ZERO TOLERANCE for other domains' wording" >&2
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

# 3b. README accurately describes the scan target (working tree, not just
# tracked files) so contributors do not develop the wrong mental model
# (PR #488 review thread on scripts/README.md:20).
if grep -Fq 'scans tracked text files' "$README"; then
  echo "scripts/README.md must not claim check-domains.sh scans only tracked files; it greps the working tree" >&2
  exit 1
fi

if ! grep -Fq 'working tree' "$README"; then
  echo "scripts/README.md must describe the scan target as the working tree" >&2
  exit 1
fi

# 3c. README documents the `.context/` exclusion so contributors discover
# that the gate intentionally skips the gitignored agent scratch directory
# (SecPal/.github#489).
if ! grep -Fq '.context' "$README"; then
  echo "scripts/README.md must document the .context/ exclusion (see SecPal/.github#489)" >&2
  exit 1
fi

# 4. CHANGELOG.md must not contain a literal unapproved secpal.* host even
# in its prose. The regression fixture lives in the test's own temporary
# workspace so the changelog entry cannot accidentally trip the gate after
# a reword (PR #488 review thread on CHANGELOG.md:21).
if grep -Fq 'secpal.xyz' "$CHANGELOG"; then
  echo "CHANGELOG.md must not contain literal unapproved secpal.* hosts (e.g. secpal.xyz); keep such fixtures inside tests/check-domains.sh" >&2
  exit 1
fi

# 5. Behavioural check: guardguide.de references pass, unapproved secpal.* fails.
workspace=""
ctx_workspace=""
cleanup() { rm -rf "${workspace:-}" "${ctx_workspace:-}"; }
trap cleanup EXIT

workspace="$(mktemp -d "${TMPDIR:-/tmp}/check-domains.XXXXXX")"

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

set +e
(
  cd "$workspace"
  bash scripts/check-domains.sh >output.txt 2>&1
)
_rc=$?
set -e

if [ "$_rc" -ne 0 ] || ! grep -Fq 'Domain Policy Check PASSED' "$workspace/output.txt"; then
  cat "$workspace/output.txt"
  echo "check-domains.sh should pass when only guardguide.de + approved secpal.* hosts are present" >&2
  exit 1
fi

if grep -F 'guardguide' "$workspace/output.txt" | grep -qiEv 'out of scope|governed by|namespace'; then
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

# 6. Behavioural check: the gitignored agent scratch directory `.context/`
# must be skipped (positive case) while tracked content with the same
# string still fails (negative case). Use a fresh workspace so the previous
# regression.md fixture cannot mask either result.
ctx_workspace="$(mktemp -d "${TMPDIR:-/tmp}/check-domains-context.XXXXXX")"

mkdir -p "$ctx_workspace/scripts" "$ctx_workspace/.context"
cp "$SCRIPT" "$ctx_workspace/scripts/check-domains.sh"

cat >"$ctx_workspace/.context/notes.md" <<'EOF'
# Agent scratch notes

PR body draft mentioning the unapproved secpal.xyz fixture host so the
gate has a reason to fail if .context/ is not excluded.
EOF

set +e
(
  cd "$ctx_workspace"
  bash scripts/check-domains.sh >output.txt 2>&1
)
_ctx_rc=$?
set -e

if [ "$_ctx_rc" -ne 0 ] || ! grep -Fq 'Domain Policy Check PASSED' "$ctx_workspace/output.txt"; then
  cat "$ctx_workspace/output.txt"
  echo "check-domains.sh must ignore .context/ content (see SecPal/.github#489)" >&2
  exit 1
fi

if grep -Fq '.context/notes.md' "$ctx_workspace/output.txt"; then
  cat "$ctx_workspace/output.txt"
  echo "check-domains.sh must not surface .context/ files even in passing output" >&2
  exit 1
fi

# Remove .context/ before the negative case so only the tracked-equivalent
# regression.md is present. This isolates the two subcases: the positive run
# proved that .context/ alone is ignored; the negative run must prove that a
# non-.context/ violation is still caught — without .context/notes.md
# providing a false failure path if the exclusion were broken.
rm -rf "$ctx_workspace/.context"

# Negative case: the same string in a tracked-equivalent location at the
# workspace root must still fail the gate so the exclusion cannot be
# mistaken for a blanket free pass.
cat >"$ctx_workspace/regression.md" <<'EOF'
# Regression fixture

Tracked-equivalent content still references the unapproved secpal.xyz
host so the gate must still fail when the violation lives outside
.context/.
EOF

set +e
(
  cd "$ctx_workspace"
  bash scripts/check-domains.sh >output.txt 2>&1
)
ctx_exit_code=$?
set -e

if [ "$ctx_exit_code" -eq 0 ]; then
  cat "$ctx_workspace/output.txt"
  echo "check-domains.sh must still fail on tracked-equivalent content even when .context/ is excluded" >&2
  exit 1
fi

if ! grep -Fq 'regression.md' "$ctx_workspace/output.txt"; then
  cat "$ctx_workspace/output.txt"
  echo "check-domains.sh must surface the tracked-equivalent regression fixture in its output" >&2
  exit 1
fi

echo "tests/check-domains.sh: ok"
