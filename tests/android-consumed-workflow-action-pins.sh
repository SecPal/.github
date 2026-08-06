#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
full_commit_sha='^[0-9a-f]{40}$'
null_commit_sha='^0{40}$'
documented_source='^[A-Za-z0-9][A-Za-z0-9._/-]*$'
documented_release='^v?[0-9]+([.][0-9]+){2}([-+][A-Za-z0-9.-]+)?$'

is_documented_pin() {
  local reference="$1"
  local version="$2"
  local revision="${reference##*@}"

  [[ "$reference" == *@* ]] || return 1
  [[ "$revision" =~ $full_commit_sha ]] || return 1
  [[ ! "$revision" =~ $null_commit_sha ]] || return 1

  if [[ "${reference%@*}" == */.github/workflows/*.yml ]] ||
    [[ "${reference%@*}" == */.github/workflows/*.yaml ]]; then
    [[ "$version" =~ $documented_source ]] &&
      [[ ! "$version" =~ $full_commit_sha ]]
  else
    [[ "$version" =~ $documented_release ]]
  fi
}

is_accepted_action_pin() {
  local reference="$1"
  local version="$2"

  is_documented_pin "$reference" "$version"
}

has_github_actions_dependabot() {
  local configuration="$1"

  awk '
    function indentation(line) {
      match(line, /[^ ]/)
      return RSTART - 1
    }

    function finish_entry() {
      if (github_actions && root_directory) {
        found = 1
      }
    }

    /^[ ]*-[ ]+package-ecosystem:[ ]*/ {
      finish_entry()
      github_actions = $0 ~ /package-ecosystem:[ ]*"github-actions"[ ]*$/
      root_directory = 0
      entry_indent = indentation($0)
      next
    }

    github_actions &&
      indentation($0) == entry_indent + 2 &&
      $0 ~ /^[ ]*directory:[ ]*"\/"[ ]*$/ {
      root_directory = 1
    }

    END {
      finish_entry()
      exit found ? 0 : 1
    }
  ' <<<"$configuration"
}

# Dependabot owns action references and their version comments. The structural
# guard must accept a valid updated pair without requiring a second fixture.
if ! is_documented_pin \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' 'v1.2.3'; then
  echo "Rejected a structurally documented action pin." >&2
  exit 1
fi

if ! is_documented_pin \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' '1.2.3'; then
  echo "Rejected an exact release without a v prefix." >&2
  exit 1
fi

if ! is_documented_pin \
  'example/workflows/.github/workflows/check.yml@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' 'main'; then
  echo "Rejected a documented branch workflow pin." >&2
  exit 1
fi

for invalid_fixture in \
  'actions/example@v1|v1' \
  'actions/example@abcdef0|v1' \
  'actions/example@AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|v1.2.3' \
  'actions/example@0000000000000000000000000000000000000000|v1.2.3' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|v1' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|main' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|#v1'; do
  IFS='|' read -r reference version <<<"$invalid_fixture"
  if is_documented_pin "$reference" "$version"; then
    echo "Accepted an invalid action pin fixture: $invalid_fixture" >&2
    exit 1
  fi
done

if ! is_accepted_action_pin \
  'actions/cache@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' 'v6.1.1'; then
  echo "Rejected a structurally valid Dependabot-managed action update." >&2
  exit 1
fi

has_github_actions_dependabot $'updates:\n  - package-ecosystem: "github-actions"\n    directory: "/"'
if has_github_actions_dependabot $'updates:\n  # - package-ecosystem: "github-actions"'; then
  echo "Accepted commented-out GitHub Actions Dependabot coverage." >&2
  exit 1
fi
if has_github_actions_dependabot $'updates:\n  - package-ecosystem: "github-actions"\n    directory: "/not-root"'; then
  echo "Accepted GitHub Actions Dependabot coverage outside the workflow root." >&2
  exit 1
fi

governance_checkout_workflows=(
  reusable-ai-instructions.yml
  reusable-markdown-lint.yml
)

for workflow in "${governance_checkout_workflows[@]}"; do
  workflow_path="$repo_root/.github/workflows/$workflow"
  if ! grep -q '^      governance-ref:$' "$workflow_path"; then
    echo "$workflow: deprecated governance-ref compatibility input was removed." >&2
    exit 1
  fi
  if grep -Fq "ref: \${{ inputs.governance-ref }}" "$workflow_path"; then
    echo "$workflow: governance checkout remains caller-selectable." >&2
    exit 1
  fi
  grep -Fq "repository: \${{ fromJSON(toJSON(job)).workflow_repository }}" "$workflow_path"
  grep -Fq "ref: \${{ fromJSON(toJSON(job)).workflow_sha }}" "$workflow_path"
done

while IFS= read -r workflow_path; do
  workflow="${workflow_path##*/}"

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
    if ! is_accepted_action_pin "$reference" "$version"; then
      echo "$workflow: external action is not a documented full-SHA pin: $payload" >&2
      exit 1
    fi
  done < <(grep -E '^[[:space:]]*(-[[:space:]]+)?uses:' "$workflow_path")
done < <(find "$repo_root/.github/workflows" -maxdepth 1 -type f \
  \( -name '*.yml' -o -name '*.yaml' \) -print | sort)

has_github_actions_dependabot "$(<"$repo_root/.github/dependabot.yml")"

echo "Workflow external action and reusable-workflow pins verified."
