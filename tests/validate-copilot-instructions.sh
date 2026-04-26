#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$REPO_ROOT/tests/fixtures/validate-copilot-instructions"

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

    PATH="$workspace/bin:$PATH" REPO_TYPE="$repo_type" \
        bash "$REPO_ROOT/scripts/validate-copilot-instructions.sh" >"$output_file" 2>&1
    return $?
}

valid_api_repo="$workspace/valid-api"
mkdir -p "$valid_api_repo"
touch "$valid_api_repo/composer.json"
valid_api_extra_ai_lines="$(cat <<'EOF'
- Reject AI-generated refactors that resolve services inside API resources or serializers, move business logic into presentation code, or repeat request-scoped work that should run once per request.
- Reject AI-generated key or constraint changes that derive identifiers from mutable display names or ignore tenant-scoped uniqueness and database constraints.
EOF
)"
write_common_instruction_file "$valid_api_repo" "$valid_api_extra_ai_lines"

valid_output="$workspace/valid-output.txt"
(
    cd "$valid_api_repo"
    run_validator api "$valid_output"
)
grep -q 'copilot-instructions.md has REUSE license' "$valid_output"

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
write_common_instruction_file "$missing_api_specific_repo" '- Reject AI-generated refactors that resolve services inside API resources or serializers, move business logic into presentation code, or repeat request-scoped work that should run once per request.'

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
write_common_instruction_file "$wrong_license_repo" "$valid_api_extra_ai_lines"
# Keep an Apache-2.0 sidecar fixture here because this validator must reject
# Apache-2.0 for .github/copilot-instructions.md.license.
cp "$FIXTURES_DIR/wrong-copilot-instructions-license-fixture.txt" \
    "$wrong_license_repo/.github/copilot-instructions.md.license"

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

negative_inherit_repo="$workspace/negative-inherit"
mkdir -p "$negative_inherit_repo"
touch "$negative_inherit_repo/composer.json"
negative_inherit_extra_ai_lines="$valid_api_extra_ai_lines"
write_common_instruction_file "$negative_inherit_repo" "$negative_inherit_extra_ai_lines"
cat >"$negative_inherit_repo/.github/instructions/negative.instructions.md" <<'EOF'
---
name: Negative Inherit Example
applyTo: "**"
---

# Negative Inherit Example

- Do not inherit from sibling repositories.
EOF

negative_inherit_output="$workspace/negative-inherit-output.txt"
set +e
(
    cd "$negative_inherit_repo"
    run_validator api "$negative_inherit_output"
)
negative_inherit_exit=$?
set -e
if [ "$negative_inherit_exit" -ne 0 ]; then
    cat "$negative_inherit_output"
    echo "validator falsely rejected negative do-not-inherit wording" >&2
    exit 1
fi
grep -q 'instructions avoid pseudo-inheritance markers' "$negative_inherit_output"

android_repo="$workspace/android-repo"
mkdir -p "$android_repo"
touch "$android_repo/capacitor.config.ts"
write_common_instruction_file "$android_repo" '- Reject AI-generated bridge changes that alter listener handles or teardown ordering without focused tests.
- Reject AI-generated back-navigation or managed-mode changes that do not prove WebView history and owner-state invariants.'

android_output="$workspace/android-output.txt"
set +e
(
    cd "$android_repo"
    run_validator android "$android_output"
)
android_exit=$?
set -e
if [ "$android_exit" -ne 0 ]; then
    cat "$android_output"
    echo "validator failed for valid android fixture" >&2
    exit 1
fi
grep -q 'Repository Type: android' "$android_output"
