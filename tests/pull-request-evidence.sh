#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-pull-request-evidence.sh"
TEMPLATE="$REPO_ROOT/.github/pull_request_template.md"
WORKFLOW="$REPO_ROOT/.github/workflows/pull-request-evidence.yml"
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

if ! grep -Fq '## TDD / Validate-First Evidence' "$TEMPLATE"; then
  echo "PR template is missing the TDD / Validate-First Evidence section." >&2
  exit 1
fi

if ! grep -Fq 'only if the repository instructions explicitly allow validate-first' "$TEMPLATE"; then
  echo "PR template must keep validate-first exceptions explicitly tied to repository instructions." >&2
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
