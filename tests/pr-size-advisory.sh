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

append_lines() {
  local count="$1"
  local target="$2"

  awk -v count="$count" 'BEGIN { for (line = 1; line <= count; line++) print "appended " line }' >>"$target"
}

make_prefixed_lines() {
  local count="$1"
  local prefix="$2"
  local target="$3"

  awk -v count="$count" -v prefix="$prefix" \
    'BEGIN { for (line = 1; line <= count; line++) print prefix " " line }' >"$target"
}

create_git_fixture() {
  local repository="$1"
  local exclude_patterns="${2-}"
  local seed_renames="${3-false}"

  mkdir -p "$repository/source" "$repository/generated" "$repository/vendor"
  if [ -n "$exclude_patterns" ]; then
    printf '%s\n' "$exclude_patterns" >"$repository/.preflight-exclude"
  else
    cat >"$repository/.preflight-exclude" <<'EOF'
# Keep generated changes out of the reviewability report.
generated/
EOF
  fi
  make_lines 4 "$repository/source/existing.txt"
  if [ "$seed_renames" = "true" ]; then
    make_prefixed_lines 700 "generated source" "$repository/generated/old-name.txt"
    make_prefixed_lines 700 "included source" "$repository/source/to-generated.txt"
  fi

  (
    cd "$repository"
    git init --quiet --initial-branch=main
    git config user.name "SecPal Test"
    git config user.email "test@secpal.dev"
    git config commit.gpgSign false
    git add .preflight-exclude source/existing.txt
    if [ "$seed_renames" = "true" ]; then
      git add generated/old-name.txt source/to-generated.txt
    fi
    git commit --quiet -m "test: seed size fixture"
    git remote add origin "$repository"
    git update-ref refs/remotes/origin/main HEAD
    git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
    git checkout --quiet -b test-branch
  )
}

create_preflight_fixture() {
  local repository="$1"
  local exclude_patterns="${2-}"
  local seed_renames="${3-false}"

  create_git_fixture "$repository" "$exclude_patterns" "$seed_renames"
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
  local stdout="$2"
  local stderr="$3"

  set +e
  (
    cd "$repository"
    PATH="$repository/bin:/usr/bin:/bin" bash scripts/preflight.sh
  ) >"$stdout" 2>"$stderr"
  fixture_status=$?
  set -e
}

large_local_repo="$workspace/local-large"
large_local_stdout="$workspace/local-large.stdout"
large_local_stderr="$workspace/local-large.stderr"
create_preflight_fixture "$large_local_repo"
make_lines 597 "$large_local_repo/source/large.txt"
(
  cd "$large_local_repo"
  git rm --quiet source/existing.txt
  git add source/large.txt
  git commit --quiet -m "test: create 601-line change"
)
run_preflight_fixture "$large_local_repo" "$large_local_stdout" "$large_local_stderr"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed when the advisory threshold is exceeded (status $fixture_status)"
fi
assert_contains \
  "$large_local_stderr" \
  "PR size: 601 changed lines (597 insertions, 4 deletions; advisory threshold: 600)" \
  "local preflight must report insertion, deletion, total, and advisory-threshold counts above the threshold"
assert_contains \
  "$large_local_stderr" \
  "WARNING: PR size advisory threshold exceeded" \
  "local preflight must emit a visible advisory warning above the threshold"
if [ -e "$large_local_repo/.preflight-allow-large-pr" ]; then
  record_failure "local advisory reporting must not require an override file"
fi

threshold_local_repo="$workspace/local-threshold"
threshold_local_stdout="$workspace/local-threshold.stdout"
threshold_local_stderr="$workspace/local-threshold.stderr"
create_preflight_fixture "$threshold_local_repo"
make_lines 600 "$threshold_local_repo/source/threshold.txt"
(
  cd "$threshold_local_repo"
  git add source/threshold.txt
  git commit --quiet -m "test: create threshold-sized change"
)
run_preflight_fixture "$threshold_local_repo" "$threshold_local_stdout" "$threshold_local_stderr"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed at the advisory threshold (status $fixture_status)"
fi
assert_contains \
  "$threshold_local_stdout" \
  "Preflight OK · PR size: 600 changed lines (600 insertions, 0 deletions; advisory threshold: 600)" \
  "local preflight must report normal success and complete counts at the threshold"
assert_not_contains \
  "$threshold_local_stderr" \
  "WARNING: PR size advisory threshold exceeded" \
  "local preflight must not warn at the advisory threshold"

excluded_local_repo="$workspace/local-excluded"
excluded_local_stdout="$workspace/local-excluded.stdout"
excluded_local_stderr="$workspace/local-excluded.stderr"
create_preflight_fixture "$excluded_local_repo"
make_lines 700 "$excluded_local_repo/generated/client.txt"
make_lines 5 "$excluded_local_repo/source/included.txt"
(
  cd "$excluded_local_repo"
  git add generated/client.txt source/included.txt
  git commit --quiet -m "test: create excluded change"
)
run_preflight_fixture "$excluded_local_repo" "$excluded_local_stdout" "$excluded_local_stderr"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed when exclusions reduce the report below the threshold (status $fixture_status)"
fi
assert_contains \
  "$excluded_local_stdout" \
  "Preflight OK · PR size: 5 changed lines (5 insertions, 0 deletions; advisory threshold: 600)" \
  "local preflight must preserve .preflight-exclude behavior"
assert_not_contains \
  "$excluded_local_stderr" \
  "WARNING: PR size advisory threshold exceeded" \
  "excluded changes must not trigger the advisory warning"

path_exclusion_local_repo="$workspace/local-path-exclusions"
path_exclusion_local_stdout="$workspace/local-path-exclusions.stdout"
path_exclusion_local_stderr="$workspace/local-path-exclusions.stderr"
create_preflight_fixture \
  "$path_exclusion_local_repo" \
  $'^LICENSES/.*\\.txt$\npackage-lock.json\n^generated/' \
  true
mkdir -p \
  "$path_exclusion_local_repo/LICENSES" \
  "$path_exclusion_local_repo/docs/LICENSES" \
  "$path_exclusion_local_repo/assets" \
  "$path_exclusion_local_repo/custom" \
  "$path_exclusion_local_repo/lockfiles" \
  "$path_exclusion_local_repo/prefix LICENSES"
make_lines 601 "$path_exclusion_local_repo/LICENSES/license.txt"
make_lines 602 "$path_exclusion_local_repo/LICENSES/über.txt"
make_lines 603 "$path_exclusion_local_repo/"$'LICENSES/tab\tname.txt'
make_lines 604 "$path_exclusion_local_repo/"$'LICENSES/line\nname.txt'
make_lines 5 "$path_exclusion_local_repo/docs/LICENSES/license.txt"
make_lines 6 "$path_exclusion_local_repo/prefix LICENSES/notes.txt"
make_lines 700 "$path_exclusion_local_repo/lockfiles/package-lock.json"
make_lines 500 "$path_exclusion_local_repo/custom/ignored.txt"
printf 'binary\0content\n' >"$path_exclusion_local_repo/assets/image.bin"
(
  cd "$path_exclusion_local_repo"
  mv generated/old-name.txt source/from-generated.txt
  append_lines 20 source/from-generated.txt
  mv source/to-generated.txt generated/from-source.txt
  append_lines 21 generated/from-source.txt
  git add -- LICENSES/license.txt 'LICENSES/über.txt' $'LICENSES/tab\tname.txt' \
    $'LICENSES/line\nname.txt' docs/LICENSES/license.txt 'prefix LICENSES/notes.txt' \
    lockfiles/package-lock.json custom/ignored.txt assets/image.bin \
    generated/old-name.txt source/from-generated.txt \
    source/to-generated.txt generated/from-source.txt
  git commit --quiet -m "test: cover path-based exclusions"
)
if ! git -C "$path_exclusion_local_repo" diff --numstat origin/main..HEAD | grep -Fqx -- $'-\t-\tassets/image.bin'; then
  record_failure "path-exclusion fixture must contain a binary --numstat record"
fi
if ! git -C "$path_exclusion_local_repo" diff --numstat origin/main..HEAD | grep -Fqx -- $'20\t0\tgenerated/old-name.txt => source/from-generated.txt'; then
  record_failure "path-exclusion fixture must contain a detected rename from excluded to included"
fi
if ! git -C "$path_exclusion_local_repo" diff --numstat origin/main..HEAD | grep -Fqx -- $'21\t0\tsource/to-generated.txt => generated/from-source.txt'; then
  record_failure "path-exclusion fixture must contain a detected rename from included to excluded"
fi
run_preflight_fixture \
  "$path_exclusion_local_repo" \
  "$path_exclusion_local_stdout" \
  "$path_exclusion_local_stderr"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must support anchored path exclusions (status $fixture_status)"
fi
assert_contains \
  "$path_exclusion_local_stdout" \
  "Preflight OK · PR size: 531 changed lines (531 insertions, 0 deletions; advisory threshold: 600)" \
  "local preflight must filter raw paths and apply rename exclusions to destination paths"
assert_not_contains \
  "$path_exclusion_local_stderr" \
  "WARNING: PR size advisory threshold exceeded" \
  "path exclusions must prevent the local advisory warning"

all_excluded_local_repo="$workspace/local-all-excluded"
all_excluded_local_stdout="$workspace/local-all-excluded.stdout"
all_excluded_local_stderr="$workspace/local-all-excluded.stderr"
create_preflight_fixture "$all_excluded_local_repo"
make_lines 700 "$all_excluded_local_repo/generated/client.txt"
(
  cd "$all_excluded_local_repo"
  git add generated/client.txt
  git commit --quiet -m "test: create fully excluded change"
)
run_preflight_fixture \
  "$all_excluded_local_repo" \
  "$all_excluded_local_stdout" \
  "$all_excluded_local_stderr"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must succeed when every changed file is excluded (status $fixture_status)"
fi
assert_contains \
  "$all_excluded_local_stderr" \
  "All changed files are excluded" \
  "local preflight must emit the all-excluded advisory on stderr"
assert_not_contains \
  "$all_excluded_local_stdout" \
  "All changed files are excluded" \
  "local preflight must keep the all-excluded advisory out of stdout"
assert_contains \
  "$all_excluded_local_stdout" \
  "Preflight OK · PR size: 0 changed lines (0 insertions, 0 deletions; advisory threshold: 600)" \
  "local preflight must report zero counts normally when every changed file is excluded"

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
assert_contains \
  "$CALLER_WORKFLOW" \
  "uses: ./.github/workflows/reusable-pr-size.yml" \
  "the same-repository caller must resolve the changed reusable workflow from the same revision"
assert_not_contains \
  "$CALLER_WORKFLOW" \
  "uses: SecPal/.github/.github/workflows/reusable-pr-size.yml@main" \
  "the same-repository caller must not combine branch permissions with the reusable workflow from main"
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
  "::error::PR too large" \
  "the reusable workflow must not emit the removed hard-failure error"
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

path_exclusion_workflow_output="$workspace/workflow-path-exclusions.out"
run_workflow_fixture \
  "$path_exclusion_local_repo" \
  "$path_exclusion_workflow_output" \
  ""
if [ "$fixture_status" -ne 0 ]; then
  record_failure "reusable workflow shell must match local path exclusions (status $fixture_status)"
fi
assert_contains \
  "$path_exclusion_workflow_output" \
  "PR size: 531 changed lines (531 insertions, 0 deletions; advisory threshold: 600)" \
  "local and hosted fixtures must report identical counts after repository exclusions"

path_exclusion_custom_workflow_output="$workspace/workflow-path-custom-exclusions.out"
run_workflow_fixture \
  "$path_exclusion_local_repo" \
  "$path_exclusion_custom_workflow_output" \
  '^custom/.*\.txt$'
if [ "$fixture_status" -ne 0 ]; then
  record_failure "reusable workflow shell must support anchored path exclusions (status $fixture_status)"
fi
assert_contains \
  "$path_exclusion_custom_workflow_output" \
  "PR size: 31 changed lines (31 insertions, 0 deletions; advisory threshold: 600)" \
  "reusable workflow must apply repository and custom exclusions to paths only"
assert_not_contains \
  "$path_exclusion_custom_workflow_output" \
  "::warning::PR size advisory threshold exceeded" \
  "path exclusions must prevent the hosted advisory warning"

local_path_counts=$(sed -n 's/.*\(PR size: [0-9][0-9]* changed lines.*\)/\1/p' "$path_exclusion_local_stdout")
hosted_path_counts=$(sed -n 's/.*\(PR size: [0-9][0-9]* changed lines.*\)/\1/p' "$path_exclusion_workflow_output")
if [ "$local_path_counts" != "PR size: 531 changed lines (531 insertions, 0 deletions; advisory threshold: 600)" ]; then
  record_failure "local path-exclusion fixture must retain included paths and rename destinations"
fi
if [ "$hosted_path_counts" != "$local_path_counts" ]; then
  record_failure "hosted path-exclusion fixture must retain nested and spaced paths"
fi

invalid_workflow_repo="$workspace/workflow-invalid-exclusion"
invalid_workflow_output="$workspace/workflow-invalid-exclusion.out"
invalid_local_stdout="$workspace/local-invalid-exclusion.stdout"
invalid_local_stderr="$workspace/local-invalid-exclusion.stderr"
create_preflight_fixture "$invalid_workflow_repo"
make_lines 601 "$invalid_workflow_repo/source/large.txt"
printf '[\n' >"$invalid_workflow_repo/.preflight-exclude"
(
  cd "$invalid_workflow_repo"
  git add source/large.txt .preflight-exclude
  git commit --quiet -m "test: create hosted invalid exclusion"
)
run_preflight_fixture \
  "$invalid_workflow_repo" \
  "$invalid_local_stdout" \
  "$invalid_local_stderr"
if [ "$fixture_status" -ne 0 ]; then
  record_failure "local preflight must safely ignore invalid exclusions (status $fixture_status)"
fi
assert_contains \
  "$invalid_local_stderr" \
  ".preflight-exclude contains invalid regex pattern" \
  "local preflight must report an invalid exclusion"
assert_contains \
  "$invalid_local_stderr" \
  "PR size: 604 changed lines" \
  "an invalid exclusion must not hide a large local diff"
run_workflow_fixture "$invalid_workflow_repo" "$invalid_workflow_output" ""
if [ "$fixture_status" -ne 0 ]; then
  record_failure "reusable workflow shell must safely ignore invalid exclusions (status $fixture_status)"
fi
assert_contains \
  "$invalid_workflow_output" \
  ".preflight-exclude contains invalid regex pattern(s)" \
  "reusable workflow must report an invalid exclusion"
assert_contains \
  "$invalid_workflow_output" \
  "PR size: 604 changed lines" \
  "an invalid exclusion must not hide a large hosted-workflow diff"

invalid_custom_workflow_output="$workspace/workflow-invalid-custom-exclusion.out"
run_workflow_fixture "$large_workflow_repo" "$invalid_custom_workflow_output" "["
if [ "$fixture_status" -ne 0 ]; then
  record_failure "reusable workflow shell must safely ignore invalid custom exclusions (status $fixture_status)"
fi
assert_contains \
  "$invalid_custom_workflow_output" \
  "Custom exclude patterns contain invalid regex" \
  "reusable workflow must report an invalid custom exclusion"
assert_contains \
  "$invalid_custom_workflow_output" \
  "PR size: 601 changed lines" \
  "an invalid custom exclusion must not hide a large hosted-workflow diff"

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
