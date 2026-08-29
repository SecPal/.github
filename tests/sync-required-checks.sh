#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_SCRIPT="$REPO_ROOT/scripts/sync-required-checks.sh"
CODECOV_SCRIPT="$REPO_ROOT/scripts/configure-codecov-optional.sh"
SHELL_BIN="${BASH:-$(command -v bash)}"

if ! command -v jq >/dev/null 2>&1; then
  echo "Missing required command: jq" >&2
  echo "Install jq before running tests/sync-required-checks.sh (preflight wires this test in)." >&2
  exit 2
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sync-required-checks.XXXXXX")"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

assert_payload_has_context() {
  local payload="$1"
  local expected="$2"

  if ! jq -e --arg expected "$expected" '.strict == false and (.checks | any(.context == $expected))' >/dev/null <<<"$payload"; then
    echo "Expected payload to require '$expected'" >&2
    echo "$payload" >&2
    exit 1
  fi
}

assert_payload_contexts_equal() {
  local payload="$1"
  local expected="$2"

  if ! jq -e --argjson expected "$expected" '
    .strict == false and
    (.checks | length) == ($expected | length) and
    ([.checks[].context] | length) == ([.checks[].context] | unique | length) and
    ($expected | length) == ($expected | unique | length) and
    ([.checks[].context] | sort) == ($expected | sort) and
    all(.checks[]; .app_id == -1)
  ' >/dev/null <<<"$payload"; then
    echo "Payload did not contain exactly the expected required checks" >&2
    echo "$payload" >&2
    exit 1
  fi
}

assert_review_payload_exact() {
  local payload="$1"

  if ! jq -e '. == {required_approving_review_count: 0}' >/dev/null <<<"$payload"; then
    echo "Review payload must contain only required_approving_review_count=0" >&2
    echo "$payload" >&2
    exit 1
  fi
}

duplicate_payload='{
  "strict": false,
  "checks": [
    {"context": "duplicate", "app_id": -1},
    {"context": "duplicate", "app_id": -1}
  ]
}'
duplicate_contexts='["duplicate", "duplicate"]'
if (assert_payload_contexts_equal "$duplicate_payload" "$duplicate_contexts") >/dev/null 2>&1; then
  echo "Exact payload assertion must reject duplicate payload and expected contexts" >&2
  exit 1
fi

if [[ ! -x "$SYNC_SCRIPT" ]]; then
  echo "Expected executable sync script at $SYNC_SCRIPT" >&2
  exit 1
fi

if grep -Fq 'XXXXXX.json' "$SYNC_SCRIPT"; then
  echo "Sync script uses a BSD-incompatible mktemp template with a suffix after the X placeholder." >&2
  exit 1
fi

# shellcheck disable=SC2016
if ! grep -Fq 'sync-required-checks.${repo//[^A-Za-z0-9]/_}.json.XXXXXX' "$SYNC_SCRIPT"; then
  echo "Sync script must use a portable mktemp template whose X placeholder is at the end." >&2
  exit 1
fi

EXPECTED_CONTEXTS_JSON='{
  ".github": [
    "Check REUSE Compliance",
    "Check License Compatibility",
    "Check Code Formatting",
    "Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "conflict-markers / Detect Git Conflict Markers",
    "Lint GitHub Actions Workflows",
    "CodeQL",
    "Validate PR Evidence",
    "Validate PR Title And Body Language",
    "Validate Signed PR Commits",
    "Work-Graph PR Advisory"
  ],
  "GuardGuide": [
    "check-conflicts / Detect Git Conflict Markers",
    "Check PR Size / Check PR Size",
    "Detect repository manifests",
    "AI Instructions / Validate AI Instructions",
    "Check REUSE Compliance / Check REUSE Compliance",
    "Detect JavaScript manifest",
    "Detect PHP manifest",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Vitest Tests / Build Project",
    "Laravel Pint / Check Code Style",
    "PHPStan / Static Analysis",
    "Pest Tests (PostgreSQL)",
    "Pest Tests (MariaDB)",
    "Analyze with CodeQL (javascript-typescript)"
  ],
  "android": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "check-conflicts / Detect Git Conflict Markers",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Vitest Tests",
    "Analyze with CodeQL (javascript-typescript)",
    "Check PR Size / Check PR Size",
    "AI Instructions / Validate AI Instructions",
    "Markdown Lint / Lint Markdown Files",
    "Certificate transparency"
  ],
  "api": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility",
    "Laravel Pint / Check Code Style",
    "PHPStan / Static Analysis",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "PEST Tests",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions"
  ],
  "guardguide.de": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "ESLint / Run Linter",
    "Astro TypeScript Check / Build Project",
    "Astro Build / Build Project",
    "Check PR Size / Check PR Size",
    "check-conflicts / Detect Git Conflict Markers",
    "Analyze Code (javascript-typescript)",
    "AI Instructions / Validate AI Instructions",
    "Node Tests / Run Tests"
  ],
  "contracts": [
    "REUSE Compliance / Check REUSE Compliance",
    "Prettier Formatting / Check Code Formatting",
    "OpenAPI Lint / Validate OpenAPI Specification",
    "Actionlint / Lint GitHub Actions Workflows",
    "pr-size / Check PR Size",
    "License Compatibility / Check License Compatibility",
    "Markdown Lint / Lint Markdown Files",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions"
  ],
  "frontend": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Analyze with CodeQL (javascript-typescript)",
    "Markdown Lint / Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "Vitest Tests",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions",
    "Strict CSP",
    "Container Contract"
  ],
  "secpal.app": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "ESLint / Run Linter",
    "Astro TypeScript Check / Build Project",
    "Astro Build / Build Project",
    "Check PR Size / Check PR Size",
    "check-conflicts / Detect Git Conflict Markers",
    "Analyze Code (javascript-typescript)",
    "AI Instructions / Validate AI Instructions",
    "Node Tests / Run Tests"
  ]
}'

mapfile -t expected_repositories < <(jq -r 'keys[]' <<<"$EXPECTED_CONTEXTS_JSON")
if [[ "${expected_repositories[*]}" != ".github GuardGuide android api contracts frontend guardguide.de secpal.app" ]]; then
  echo "Expected exact canonical required-check repository inventory" >&2
  exit 1
fi

declare -A payloads
for expected_repo in "${expected_repositories[@]}"; do
  payloads["$expected_repo"]="$(bash "$SYNC_SCRIPT" --repo "$expected_repo" --print-payload)"
  expected_contexts="$(jq -c --arg repo "$expected_repo" '.[$repo]' <<<"$EXPECTED_CONTEXTS_JSON")"
  assert_payload_contexts_equal "${payloads[$expected_repo]}" "$expected_contexts"
done

# The bare 'CodeQL' context is only emitted by .github (its CodeQL Applicability
# Guardrail workflow names its job exactly 'CodeQL'). For every other repo the
# CodeQL workflow names a different job (e.g. 'Analyze with CodeQL' / 'Analyze
# Code'), so requiring bare 'CodeQL' there would block PRs forever.
for non_github_repo in GuardGuide android api contracts frontend guardguide.de secpal.app; do
  non_github_payload="${payloads[$non_github_repo]}"
  if jq -e '.checks | any(.context == "CodeQL")' >/dev/null <<<"$non_github_payload"; then
    echo "Only the '.github' manifest entry may require the bare 'CodeQL' context; other repos must require their actual CodeQL job context (e.g. 'Analyze with CodeQL (<language>)' or 'Analyze Code (<language>)')." >&2
    echo "$non_github_payload" >&2
    exit 1
  fi
done

github_payload="${payloads[.github]}"
assert_payload_has_context "$github_payload" "Validate PR Evidence"
assert_payload_has_context "$github_payload" "Validate PR Title And Body Language"
assert_payload_has_context "$github_payload" "Validate Signed PR Commits"
assert_payload_has_context "$github_payload" "Work-Graph PR Advisory"

for non_github_repo in GuardGuide android api contracts frontend guardguide.de secpal.app; do
  if jq -e '.checks | any(.context == "Work-Graph PR Advisory")' >/dev/null \
    <<<"${payloads[$non_github_repo]}"; then
    echo "The repository-local work-graph gate context must not be invented for unmanaged caller workflows" >&2
    exit 1
  fi
done

for review_repo in .github GuardGuide android; do
  review_payload="$(bash "$SYNC_SCRIPT" --repo "$review_repo" --print-review-payload)"
  assert_review_payload_exact "$review_payload"
done

set +e
unknown_output="$(bash "$SYNC_SCRIPT" --repo does-not-exist --print-payload 2>&1)"
unknown_status=$?
set -e

if [[ $unknown_status -eq 0 ]]; then
  echo "Expected unknown repo lookup to fail" >&2
  exit 1
fi

if [[ "$unknown_output" != *"Unknown repository"* ]]; then
  echo "Expected unknown repo error to mention 'Unknown repository'" >&2
  echo "$unknown_output" >&2
  exit 1
fi

set +e
unknown_review_output="$(bash "$SYNC_SCRIPT" --repo does-not-exist --print-review-payload 2>&1)"
unknown_review_status=$?
set -e

if [[ $unknown_review_status -eq 0 ]]; then
  echo "Expected unknown review repo lookup to fail" >&2
  exit 1
fi

if [[ "$unknown_review_output" != *"Unknown repository"* ]]; then
  echo "Expected unknown review repo error to mention 'Unknown repository'" >&2
  echo "$unknown_review_output" >&2
  exit 1
fi

missing_jq_bin="$TMP_DIR/missing-jq-bin"
mkdir -p "$missing_jq_bin"
ln -s "$(command -v cat)" "$missing_jq_bin/cat"

set +e
missing_jq_output="$(PATH="$missing_jq_bin" "$SHELL_BIN" "$SYNC_SCRIPT" --repo api --print-payload 2>&1)"
missing_jq_status=$?
set -e

if [[ $missing_jq_status -ne 2 ]]; then
  echo "Expected --print-payload without jq to exit with status 2" >&2
  echo "$missing_jq_output" >&2
  exit 1
fi

if [[ "$missing_jq_output" != *"Missing required command: jq"* ]]; then
  echo "Expected --print-payload without jq to report the missing jq dependency" >&2
  echo "$missing_jq_output" >&2
  exit 1
fi

fake_bin="$TMP_DIR/fake-bin"
mkdir -p "$fake_bin"
ln -s "$SHELL_BIN" "$fake_bin/bash"
ln -s "$(command -v cat)" "$fake_bin/cat"
ln -s "$(command -v jq)" "$fake_bin/jq"
ln -s "$(command -v mktemp)" "$fake_bin/mktemp"
ln -s "$(command -v rm)" "$fake_bin/rm"
ln -s "$(command -v sed)" "$fake_bin/sed"

cat >"$fake_bin/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "api" || -z "${2:-}" ]]; then
  echo "Unexpected fake gh invocation: $*" >&2
  exit 2
fi

endpoint="$2"
shift 2
method="GET"
input_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -X)
      method="$2"
      shift 2
      ;;
    --input)
      input_file="$2"
      shift 2
      ;;
    *)
      echo "Unexpected fake gh argument: $1" >&2
      exit 2
      ;;
  esac
done

repo=""
if [[ "$endpoint" =~ ^repos/SecPal/([^/]+)/ ]]; then
  repo="${BASH_REMATCH[1]}"
fi

if [[ "$method" == "GET" ]]; then
  printf 'GET\t%s\t-\n' "$endpoint" >>"$GH_CALL_LOG"
  if [[ -n "${GH_FAIL_GET_REPO:-}" && "$repo" == "$GH_FAIL_GET_REPO" ]]; then
    exit 1
  fi
  state_file="${GH_REQUIRED_STATE_FILE:-}"
  if [[ -n "${GH_STATE_DIR:-}" && -f "$GH_STATE_DIR/$repo.json" ]]; then
    state_file="$GH_STATE_DIR/$repo.json"
  fi
  if [[ -z "$state_file" || ! -f "$state_file" ]]; then
    echo "Missing fake required-status-check state for $repo" >&2
    exit 2
  fi
  jq . "$state_file"
  exit 0
fi

if [[ "$method" != "PATCH" || -z "$input_file" ]]; then
  echo "Expected PATCH with --input for $endpoint" >&2
  exit 2
fi

payload="$(jq -c . "$input_file")"
printf 'PATCH\t%s\t%s\n' "$endpoint" "$payload" >>"$GH_CALL_LOG"

if [[ -n "${GH_FAIL_REPO:-}" && "$repo" == "$GH_FAIL_REPO" ]]; then
  exit 1
fi
if [[ -n "${GH_FAIL_PATCH_REPO:-}" && "$repo" == "$GH_FAIL_PATCH_REPO" ]]; then
  exit 1
fi
EOF
chmod +x "$fake_bin/gh"

state_dir="$TMP_DIR/required-states"
mkdir -p "$state_dir"
for expected_repo in "${expected_repositories[@]}"; do
  jq '.strict = true | .checks |= map(.app_id = null)' \
    <<<"${payloads[$expected_repo]}" >"$state_dir/$expected_repo.json"
done

jq '
  .checks |= map(
    if .context == "Validate PR Evidence" or
       .context == "Validate PR Title And Body Language" or
       .context == "Validate Signed PR Commits"
    then .app_id = 15368
    else .app_id = null
    end
  )
' "$state_dir/.github.json" >"$state_dir/.github.bound.json"
mv "$state_dir/.github.bound.json" "$state_dir/.github.json"

assert_mode_conflict() {
  local label="$1"
  shift
  local call_log="$TMP_DIR/$label-gh.log"
  local output status

  set +e
  output="$(GH_CALL_LOG="$call_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" "$@" 2>&1)"
  status=$?
  set -e

  if [[ $status -ne 2 ]]; then
    echo "Expected conflicting modes '$*' to exit with status 2, got $status" >&2
    echo "$output" >&2
    exit 1
  fi

  if [[ "$output" != *"Multiple operation modes"* ]]; then
    echo "Expected conflicting modes '$*' to report multiple operation modes" >&2
    echo "$output" >&2
    exit 1
  fi

  if [[ -e "$call_log" ]]; then
    echo "Conflicting modes '$*' must fail before invoking gh" >&2
    cat "$call_log" >&2
    exit 1
  fi
}

assert_mode_conflict conflicting-live --apply --apply-review-baseline
assert_mode_conflict conflicting-print --repo api --print-payload --print-review-payload
assert_mode_conflict repeated-mode --apply --apply

unknown_review_apply_log="$TMP_DIR/unknown-review-apply.log"
set +e
unknown_review_apply_output="$(GH_CALL_LOG="$unknown_review_apply_log" PATH="$fake_bin" \
  "$SHELL_BIN" "$SYNC_SCRIPT" --repo does-not-exist --apply-review-baseline 2>&1)"
unknown_review_apply_status=$?
set -e

if [[ $unknown_review_apply_status -eq 0 || "$unknown_review_apply_output" != *"Unknown repository"* ]]; then
  echo "Expected unknown review apply repository to fail clearly" >&2
  echo "$unknown_review_apply_output" >&2
  exit 1
fi

if [[ -e "$unknown_review_apply_log" ]]; then
  echo "Unknown review repository must fail before invoking gh" >&2
  cat "$unknown_review_apply_log" >&2
  exit 1
fi

review_log="$TMP_DIR/review.log"
GH_CALL_LOG="$review_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" \
  --repo GuardGuide --apply-review-baseline >/dev/null

expected_review_call=$'PATCH\trepos/SecPal/GuardGuide/branches/main/protection/required_pull_request_reviews\t{"required_approving_review_count":0}'
if [[ "$(<"$review_log")" != "$expected_review_call" ]]; then
  echo "Review apply did not use the dedicated PATCH endpoint and exact payload" >&2
  cat "$review_log" >&2
  exit 1
fi

status_log="$TMP_DIR/status.log"
GH_CALL_LOG="$status_log" GH_STATE_DIR="$state_dir" PATH="$fake_bin" \
  "$SHELL_BIN" "$SYNC_SCRIPT" --repo .github --apply >/dev/null

if grep -Fq '/required_status_checks' "$review_log"; then
  echo "Review apply must not update required status checks" >&2
  cat "$review_log" >&2
  exit 1
fi

remediation_failures=0
expected_status_endpoint='repos/SecPal/.github/branches/main/protection/required_status_checks'
expected_status_payload="$(
  jq -c '{
    strict: false,
    checks: [
      .checks[]
      | {
          context,
          app_id: (if .app_id == null then -1 else .app_id end)
        }
    ]
  }' "$state_dir/.github.json"
)"
expected_status_log="$(printf 'GET\t%s\t-\nPATCH\t%s\t%s' \
  "$expected_status_endpoint" "$expected_status_endpoint" "$expected_status_payload")"
if [[ "$(<"$status_log")" != "$expected_status_log" ]]; then
  echo "FAIL-FIRST F1: status apply must GET live state and PATCH only strict while preserving mixed bindings" >&2
  cat "$status_log" >&2
  remediation_failures=$((remediation_failures + 1))
fi

codecov_state_dir="$TMP_DIR/codecov-states"
mkdir -p "$codecov_state_dir"
for codecov_repo in .github api frontend contracts; do
  jq -n --argjson strict false '{
    strict: $strict,
    checks: [
      {context: "codecov/patch", app_id: 777},
      {context: "unbound-check", app_id: null},
      {context: "bound-check", app_id: 15368}
    ]
  }' >"$codecov_state_dir/$codecov_repo.json"
  if [[ "$codecov_repo" != ".github" ]]; then
    jq '.checks |= map(select(.context != "codecov/patch"))' \
      "$codecov_state_dir/$codecov_repo.json" >"$codecov_state_dir/$codecov_repo.filtered.json"
    mv "$codecov_state_dir/$codecov_repo.filtered.json" "$codecov_state_dir/$codecov_repo.json"
  fi
done

codecov_log="$TMP_DIR/codecov.log"
GH_CALL_LOG="$codecov_log" GH_STATE_DIR="$codecov_state_dir" PATH="$fake_bin" \
  "$SHELL_BIN" "$CODECOV_SCRIPT" >/dev/null 2>&1 || true
expected_codecov_endpoint='repos/SecPal/.github/branches/main/protection/required_status_checks'
expected_codecov_payload='{"strict":false,"checks":[{"context":"unbound-check","app_id":-1},{"context":"bound-check","app_id":15368}]}'
codecov_patch_line="$(sed -n '/^PATCH\trepos\/SecPal\/\.github\//p' "$codecov_log")"
if [[ "$codecov_patch_line" != "$(printf 'PATCH\t%s\t%s' "$expected_codecov_endpoint" "$expected_codecov_payload")" ]]; then
  echo "FAIL-FIRST F2: Codecov helper must preserve current strictness and remaining bindings" >&2
  cat "$codecov_log" >&2
  remediation_failures=$((remediation_failures + 1))
fi

for codecov_repo in .github api frontend contracts; do
  codecov_endpoint="repos/SecPal/$codecov_repo/branches/main/protection/required_status_checks"
  if [[ "$(grep -Fc "$(printf 'GET\t%s\t-' "$codecov_endpoint")" "$codecov_log")" -ne 1 ]]; then
    echo "Codecov helper must read required checks exactly once for SecPal/$codecov_repo" >&2
    cat "$codecov_log" >&2
    remediation_failures=$((remediation_failures + 1))
  fi
done

if sed -n '/^PATCH\t/p' "$codecov_log" | grep -Fqv "$expected_codecov_endpoint"; then
  echo "Codecov helper must not PATCH repositories without a Codecov check" >&2
  cat "$codecov_log" >&2
  remediation_failures=$((remediation_failures + 1))
fi

if [[ $remediation_failures -ne 0 ]]; then
  echo "Focused required-check remediation contracts failed: $remediation_failures" >&2
  exit 1
fi

assert_sync_rejects_state() {
  local label="$1"
  local state_file="$2"
  local log_file="$TMP_DIR/$label.log"
  local output status

  set +e
  output="$(GH_CALL_LOG="$log_file" GH_REQUIRED_STATE_FILE="$state_file" PATH="$fake_bin" \
    "$SHELL_BIN" "$SYNC_SCRIPT" --repo .github --apply 2>&1)"
  status=$?
  set -e

  if [[ $status -eq 0 || "$output" != *"SecPal/.github"* ]]; then
    echo "Expected $label live state to fail clearly for SecPal/.github" >&2
    echo "$output" >&2
    exit 1
  fi
  if grep -q '^PATCH' "$log_file"; then
    echo "$label live state must fail before PATCH" >&2
    cat "$log_file" >&2
    exit 1
  fi
}

missing_state="$TMP_DIR/missing-state.json"
jq '.checks |= map(select(.context != "CodeQL"))' "$state_dir/.github.json" >"$missing_state"
missing_log="$TMP_DIR/missing-context.log"
GH_CALL_LOG="$missing_log" GH_REQUIRED_STATE_FILE="$missing_state" PATH="$fake_bin" \
  "$SHELL_BIN" "$SYNC_SCRIPT" --repo .github --apply >/dev/null
if [[ "$(grep -c '^PATCH' "$missing_log")" -ne 1 ]] \
  || ! sed -n '/^PATCH/p' "$missing_log" | cut -f3- \
    | jq -e '.checks | any(.context == "CodeQL")' >/dev/null; then
  echo "A missing canonical context must be restored in one bounded PATCH" >&2
  cat "$missing_log" >&2
  exit 1
fi

unexpected_state="$TMP_DIR/unexpected-state.json"
jq '.checks += [{context: "unexpected-check", app_id: null}]' "$state_dir/.github.json" >"$unexpected_state"
assert_sync_rejects_state unexpected-context "$unexpected_state"

duplicate_state="$TMP_DIR/duplicate-state.json"
jq '.checks += [.checks[0]]' "$state_dir/.github.json" >"$duplicate_state"
assert_sync_rejects_state duplicate-context "$duplicate_state"

malformed_state="$TMP_DIR/malformed-state.json"
jq '.strict = "true"' "$state_dir/.github.json" >"$malformed_state"
assert_sync_rejects_state malformed-response "$malformed_state"

get_failure_log="$TMP_DIR/get-failure.log"
set +e
get_failure_output="$(GH_CALL_LOG="$get_failure_log" GH_STATE_DIR="$state_dir" \
  GH_FAIL_GET_REPO=.github PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" \
  --repo .github --apply 2>&1)"
get_failure_status=$?
set -e
if [[ $get_failure_status -eq 0 || "$get_failure_output" != *"SecPal/.github"* ]] \
  || grep -q '^PATCH' "$get_failure_log"; then
  echo "Required-status-check GET failure must propagate before PATCH" >&2
  echo "$get_failure_output" >&2
  exit 1
fi

status_patch_failure_log="$TMP_DIR/status-patch-failure.log"
set +e
status_patch_failure_output="$(GH_CALL_LOG="$status_patch_failure_log" GH_STATE_DIR="$state_dir" \
  GH_FAIL_PATCH_REPO=.github PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" \
  --repo .github --apply 2>&1)"
status_patch_failure_status=$?
set -e
if [[ $status_patch_failure_status -eq 0 || "$status_patch_failure_output" != *"SecPal/.github"* ]]; then
  echo "Required-status-check PATCH failure must propagate and identify the repository" >&2
  echo "$status_patch_failure_output" >&2
  exit 1
fi

codecov_true_dir="$TMP_DIR/codecov-true-states"
mkdir -p "$codecov_true_dir"
for codecov_repo in .github api frontend contracts; do
  jq '.strict = true' "$codecov_state_dir/$codecov_repo.json" >"$codecov_true_dir/$codecov_repo.json"
done
codecov_true_log="$TMP_DIR/codecov-true.log"
GH_CALL_LOG="$codecov_true_log" GH_STATE_DIR="$codecov_true_dir" PATH="$fake_bin" \
  "$SHELL_BIN" "$CODECOV_SCRIPT" >/dev/null
expected_codecov_true_payload='{"strict":true,"checks":[{"context":"unbound-check","app_id":-1},{"context":"bound-check","app_id":15368}]}'
if ! grep -Fxq "$(printf 'PATCH\t%s\t%s' "$expected_codecov_endpoint" "$expected_codecov_true_payload")" "$codecov_true_log"; then
  echo "Codecov helper must preserve strict=true and remaining bindings" >&2
  cat "$codecov_true_log" >&2
  exit 1
fi

codecov_get_failure_log="$TMP_DIR/codecov-get-failure.log"
set +e
codecov_get_failure_output="$(GH_CALL_LOG="$codecov_get_failure_log" GH_STATE_DIR="$codecov_state_dir" \
  GH_FAIL_GET_REPO=.github PATH="$fake_bin" "$SHELL_BIN" "$CODECOV_SCRIPT" 2>&1)"
codecov_get_failure_status=$?
set -e
if [[ $codecov_get_failure_status -eq 0 ]] \
  || grep -Fq $'PATCH\trepos/SecPal/.github/' "$codecov_get_failure_log"; then
  echo "Codecov required-status-check GET failure must fail closed" >&2
  echo "$codecov_get_failure_output" >&2
  exit 1
fi

codecov_patch_failure_log="$TMP_DIR/codecov-patch-failure.log"
set +e
codecov_patch_failure_output="$(GH_CALL_LOG="$codecov_patch_failure_log" GH_STATE_DIR="$codecov_state_dir" \
  GH_FAIL_PATCH_REPO=.github PATH="$fake_bin" "$SHELL_BIN" "$CODECOV_SCRIPT" 2>&1)"
codecov_patch_failure_status=$?
set -e
if [[ $codecov_patch_failure_status -eq 0 ]]; then
  echo "Codecov required-status-check PATCH failure must propagate" >&2
  echo "$codecov_patch_failure_output" >&2
  exit 1
fi

all_status_log="$TMP_DIR/all-status.log"
all_review_log="$TMP_DIR/all-review.log"
GH_CALL_LOG="$all_status_log" GH_STATE_DIR="$state_dir" PATH="$fake_bin" \
  "$SHELL_BIN" "$SYNC_SCRIPT" --apply >/dev/null
GH_CALL_LOG="$all_review_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" --apply-review-baseline >/dev/null

status_repositories="$(sed -n 's#^PATCH[[:space:]]repos/SecPal/\([^/]*\)/branches/main/protection/required_status_checks.*#\1#p' "$all_status_log")"
review_repositories="$(sed -n 's#^[^[:space:]]*[[:space:]]repos/SecPal/\([^/]*\)/branches/main/protection/required_pull_request_reviews.*#\1#p' "$all_review_log")"
if [[ -z "$status_repositories" || "$review_repositories" != "$status_repositories" ]]; then
  echo "Review baseline must iterate over the required-check managed repository set" >&2
  echo "Status repositories:" >&2
  echo "$status_repositories" >&2
  echo "Review repositories:" >&2
  echo "$review_repositories" >&2
  exit 1
fi

failure_log="$TMP_DIR/failure.log"
set +e
failure_output="$(GH_CALL_LOG="$failure_log" GH_FAIL_REPO=android PATH="$fake_bin" \
  "$SHELL_BIN" "$SYNC_SCRIPT" --apply-review-baseline 2>&1)"
failure_status=$?
set -e

if [[ $failure_status -eq 0 || "$failure_output" != *"SecPal/android"* ]]; then
  echo "Review API failure must propagate and identify the repository" >&2
  echo "$failure_output" >&2
  exit 1
fi

if grep -Fq 'repos/SecPal/api/' "$failure_log"; then
  echo "Review apply must stop after a repository update fails" >&2
  cat "$failure_log" >&2
  exit 1
fi

status_failure_log="$TMP_DIR/status-failure.log"
set +e
status_failure_output="$(GH_CALL_LOG="$status_failure_log" GH_STATE_DIR="$state_dir" \
  GH_FAIL_PATCH_REPO=android PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" --apply 2>&1)"
status_failure_status=$?
set -e

if [[ $status_failure_status -eq 0 || "$status_failure_output" != *"SecPal/android"* ]]; then
  echo "Status API failure must propagate and identify the repository" >&2
  echo "$status_failure_output" >&2
  exit 1
fi

if grep -Fq 'repos/SecPal/api/' "$status_failure_log"; then
  echo "Status apply must stop after a repository update fails" >&2
  cat "$status_failure_log" >&2
  exit 1
fi
