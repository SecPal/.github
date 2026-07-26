#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PREFLIGHT_SCRIPT="$REPO_ROOT/scripts/preflight.sh"
CALLER_WORKFLOW="$REPO_ROOT/.github/workflows/pr-size.yml"
REUSABLE_WORKFLOW="$REPO_ROOT/.github/workflows/reusable-pr-size.yml"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/pr-size-advisory.XXXXXX")"
trap 'rm -rf -- "$workspace"' EXIT

failures=0

record_failure() {
  echo "FAIL: $*" >&2
  failures=$((failures + 1))
}

assert_contains() {
  local file="$1"
  local expected="$2"
  local message="$3"

  if ! grep -Fq -- "$expected" "$file"; then
    record_failure "$message"
  fi
}

assert_not_contains() {
  local file="$1"
  local forbidden="$2"
  local message="$3"

  if grep -Fq -- "$forbidden" "$file"; then
    record_failure "$message"
  fi
}

make_lines() {
  local count="$1"
  local target="$2"

  awk -v count="$count" 'BEGIN { for (line = 1; line <= count; line++) print "line " line }' >"$target"
}

create_git_fixture() {
  local repository="$1"

  mkdir -p "$repository/source" "$repository/generated" "$repository/vendor"
  cat >"$repository/.preflight-exclude" <<'EOF'
# Keep generated changes out of the reviewability report.
generated/
EOF
  make_lines 4 "$repository/source/existing.txt"

  (
    cd "$repository"
    git init --quiet --initial-branch=main
    git config user.name "SecPal Test"
    git config user.email "test@secpal.dev"
    git config commit.gpgSign false
    git add .preflight-exclude source/existing.txt
    git commit --quiet -m "test: seed size fixture"
    git remote add origin "$repository"
    git update-ref refs/remotes/origin/main HEAD
    git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
    git checkout --quiet -b test-branch
  )
}

create_preflight_fixture() {
  local repository="$1"

  create_git_fixture "$repository"
  mkdir -p "$repository/scripts" "$repository/bin"
  cp "$PREFLIGHT_SCRIPT" "$repository/scripts/preflight.sh"

  cat >"$repository/bin/npx" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  cat >"$repository/bin/reuse" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$repository/bin/npx" "$repository/bin/reuse"
}

run_preflight_fixture() {
  local repository="$1"
  local output="$2"

  set +e
  (
    cd "$repository"
    PATH="$repository/bin:/usr/bin:/bin" bash scripts/preflight.sh
  ) >"$output" 2>&1
  fixture_status=$?
  set -e
}

large_local_repo="$workspace/local-large"
large_local_output="$workspace/local-large.out"
create_preflight_fixture "$large_local_repo"
make_lines 597 "$large_local_repo/source/large.txt"
(
  cd "$large_local_repo"
  git rm --quiet source/existing.txt
  git add source/large.txt
  git commit --quiet -m "test: create 601-line change"
)
run_preflight_fixture "$large_local_repo" "$large_local_output"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed when the advisory threshold is exceeded (status $fixture_status)"
fi
assert_contains \
  "$large_local_output" \
  "PR size: 601 changed lines (597 insertions, 4 deletions; advisory threshold: 600)" \
  "local preflight must report insertion, deletion, total, and advisory-threshold counts above the threshold"
assert_contains \
  "$large_local_output" \
  "WARNING: PR size advisory threshold exceeded" \
  "local preflight must emit a visible advisory warning above the threshold"
if [ -e "$large_local_repo/.preflight-allow-large-pr" ]; then
  record_failure "local advisory reporting must not require an override file"
fi

threshold_local_repo="$workspace/local-threshold"
threshold_local_output="$workspace/local-threshold.out"
create_preflight_fixture "$threshold_local_repo"
make_lines 600 "$threshold_local_repo/source/threshold.txt"
(
  cd "$threshold_local_repo"
  git add source/threshold.txt
  git commit --quiet -m "test: create threshold-sized change"
)
run_preflight_fixture "$threshold_local_repo" "$threshold_local_output"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed at the advisory threshold (status $fixture_status)"
fi
assert_contains \
  "$threshold_local_output" \
  "Preflight OK · PR size: 600 changed lines (600 insertions, 0 deletions; advisory threshold: 600)" \
  "local preflight must report normal success and complete counts at the threshold"
assert_not_contains \
  "$threshold_local_output" \
  "WARNING: PR size advisory threshold exceeded" \
  "local preflight must not warn at the advisory threshold"

excluded_local_repo="$workspace/local-excluded"
excluded_local_output="$workspace/local-excluded.out"
create_preflight_fixture "$excluded_local_repo"
make_lines 700 "$excluded_local_repo/generated/client.txt"
make_lines 5 "$excluded_local_repo/source/included.txt"
(
  cd "$excluded_local_repo"
  git add generated/client.txt source/included.txt
  git commit --quiet -m "test: create excluded change"
)
run_preflight_fixture "$excluded_local_repo" "$excluded_local_output"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed when exclusions reduce the report below the threshold (status $fixture_status)"
fi
assert_contains \
  "$excluded_local_output" \
  "Preflight OK · PR size: 5 changed lines (5 insertions, 0 deletions; advisory threshold: 600)" \
  "local preflight must preserve .preflight-exclude behavior"
assert_not_contains \
  "$excluded_local_output" \
  "WARNING: PR size advisory threshold exceeded" \
  "excluded changes must not trigger the advisory warning"

assert_contains \
  "$REUSABLE_WORKFLOW" \
  'description: "Advisory changed-line threshold for reviewability"' \
  "the reusable max-lines input must describe an advisory threshold"
assert_contains \
  "$REUSABLE_WORKFLOW" \
  "default: 600" \
  "the reusable advisory threshold must remain configurable with a 600-line default"
assert_contains \
  "$REUSABLE_WORKFLOW" \
  "ADVISORY_THRESHOLD: \${{ inputs.max-lines }}" \
  "the reusable workflow must pass the configured advisory threshold to its shell"
assert_contains \
  "$REUSABLE_WORKFLOW" \
  "CUSTOM_EXCLUDE_PATTERNS: \${{ inputs.exclude-patterns }}" \
  "custom exclusions must remain supported without interpolating them into shell source"
assert_not_contains \
  "$REUSABLE_WORKFLOW" \
  "pull-requests: read" \
  "the reusable workflow must not retain pull-request permission solely for a size override"
assert_not_contains \
  "$CALLER_WORKFLOW" \
  "pull-requests: read" \
  "the caller must not retain pull-request permission solely for a size override"
assert_not_contains \
  "$REUSABLE_WORKFLOW" \
  "GH_TOKEN" \
  "the reusable workflow must not require GH_TOKEN for advisory size reporting"
assert_not_contains \
  "$REUSABLE_WORKFLOW" \
  "PR_NUMBER" \
  "the reusable workflow must not require PR_NUMBER for advisory size reporting"
assert_not_contains \
  "$REUSABLE_WORKFLOW" \
  "gh pr view" \
  "the reusable workflow must not query pull-request labels"
assert_not_contains \
  "$REUSABLE_WORKFLOW" \
  "large-pr-approved" \
  "the reusable workflow must not implement a label override"
assert_not_contains \
  "$REUSABLE_WORKFLOW" \
  "exit 1" \
  "the reusable workflow must not fail solely because the advisory threshold was exceeded"
assert_contains \
  "$CALLER_WORKFLOW" \
  "name: PR Size Check" \
  "the caller workflow name must remain stable"
assert_contains \
  "$CALLER_WORKFLOW" \
  "  pr-size:" \
  "the caller job identifier must remain stable"
assert_contains \
  "$CALLER_WORKFLOW" \
  "name: Check PR Size" \
  "the caller job name must remain stable"
assert_contains \
  "$REUSABLE_WORKFLOW" \
  "name: Reusable PR Size Check" \
  "the reusable workflow name must remain stable"
assert_contains \
  "$REUSABLE_WORKFLOW" \
  "  pr-size:" \
  "the reusable job identifier must remain stable"
assert_contains \
  "$REUSABLE_WORKFLOW" \
  "name: Check PR Size" \
  "the reusable job name must remain stable"

workflow_script="$workspace/reusable-pr-size-step.sh"
awk '
  /^      - name: Check PR size$/ { in_step = 1; next }
  in_step && /^        run: \|$/ { capture = 1; next }
  capture && /^      - name:/ { exit }
  capture && /^          / { print substr($0, 11) }
' "$REUSABLE_WORKFLOW" >"$workflow_script"

run_workflow_fixture() {
  local repository="$1"
  local output="$2"
  local custom_patterns="$3"

  set +e
  (
    cd "$repository"
    BASE_REF=main \
      ADVISORY_THRESHOLD=600 \
      CUSTOM_EXCLUDE_PATTERNS="$custom_patterns" \
      bash -euo pipefail "$workflow_script"
  ) >"$output" 2>&1
  fixture_status=$?
  set -e
}

large_workflow_repo="$workspace/workflow-large"
large_workflow_output="$workspace/workflow-large.out"
create_git_fixture "$large_workflow_repo"
make_lines 601 "$large_workflow_repo/source/large.txt"
(
  cd "$large_workflow_repo"
  git add source/large.txt
  git commit --quiet -m "test: create hosted advisory change"
)
run_workflow_fixture "$large_workflow_repo" "$large_workflow_output" ""
if [ "$fixture_status" -ne 0 ]; then
  record_failure "reusable workflow shell must succeed above the advisory threshold (status $fixture_status)"
fi
assert_contains \
  "$large_workflow_output" \
  "PR size: 601 changed lines (601 insertions, 0 deletions; advisory threshold: 600)" \
  "reusable workflow must report insertion, deletion, total, and threshold counts"
assert_contains \
  "$large_workflow_output" \
  "::warning::PR size advisory threshold exceeded" \
  "reusable workflow must emit a GitHub warning above the threshold"

excluded_workflow_repo="$workspace/workflow-excluded"
excluded_workflow_output="$workspace/workflow-excluded.out"
create_git_fixture "$excluded_workflow_repo"
make_lines 700 "$excluded_workflow_repo/generated/client.txt"
make_lines 800 "$excluded_workflow_repo/vendor/bundle.txt"
make_lines 5 "$excluded_workflow_repo/source/included.txt"
(
  cd "$excluded_workflow_repo"
  git add generated/client.txt vendor/bundle.txt source/included.txt
  git commit --quiet -m "test: create hosted excluded change"
)
run_workflow_fixture "$excluded_workflow_repo" "$excluded_workflow_output" "vendor/"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "reusable workflow shell must preserve repository and custom exclusions (status $fixture_status)"
fi
assert_contains \
  "$excluded_workflow_output" \
  "PR size: 5 changed lines (5 insertions, 0 deletions; advisory threshold: 600)" \
  "reusable workflow must apply .preflight-exclude and custom exclusions"
assert_not_contains \
  "$excluded_workflow_output" \
  "::warning::PR size advisory threshold exceeded" \
  "hosted excluded changes must not trigger the advisory warning"

policy_files=(
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/CONTRIBUTING.md"
  "$REPO_ROOT/docs/labels.md"
  "$REPO_ROOT/.github/ISSUE_TEMPLATE/sub-issue.yml"
  "$REPO_ROOT/.preflight-exclude"
)

for policy_file in "${policy_files[@]}"; do
  assert_not_contains \
    "$policy_file" \
    ".preflight-allow-large-pr" \
    "policy documentation must not instruct contributors to use a local size override: ${policy_file#"$REPO_ROOT"/}"
  assert_not_contains \
    "$policy_file" \
    "large-pr-approved" \
    "policy documentation must not instruct contributors to use a label size override: ${policy_file#"$REPO_ROOT"/}"
done

if grep -Eni 'PR Size Limit|Maximum allowed: 600|600-line limit|≤ 600 changed lines' \
  "${policy_files[@]}" >/dev/null; then
  record_failure "policy documentation must not describe 600 lines as a hard maximum"
fi
assert_contains \
  "$REPO_ROOT/CONTRIBUTING.md" \
  "600 changed lines is a reviewability recommendation" \
  "the contribution guide must describe 600 lines as a reviewability recommendation"
assert_contains \
  "$REPO_ROOT/CONTRIBUTING.md" \
  "Every PR must address exactly ONE logical topic." \
  "the strict one-PR-one-topic rule must remain in force"
assert_contains \
  "$REPO_ROOT/README.md" \
  "600-line advisory threshold" \
  "the repository README must describe advisory PR-size reporting"
assert_not_contains \
  "$REPO_ROOT/scripts/sync-labels.sh" \
  "large-pr-approved" \
  "the obsolete size-override label must be removed from managed label definitions"
assert_contains \
  "$REPO_ROOT/CHANGELOG.md" \
  "Make Pull Request Size Reporting Advisory" \
  "the governance changelog must record the advisory reporting change"

if [ "$failures" -ne 0 ]; then
  echo "tests/pr-size-advisory.sh: $failures regression assertion(s) failed." >&2
  exit 1
fi

echo "tests/pr-size-advisory.sh: advisory PR-size reporting verified."
