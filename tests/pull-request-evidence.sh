#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-pull-request-evidence.sh"
TEMPLATE="$REPO_ROOT/.github/pull_request_template.md"
WORKFLOW="$REPO_ROOT/.github/workflows/pull-request-evidence.yml"

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

if ! PR_BODY="$positive_body" bash "$VALIDATOR" >/tmp/pull-request-evidence-positive.log 2>&1; then
  cat /tmp/pull-request-evidence-positive.log >&2
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

if ! PR_BODY="$docs_only_body" bash "$VALIDATOR" >/tmp/pull-request-evidence-docs.log 2>&1; then
  cat /tmp/pull-request-evidence-docs.log >&2
  echo "Validator rejected a documentation-only PR body with an explicit no-executable-change reason." >&2
  exit 1
fi

missing_section_body="$(cat <<'EOF'
## Description

Missing the required evidence section.
EOF
)"

if PR_BODY="$missing_section_body" bash "$VALIDATOR" >/tmp/pull-request-evidence-missing.log 2>&1; then
  echo "Validator unexpectedly accepted a PR body without the evidence section." >&2
  exit 1
fi

if ! grep -Fq 'TDD / Validate-First Evidence section is required.' /tmp/pull-request-evidence-missing.log; then
  cat /tmp/pull-request-evidence-missing.log >&2
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

if PR_BODY="$placeholder_body" bash "$VALIDATOR" >/tmp/pull-request-evidence-placeholder.log 2>&1; then
  echo "Validator unexpectedly accepted placeholder evidence." >&2
  exit 1
fi

if ! grep -Fq 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' /tmp/pull-request-evidence-placeholder.log; then
  cat /tmp/pull-request-evidence-placeholder.log >&2
  echo "Validator did not explain the placeholder evidence failure." >&2
  exit 1
fi

template_default_body="$(sed \
  -e 's/REPLACE_WITH_FAILING_PROOF/N\/A/' \
  -e 's/REPLACE_WITH_PASSING_PROOF/N\/A/' \
  "$TEMPLATE"
)"

if PR_BODY="$template_default_body" bash "$VALIDATOR" >/tmp/pull-request-evidence-template-default.log 2>&1; then
  echo "Validator unexpectedly accepted the template default no-executable-change placeholder." >&2
  exit 1
fi

if ! grep -Fq 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' /tmp/pull-request-evidence-template-default.log; then
  cat /tmp/pull-request-evidence-template-default.log >&2
  echo "Validator did not explain the template default placeholder failure." >&2
  exit 1
fi
