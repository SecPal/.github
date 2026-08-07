#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow_path="$repo_root/.github/workflows/reusable-copilot-instructions.yml"
# shellcheck source=tests/android-consumed-workflow-action-pins.sh
# shellcheck disable=SC1091 # Source path is resolved through repo_root at runtime.
source "$repo_root/tests/android-consumed-workflow-action-pins.sh"

assert_immutable_provenance() {
  local path="$1"

  node - "$repo_root" "$path" <<'NODE' || return 1
const fs = require("node:fs");
const path = require("node:path");
const repoRoot = process.argv[2];
const workflowPath = process.argv[3];
const yaml = require(path.join(repoRoot, "node_modules/js-yaml"));
const workflow = yaml.load(fs.readFileSync(workflowPath, "utf8"));
const compatibilityInput = workflow?.on?.workflow_call?.inputs?.["governance-ref"];

if (!compatibilityInput ||
    !compatibilityInput.description?.includes("Deprecated compatibility input.")) {
  process.exit(1);
}

const validateSteps = workflow?.jobs?.validate?.steps || [];
if (JSON.stringify(workflow?.jobs || {}).includes("governance-ref")) process.exit(1);

const governanceCheckouts = validateSteps.filter(
  (step) => step?.with?.path === ".secpal-governance",
);
if (governanceCheckouts.length !== 1) process.exit(1);

const governanceCheckout = governanceCheckouts[0];
if (Object.hasOwn(governanceCheckout, "if")) process.exit(1);
if (!/^actions\/checkout@[0-9a-f]{40}$/.test(governanceCheckout.uses)) process.exit(1);
if (governanceCheckout.with.repository !==
    "${{ fromJSON(toJSON(job)).workflow_repository }}") process.exit(1);
if (governanceCheckout.with.ref !==
    "${{ fromJSON(toJSON(job)).workflow_sha }}") process.exit(1);

const dependencySteps = validateSteps.filter(
  (step) => step?.name === "Install governance Node dependencies",
);
if (dependencySteps.length !== 1) process.exit(1);
const dependencyStep = dependencySteps[0];
if (Object.hasOwn(dependencyStep, "if")) process.exit(1);
if (dependencyStep["working-directory"] !== ".secpal-governance") process.exit(1);
if (!dependencyStep.run?.includes("npm ci") ||
    !dependencyStep.run?.includes('$PWD/node_modules/.bin')) process.exit(1);

const validatorSteps = validateSteps.filter(
  (step) => step?.name === "Run validation script",
);
if (validatorSteps.length !== 1) process.exit(1);
const validatorStep = validatorSteps[0];
if (Object.hasOwn(validatorStep, "if")) process.exit(1);
if (validatorStep.env?.VALIDATOR_PATH !==
    "./.secpal-governance/scripts/validate-copilot-instructions.sh") process.exit(1);
if (validatorStep.run !== "$VALIDATOR_PATH") process.exit(1);
NODE

  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_action_definition_pins "$path" "${path#"$repo_root"/}"
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

replace_once() {
  local path="$1"
  local expected="$2"
  local replacement="$3"

  node - "$path" "$expected" "$replacement" <<'NODE'
const fs = require("node:fs");
const path = process.argv[2];
const expected = process.argv[3];
const replacement = process.argv[4];
const source = fs.readFileSync(path, "utf8");
const first = source.indexOf(expected);
if (first === -1 || source.indexOf(expected, first + expected.length) !== -1) {
  process.exit(1);
}
fs.writeFileSync(path, source.slice(0, first) + replacement + source.slice(first + expected.length));
NODE
}

same_repository_skip_fixture="$workspace/same-repository-skip.yml"
cp "$workflow_path" "$same_repository_skip_fixture"
replace_once "$same_repository_skip_fixture" \
  $'      - name: Checkout governance repository\n        uses:' \
  $'      - name: Checkout governance repository\n        if: ${{ github.repository != '\''SecPal/.github'\'' }}\n        uses:'
assert_rejected 'same-repository caller skips immutable governance checkout' \
  "$same_repository_skip_fixture"

mutable_ref_fixture="$workspace/mutable-ref.yml"
cp "$workflow_path" "$mutable_ref_fixture"
# shellcheck disable=SC2016 # GitHub expressions are literal fixture content.
replace_once "$mutable_ref_fixture" \
  '          ref: ${{ fromJSON(toJSON(job)).workflow_sha }}' \
  '          ref: ${{ inputs.governance-ref }}'
assert_rejected 'caller-selectable governance ref' "$mutable_ref_fixture"

mutable_repository_fixture="$workspace/mutable-repository.yml"
cp "$workflow_path" "$mutable_repository_fixture"
# shellcheck disable=SC2016 # GitHub expressions are literal fixture content.
replace_once "$mutable_repository_fixture" \
  '          repository: ${{ fromJSON(toJSON(job)).workflow_repository }}' \
  '          repository: SecPal/.github'
assert_rejected 'hard-coded governance repository' "$mutable_repository_fixture"

decoy_fixture="$workspace/decoy.yml"
cp "$workflow_path" "$decoy_fixture"
replace_once "$decoy_fixture" \
  $'          repository: ${{ fromJSON(toJSON(job)).workflow_repository }}\n          ref: ${{ fromJSON(toJSON(job)).workflow_sha }}' \
  $'          repository: ${{ github.repository }}\n          ref: "${{ inputs.governance-ref }}"'
replace_once "$decoy_fixture" \
  $'        env:\n          VALIDATOR_PATH:' \
  $'        env:\n          repository: ${{ fromJSON(toJSON(job)).workflow_repository }}\n          ref: ${{ fromJSON(toJSON(job)).workflow_sha }}\n          VALIDATOR_PATH:'
assert_rejected 'immutable provenance strings outside governance checkout' "$decoy_fixture"

caller_dependencies_fixture="$workspace/caller-dependencies.yml"
cp "$workflow_path" "$caller_dependencies_fixture"
replace_once "$caller_dependencies_fixture" \
  '        working-directory: .secpal-governance' \
  '        working-directory: .'
assert_rejected 'governance dependencies installed from caller checkout' \
  "$caller_dependencies_fixture"

caller_validator_fixture="$workspace/caller-validator.yml"
cp "$workflow_path" "$caller_validator_fixture"
replace_once "$caller_validator_fixture" \
  '          VALIDATOR_PATH: ./.secpal-governance/scripts/validate-copilot-instructions.sh' \
  '          VALIDATOR_PATH: ./scripts/validate-copilot-instructions.sh'
assert_rejected 'validator executed from caller checkout' "$caller_validator_fixture"

mutable_action_fixture="$workspace/mutable-action.yml"
cp "$workflow_path" "$mutable_action_fixture"
replace_once "$mutable_action_fixture" \
  'actions/setup-node@820762786026740c76f36085b0efc47a31fe5020' \
  'actions/setup-node@v7'
assert_rejected 'mutable external action tag' "$mutable_action_fixture"

echo 'Reusable Copilot workflow provenance invariants passed.'
