#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
full_commit_sha='^[0-9a-f]{40}$'
documented_version='^(main|v[0-9]+([.][0-9]+){0,2}([.-][A-Za-z0-9.-]+)?)$'
github_actions_dependabot='^[[:space:]]*-[[:space:]]+package-ecosystem:[[:space:]]*"github-actions"[[:space:]]*$'

is_documented_pin() {
  local reference="$1"
  local version="$2"
  local revision="${reference##*@}"

  [[ "$reference" == *@* ]] &&
    [[ "$revision" =~ $full_commit_sha ]] &&
    [[ "$version" =~ $documented_version ]]
}

has_github_actions_dependabot() {
  local configuration="$1"

  grep -Eq "$github_actions_dependabot" <<<"$configuration"
}

is_documented_pin \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' 'v1'
is_documented_pin \
  'actions/example@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' 'v1.2.3'

for invalid_fixture in \
  'actions/example@v1|v1' \
  'actions/example@abcdef0|v1' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|version-one'; do
  IFS='|' read -r reference version <<<"$invalid_fixture"
  if is_documented_pin "$reference" "$version"; then
    echo "Accepted an invalid action pin fixture: $invalid_fixture" >&2
    exit 1
  fi
done

has_github_actions_dependabot $'updates:\n  - package-ecosystem: "github-actions"'
if has_github_actions_dependabot $'updates:\n  # - package-ecosystem: "github-actions"'; then
  echo "Accepted commented-out GitHub Actions Dependabot coverage." >&2
  exit 1
fi

workflows=(
  reusable-reuse.yml
  reusable-license-compatibility.yml
  reusable-prettier.yml
  reusable-markdown-lint.yml
  reusable-ai-instructions.yml
  reusable-node-lint.yml
  reusable-node-build.yml
  reusable-check-conflict-markers.yml
  project-automation-core.yml
  draft-pr-reminder.yml
  reusable-pr-size.yml
)

for workflow in "${workflows[@]}"; do
  workflow_path="$repo_root/.github/workflows/$workflow"
  test -f "$workflow_path"

  while IFS= read -r line; do
    payload="$(sed -E 's/^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*//' <<<"$line")"
    if [[ "$payload" == ./* ]]; then
      continue
    fi
    if [[ ! "$payload" =~ ^([^[:space:]#]+)[[:space:]]+#[[:space:]]+([^[:space:]#]+)[[:space:]]*$ ]]; then
      echo "$workflow: external action lacks same-line version documentation: $payload" >&2
      exit 1
    fi

    reference="${BASH_REMATCH[1]}"
    version="${BASH_REMATCH[2]}"
    if ! is_documented_pin "$reference" "$version"; then
      echo "$workflow: external action is not a documented full-SHA pin: $payload" >&2
      exit 1
    fi
  done < <(grep -E '^[[:space:]]*(-[[:space:]]+)?uses:' "$workflow_path")
done

has_github_actions_dependabot "$(<"$repo_root/.github/dependabot.yml")"

echo "Android-consumed reusable workflow action pins verified."
