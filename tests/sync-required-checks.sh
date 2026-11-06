#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_SCRIPT="$REPO_ROOT/scripts/sync-required-checks.sh"
CODECOV_SCRIPT="$REPO_ROOT/scripts/configure-codecov-optional.sh"
EXPECTED_APP_BINDINGS_JSON='{
  ".github": {
    "Validate Signed PR Commits": 15368,
    "Evidence Architecture PR Gate": 15368,
    "Verify Workflow Pin Provenance": 15368,
    "Work-Graph Resolver": 15368,
    "Vulnerability Policy": 15368,
    "Dependabot Manifest Guard Contract": 15368,
    "auto-merge / Dependabot Source Safety": 15368
  },
  "deployment": {
    "Repository Contract": 15368,
    "REUSE Compliance / Check REUSE Compliance": 15368,
    "Markdown and Shell": 15368,
    "Quadlet Contract (amd64)": 15368,
    "Quadlet Contract (arm64)": 15368,
    "Repository Security": 15368,
    "OpenSSH Account Contract": 15368,
    "DNF4 Exact NEVRA Contract": 15368,
    "Architecture Gate (Python 3.12.13)": 15368,
    "Architecture Gate (Python 3.13.14)": 15368
  },
  "android": {
    "Android Lint": 15368,
    "Android JVM Unit Tests": 15368,
    "Android Release Network Security": 15368,
    "Dependency Audit": 15368,
    "Repository Security / Scan repository": 15368
  },
  "api": {
    "Repository Security / Accept API Repository Security": 15368,
    "Pre-commit Hook Smoke Test (ubuntu-latest)": 15368,
    "Pre-commit Hook Smoke Test (macos-latest)": 15368
  },
  "contracts": {
    "Dependabot Manifest Guard / Manifest Coverage": 15368,
    "Dependabot Manifest Guard / Cadence Policy": 15368,
    "auto-merge / Dependabot Source Safety": 15368
  },
  "frontend": {
    "Repository Security / Repository Security": 15368,
    "Dependabot Manifest Guard / Manifest Coverage": 15368,
    "Dependabot Manifest Guard / Cadence Policy": 15368,
    "Performance Audit": 15368
  },
  "secpal.app": {
    "auto-merge / Dependabot Source Safety": 15368
  }
}'
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

  if ! jq -e --arg expected "$expected" '(.checks | any(.context == $expected))' >/dev/null <<<"$payload"; then
    echo "Expected payload to require '$expected'" >&2
    echo "$payload" >&2
    exit 1
  fi
}

assert_payload_contexts_equal() {
  local payload="$1"
  local expected="$2"
  local expected_strict="$3"
  local expected_repo="${4:-}"

  if ! jq -e --argjson expected "$expected" --argjson expected_strict "$expected_strict" --arg repo "$expected_repo" --argjson apps "$EXPECTED_APP_BINDINGS_JSON" '
    .strict == $expected_strict and
    (.checks | length) == ($expected | length) and
    ([.checks[].context] | length) == ([.checks[].context] | unique | length) and
    ($expected | length) == ($expected | unique | length) and
    ([.checks[].context] | sort) == ($expected | sort) and
    all(.checks[];
      .app_id == ($apps[$repo][.context] // -1)
    )
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
if (assert_payload_contexts_equal "$duplicate_payload" "$duplicate_contexts" false) >/dev/null 2>&1; then
  echo "Exact payload assertion must reject duplicate payload and expected contexts" >&2
  exit 1
fi

if [[ ! -x "$SYNC_SCRIPT" ]]; then
  echo "Expected executable sync script at $SYNC_SCRIPT" >&2
  exit 1
fi

pending="$(bash "$SYNC_SCRIPT" --repo .github --print-pending-checks)"
if ! jq -e '. == []' <<<"$pending" >/dev/null; then
  echo "Promoted Evidence Architecture identity must no longer be pending" >&2
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
    "Validate Signed PR Commits",
    "Evidence Architecture PR Gate",
    "Verify Workflow Pin Provenance",
    "Work-Graph Resolver",
    "Vulnerability Policy",
    "Dependabot Manifest Guard Contract",
    "auto-merge / Dependabot Source Safety"
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
    "Markdown Lint / Lint Markdown Files",
    "AI Instructions / Validate AI Instructions",
    "Certificate transparency",
    "Android Lint",
    "Android JVM Unit Tests",
    "Android Release Network Security",
    "Dependency Audit",
    "Repository Security / Scan repository"
  ],
  "api": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Laravel Pint / Check Code Style",
    "PHPStan / Static Analysis",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "PEST Tests",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions",
    "Check License Compatibility",
    "Repository Security / Accept API Repository Security",
    "Pre-commit Hook Smoke Test (ubuntu-latest)",
    "Pre-commit Hook Smoke Test (macos-latest)"
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
    "AI Instructions / Validate AI Instructions",
    "Dependabot Manifest Guard / Manifest Coverage",
    "Dependabot Manifest Guard / Cadence Policy",
    "auto-merge / Dependabot Source Safety"
  ],
  "deployment": [
    "Repository Contract",
    "REUSE Compliance / Check REUSE Compliance",
    "Markdown and Shell",
    "Quadlet Contract (amd64)",
    "Quadlet Contract (arm64)",
    "Repository Security",
    "OpenSSH Account Contract",
    "DNF4 Exact NEVRA Contract",
    "Architecture Gate (Python 3.12.13)",
    "Architecture Gate (Python 3.13.14)"
  ],
  "frontend": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Formatting Check / Check Code Formatting",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Markdown Lint / Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "Vitest Tests",
    "check-conflicts / Detect Git Conflict Markers",
    "Analyze with CodeQL (javascript-typescript)",
    "AI Instructions / Validate AI Instructions",
    "Check License Compatibility",
    "Strict CSP",
    "Container Contract",
    "Repository Security / Repository Security",
    "Dependabot Manifest Guard / Manifest Coverage",
    "Dependabot Manifest Guard / Cadence Policy",
    "Performance Audit"
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
    "Node Tests / Run Tests",
    "Analyze Code (javascript-typescript)",
    "AI Instructions / Validate AI Instructions",
    "auto-merge / Dependabot Source Safety"
  ]
}'

mapfile -t expected_repositories < <(jq -r 'keys[]' <<<"$EXPECTED_CONTEXTS_JSON")
if [[ "${expected_repositories[*]}" != ".github android api contracts deployment frontend secpal.app" ]]; then
  echo "Expected exact canonical required-check repository inventory" >&2
  exit 1
fi

declare -A payloads
for expected_repo in "${expected_repositories[@]}"; do
  payloads["$expected_repo"]="$(bash "$SYNC_SCRIPT" --repo "$expected_repo" --print-payload)"
  expected_contexts="$(jq -c --arg repo "$expected_repo" '.[$repo]' <<<"$EXPECTED_CONTEXTS_JSON")"
  expected_strict=true
  assert_payload_contexts_equal "${payloads[$expected_repo]}" "$expected_contexts" "$expected_strict" "$expected_repo"
done

# The bare 'CodeQL' context is only emitted by .github (its CodeQL Applicability
# Guardrail workflow names its job exactly 'CodeQL'). For every other repo the
# CodeQL workflow names a different job (e.g. 'Analyze with CodeQL' / 'Analyze
# Code'), so requiring bare 'CodeQL' there would block PRs forever.
for non_github_repo in android api contracts frontend secpal.app; do
  non_github_payload="${payloads[$non_github_repo]}"
  if jq -e '.checks | any(.context == "CodeQL")' >/dev/null <<<"$non_github_payload"; then
    echo "Only the '.github' manifest entry may require the bare 'CodeQL' context; other repos must require their actual CodeQL job context (e.g. 'Analyze with CodeQL (<language>)' or 'Analyze Code (<language>)')." >&2
    echo "$non_github_payload" >&2
    exit 1
  fi
done

github_payload="${payloads[.github]}"
assert_payload_has_context "$github_payload" "Validate Signed PR Commits"

for review_repo in .github android; do
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
  jq --arg repo "$expected_repo" --argjson apps "$EXPECTED_APP_BINDINGS_JSON" '.strict = false |
    .checks |= map(if $apps[$repo][.context] == null then .app_id = null else . end)' \
    <<<"${payloads[$expected_repo]}" >"$state_dir/$expected_repo.json"
done

# Existing live API/frontend producers remain bound even where the canonical
# inventory permits any producer for a newly introduced context.
for bound_repo in api frontend; do
  jq '.checks |= map(
    if .context == "Check License Compatibility" or .context == "Strict CSP" or .context == "Container Contract"
    then .app_id = 15368 else . end
  )' "$state_dir/$bound_repo.json" >"$state_dir/$bound_repo.bound.json"
  mv "$state_dir/$bound_repo.bound.json" "$state_dir/$bound_repo.json"
done

# Exercise promotion of the evidence gate while preserving every other binding.
jq '.checks |= map(select(.context != "Evidence Architecture PR Gate"))' \
  "$state_dir/.github.json" >"$state_dir/.github.bound.json"
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

# Retired and substituted repositories must fail before any provider call.
# Operations is private with independently owned protection, outside this
# public required-check inventory.
for unsupported_repository in operations GuardGuide guardguide.de Assure Visit does-not-exist; do
  for operation in --print-payload --print-review-payload --apply --apply-review-baseline; do
    unsupported_log="$TMP_DIR/$unsupported_repository-${operation#--}.log"
    set +e
    unsupported_output="$(GH_CALL_LOG="$unsupported_log" PATH="$fake_bin" \
      "$SHELL_BIN" "$SYNC_SCRIPT" --repo "$unsupported_repository" "$operation" 2>&1)"
    unsupported_status=$?
    set -e
    if [[ $unsupported_status -eq 0 || "$unsupported_output" != *"Unknown repository"* ]]; then
      echo "Unsupported repository $unsupported_repository must fail clearly for $operation" >&2
      exit 1
    fi
    if [[ -e "$unsupported_log" ]]; then
      echo "Unsupported repository must fail before invoking gh" >&2
      exit 1
    fi
  done
done

# Required-check enrollment must not expand review-baseline write authority.
for operation in --print-review-payload --apply-review-baseline; do
  deployment_review_log="$TMP_DIR/deployment-${operation#--}.log"
  set +e
  deployment_review_output="$(GH_CALL_LOG="$deployment_review_log" PATH="$fake_bin" \
    "$SHELL_BIN" "$SYNC_SCRIPT" --repo deployment "$operation" 2>&1)"
  deployment_review_status=$?
  set -e
  if [[ $deployment_review_status -ne 2 || "$deployment_review_output" != *"Review baseline is not managed for SecPal/deployment"* ]]; then
    echo "Deployment review-baseline mode must be rejected without provider access" >&2
    exit 1
  fi
  if [[ -e "$deployment_review_log" ]]; then
    echo "Deployment review-baseline rejection must precede every provider call" >&2
    exit 1
  fi
done

review_log="$TMP_DIR/review.log"
GH_CALL_LOG="$review_log" PATH="$fake_bin" "$SHELL_BIN" "$SYNC_SCRIPT" \
  --repo android --apply-review-baseline >/dev/null

expected_review_call=$'PATCH\trepos/SecPal/android/branches/main/protection/required_pull_request_reviews\t{"required_approving_review_count":0}'
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
  jq -c --argjson order "$(jq -c '.[".github"]' <<<"$EXPECTED_CONTEXTS_JSON")" '{
    strict: true,
    checks: ([
      .checks[]
      | {
          context,
          app_id: (if .app_id == null then -1 else .app_id end)
        }
    ] + [{context: "Evidence Architecture PR Gate", app_id: 15368}])
  } | .checks |= sort_by(.context as $context | $order | index($context))' "$state_dir/.github.json"
)"
expected_status_log="$(printf 'GET\t%s\t-\nPATCH\t%s\t%s' \
  "$expected_status_endpoint" "$expected_status_endpoint" "$expected_status_payload")"
if [[ "$(<"$status_log")" != "$expected_status_log" ]]; then
  echo "FAIL-FIRST F1: status apply must apply strict checks and preserve mixed App bindings" >&2
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
  local repo="${3:-.github}"
  local log_file="$TMP_DIR/$label.log"
  local output status

  set +e
  output="$(GH_CALL_LOG="$log_file" GH_REQUIRED_STATE_FILE="$state_file" PATH="$fake_bin" \
    "$SHELL_BIN" "$SYNC_SCRIPT" --repo "$repo" --apply 2>&1)"
  status=$?
  set -e

  if [[ $status -eq 0 || "$output" != *"SecPal/$repo"* ]]; then
    echo "Expected $label live state to fail clearly for SecPal/$repo" >&2
    echo "$output" >&2
    exit 1
  fi
  if grep -q '^PATCH' "$log_file"; then
    echo "$label live state must fail before PATCH" >&2
    cat "$log_file" >&2
    exit 1
  fi
}

# Deployment's existing producer bindings are mandatory, never inferred
# or relaxed when a live entry already has a conflicting identity.
for binding in null -1 777; do
  jq --argjson binding "$binding" '.checks[0].app_id = $binding' \
    "$state_dir/deployment.json" >"$TMP_DIR/deployment-binding.json"
  assert_sync_rejects_state "deployment-binding-$binding" "$TMP_DIR/deployment-binding.json" deployment
done

# The binding policy must reference exact canonical membership. Mutate only the
# candidate inventory and exercise the same CLI; no live provider is available.
original_sync_script="$SYNC_SCRIPT"
for mutation in missing substituted duplicate; do
  mutated_script="$TMP_DIR/$mutation-sync.sh"
  case "$mutation" in
    missing) sed '/^    "Evidence Architecture PR Gate",$/d' "$original_sync_script" >"$mutated_script" ;;
    substituted) sed 's/^    "Evidence Architecture PR Gate",$/    "Evidence Architecture Gate",/' "$original_sync_script" >"$mutated_script" ;;
    duplicate) sed 's/^    "Evidence Architecture PR Gate",$/    "Evidence Architecture PR Gate", "Evidence Architecture PR Gate",/' "$original_sync_script" >"$mutated_script" ;;
  esac
  SYNC_SCRIPT="$mutated_script"
  if "$SHELL_BIN" "$SYNC_SCRIPT" --repo .github --print-payload >/dev/null 2>&1; then
    echo "Canonical $mutation identity must fail in printed payloads" >&2
    exit 1
  fi
  assert_sync_rejects_state "canonical-$mutation" "$state_dir/.github.json"
done
SYNC_SCRIPT="$original_sync_script"

# The canonical fifteen checks preserve positive and unbound bindings.
# The already-activated state is idempotent.
jq -e '.strict == true and (.checks | length) == 15 and
  ([.checks[].context] | unique | length) == 15 and
  ([.checks[] | select(.app_id == 15368)] | length) == 7 and
  ([.checks[] | select(.app_id == -1)] | length) == 8' \
  <<<"$expected_status_payload" >/dev/null
activated_state="$TMP_DIR/activated-state.json"
printf '%s\n' "$expected_status_payload" >"$activated_state"
activated_log="$TMP_DIR/activated.log"
GH_CALL_LOG="$activated_log" GH_REQUIRED_STATE_FILE="$activated_state" PATH="$fake_bin" \
  "$SHELL_BIN" "$SYNC_SCRIPT" --repo .github --apply >/dev/null
if [[ "$(<"$activated_log")" != "$expected_status_log" ]]; then
  echo "Already-activated exact identity must preserve the same payload" >&2
  exit 1
fi

# Missing/unbound, malformed or substituted producer identity is never silently
# normalized to the canonical producer for an already-present gate.
for binding in null -1 777 0 '"15368"' 15368.5; do
  binding_state="$TMP_DIR/gate-binding.json"
  jq --argjson binding "$binding" '.checks |= map(
    if .context == "Evidence Architecture PR Gate" then .app_id = $binding else . end
  )' "$activated_state" >"$binding_state"
  assert_sync_rejects_state "gate-binding-$binding" "$binding_state"
done
jq '.checks |= map(if .context == "Evidence Architecture PR Gate" then del(.app_id) else . end)' \
  "$activated_state" >"$TMP_DIR/gate-missing-producer.json"
assert_sync_rejects_state gate-missing-producer "$TMP_DIR/gate-missing-producer.json"
jq '.checks |= map(if .context == "Evidence Architecture PR Gate" then .context = "Evidence Architecture Gate" else . end)' \
  "$activated_state" >"$TMP_DIR/gate-substituted-context.json"
assert_sync_rejects_state gate-substituted-context "$TMP_DIR/gate-substituted-context.json"
jq '.checks += [.checks[] | select(.context == "Evidence Architecture PR Gate")]' \
  "$activated_state" >"$TMP_DIR/gate-duplicate.json"
assert_sync_rejects_state gate-duplicate "$TMP_DIR/gate-duplicate.json"

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

# Every managed repository applies strictness without changing the live
# producer identities. The separate .github promotion case adds its gate.
for expected_repo in "${expected_repositories[@]}"; do
  actual_payload="$(sed -n "/^PATCH[[:space:]]repos\/SecPal\/$expected_repo\/branches\/main\/protection\/required_status_checks[[:space:]]/p" "$all_status_log" | cut -f3-)"
  if [[ "$expected_repo" == ".github" ]]; then
    expected_payload="$expected_status_payload"
  else
    expected_payload="$(jq -c '.strict = true | .checks |= map(
      if .app_id == null then .app_id = -1 else . end
    )' "$state_dir/$expected_repo.json")"
  fi
  if [[ "$actual_payload" != "$expected_payload" ]]; then
    echo "Required-check identity/binding preservation failed for SecPal/$expected_repo" >&2
    exit 1
  fi
done

status_repositories="$(sed -n 's#^PATCH[[:space:]]repos/SecPal/\([^/]*\)/branches/main/protection/required_status_checks.*#\1#p' "$all_status_log")"
review_repositories="$(sed -n 's#^[^[:space:]]*[[:space:]]repos/SecPal/\([^/]*\)/branches/main/protection/required_pull_request_reviews.*#\1#p' "$all_review_log")"
expected_review_repositories="$(printf '%s\n' "${expected_repositories[@]}" | grep -vx deployment)"
if [[ "$status_repositories" != "$(printf '%s\n' "${expected_repositories[@]}")" || "$review_repositories" != "$expected_review_repositories" ]]; then
  echo "Required checks must cover seven repositories while preserving the original review-baseline scope" >&2
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

# Activated safety requirements must survive the existing owner’s next sync.
for safety_repo in .github contracts secpal.app; do
  safety_payload="$(bash "$SYNC_SCRIPT" --repo "$safety_repo" --print-payload)"
  jq -e '.checks | any(.context == "auto-merge / Dependabot Source Safety" and .app_id == 15368)' \
    <<<"$safety_payload" >/dev/null || {
    echo "Activated source safety is missing from the canonical inventory: $safety_repo" >&2
    exit 1
  }
done

for safety_repo in .github contracts secpal.app; do
  jq '.checks |= map(if .context == "auto-merge / Dependabot Source Safety" then .app_id = 777 else . end)' \
    "$state_dir/$safety_repo.json" >"$TMP_DIR/wrong-safety-producer.json"
  assert_sync_rejects_state "wrong-safety-$safety_repo" "$TMP_DIR/wrong-safety-producer.json" "$safety_repo"
done
for pending_repo in api android frontend deployment; do
  pending="$(bash "$SYNC_SCRIPT" --repo "$pending_repo" --print-pending-checks)"
  jq -e --argjson pending "$pending" 'all(.checks[]; .context as $context | $pending | index($context) == null)' \
    <<<"${payloads[$pending_repo]}" >/dev/null || {
    echo "Unactivated identity leaked into apply payload: $pending_repo" >&2
    exit 1
  }
done
for expected_repo in "${expected_repositories[@]}"; do
  jq -e 'all(.checks[]; .context != "auto-merge / Enable Auto-Merge" and
    .context != "auto-merge / Skip Auto-Merge" and .context != "auto-merge / Check Auto-Merge Eligibility")' \
    <<<"${payloads[$expected_repo]}" >/dev/null || {
    echo "Informational enrollment job must not be required: $expected_repo" >&2
    exit 1
  }
done
