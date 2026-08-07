#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow_path="$repo_root/.github/workflows/reusable-copilot-instructions.yml"

assert_immutable_provenance() {
  local path="$1"
  local uses_count pinned_uses_count

  grep -Fqx '      governance-ref:' "$path" || return 1
  grep -Fq 'Deprecated compatibility input.' "$path" || return 1
  if grep -Fq "ref: \${{ inputs.governance-ref }}" "$path"; then
    return 1
  fi
  grep -Fqx "          repository: \${{ fromJSON(toJSON(job)).workflow_repository }}" "$path" || return 1
  grep -Fqx "          ref: \${{ fromJSON(toJSON(job)).workflow_sha }}" "$path" || return 1

  uses_count="$(grep -Ec '^[[:space:]]+uses:[[:space:]]+' "$path")"
  pinned_uses_count="$(grep -Ec '^[[:space:]]+uses:[[:space:]]+[^@[:space:]]+@[0-9a-f]{40}[[:space:]]+#[[:space:]]+v[0-9]+([.][0-9]+){2}([-.+][A-Za-z0-9.-]+)?$' "$path")"
  [ "$uses_count" -gt 0 ] && [ "$uses_count" -eq "$pinned_uses_count" ] || return 1
}

assert_immutable_provenance "$workflow_path"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/reusable-copilot-provenance.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

assert_rejected() {
  local scenario="$1"
  local fixture="$2"

  if assert_immutable_provenance "$fixture" >/dev/null 2>&1; then
    echo "Accepted mutable Copilot workflow provenance: $scenario" >&2
    exit 1
  fi
}

mutable_ref_fixture="$workspace/mutable-ref.yml"
cp "$workflow_path" "$mutable_ref_fixture"
sed -i 's|ref: ${{ fromJSON(toJSON(job)).workflow_sha }}|ref: ${{ inputs.governance-ref }}|' \
  "$mutable_ref_fixture"
assert_rejected 'caller-selectable governance ref' "$mutable_ref_fixture"

mutable_repository_fixture="$workspace/mutable-repository.yml"
cp "$workflow_path" "$mutable_repository_fixture"
sed -i 's|repository: ${{ fromJSON(toJSON(job)).workflow_repository }}|repository: SecPal/.github|' \
  "$mutable_repository_fixture"
assert_rejected 'hard-coded governance repository' "$mutable_repository_fixture"

mutable_action_fixture="$workspace/mutable-action.yml"
cp "$workflow_path" "$mutable_action_fixture"
sed -i 's|actions/checkout@[0-9a-f]\{40\}|actions/checkout@v7|' "$mutable_action_fixture"
assert_rejected 'mutable external action tag' "$mutable_action_fixture"

echo 'Reusable Copilot workflow provenance invariants passed.'
