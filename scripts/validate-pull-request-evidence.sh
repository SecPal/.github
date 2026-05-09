#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

PR_BODY="${PR_BODY:-}"

require_body() {
  if [ -z "${PR_BODY//[[:space:]]/}" ]; then
    echo "Pull request body is required for PR evidence validation." >&2
    exit 1
  fi
}

require_section() {
  if ! printf '%s\n' "$PR_BODY" | grep -Fq '## TDD / Validate-First Evidence'; then
    echo 'TDD / Validate-First Evidence section is required.' >&2
    exit 1
  fi
}

extract_field() {
  local label="$1"

  printf '%s\n' "$PR_BODY" | sed -nE "s/^[*-][[:space:]]+${label}:[[:space:]]*(.*)$/\1/p" | head -n 1
}

normalize_value() {
  local value="$1"

  value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  if [[ "$value" == \`*\` ]]; then
    value="${value#\`}"
    value="${value%\`}"
  fi
  printf '%s' "$value"
}

is_empty_or_na() {
  local value="$1"

  if [ -z "$value" ]; then
    return 0
  fi

  printf '%s\n' "$value" | grep -qiE '^(n/?a([[:space:][:punct:]].*)?|none|not applicable)$'
}

is_placeholder() {
  local value="$1"

  printf '%s\n' "$value" | grep -qE '^(REPLACE_WITH_(FAILING_PROOF|PASSING_PROOF|VALIDATE_FIRST_REFERENCE|NO_EXECUTABLE_CHANGE_REASON)|<[^<>]+>)$'
}

main() {
  local failing_proof
  local passing_proof
  local validate_first_reference
  local no_executable_change_reason

  require_body
  require_section

  failing_proof="$(normalize_value "$(extract_field 'Failing proof before implementation')")"
  passing_proof="$(normalize_value "$(extract_field 'Passing proof after implementation')")"
  validate_first_reference="$(normalize_value "$(extract_field 'Validate-first exception reference')")"
  no_executable_change_reason="$(normalize_value "$(extract_field 'No executable change reason')")"

  if is_placeholder "$failing_proof" \
    || is_placeholder "$passing_proof" \
    || is_placeholder "$validate_first_reference" \
    || is_placeholder "$no_executable_change_reason"; then
    echo 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' >&2
    exit 1
  fi

  if ! is_empty_or_na "$no_executable_change_reason"; then
    exit 0
  fi

  if ! is_empty_or_na "$failing_proof" && ! is_empty_or_na "$passing_proof"; then
    exit 0
  fi

  echo 'Replace the evidence placeholders with concrete proof or an explicit no-executable-change reason.' >&2
  exit 1
}

main "$@"
