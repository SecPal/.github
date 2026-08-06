#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

  is_documented_pin "$reference" "$version" || return 1

  if [[ "${VERIFY_ACTION_PIN_PROVENANCE:-false}" != "true" ]]; then
    return 0
  fi

  if [[ "${reference%@*}" == */.github/workflows/*.yml ]] ||
    [[ "${reference%@*}" == */.github/workflows/*.yaml ]]; then
    verify_reusable_workflow_pin "$reference" "$version"
  else
    verify_action_release_pin "$reference" "$version"
  fi
}

release_pin_matches_refs() {
  local reference="$1"
  local version="$2"
  local direct_revision=""
  local peeled_revision=""
  local candidate_revision candidate_ref
  local tag_ref="refs/tags/$version"

  is_documented_pin "$reference" "$version" || return 1

  while IFS=$'\t' read -r candidate_revision candidate_ref; do
    [[ "$candidate_revision" =~ $full_commit_sha ]] || continue
    case "$candidate_ref" in
      "$tag_ref") direct_revision="$candidate_revision" ;;
      "$tag_ref^{}") peeled_revision="$candidate_revision" ;;
    esac
  done

  [[ -n "${peeled_revision:-$direct_revision}" ]] || return 1
  [[ "${reference##*@}" == "${peeled_revision:-$direct_revision}" ]]
}

verified_release_pins=()

verify_action_release_pin() {
  local reference="$1"
  local version="$2"
  local source="${reference%@*}"
  local cache_key="$reference|$version"
  local cached_key owner repository remote_source tag_refs

  [[ "$source" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$ ]] || return 1
  IFS='/' read -r owner repository _ <<<"$source"
  remote_source="$owner/$repository"
  for cached_key in "${verified_release_pins[@]}"; do
    [[ "$cached_key" == "$cache_key" ]] && return 0
  done

  tag_refs="$(
    git ls-remote --tags "https://github.com/$remote_source.git" \
      "refs/tags/$version" "refs/tags/$version^{}"
  )" || return 1
  release_pin_matches_refs "$reference" "$version" <<<"$tag_refs" || return 1
  verified_release_pins+=("$cache_key")
}

verify_reusable_workflow_pin() {
  local reference="$1"
  local branch="$2"
  local workflow_source="${reference%@*}"
  local repository_source="${workflow_source%%/.github/workflows/*}"
  local expected_repository="${GITHUB_REPOSITORY:-SecPal/.github}"
  local base_revision="${SECPAL_BASE_REVISION:-}"
  local candidate

  [[ "$repository_source" == "$expected_repository" ]] || return 1

  if [[ -n "$base_revision" ]]; then
    base_revision="$(git -C "$repo_root" rev-parse --verify "$base_revision^{commit}")" || return 1
  else
    for candidate in "refs/heads/$branch" "refs/remotes/origin/$branch"; do
      if base_revision="$(git -C "$repo_root" rev-parse --verify "$candidate^{commit}" 2>/dev/null)"; then
        break
      fi
      base_revision=""
    done
  fi

  [[ -n "$base_revision" ]] || return 1
  git -C "$repo_root" merge-base --is-ancestor "${reference##*@}" "$base_revision"
}

list_yaml_action_references() {
  local action_definition_path="$1"
  local parser=()
  local yaml_json

  if [[ -x "$repo_root/node_modules/.bin/js-yaml" ]]; then
    parser=("$repo_root/node_modules/.bin/js-yaml")
  elif command -v npx >/dev/null 2>&1; then
    parser=(npx --yes js-yaml@4.2.0)
  else
    echo "Action reference validation requires npm dependencies or npx." >&2
    return 1
  fi

  yaml_json="$("${parser[@]}" "$action_definition_path")" || return 1
  # shellcheck disable=SC2016 # JavaScript template literals are intentionally passed verbatim.
  printf '%s\n' "$yaml_json" |
    node -e '
      const fs = require("node:fs");
      const sourceName = process.argv[1];
      const definition = JSON.parse(fs.readFileSync(0, "utf8"));
      const references = [];

      function addReference(value, location) {
        if (typeof value !== "string" || value.includes("\n")) {
          process.stderr.write(`${sourceName}: ${location} must be a single-line string\n`);
          process.exitCode = 1;
          return;
        }
        references.push(value);
      }

      function visit(value, location) {
        if (!value || typeof value !== "object") return;
        if (Array.isArray(value)) {
          value.forEach((item, index) => visit(item, `${location}[${index}]`));
          return;
        }
        for (const [key, child] of Object.entries(value)) {
          const childLocation = location ? `${location}.${key}` : key;
          if (key === "uses") addReference(child, childLocation);
          visit(child, childLocation);
        }
      }

      visit(definition, "");

      if (!process.exitCode) process.stdout.write(references.join("\n"));
    ' "$action_definition_path"
}

validate_action_definition_pins() {
  local action_definition_path="$1"
  local action_definition="${2:-${action_definition_path#"$repo_root"/}}"
  local parsed_references documented_references parsed_sorted documented_sorted
  local line payload reference version

  parsed_references="$(list_yaml_action_references "$action_definition_path")" || return 1
  if ! documented_references="$({
    while IFS= read -r line; do
      payload="$(sed -E 's/^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*//' <<<"$line")"
      reference="${payload%%[[:space:]#]*}"
      if [[ "$reference" == ./* ]]; then
        printf '%s\n' "$reference"
        continue
      fi
      if [[ ! "$payload" =~ ^([^[:space:]#]+)[[:space:]]+#[[:space:]]+([^[:space:]#]+)[[:space:]]*$ ]]; then
        echo "$action_definition: external action lacks same-line version documentation: $payload" >&2
        return 1
      fi

      reference="${BASH_REMATCH[1]}"
      version="${BASH_REMATCH[2]}"
      if ! is_accepted_action_pin "$reference" "$version"; then
        echo "$action_definition: external action is not a verified documented full-SHA pin: $payload" >&2
        return 1
      fi
      printf '%s\n' "$reference"
    done < <(grep -E '^[[:space:]]*(-[[:space:]]+)?uses:' "$action_definition_path" || true)
  })"; then
    return 1
  fi

  parsed_sorted="$(printf '%s\n' "$parsed_references" | sed '/^$/d' | LC_ALL=C sort)"
  documented_sorted="$(printf '%s\n' "$documented_references" | sed '/^$/d' | LC_ALL=C sort)"
  if [[ "$parsed_sorted" != "$documented_sorted" ]]; then
    echo "$action_definition: every uses reference must use canonical 'uses:' YAML with required same-line provenance." >&2
    return 1
  fi
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

main() {
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

if ! is_documented_pin \
  'actions/cache@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' 'v6.1.1'; then
  echo "Rejected a structurally valid Dependabot-managed action update." >&2
  exit 1
fi

lightweight_tag_refs=$'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/v6.1.1'
if ! release_pin_matches_refs \
  'actions/cache@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' \
  'v6.1.1' <<<"$lightweight_tag_refs"; then
  echo "Rejected a release pin that matches its lightweight tag." >&2
  exit 1
fi
if release_pin_matches_refs \
  'actions/cache@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  'v6.1.1' <<<"$lightweight_tag_refs"; then
  echo "Accepted a release pin whose SHA does not match its documented tag." >&2
  exit 1
fi

annotated_tag_refs=$'cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v6.1.1\nbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/v6.1.1^{}'
if ! release_pin_matches_refs \
  'actions/cache@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' \
  'v6.1.1' <<<"$annotated_tag_refs"; then
  echo "Rejected a release pin that matches an annotated tag commit." >&2
  exit 1
fi
if release_pin_matches_refs \
  'actions/cache@cccccccccccccccccccccccccccccccccccccccc' \
  'v6.1.1' <<<"$annotated_tag_refs"; then
  echo "Accepted an annotated tag object instead of its commit." >&2
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

while IFS= read -r action_definition_path; do
  validate_action_definition_pins "$action_definition_path" || exit 1
done < <(
  {
    find "$repo_root/.github/workflows" -maxdepth 1 -type f \
      \( -name '*.yml' -o -name '*.yaml' \) -print
    find "$repo_root/.github/actions" -type f \
      \( -name 'action.yml' -o -name 'action.yaml' \) -print
  } | sort
)

has_github_actions_dependabot "$(<"$repo_root/.github/dependabot.yml")"

if [[ "${VERIFY_ACTION_PIN_PROVENANCE:-false}" == "true" ]]; then
  echo "Workflow and composite-action external pin provenance verified."
else
  echo "Workflow and composite-action external pin structure verified."
fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
