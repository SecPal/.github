#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
full_commit_sha='^[0-9a-f]{40}$'
documented_version='^v[0-9]+([.][0-9]+){2}([-+][A-Za-z0-9.-]+)?$'

# Keep this offline provenance allowlist synchronized with source-verified
# upstream release tags. Annotated tags use their peeled commit SHA.
verified_action_releases=(
  'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1|v7.0.1'
  'actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1|v3.2.0'
  'actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3|v9.0.0'
  'actions/setup-node@820762786026740c76f36085b0efc47a31fe5020|v7.0.0'
  'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97|v7.0.0'
  'fsfe/reuse-action@676e2d560c9a403aa252096d99fcab3e1132b0f5|v6.0.0'
)

is_verified_action_release() {
  local candidate="$1|$2"
  local verified_release

  for verified_release in "${verified_action_releases[@]}"; do
    if [[ "$verified_release" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

is_documented_pin() {
  local reference="$1"
  local version="$2"
  local revision="${reference##*@}"

  [[ "$reference" == *@* ]] &&
    [[ "$revision" =~ $full_commit_sha ]] &&
    [[ "$version" =~ $documented_version ]] &&
    is_verified_action_release "$reference" "$version"
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

is_documented_pin \
  'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1' 'v7.0.1'

for invalid_fixture in \
  'actions/example@v1|v1' \
  'actions/example@abcdef0|v1' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|v1' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|v1.2' \
  'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1|v7.0.0' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|' \
  'actions/example@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|version-one'; do
  IFS='|' read -r reference version <<<"$invalid_fixture"
  if is_documented_pin "$reference" "$version"; then
    echo "Accepted an invalid action pin fixture: $invalid_fixture" >&2
    exit 1
  fi
done

has_github_actions_dependabot $'updates:\n  - package-ecosystem: "github-actions"\n    directory: "/"'
if has_github_actions_dependabot $'updates:\n  # - package-ecosystem: "github-actions"'; then
  echo "Accepted commented-out GitHub Actions Dependabot coverage." >&2
  exit 1
fi
if has_github_actions_dependabot $'updates:\n  - package-ecosystem: "github-actions"\n    directory: "/not-root"'; then
  echo "Accepted GitHub Actions Dependabot coverage outside the workflow root." >&2
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
