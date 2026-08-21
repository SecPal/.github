#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_SCRIPT="$REPO_ROOT/scripts/sync-required-checks.sh"
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

  if ! jq -e --arg expected "$expected" '.strict == true and (.checks | any(.context == $expected))' >/dev/null <<<"$payload"; then
    echo "Expected payload to require '$expected'" >&2
    echo "$payload" >&2
    exit 1
  fi
}

assert_payload_contexts_equal() {
  local payload="$1"
  local expected="$2"

  if ! jq -e --argjson expected "$expected" '
    .strict == true and
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
  "strict": true,
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

api_payload="$(bash "$SYNC_SCRIPT" --repo api --print-payload)"
assert_payload_has_context "$api_payload" "AI Instructions / Validate AI Instructions"
assert_payload_has_context "$api_payload" "PEST Tests"

android_payload="$(bash "$SYNC_SCRIPT" --repo android --print-payload)"
android_contexts='[
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
]'
assert_payload_contexts_equal "$android_payload" "$android_contexts"

guardguide_payload="$(bash "$SYNC_SCRIPT" --repo GuardGuide --print-payload)"
assert_payload_has_context "$guardguide_payload" "Pest Tests (PostgreSQL)"
assert_payload_has_context "$guardguide_payload" "Pest Tests (MariaDB)"
assert_payload_has_context "$guardguide_payload" "Analyze with CodeQL (javascript-typescript)"

secpal_app_payload="$(bash "$SYNC_SCRIPT" --repo secpal.app --print-payload)"
assert_payload_has_context "$secpal_app_payload" "Node Tests / Run Tests"
assert_payload_has_context "$secpal_app_payload" "Analyze Code (javascript-typescript)"

guardguide_de_payload="$(bash "$SYNC_SCRIPT" --repo guardguide.de --print-payload)"
assert_payload_has_context "$guardguide_de_payload" "Node Tests / Run Tests"
assert_payload_has_context "$guardguide_de_payload" "Astro Build / Build Project"

frontend_payload="$(bash "$SYNC_SCRIPT" --repo frontend --print-payload)"
assert_payload_has_context "$frontend_payload" "Analyze with CodeQL (javascript-typescript)"
assert_payload_has_context "$frontend_payload" "Vitest Tests"

contracts_payload="$(bash "$SYNC_SCRIPT" --repo contracts --print-payload)"
assert_payload_has_context "$contracts_payload" "OpenAPI Lint / Validate OpenAPI Specification"
assert_payload_has_context "$contracts_payload" "AI Instructions / Validate AI Instructions"

# The bare 'CodeQL' context is only emitted by .github (its CodeQL Applicability
# Guardrail workflow names its job exactly 'CodeQL'). For every other repo the
# CodeQL workflow names a different job (e.g. 'Analyze with CodeQL' / 'Analyze
# Code'), so requiring bare 'CodeQL' there would block PRs forever.
for non_github_payload in "$api_payload" "$android_payload" "$guardguide_payload" "$secpal_app_payload" "$guardguide_de_payload" "$frontend_payload" "$contracts_payload"; do
  if jq -e '.checks | any(.context == "CodeQL")' >/dev/null <<<"$non_github_payload"; then
    echo "Only the '.github' manifest entry may require the bare 'CodeQL' context; other repos must require their actual CodeQL job context (e.g. 'Analyze with CodeQL (<language>)' or 'Analyze Code (<language>)')." >&2
    echo "$non_github_payload" >&2
    exit 1
  fi
done

github_payload="$(bash "$SYNC_SCRIPT" --repo .github --print-payload)"
assert_payload_has_context "$github_payload" "Validate PR Evidence"
assert_payload_has_context "$github_payload" "Validate PR Title And Body Language"
assert_payload_has_context "$github_payload" "Validate Signed PR Commits"

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

payload="$(jq -c . "$input_file")"
printf '%s\t%s\t%s\n' "$method" "$endpoint" "$payload" >>"$GH_CALL_LOG"

if [[ -n "${GH_FAIL_REPO:-}" && "$endpoint" == "repos/SecPal/$GH_FAIL_REPO/"* ]]; then
  exit 1
fi
EOF
chmod +x "$fake_bin/gh"

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
GH_CALL_LOG="$status_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" \
  --repo api --apply >/dev/null

if grep -Fq '/required_pull_request_reviews' "$status_log"; then
  echo "Status apply must not update pull-request review protection" >&2
  cat "$status_log" >&2
  exit 1
fi

if grep -Fq '/required_status_checks' "$review_log"; then
  echo "Review apply must not update required status checks" >&2
  cat "$review_log" >&2
  exit 1
fi

all_status_log="$TMP_DIR/all-status.log"
all_review_log="$TMP_DIR/all-review.log"
GH_CALL_LOG="$all_status_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" --apply >/dev/null
GH_CALL_LOG="$all_review_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" --apply-review-baseline >/dev/null

status_repositories="$(sed -n 's#^[^[:space:]]*[[:space:]]repos/SecPal/\([^/]*\)/branches/main/protection/required_status_checks.*#\1#p' "$all_status_log")"
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
