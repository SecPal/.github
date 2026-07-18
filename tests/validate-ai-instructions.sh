#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$REPO_ROOT/tests/fixtures/validate-ai-instructions"
VALIDATOR="$REPO_ROOT/scripts/validate-ai-instructions.sh"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/validate-ai-instructions.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

MARKDOWNLINT="$REPO_ROOT/node_modules/.bin/markdownlint"
if [ ! -x "$MARKDOWNLINT" ]; then
    echo "repository-pinned markdownlint is required; run npm ci" >&2
    exit 1
fi

write_valid_repo() {
    local target_dir="$1"

    mkdir -p "$target_dir/.github/instructions"
    cp "$REPO_ROOT/.markdownlint.json" "$target_dir/.markdownlint.json"

    cat >"$target_dir/AGENTS.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Repository Runtime Instructions

## Runtime Safety

- Preserve existing work before making changes.
- Validate executable changes with the smallest relevant check.

## Repository Contract

- Keep changes focused on one coherent topic.
EOF

    cat >"$target_dir/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Code Review Profile

Inspect the complete diff and affected execution paths. Report only concise,
actionable findings supported by evidence.

## Review Priorities

- Prioritize correctness, security, privacy, and data integrity.
- Identify missing tests and avoidable complexity.
EOF

    cat >"$target_dir/.github/instructions/example.instructions.md" <<'EOF'
---
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: CC0-1.0
name: Example Workflow Rules
description: Applies focused checks to workflow files.
applyTo: ".github/workflows/**/*.yml"
---

# Example Workflow Rules

- Set explicit permissions for each workflow.
EOF
}

copy_valid_repo() {
    local source_dir="$1"
    local target_dir="$2"

    mkdir -p "$target_dir"
    cp -R "$source_dir/." "$target_dir/"
}

run_validator() {
    local repo_dir="$1"
    local output_file="$2"

    (
        cd "$repo_dir"
        REPO_TYPE=org bash "$VALIDATOR"
    ) >"$output_file" 2>&1
}

assert_passes() {
    local repo_dir="$1"
    local output_file="$2"

    if ! run_validator "$repo_dir" "$output_file"; then
        sed -n '1,240p' "$output_file" >&2
        echo "validator unexpectedly rejected $repo_dir" >&2
        exit 1
    fi
}

assert_fails_with() {
    local repo_dir="$1"
    local expected="$2"
    local output_file
    local exit_code

    output_file="$workspace/$(basename "$repo_dir").output"

    set +e
    run_validator "$repo_dir" "$output_file"
    exit_code=$?
    set -e

    if [ "$exit_code" -eq 0 ]; then
        sed -n '1,240p' "$output_file" >&2
        echo "validator unexpectedly accepted $repo_dir" >&2
        exit 1
    fi

    if ! grep -qF "$expected" "$output_file"; then
        sed -n '1,240p' "$output_file" >&2
        echo "validator failure did not include expected result: $expected" >&2
        exit 1
    fi
}

valid_repo="$workspace/valid-independent-layers"
write_valid_repo "$valid_repo"
valid_output="$workspace/valid-independent-layers.output"
assert_passes "$valid_repo" "$valid_output"
grep -qF 'required instruction files exist' "$valid_output"
grep -qF 'AGENTS.md is readable UTF-8 Markdown' "$valid_output"
grep -qF 'copilot-instructions.md is readable UTF-8 Markdown' "$valid_output"
grep -qF 'AGENTS.md has REUSE license' "$valid_output"
grep -qF 'instruction Markdown passes lint' "$valid_output"
grep -qF 'instruction overlays include valid frontmatter' "$valid_output"
grep -qF 'AGENTS.md stays under runtime discovery size limit' "$valid_output"

# The positive fixture deliberately has different runtime and review content,
# no mirror declaration, no copied overlay body, and none of the former policy
# keywords. Its success is the behavioral contract for independent layers.
if cmp -s "$valid_repo/AGENTS.md" "$valid_repo/.github/copilot-instructions.md"; then
    echo "positive fixture must keep runtime and review instructions independent" >&2
    exit 1
fi
if grep -qiE 'mirror|authoritative sources|always-on rules|AI findings triage' \
    "$valid_repo/.github/copilot-instructions.md"; then
    echo "positive Copilot fixture unexpectedly contains the obsolete mirror contract" >&2
    exit 1
fi

path_argument_output="$workspace/path-argument.output"
bash "$VALIDATOR" "$valid_repo" >"$path_argument_output" 2>&1
grep -qF 'Repository Type: org' "$path_argument_output"

missing_agents_repo="$workspace/missing-agents"
copy_valid_repo "$valid_repo" "$missing_agents_repo"
rm "$missing_agents_repo/AGENTS.md"
assert_fails_with "$missing_agents_repo" 'required instruction files exist'

missing_copilot_repo="$workspace/missing-copilot"
copy_valid_repo "$valid_repo" "$missing_copilot_repo"
rm "$missing_copilot_repo/.github/copilot-instructions.md"
assert_fails_with "$missing_copilot_repo" 'required instruction files exist'

empty_agents_repo="$workspace/empty-agents"
copy_valid_repo "$valid_repo" "$empty_agents_repo"
: >"$empty_agents_repo/AGENTS.md"
assert_fails_with "$empty_agents_repo" 'AGENTS.md is readable UTF-8 Markdown'

empty_copilot_repo="$workspace/empty-copilot"
copy_valid_repo "$valid_repo" "$empty_copilot_repo"
: >"$empty_copilot_repo/.github/copilot-instructions.md"
assert_fails_with "$empty_copilot_repo" 'copilot-instructions.md is readable UTF-8 Markdown'

invalid_utf8_repo="$workspace/invalid-utf8"
copy_valid_repo "$valid_repo" "$invalid_utf8_repo"
printf '\377' >>"$invalid_utf8_repo/AGENTS.md"
assert_fails_with "$invalid_utf8_repo" 'AGENTS.md is readable UTF-8 Markdown'

missing_agents_license_repo="$workspace/missing-agents-license"
copy_valid_repo "$valid_repo" "$missing_agents_license_repo"
sed -i '/SPDX-License''-Identifier:/d' "$missing_agents_license_repo/AGENTS.md"
assert_fails_with "$missing_agents_license_repo" 'AGENTS.md has REUSE license'

missing_copilot_license_repo="$workspace/missing-copilot-license"
copy_valid_repo "$valid_repo" "$missing_copilot_license_repo"
sed -i '/SPDX-License''-Identifier:/d' \
    "$missing_copilot_license_repo/.github/copilot-instructions.md"
assert_fails_with "$missing_copilot_license_repo" 'copilot-instructions.md has REUSE license'

wrong_sidecar_repo="$workspace/wrong-sidecar-license"
copy_valid_repo "$valid_repo" "$wrong_sidecar_repo"
cp "$FIXTURES_DIR/wrong-ai-instructions-license-fixture.txt" \
    "$wrong_sidecar_repo/.github/copilot-instructions.md.license"
assert_fails_with "$wrong_sidecar_repo" \
    'Sidecar .license exists but does not declare an allowed license'

malformed_markdown_repo="$workspace/malformed-markdown"
copy_valid_repo "$valid_repo" "$malformed_markdown_repo"
printf '\n# Second Top-Level Heading\n' \
    >>"$malformed_markdown_repo/.github/copilot-instructions.md"
assert_fails_with "$malformed_markdown_repo" 'instruction Markdown passes lint'

malformed_frontmatter_repo="$workspace/malformed-frontmatter"
copy_valid_repo "$valid_repo" "$malformed_frontmatter_repo"
sed -i '/^applyTo:/d' \
    "$malformed_frontmatter_repo/.github/instructions/example.instructions.md"
assert_fails_with "$malformed_frontmatter_repo" \
    'instruction overlays include valid frontmatter'

unclosed_frontmatter_repo="$workspace/unclosed-frontmatter"
copy_valid_repo "$valid_repo" "$unclosed_frontmatter_repo"
sed -i '7d' \
    "$unclosed_frontmatter_repo/.github/instructions/example.instructions.md"
assert_fails_with "$unclosed_frontmatter_repo" \
    'instruction overlays include valid frontmatter'

malformed_overlay_markdown_repo="$workspace/malformed-overlay-markdown"
copy_valid_repo "$valid_repo" "$malformed_overlay_markdown_repo"
printf '\n# Duplicate Overlay Heading\n' \
    >>"$malformed_overlay_markdown_repo/.github/instructions/example.instructions.md"
assert_fails_with "$malformed_overlay_markdown_repo" 'instruction Markdown passes lint'

oversized_agents_repo="$workspace/oversized-agents"
copy_valid_repo "$valid_repo" "$oversized_agents_repo"
{
    printf '\n## Oversized Fixture\n\n'
    for _ in $(seq 1 700); do
        printf '%s\n' '- filler line to exceed the AGENTS.md runtime discovery byte limit.'
    done
} >>"$oversized_agents_repo/AGENTS.md"
assert_fails_with "$oversized_agents_repo" \
    'AGENTS.md stays under runtime discovery size limit'

oversized_copilot_repo="$workspace/oversized-copilot"
copy_valid_repo "$valid_repo" "$oversized_copilot_repo"
{
    printf '\n## Oversized Fixture\n\n'
    for _ in $(seq 1 700); do
        printf '%s\n' '- filler line to exceed the Copilot instruction discovery byte limit.'
    done
} >>"$oversized_copilot_repo/.github/copilot-instructions.md"
assert_fails_with "$oversized_copilot_repo" \
    'copilot-instructions.md stays under instruction discovery size limit'

no_overlays_repo="$workspace/no-overlays"
copy_valid_repo "$valid_repo" "$no_overlays_repo"
rm -r "$no_overlays_repo/.github/instructions"
no_overlays_output="$workspace/no-overlays.output"
assert_passes "$no_overlays_repo" "$no_overlays_output"
grep -qF 'Skipped (no focused instruction files present)' "$no_overlays_output"

# Execute an unmodified copy of the real validator from a temporary scripts
# directory so its repository-pinned Markdownlint path is absent. Restrict PATH
# to the validator's other required tools and deliberately omit any global
# Markdownlint command.
isolated_root="$workspace/no-markdownlint-toolchain"
isolated_validator="$isolated_root/scripts/validate-ai-instructions.sh"
isolated_bin="$isolated_root/bin"
isolated_repo="$isolated_root/repository"
mkdir -p "$isolated_root/scripts" "$isolated_bin"
cp "$VALIDATOR" "$isolated_validator"
copy_valid_repo "$valid_repo" "$isolated_repo"
for required_tool in dirname grep head find python3 wc; do
    ln -s "$(command -v "$required_tool")" "$isolated_bin/$required_tool"
done

missing_markdownlint_output="$workspace/missing-markdownlint.output"
set +e
(
    cd "$isolated_repo"
    PATH="$isolated_bin" REPO_TYPE=org /bin/bash "$isolated_validator"
) >"$missing_markdownlint_output" 2>&1
missing_markdownlint_status=$?
set -e

if [ "$missing_markdownlint_status" -eq 0 ]; then
    sed -n '1,240p' "$missing_markdownlint_output" >&2
    echo "validator must fail when Markdownlint is unavailable" >&2
    exit 1
fi
grep -qF 'Markdownlint is unavailable' "$missing_markdownlint_output"
grep -qF 'provide it with the committed lockfile dependencies or a compatible global markdownlint' \
    "$missing_markdownlint_output"
if grep -qF 'All tests passed' "$missing_markdownlint_output"; then
    echo "missing Markdownlint must not report overall validation success" >&2
    exit 1
fi

printf 'validate-ai-instructions tests passed\n'
