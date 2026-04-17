#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/validate-copilot-instructions.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/bin"

cat >"$workspace/bin/npx" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$workspace/bin/npx"

cat >"$workspace/bin/ruby" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$workspace/bin/ruby"

write_common_instruction_file() {
    local target_dir="$1"
    local extra_ai_lines="$2"

    mkdir -p "$target_dir/.github/instructions"

    cat >"$target_dir/.github/copilot-instructions.md" <<EOF
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Test Instructions

These instructions are self-contained for this repository at runtime.
Do not automatically inherit from sibling repositories.

## Always-On Rules

- Quality first.

## Required Validation

- run the relevant checks

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant and why the current code violates it.
- Green CI alone is not enough for AI-generated changes.
$extra_ai_lines
EOF

    cat >"$target_dir/.github/instructions/example.instructions.md" <<'EOF'
---
name: Example
applyTo: "**"
---

# Example Instruction

- Do not automatically inherit from sibling repositories.
EOF
}

run_validator() {
    local repo_type="$1"
    local output_file="$2"

    set +e
    PATH="$workspace/bin:$PATH" REPO_TYPE="$repo_type" \
        bash "$REPO_ROOT/scripts/validate-copilot-instructions.sh" >"$output_file" 2>&1
    local exit_code=$?
    set -e

    return "$exit_code"
}

valid_api_repo="$workspace/valid-api"
mkdir -p "$valid_api_repo"
touch "$valid_api_repo/composer.json"
write_common_instruction_file "$valid_api_repo" '- Reject AI-generated refactors that resolve services inside API resources or serializers, move business logic into presentation code, or repeat request-scoped work that should run once per request.
- Reject AI-generated key or constraint changes that derive identifiers from mutable display names or ignore tenant-scoped uniqueness and database constraints.'

valid_output="$workspace/valid-output.txt"
(
    cd "$valid_api_repo"
    run_validator api "$valid_output"
)

missing_generic_repo="$workspace/missing-generic"
mkdir -p "$missing_generic_repo/.github"
touch "$missing_generic_repo/composer.json"
cat >"$missing_generic_repo/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Broken Instructions

These instructions are self-contained for this repository at runtime.

## Always-On Rules

- Quality first.

## Required Validation

- run the relevant checks
EOF

missing_generic_output="$workspace/missing-generic-output.txt"
set +e
(
    cd "$missing_generic_repo"
    run_validator api "$missing_generic_output"
)
missing_generic_exit=$?
set -e
if [ "$missing_generic_exit" -eq 0 ]; then
    cat "$missing_generic_output"
    echo "validator unexpectedly passed without generic AI findings guidance" >&2
    exit 1
fi
grep -q 'instructions contain AI findings triage guidance' "$missing_generic_output"

missing_api_specific_repo="$workspace/missing-api-specific"
mkdir -p "$missing_api_specific_repo"
touch "$missing_api_specific_repo/composer.json"
write_common_instruction_file "$missing_api_specific_repo" '- Reject AI-generated helper mutations that move executable code across Pest scope boundaries.'

missing_api_specific_output="$workspace/missing-api-specific-output.txt"
set +e
(
    cd "$missing_api_specific_repo"
    run_validator api "$missing_api_specific_output"
)
missing_api_specific_exit=$?
set -e
if [ "$missing_api_specific_exit" -eq 0 ]; then
    cat "$missing_api_specific_output"
    echo "validator unexpectedly passed without API-specific AI risk guidance" >&2
    exit 1
fi
grep -q 'instructions contain repo-specific AI risk guidance' "$missing_api_specific_output"

wrong_license_repo="$workspace/wrong-license"
mkdir -p "$wrong_license_repo"
touch "$wrong_license_repo/composer.json"
write_common_instruction_file "$wrong_license_repo" '- Reject AI-generated refactors that resolve services inside API resources or serializers, move business logic into presentation code, or repeat request-scoped work that should run once per request.
- Reject AI-generated key or constraint changes that derive identifiers from mutable display names or ignore tenant-scoped uniqueness and database constraints.'
cat >"$wrong_license_repo/.github/copilot-instructions.md.license" <<'EOF'
SPDX-License-Identifier: MIT
EOF

wrong_license_output="$workspace/wrong-license-output.txt"
set +e
(
    cd "$wrong_license_repo"
    run_validator api "$wrong_license_output"
)
wrong_license_exit=$?
set -e
if [ "$wrong_license_exit" -eq 0 ]; then
    cat "$wrong_license_output"
    echo "validator unexpectedly accepted wrong copilot-instructions sidecar license" >&2
    exit 1
fi
grep -q 'Sidecar .license exists but does not declare an allowed license' "$wrong_license_output"

android_repo="$workspace/android-repo"
mkdir -p "$android_repo"
touch "$android_repo/capacitor.config.ts"
write_common_instruction_file "$android_repo" '- Reject AI-generated bridge changes that alter listener handles or teardown ordering without focused tests.
- Reject AI-generated back-navigation or managed-mode changes that do not prove WebView history and owner-state invariants.'

android_output="$workspace/android-output.txt"
set +e
(
    cd "$android_repo"
    PATH="$workspace/bin:$PATH" bash "$REPO_ROOT/scripts/validate-copilot-instructions.sh" >"$android_output" 2>&1
)
android_exit=$?
set -e
if [ "$android_exit" -ne 0 ]; then
    cat "$android_output"
    echo "validator failed for valid android fixture" >&2
    exit 1
fi
grep -q 'Repository Type: android' "$android_output"
