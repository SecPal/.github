#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VALIDATOR="$SCRIPT_DIR/reusable-workflow-timeouts.sh"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/reusable-workflow-policy.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/tests" "$workspace/.github/workflows"
cp "$VALIDATOR" "$workspace/tests/reusable-workflow-timeouts.sh"

run_validator() {
  (
    cd "$workspace"
    bash tests/reusable-workflow-timeouts.sh
  )
}

reset_workflows() {
  rm -f "$workspace"/.github/workflows/reusable-*.yml
  rm -f "$workspace"/.github/workflows/reusable-*.yaml
}

reset_workflows
cat >"$workspace/.github/workflows/reusable-valid.yml" <<'YAML'
---
name: Valid mapping permissions
on:
  workflow_call:
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: "true"
YAML
run_validator

reset_workflows
cat >"$workspace/.github/workflows/reusable-deny-all.yaml" <<'YAML'
---
name: Valid deny-all permissions
on:
  workflow_call:
permissions: {} # Explicitly deny all token scopes.
jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: "true"
YAML
run_validator

reset_workflows
cat >"$workspace/.github/workflows/reusable-missing-permissions.yaml" <<'YAML'
---
name: Missing permissions
on:
  workflow_call:
jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: "true"
YAML
if run_validator >/dev/null 2>&1; then
  echo "Validator accepted a reusable .yaml workflow without top-level permissions." >&2
  exit 1
fi

reset_workflows
cat >"$workspace/.github/workflows/reusable-null-permissions.yml" <<'YAML'
---
name: Null permissions
on:
  workflow_call:
permissions:
jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: "true"
YAML
if run_validator >/dev/null 2>&1; then
  echo "Validator accepted a reusable workflow with null top-level permissions." >&2
  exit 1
fi

reset_workflows
cat >"$workspace/.github/workflows/reusable-missing-timeout.yaml" <<'YAML'
---
name: Missing timeout
on:
  workflow_call:
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - run: "true"
YAML
if run_validator >/dev/null 2>&1; then
  echo "Validator accepted a reusable .yaml workflow without a job timeout." >&2
  exit 1
fi
