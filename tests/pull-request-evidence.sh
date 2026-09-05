#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

export PR_DRAFT=false

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-pull-request-evidence.sh"
TEMPLATE="$REPO_ROOT/.github/pull_request_template.md"
WORKFLOW="$REPO_ROOT/.github/workflows/pull-request-evidence.yml"
QUICK_REFERENCE="$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pull-request-evidence.XXXXXX")"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

if [ ! -f "$VALIDATOR" ]; then
  echo "Expected validator script was not found: $VALIDATOR" >&2
  exit 1
fi

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

if [ ! -f "$TEMPLATE" ]; then
  echo "Expected PR template was not found: $TEMPLATE" >&2
  exit 1
fi

if [ ! -f "$QUICK_REFERENCE" ]; then
  echo "Expected quick reference doc was not found: $QUICK_REFERENCE" >&2
  exit 1
fi

if ! grep -Fq '## TDD / Validate-First Evidence' "$TEMPLATE"; then
  echo "PR template is missing the TDD / Validate-First Evidence section." >&2
  exit 1
fi

if ! grep -Fq 'only if the repository instructions explicitly allow validate-first' "$TEMPLATE"; then
  echo "PR template must keep validate-first exceptions explicitly tied to repository instructions." >&2
  exit 1
fi

if ! grep -Fq 'REPLACE_WITH_FAILING_PROOF' "$QUICK_REFERENCE"; then
  echo "Quick reference must use the same explicit evidence placeholders as the PR template." >&2
  exit 1
fi

if grep -Fq '<command or reproduced defect>' "$QUICK_REFERENCE"; then
  echo "Quick reference must not keep angle-bracket placeholder defaults that could be mistaken for concrete evidence." >&2
  exit 1
fi

if ! grep -Fq 'scripts/validate-pull-request-evidence.sh' "$WORKFLOW"; then
  echo "Workflow does not invoke the pull-request evidence validator script." >&2
  exit 1
fi

if ! grep -Fq 'github.event.pull_request.body' "$WORKFLOW"; then
  echo "Workflow does not pass the pull request body into the validator." >&2
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

if ! grep -Fq 'edited' "$WORKFLOW"; then
  echo "Workflow must rerun when the pull request body is edited." >&2
  exit 1
fi

positive_body="$(cat <<'EOF'
## Description

Tighten PR governance around fail-first proof.

## Related Issues

Refs #426

## TDD / Validate-First Evidence

- Failing proof before implementation: `bash tests/pull-request-evidence.sh` failed because the validator script and workflow did not exist yet.
- Passing proof after implementation: `bash tests/pull-request-evidence.sh`
- Validate-first exception reference: N/A
- No executable change reason: N/A
EOF
)"

positive_log="$TMP_DIR/positive.log"
docs_log="$TMP_DIR/docs.log"
missing_log="$TMP_DIR/missing.log"
placeholder_log="$TMP_DIR/placeholder.log"
defaults_log="$TMP_DIR/defaults.log"
quick_reference_log="$TMP_DIR/quick-reference.log"

if ! PR_BODY="$positive_body" bash "$VALIDATOR" >"$positive_log" 2>&1; then
  cat "$positive_log" >&2
  echo "Validator rejected a PR body with concrete failing and passing evidence." >&2
  exit 1
fi

docs_only_body="$(cat <<'EOF'
## Description

Refresh documentation wording only.

## Related Issues

Refs #426

## TDD / Validate-First Evidence

- Failing proof before implementation: N/A
- Passing proof after implementation: N/A
- Validate-first exception reference: N/A
- No executable change reason: Documentation-only change; no executable behavior or validation changed.
EOF
)"

if ! PR_BODY="$docs_only_body" bash "$VALIDATOR" >"$docs_log" 2>&1; then
  cat "$docs_log" >&2
  echo "Validator rejected a documentation-only PR body with an explicit no-executable-change reason." >&2
  exit 1
fi

missing_section_body="$(cat <<'EOF'
## Description

Missing the required evidence section.
EOF
)"

if PR_BODY="$missing_section_body" bash "$VALIDATOR" >"$missing_log" 2>&1; then
  echo "Validator unexpectedly accepted a PR body without the evidence section." >&2
  exit 1
fi

if ! grep -Fq 'TDD / Validate-First Evidence section is required.' "$missing_log"; then
  cat "$missing_log" >&2
  echo "Validator did not explain the missing evidence section failure." >&2
  exit 1
fi

placeholder_body="$(cat <<'EOF'
## Description

Still using placeholders.

## TDD / Validate-First Evidence

- Failing proof before implementation: REPLACE_WITH_FAILING_PROOF
- Passing proof after implementation: REPLACE_WITH_PASSING_PROOF
- Validate-first exception reference: N/A
- No executable change reason: N/A
EOF
)"

if PR_BODY="$placeholder_body" bash "$VALIDATOR" >"$placeholder_log" 2>&1; then
  echo "Validator unexpectedly accepted placeholder evidence." >&2
  exit 1
fi

if ! grep -Fq 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' "$placeholder_log"; then
  cat "$placeholder_log" >&2
  echo "Validator did not explain the placeholder evidence failure." >&2
  exit 1
fi

template_default_body="$(cat <<'EOF'
## Description

Still using the instructional defaults.

## TDD / Validate-First Evidence

- Failing proof before implementation: N/A unless the repository instructions explicitly allow validate-first
- Passing proof after implementation: N/A
- Validate-first exception reference: N/A unless the repository instructions explicitly allow validate-first
- No executable change reason: N/A (use this only when no executable behavior or validation changed)
EOF
)"

if PR_BODY="$template_default_body" bash "$VALIDATOR" >"$defaults_log" 2>&1; then
  echo "Validator unexpectedly accepted instructional default text as real evidence." >&2
  exit 1
fi

if ! grep -Fq 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' "$defaults_log"; then
  cat "$defaults_log" >&2
  echo "Validator did not explain why instructional default text is invalid evidence." >&2
  exit 1
fi

quick_reference_default_body="$(cat <<'EOF'
## Description

Still using the quick reference defaults.

## TDD / Validate-First Evidence

- Failing proof before implementation: <command or reproduced defect>
- Passing proof after implementation: <command or validation that now passes>
- Validate-first exception reference: N/A
- No executable change reason: N/A
EOF
)"

if PR_BODY="$quick_reference_default_body" bash "$VALIDATOR" >"$quick_reference_log" 2>&1; then
  echo "Validator unexpectedly accepted quick-reference placeholder evidence." >&2
  exit 1
fi

if ! grep -Fq 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' "$quick_reference_log"; then
  cat "$quick_reference_log" >&2
  echo "Validator did not explain why quick-reference placeholder text is invalid evidence." >&2
  exit 1
fi

failures=0
assert_validation() {
  local name="$1" draft="$2" expected="$3" body="$4" actual=0
  PR_DRAFT="$draft" PR_BODY="$body" bash "$VALIDATOR" >"$TMP_DIR/case.log" 2>&1 || actual=$?
  if [ "$actual" -ne "$expected" ]; then
    printf 'FAIL: %s (expected %s, got %s)\n' "$name" "$expected" "$actual" >&2
    cat "$TMP_DIR/case.log" >&2
    failures=$((failures + 1))
  else
    printf 'PASS: %s\n' "$name"
  fi
}

early_body="${positive_body/\`bash tests\/pull-request-evidence.sh\`$'\n'/N\/A$'\n'}"
empty_body="$(printf '%s\n' "$early_body" | sed 's/^- Failing proof before implementation:.*/- Failing proof before implementation: N\/A/')"
exception_body="${empty_body/Validate-first exception reference: N\/A/Validate-first exception reference: Fixture repository AGENTS.md, Validation Exceptions: validate-first explicitly permitted for generated schema updates; schema validation selected before regeneration.}"
ready_exception_body="${exception_body/Passing proof after implementation: N\/A/Passing proof after implementation: schema validation passed after regeneration.}"
passing_only_body="${empty_body/Passing proof after implementation: N\/A/Passing proof after implementation: schema validation passed.}"
blank_body="${empty_body//N\/A/}"
placeholder_exception_body="${exception_body/Validate-first exception reference: */Validate-first exception reference: REPLACE_WITH_VALIDATE_FIRST_REFERENCE}"

for draft in true false; do
  assert_validation "$draft missing body" "$draft" 1 ''
  assert_validation "$draft missing section" "$draft" 1 "$missing_section_body"
  assert_validation "$draft placeholders" "$draft" 1 "$placeholder_body"
  assert_validation "$draft empty executable evidence" "$draft" 1 "$empty_body"
  assert_validation "$draft blank executable evidence" "$draft" 1 "$blank_body"
  assert_validation "$draft passing without fail-first or exception" "$draft" 1 "$passing_only_body"
  assert_validation "$draft placeholder exception" "$draft" 1 "$placeholder_exception_body"
  assert_validation "$draft unsupported validate-first default" "$draft" 1 "$template_default_body"
  assert_validation "$draft no executable change" "$draft" 0 "$docs_only_body"
  assert_validation "$draft complete fail-first" "$draft" 0 "$positive_body"
  assert_validation "$draft complete validate-first" "$draft" 0 "$ready_exception_body"
done
assert_validation 'Draft fail-first without passing proof' true 0 "$early_body"
assert_validation 'Draft explicit validate-first without passing proof' true 0 "$exception_body"
assert_validation 'Ready fail-first without passing proof' false 1 "$early_body"
assert_validation 'Ready validate-first without passing proof' false 1 "$exception_body"
assert_validation 'missing lifecycle' '' 1 "$positive_body"
assert_validation 'invalid lifecycle' draft 1 "$positive_body"

if [ "$failures" -ne 0 ]; then
  exit 1
fi

if ! grep -Fq "PR_DRAFT: \${{ github.event.pull_request.draft }}" "$WORKFLOW"; then
  echo 'Workflow must pass the actual Draft state as data.' >&2
  exit 1
fi
